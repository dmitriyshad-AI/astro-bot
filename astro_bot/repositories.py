"""Репозитории для работы с БД."""

from __future__ import annotations

import sqlite3
from typing import Optional


def get_or_create_user(
    conn: sqlite3.Connection,
    telegram_id: str,
    username: Optional[str],
    full_name: Optional[str],
) -> int:
    """
    Получить пользователя по telegram_id или создать нового.
    Возвращает id пользователя в таблице.
    """
    row = conn.execute(
        "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()

    if row:
        conn.execute(
            """
            UPDATE users
            SET username = ?, full_name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (username, full_name, row["id"]),
        )
        conn.commit()
        return row["id"]

    cursor = conn.execute(
        """
        INSERT INTO users (telegram_id, username, full_name)
        VALUES (?, ?, ?)
        """,
        (telegram_id, username, full_name),
    )
    conn.commit()
    return cursor.lastrowid


def log_request(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    request_type: str,
    input_payload: Optional[str],
    response_text: Optional[str],
) -> int:
    """
    Сохранить запрос/ответ в таблицу requests.
    Возвращает id созданной записи.
    """
    cursor = conn.execute(
        """
        INSERT INTO requests (user_id, type, input_payload, response_text)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, request_type, input_payload, response_text),
    )
    conn.commit()
    return cursor.lastrowid
