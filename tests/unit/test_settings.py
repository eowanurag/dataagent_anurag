import pytest

from src.config.settings import get_settings, reset_settings


def test_no_key_resolves_to_stub(no_keys):
    reset_settings()
    s = get_settings()
    assert s.resolve_provider() == "stub"
    assert s.resolve_model() == ""


def test_auto_detects_anthropic(no_keys, monkeypatch):
    reset_settings()
    monkeypatch.setenv("AGENT_ANTHROPIC_API_KEY", "test-key-not-real")
    s = get_settings()
    assert s.resolve_provider() == "anthropic"
    assert s.resolve_model() == "claude-sonnet-4-6"


def test_auto_detects_openrouter(no_keys, monkeypatch):
    reset_settings()
    monkeypatch.setenv("AGENT_OPENROUTER_API_KEY", "test-key-not-real")
    s = get_settings()
    assert s.resolve_provider() == "openrouter"
    assert s.resolve_model()


def test_auto_detects_nvidia(no_keys, monkeypatch):
    reset_settings()
    monkeypatch.setenv("AGENT_NVIDIA_API_KEY", "test-key-not-real")
    s = get_settings()
    assert s.resolve_provider() == "nvidia"
    assert s.resolve_model() == "meta/llama-3.1-70b-instruct"


def test_nvidia_model_alias_round_trip(no_keys, monkeypatch):
    reset_settings()
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("AGENT_LLM_MODEL", "meta/llama-3.1-nemotron-70b-instruct")
    s = get_settings()
    assert s.resolve_model() == "nvidia/llama-3.1-nemotron-70b-instruct"


def test_explicit_provider_and_model_win(no_keys, monkeypatch):
    reset_settings()
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("AGENT_LLM_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("AGENT_GEMINI_API_KEY", "test-key-not-real")
    s = get_settings()
    assert s.resolve_provider() == "gemini"
    assert s.resolve_model() == "gemini-2.5-flash"


def test_database_url_isolated_by_fixture(tmp_path):
    assert get_settings().database_url.startswith("sqlite:///")
    assert "test.db" in get_settings().database_url


def test_nvidia_provider_direct():
    from src.llm.providers.nvidia import NvidiaProvider

    provider = NvidiaProvider(
        api_key="fake", model="nvidia/llama-3.1-nemotron-70b-instruct"
    )
    assert provider.name == "nvidia"
    assert provider.model == "nvidia/llama-3.1-nemotron-70b-instruct"
    assert provider._base_url == "https://integrate.api.nvidia.com/v1"


def test_factory_returns_nvidia_provider(no_keys, monkeypatch):
    reset_settings()
    monkeypatch.setenv("AGENT_NVIDIA_API_KEY", "test-key-not-real")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("AGENT_LLM_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct")
    from src.llm.providers.factory import create_llm_provider

    provider = create_llm_provider()
    assert provider.name == "nvidia"
    assert provider.model == "nvidia/llama-3.1-nemotron-70b-instruct"


def test_nvidia_rate_limit_and_limiter_wired():
    from src.llm.limiter import nvidia_limited
    from src.llm.providers.nvidia import NvidiaProvider
    from src.llm.retry import with_rate_limit_retries

    provider = NvidiaProvider(
        api_key="fake", model="nvidia/llama-3.1-nemotron-70b-instruct"
    )
    assert provider._base_url == "https://integrate.api.nvidia.com/v1"
    assert with_rate_limit_retries is not None

    assert callable(nvidia_limited)
    assert getattr(provider, "model", None) is not None
