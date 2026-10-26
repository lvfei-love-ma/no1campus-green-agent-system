"""SSE 接口测试：事件顺序、增量内容、来源、错误与落库状态。"""
from __future__ import annotations

from service.sse import parse_sse
from tests.conftest import FakeEngine

SOURCE = {
    "title": "教学楼和图书馆的空调应该设多少度",
    "category": "节能用电",
    "source_name": "国务院办公厅",
    "source_url": "https://www.gov.cn/zwgk/2007-06/03/content_634614.htm",
    "published_at": "2007-06-01",
}


def test_stream_emits_meta_answers_sources_done(client, login, runtime):
    runtime.chat.engine = FakeEngine(chunks=["可以把空调", "设在 26℃ 左右。"], sources=[SOURCE])
    login("A")
    res = client.post("/api/chat/stream", json={"query": "宿舍空调开多少度？"})

    events = parse_sse(res.text)
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert names[-1] == "done"
    assert names.count("answer") == 2
    assert "sources" in names
    assert names.index("sources") > names.index("answer")

    meta = events[0][1]
    assert meta["conversation_id"]
    assert meta["created"] is True

    answer = "".join(data["delta"] for name, data in events if name == "answer")
    assert answer == "可以把空调设在 26℃ 左右。"

    done = events[-1][1]
    assert done["status"] == "complete"
    assert done["message_id"]
    assert done["content_chars"] == len(answer)
    assert done["sources_count"] == 1

    # 落库：助手消息带来源、状态完整
    detail = client.get(f"/api/conversations/{done['conversation_id']}").json()["data"]
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["sources"][0]["title"].startswith("教学楼")
    assert detail["messages"][1]["status"] == "complete"


def test_stream_with_existing_conversation(client, login, runtime):
    login("A")
    conv = client.post("/api/conversations", json={"title": "已有会话"}).json()["data"]
    runtime.chat.engine = FakeEngine(chunks=["回答"])
    res = client.post(
        "/api/chat/stream", json={"query": "继续问", "conversation_id": conv["id"]}
    )
    events = parse_sse(res.text)
    meta = events[0][1]
    assert meta["conversation_id"] == conv["id"]
    assert meta["created"] is False


def test_engine_error_event_marks_interrupted(client, login, runtime):
    runtime.chat.engine = FakeEngine(chunks=["部分回答"], mode="error_after")
    login("A")
    res = client.post("/api/chat/stream", json={"query": "测试错误"})
    events = parse_sse(res.text)
    names = [name for name, _ in events]
    assert "error" in names
    done = events[-1][1]
    assert done["status"] == "interrupted"

    detail = client.get(f"/api/conversations/{done['conversation_id']}").json()["data"]
    assistant = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert assistant and assistant[0]["status"] == "interrupted"


def test_engine_exception_returns_error_and_no_partial_message(client, login, runtime):
    runtime.chat.engine = FakeEngine(mode="raise")
    login("A")
    res = client.post("/api/chat/stream", json={"query": "触发异常"})
    events = parse_sse(res.text)
    names = [name for name, _ in events]
    assert "error" in names
    assert events[-1][0] == "done"
    assert events[-1][1]["status"] == "failed"

    conv_id = events[0][1]["conversation_id"]
    detail = client.get(f"/api/conversations/{conv_id}").json()["data"]
    assert [m["role"] for m in detail["messages"]] == ["user"]


def test_whitespace_query_is_rejected_as_event(client, login, runtime):
    login("A")
    res = client.post("/api/chat/stream", json={"query": "   "})
    events = parse_sse(res.text)
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "empty_query"


def test_cannot_stream_into_others_conversation(client, login, runtime):
    login("A")
    conv = client.post("/api/conversations", json={"title": "A 的会话"}).json()["data"]
    client.post("/api/auth/logout")
    login("B")
    runtime.chat.engine = FakeEngine(chunks=["不该出现的回答"])
    res = client.post(
        "/api/chat/stream", json={"query": "越权提问", "conversation_id": conv["id"]}
    )
    events = parse_sse(res.text)
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "conversation_not_found"

    client.post("/api/auth/logout")
    login("A")
    detail = client.get(f"/api/conversations/{conv['id']}").json()["data"]
    assert detail["messages"] == []


def test_stream_requires_login(client):
    res = client.post("/api/chat/stream", json={"query": "你好"})
    assert res.status_code == 401


def test_legacy_get_ask_stream_works(client, login, runtime):
    runtime.chat.engine = FakeEngine(chunks=["兼容回答"])
    login("A")
    res = client.get("/api/chat/ask", params={"query": "旧接口"})
    assert res.status_code == 200
    events = parse_sse(res.text)
    assert events[-1][0] == "done"
    assert events[-1][1]["status"] == "complete"


def test_sse_data_lines_are_single_line_json(client, login, runtime):
    runtime.chat.engine = FakeEngine(chunks=["第一行\n第二行"])
    login("A")
    res = client.post("/api/chat/stream", json={"query": "换行"})
    for block in res.text.split("\n\n"):
        data_lines = [line for line in block.splitlines() if line.startswith("data:")]
        assert len(data_lines) <= 1
