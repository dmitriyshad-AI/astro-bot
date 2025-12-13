# Astro Bot

Учебный Telegram-бот по астрологии. Бот приветствует на `/start`, показывает `/help`, отвечает на `/ask` через OpenAI, считает натальную карту через `/natal` (Placidus, оффлайн‑эпемериды), повторяет текстовые сообщения и сохраняет пользователей и историю запросов в локальную SQLite-базу. Добавлен лёгкий FastAPI backend и WebApp (Vite) для будущей Mini App.

## Требования
- Python 3.10+
- Node.js 18+ (для фронтенда)

## Быстрый старт (бот)
1. Создайте и активируйте виртуальное окружение (macOS):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
3. Скопируйте `.env.example` в `.env` и заполните токены (файл подхватывается автоматически):
   ```bash
   cp .env.example .env
   # TELEGRAM_BOT_TOKEN, OPENAI_API_KEY и др.
   ```
4. Запустите бота:
   ```bash
   python -m astro_bot.bot
   ```
По умолчанию база создаётся в `astro_bot.db` в корне проекта (путь можно переопределить через `ASTRO_BOT_DB_PATH`). Логирование настраивается переменной `ASTRO_BOT_LOG_LEVEL` (по умолчанию INFO). Команда `/history` покажет последние запросы (можно указать число: `/history 5`).

## Mini App: backend (FastAPI) + frontend (Vite)
Требования: Python 3.10+, Node.js 18+.

### Backend (FastAPI)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn astro_api.main:app --reload --port 8000
```
Маршрут `/api/health` отдаёт `{"status":"ok"}`. Если собран frontend (`webapp/dist`), бэкенд отдаёт его на `/` и статику; иначе показывает заглушку.
- Основные API сейчас: `/api/geo/search`, `/api/natal/calc`, `/api/natal/{id}`, `/api/natal/{id}/wheel.svg`, `/api/insights/{chart_id}`, `/api/ask`.
- Быстрый список карт: `/api/charts/recent` (для быстрого открытия последней/недавних карт в Mini App).

### Frontend (Vite, vanilla)
```bash
cd webapp
npm install
npm run dev   # http://localhost:5173
```

Сборка:
```bash
cd webapp && npm run build
# затем в корне:
uvicorn astro_api.main:app --reload --port 8000
# открыть http://localhost:8000
```
Telegram Mini App требует HTTPS-URL; локально можно смотреть в браузере. Для теста в Telegram без деплоя используйте туннель (например, `ngrok http 8000` или Cloudflare Tunnel), возьмите выданный https://... и вставьте в `WEBAPP_PUBLIC_URL`.

### Подключение Mini App в боте
- В `.env` задайте `WEBAPP_PUBLIC_URL=https://ваш_https_адрес` (для Telegram нужен HTTPS; для локальной проверки в браузере можно временно http — бот предупредит).
- Опционально `WEBAPP_MENU_TEXT=AstroGlass`.
- Запустите бота: `python -m astro_bot.bot`.
- В Telegram: команды `/start` или `/app` покажут кнопку “Открыть AstroGlass”. Бот пытается установить кнопку меню WebApp; если не удалось, остаётся inline-кнопка.

## Натальная карта
- Геокодинг через Nominatim (нужен интернет, 1 запрос/сек, кастомный User-Agent в `ASTRO_BOT_USER_AGENT`).
- Часовой пояс оффлайн через `timezonefinder`.
- Расчёт оффлайн (kerykeion/Swiss Ephemeris), система домов Placidus.
- Результат: SVG круг натальной карты + текст (углы, дома, планеты/узлы/астероды, аспекты). При наличии OPENAI_API_KEY дополнительно генерируется интерпретация по фактическим позициям.
- В Mini App доступны вкладки: основное, планеты, дома, аспекты, инсайты (генерация через OpenAI), wheel (SVG) и “Вопрос по карте” (чат с OpenAI на основе контекста карты).
- Есть блок “Недавние карты” (берётся из API) и кнопка “Открыть последнюю карту”.
- Вкладка “Совместимость” — расчёт синстрии по вашим данным и данным партнёра: score, ключевые/топ аспекты, wheel.

## Самопроверка без Telegram
- CLI: `python -m astro_bot.debug_natal --date 12.03.1990 --time 08:30 --place "Москва, Россия"`
- Тесты:
  ```bash
  python -m unittest tests.test_natal_engine tests.test_init_data_validation tests.test_api_chat_insights tests.test_compatibility_api
  ```
- Веб auth: `npm run dev` (в webapp) и `uvicorn astro_api.main:app --reload --port 8000`, затем `http://localhost:5173/?debug=1` → вставить initData и нажать Validate.

## Деплой с HTTPS (кратко)
- Собрать фронт: `cd webapp && npm install && npm run build`.
- Запуск uvicorn на сервере: `uvicorn astro_api.main:app --host 0.0.0.0 --port 8000` (под systemd/supervisor).
- Прокси с сертификатом:
  - вариант A: Nginx + certbot (Let’s Encrypt) на ваш домен, проксируем на http://127.0.0.1:8000;
  - вариант B: Cloudflare Tunnel с кастомным доменом и готовым HTTPS;
  - вариант C: ngrok с платным доменом (нужен постоянный https).
- В `.env` на сервере выставить `WEBAPP_PUBLIC_URL=https://ваш_домен`, `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `ASTRO_BOT_USER_AGENT`.
- Проверить: домен открывается в браузере/iOS Safari; бот `/start` или `/app` открывает Mini App без предупреждений.
