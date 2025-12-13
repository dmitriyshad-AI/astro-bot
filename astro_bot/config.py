"""Загрузка конфигурации и базовое логирование."""

import logging
import os
from pathlib import Path
from typing import Optional, Final

from dotenv import load_dotenv

# Автоматически загрузим .env, если он есть.
load_dotenv()

# Имена переменных окружения
TELEGRAM_BOT_TOKEN_ENV: Final[str] = "TELEGRAM_BOT_TOKEN"
DB_PATH_ENV: Final[str] = "ASTRO_BOT_DB_PATH"
LOG_LEVEL_ENV: Final[str] = "ASTRO_BOT_LOG_LEVEL"
OPENAI_API_KEY_ENV: Final[str] = "OPENAI_API_KEY"
OPENAI_MODEL_ENV: Final[str] = "OPENAI_MODEL"
OPENAI_TEMPERATURE_ENV: Final[str] = "OPENAI_TEMPERATURE"
NOMINATIM_USER_AGENT_ENV: Final[str] = "ASTRO_BOT_USER_AGENT"
CHARTS_DIR_ENV: Final[str] = "ASTRO_BOT_CHARTS_DIR"

# Значения по умолчанию
DEFAULT_DB_PATH: Path = Path(__file__).resolve().parent.parent / "astro_bot.db"
DEFAULT_OPENAI_MODEL: str = "gpt-4o-mini"
DEFAULT_TEMPERATURE: float = 0.7
DEFAULT_USER_AGENT: str = "astro-bot (contact: set ASTRO_BOT_USER_AGENT)"
DEFAULT_CHARTS_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "charts"


def get_bot_token() -> Optional[str]:
    """Получить токен бота из переменной окружения."""
    return os.getenv(TELEGRAM_BOT_TOKEN_ENV)


def get_openai_api_key() -> Optional[str]:
    """Получить ключ OpenAI."""
    return os.getenv(OPENAI_API_KEY_ENV)


def get_openai_model() -> str:
    """Модель OpenAI, по умолчанию gpt-4o-mini."""
    return os.getenv(OPENAI_MODEL_ENV, DEFAULT_OPENAI_MODEL)


def get_openai_temperature() -> float:
    """Температура для генерации, по умолчанию 0.7."""
    raw = os.getenv(OPENAI_TEMPERATURE_ENV)
    if raw is None:
        return DEFAULT_TEMPERATURE
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_TEMPERATURE


def get_db_path() -> Path:
    """Получить путь к базе данных, можно переопределить через ASTRO_BOT_DB_PATH."""
    env_value = os.getenv(DB_PATH_ENV)
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_DB_PATH


def get_user_agent() -> str:
    """User-Agent для запросов к Nominatim."""
    return os.getenv(NOMINATIM_USER_AGENT_ENV, DEFAULT_USER_AGENT)


def get_charts_dir() -> Path:
    """Папка для сохранения SVG-карт."""
    env_value = os.getenv(CHARTS_DIR_ENV)
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_CHARTS_DIR


def setup_logging() -> None:
    """Настроить базовое логирование."""
    level_name = os.getenv(LOG_LEVEL_ENV, "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
