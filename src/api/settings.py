"""User/runtime settings API — provider/model selection, cost rates/reset."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.api._common import api_error, ok
from src.services.settings_store import (
    load_cost_rates,
    load_user_settings,
    save_cost_rates,
    save_provider_model,
)

router = APIRouter()


@router.get("/settings")
def get_settings_endpoint() -> dict:
    return ok(load_user_settings())


@router.post("/settings/provider-model")
def set_provider_model(payload: dict[str, Any]) -> dict:
    provider = (payload.get("provider") or "").strip()
    model = (payload.get("model") or "").strip()
    if not provider or not model:
        raise api_error("bad_request", "provider and model are required", 400)
    data = save_provider_model(provider, model)
    return ok(data)


@router.post("/settings/cost-rates")
def set_cost_rates(payload: dict[str, Any]) -> dict:
    try:
        cost_in = payload.get("cost_per_million_in")
        cost_out = payload.get("cost_per_million_out")
        currency = (payload.get("currency") or "USD").strip().upper()
        data = save_cost_rates(
            float(cost_in) if cost_in is not None else None,
            float(cost_out) if cost_out is not None else None,
            currency or "USD",
        )
    except (TypeError, ValueError) as exc:
        raise api_error("bad_request", str(exc), 400) from exc
    return ok(data)


@router.delete("/settings/cost-rates")
def reset_cost_rates() -> dict:
    data = save_cost_rates(None, None, "USD")
    return ok(data)
