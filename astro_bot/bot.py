"""Простой echo-бот на базе python-telegram-bot."""
"""Я важный писюнец"""
import logging
import sys

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from astro_bot import config, db, repositories

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправить приветственное сообщение на команду /start."""
    if update.message is None:
        return
    ensure_user(update, context)

    greeting = (
        "Привет! Я учебный астробот. Пока что я просто повторяю ваши сообщения."
    )
    await update.message.reply_text(greeting)


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Повторить любое текстовое сообщение пользователя."""
    if update.message is None:
        return
    user_id = ensure_user(update, context)
    if user_id is None:
        return

    incoming_text = update.message.text
    await update.message.reply_text(incoming_text)

    db_conn = context.application.bot_data.get("db_conn")
    if db_conn is None:
        logger.warning("Пропущено логирование запроса: нет соединения с БД")
        return
    repositories.log_request(
        conn=db_conn,
        user_id=user_id,
        request_type="echo",
        input_payload=incoming_text,
        response_text=incoming_text,
    )


def ensure_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создать или обновить пользователя в базе."""
    tg_user = update.effective_user
    if tg_user is None:
        return None

    db_conn = context.application.bot_data.get("db_conn")
    if db_conn is None:
        logger.warning("Пропущена запись пользователя: нет соединения с БД")
        return None

    full_name_parts = [part for part in (tg_user.first_name, tg_user.last_name) if part]
    full_name = " ".join(full_name_parts) if full_name_parts else None

    return repositories.get_or_create_user(
        conn=db_conn,
        telegram_id=str(tg_user.id),
        username=tg_user.username,
        full_name=full_name,
    )


def run_bot(token: str) -> None:
    """Инициализировать приложение и запустить бота."""
    config.setup_logging()
    application: Application = ApplicationBuilder().token(token).build()

    # Инициализация БД и сохранение соединения в bot_data
    db_conn = db.get_connection()
    db.init_db(db_conn)
    application.bot_data["db_conn"] = db_conn

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Полный цикл запуска/пулинга/остановки
    logger.info("Astro Bot запущен. Нажмите Ctrl+C для остановки.")
    try:
        application.run_polling()
    finally:
        db_conn.close()


def main() -> None:
    """Точка входа для запуска бота."""
    token = config.get_bot_token()
    if not token:
        logger.error(
            "Не найден токен в переменной окружения %s. "
            "Установите переменную и запустите бота снова.",
            config.TELEGRAM_BOT_TOKEN_ENV,
        )
        sys.exit(1)

    try:
        run_bot(token)
    except KeyboardInterrupt:
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    main()
