"""Audit service — append-only event log for investigations, runs, exports."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text as sql_text

from src.db.session import create_db_session
from src.observability.events import get_logger


def record_audit(
    *,
    investigation_id: str | None,
    actor_user_id: str,
    actor_rank: str | None = None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    source: str | None = None,
    sql: str | None = None,
    row_count: int | None = None,
    latency_ms: int | None = None,
    error_message: str | None = None,
    metadata: dict | None = None,
    run_id: str | None = None,
) -> None:
    log = get_logger("audit")
    try:
        now = datetime.now(timezone.utc)
        with create_db_session() as session:
            session.execute(
                sql_text(
                    """
                INSERT INTO audit_events (
                    investigation_id, run_id, actor_user_id, actor_unit, actor_rank,
                    action, resource_type, resource_id, source, sql, row_count,
                    latency_ms, error_message, metadata, created_at
                ) VALUES (
                    :investigation_id, :run_id, :actor_user_id, :actor_unit, :actor_rank,
                    :action, :resource_type, :resource_id, :source, :sql, :row_count,
                    :latency_ms, :error_message, :metadata, :created_at
                )
                """
                ),
                {
                    "investigation_id": investigation_id,
                    "run_id": run_id,
                    "actor_user_id": actor_user_id,
                    "actor_unit": None,
                    "actor_rank": actor_rank,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "source": source,
                    "sql": sql,
                    "row_count": row_count,
                    "latency_ms": latency_ms,
                    "error_message": error_message,
                    "metadata": None if metadata is None else str(metadata),
                    "created_at": now,
                },
            )
            session.commit()
        log.info(
            "audit_recorded",
            action=action,
            investigation_id=investigation_id,
            actor_user_id=actor_user_id,
            source=source,
            row_count=row_count,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("audit_failed", action=action, error=str(exc))
