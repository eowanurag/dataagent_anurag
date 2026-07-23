"""Retry-with-backoff for provider calls.

429/5xx get exponential backoff (free-tier quota trips constantly during
builds); 4xx client errors fail fast with an actionable message.
"""
from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from src.llm.providers.base import LLMError
from src.observability.events import get_logger

_RETRIABLE = {429, 500, 502, 503, 529}
_MAX_ATTEMPTS = 4
_BASE_DELAY = 2.0


def with_retries(call: Callable[[], str], *, provider: str) -> str:
    log = get_logger("llm")
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return call()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in _RETRIABLE and attempt < _MAX_ATTEMPTS:
                delay = _BASE_DELAY * (2 ** (attempt - 1))
                log.warning("llm_retry", provider=provider, status=status,
                            attempt=attempt, delay_s=delay)
                time.sleep(delay)
                last_error = exc
                continue
            if status == 401:
                raise LLMError(
                    f"{provider}: authentication failed (401) — check the API key in .env"
                ) from exc
            if status == 404:
                raise LLMError(
                    f"{provider}: model not found (404) — the model name is probably "
                    "wrong or deprecated; check AGENT_LLM_MODEL"
                ) from exc
            if status == 429:
                raise LLMError(
                    f"{provider}: rate limit / quota exhausted (429) after "
                    f"{_MAX_ATTEMPTS} attempts — wait for quota reset or use a paid key"
                ) from exc
            raise LLMError(f"{provider}: HTTP {status} from provider") from exc
        except httpx.HTTPError as exc:
            if attempt < _MAX_ATTEMPTS:
                delay = _BASE_DELAY * (2 ** (attempt - 1))
                log.warning("llm_retry", provider=provider, error=type(exc).__name__,
                            attempt=attempt, delay_s=delay)
                time.sleep(delay)
                last_error = exc
                continue
            raise LLMError(f"{provider}: retries exhausted") from last_error
    raise LLMError(f"{provider}: retries exhausted") from last_error
