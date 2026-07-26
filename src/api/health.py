"""Health check — reports which provider is active (presence only, never keys)."""
from __future__ import annotations

from fastapi import APIRouter

from src.api._common import ok
from src.config.settings import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    from src.services.settings_store import load_user_settings

    s = get_settings()
    saved = load_user_settings()
    saved_provider = (saved.get("provider") or "").strip().lower()
    saved_model = (saved.get("model") or "").strip()
    provider = saved_provider or s.resolve_provider()
    model = saved_model or s.resolve_model()
    return ok(
        {
            "status": "ok",
            "provider": provider,
            "model": model,
            "key_configured": provider != "stub",
        }
    )
