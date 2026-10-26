"""认证接口：邮箱验证码登录、演示账号登录、当前用户、退出登录。

登录成功后写入 HttpOnly Cookie（默认 lz_session），同时在响应体里返回
token，方便 curl / 接口测试使用 Authorization: Bearer。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api_router.deps import get_current_user, get_token
from api_router.response import ok
from service.auth_service import AuthError
from service.runtime import get_runtime
from utils.config import DEMO_LOGIN_ENABLED, KNOWLEDGE_TITLE, SESSION_COOKIE_NAME, SESSION_TTL_HOURS

auth_router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(...)
    vcode: str = Field(...)


class DemoLoginRequest(BaseModel):
    account: str = Field(..., description="演示账号 A / B")


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_HOURS * 3600,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _raise(exc: AuthError):
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@auth_router.get("/status")
def auth_status():
    return ok(
        {
            "demo_login_enabled": DEMO_LOGIN_ENABLED,
            "knowledge_title": KNOWLEDGE_TITLE,
            "redis_ok": get_runtime().redis.ping(),
        }
    )


@auth_router.get("/vcode")
def send_vcode(email: str):
    try:
        data = get_runtime().auth.send_vcode(email)
    except AuthError as exc:
        _raise(exc)
    return ok(data, msg="验证码已发送，请查收邮箱")


@auth_router.post("/login")
def login_with_email(req: LoginRequest, response: Response):
    try:
        data = get_runtime().auth.login_with_code(req.email, req.vcode)
    except AuthError as exc:
        _raise(exc)
    _set_cookie(response, data["token"])
    return ok({"user": data["user"], "token": data["token"]}, msg="登录成功")


@auth_router.post("/demo-login")
def login_demo(req: DemoLoginRequest, response: Response):
    try:
        data = get_runtime().auth.login_demo(req.account)
    except AuthError as exc:
        _raise(exc)
    _set_cookie(response, data["token"])
    return ok({"user": data["user"], "token": data["token"]}, msg="已进入演示账号")


@auth_router.get("/me")
def me(user: dict = Depends(get_current_user)):
    data = dict(user)
    data["knowledge_title"] = KNOWLEDGE_TITLE
    return ok(data)


@auth_router.post("/logout")
def logout(request: Request, response: Response):
    get_runtime().auth.logout(get_token(request))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return ok(None, msg="已退出登录")
