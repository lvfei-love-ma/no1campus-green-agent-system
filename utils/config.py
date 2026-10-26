"""全局配置。

所有配置优先从项目根目录的 .env 读取，缺省值保证在没有 .env 时也能导入模块。
注意：本文件只保存配置，不会把任何密钥打印到日志或返回给接口。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------- 模型相关
QWEN_MODEL_NAME = _env("QWEN_MODEL_NAME")
QWEN_API_KEY = _env("QWEN_API_KEY")
QWEN_BASE_URL = _env("QWEN_BASE_URL")
EMBEDDINGS_MODEL_NAME = _env("EMBEDDINGS_MODEL_NAME")

qwen_model_name = QWEN_MODEL_NAME
qwen_api_key = QWEN_API_KEY
qwen_base_url = QWEN_BASE_URL
embeddings_model_name = EMBEDDINGS_MODEL_NAME

# ---------------------------------------------------------------- 邮件 / Redis
smtp_host = _env("SMTP_HOST")
smtp_port = _env("SMTP_PORT")
smtp_user = _env("SMTP_USER")
smtp_password = _env("SMTP_PASSWORD")
redis_url = _env("REDIS_URL", "redis://localhost:6379/0")

# ---------------------------------------------------------------- 知识库索引
FAISS_INDEX_PATH = _env("FAISS_INDEX_PATH", str(BASE_DIR / "faiss-index" / "default"))
DATASETS_DIR = Path(_env("DATASETS_DIR", str(BASE_DIR / "datasets")))
KNOWLEDGE_FILE = DATASETS_DIR / "green_campus_low_carbon.md"
KNOWLEDGE_TITLE = "绿色校园与低碳生活知识问答"

# ---------------------------------------------------------------- 会话 / 历史
DATA_DIR = Path(_env("DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DB_PATH = _env("HISTORY_DB_PATH", str(DATA_DIR / "app.db"))

SESSION_COOKIE_NAME = _env("SESSION_COOKIE_NAME", "lz_session")
SESSION_TTL_HOURS = _env_int("SESSION_TTL_HOURS", 24 * 7)
VCODE_TTL_SECONDS = _env_int("VCODE_TTL_SECONDS", 300)
VCODE_COOLDOWN_SECONDS = _env_int("VCODE_COOLDOWN_SECONDS", 60)

# 短期记忆：最近 N 轮完整对话；单条消息截断长度与总上下文长度上限
MEMORY_TURNS = _env_int("MEMORY_TURNS", 5)
MEMORY_MESSAGE_CHARS = _env_int("MEMORY_MESSAGE_CHARS", 600)
MEMORY_TOTAL_CHARS = _env_int("MEMORY_TOTAL_CHARS", 3000)

# 检索
RETRIEVE_TOP_K = _env_int("RETRIEVE_TOP_K", 5)
RETRIEVE_FETCH_K = _env_int("RETRIEVE_FETCH_K", 8)

# 演示账号登录：仅用于本地课堂演示 / 无 SMTP 时体验，正式部署请设为 0
DEMO_LOGIN_ENABLED = _env_bool("DEMO_LOGIN_ENABLED", True)
DEMO_ACCOUNTS = {
    "A": _env("DEMO_ACCOUNT_A", "student_a@demo.local"),
    "B": _env("DEMO_ACCOUNT_B", "student_b@demo.local"),
}
