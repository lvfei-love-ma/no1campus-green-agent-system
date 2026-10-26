"""Redis 服务：登录验证码、发送冷却。

Redis 只保存短生命周期数据。历史会话不依赖 Redis，即使 Redis 宕机，
已登录用户仍可浏览历史（登录状态存在 SQLite 的 sessions 表）。
"""
from __future__ import annotations

import redis

from utils.config import VCODE_COOLDOWN_SECONDS, VCODE_TTL_SECONDS, redis_url


class RedisUnavailable(RuntimeError):
    """Redis 不可用时抛出，由接口层转换为明确的错误提示。"""


class RedisService:
    def __init__(self, url: str | None = None):
        self.url = url or redis_url
        self._client = None

    # ------------------------------------------------------------ 基础
    @property
    def client(self):
        if self._client is None:
            try:
                client = redis.Redis.from_url(
                    self.url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=3,
                )
                client.ping()
                self._client = client
            except Exception as exc:  # pragma: no cover - 依赖真实服务
                self._client = None
                raise RedisUnavailable("Redis 未启动或无法连接") from exc
        return self._client

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except RedisUnavailable:
            return False

    # ------------------------------------------------------------ 验证码
    def save_code(self, email: str, code: str) -> bool:
        key = f"code:{email.strip().lower()}"
        try:
            self.client.setex(key, VCODE_TTL_SECONDS, code)
            return True
        except RedisUnavailable:
            raise
        except Exception:
            return False

    def get_code(self, email: str):
        try:
            return self.client.get(f"code:{email.strip().lower()}")
        except RedisUnavailable:
            raise
        except Exception:
            return None

    def consume_code(self, email: str, code: str) -> bool:
        """校验并一次性删除验证码，避免重复使用。"""
        key = f"code:{email.strip().lower()}"
        try:
            stored = self.client.get(key)
            if stored is None or stored != code:
                return False
            self.client.delete(key)
            return True
        except RedisUnavailable:
            raise
        except Exception:
            return False

    def acquire_cooldown(self, email: str, seconds: int = VCODE_COOLDOWN_SECONDS) -> bool:
        """发送冷却：SET NX EX，返回 True 表示可以发送。"""
        key = f"vcode:cooldown:{email.strip().lower()}"
        try:
            return bool(self.client.set(key, "1", nx=True, ex=max(1, seconds)))
        except RedisUnavailable:
            raise
        except Exception:
            return True

    def cooldown_ttl(self, email: str) -> int:
        try:
            ttl = self.client.ttl(f"vcode:cooldown:{email.strip().lower()}")
            return max(0, int(ttl))
        except Exception:
            return 0
