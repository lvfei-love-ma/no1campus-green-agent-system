"""短期记忆。

规则（见 README «短期记忆»）：
- 只取当前会话、最近 MEMORY_TURNS（默认 5）轮完整对话；
- 只取“清空记忆”标记之后、status=complete 的消息；
- 单条消息超过 MEMORY_MESSAGE_CHARS 截断，总长度超过 MEMORY_TOTAL_CHARS
  时从最旧的一轮开始丢弃，保证上下文不会无限增长；
- 不同会话、不同用户之间不会混入。
"""
from __future__ import annotations

from typing import List, Tuple

from service.storage import Storage
from utils.config import MEMORY_MESSAGE_CHARS, MEMORY_TOTAL_CHARS, MEMORY_TURNS


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def build_memory(
    storage: Storage,
    conversation_id: str,
    since: str | None,
    max_turns: int = MEMORY_TURNS,
) -> List[Tuple[str, str]]:
    """返回 [(问题, 回答), ...]，按时间从旧到新，最多 max_turns 轮。"""
    max_messages = max_turns * 2
    rows = storage.memory_messages(conversation_id, since, limit=max_messages)

    turns: List[Tuple[str, str]] = []
    pending_question: str | None = None
    for row in rows:
        if row["role"] == "user":
            pending_question = _clip(row["content"], MEMORY_MESSAGE_CHARS)
        elif row["role"] == "assistant" and pending_question is not None:
            turns.append((pending_question, _clip(row["content"], MEMORY_MESSAGE_CHARS)))
            pending_question = None
    turns = turns[-max_turns:]

    # 从最旧的轮次开始裁剪总长度
    while turns and sum(len(q) + len(a) for q, a in turns) > MEMORY_TOTAL_CHARS:
        turns.pop(0)
    return turns


def format_memory(turns: List[Tuple[str, str]]) -> str:
    if not turns:
        return ""
    lines = []
    for index, (question, answer) in enumerate(turns, start=1):
        lines.append(f"第{index}轮\n用户：{question}\n助手：{answer}")
    return "\n\n".join(lines)
