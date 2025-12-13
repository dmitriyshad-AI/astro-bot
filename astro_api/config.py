"""Configuration helpers for FastAPI backend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from astro_bot.config import (
    TELEGRAM_BOT_TOKEN_ENV,  # reuse same env name
    OPENAI_API_KEY_ENV,
    OPENAI_MODEL_ENV,
    OPENAI_TEMPERATURE_ENV,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_TEMPERATURE,
)
from astro_bot import config as bot_config

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


def get_openai_api_key() -> Optional[str]:
    """Return OpenAI key for backend (reuse bot config)."""
    return bot_config.get_openai_api_key()


def get_openai_model() -> str:
    """Return OpenAI model for backend (reuse bot config)."""
    return os.getenv(OPENAI_MODEL_ENV, DEFAULT_OPENAI_MODEL)


def get_openai_temperature() -> float:
    """Return OpenAI temperature."""
    raw = os.getenv(OPENAI_TEMPERATURE_ENV)
    if raw is None:
        return DEFAULT_TEMPERATURE
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_TEMPERATURE


def get_init_data_max_age_seconds() -> int:
    """Max age for Telegram WebApp initData (seconds). Default: 24h."""
    raw = os.getenv("INIT_DATA_MAX_AGE_SECONDS")
    if raw is None:
        return 86400
    try:
        return int(raw)
    except ValueError:
        return 86400
