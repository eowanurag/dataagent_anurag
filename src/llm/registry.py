"""Model registry + selection metadata for the portal."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelVariant:
    id: str
    provider: str
    label: str
    context: int = 8192
    tags: list[str] = field(default_factory=list)
    default: bool = False


_VARIANTS: list[ModelVariant] = [
    # OpenRouter catalog candidates commonly available through /models.
    ModelVariant(id="meta-llama/llama-3.1-70b-instruct", provider="openrouter", label="Llama 3.1 70B", context=131072, tags=["chat","balanced"], default=True),
    ModelVariant(id="google/gemini-2.5-flash", provider="openrouter", label="Gemini 2.5 Flash", context=1048576, tags=["chat","fast","long"]),
    ModelVariant(id="qwen/qwen-2.5-72b-instruct", provider="openrouter", label="Qwen 2.5 72B", context=32768, tags=["chat","balanced"]),
    ModelVariant(id="deepseek/deepseek-chat", provider="openrouter", label="DeepSeek Chat", context=65536, tags=["chat","fast"]),
    ModelVariant(id="nvidia/llama-3.1-nemotron-70b-instruct", provider="openrouter", label="Nemotron 70B", context=32768, tags=["chat","balanced"]),
]


def list_variants() -> list[dict[str, Any]]:
    now = int(time.time())
    out: list[dict[str, Any]] = []
    for v in _VARIANTS:
        out.append({
            "id": v.id,
            "provider": v.provider,
            "label": v.label,
            "context": v.context,
            "tags": list(v.tags),
            "default": bool(v.default),
            "selected_at": now,
        })
    return out


def best_variant(preferred_id: str = "") -> dict[str, Any]:
    variants = list_variants()
    if preferred_id:
        for v in variants:
            if v["id"] == preferred_id:
                return v
    for v in variants:
        if v.get("default"):
            return v
    return variants[0]


def canonicalize(model_id: str) -> str:
    cleaned = (model_id or "").strip().lower()
    mapping = {
        "meta/llama-3.1-70b-instruct": "meta-llama/llama-3.1-70b-instruct",
    }
    return mapping.get(cleaned, model_id)
