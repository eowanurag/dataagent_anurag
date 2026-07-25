import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.llm.registry import canonicalize, list_variants


def test_models_endpoint_returns_count_and_selected():
    client = TestClient(create_app())
    with client:
        res = client.get("/models")
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["count"] >= 1
    assert isinstance(payload["models"], list)
    assert "selected" in payload
    assert payload["selected"]["id"] == payload["models"][0]["id"]


def test_list_variants_has_expected_candidates():
    variants = list_variants()
    assert any(v["provider"] == "openrouter" for v in variants)
    assert any(v["id"] == "meta-llama/llama-3.1-70b-instruct" for v in variants)


def test_canonicalize_is_identity_when_no_alias():
    assert canonicalize("meta/llama-3.1-70b-instruct") == "meta/llama-3.1-70b-instruct"
    assert canonicalize("") == ""
