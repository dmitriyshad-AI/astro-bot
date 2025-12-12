"""Простой echo-бот на базе python-telegram-bot."""
"""Я важный писюнец"""
import datetime as dt
import json
import logging
import sys
from typing import Optional

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    ConversationHandler,
    filters,
)

from astro_bot import config, db, repositories, openai_client, astro_service

logger = logging.getLogger(__name__)
ASKING_QUESTION = 1
NATAL_DATE, NATAL_TIME, NATAL_PLACE = range(2, 5)

BOT_COMMANDS = [
    BotCommand("start", "Приветствие"),
    BotCommand("ask", "Спросить астролога"),
    BotCommand("natal", "Ввести данные рождения"),
]


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


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать сценарий задавания вопроса."""
    ensure_user(update, context)
    await update.message.reply_text("Напиши свой вопрос, я отвечу как астролог.")
    return ASKING_QUESTION


async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получить вопрос, спросить OpenAI и вернуть ответ."""
    if update.message is None:
        return ConversationHandler.END

    user_id = ensure_user(update, context)
    if user_id is None:
        await update.message.reply_text("Не удалось сохранить пользователя, попробуйте ещё раз.")
        return ConversationHandler.END

    question_text = update.message.text
    db_conn = context.application.bot_data.get("db_conn")

    try:
        answer = openai_client.ask_gpt(question_text)
    except openai_client.OpenAIError as exc:
        logger.error("Ошибка OpenAI: %s", exc)
        await update.message.reply_text("Не удалось получить ответ от модели. Попробуйте позже.")
        return ConversationHandler.END

    await update.message.reply_text(answer)

    if db_conn is None:
        logger.warning("Пропущено логирование запроса: нет соединения с БД")
        return ConversationHandler.END

    payload = json.dumps({"question": question_text})
    repositories.log_request(
        conn=db_conn,
        user_id=user_id,
        request_type="general_question",
        input_payload=payload,
        response_text=answer,
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменить диалог /ask."""
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


async def natal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать сбор данных для натальной карты."""
    ensure_user(update, context)
    context.user_data["natal"] = {}
    await update.message.reply_text(
        "Укажи дату рождения в формате ДД.ММ.ГГГГ (пример: 12.03.1990)."
    )
    return NATAL_DATE


async def natal_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получить дату рождения."""
    if update.message is None:
        return ConversationHandler.END

    text = update.message.text.strip()
    try:
        dt.datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        await update.message.reply_text(
            "Не понял дату. Введи в формате ДД.ММ.ГГГГ, например 12.03.1990."
        )
        return NATAL_DATE

    context.user_data.setdefault("natal", {})["date"] = text
    await update.message.reply_text(
        "Укажи время рождения в формате ЧЧ:ММ. Если не знаешь, напиши «не знаю»."
    )
    return NATAL_TIME


async def natal_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получить время рождения (может быть неизвестно)."""
    if update.message is None:
        return ConversationHandler.END

    text = update.message.text.strip()
    lowered = text.casefold()
    birth_time: Optional[str]
    if lowered in {"", "не знаю", "не помню", "нет", "неизвестно"}:
        birth_time = None
    else:
        try:
            dt.datetime.strptime(text, "%H:%M")
            birth_time = text
        except ValueError:
            await update.message.reply_text(
                "Не понял время. Укажи в формате ЧЧ:ММ (например, 08:30) или напиши «не знаю»."
            )
            return NATAL_TIME

    context.user_data.setdefault("natal", {})["time"] = birth_time
    await update.message.reply_text(
        "Укажи место рождения (город, страна)."
    )
    return NATAL_PLACE


async def natal_place(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получить место рождения и сгенерировать краткий разбор."""
    if update.message is None:
        return ConversationHandler.END

    place = update.message.text.strip()
    if len(place) < 2:
        await update.message.reply_text("Слишком коротко. Укажи город и страну.")
        return NATAL_PLACE

    data = context.user_data.get("natal", {})
    data["place"] = place

    user_id = ensure_user(update, context)
    if user_id is None:
        await update.message.reply_text("Не удалось сохранить пользователя, попробуйте ещё раз.")
        return ConversationHandler.END

    db_conn = context.application.bot_data.get("db_conn")
    birth_date = data.get("date", "")
    birth_time = data.get("time")
    birth_place = data.get("place", "")

    try:
        report = astro_service.generate_natal_report(
            birth_date=birth_date,
            birth_time=birth_time,
            birth_place=birth_place,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Ошибка генерации натальной карты: %s", exc)
        await update.message.reply_text(
            "Не удалось сформировать разбор. Попробуйте позже."
        )
        return ConversationHandler.END

    await update.message.reply_text(report)

    if db_conn is None:
        logger.warning("Пропущено логирование запроса: нет соединения с БД")
        return ConversationHandler.END

    payload = json.dumps(
        {"date": birth_date, "time": birth_time, "place": birth_place},
        ensure_ascii=False,
    )
    repositories.log_request(
        conn=db_conn,
        user_id=user_id,
        request_type="natal",
        input_payload=payload,
        response_text=report,
    )

    context.user_data.pop("natal", None)
    return ConversationHandler.END


async def set_commands(application: Application) -> None:
    """Установить меню команд в Telegram."""
    await application.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Команды бота обновлены: %s", [cmd.command for cmd in BOT_COMMANDS])


def ensure_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
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
    application: Application = (
        ApplicationBuilder()
        .token(token)
        .post_init(set_commands)
        .build()
    )

    # Инициализация БД и сохранение соединения в bot_data
    db_conn = db.get_connection()
    db.init_db(db_conn)
    application.bot_data["db_conn"] = db_conn

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("ask", ask)],
            states={
                ASKING_QUESTION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question)
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("natal", natal_start)],
            states={
                NATAL_DATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, natal_date)
                ],
                NATAL_TIME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, natal_time)
                ],
                NATAL_PLACE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, natal_place)
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )
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
