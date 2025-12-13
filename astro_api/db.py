"""SQLite helpers for Astro API."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from astro_api import config


DB_PATH = config.get_repo_root() / "data" / "astroglass.db"


def ensure_data_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Get SQLite connection (thread-safe for our usage)."""
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if missing."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            telegram_user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            language_code TEXT,
            is_premium INTEGER,
            created_at TEXT,
            updated_at TEXT
        );
        """
    )
    conn.commit()


def upsert_user(conn: sqlite3.Connection, user: dict) -> None:
    """Insert or update user from Telegram WebApp initData."""
    now = datetime.utcnow().isoformat()
    conn.execute(
        """
        INSERT INTO users
            (telegram_user_id, username, first_name, last_name, language_code, is_premium, created_at, updated_at)
        VALUES
            (:telegram_user_id, :username, :first_name, :last_name, :language_code, :is_premium, :created_at, :updated_at)
        ON CONFLICT(telegram_user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name,
            last_name=excluded.last_name,
            language_code=excluded.language_code,
            is_premium=excluded.is_premium,
            updated_at=excluded.updated_at;
        """,
        {
            "telegram_user_id": user.get("id"),
            "username": user.get("username"),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
            "language_code": user.get("language_code"),
            "is_premium": int(bool(user.get("is_premium"))) if user.get("is_premium") is not None else None,
            "created_at": now,
            "updated_at": now,
        },
    )
    conn.commit()
