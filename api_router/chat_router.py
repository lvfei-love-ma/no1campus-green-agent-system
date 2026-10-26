"""聊天接口：SSE 流式回答。

POST /api/chat/stream  前端使用（fetch + ReadableStream）
GET  /api/chat/ask     兼容 EventSource 的旧调用方式
GET  /api/chat/health  索引与模型配置自检（不返回任何密钥）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from api_router.deps import get_current_user
from api_router.response import ok
from retriever.vector_retriever import VectorRetriever, index_is_ready
from service.runtime import get_runtime
from utils.config import FAISS_INDEX_PATH, RETRIEVE_TOP_K, qwen_api_key, qwen_model_name

chat_router = APIRouter(prefix="/chat", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str | None = Field(None, description="为空时自动新建会话")


def _stream_response(chat_service, user, query, conversation_id, request: Request):
    generator = chat_service.stream(
        user,
        query,
        conversation_id=conversation_id,
        should_disconnect=request.is_disconnected,
    )
    return StreamingResponse(generator, media_type="text/event-stream", headers=SSE_HEADERS)


@chat_router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request, user: dict = Depends(get_current_user)):
    return _stream_response(
        get_runtime().chat, user, req.query, req.conversation_id, request
    )


@chat_router.get("/ask")
async def chat_ask(
    request: Request,
    query: str = Query(..., min_length=1, max_length=2000),
    conversation_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    return _stream_response(get_runtime().chat, user, query, conversation_id, request)


@chat_router.get("/health")
def chat_health():
    manifest = VectorRetriever.manifest(FAISS_INDEX_PATH)
    ready = index_is_ready(FAISS_INDEX_PATH)
    return ok(
        {
            "index_ready": ready,
            "index_path": FAISS_INDEX_PATH,
            "index_manifest": manifest,
            "retrieve_top_k": RETRIEVE_TOP_K,
            "model_configured": bool(qwen_model_name and qwen_api_key),
        }
    )
