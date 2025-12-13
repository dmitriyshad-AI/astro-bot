"""Configuration helpers for FastAPI backend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from astro_bot.config import TELEGRAM_BOT_TOKEN_ENV  # reuse same env name

def get_repo_root() -> Path:
    """Return repository root (two levels above this file)."""
    return Path(__file__).resolve().parent.parent


def get_webapp_dist_dir() -> Path:
    """Directory with built frontend."""
    env = os.getenv("WEBAPP_DIST_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return get_repo_root() / "webapp" / "dist"


def get_static_root_fallback() -> Path:
    """Fallback location for temporary HTML when dist is missing."""
    return get_repo_root()


def get_telegram_bot_token() -> Optional[str]:
    """Return TELEGRAM_BOT_TOKEN from environment."""
    return os.getenv(TELEGRAM_BOT_TOKEN_ENV)


def get_init_data_max_age_seconds() -> int:
    """Max age for Telegram WebApp initData (seconds). Default: 24h."""
    raw = os.getenv("INIT_DATA_MAX_AGE_SECONDS")
    if raw is None:
        return 86400
    try:
        return int(raw)
    except ValueError:
        return 86400
