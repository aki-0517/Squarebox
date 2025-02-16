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

# 環境変数の設定
class Settings(BaseSettings):
    searxng_url: str = os.getenv("SEARXNG_URL", "http://localhost:8080/search")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY")
    gemini_base_url: str = os.getenv("GEMINI_BASE_URL")
    redis_host: str = os.getenv("REDIS_HOST", "redis")  
    redis_port: int = int(os.getenv("REDIS_PORT", 6379))  

settings = Settings()

app = FastAPI()

redis_client = redis.StrictRedis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
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
    match = re.search(r"I want information for the following tokens: (.+)", user_message)
    if match:
        tokens = match.group(1).split(", ")
        redis_client.set("tokens", json.dumps(tokens))  
        print(f"Saved tokens to Redis: {tokens}")

async def search_searxng(query: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                settings.searxng_url,
                params={"q": query, "format": "json"}
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            top_results = results[:3]
            return "\n\n".join([
                f"{result.get('title', '')}\n{result.get('content', result.get('snippet', ''))}"
                for result in top_results
            ])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

async def should_search(user_message: str) -> bool:
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
    return {
        "object": "chat.completion",
        "choices": [{
            'message': {
                'role': 'assistant',
                'content': content
            }
        }]
    }

async def generate_response(user_message: str, context: str, max_tokens: int, temperature: float) -> str:
    headers = {
        "Content-Type": "application/json"
    }
    params = {
        "key": settings.gemini_api_key
    }
    prompt = (
        "You are a helpful AI assistant. "
        "Answer the user's question based on the following context.\n\n"
        "【Search Context】\n"
        f"{context}\n\n"
        f"Question: {user_message}"
    )
    
    data = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]}
        ],
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

# Chat Completion API
@app.post("/v1/chat/completions")
async def chat_completion(request: ChatCompletionRequest):
    try:
        user_message = request.messages[-1].content

        extract_and_store_tokens(user_message)

        search_results = ""
        
        if await should_search(user_message):
            try:
                search_results = await search_searxng(user_message)
            except Exception as e:
                print(f"Search failed: {str(e)}")
                search_results = "No relevant search results found. Please answer based on general knowledge."

        if request.stream:
            content_stream = generate_response(
                user_message=user_message,
                context=search_results,
                max_tokens=request.max_tokens,
                temperature=request.temperature
            )
            return StreamingResponse(
                format_stream_response(content_stream),
                media_type="text/event-stream"
            )
        else:
            content = await generate_response(
                user_message=user_message,
                context=search_results,
                max_tokens=request.max_tokens,
                temperature=request.temperature
            )
            return format_response(content)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

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
