"""FastAPI backend for AstroGlass."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
import json

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from astro_api import config, db
from astro_api import natal_service
from astro_api import insights_service
from astro_api.telegram_webapp_auth import validate_init_data, InitDataError
from astro_bot import openai_client

logger = logging.getLogger(__name__)

app = FastAPI(title="AstroGlass API")


@app.get("/api/health")
async def health():
    """Simple healthcheck."""
    return {"status": "ok"}


def get_dist_paths() -> tuple[Optional[Path], Optional[Path]]:
    """Return (dist_dir, index_html) if exists, else (None, None)."""
    dist_dir = config.get_webapp_dist_dir()
    index_html = dist_dir / "index.html"
    if dist_dir.exists() and index_html.exists():
        return dist_dir, index_html
    return None, None


def mount_static_if_available(app: FastAPI) -> None:
    dist_dir, index_html = get_dist_paths()
    if dist_dir and index_html:
        app.mount(
            "/",
            StaticFiles(directory=dist_dir, html=True),
            name="frontend",
        )
        logger.info("Mounted static frontend at %s", dist_dir)
    else:
        logger.warning("webapp/dist not found; serving fallback placeholder.")


@app.get("/", response_class=HTMLResponse)
async def serve_root():
    dist_dir, index_html = get_dist_paths()
    if dist_dir and index_html:
        return FileResponse(index_html)

    # Fallback page
    return HTMLResponse(
        """
        <html>
        <head><title>AstroGlass</title></head>
        <body style="font-family: system-ui; padding: 2rem;">
            <h1>WebApp not built yet</h1>
            <p>Run <code>cd webapp && npm install && npm run build</code> to build frontend.</p>
        </body>
        </html>
        """,
        status_code=200,
    )


@app.on_event("startup")
async def on_startup() -> None:
    mount_static_if_available(app)
    conn = db.get_connection()
    db.init_db(conn)


def get_init_data_from_request(request: Request, auth_header: Optional[str]) -> Optional[str]:
    """Extract initData from Authorization header or JSON body."""
    if auth_header and auth_header.lower().startswith("tma "):
        return auth_header[4:].strip()
    try:
        body = request.json()
    except Exception:
        body = None
    if hasattr(body, "__await__"):
        # If it's awaitable (async request.json())
        body = None
    return None


@app.post("/api/auth/whoami")
async def whoami(request: Request, authorization: Optional[str] = Header(None)):
    """Validate Telegram initData and return user info."""
    bot_token = config.get_telegram_bot_token()
    if not bot_token:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": {"code": "server_misconfigured", "message": "Bot token is not configured on server"}},
        )

    # Extract initData: prefer Authorization: tma <data>
    init_data = None
    if authorization and authorization.lower().startswith("tma "):
        init_data = authorization[4:].strip()
    else:
        try:
            payload = await request.json()
            init_data = payload.get("init_data") if isinstance(payload, dict) else None
        except Exception:
            init_data = None

    if not init_data:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": {"code": "missing_init_data", "message": "initData is required"}},
        )

    logger.info("Received whoami request with initData length: %d", len(init_data))

    try:
        validated = validate_init_data(init_data, bot_token, config.get_init_data_max_age_seconds())
    except InitDataError as exc:
        status = 401 if exc.code in {"invalid_init_data", "expired_init_data"} else 400
        return JSONResponse(status_code=status, content={"ok": False, "error": {"code": exc.code, "message": exc.message}})
    except Exception:
        logger.exception("Unexpected error validating initData")
        return JSONResponse(status_code=500, content={"ok": False, "error": {"code": "internal_error", "message": "Failed to validate initData"}})

    # Upsert user into API DB
    conn = db.get_connection()
    db.init_db(conn)
    user_data = validated.get("user") or {}
    if user_data.get("id"):
        db.upsert_user(conn, user_data)

    return {
        "ok": True,
        "user": user_data,
        "auth_date": validated["auth_date"],
        "is_fresh": validated["is_fresh"],
    }


@app.get("/api/geo/search")
async def geo_search(q: Optional[str] = None):
    """Geocoding endpoint with cache."""
    if not q:
        return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "missing_query", "message": "q is required"}})
    conn = db.get_connection()
    db.init_db(conn)
    try:
        location = natal_service.resolve_location(conn, q)
    except Exception as exc:  # pylint: disable=broad-except
        return JSONResponse(status_code=500, content={"ok": False, "error": {"code": "geo_error", "message": str(exc)}})
    return {
        "ok": True,
        "location": {
            "query": location.query,
            "display_name": location.display_name,
            "lat": location.lat,
            "lng": location.lng,
            "tz_str": location.tz_str,
        },
    }


@app.post("/api/natal/calc")
async def natal_calc(payload: dict):
    """Calculate natal chart and return ids + summary."""
    required = ["birth_date", "place"]
    for key in required:
        if key not in payload:
            return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "missing_field", "message": f"{key} is required"}})

    birth_date = payload.get("birth_date")
    birth_time = payload.get("birth_time")
    place = payload.get("place")
    telegram_user_id = payload.get("telegram_user_id")
    label = payload.get("label")

    conn = db.get_connection()
    db.init_db(conn)
    try:
        result = natal_service.calculate_natal_chart(
            conn=conn,
            birth_date_str=birth_date,
            birth_time_str=birth_time,
            place_query=place,
            user_identifier=str(telegram_user_id or "guest"),
            charts_dir=config.get_webapp_dist_dir().parent / "charts",
            telegram_user_id=telegram_user_id,
            label=label,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": {"code": "calc_error", "message": str(exc)}},
        )

    wheel_url = f"/api/natal/{result['chart_id']}/wheel.svg"
    return {
        "ok": True,
        "chart_id": result["chart_id"],
        "profile_id": result["profile_id"],
        "summary": result["summary"],
        "wheel_url": wheel_url,
        "chart": result["chart"],
        "location": result["location"],
    }


@app.get("/api/natal/{chart_id}")
async def get_chart(chart_id: int):
    """Return stored chart JSON."""
    conn = db.get_connection()
    db.init_db(conn)
    row = db.get_chart(conn, chart_id)
    if not row:
        return JSONResponse(status_code=404, content={"ok": False, "error": {"code": "not_found", "message": "chart not found"}})
    return {
        "ok": True,
        "chart": row["chart_json"],
        "wheel_url": f"/api/natal/{chart_id}/wheel.svg",
        "summary": row["summary"],
        "created_at": row["created_at"],
    }


@app.get("/api/natal/{chart_id}/wheel.svg")
async def get_wheel(chart_id: int):
    conn = db.get_connection()
    db.init_db(conn)
    row = db.get_chart(conn, chart_id)
    if not row or not row["wheel_path"]:
        return JSONResponse(status_code=404, content={"ok": False, "error": {"code": "not_found", "message": "wheel not found"}})
    wheel_path = Path(row["wheel_path"])
    if not wheel_path.exists():
        return JSONResponse(status_code=404, content={"ok": False, "error": {"code": "not_found", "message": "wheel file missing"}})
    return FileResponse(wheel_path, media_type="image/svg+xml")


@app.get("/api/insights/{chart_id}")
async def get_insights(chart_id: int):
    """Generate insights for chart via OpenAI."""
    if not config.get_openai_api_key():
        return JSONResponse(status_code=500, content={"ok": False, "error": {"code": "server_misconfigured", "message": "OPENAI_API_KEY not set"}})
    conn = db.get_connection()
    db.init_db(conn)
    row = db.get_chart(conn, chart_id)
    if not row or not row["chart_json"]:
        return JSONResponse(status_code=404, content={"ok": False, "error": {"code": "not_found", "message": "chart not found"}})
    chart_payload = None
    if row["chart_json"]:
        try:
            chart_payload = json.loads(row["chart_json"]) if isinstance(row["chart_json"], str) else row["chart_json"]
        except Exception:  # pylint: disable=broad-except
            logger.warning("Failed to parse chart_json for chart_id=%s", chart_id)

    context_text = insights_service.build_context_from_chart(chart_payload)
    if not context_text:
        context_text = row["summary"] or "Натальная карта"
    try:
        insights = insights_service.generate_insights(context_text)
    except Exception as exc:  # pylint: disable=broad-except
        return JSONResponse(status_code=500, content={"ok": False, "error": {"code": "insight_error", "message": str(exc)}})
    return {"ok": True, "insights": insights.get("insights_text")}


@app.post("/api/ask")
async def ask_question(payload: dict):
    """Answer a user question based on stored chart context."""
    if not config.get_openai_api_key():
        return JSONResponse(status_code=500, content={"ok": False, "error": {"code": "server_misconfigured", "message": "OPENAI_API_KEY not set"}})
    question = payload.get("question")
    chart_id = payload.get("chart_id")
    if not question or not chart_id:
        return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "missing_field", "message": "chart_id and question are required"}})

    conn = db.get_connection()
    db.init_db(conn)
    row = db.get_chart(conn, int(chart_id))
    if not row or not row["chart_json"]:
        return JSONResponse(status_code=404, content={"ok": False, "error": {"code": "not_found", "message": "chart not found"}})

    chart_payload = None
    if row["chart_json"]:
        try:
            chart_payload = json.loads(row["chart_json"]) if isinstance(row["chart_json"], str) else row["chart_json"]
        except Exception:  # pylint: disable=broad-except
            chart_payload = None

    context_text = insights_service.build_context_from_chart(chart_payload)
    if not context_text:
        context_text = row["summary"] or "Натальная карта"

    prompt = (
        "Ты профессиональный астролог. Ответь на вопрос пользователя, опираясь только на данные натальной карты.\n"
        "Не придумывай новые позиции, используй факты ниже.\n\n"
        f"Натальная карта:\n{context_text}\n\n"
        f"Вопрос: {question}\nОтвет:"
    )
    try:
        answer = openai_client.ask_gpt(prompt, role="астролог")
    except Exception as exc:  # pylint: disable=broad-except
        return JSONResponse(status_code=500, content={"ok": False, "error": {"code": "ask_error", "message": str(exc)}})

    try:
        db.insert_chat_message(conn, chart_id=int(chart_id), question=question, answer=answer)
    except Exception:  # pylint: disable=broad-except
        logger.warning("Failed to persist chat message for chart_id=%s", chart_id)

    history_rows = db.list_chat_messages(conn, chart_id=int(chart_id), limit=20) or []
    history = [
        {"question": r["question"], "answer": r["answer"], "created_at": r["created_at"]}
        for r in reversed(history_rows)
    ]
    return {"ok": True, "answer": answer, "history": history}


@app.get("/api/charts/recent")
async def get_recent_charts(limit: int = 5):
    """Return recent charts for quick reopen."""
    conn = db.get_connection()
    db.init_db(conn)
    rows = db.list_recent_charts(conn, limit=limit)
    charts = []
    for r in rows or []:
        charts.append(
            {
                "id": r["id"],
                "profile_id": r["profile_id"],
                "summary": r["summary"],
                "created_at": r["created_at"],
                "place_query": r["place_query"],
            }
        )
    return {"ok": True, "charts": charts}
