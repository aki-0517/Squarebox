from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from typing import List, Optional, AsyncGenerator
import httpx
import os
import json
import re
import redis  

class SearchResult(BaseModel):
    title: str
    content: str
    url: str

# 環境変数の設定
class Settings(BaseSettings):
    searxng_url: str = os.getenv("SEARXNG_URL", "http://localhost:8080/search")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY")
    gemini_base_url: str = os.getenv("GEMINI_BASE_URL")
    redis_host: str = os.getenv("REDIS_HOST", "redis")  
    redis_port: int = int(os.getenv("REDIS_PORT", 6379))  

settings = Settings()

app = FastAPI()

redis_client = redis.StrictRedis(
    host=settings.redis_host, 
    port=settings.redis_port, 
    decode_responses=True
)
# CORS 設定
origins = ["http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"], 
)

# リクエストモデル
class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    messages: List[Message]
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False

async def extract_and_store_tokens(user_message: str):
    """
    If the user's message includes "I want information for the following tokens: X, Y", 
    store those tokens in Redis under the key "tokens".
    """
    match = re.search(r"I want information for the following tokens:\s*(.+)", user_message)
    if match:
        tokens = match.group(1).split(", ")
        redis_client.set("tokens", json.dumps(tokens))  
        print(f"Saved tokens to Redis: {tokens}")

async def get_tokens_context(user_message: str) -> str:
    """
    If the user’s message has a token request, retrieve from Redis all search data for each token.
    Return that as a concatenated string for AI context.
    """
    match = re.search(r"I want information for the following tokens:\s*(.+)", user_message)
    if not match:
        return ""
    
    tokens = match.group(1).split(", ")
    context_parts = []
    
    for token in tokens:
        search_data = redis_client.get(f"search:{token}")
        if search_data:
            results = json.loads(search_data)
            for result in results:
                part = (
                    f"Token: {token}\n"
                    f"Title: {result.get('title', '')}\n"
                    f"Content: {result.get('content', '')}\n"
                    f"URL: {result.get('url', '')}\n\n"
                )
                context_parts.append(part)
    return "\n".join(context_parts)

async def search_searxng(query: str) -> str:
    """
    Search SearxNG with the user query, cache top 3 results in Redis for 1 hour.
    """
    try:
        # Redis に保存された検索結果があるかチェック
        cached_results = redis_client.get(f"search:{query}")
        if cached_results:
            print(f"Cache hit for query: {query}")
            return json.loads(cached_results)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                settings.searxng_url,
                params={"q": query, "format": "json"}
            )
            response.raise_for_status()
            results = response.json().get("results", [])

            top_results = [
                {
                    "title": result.get("title", ""),
                    "content": result.get("content", result.get("snippet", "")),
                    "url": result.get("url", "")
                }
                for result in results[:3]
            ]

            redis_client.setex(f"search:{query}", 3600, json.dumps(top_results))
            return top_results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

async def should_search(user_message: str) -> bool:
    """
    Calls Gemini to determine if a search is needed. 
    This is bypassed if we already detect tokens & have them in Redis.
    """
    headers = {
        "Content-Type": "application/json"
    }
    params = {
        "key": settings.gemini_api_key  
    }
    data = {
        "contents": [{
            "parts": [{
                "text": f"""
                Consider the following user query: "{user_message}"
                Determine if an online search is required to answer this query accurately.
                If the query involves recent events, specific brand names, obscure entities, or uncommon technical concepts, answer 'yes'.
                Otherwise, answer 'no'.
                """
            }]}
        ]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(settings.gemini_base_url, json=data, headers=headers, params=params)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"API Error: {response.text}")
        
        result = response.json()
        answer = result["candidates"][0]["content"]["parts"][0]["text"].strip().lower()
        return "yes" in answer

async def format_stream_response(content_stream: AsyncGenerator[str, None]) -> StreamingResponse:
    """
    Converts an async generator of strings into an SSE stream response.
    """
    async def generator():
        async for chunk in content_stream:
            yield f"data: {json.dumps({
                'object': 'chat.completion.chunk',
                'choices': [{
                    'delta': {
                        'content': chunk
                    }
                }]
            })}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }
    )

def format_response(content: str) -> dict:
    """
    Converts final text content into a Chat Completion-like JSON payload.
    """
    return {
        "object": "chat.completion",
        "choices": [{
            'message': {
                'role': 'assistant',
                'content': content
            }
        }]
    }

async def generate_response(
    user_message: str, 
    max_tokens: int, 
    temperature: float, 
    context: str = ""
) -> str:
    """
    Sends the combined prompt (which includes context and user message) to Gemini 
    and returns the best completion from the model.
    """
    headers = {
        "Content-Type": "application/json"
    }
    params = {
        "key": settings.gemini_api_key
    }

    # Create a prompt that references context + user query
    prompt = (
        "You are a helpful AI assistant.\n\n"
        "Below is some context, followed by the user's query.\n"
        "Please provide a helpful, coherent answer.\n\n"
        "【Search Context】\n"
        f"{context}\n\n"
        f"User's Query: {user_message}"
    )

    data = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }],
        "generationConfig": {
            "max_output_tokens": max_tokens,
            "temperature": temperature
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(settings.gemini_base_url, json=data, headers=headers, params=params)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"API Error: {response.text}")

        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]

# -----------------------------
#  Chat Completion Main Endpoint
# -----------------------------
@app.post("/v1/chat/completions")
async def chat_completion(request: ChatCompletionRequest):
    try:
        user_message = request.messages[-1].content
        
        # 1) Extract and store tokens if present
        await extract_and_store_tokens(user_message)
        
        # 2) Retrieve any token-based context from Redis
        token_context = await get_tokens_context(user_message)
        print(f"[DEBUG] Token context: {token_context}")

        # If we found token-based data in Redis, 
        # we will summarize that data in a user-friendly manner.
        if token_context.strip():
            # Create a specialized prompt for summarizing the token context
            summary_prompt = (
                "You are a helpful AI assistant.\n\n"
                "The user wants information about certain tokens. "
                "Below is the data we have from Redis. "
                "Please summarize it in a user-friendly manner, highlighting key points.\n\n"
                f"【Token Search Results】\n{token_context}\n"
            )

            if request.stream:
                # Streaming version
                content_stream = _streaming_summarize(
                    summary_prompt=summary_prompt,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature
                )
                return StreamingResponse(
                    format_stream_response(content_stream),
                    media_type="text/event-stream"
                )
            else:
                # Non-stream version
                summarized_content = await _summarize(
                    summary_prompt=summary_prompt,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature
                )
                return format_response(summarized_content)

        # 3) Otherwise, proceed with the normal logic:
        #    - Check if we *should* search
        #    - Possibly do an online search
        #    - Generate a response based on search results or fallback
        search_results = ""
        if await should_search(user_message):
            try:
                search_results = await search_searxng(user_message)
            except Exception as e:
                print(f"Search failed: {str(e)}")
                search_results = "No relevant search results found. Please answer based on general knowledge."

        # `search_results` might be a list of dicts. Turn it into a string for Gemini
        if isinstance(search_results, list):
            sr_text = ""
            for r in search_results:
                sr_text += (
                    f"Title: {r.get('title', '')}\n"
                    f"Content: {r.get('content', '')}\n"
                    f"URL: {r.get('url', '')}\n\n"
                )
            search_results = sr_text

        if request.stream:
            content_stream = _streaming_chat(
                user_message=user_message,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                context=search_results
            )
            return StreamingResponse(
                format_stream_response(content_stream),
                media_type="text/event-stream"
            )
        else:
            content = await generate_response(
                user_message=user_message,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                context=search_results
            )
            return format_response(content)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------
# Helper methods for Summaries & Streaming Summaries
# -----------------------------------------------
async def _summarize(summary_prompt: str, max_tokens: int, temperature: float) -> str:
    """
    Helper that directly calls Gemini to produce a summary based on 'summary_prompt'.
    """
    headers = {
        "Content-Type": "application/json"
    }
    params = {
        "key": settings.gemini_api_key
    }
    data = {
        "contents": [{
            "parts": [{
                "text": summary_prompt
            }]
        }],
        "generationConfig": {
            "max_output_tokens": max_tokens,
            "temperature": temperature
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(settings.gemini_base_url, json=data, headers=headers, params=params)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"API Error: {response.text}")

        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]

async def _streaming_summarize(summary_prompt: str, max_tokens: int, temperature: float) -> AsyncGenerator[str, None]:
    """
    Example streaming approach (pseudo-code) if your Gemini endpoint supports streaming. 
    If not, you can adapt this to simply yield in chunks or replicate the response in small parts.
    """
    # This is a stand-in generator for demonstration.
    # In practice, you'd call your streaming Gemini API here and yield chunks as they come in.
    summarized_text = await _summarize(summary_prompt, max_tokens, temperature)
    # For demonstration, yield it in small chunks:
    chunk_size = 100
    for i in range(0, len(summarized_text), chunk_size):
        yield summarized_text[i:i+chunk_size]

async def _streaming_chat(
    user_message: str,
    max_tokens: int,
    temperature: float,
    context: str
) -> AsyncGenerator[str, None]:
    """
    Similar approach if you want to streaming-ify normal chat completions.
    """
    # We'll just do a single chunk for demonstration
    complete_answer = await generate_response(
        user_message=user_message,
        max_tokens=max_tokens,
        temperature=temperature,
        context=context
    )
    yield complete_answer

# --------------------
#  Redis Utility Routes
# --------------------
@app.get("/redis/tokens")
def get_tokens():
    tokens_data = redis_client.get("tokens")
    if tokens_data:
        return {"tokens": json.loads(tokens_data)}
    return {"error": "No tokens found"}

@app.delete("/redis/tokens")
def delete_tokens():
    """Redis に保存された tokens データを削除"""
    if redis_client.exists("tokens"):
        redis_client.delete("tokens")
        return {"message": "Tokens deleted from Redis"}
    return {"error": "No tokens found in Redis"}

@app.post("/redis/search/{query}")
def save_search_results(query: str, search_result: SearchResult):
    search_key = f"search:{query}"
    
    # 既存の検索結果を取得
    existing_data = redis_client.get(search_key)
    if existing_data:
        existing_results = json.loads(existing_data)
    else:
        existing_results = []

    # 新しい検索結果を追加
    existing_results.append(search_result.dict())

    # Redis に保存（1時間キャッシュ）
    redis_client.setex(search_key, 3600, json.dumps(existing_results))

    return {"message": f"Search result added for '{query}'", "updated_results": existing_results}

@app.get("/redis/search/{query}")
def get_search_results(query: str):
    search_data = redis_client.get(f"search:{query}")
    if search_data:
        return {"query": query, "results": json.loads(search_data)}
    return {"error": f"No cached results found for {query}"}

@app.delete("/redis/search/{query}")
def delete_search_cache(query: str):
    if redis_client.exists(f"search:{query}"):
        redis_client.delete(f"search:{query}")
        return {"message": f"Search cache for '{query}' deleted"}
    return {"error": f"No cache found for query '{query}'"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
