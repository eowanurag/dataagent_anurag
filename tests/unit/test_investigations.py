from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from src.api import create_app
from src.config.settings import get_settings


def _client() -> TestClient:
    return TestClient(create_app())


def test_storage_root_defaults_to_dot(monkeypatch):
    monkeypatch.delenv("AGENT_STORAGE_ROOT", raising=False)
    assert get_settings().storage_root == "."


def test_upload_csv_creates_investigation_and_file(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    storage.mkdir()
    monkeypatch.setenv("AGENT_STORAGE_ROOT", str(storage))

    payload = (
        "district,count,quarter\n"
        "A,10,Q1\n"
        "B,25,Q1\n"
        "A,17,Q2\n"
        "C,8,Q2\n"
    )
    with _client() as client:
        res = client.post(
            "/investigations",
            json={"title": "Q1 Q2 compare", "description": "Test"},
        )
        assert res.status_code == 200, res.text
        investigation_id = res.json()["data"]["investigation_id"]

        res = client.post(
            f"/investigations/{investigation_id}/files",
            files={"file": ("sample.csv", payload, "text/csv")},
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["row_count"] == 4
        assert set(data["columns"]) == {"district", "count", "quarter"}
        stored = storage / data["file_id"]
        assert stored.exists()


def test_ask_question_over_csv_returns_cited_answer(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    storage.mkdir()
    monkeypatch.setenv("AGENT_STORAGE_ROOT", str(storage))

    payload = "district,count\nA,10\nB,25\nC,8\n"

    with _client() as client:
        res = client.post("/investigations", json={"title": "District counts"})
        investigation_id = res.json()["data"]["investigation_id"]

        res = client.post(
            f"/investigations/{investigation_id}/files",
            files={"file": ("sample.csv", payload, "text/csv")},
        )
        assert res.status_code == 200, res.text

        res = client.post(
            f"/investigations/{investigation_id}/runs",
            json={"question": "Which district has the highest count?"},
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["status"] == "completed"
        assert data["source"] == "csv"
        assert "B" in (data["answer_text"] or "")
        assert len(data["citations"]) >= 1
        assert len(data["sql"]) > 0


def test_ask_question_without_files_returns_actionable_error(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    storage.mkdir()
    monkeypatch.setenv("AGENT_STORAGE_ROOT", str(storage))

    with _client() as client:
        res = client.post("/investigations", json={"title": "Empty"})
        investigation_id = res.json()["data"]["investigation_id"]

        res = client.post(
            f"/investigations/{investigation_id}/runs",
            json={"question": "anything"},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["status"] == "failed"
        assert data["error_message"]


def test_history_returns_messages(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    storage.mkdir()
    monkeypatch.setenv("AGENT_STORAGE_ROOT", str(storage))

    with _client() as client:
        res = client.post("/investigations", json={"title": "History test"})
        investigation_id = res.json()["data"]["investigation_id"]
        client.post(
            f"/investigations/{investigation_id}/files",
            files={"file": ("sample.csv", "a,1\nb,2\n", "text/csv")},
        )
        client.post(
            f"/investigations/{investigation_id}/runs",
            json={"question": "sum"},
        )

        res = client.get(f"/investigations/{investigation_id}/history")
        assert res.status_code == 200
        messages = res.json()["data"]["items"]
        assert len(messages) >= 2  # user question + assistant answer


def test_unknown_investigation_is_404():
    with _client() as client:
        assert client.get("/investigations/nope").status_code == 404
        assert client.get("/investigations/nope/history").status_code == 404
        assert client.post("/investigations/nope/runs", json={"question": "x"}).status_code == 404
