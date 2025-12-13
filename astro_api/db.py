"""SQLite helpers for Astro API."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
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
            summary TEXT,
            created_at TEXT,
            FOREIGN KEY(profile_id) REFERENCES profiles(id)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chart_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT,
            created_at TEXT,
            FOREIGN KEY(chart_id) REFERENCES charts(id)
        );
        """
    )
    conn.commit()
    _migrate_schema(conn)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1].lower() == column.lower() for row in rows)


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Lightweight migrations for existing installs."""
    # charts.summary
    if not _column_exists(conn, "charts", "summary"):
        conn.execute("ALTER TABLE charts ADD COLUMN summary TEXT;")
    # charts.created_at
    if not _column_exists(conn, "charts", "created_at"):
        conn.execute("ALTER TABLE charts ADD COLUMN created_at TEXT;")
    # charts.llm_summary
    if not _column_exists(conn, "charts", "llm_summary"):
        conn.execute("ALTER TABLE charts ADD COLUMN llm_summary TEXT;")
    # compatibility_runs
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS compatibility_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            self_profile_id INTEGER,
            partner_profile_id INTEGER,
            synastry_json TEXT,
            score_json TEXT,
            top_aspects_json TEXT,
            wheel_path TEXT,
            created_at TEXT
        );
        """
    )
    conn.commit()


def upsert_user(conn: sqlite3.Connection, user: dict) -> None:
    """Insert or update user from Telegram WebApp initData."""
    now = datetime.now(timezone.utc).isoformat()
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
    now = datetime.now(timezone.utc).isoformat()
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
    now = datetime.now(timezone.utc).isoformat()
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
    summary: str | None,
    llm_summary: str | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO charts (profile_id, chart_json, wheel_path, summary, llm_summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (profile_id, chart_json, wheel_path, summary, llm_summary, now),
    )
    conn.commit()
    return cur.lastrowid


def insert_compatibility(
    conn: sqlite3.Connection,
    *,
    user_id: str | None,
    self_profile_id: int | None,
    partner_profile_id: int | None,
    synastry_json: str,
    score_json: str | None,
    top_aspects_json: str | None,
    wheel_path: str | None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO compatibility_runs (
            user_id, self_profile_id, partner_profile_id,
            synastry_json, score_json, top_aspects_json, wheel_path, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, self_profile_id, partner_profile_id, synastry_json, score_json, top_aspects_json, wheel_path, now),
    )
    conn.commit()
    return cur.lastrowid


def get_compatibility(conn: sqlite3.Connection, comp_id: int):
    return conn.execute("SELECT * FROM compatibility_runs WHERE id = ?", (comp_id,)).fetchone()


def get_chart(conn: sqlite3.Connection, chart_id: int):
    return conn.execute("SELECT * FROM charts WHERE id = ?", (chart_id,)).fetchone()


def find_profile(
    conn: sqlite3.Connection,
    *,
    telegram_user_id: int | None,
    birth_date: str,
    birth_time: str | None,
    time_unknown: bool,
    place_query: str,
    lat: float,
    lng: float,
    tz_str: str,
):
    return conn.execute(
        """
        SELECT * FROM profiles
        WHERE
            (telegram_user_id IS ? OR telegram_user_id = ?)
            AND birth_date = ?
            AND birth_time IS ?
            AND time_unknown = ?
            AND place_query = ?
            AND lat = ?
            AND lng = ?
            AND tz_str = ?
        """,
        (
            telegram_user_id,
            telegram_user_id,
            birth_date,
            birth_time,
            int(time_unknown),
            place_query,
            lat,
            lng,
            tz_str,
        ),
    ).fetchone()


def get_latest_chart_for_profile(conn: sqlite3.Connection, profile_id: int):
    return conn.execute(
        "SELECT * FROM charts WHERE profile_id = ? ORDER BY created_at DESC LIMIT 1",
        (profile_id,),
    ).fetchone()


def list_recent_charts(conn: sqlite3.Connection, limit: int = 5):
    """Return recent charts with basic info and place."""
    return conn.execute(
        """
        SELECT c.id, c.profile_id, c.summary, c.created_at, c.chart_json
        FROM charts c
        ORDER BY c.created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def insert_chat_message(conn: sqlite3.Connection, *, chart_id: int, question: str, answer: str | None) -> int:
    """Store chat Q/A for a chart."""
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO chat_messages (chart_id, question, answer, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (chart_id, question, answer, now),
    )
    conn.commit()
    return cur.lastrowid


def list_chat_messages(conn: sqlite3.Connection, *, chart_id: int, limit: int = 20):
    """Return recent chat messages for chart."""
    return conn.execute(
        """
        SELECT question, answer, created_at
        FROM chat_messages
        WHERE chart_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (chart_id, limit),
    ).fetchall()
