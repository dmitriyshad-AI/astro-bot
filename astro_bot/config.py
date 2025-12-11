"""Загрузка конфигурации и базовое логирование."""

from pathlib import Path
import logging
import os
from typing import Optional, Final

# Имена переменных окружения
TELEGRAM_BOT_TOKEN_ENV: Final[str] = "TELEGRAM_BOT_TOKEN"
DB_PATH_ENV: Final[str] = "ASTRO_BOT_DB_PATH"
LOG_LEVEL_ENV: Final[str] = "ASTRO_BOT_LOG_LEVEL"

# Значения по умолчанию
DEFAULT_DB_PATH: Path = Path(__file__).resolve().parent.parent / "astro_bot.db"


def get_bot_token() -> Optional[str]:
    """Получить токен бота из переменной окружения."""
    return os.getenv(TELEGRAM_BOT_TOKEN_ENV)


def get_db_path() -> Path:
    """Получить путь к базе данных, можно переопределить через ASTRO_BOT_DB_PATH."""
    env_value = os.getenv(DB_PATH_ENV)
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_DB_PATH


def setup_logging() -> None:
    """Настроить базовое логирование."""
    level_name = os.getenv(LOG_LEVEL_ENV, "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
