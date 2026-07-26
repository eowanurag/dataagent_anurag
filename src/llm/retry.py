"""Retry utilities for LLM provider calls.

OpenAI-compatible behavior is preserved by default. NVIDIA gets its own
``with_rate_limit_retries`` helper because direct NIM’s free tier can return
burst-oriented failures even when a request is retried instantly.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import httpx

from src.llm.providers.base import LLMError


T = TypeVar("T")

_RETRIABLE = {429, 500, 502, 503, 529}
_MAX_ATTEMPTS = 4
_BASE_DELAY = 2.0


def with_retries(call: Callable[[], str], *, provider: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return call()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in _RETRIABLE and attempt < _MAX_ATTEMPTS:
                _maybe_log("llm_retry", provider=provider, status=status, attempt=attempt, error=None)
                time.sleep(_BASE_DELAY * (2 ** (attempt - 1)))
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
                    f"{provider}: rate limit/quota exhausted (429) after "
                    f"{_MAX_ATTEMPTS} attempts — back off or switch providers"
                ) from exc
            raise LLMError(f"{provider}: HTTP {status} from provider") from exc
        except httpx.HTTPError as exc:
            if attempt < _MAX_ATTEMPTS:
                _maybe_log("llm_retry", provider=provider, status=None, attempt=attempt, error=type(exc).__name__)
                time.sleep(_BASE_DELAY * (2 ** (attempt - 1)))
                last_error = exc
                continue
            raise LLMError(f"{provider}: retries exhausted") from last_error
    raise LLMError(f"{provider}: retries exhausted") from last_error


def with_rate_limit_retries(call: Callable[[], str], provider: str = "nvidia") -> str:
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return call()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in _RETRIABLE and attempt < _MAX_ATTEMPTS:
                _maybe_log(
                    "llm_rate_limit_retry",
                    provider=provider,
                    status=status,
                    attempt=attempt,
                    error=None,
                )
                time.sleep(_BASE_DELAY * (2 ** (attempt - 1)))
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
                    f"{provider}: rate limit/quota exhausted (429) after "
                    f"{_MAX_ATTEMPTS} attempts — back off or switch providers"
                ) from exc
            raise LLMError(f"{provider}: HTTP {status} from provider") from exc
        except httpx.HTTPError as exc:
            if attempt < _MAX_ATTEMPTS:
                _maybe_log(
                    "llm_rate_limit_retry",
                    provider=provider,
                    status=None,
                    attempt=attempt,
                    error=type(exc).__name__,
                )
                time.sleep(_BASE_DELAY * (2 ** (attempt - 1)))
                last_error = exc
                continue
            raise LLMError(f"{provider}: retries exhausted") from last_error
    raise LLMError(f"{provider}: retries exhausted") from last_error


def _maybe_log(*args, **kwargs):
    try:
        from src.observability.events import get_logger

        log = get_logger("llm")
        log.warning(*args, **kwargs)
    except Exception:
        pass
