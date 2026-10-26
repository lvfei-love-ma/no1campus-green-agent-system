"""聊天编排：身份 -> 会话 -> 短期记忆 -> Agent 流式回答 -> 落库。

关键约定：
- 只有一次完整结束的回答才以 status=complete 入库并进入短期记忆；
- 客户端断开或模型异常时，已生成的部分以 status=interrupted 保存，
  历史里标记为“未完成”，不会被当成完整答案；
- SSE 先发 meta（含 conversation_id），前端据此切换/刷新会话列表。
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Awaitable, Callable, Optional

from service.agent_engine import AgentEngine
from service.conversation_service import ConversationNotFound, ConversationService
from service.sse import sse_event
from utils.logger import setup_logger

logger = setup_logger(__name__)

DisconnectCheck = Callable[[], Awaitable[bool]]


class ChatService:
    def __init__(
        self,
        conversations: ConversationService,
        engine: Optional[AgentEngine] = None,
    ):
        self.conversations = conversations
        self.engine = engine or AgentEngine()

    async def stream(
        self,
        user: dict,
        query: str,
        conversation_id: Optional[str] = None,
        should_disconnect: Optional[DisconnectCheck] = None,
    ) -> AsyncIterator[str]:
        query = (query or "").strip()
        if not query:
            yield sse_event("error", {"message": "问题不能为空", "code": "empty_query"})
            return

        user_id = user["id"]
        try:
            if conversation_id:
                conversation = self.conversations.detail(user_id, conversation_id)["conversation"]
                created = False
            else:
                conversation = self.conversations.create(user_id, title="")
                created = True
        except ConversationNotFound:
            yield sse_event(
                "error",
                {"message": "会话不存在或不属于当前用户", "code": "conversation_not_found"},
            )
            return

        conversation_id = conversation["id"]
        # 先取记忆（不包含本轮问题），再保存用户消息
        memory_text, memory_turns = self.conversations.memory_context(user_id, conversation_id)
        user_message = self.conversations.append_user_message(user_id, conversation_id, query)

        content_parts: list[str] = []
        sources: list[dict] = []
        engine_error: Optional[str] = None

        yield sse_event(
            "meta",
            {
                "conversation_id": conversation_id,
                "created": created,
                "user_message_id": user_message["id"],
                "memory_turns": memory_turns,
            },
        )

        try:
            async for item in self.engine.run(query, memory_text):
                if should_disconnect is not None and await should_disconnect():
                    self._persist_partial(user_id, conversation_id, content_parts, sources)
                    return
                item_type = item.get("type")
                if item_type == "answer":
                    delta = item.get("delta") or ""
                    if delta:
                        content_parts.append(delta)
                        yield sse_event("answer", {"delta": delta})
                elif item_type == "sources":
                    new_sources = [s for s in item.get("sources", []) if s and s not in sources]
                    if new_sources:
                        sources.extend(new_sources)
                        yield sse_event("sources", {"sources": new_sources})
                elif item_type == "error":
                    engine_error = item.get("message", "模型调用失败")
                    yield sse_event(
                        "error",
                        {"message": engine_error, "code": item.get("code", "engine_error")},
                    )
        except asyncio.CancelledError:
            self._persist_partial(user_id, conversation_id, content_parts, sources)
            raise
        except GeneratorExit:
            self._persist_partial(user_id, conversation_id, content_parts, sources)
            raise
        except Exception as exc:  # 模型 / 网络 / 索引异常
            logger.exception("Agent 执行异常: %s", exc)
            engine_error = f"服务执行异常：{str(exc)[:200]}"
            yield sse_event("error", {"message": engine_error, "code": "engine_exception"})

        content = "".join(content_parts)
        if not content:
            if not engine_error:
                yield sse_event(
                    "error", {"message": "模型没有返回内容，请稍后重试", "code": "empty_answer"}
                )
            yield sse_event(
                "done",
                {
                    "conversation_id": conversation_id,
                    "message_id": None,
                    "status": "failed",
                    "content_chars": 0,
                    "memory_turns": memory_turns,
                    "sources_count": 0,
                },
            )
            return

        status = "complete" if engine_error is None else "interrupted"
        saved = self._persist(user_id, conversation_id, content, sources, status)
        yield sse_event(
            "done",
            {
                "conversation_id": conversation_id,
                "message_id": saved["id"] if saved else None,
                "status": status,
                "content_chars": len(content),
                "memory_turns": memory_turns,
                "sources_count": len(sources),
            },
        )

    # ------------------------------------------------------------ 落库
    def _persist(
        self,
        user_id: int,
        conversation_id: str,
        content: str,
        sources: list[dict],
        status: str,
    ) -> Optional[dict]:
        try:
            return self.conversations.append_assistant_message(
                user_id, conversation_id, content, sources=sources, status=status
            )
        except Exception:  # pragma: no cover - 落库失败不能影响已输出的内容
            logger.exception("助手消息保存失败")
            return None

    def _persist_partial(
        self, user_id: int, conversation_id: str, content_parts: list[str], sources: list[dict]
    ) -> None:
        content = "".join(content_parts)
        if not content:
            return
        self._persist(user_id, conversation_id, content, sources, "interrupted")
