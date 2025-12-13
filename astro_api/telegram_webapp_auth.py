"""Telegram WebApp initData validation."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Dict, Tuple
from urllib.parse import parse_qsl


class InitDataError(Exception):
    """Base error for initData."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_init_data(init_data: str) -> Dict[str, str]:
    """Parse querystring-like initData into dict preserving blank values."""
    if not init_data:
        raise InitDataError("missing_init_data", "initData is empty")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    return pairs


def build_data_check_string(pairs: Dict[str, str]) -> Tuple[str, str]:
    """Build data_check_string and return it with received hash."""
    if "hash" not in pairs:
        raise InitDataError("invalid_init_data", "hash is missing in initData")
    received_hash = pairs["hash"]
    filtered = {k: v for k, v in pairs.items() if k != "hash"}
    parts = [f"{k}={filtered[k]}" for k in sorted(filtered.keys())]
    data_check_string = "\n".join(parts)
    return data_check_string, received_hash


def compute_hash(bot_token: str, data_check_string: str) -> str:
    """Compute HMAC-SHA256 as per Telegram docs."""
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int) -> dict:
    """Validate initData and return parsed payload with user and auth_date."""
    if not bot_token:
        raise InitDataError("server_misconfigured", "Bot token is not configured on server")

    pairs = parse_init_data(init_data)
    data_check_string, received_hash = build_data_check_string(pairs)
    computed_hash = compute_hash(bot_token, data_check_string)
    if not hmac.compare_digest(computed_hash, received_hash):
        raise InitDataError("invalid_init_data", "Hash mismatch")

    auth_date_raw = pairs.get("auth_date")
    if not auth_date_raw:
        raise InitDataError("invalid_init_data", "auth_date missing")
    try:
        auth_date_int = int(auth_date_raw)
    except ValueError as exc:
        raise InitDataError("invalid_init_data", "auth_date is not int") from exc

    now = int(time.time())
    is_fresh = (now - auth_date_int) <= max_age_seconds
    if not is_fresh:
        raise InitDataError("expired_init_data", "initData is too old")

    user_raw = pairs.get("user")
    user_data = json.loads(user_raw) if user_raw else {}

    return {
        "pairs": pairs,
        "user": user_data,
        "auth_date": auth_date_int,
        "is_fresh": is_fresh,
    }
