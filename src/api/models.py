"""Expose model registry metadata for the left-panel model selector."""
from __future__ import annotations

from fastapi import APIRouter

from src.llm.registry import best_variant, list_variants

router = APIRouter()


@router.get("/models")
def get_models() -> dict:
    variants = list_variants()
    selected = best_variant()
    unique = []
    seen = set()
    for item in variants:
        key = (item.get("id"), item.get("provider"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return {
        "selected": selected,
        "models": unique,
        "count": len(unique),
    }
