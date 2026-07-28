from fastapi.testclient import TestClient
from sqlalchemy import text as sql_text

from src.api import app
from src.db.session import create_db_session


client = TestClient(app)


def test_pdf_export_returns_pdf_when_history_exists():
    res = client.get("/health")
    assert res.status_code == 200

    res = client.post("/investigations", json={"title": "pdf-export", "question": "x"})
    assert res.status_code == 200
    inv = res.json()["data"]["investigation_id"]

    with create_db_session() as session:
        session.execute(
            sql_text(
                "INSERT INTO chat_messages (investigation_id, role, content, citations, created_at) "
                "VALUES (:iid, 'user', 'u', '[]', datetime('now'))"
            ),
            {"iid": inv},
        )
        session.execute(
            sql_text(
                "INSERT INTO chat_messages (investigation_id, role, content, citations, created_at) "
                "VALUES (:iid, 'assistant', 'a', '[]', datetime('now'))"
            ),
            {"iid": inv},
        )
        session.commit()

    res = client.post(f"/investigations/{inv}/export/pdf", json={"chart_images": []})
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")


_MINI_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_pdf_export_accepts_frontend_data_url_chart_images():
    res = client.post("/investigations", json={"title": "pdf-export-dataurl", "question": "x"})
    assert res.status_code == 200
    inv = res.json()["data"]["investigation_id"]

    with create_db_session() as session:
        session.execute(
            sql_text(
                "INSERT INTO chat_messages (investigation_id, role, content, citations, created_at) "
                "VALUES (:iid, 'assistant', 'answer', '[]', datetime('now'))"
            ),
            {"iid": inv},
        )
        session.commit()

    res = client.post(
        f"/investigations/{inv}/export/pdf",
        json={"chart_images": [f"data:image/png;base64,{_MINI_PNG_BASE64}"]},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
