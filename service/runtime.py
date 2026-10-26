"""运行期服务容器。

main.py 启动时调用 init_runtime()；测试可以直接 init_runtime(tmp_db) 后再注入
假的引擎，避免真实调用模型。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from service.auth_service import AuthService
from service.chat_service import ChatService
from service.conversation_service import ConversationService
from service.redis_service import RedisService
from service.storage import Storage
from utils.config import HISTORY_DB_PATH


@dataclass
class Runtime:
    storage: Storage
    auth: AuthService
    conversations: ConversationService
    chat: ChatService
    redis: RedisService


_runtime: Optional[Runtime] = None


def init_runtime(db_path: str | None = None, redis_service: Optional[RedisService] = None) -> Runtime:
    global _runtime
    storage = Storage(db_path or HISTORY_DB_PATH)
    redis = redis_service or RedisService()
    auth = AuthService(storage, redis)
    conversations = ConversationService(storage)
    _runtime = Runtime(
        storage=storage,
        auth=auth,
        conversations=conversations,
        chat=ChatService(conversations),
        redis=redis,
    )
    return _runtime


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        return init_runtime()
    return _runtime


def reset_runtime() -> None:
    global _runtime
    _runtime = None
