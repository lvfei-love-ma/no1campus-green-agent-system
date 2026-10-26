"""pytest 公共夹具。

测试全部使用临时 SQLite 和假引擎，不需要真实模型 API、SMTP 或外网。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeEngine:
    """替代真实 Agent：按预设脚本产出事件，并记录收到的短期记忆。"""

    def __init__(self, chunks=("这是回答。",), sources=None, mode="ok"):
        self.chunks = list(chunks)
        self.sources = sources or []
        self.mode = mode
        self.calls = []

    async def run(self, query, memory_text=""):
        self.calls.append({"query": query, "memory": memory_text})
        if self.mode == "raise":
            raise RuntimeError("模型服务不可用")
        for chunk in self.chunks:
            yield {"type": "answer", "delta": chunk}
        if self.sources:
            yield {"type": "sources", "sources": self.sources}
        if self.mode == "error_after":
            yield {"type": "error", "message": "模型超时", "code": "timeout"}


class FakeRedis:
    def __init__(self):
        self.codes = {}
        self.cooldown = set()

    def ping(self):
        return True

    def acquire_cooldown(self, email, seconds=60):
        if email in self.cooldown:
            return False
        self.cooldown.add(email)
        return True

    def cooldown_ttl(self, email):
        return 60 if email in self.cooldown else 0

    def save_code(self, email, code):
        self.codes[email] = code
        return True

    def get_code(self, email):
        return self.codes.get(email)

    def consume_code(self, email, code):
        if self.codes.get(email) == code:
            self.codes.pop(email, None)
            return True
        return False


@pytest.fixture()
def runtime(tmp_path):
    from service.runtime import init_runtime, reset_runtime

    reset_runtime()
    rt = init_runtime(str(tmp_path / "test.db"))
    rt.redis = FakeRedis()
    rt.auth.redis = rt.redis
    yield rt
    reset_runtime()


@pytest.fixture()
def client(runtime):
    from fastapi.testclient import TestClient

    from main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def login(client):
    def _login(account="A"):
        res = client.post("/api/auth/demo-login", json={"account": account})
        assert res.status_code == 200, res.text
        return res.json()["data"]["user"]

    return _login
