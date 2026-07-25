"""Abstract LLM provider.

Optional extension point for token/cost accounting:
- `complete_usage(...)` returns `(text, input_tokens, output_tokens)`
- `cost_hint(...)` returns per-token pricing metadata, if known.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    """A provider call failed after retries; message is safe to surface."""


class Usage:
    def __init__(self, input_tokens: int | None = None, output_tokens: int | None = None):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        raise NotImplementedError

    def complete_usage(self, system: str, user: str, *, max_tokens: int = 1024) -> tuple[str, Usage]:
        text = self.complete(system, user, max_tokens=max_tokens)
        return text, Usage()

    def cost_hint(self) -> dict | None:
        return None
