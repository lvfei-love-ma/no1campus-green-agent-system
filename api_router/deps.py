"""FastAPI 依赖：从 Cookie / Authorization 头解析当前用户。

身份只认服务端 sessions 表中的令牌；请求体、localStorage 里的邮箱不参与判断。
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request

from service.runtime import get_runtime
from utils.config import SESSION_COOKIE_NAME


def get_token(request: Request) -> Optional[str]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        return token
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def resolve_user(request: Request) -> Optional[dict]:
    token = get_token(request)
    if not token:
        return None
    return get_runtime().auth.resolve_token(token)


def get_current_user(request: Request) -> dict:
    user = resolve_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user


def require_user(user: Optional[dict]) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user
