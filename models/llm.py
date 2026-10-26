"""模型与 Embedding 工厂。

延迟创建，避免在没有 API Key 的环境（例如只跑单元测试）里导入即报错。
旧代码中的 ``from models.llm import llm, embeddings`` 仍然可用，通过模块级
``__getattr__`` 懒加载。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from utils.config import (
    embeddings_model_name,
    qwen_api_key,
    qwen_base_url,
    qwen_model_name,
)


def _require_config() -> None:
    if not qwen_api_key:
        raise RuntimeError("缺少 QWEN_API_KEY，请复制 .env.example 为 .env 并填写模型密钥")
    if not qwen_model_name or not qwen_base_url:
        raise RuntimeError("缺少 QWEN_MODEL_NAME / QWEN_BASE_URL，请检查 .env")


@lru_cache(maxsize=1)
def get_llm():
    _require_config()
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=qwen_model_name,
        api_key=qwen_api_key,
        base_url=qwen_base_url,
        temperature=0,
        extra_body={"enable_thinking": False},
    )


@lru_cache(maxsize=1)
def get_embeddings():
    _require_config()
    from langchain_community.embeddings import DashScopeEmbeddings

    return DashScopeEmbeddings(
        model=embeddings_model_name,
        dashscope_api_key=qwen_api_key,
    )


def __getattr__(name: str) -> Any:  # pragma: no cover - 兼容旧导入
    if name == "llm":
        return get_llm()
    if name == "embeddings":
        return get_embeddings()
    raise AttributeError(name)
