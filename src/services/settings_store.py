"""Persist lightweight UI/runtime settings in SQLite.

This stores the user's selected provider/model and token/cost tracking state.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from typing import Any

from src.config.settings import get_settings
from src.db.session import create_db_session


_KEY = "user_settings"
_lock = threading.Lock()
_mem: dict[str, dict[str, Any]] = {}


def _ensure_schema() -> None:
    with create_db_session() as session:
        session.execute(
            """
            CREATE TABLE IF NOT EXISTS settings_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        session.commit()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def load_user_settings() -> dict[str, Any]:
    _ensure_schema()
    key = _KEY
    with create_db_session() as session:
        row = session.execute(
            "SELECT value FROM settings_store WHERE key = :k",
            {"k": key},
        ).fetchone()
        if row is None:
            return _defaults()
        try:
            value = json.loads(row.value)
        except json.JSONDecodeError:
            return _defaults()
    return {**_defaults(), **value}


def save_provider_model(provider: str, model: str) -> dict[str, Any]:
    current = load_user_settings()
    payload = {
        "provider": provider,
        "model": model,
        "cost_per_million_in": current.get("cost_per_million_in"),
        "cost_per_million_out": current.get("cost_per_million_out"),
        "currency": current.get("currency", "USD"),
    }
    _upsert(payload)
    return payload


def save_cost_rates(cost_per_million_in: float | None, cost_per_million_out: float | None, currency: str | None = None) -> dict[str, Any]:
    current = load_user_settings()
    payload = {
        "provider": current.get("provider"),
        "model": current.get("model"),
        "cost_per_million_in": cost_per_million_in,
        "cost_per_million_out": cost_per_million_out,
        "currency": currency or current.get("currency", "USD"),
    }
    _upsert(payload)
    return payload


def load_cost_rates() -> dict[str, Any]:
    settings = load_user_settings()
    return {
        "provider": settings.get("provider"),
        "model": settings.get("model"),
        "cost_per_million_in": settings.get("cost_per_million_in"),
        "cost_per_million_out": settings.get("cost_per_million_out"),
        "currency": settings.get("currency", "USD"),
    }


def _upsert(payload: dict[str, Any]) -> None:
    _ensure_schema()
    with _lock:
        _mem[_KEY] = payload
    with create_db_session() as session:
        session.execute(
            """
            INSERT INTO settings_store (key, value, updated_at)
            VALUES (:k, :v, :now)
            ON CONFLICT(key) DO UPDATE SET value = :v, updated_at = :now
            """,
            {"k": _KEY, "v": json.dumps(payload, default=str), "now": _now_iso()},
        )
        session.commit()


def _defaults() -> dict[str, Any]:
    return {
        "provider": get_settings().resolve_provider(),
        "model": get_settings().resolve_model(),
        "cost_per_million_in": None,
        "cost_per_million_out": None,
        "currency": "USD",
    }
