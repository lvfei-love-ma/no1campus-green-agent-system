"""会话管理接口：新建、列表、详情、删除、重命名、清空短期记忆。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api_router.deps import get_current_user
from api_router.response import ok
from service.conversation_service import ConversationNotFound
from service.runtime import get_runtime

conversation_router = APIRouter(prefix="/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    title: str = Field("", max_length=40)


class RenameConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=40)


def _not_found():
    raise HTTPException(status_code=404, detail="会话不存在")


@conversation_router.post("")
def create_conversation(req: CreateConversationRequest | None = None, user: dict = Depends(get_current_user)):
    service = get_runtime().conversations
    title = req.title if req else ""
    return ok(service.create(user["id"], title), msg="会话已创建")


@conversation_router.get("")
def list_conversations(
    q: str = Query("", max_length=50, description="按标题或消息内容搜索"),
    user: dict = Depends(get_current_user),
):
    service = get_runtime().conversations
    items = service.list(user["id"], keyword=q)
    return ok({"items": items, "total": len(items)})


@conversation_router.get("/{conversation_id}")
def get_conversation(conversation_id: str, user: dict = Depends(get_current_user)):
    service = get_runtime().conversations
    try:
        return ok(service.detail(user["id"], conversation_id))
    except ConversationNotFound:
        _not_found()


@conversation_router.patch("/{conversation_id}")
def rename_conversation(
    conversation_id: str, req: RenameConversationRequest, user: dict = Depends(get_current_user)
):
    service = get_runtime().conversations
    try:
        return ok(service.rename(user["id"], conversation_id, req.title), msg="标题已更新")
    except ConversationNotFound:
        _not_found()


@conversation_router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str, user: dict = Depends(get_current_user)):
    service = get_runtime().conversations
    try:
        service.delete(user["id"], conversation_id)
    except ConversationNotFound:
        _not_found()
    return ok({"id": conversation_id}, msg="会话已删除")


@conversation_router.post("/{conversation_id}/memory/clear")
def clear_memory(conversation_id: str, user: dict = Depends(get_current_user)):
    service = get_runtime().conversations
    try:
        data = service.clear_memory(user["id"], conversation_id)
    except ConversationNotFound:
        _not_found()
    return ok(
        data,
        msg=f"记忆已清空，历史消息仍保留（当前 {data['kept_messages']} 条）",
    )
