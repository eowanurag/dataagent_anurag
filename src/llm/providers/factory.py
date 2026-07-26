"""Provider factory — resolves provider + model from settings.

``auto`` picks whichever key is set. With no key at all we raise a clear,
actionable error: the real provider is the default and the only gated path — 
there is no silent stub fallback (harness/rules/ai-agents.md rule 7).
"""
from __future__ import annotations

from src.config.settings import _normalize_model_name
from src.config.settings import get_settings
from src.llm.providers.anthropic import AnthropicProvider
from src.llm.providers.base import LLMError, LLMProvider
from src.llm.providers.gemini import GeminiProvider
from src.llm.providers.nvidia import NvidiaProvider
from src.llm.providers.openrouter import OpenRouterProvider


def create_llm_provider() -> LLMProvider:
    from src.services.settings_store import load_user_settings
    saved = load_user_settings()
    saved_provider = (saved.get("provider") or "").strip().lower()
    saved_model = (saved.get("model") or "").strip()

    s = get_settings()
    provider = saved_provider or s.resolve_provider()
    model = saved_model or s.resolve_model()
    model = _normalize_model_name(provider, model)

    if provider == "anthropic":
        return AnthropicProvider(api_key=s.anthropic_api_key, model=model)
    if provider == "gemini":
        return GeminiProvider(api_key=s.gemini_api_key, model=model)
    if provider == "openrouter":
        return OpenRouterProvider(
            api_key=s.openrouter_api_key, model=model, base_url=s.openrouter_base_url
        )
    if provider == "nvidia":
        return NvidiaProvider(
            api_key=s.nvidia_api_key, model=model, base_url=s.nvidia_base_url
        )
    raise LLMError(
        "No LLM API key configured. Set exactly one of AGENT_ANTHROPIC_API_KEY, "
        "AGENT_GEMINI_API_KEY, AGENT_OPENROUTER_API_KEY, or AGENT_NVIDIA_API_KEY "
        "in .env (see .env.example)."
    )
