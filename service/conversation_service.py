"""会话与消息的业务逻辑。

所有方法都显式接收 user_id：越权访问统一按“不存在”处理，避免通过错误信息
探测别人会话的存在性。
"""
from __future__ import annotations

from typing import Optional

from service.memory import build_memory, format_memory
from service.storage import Storage, utc_now, iso

TITLE_MAX_CHARS = 24


class ConversationNotFound(LookupError):
    pass


def make_title(query: str) -> str:
    text = " ".join((query or "").split())
    if len(text) <= TITLE_MAX_CHARS:
        return text
    return text[: TITLE_MAX_CHARS - 1] + "…"


class ConversationService:
    def __init__(self, storage: Storage):
        self.storage = storage

    # ------------------------------------------------------------ 会话
    def create(self, user_id: int, title: str = "") -> dict:
        return self.storage.create_conversation(user_id, title=(title or "").strip())

    def list(self, user_id: int, keyword: str = "") -> list[dict]:
        conversations = self.storage.list_conversations(user_id, keyword=keyword.strip())
        return [self._summary(c) for c in conversations]

    def detail(self, user_id: int, conversation_id: str) -> dict:
        conversation = self._require(user_id, conversation_id)
        messages = self.storage.list_messages(conversation_id)
        return {
            "conversation": self._summary(conversation, len(messages)),
            "messages": [self._message(m) for m in messages],
        }

    def delete(self, user_id: int, conversation_id: str) -> None:
        if not self.storage.delete_conversation(user_id, conversation_id):
            raise ConversationNotFound("会话不存在")

    def clear_memory(self, user_id: int, conversation_id: str) -> dict:
        conversation = self._require(user_id, conversation_id)
        if not self.storage.clear_memory(user_id, conversation_id):
            raise ConversationNotFound("会话不存在")
        messages = self.storage.list_messages(conversation_id)
        return {
            "conversation_id": conversation_id,
            "kept_messages": len(messages),
            "memory_cleared_at": iso(utc_now()),
            "history_kept": True,
        }

    def rename(self, user_id: int, conversation_id: str, title: str) -> dict:
        self._require(user_id, conversation_id)
        self.storage.touch_conversation(conversation_id, title=title.strip()[:40])
        return self._summary(self._require(user_id, conversation_id))

    # ------------------------------------------------------------ 消息
    def append_user_message(self, user_id: int, conversation_id: str, content: str) -> dict:
        conversation = self._require(user_id, conversation_id)
        message = self.storage.add_message(conversation_id, "user", content, status="complete")
        if not conversation["title"]:
            self.storage.touch_conversation(conversation_id, title=make_title(content))
        return message

    def append_assistant_message(
        self,
        user_id: int,
        conversation_id: str,
        content: str,
        sources: Optional[list[dict]] = None,
        status: str = "complete",
        message_id: Optional[str] = None,
    ) -> dict:
        self._require(user_id, conversation_id)
        return self.storage.add_message(
            conversation_id,
            "assistant",
            content,
            sources=sources or [],
            status=status,
            message_id=message_id,
        )

    def memory_context(self, user_id: int, conversation_id: str) -> tuple[str, int]:
        conversation = self._require(user_id, conversation_id)
        turns = build_memory(
            self.storage, conversation_id, since=conversation["memory_cleared_at"]
        )
        return format_memory(turns), len(turns)

    # ------------------------------------------------------------ 内部
    def _require(self, user_id: int, conversation_id: str) -> dict:
        conversation = self.storage.get_conversation(user_id, conversation_id)
        if conversation is None:
            raise ConversationNotFound("会话不存在")
        return conversation

    @staticmethod
    def _summary(conversation: dict, message_count: Optional[int] = None) -> dict:
        return {
            "id": conversation["id"],
            "title": conversation["title"],
            "created_at": conversation["created_at"],
            "updated_at": conversation["updated_at"],
            "memory_cleared_at": conversation["memory_cleared_at"],
            "message_count": (
                conversation.get("message_count", 0)
                if message_count is None
                else message_count
            ),
        }

    @staticmethod
    def _message(message: dict) -> dict:
        return {
            "id": message["id"],
            "role": message["role"],
            "content": message["content"],
            "sources": message.get("sources") or [],
            "status": message.get("status", "complete"),
            "created_at": message["created_at"],
        }
