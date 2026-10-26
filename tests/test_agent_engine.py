"""Agent 事件转换测试：工具结果不能混进回答增量。"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessageChunk, ToolMessage

from service.agent_engine import AgentEngine

TOOL_PAYLOAD = {
    "query": "垃圾分类",
    "count": 1,
    "results": [
        {
            "rank": 1,
            "title": "校园生活垃圾一般怎么分类",
            "category": "垃圾分类",
            "source_name": "国务院办公厅",
            "source_url": "https://www.gov.cn/gongbao/content/2017/content_5186978.htm",
            "published_at": "2017-03-18",
            "content": "正文",
        }
    ],
}


class FakeAgent:
    def __init__(self, events):
        self.events = events

    async def astream(self, payload, stream_mode=None, version=None):
        for event in self.events:
            yield event


def _collect(events):
    engine = AgentEngine(agent_factory=lambda memory: FakeAgent(events))
    return engine


async def _drain(engine):
    items = []
    async for item in engine.run("垃圾分类怎么分", ""):
        items.append(item)
    return items


def test_tool_message_is_not_streamed_as_answer():
    tool_text = json.dumps(TOOL_PAYLOAD, ensure_ascii=False)
    events = [
        {"type": "messages", "data": (AIMessageChunk(content="", id="run-1", tool_call_chunks=[{"name": "vector_retrieve"}]), {})},
        {"type": "messages", "data": (ToolMessage(content=tool_text, tool_call_id="call-1", name="vector_retrieve", id="tool-1"), {})},
        {"type": "messages", "data": (AIMessageChunk(content="根据知识库，", id="run-2"), {})},
        {"type": "messages", "data": (AIMessageChunk(content="垃圾分为四类。", id="run-2"), {})},
        {"type": "updates", "data": {"tools": {"messages": [ToolMessage(content=tool_text, tool_call_id="call-1", name="vector_retrieve")]}}},
    ]
    import asyncio

    items = asyncio.run(_drain(_collect(events)))
    answers = [item["delta"] for item in items if item["type"] == "answer"]
    assert answers == ["根据知识库，", "垃圾分为四类。"]
    assert tool_text not in "".join(answers)

    sources = [source for item in items if item["type"] == "sources" for source in item["sources"]]
    assert sources and sources[0]["title"] == "校园生活垃圾一般怎么分类"
    assert sources[0]["source_url"].startswith("https://www.gov.cn")


def test_json_like_answer_chunk_is_filtered():
    payload = json.dumps({"query": "x", "results": []}, ensure_ascii=False)
    events = [{"type": "messages", "data": (AIMessageChunk(content=payload), {})}]
    import asyncio

    items = asyncio.run(_drain(_collect(events)))
    assert [item for item in items if item["type"] == "answer"] == []
