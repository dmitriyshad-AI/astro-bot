"""Configuration helpers for FastAPI backend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def get_repo_root() -> Path:
    """Return repository root (two levels above this file)."""
    return Path(__file__).resolve().parent.parent


def get_webapp_dist_dir() -> Path:
    """Directory with built frontend."""
    env = os.getenv("WEBAPP_DIST_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return get_repo_root() / "webapp" / "dist"


def get_static_root_fallback() -> Path:
    """Fallback location for temporary HTML when dist is missing."""
    return get_repo_root()
