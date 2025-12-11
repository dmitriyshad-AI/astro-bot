"""Подключение к SQLite и инициализация схемы."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from astro_bot import config


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Создать соединение с SQLite."""
    path = db_path or config.get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Создать необходимые таблицы, если их нет."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
