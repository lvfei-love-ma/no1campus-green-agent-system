"""统一响应结构：所有接口返回 {code, msg, data}。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ApiResponse(BaseModel):
    code: int
    msg: str
    data: Optional[Any] = None


def ok(data: Any = None, msg: str = "success") -> ApiResponse:
    return ApiResponse(code=200, msg=msg, data=data)


def fail(msg: str, code: int = 400, data: Any = None) -> ApiResponse:
    return ApiResponse(code=code, msg=msg, data=data)
