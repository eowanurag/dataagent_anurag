"""Investigations API — create investigations, upload files, run questions, history."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from src.api._common import api_error, ok
from src.config.settings import get_settings
from src.db.models import RunRow
from src.db.session import create_db_session, get_session
from src.observability.events import get_logger, log_span
from src.services.audit import record_audit
from src.services.storage import write_attachment
from src.tools.csv_tool import inspect_schema, query_sql

router = APIRouter()
log = get_logger("investigations")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _actor() -> dict[str, Any]:
    return {"user_id": "demo-user", "rank": None, "unit": None}


def _init_schema() -> None:
    from src.db.session import create_db_session

    statements = [
        """CREATE TABLE IF NOT EXISTS investigations (
            investigation_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            tags TEXT,
            live_source_enabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS investigation_files (
            file_id TEXT PRIMARY KEY,
            investigation_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            content_type TEXT,
            size_bytes INTEGER,
            row_count INTEGER,
            columns_json TEXT,
            created_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS chat_messages (
            message_id TEXT PRIMARY KEY,
            investigation_id TEXT NOT NULL,
            run_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            citations TEXT,
            created_at TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_inv_files_investigation_id ON investigation_files(investigation_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_investigation_id ON chat_messages(investigation_id)",
        """CREATE TABLE IF NOT EXISTS audit_events (
            audit_id TEXT PRIMARY KEY,
            investigation_id TEXT,
            run_id TEXT,
            actor_user_id TEXT NOT NULL,
            actor_unit TEXT,
            actor_rank TEXT,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            source TEXT,
            sql TEXT,
            row_count INTEGER,
            latency_ms INTEGER,
            error_message TEXT,
            payload TEXT,
            created_at TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_audit_investigation_id ON audit_events(investigation_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_run_id ON audit_events(run_id)",
        """CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            input_text TEXT NOT NULL,
            instruction TEXT NOT NULL,
            output_text TEXT,
            provider TEXT,
            model TEXT,
            error_message TEXT,
            created_at TEXT,
            updated_at TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)",
    ]
    with create_db_session() as session:
        for stmt in statements:
            session.execute(sql_text(stmt))
        session.commit()


@router.post("/investigations")
def create_investigation(payload: dict[str, Any], session: Session = Depends(get_session)) -> dict:
    _init_schema()
    actor = _actor()
    investigation_id = f"inv-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    now = _now_iso()
    session.execute(
        sql_text(
            "INSERT INTO investigations (investigation_id, owner_user_id, title, description, tags, live_source_enabled, created_at, updated_at) "
            "VALUES (:id, :owner, :title, :desc, :tags, 0, :now, :now)"
        ),
        {
            "id": investigation_id,
            "owner": actor["user_id"],
            "title": payload.get("title") or "Untitled",
            "desc": payload.get("description"),
            "tags": json.dumps(payload.get("tags") or []),
            "now": now,
        },
    )
    session.commit()
    record_audit(
        investigation_id=investigation_id,
        actor_user_id=actor["user_id"],
        actor_rank=actor["rank"],
        action="investigation_created",
        resource_type="investigation",
        resource_id=investigation_id,
    )
    return ok({
        "investigation_id": investigation_id,
        "owner_user_id": actor["user_id"],
        "title": payload.get("title") or "Untitled",
        "description": payload.get("description"),
        "tags": payload.get("tags") or [],
        "live_source_enabled": False,
        "created_at": now,
        "updated_at": now,
    })


@router.get("/investigations/{investigation_id}")
def get_investigation(investigation_id: str, session: Session = Depends(get_session)) -> dict:
    _init_schema()
    row = session.execute(
        sql_text("SELECT * FROM investigations WHERE investigation_id = :id"), {"id": investigation_id}
    ).fetchone()
    if row is None:
        raise api_error("not_found", "investigation not found", 404)
    return ok(_row_to(row))


@router.patch("/investigations/{investigation_id}")
def update_investigation(investigation_id: str, payload: dict[str, Any], session: Session = Depends(get_session)) -> dict:
    _init_schema()
    row = session.execute(
        sql_text("SELECT * FROM investigations WHERE investigation_id = :id"), {"id": investigation_id}
    ).fetchone()
    if row is None:
        raise api_error("not_found", "investigation not found", 404)
    title = payload.get("title", row.title)
    description = payload.get("description", row.description)
    tags = json.dumps(payload.get("tags", json.loads(row.tags or "[]")))
    now = _now_iso()
    session.execute(
        sql_text("UPDATE investigations SET title=:title, description=:desc, tags=:tags, updated_at=:now WHERE investigation_id=:id"),
        {"title": title, "desc": description, "tags": tags, "now": now, "id": investigation_id},
    )
    session.commit()
    return ok({
        "investigation_id": investigation_id,
        "owner_user_id": row.owner_user_id,
        "title": title,
        "description": description,
        "tags": json.loads(tags),
        "live_source_enabled": bool(row.live_source_enabled),
        "created_at": row.created_at,
        "updated_at": now,
    })


@router.get("/investigations/{investigation_id}/files")
def get_files(investigation_id: str, session: Session = Depends(get_session)) -> dict:
    _init_schema()
    inv = session.execute(
        sql_text("SELECT * FROM investigations WHERE investigation_id = :id"), {"id": investigation_id}
    ).fetchone()
    if inv is None:
        raise api_error("not_found", "investigation not found", 404)
    rows = session.execute(
        sql_text("SELECT * FROM investigation_files WHERE investigation_id = :iid ORDER BY created_at"),
        {"iid": investigation_id},
    ).fetchall()
    items = []
    for r in rows:
        items.append(
            {
                "file_id": r.file_id,
                "investigation_id": r.investigation_id,
                "filename": r.filename,
                "original_filename": r.original_filename,
                "content_type": r.content_type,
                "size_bytes": r.size_bytes,
                "row_count": r.row_count,
                "columns": json.loads(r.columns_json) if r.columns_json else [],
                "created_at": r.created_at,
            }
        )
    return ok({"items": items})

@router.post("/investigations/{investigation_id}/files")
def upload_file(investigation_id: str, file: UploadFile = File(...), session: Session = Depends(get_session)) -> dict:
    _init_schema()
    actor = _actor()
    inv = session.execute(
        sql_text("SELECT * FROM investigations WHERE investigation_id = :id"), {"id": investigation_id}
    ).fetchone()
    if inv is None:
        raise api_error("not_found", "investigation not found", 404)

    payload = file.file.read()
    file_rec_id = f"f-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    stored = write_attachment(file_rec_id, payload)

    df = pd.read_csv(stored, nrows=1000)
    row_count = int(pd.read_csv(stored).shape[0])
    columns = list(df.columns)

    session.execute(
        sql_text(
            "INSERT INTO investigation_files (file_id, investigation_id, filename, original_filename, content_type, size_bytes, row_count, columns_json, created_at) "
            "VALUES (:fid, :iid, :filename, :orig, :ct, :size, :rows, :cols, :now)"
        ),
        {
            "fid": file_rec_id,
            "iid": investigation_id,
            "filename": stored.name,
            "orig": file.filename or "upload.csv",
            "ct": file.content_type,
            "size": len(payload),
            "rows": row_count,
            "cols": json.dumps(columns),
            "now": _now_iso(),
        },
    )
    session.commit()

    record_audit(
        investigation_id=investigation_id,
        actor_user_id=actor["user_id"],
        actor_rank=actor["rank"],
        action="file_uploaded",
        resource_type="file",
        resource_id=file_rec_id,
        source="csv",
    )
    return ok({
        "file_id": file_rec_id,
        "investigation_id": investigation_id,
        "filename": stored.name,
        "original_filename": file.filename or "upload.csv",
        "content_type": file.content_type,
        "size_bytes": len(payload),
        "row_count": row_count,
        "columns": columns,
        "created_at": _now_iso(),
    })


@router.post("/investigations/{investigation_id}/runs")
def create_run(investigation_id: str, payload: dict[str, Any], session: Session = Depends(get_session)) -> dict:
    _init_schema()
    actor = _actor()
    inv = session.execute(
        sql_text("SELECT * FROM investigations WHERE investigation_id = :id"), {"id": investigation_id}
    ).fetchone()
    if inv is None:
        raise api_error("not_found", "investigation not found", 404)

    question = (payload.get("question") or "").strip()
    if not question:
        raise api_error("invalid_input", "question is required", 400)

    files = session.execute(
        sql_text("SELECT * FROM investigation_files WHERE investigation_id = :iid ORDER BY created_at"),
        {"iid": investigation_id},
    ).fetchall()
    if not files:
        msg_id = f"msg-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        now = _now_iso()
        session.execute(
            sql_text("INSERT INTO chat_messages (message_id, investigation_id, run_id, role, content, citations, created_at) VALUES (:mid, :iid, :rid, 'assistant', :content, :cites, :now)"),
            {"mid": msg_id, "iid": investigation_id, "rid": None, "content": "No files are attached to this investigation yet. Upload CSV data before asking questions.", "cites": json.dumps([]), "now": now},
        )
        session.commit()
        record_audit(
            investigation_id=investigation_id,
            actor_user_id=actor["user_id"],
            actor_rank=actor["rank"],
            action="run_failed",
            resource_type="run",
            resource_id=msg_id,
            source="csv",
            error_message="no files attached",
        )
        return ok({
            "run_id": msg_id,
            "investigation_id": investigation_id,
            "status": "failed",
            "question": question,
            "source": "csv",
            "answer_text": None,
            "chart_spec": None,
            "citations": [],
            "sql": None,
            "sql_row_count": None,
            "followup_suggestions": None,
            "error_message": "No files are attached to this investigation yet. Upload CSV data before asking questions.",
            "provider": get_settings().resolve_provider(),
            "model": get_settings().resolve_model(),
            "created_at": now,
            "latency_ms": None,
        })

    file_row = files[0]
    file_id = file_row.file_id
    user_msg_id = f"msg-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    now = _now_iso()
    session.execute(
        sql_text("INSERT INTO chat_messages (message_id, investigation_id, run_id, role, content, citations, created_at) VALUES (:mid, :iid, :rid, 'user', :content, :cites, :now)"),
        {"mid": user_msg_id, "iid": investigation_id, "rid": None, "content": question, "cites": json.dumps([]), "now": now},
    )
    session.commit()

    sql_text_str = None
    sql_rows_df = None
    sql_row_count = None
    answer_text = None
    chart_spec = None
    citations_list = []
    followup_suggestions = None
    status = "completed"

    run_row = RunRow(
        id=user_msg_id,
        status="running",
        input_text=question,
        instruction="investigation",
        provider=get_settings().resolve_provider(),
        model=get_settings().resolve_model(),
    )
    session.add(run_row)
    session.commit()
    t0 = __import__("time").perf_counter()
    try:
        from src.graph.runner import run_investigation_graph

        result = run_investigation_graph(
            investigation_id=investigation_id,
            run_id=user_msg_id,
            user_id=actor["user_id"],
            question=question,
            source="csv",
        )
        status = result.get("status") or "completed"
        run_row.status = status
        run_row.output_text = result.get("answer_text")
        run_row.error_message = result.get("error")
        run_row.updated_at = datetime.now(timezone.utc)
        session.commit()
    except Exception as exc:  # noqa: BLE001
        log.error("run_failed", error=str(exc))
        status = "failed"
        run_error = str(exc)
        run_row.status = "failed"
        run_row.error_message = str(exc)
        run_row.updated_at = datetime.now(timezone.utc)
        session.commit()
    latency_ms = int((__import__("time").perf_counter() - t0) * 1000)

    assistant_msg_id = f"msg-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    now = _now_iso()
    session.execute(
        sql_text("INSERT INTO chat_messages (message_id, investigation_id, run_id, role, content, citations, created_at) VALUES (:mid, :iid, :rid, 'assistant', :content, :cites, :now)"),
        {"mid": assistant_msg_id, "iid": investigation_id, "rid": user_msg_id, "content": answer_text or "", "cites": json.dumps(citations_list), "now": now},
    )
    session.commit()

    record_audit(
        investigation_id=investigation_id,
        run_id=user_msg_id,
        actor_user_id=actor["user_id"],
        actor_rank=actor["rank"],
        action="run_created",
        resource_type="run",
        resource_id=user_msg_id,
        source="csv",
        sql=sql_text_str,
        row_count=sql_row_count,
        latency_ms=latency_ms,
        error_message=answer_text if status == "failed" else None,
        payload={"question": question},
    )

    return ok({
        "run_id": user_msg_id,
        "investigation_id": investigation_id,
        "status": status,
        "question": question,
        "source": "csv",
        "answer_text": answer_text,
        "chart_spec": chart_spec,
        "citations": citations_list,
        "sql": sql_text_str,
        "sql_row_count": sql_row_count,
        "followup_suggestions": followup_suggestions,
        "error_message": answer_text if status == "failed" else None,
        "provider": get_settings().resolve_provider(),
        "model": get_settings().resolve_model(),
        "created_at": now,
        "latency_ms": latency_ms,
    })


@router.get("/investigations/{investigation_id}/history")
def get_history(investigation_id: str, session: Session = Depends(get_session)) -> dict:
    _init_schema()
    inv = session.execute(
        sql_text("SELECT * FROM investigations WHERE investigation_id = :id"), {"id": investigation_id}
    ).fetchone()
    if inv is None:
        raise api_error("not_found", "investigation not found", 404)
    rows = session.execute(
        sql_text("SELECT * FROM chat_messages WHERE investigation_id = :iid ORDER BY created_at"),
        {"iid": investigation_id},
    ).fetchall()
    return ok({
        "investigation_id": investigation_id,
        "items": [
            {
                "message_id": r.message_id,
                "role": r.role,
                "content": r.content,
                "citations": json.loads(r.citations) if r.citations else [],
                "created_at": r.created_at,
            }
            for r in rows
        ],
    })


def _row_to(row) -> dict[str, Any]:
    keys = row._fields if hasattr(row, "_fields") else row.keys()
    return {k: getattr(row, k, None) for k in keys}
