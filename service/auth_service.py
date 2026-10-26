"""身份与会话令牌。

身份来源有三处，全部由服务端校验：
1. Cookie 中的会话 token（浏览器默认路径，HttpOnly）；
2. Authorization: Bearer <token>（便于 curl / 自动化测试）；
3. 服务端存储 sessions 表中的记录（过期即失效）。
前端 localStorage 里的任何值都不参与身份判断。
"""
from __future__ import annotations

import re
from typing import Optional

from service.redis_service import RedisService, RedisUnavailable
from service.storage import Storage
from utils.config import DEMO_ACCOUNTS, DEMO_LOGIN_ENABLED, SESSION_TTL_HOURS

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "auth_error"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("邮箱格式不正确", 400, "invalid_email")
    return email


def display_name_for(email: str) -> str:
    return email.split("@")[0][:32]


class AuthService:
    def __init__(self, storage: Storage, redis_service: Optional[RedisService] = None):
        self.storage = storage
        self.redis = redis_service or RedisService()

    # ------------------------------------------------------------ 验证码
    def send_vcode(self, email: str) -> dict:
        email = normalize_email(email)
        if not self.redis.acquire_cooldown(email):
            raise AuthError(
                f"发送过于频繁，请 {self.redis.cooldown_ttl(email)} 秒后再试",
                429,
                "vcode_cooldown",
            )
        from service.email_service import EmailService

        email_server = EmailService()
        code = email_server.generate_code()
        if not email_server.send_vcode(email, code):
            raise AuthError("验证码邮件发送失败，请检查 SMTP 配置或改用演示账号", 502, "smtp_failed")
        self.redis.save_code(email, code)
        return {"email": email, "expires_in": 300}

    # ------------------------------------------------------------ 登录
    def login_with_code(self, email: str, code: str) -> dict:
        email = normalize_email(email)
        code = (code or "").strip()
        if not code:
            raise AuthError("请输入验证码", 400, "empty_vcode")
        try:
            ok = self.redis.consume_code(email, code)
        except RedisUnavailable as exc:
            raise AuthError("验证码服务不可用（Redis 未启动）", 503, "redis_unavailable") from exc
        if not ok:
            raise AuthError("验证码不存在或已过期", 400, "invalid_vcode")
        user = self.storage.upsert_user(email, display_name_for(email))
        return self._issue(user)

    def login_demo(self, account: str) -> dict:
        if not DEMO_LOGIN_ENABLED:
            raise AuthError("演示账号登录已关闭", 403, "demo_disabled")
        key = (account or "").strip().upper()
        if key not in DEMO_ACCOUNTS:
            raise AuthError("未知的演示账号", 400, "unknown_demo_account")
        email = DEMO_ACCOUNTS[key]
        user = self.storage.upsert_user(email, f"演示同学 {key}", is_demo=True)
        return self._issue(user)

    def _issue(self, user: dict) -> dict:
        token = self.storage.create_session(user["id"], ttl_hours=SESSION_TTL_HOURS)
        return {"token": token, "user": self._public_user(user)}

    # ------------------------------------------------------------ 校验 / 退出
    def resolve_token(self, token: Optional[str]) -> Optional[dict]:
        if not token:
            return None
        user = self.storage.get_session_user(token)
        return user

    def logout(self, token: Optional[str]) -> None:
        if token:
            self.storage.delete_session(token)

    @staticmethod
    def _public_user(user: dict) -> dict:
        return {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "is_demo": user.get("is_demo", False),
        }
