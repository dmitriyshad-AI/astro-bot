"""FastAPI backend for AstroGlass."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from astro_api import config

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
