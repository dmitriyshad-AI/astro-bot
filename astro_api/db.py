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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_cache (
            query TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            tz_str TEXT NOT NULL,
            display_name TEXT,
            updated_at TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id INTEGER,
            label TEXT,
            birth_date TEXT,
            birth_time TEXT,
            time_unknown INTEGER,
            place_query TEXT,
            lat REAL,
            lng REAL,
            tz_str TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS charts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER,
            chart_json TEXT,
            wheel_path TEXT,
            created_at TEXT,
            FOREIGN KEY(profile_id) REFERENCES profiles(id)
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


def get_cached_location(conn: sqlite3.Connection, query: str):
    """Get cached geo result."""
    return conn.execute(
        "SELECT query, lat, lng, tz_str, display_name FROM geo_cache WHERE query = ?",
        (query,),
    ).fetchone()


def upsert_cached_location(
    conn: sqlite3.Connection,
    *,
    query: str,
    lat: float,
    lng: float,
    tz_str: str,
    display_name: str,
) -> None:
    """Upsert geo result."""
    now = datetime.utcnow().isoformat()
    conn.execute(
        """
        INSERT INTO geo_cache (query, lat, lng, tz_str, display_name, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(query) DO UPDATE SET
            lat=excluded.lat,
            lng=excluded.lng,
            tz_str=excluded.tz_str,
            display_name=excluded.display_name,
            updated_at=excluded.updated_at
        """,
        (query, lat, lng, tz_str, display_name, now),
    )
    conn.commit()


def insert_profile(
    conn: sqlite3.Connection,
    *,
    telegram_user_id: int | None,
    label: str | None,
    birth_date: str,
    birth_time: str | None,
    time_unknown: bool,
    place_query: str,
    lat: float,
    lng: float,
    tz_str: str,
) -> int:
    """Insert profile and return id."""
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        """
        INSERT INTO profiles (
            telegram_user_id, label, birth_date, birth_time, time_unknown,
            place_query, lat, lng, tz_str, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            telegram_user_id,
            label,
            birth_date,
            birth_time,
            int(time_unknown),
            place_query,
            lat,
            lng,
            tz_str,
            now,
            now,
        ),
    )
    conn.commit()
    return cur.lastrowid


def insert_chart(
    conn: sqlite3.Connection,
    *,
    profile_id: int,
    chart_json: str,
    wheel_path: str,
) -> int:
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        """
        INSERT INTO charts (profile_id, chart_json, wheel_path, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (profile_id, chart_json, wheel_path, now),
    )
    conn.commit()
    return cur.lastrowid


def get_chart(conn: sqlite3.Connection, chart_id: int):
    return conn.execute("SELECT * FROM charts WHERE id = ?", (chart_id,)).fetchone()
