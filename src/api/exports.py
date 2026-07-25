"""Export API — CSV and PDF downloads for investigations."""
from __future__ import annotations

import base64
import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from src.api._common import api_error
from src.db.session import create_db_session, get_session
from src.observability.events import get_logger
from src.services.audit import record_audit

router = APIRouter()
log = get_logger("exports")


class PdfExportPayload(BaseModel):
    chart_images: list[str] = []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _actor() -> dict[str, Any]:
    return {"user_id": "demo-user", "rank": None, "unit": None}


def _load_history(investigation_id: str) -> list[dict[str, Any]]:
    with create_db_session() as session:
        rows = session.execute(
            sql_text("SELECT * FROM chat_messages WHERE investigation_id = :iid ORDER BY created_at"),
            {"iid": investigation_id},
        ).fetchall()
    return [
        {
            "message_id": r.message_id,
            "role": r.role,
            "content": r.content,
            "citations": json.loads(r.citations) if r.citations else [],
            "created_at": r.created_at,
        }
        for r in rows
    ]


def _load_files(investigation_id: str) -> list[dict[str, Any]]:
    with create_db_session() as session:
        rows = session.execute(
            sql_text("SELECT * FROM investigation_files WHERE investigation_id = :iid ORDER BY created_at"),
            {"iid": investigation_id},
        ).fetchall()
    return [
        {
            "file_id": r.file_id,
            "filename": r.filename,
            "original_filename": r.original_filename,
            "row_count": r.row_count,
            "columns_json": r.columns_json,
        }
        for r in rows
    ]


@router.get("/investigations/{investigation_id}/export/csv")
def export_investigation_csv(investigation_id: str, session: Session = Depends(get_session)) -> Response:
    _actor()
    history = _load_history(investigation_id)
    files = _load_files(investigation_id)
    if not history and not files:
        raise api_error("not_found", "no history or files to export", 404)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["section", "idx", "timestamp", "role", "content", "citations", "source_file", "columns", "row_count"])
    idx = 1
    for row in files:
        cols = ""
        try:
            cols = json.dumps(json.loads(row["columns_json"] or "[]"))
        except Exception:
            cols = row.get("columns_json") or ""
        writer.writerow([
            "file",
            idx,
            "",
            "",
            row.get("filename") or "",
            row.get("original_filename") or "",
            row.get("file_id") or "",
            cols,
            row.get("row_count"),
        ])
        idx += 1
    for row in history:
        writer.writerow([
            "message",
            idx,
            row.get("created_at") or "",
            row.get("role") or "",
            (row.get("content") or "").replace("\n", " "),
            "|".join(row.get("citations") or []),
            "",
            "",
            "",
        ])
        idx += 1

    record_audit(
        investigation_id=investigation_id,
        actor_user_id=_actor()["user_id"],
        action="export",
        resource_type="investigation",
        resource_id=investigation_id,
        payload={"format": "csv"},
    )

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={investigation_id}-export.csv"},
    )


@router.post("/investigations/{investigation_id}/export/pdf")
def export_investigation_pdf(
    investigation_id: str,
    payload: PdfExportPayload | None = None,
    session: Session = Depends(get_session),
) -> Response:
    _actor()
    rows = _load_history(investigation_id)
    if not rows:
        raise api_error("not_found", "no history to export", 404)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=48, leftMargin=48, topMargin=48, bottomMargin=48)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(f"Investigation {investigation_id}", styles["Title"]))
    story.append(Paragraph(f"Exported: {_now_iso()}", styles["Normal"]))
    story.append(Spacer(1, 10))

    chart_images = [item for item in (payload.chart_images if payload else []) if isinstance(item, str) and item.strip()]
    for idx, row in enumerate(rows, start=1):
        story.append(Paragraph(f"{idx}. {row['role']}", styles["Heading3"]))
        story.append(Paragraph((row["content"] or "").replace("\n", "<br/>"), styles["BodyText"]))
        citations = row.get("citations") or []
        if citations:
            story.append(Paragraph("<b>Citations:</b> " + "; ".join(citations), styles["Normal"]))
        if chart_images and row.get("role") == "assistant":
            image_index = min(idx - 1, len(chart_images) - 1)
            img_data = base64.b64decode(chart_images[image_index])
            img_buf = io.BytesIO(img_data)
            try:
                story.append(Spacer(1, 6))
                story.append(Image(img_buf, width=460, height=260, kind="proportional"))
            except Exception as exc:  # noqa: BLE001
                log.warning("pdf_image_embed_failed", error=str(exc))
        story.append(Spacer(1, 10))

    doc.build(story)
    pdf = buf.getvalue()

    record_audit(
        investigation_id=investigation_id,
        actor_user_id=_actor()["user_id"],
        action="export",
        resource_type="investigation",
        resource_id=investigation_id,
        payload={"format": "pdf"},
    )

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={investigation_id}-history.pdf"},
    )
