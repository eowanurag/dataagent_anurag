"""LLMClient — the one wrapper graph nodes call.

Nodes never touch a provider directly; this keeps the capability slot
provider-agnostic and gives one place for logging, prompt loading, and
token/cost accounting.
"""
from __future__ import annotations

from pathlib import Path

from src.llm.providers.base import LLMProvider, Usage
from src.llm.providers.factory import create_llm_provider
from src.observability.events import get_logger, log_span

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt template from src/prompts/<name>.md."""
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


class LLMClient:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider or create_llm_provider()
        self._log = get_logger("llm")
        self.last_usage = Usage()

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def model(self) -> str:
        return self._provider.model

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        with log_span(
            self._log, "llm_complete",
            provider=self._provider.name, model=self._provider.model,
            input_chars=len(user),
        ) as span:
            text, usage = self._complete_with_usage(system, user, max_tokens=max_tokens)
            span["output_chars"] = len(text)
            span["input_tokens"] = usage.input_tokens
            span["output_tokens"] = usage.output_tokens
            self.last_usage = usage
            return text

    def _complete_with_usage(self, system: str, user: str, *, max_tokens: int = 1024) -> tuple[str, Usage]:
        if hasattr(self._provider, "complete_usage"):
            try:
                return self._provider.complete_usage(system, user, max_tokens=max_tokens)
            except Exception:
                pass
        text = self._provider.complete(system, user, max_tokens=max_tokens)
        return text, Usage()
