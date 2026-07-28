"""Rate limiting utilities for LLM provider calls."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RateLimiter:
    """A simple semaphore-based rate limiter.

    Not a precise token-bucket RPM counter; instead it bounds how many calls
    may be in flight at once, which stabilizes free-tier providers under
    concurrent load without adding a hard dependency on a full Redis/DB
    quota budget.
    """

    max_concurrency: int = 1
    name: str = "default"

    def __post_init__(self) -> None:
        object.__setattr__(self, "_semaphore", threading.Semaphore(self.max_concurrency))

    def run(self, func: Callable[[], T], *, timeout: float | None = None) -> T:
        semaphore = object.__getattribute__(self, "_semaphore")
        acquired = semaphore.acquire(blocking=True, timeout=timeout)
        if not acquired:
            raise TimeoutError(f"{self.name} limiter timeout after {timeout}s")
        try:
            return func()
        finally:
            semaphore.release()


_NVIDIA_LIMITER = RateLimiter(max_concurrency=1, name="nvidia-40rps")


def nvidia_limited(func: Callable[[], T]) -> T:
    return _NVIDIA_LIMITER.run(func, timeout=120.0)
