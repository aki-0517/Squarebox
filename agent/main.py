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

# 환경 변수 설정 (SearxNG 관련 삭제됨)
class Settings(BaseSettings):
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

# CORS 설정
origins = ["http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"], 
)

# 리크에스트 모델
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
    사용자 메시지에 'I want information for the following tokens: X, Y'가
    포함되어 있다면, 해당 토큰 정보를 Redis의 "tokens" 키에 저장합니다.
    """
    match = re.search(r"I want information for the following tokens:\s*(.+)", user_message)
    if match:
        tokens = match.group(1).split(", ")
        redis_client.set("tokens", json.dumps(tokens))  
        print(f"Saved tokens to Redis: {tokens}")

async def get_tokens_context(user_message: str) -> str:
    """
    릌요자의 메시지에 토큰 지정이 있으면, 각 토큰에 대한 Redis 상의 검색 결과를 연결하여 반환합니다.
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

async def format_stream_response(content_stream: AsyncGenerator[str, None]) -> StreamingResponse:
    """
    비동기 제네레이터의 문자열을 SSE 스트림 응답으로 변환합니다.
    """
    async def generator():
        async for chunk in content_stream:
            yield f"data: {json.dumps({'object': 'chat.completion.chunk', 'choices': [{'delta': {'content': chunk}}]})}\n\n"
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
    최종 텍스트를 Chat Completion 형식의 JSON 페이로드로 변환합니다.
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
    컨텍스트와 릌요자의 퀘리를 포함한 프롬프트를 Gemini에 보내고,
    보완 결과를 반환합니다.
    """
    headers = {
        "Content-Type": "application/json"
    }
    params = {
        "key": settings.gemini_api_key
    }

    prompt = (
        "You are a helpful AI assistant.\n\n"
        "Below is some context, followed by the user's query.\n"
        "Please provide a helpful, coherent answer.\n\n"
        "【Context】\n"
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
        
        # 1) 토큰 정보의 추출과 저장
        await extract_and_store_tokens(user_message)
        
        # 2) Redis에 저장된 토큰 관련 컨텍스트를 가져오기
        token_context = await get_tokens_context(user_message)
        print(f"[DEBUG] Token context: {token_context}")

        # 토큰 데이터가 있으면, 요약하여 반환하기
        if token_context.strip():
            summary_prompt = (
                "You are a helpful AI assistant.\n\n"
                "The user wants information about certain tokens. "
                "Below is the data we have from Redis. "
                "Please summarize it in a user-friendly manner, highlighting key points.\n\n"
                f"【Token Data】\n{token_context}\n"
            )

            if request.stream:
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
                summarized_content = await _summarize(
                    summary_prompt=summary_prompt,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature
                )
                return format_response(summarized_content)

        # 3) 온라인 검색은 수행하지 않고, 빈 컨텍스트로 Gemini에 질의하기
        search_results = ""

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
    

@app.post("/v1/chat/completions/static")
async def chat_completion_static(request: ChatCompletionRequest):
    try:
        static_response = (
            "Information found on HeyAnon. HeyAnon (ANON) is an AI-driven decentralized finance (DeFi) protocol designed to streamline DeFi interactions and consolidate essential project-related information. \n"
            "MESSARI.IO\n\n"
            "As of February 19, 2025, ANON is trading at approximately $7.26, with an intraday high of $8.00 and a low of $3.76. The total supply is capped at 21 million tokens, with about 12.74 million currently in circulation, resulting in a market capitalization of approximately $94.52 million.\n\n"
            "Technical analysis indicates a neutral trend, with key indicators such as moving averages and oscillators not signaling strong buy or sell positions. \n"
            "TRADINGVIEW.COM\n\n"
            "Price predictions for ANON vary among analysts. Some forecasts suggest that ANON could reach $10.90 by the end of 2025, potentially climbing to $12.90 in 2026 and $18.07 by 2027. \n"
            "DIGITALCOINPRICE.COM\n"
            " Conversely, other analyses project a more conservative outlook, with ANON trading between $2.50 and $3.12 by the end of 2025. \n"
            "CRYPTOTICKER.IO\n\n"
            "Investors should consider both the innovative aspects of HeyAnon and the inherent volatility of the cryptocurrency market. Conducting thorough research and staying informed about market trends is essential before making investment decisions."
        )

        if request.stream:
            async def static_generator() -> AsyncGenerator[str, None]:
                chunk_size = 100
                for i in range(0, len(static_response), chunk_size):
                    yield static_response[i:i+chunk_size]
            return StreamingResponse(
                format_stream_response(static_generator()),
                media_type="text/event-stream"
            )
        else:
            return format_response(static_response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------
# Helper methods for Summaries & Streaming Summaries
# -----------------------------------------------
async def _summarize(summary_prompt: str, max_tokens: int, temperature: float) -> str:
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
    summarized_text = await _summarize(summary_prompt, max_tokens, temperature)
    chunk_size = 100
    for i in range(0, len(summarized_text), chunk_size):
        yield summarized_text[i:i+chunk_size]

async def _streaming_chat(
    user_message: str,
    max_tokens: int,
    temperature: float,
    context: str
) -> AsyncGenerator[str, None]:
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
    if redis_client.exists("tokens"):
        redis_client.delete("tokens")
        return {"message": "Tokens deleted from Redis"}
    return {"error": "No tokens found in Redis"}

@app.post("/redis/search/{query}")
def save_search_results(query: str, search_result: SearchResult):
    search_key = f"search:{query}"
    existing_data = redis_client.get(search_key)
    if existing_data:
        existing_results = json.loads(existing_data)
    else:
        existing_results = []

    existing_results.append(search_result.dict())
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
