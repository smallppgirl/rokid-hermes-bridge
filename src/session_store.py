"""
Hermes Session 持久化模块
========================
将 Rokid 眼镜的对话写入 Hermes 的 session SQLite 数据库，
让眼镜对话也能被 session_search 搜到。

用法：
    from session_store import store_conversation
    await store_conversation(user_id="xxx", user_msg="你好", assistant_msg="你好！")
"""

import os
import time
import sqlite3
import logging
import asyncio
from pathlib import Path

logger = logging.getLogger("session-store")

# Hermes state.db 的路径
STATE_DB_PATH = os.getenv(
    "HERMES_STATE_DB",
    str(Path.home() / ".hermes" / "state.db")
)

# 会话来源标识
SOURCE = "rokid-glasses"


def _get_session_id(user_id: str) -> str:
    """生成 session ID，同一天的对话共用一个 session"""
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    return f"rokid:{user_id}:{date_str}"


def _get_or_create_session(conn, session_id: str, user_id: str, model: str = "unknown") -> None:
    """确保 session 存在，不存在则创建"""
    row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        now = time.time()
        conn.execute(
            """INSERT INTO sessions (id, source, user_id, model, started_at, message_count)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (session_id, SOURCE, user_id, model, now),
        )
        conn.commit()
        logger.info(f"创建新 session: {session_id}")


def _insert_message(conn, session_id: str, role: str, content: str) -> None:
    """插入一条消息"""
    now = time.time()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now),
    )
    conn.execute(
        "UPDATE sessions SET message_count = message_count + 1, ended_at = ? WHERE id = ?",
        (now, session_id),
    )
    conn.commit()


def _save_conversation_sync(user_id: str, user_msg: str, assistant_msg: str, model: str = "unknown") -> bool:
    """同步写入对话到 session DB"""
    try:
        conn = sqlite3.connect(STATE_DB_PATH, timeout=5.0)
        try:
            session_id = _get_session_id(user_id)
            _get_or_create_session(conn, session_id, user_id, model)
            _insert_message(conn, session_id, "user", user_msg)
            _insert_message(conn, session_id, "assistant", assistant_msg)
            logger.info(f"对话已写入 session DB: session={session_id}")
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"写入 session DB 失败: {e}")
        return False


async def store_conversation(user_id: str, user_msg: str, assistant_msg: str, model: str = "unknown") -> bool:
    """异步写入对话到 Hermes session DB（不阻塞 SSE 响应）"""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _save_conversation_sync, user_id, user_msg, assistant_msg, model)
        return result
    except Exception as e:
        logger.error(f"异步写入 session 失败: {e}")
        return False
