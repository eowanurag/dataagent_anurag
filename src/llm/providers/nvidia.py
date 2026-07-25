"""NVIDIA NIM provider — OpenAI-compatible chat/completions over httpx."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from src.llm.limiter import nvidia_limited
from src.llm.providers.base import LLMError, LLMProvider, Usage
from src.llm.retry import with_rate_limit_retries


class NvidiaProvider(LLMProvider):
    name = "nvidia"
    _DEFAULT_BASE = "https://integrate.api.nvidia.com/v1"

    def __init__(self, api_key: str, model: str, base_url: str = "") -> None:
        self._api_key = api_key
        self.model = model
        self._base_url = (base_url or self._DEFAULT_BASE).rstrip("/")

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        text, _ = self.complete_usage(system, user, max_tokens=max_tokens)
        return text

    def complete_usage(self, system: str, user: str, *, max_tokens: int = 1024) -> tuple[str, Usage]:
        def _call() -> tuple[str, Usage]:
            payload = json.dumps({
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self._base_url}/chat/completions",
                data=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "content-type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=120.0) as r:
                    body = json.loads(r.read())
            except urllib.error.HTTPError as exc:
                raise LLMError(
                    f"nvidia: HTTP {exc.code} from provider"
                ) from exc
            except Exception as exc:
                raise LLMError(f"nvidia: request failed: {exc}") from exc
            try:
                choice = (body.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                text = (message.get("content") or "").strip()
            except (IndexError, KeyError) as exc:
                raise LLMError(f"nvidia returned no choices: {list(body)}") from exc
            if not text:
                raise LLMError("nvidia returned an empty completion")
            usage_body = body.get("usage") or {}
            return text, Usage(
                input_tokens=int(usage_body.get("prompt_tokens") or 0) or None,
                output_tokens=int(usage_body.get("completion_tokens") or 0) or None,
            )

        return nvidia_limited(lambda: with_rate_limit_retries(_call, provider=self.name))

    def cost_hint(self) -> dict[str, Any] | None:
        return {
            "provider": self.name,
            "model": self.model,
            "currency": "USD",
            "per_million_in": None,
            "per_million_out": None,
        }
