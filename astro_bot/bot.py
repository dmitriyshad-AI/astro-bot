"""Простой echo-бот на базе python-telegram-bot."""
import asyncio
import datetime as dt
import json
import logging
import sys
from typing import Optional

from telegram import (
    Update,
    BotCommand,
    WebAppInfo,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    ConversationHandler,
    filters,
)

from astro_bot import config, db, repositories, openai_client, natal_engine

logger = logging.getLogger(__name__)
ASKING_QUESTION = 1
NATAL_DATE, NATAL_TIME, NATAL_PLACE = range(2, 5)

BOT_COMMANDS = [
    BotCommand("start", "Приветствие"),
    BotCommand("help", "Список команд"),
    BotCommand("app", "Открыть AstroGlass"),
    BotCommand("ask", "Спросить астролога"),
    BotCommand("natal", "Ввести данные рождения"),
    BotCommand("history", "Последние запросы"),
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправить приветственное сообщение на команду /start."""
    if update.message is None:
        return
    ensure_user(update, context)

    greeting = (
        "Привет! Я учебный астробот. Я могу:\n"
        "• /ask — спросить меня как астролога\n"
        "• /natal — ввести дату/время/место рождения для разбора\n"
        "• повторять обычные сообщения (echo)\n"
        "• /history — показать последние запросы\n"
        "• /app — открыть AstroGlass (Mini App)\n"
        "Если что — /help подскажет команды."
    )
    await update.message.reply_text(greeting)
    await send_webapp_button(update, context)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать список команд."""
    ensure_user(update, context)
    await update.message.reply_text(
        "/start — приветствие\n"
        "/help — список команд\n"
        "/app — открыть Mini App\n"
        "/ask — задать вопрос (OpenAI)\n"
        "/natal — ввести данные рождения\n"
        "/history — показать последние запросы"
    )


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
        result = await asyncio.to_thread(
            natal_engine.generate_natal_chart,
            birth_date_str=birth_date,
            birth_time_str=birth_time,
            place_query=birth_place,
            db_conn=db_conn,
            user_identifier=str(user_id),
            charts_dir=config.get_charts_dir(),
        )
    except natal_engine.NatalError as exc:
        await update.message.reply_text(str(exc))
        return ConversationHandler.END
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Ошибка генерации натальной карты: %s", exc)
        await update.message.reply_text("Не удалось сформировать разбор. Попробуйте позже.")
        return ConversationHandler.END

    for part in chunk_text(result.summary):
        await update.message.reply_text(part)

    try:
        with result.svg_path.open("rb") as svg_file:
            await update.message.reply_document(
                document=svg_file,
                filename=result.svg_path.name,
                caption="Круг натальной карты (SVG)",
            )
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Не удалось отправить SVG: %s", exc)
        await update.message.reply_text("Не удалось отправить файл SVG, но текст готов.")

    repositories.log_request(
        conn=db_conn,
        user_id=user_id,
        request_type="natal",
        input_payload=json.dumps(
            {"date": birth_date, "time": birth_time, "place": birth_place},
            ensure_ascii=False,
        ),
        response_text=result.summary,
    )

    if config.get_openai_api_key():
        try:
            llm_answer = openai_client.ask_gpt(
                question=(
                    "Сделай профессиональный астрологический разбор на основе фактических позиций:\n"
                    f"{result.context_text}\n"
                    "Дай 4-6 осмысленных пунктов без выдуманных позиций."
                ),
                role="астролог",
            )
            for part in chunk_text(llm_answer):
                await update.message.reply_text(part)
            repositories.log_request(
                conn=db_conn,
                user_id=user_id,
                request_type="natal_llm",
                input_payload=result.context_text,
                response_text=llm_answer,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка LLM-интерпретации: %s", exc)

    context.user_data.pop("natal", None)
    return ConversationHandler.END


async def set_commands(application: Application) -> None:
    """Установить меню команд в Telegram и кнопку WebApp, если URL задан."""
    await application.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Команды бота обновлены: %s", [cmd.command for cmd in BOT_COMMANDS])

    url, warn = describe_webapp_url()
    if not url:
        logger.info("WEBAPP_PUBLIC_URL не задан, кнопку меню WebApp не устанавливаем.")
        return
    if warn:
        logger.warning(warn)
    try:
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text=config.get_webapp_menu_text(),
                web_app=WebAppInfo(url=url),
            )
        )
        logger.info("Кнопка меню WebApp установлена.")
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Не удалось установить кнопку меню WebApp: %s", exc)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вывести последние N запросов пользователя."""
    user_id = ensure_user(update, context)
    if user_id is None:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    db_conn = context.application.bot_data.get("db_conn")
    if db_conn is None:
        await update.message.reply_text("История недоступна: нет соединения с БД.")
        return

    limit = 5
    if context.args:
        try:
            limit = max(1, min(20, int(context.args[0])))
        except ValueError:
            await update.message.reply_text("Введите число после /history, например /history 5.")
            return

    rows = db_conn.execute(
        """
        SELECT type, input_payload, response_text, created_at
        FROM requests
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()

    if not rows:
        await update.message.reply_text("История пуста.")
        return

    lines = []
    for row in rows:
        snippet = (row["response_text"] or "")[:120].replace("\n", " ")
        lines.append(f"{row['created_at']} | {row['type']} | {snippet}")

    await update.message.reply_text("\n".join(lines))


async def open_app(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /app — отправить кнопку открытия WebApp."""
    await send_webapp_button(update, context)


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


def chunk_text(text: str, max_len: int = 3500) -> list[str]:
    """Разбить длинный текст на части для Telegram."""
    lines = text.splitlines()
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current.rstrip())
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def build_webapp_markup(url: str) -> InlineKeyboardMarkup:
    """Собрать inline-клавиатуру для открытия WebApp."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=config.get_webapp_menu_text(),
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


def describe_webapp_url() -> tuple[Optional[str], Optional[str]]:
    """Вернуть (url, warning) если url задан, но не https."""
    url = config.get_webapp_url()
    if not url:
        return None, None
    warning = None
    if not url.startswith("https://"):
        warning = "Для Mini App нужен HTTPS URL. Текущий URL не https, в Telegram может не открыться."
    return url, warning


async def send_webapp_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправить кнопку WebApp или подсказку о настройке URL."""
    if update.message is None:
        return
    url, warning = describe_webapp_url()
    if not url:
        await update.message.reply_text(
            "WEBAPP_PUBLIC_URL не настроен. Установите переменную окружения "
            "WEBAPP_PUBLIC_URL на ваш HTTPS URL Mini App."
        )
        return
    if warning:
        await update.message.reply_text(f"{warning}\nURL: {url}")
    await update.message.reply_text(
        "Открыть AstroGlass:",
        reply_markup=build_webapp_markup(url),
    )


def run_bot(token: str) -> None:
    """Инициализировать приложение и запустить бота."""
    config.setup_logging()
    url, warn = describe_webapp_url()
    if url:
        logger.info("WEBAPP_PUBLIC_URL: %s", url)
        if warn:
            logger.warning(warn)
    else:
        logger.info("WEBAPP_PUBLIC_URL не задан, кнопка WebApp показывать не будем.")

    application: Application = (
        ApplicationBuilder()
        .token(token)
        .post_init(set_commands)
        .build()
    )

    # Подготовка каталога карт (очистка старых файлов)
    natal_engine.cleanup_old_svgs(config.get_charts_dir())

    # Инициализация БД и сохранение соединения в bot_data
    db_conn = db.get_connection()
    db.init_db(db_conn)
    application.bot_data["db_conn"] = db_conn

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
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
    application.add_handler(CommandHandler("app", open_app))
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
    application.add_handler(CommandHandler("history", history))
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
