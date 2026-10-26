"""会话历史的持久化层（SQLite）。

设计说明：
- Redis 在本项目里只承担验证码、登录冷却等短生命周期数据；会话与消息属于
  必须可靠保存的数据，因此落到项目内 SQLite 文件（默认 data/app.db）。
- 每次操作使用独立连接 + WAL，避免 FastAPI 多线程下共享连接的问题。
- 所有“读取会话/消息”的方法都要求传入 user_id，SQL 中直接带 owner 条件，
  防止越权读取；调用方不能只靠前端传来的 id 判断归属。
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    display_name  TEXT    NOT NULL DEFAULT '',
    is_demo       INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS conversations (
    id                 TEXT PRIMARY KEY,
    user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title              TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    memory_cleared_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content          TEXT NOT NULL DEFAULT '',
    sources_json     TEXT,
    status           TEXT NOT NULL DEFAULT 'complete',
    seq              INTEGER NOT NULL,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, seq);
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    # ------------------------------------------------------------ 连接管理
    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------ 用户
    def upsert_user(self, email: str, display_name: str = "", is_demo: bool = False) -> dict:
        email = email.strip().lower()
        display_name = display_name or email
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO users (email, display_name, is_demo, created_at) VALUES (?, ?, ?, ?)",
                    (email, display_name, int(is_demo), iso(utc_now())),
                )
                row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            elif display_name and row["display_name"] != display_name:
                conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, row["id"]))
                row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return self._user_row(row)

    def get_user(self, user_id: int) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._user_row(row) if row else None

    @staticmethod
    def _user_row(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "email": row["email"],
            "display_name": row["display_name"],
            "is_demo": bool(row["is_demo"]),
            "created_at": row["created_at"],
        }

    # ------------------------------------------------------------ 登录会话
    def create_session(self, user_id: int, ttl_hours: int = 168) -> str:
        token = uuid.uuid4().hex + uuid.uuid4().hex[:8]
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user_id, iso(now), iso(now + timedelta(hours=ttl_hours))),
            )
        return token

    def get_session_user(self, token: str) -> Optional[dict]:
        if not token:
            return None
        now = iso(utc_now())
        with self.connect() as conn:
            row = conn.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token = ? AND s.expires_at > ?",
                (token, now),
            ).fetchone()
            if row is None:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                return None
        return self._user_row(row)

    def delete_session(self, token: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def purge_expired_sessions(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (iso(utc_now()),))

    # ------------------------------------------------------------ 会话
    def create_conversation(self, user_id: int, title: str = "", conversation_id: Optional[str] = None) -> dict:
        conv_id = conversation_id or new_id("conv")
        now = iso(utc_now())
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO conversations (id, user_id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv_id, user_id, (title or "").strip(), now, now),
            )
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        return self._conv_row(row)

    def get_conversation(self, user_id: int, conversation_id: str) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
        return self._conv_row(row) if row else None

    def list_conversations(self, user_id: int, keyword: str = "") -> list[dict]:
        sql = (
            "SELECT c.*, "
            "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count "
            "FROM conversations c WHERE c.user_id = ?"
        )
        params: list[Any] = [user_id]
        if keyword:
            sql += " AND (c.title LIKE ? OR EXISTS (SELECT 1 FROM messages m2 "
            sql += "WHERE m2.conversation_id = c.id AND m2.content LIKE ?))"
            like = f"%{keyword}%"
            params.extend([like, like])
        sql += " ORDER BY c.updated_at DESC"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._conv_row(r, message_count=r["message_count"]) for r in rows]

    def touch_conversation(self, conversation_id: str, title: Optional[str] = None) -> None:
        with self.connect() as conn:
            if title is None:
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (iso(utc_now()), conversation_id),
                )
            else:
                conn.execute(
                    "UPDATE conversations SET updated_at = ?, title = ? WHERE id = ?",
                    (iso(utc_now()), title, conversation_id),
                )

    def delete_conversation(self, user_id: int, conversation_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            return cur.rowcount > 0

    def clear_memory(self, user_id: int, conversation_id: str) -> bool:
        """清空短期记忆：只设置时间标记，历史消息仍保留。"""
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE conversations SET memory_cleared_at = ? WHERE id = ? AND user_id = ?",
                (iso(utc_now()), conversation_id, user_id),
            )
            return cur.rowcount > 0

    @staticmethod
    def _conv_row(row: sqlite3.Row, message_count: int = 0) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "memory_cleared_at": row["memory_cleared_at"],
            "message_count": message_count,
        }

    # ------------------------------------------------------------ 消息
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: Optional[Iterable[dict]] = None,
        status: str = "complete",
        message_id: Optional[str] = None,
    ) -> dict:
        msg_id = message_id or new_id("msg")
        now = iso(utc_now())
        sources_json = None
        if sources:
            import json

            sources_json = json.dumps(list(sources), ensure_ascii=False)
        with self.connect() as conn:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, sources_json, status, seq, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (msg_id, conversation_id, role, content, sources_json, status, seq, now),
            )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
            row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        return self._msg_row(row)

    def list_messages(self, conversation_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq ASC",
                (conversation_id,),
            ).fetchall()
        return [self._msg_row(r) for r in rows]

    def memory_messages(self, conversation_id: str, since: Optional[str], limit: int) -> list[dict]:
        """取短期记忆候选：指定时间之后、状态完整的消息，按时间倒序取 limit 条。"""
        sql = (
            "SELECT * FROM messages WHERE conversation_id = ? AND status = 'complete'"
        )
        params: list[Any] = [conversation_id]
        if since:
            sql += " AND created_at > ?"
            params.append(since)
        sql += " ORDER BY seq DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._msg_row(r) for r in reversed(rows)]

    @staticmethod
    def _msg_row(row: sqlite3.Row) -> dict:
        import json

        sources = json.loads(row["sources_json"]) if row["sources_json"] else []
        return {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "role": row["role"],
            "content": row["content"],
            "sources": sources,
            "status": row["status"],
            "created_at": row["created_at"],
        }
