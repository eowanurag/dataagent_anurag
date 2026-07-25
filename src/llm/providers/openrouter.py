"""OpenRouter provider — OpenAI-compatible chat/completions over httpx.

Any model on OpenRouter works via the ``provider/model`` id. This adapter also
covers self-hosted OpenAI-compatible endpoints (change the base URL in .env).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import httpx

from src.llm.providers.base import LLMError, LLMProvider, Usage
from src.llm.retry import with_retries

T = TypeVar("T")


def _call_with_retries(call: Callable[[], tuple[str, Usage]], *, provider: str) -> tuple[str, Usage]:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            return call()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {429, 500, 502, 503, 529} and attempt < 4:
                last_error = exc
                continue
            if status == 401:
                raise LLMError(f"{provider}: authentication failed (401) — check the API key in .env") from exc
            if status == 404:
                raise LLMError(f"{provider}: model not found (404) — the model name is probably wrong or deprecated; check AGENT_LLM_MODEL") from exc
            raise LLMError(f"{provider}: HTTP {status} from provider") from exc
        except httpx.HTTPError as exc:
            if attempt < 4:
                last_error = exc
                continue
            raise LLMError(f"{provider}: retries exhausted") from last_error
    raise LLMError(f"{provider}: retries exhausted") from last_error


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(self, api_key: str, model: str, base_url: str = "https://openrouter.ai/api/v1") -> None:
        self._api_key = api_key
        self.model = model
        self._base_url = base_url.rstrip("/")

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        text, _ = self.complete_usage(system, user, max_tokens=max_tokens)
        return text

    def complete_usage(self, system: str, user: str, *, max_tokens: int = 1024) -> tuple[str, Usage]:
        def _call() -> tuple[str, Usage]:
            resp = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            try:
                text = (data["choices"][0]["message"]["content"] or "").strip()
            except (KeyError, IndexError) as exc:
                raise LLMError(f"openrouter returned no choices: {list(data)}") from exc
            if not text:
                raise LLMError("openrouter returned an empty completion")
            usage_body = data.get("usage") or {}
            return text, Usage(
                input_tokens=int(usage_body.get("prompt_tokens") or 0) or None,
                output_tokens=int(usage_body.get("completion_tokens") or 0) or None,
            )

        return _call_with_retries(_call, provider=self.name)
