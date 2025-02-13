from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from typing import List, Optional, AsyncGenerator
import httpx
import os
import json
import re  

# Environment variable configuration for Gemini
class Settings(BaseSettings):
    searxng_url: str = os.getenv("SEARXNG_URL", "http://localhost:8080/search")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY")
    gemini_base_url: str = os.getenv("GEMINI_BASE_URL")

settings = Settings()

app = FastAPI()

# Request model (compatible with OpenAI format)
class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    messages: List[Message]
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False 

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
                "text": f"Question: {user_message}. Respond only 'yes' or 'no'."
            }]}
        ]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(settings.gemini_base_url, json=data, headers=headers, params=params)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"API Error: {response.text}")
        
        result = response.json()
        answer = result["candidates"][0]["content"]["parts"][0]["text"].strip().lower()
        return answer == "yes"

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

@app.post("/v1/chat/completions")
async def chat_completion(request: ChatCompletionRequest):
    user_message = next(
        (msg.content for msg in request.messages if msg.role == "user"),
        None
    )
    if not user_message:
        raise HTTPException(status_code=400, detail="No user message found")

    # ---- 「投資アドバイスをトークン一覧に対して求めている」かどうかを判定 ----
    # ここでは単純に "I want investment advice for the following tokens:" という文字列を利用
    # 正規表現でトークン名を抽出
    pattern = r"investment advice for the following tokens:\s*(.*)"
    match = re.search(pattern, user_message, re.IGNORECASE)

    if match:
        # カンマ区切りなどでトークン名を抽出
        tokens_str = match.group(1)
        tokens = [t.strip() for t in tokens_str.split(",") if t.strip()]

        # SearXNG 検索結果をまとめる
        combined_context = ""
        for token in tokens:
            # "価格トレンド"などを調べたい場合はクエリを工夫
            query = f"{token} price trend"
            search_result = await search_searxng(query)
            combined_context += f"--- Trend search for {token} ---\n{search_result}\n\n"

        # Geminiに投げる
        try:
            # 投資アドバイス用の追加プロンプトに変更しても良い
            # （ここではユーザーメッセージはそのまま利用）
            response_text = await generate_response(user_message, combined_context, request.max_tokens, request.temperature)
            if request.stream:
                # ストリーミング返却
                async def content_generator():
                    for chunk in response_text.split(" "):
                        yield chunk + " "
                return await format_stream_response(content_generator())
            else:
                return format_response(response_text)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Model service error (investment advice mode): {str(e)}"
            )
    else:
        # 通常のフロー
        # 検索が必要かどうか LLM で判断
        do_search = False
        try:
            do_search = await should_search(user_message)
        except Exception as e:
            # 検索判定失敗時はそのまま回答
            pass

        context = ""
        if do_search:
            try:
                context = await search_searxng(user_message)
            except Exception as e:
                if request.stream:
                    async def error_stream():
                        yield "Failed to perform a web search. Attempting to answer directly."
                    return await format_stream_response(error_stream())
                else:
                    return format_response(f"Failed to perform a web search. Attempting to answer directly. Error: {str(e)}")

        # Gemini の API を呼び出して回答を生成
        try:
            if request.stream:
                async def content_generator():
                    response = await generate_response(user_message, context, request.max_tokens, request.temperature)
                    for chunk in response.split(" "):  # ストリーミング用に単語ごとに分割
                        yield chunk + " "
                return await format_stream_response(content_generator())
            else:
                response = await generate_response(user_message, context, request.max_tokens, request.temperature)
                return format_response(response)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Model service error: {str(e)}"
            )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)