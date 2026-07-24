"""Application settings — Pydantic BaseSettings, env prefix ``AGENT_``.

The provider key is loaded from ``.env`` (the single manual user step). Presence
is checked by ``bool`` only — the value is never echoed, logged, or committed.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Provider defaults used when AGENT_LLM_MODEL is blank. Verify against current
# provider docs before pinning — a 404 from the LLM API usually means a stale name.
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini-2.5-flash",
    "openrouter": "meta-llama/llama-3.1-70b-instruct",
    "nvidia": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./data/app.db")
    llm_provider: str = Field(default="auto")
    llm_model: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")
    openrouter_api_key: str = Field(default="")
    nvidia_api_key: str = Field(default="")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1")
    log_level: str = Field(default="INFO")
    storage_root: str = Field(default=".")
    max_query_rows: int = Field(default=5000)

    def resolve_provider(self) -> str:
        """The effective provider name, or ``"stub"`` when no key is present."""
        p = (self.llm_provider or "auto").strip().lower()
        if p != "auto":
            return p
        if self.anthropic_api_key:
            return "anthropic"
        if self.gemini_api_key:
            return "gemini"
        if self.openrouter_api_key:
            return "openrouter"
        if self.nvidia_api_key:
            return "nvidia"
        return "stub"

    def resolve_model(self) -> str:
        if self.llm_model:
            return _normalize_model_name(self.resolve_provider(), self.llm_model)
        return DEFAULT_MODELS.get(self.resolve_provider(), "")

    def key_for(self, provider: str) -> str:
        return {
            "anthropic": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
            "openrouter": self.openrouter_api_key,
            "nvidia": self.nvidia_api_key,
        }.get(provider, "")


PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "gemini": "gemini",
    "nvidia": "nvidia",
    "openrouter": "openrouter",
}

MODEL_ALIASES = {
    "anthropic": {},
    "gemini": {},
    "openrouter": {
        "meta/llama-3.1-70b-instruct": "meta-llama/llama-3.1-70b-instruct",
    },
    "nvidia": {
        "meta/llama-3.1-nemotron-70b-instruct": "nvidia/llama-3.1-nemotron-70b-instruct",
        "llama-3.1-nemotron-70b-instruct": "nvidia/llama-3.1-nemotron-70b-instruct",
        "meta/llama-3.1-70b-instruct": "nvidia/llama-3.1-70b-instruct",
        "llama-3.1-70b-instruct": "nvidia/llama-3.1-70b-instruct",
    },
}


def provider_name_for(provider: str | None) -> str:
    if not provider:
        return ""
    key = (provider or "").strip().lower()
    return PROVIDER_ALIASES.get(key, key)


def _normalize_model_name(provider: str | None, model: str) -> str:
    p = provider_name_for(provider)
    aliases = MODEL_ALIASES.get(p, {})
    if model in aliases:
        return aliases[model]
    return model


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
