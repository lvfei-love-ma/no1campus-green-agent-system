"""默认回答引擎：LangChain Agent + 知识库检索工具。

只负责把 Agent 的流式输出转换成统一事件字典：
    {"type": "answer", "delta": "..."}
    {"type": "sources", "sources": [...]}
    {"type": "error", "message": "...", "code": "..."}
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Callable, Optional

from utils.logger import setup_logger

logger = setup_logger(__name__)

SOURCE_FIELDS = ("title", "category", "source_name", "source_url", "published_at")


def _sources_from_tool_message(content) -> list[dict]:
    """工具返回的是 JSON 字符串；解析失败就当作没有来源。"""
    if isinstance(content, list):  # 某些版本会把 content 拆成 blocks
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    if not isinstance(content, str):
        return []
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(payload, dict):
        return []
    sources, seen = [], set()
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        source = {key: item.get(key, "") for key in SOURCE_FIELDS}
        key = (source.get("title"), source.get("source_url"))
        if not source.get("title") or key in seen:
            continue
        seen.add(key)
        sources.append(source)
    return sources


class AgentEngine:
    def __init__(self, agent_factory: Optional[Callable] = None):
        self._agent_factory = agent_factory

    async def run(self, query: str, memory_text: str = "") -> AsyncIterator[dict]:
        from langchain_core.messages import AIMessageChunk, ToolMessage

        from agent.chat_agent import build_agent

        factory = self._agent_factory or build_agent
        agent = factory(memory_text)

        tool_call_ids: set = set()
        async for event in agent.astream(
            {"messages": [{"role": "user", "content": query}]},
            stream_mode=["updates", "messages"],
            version="v2",
        ):
            mode = event["type"]
            data = event["data"]
            if mode == "messages":
                message = data[0] if isinstance(data, tuple) else data
                # stream_mode=messages 也会把 ToolMessage（工具返回的 JSON）推出来，
                # 只有 AIMessageChunk 才是给用户的回答增量。
                if isinstance(message, ToolMessage) or not isinstance(message, AIMessageChunk):
                    continue
                if getattr(message, "tool_call_chunks", None):
                    if message.id:
                        tool_call_ids.add(message.id)
                    continue
                if getattr(message, "id", None) in tool_call_ids:
                    continue
                content = message.content if isinstance(message.content, str) else ""
                if content and content.lstrip().startswith('{"query"'):
                    continue
                if content:
                    yield {"type": "answer", "delta": content}
            elif mode == "updates":
                for node_update in data.values():
                    if not isinstance(node_update, dict):
                        continue
                    for message in node_update.get("messages", []):
                        tool_calls = getattr(message, "tool_calls", None)
                        if tool_calls:
                            for call in tool_calls:
                                logger.info("Agent 调用工具: %s", call.get("name"))
                        if isinstance(message, ToolMessage):
                            sources = _sources_from_tool_message(message.content)
                            if sources:
                                yield {"type": "sources", "sources": sources}
