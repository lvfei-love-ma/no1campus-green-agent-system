"""Agent 提示词测试：回答边界与短期记忆注入。"""
from __future__ import annotations

from agent.chat_agent import build_system_prompt


def test_prompt_requires_grounding_and_refusal_when_insufficient():
    prompt = build_system_prompt()
    assert "知识库暂时没有找到足够信息" in prompt
    assert "不要编造" in prompt
    assert "只能来自检索到的资料" in prompt


def test_prompt_includes_memory_only_when_provided():
    without_memory = build_system_prompt()
    assert "当前会话的最近对话" not in without_memory

    with_memory = build_system_prompt("第1轮\n用户：空调多少度？\n助手：26℃左右。")
    assert "当前会话的最近对话" in with_memory
    assert "第1轮" in with_memory
    assert "26℃左右" in with_memory


def test_prompt_states_memory_is_not_evidence():
    prompt = build_system_prompt("第1轮\n用户：问\n助手：答")
    assert "不是知识库证据" in prompt
