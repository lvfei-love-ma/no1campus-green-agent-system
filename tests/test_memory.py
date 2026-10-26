"""短期记忆测试：最近 5 轮、截断规则、清空后不再携带旧上下文。"""
from __future__ import annotations

from service.memory import build_memory, format_memory
from service.storage import Storage


def _seed(storage: Storage, conversation_id: str, rounds: int, question_len: int = 10):
    for index in range(rounds):
        storage.add_message(conversation_id, "user", f"问题{index}-".ljust(question_len, "问"))
        storage.add_message(conversation_id, "assistant", f"回答{index}。" * max(1, question_len // 8))


def test_memory_keeps_only_last_five_rounds(tmp_path):
    storage = Storage(str(tmp_path / "mem.db"))
    user = storage.upsert_user("m@example.com")
    conv = storage.create_conversation(user["id"], "记忆")
    _seed(storage, conv["id"], rounds=8)

    turns = build_memory(storage, conv["id"], since=None, max_turns=5)
    assert len(turns) == 5
    assert turns[0][0].startswith("问题3")
    assert turns[-1][0].startswith("问题7")


def test_memory_truncates_long_messages_and_total_length(tmp_path):
    storage = Storage(str(tmp_path / "mem2.db"))
    user = storage.upsert_user("m2@example.com")
    conv = storage.create_conversation(user["id"], "长文本")
    for index in range(5):
        storage.add_message(conv["id"], "user", ("问题" + str(index)) * 300)
        storage.add_message(conv["id"], "assistant", ("回答" + str(index)) * 300)

    turns = build_memory(storage, conv["id"], since=None, max_turns=5)
    assert len(turns) <= 5
    for question, answer in turns:
        assert len(question) <= 600
        assert len(answer) <= 600
    total = sum(len(q) + len(a) for q, a in turns)
    assert total <= 3000


def test_clear_memory_keeps_history_but_resets_context(tmp_path):
    storage = Storage(str(tmp_path / "mem3.db"))
    user = storage.upsert_user("m3@example.com")
    service_conv = storage.create_conversation(user["id"], "清空")
    _seed(storage, service_conv["id"], rounds=3)

    assert storage.clear_memory(user["id"], service_conv["id"]) is True
    cleared = storage.get_conversation(user["id"], service_conv["id"])
    assert cleared["memory_cleared_at"]
    # 历史消息仍在
    assert len(storage.list_messages(service_conv["id"])) == 6
    # 但短期记忆为空
    assert build_memory(storage, service_conv["id"], since=cleared["memory_cleared_at"]) == []


def test_format_memory_mentions_turn_numbers():
    text = format_memory([("问一", "答一"), ("问二", "答二")])
    assert "第1轮" in text and "第2轮" in text
    assert "用户：问二" in text


def test_memory_is_isolated_between_conversations(tmp_path):
    storage = Storage(str(tmp_path / "mem4.db"))
    user = storage.upsert_user("m4@example.com")
    first = storage.create_conversation(user["id"], "会话一")
    second = storage.create_conversation(user["id"], "会话二")
    storage.add_message(first["id"], "user", "只属于会话一的问题")
    storage.add_message(first["id"], "assistant", "会话一的回答")

    assert build_memory(storage, first["id"], since=None) == [("只属于会话一的问题", "会话一的回答")]
    assert build_memory(storage, second["id"], since=None) == []
