"""Expose model registry metadata for the left-panel model selector."""
from __future__ import annotations

from fastapi import APIRouter

from src.llm.registry import best_variant, list_variants

router = APIRouter()


@router.get("/models")
def get_models() -> dict:
    variants = list_variants()
    selected = best_variant()
    return {
        "selected": selected,
        "models": variants,
        "count": len(variants),
    }
