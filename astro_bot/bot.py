"""Простой echo-бот на базе python-telegram-bot."""

import asyncio
import os
import sys
from typing import Final

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Название переменной окружения для токена бота
TOKEN_ENV_VAR: Final[str] = "TELEGRAM_BOT_TOKEN"


def get_bot_token() -> str | None:
    """Получить токен бота из переменной окружения."""
    return os.getenv(TOKEN_ENV_VAR)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправить приветственное сообщение на команду /start."""
    if update.message is None:
        return

    greeting = (
        "Привет! Я учебный астробот. Пока что я просто повторяю ваши сообщения."
    )
    await update.message.reply_text(greeting)


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Повторить любое текстовое сообщение пользователя."""
    if update.message is None:
        return
    await update.message.reply_text(update.message.text)


async def run_bot(token: str) -> None:
    """Инициализировать приложение и запустить бота."""
    application: Application = (
        ApplicationBuilder().token(token).build()
    )

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Запуск бота
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    print("Astro Bot запущен. Нажмите Ctrl+C для остановки.")

    # Ждем завершения (Ctrl+C)
    await application.updater.idle()
    await application.stop()
    await application.shutdown()


def main() -> None:
    """Точка входа для запуска бота."""
    token = get_bot_token()
    if not token:
        print(
            f"Не найден токен в переменной окружения {TOKEN_ENV_VAR}. "
            "Установите переменную и запустите бота снова."
        )
        sys.exit(1)

    try:
        asyncio.run(run_bot(token))
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")


if __name__ == "__main__":
    main()
