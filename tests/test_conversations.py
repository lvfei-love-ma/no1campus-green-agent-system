"""会话接口测试：新建、列表、详情、删除与用户隔离。"""
from __future__ import annotations

from service.storage import Storage


def _create(client, title=""):
    res = client.post("/api/conversations", json={"title": title})
    assert res.status_code == 200, res.text
    return res.json()["data"]


def test_conversation_lifecycle(client, login):
    login("A")
    conv = _create(client, "垃圾分类的疑问")
    assert conv["id"]

    res = client.get("/api/conversations")
    items = res.json()["data"]["items"]
    assert [item["id"] for item in items] == [conv["id"]]

    res = client.get(f"/api/conversations/{conv['id']}")
    assert res.status_code == 200
    assert res.json()["data"]["messages"] == []

    res = client.patch(f"/api/conversations/{conv['id']}", json={"title": "新标题"})
    assert res.json()["data"]["title"] == "新标题"

    res = client.delete(f"/api/conversations/{conv['id']}")
    assert res.status_code == 200
    assert client.get(f"/api/conversations/{conv['id']}").status_code == 404
    assert client.get("/api/conversations").json()["data"]["items"] == []


def test_search_conversations_by_title_and_content(client, login, runtime):
    login("A")
    first = _create(client, "空调温度")
    second = _create(client, "快递纸箱")
    runtime.conversations.append_user_message(
        runtime.storage.upsert_user("student_a@demo.local")["id"], second["id"], "双面打印在哪里设置"
    )

    res = client.get("/api/conversations", params={"q": "空调"})
    assert [item["id"] for item in res.json()["data"]["items"]] == [first["id"]]

    res = client.get("/api/conversations", params={"q": "双面打印"})
    assert [item["id"] for item in res.json()["data"]["items"]] == [second["id"]]

    res = client.get("/api/conversations", params={"q": "不存在的词"})
    assert res.json()["data"]["items"] == []


def test_user_cannot_read_or_delete_others_conversation(client, login, runtime):
    # 用户 A 建立会话
    login("A")
    conv = _create(client, "A 的私有会话")

    # 用户 B 登录（同一 TestClient 共享 cookie，先清掉）
    client.post("/api/auth/logout")
    login("B")
    assert client.get(f"/api/conversations/{conv['id']}").status_code == 404
    assert client.delete(f"/api/conversations/{conv['id']}").status_code == 404
    assert client.get("/api/conversations").json()["data"]["items"] == []
    # 清空 B 访问 A 会话的记忆同样被拒绝
    assert client.post(f"/api/conversations/{conv['id']}/memory/clear").status_code == 404

    # A 的会话仍然存在
    client.post("/api/auth/logout")
    login("A")
    assert client.get(f"/api/conversations/{conv['id']}").status_code == 200


def test_messages_are_persisted_between_storage_instances(tmp_path):
    from service.conversation_service import ConversationService

    db_path = tmp_path / "persist.db"
    storage = Storage(str(db_path))
    user = storage.upsert_user("p@example.com")
    service = ConversationService(storage)
    conv = service.create(user["id"], "持久化")
    service.append_user_message(user["id"], conv["id"], "问题")
    service.append_assistant_message(user["id"], conv["id"], "回答")

    # 新建一个 Storage（模拟服务重启）仍能读到历史
    reopened = ConversationService(Storage(str(db_path)))
    detail = reopened.detail(user["id"], conv["id"])
    assert [m["content"] for m in detail["messages"]] == ["问题", "回答"]


def test_empty_title_is_displayed_and_renamed_after_first_question(client, login, runtime):
    from tests.conftest import FakeEngine

    login("A")
    conv = _create(client)
    assert conv["title"] == ""

    runtime.chat.engine = FakeEngine(chunks=["简短回答"])
    res = client.post(
        "/api/chat/stream",
        json={"query": "宿舍空调应该开多少度？", "conversation_id": conv["id"]},
    )
    assert res.status_code == 200

    detail = client.get(f"/api/conversations/{conv['id']}").json()["data"]["conversation"]
    assert detail["title"].startswith("宿舍空调")
