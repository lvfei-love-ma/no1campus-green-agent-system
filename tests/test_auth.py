"""认证相关测试：登录、Cookie 会话、退出、验证码、演示开关。"""
from __future__ import annotations

import pytest

from service import auth_service as auth_module
from tests.conftest import FakeRedis


def test_demo_login_sets_cookie_and_me(client, login):
    login("A")
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["email"] == "student_a@demo.local"
    assert data["knowledge_title"]

def test_unauthenticated_requests_are_rejected(client):
    for path in ("/api/auth/me", "/api/conversations"):
        res = client.get(path)
        assert res.status_code == 401
        assert res.json()["code"] == 401


def test_logout_invalidates_session(client, login):
    login("A")
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_bearer_token_works_without_cookie(client, login):
    data = login("A")
    client.cookies.clear()
    token = client.post("/api/auth/demo-login", json={"account": "A"}).json()["data"]["token"]
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200


def test_demo_login_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(auth_module, "DEMO_LOGIN_ENABLED", False)
    res = client.post("/api/auth/demo-login", json={"account": "A"})
    assert res.status_code == 403


def test_vcode_login_flow(client, runtime, monkeypatch):
    import service.email_service as email_module

    monkeypatch.setattr(email_module, "EmailService", _FakeEmail)

    res = client.get("/api/auth/vcode", params={"email": "student@example.com"})
    assert res.status_code == 200, res.text
    code = runtime.redis.get_code("student@example.com")
    assert code

    res = client.post("/api/auth/login", json={"email": "student@example.com", "vcode": code})
    assert res.status_code == 200, res.text
    assert client.get("/api/auth/me").json()["data"]["email"] == "student@example.com"

    # 验证码一次性使用
    client.post("/api/auth/logout")
    res = client.post("/api/auth/login", json={"email": "student@example.com", "vcode": code})
    assert res.status_code == 400


def test_vcode_rate_limit(client, runtime, monkeypatch):
    import service.email_service as email_module

    monkeypatch.setattr(email_module, "EmailService", _FakeEmail)
    assert client.get("/api/auth/vcode", params={"email": "a@b.com"}).status_code == 200
    res = client.get("/api/auth/vcode", params={"email": "a@b.com"})
    assert res.status_code == 429


def test_vcode_requires_valid_email(client):
    res = client.get("/api/auth/vcode", params={"email": "not-an-email"})
    assert res.status_code == 400


def test_status_endpoint_never_leaks_secrets(client):
    payload = client.get("/api/auth/status").json()["data"]
    text = str(payload)
    assert "api_key" not in text.lower()
    assert "password" not in text.lower()


class _FakeEmail:
    def __init__(self):
        pass

    def generate_code(self):
        return "123456"

    def send_vcode(self, email, code):
        return True
