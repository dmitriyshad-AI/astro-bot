"""FastAPI backend for AstroGlass."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from astro_api import config, db
from astro_api.telegram_webapp_auth import validate_init_data, InitDataError

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
