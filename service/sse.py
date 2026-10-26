"""SSE 事件封装。

事件结构固定，前后端与测试共用同一份定义：

    event: meta      data: {"conversation_id", "user_message_id", "assistant_message_id"}
    event: answer    data: {"delta": "增量文本"}
    event: sources   data: {"sources": [{"title", "category", "source_name",
                                         "source_url", "published_at"}]}
    event: done      data: {"conversation_id", "message_id", "content_chars", "memory_turns"}
    event: error     data: {"message", "code"}

所有 data 都是单行 JSON（JSON 中的换行已被转义），因此每个事件只有一个
data: 行，前端用 JSON.parse 解析即可。
"""
from __future__ import annotations

import json


def sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("\n", "\\n").replace("\r", "\\r")
    return f"event: {event}\ndata: {payload}\n\n"


def parse_sse(raw: str) -> list[tuple[str, dict]]:
    """测试辅助：把 SSE 文本解析为 [(event, data)]。"""
    events: list[tuple[str, dict]] = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].lstrip())
        if data_lines:
            try:
                events.append((event_name, json.loads("\n".join(data_lines))))
            except json.JSONDecodeError:
                events.append((event_name, {"raw": "\n".join(data_lines)}))
    return events
