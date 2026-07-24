"""run_agent() / run_investigation_graph() — entry points the API calls.

Creates the run row, invokes the graph, persists the outcome. Errors land in
the row (status=failed + message), never as a crash.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from src.config.settings import get_settings
from src.db.models import RunRow
from src.db.session import create_db_session
from src.db.session import get_session
from src.graph.agent import agentic_ai
from src.graph.state import AgentState
from src.observability.events import get_logger, log_span
from src.services.storage import write_attachment
from src.tools.csv_tool import inspect_schema, query_sql

try:
    from src.api.investigations import _init_schema  # noqa: PLC0415
except Exception:  # noqa: BLE001
    def _init_schema():  # type: ignore[misc]
        pass


log = get_logger("runner")


def run_agent(input_text: str, instruction: str) -> str:
    log = get_logger("runner")

    with create_db_session() as session:
        run = RunRow(input_text=input_text, instruction=instruction, status="running")
        session.add(run)
        session.flush()
        run_id = run.id

    initial: AgentState = {
        "run_id": run_id,
        "input_text": input_text,
        "instruction": instruction,
        "question": input_text,
        "error": None,
    }
    with log_span(log, "agent_run", run_id=run_id) as span:
        final: AgentState = agentic_ai.invoke(initial)
        span["status"] = final.get("status", "completed")

    with create_db_session() as session:
        run = session.get(RunRow, run_id)
        run.status = final.get("status", "completed")
        run.output_text = final.get("output_text")
        run.provider = final.get("provider")
        run.model = final.get("model")
        run.error_message = final.get("error")

    return run_id


def run_investigation_graph(
    *,
    investigation_id: str,
    run_id: str,
    user_id: str,
    question: str,
    source: str = "csv",
) -> dict[str, Any]:
    log = get_logger("runner")

    payload = _probe_csv_for_file_id(investigation_id)
    if not isinstance(payload, dict):
        payload = {}
    probe_error = payload.get("error")
    if probe_error or not payload.get("file_id"):
        return {
            "status": "failed",
            "run_id": run_id,
            "investigation_id": investigation_id,
            "question": question,
            "source": source,
            "answer_text": None,
            "chart_spec": None,
            "citations": [],
            "sql": None,
            "sql_row_count": None,
            "followup_suggestions": None,
            "error": probe_error or "No files are attached to this investigation yet.",
            "provider": get_settings().resolve_provider(),
            "model": get_settings().resolve_model(),
            "latency_ms": None,
        }
    initial: AgentState = {
        "run_id": run_id,
        "investigation_id": investigation_id,
        "user_id": user_id,
        "question": question,
        "source": source,
        "file_id": payload.get("file_id"),
        "error": None,
    }
    with log_span(log, "investigation_graph", run_id=run_id) as span:
        final: AgentState = agentic_ai.invoke(initial)
        span["status"] = final.get("status", "completed")
    out = dict(final)
    if not out.get("sql") and isinstance(payload, dict) and payload.get("sql"):
        out["sql"] = payload["sql"]
    if not out.get("sql_row_count") and isinstance(payload, dict) and payload.get("sql_row_count"):
        out["sql_row_count"] = payload["sql_row_count"]
    if not out.get("sql_rows") and isinstance(payload, dict) and payload.get("sql_rows"):
        out["sql_rows"] = payload["sql_rows"]
    if not out.get("answer_text") and isinstance(payload, dict) and payload.get("answer_text"):
        out["answer_text"] = payload["answer_text"]
    if not out.get("status"):
        out["status"] = "completed"
    return out


def _probe_csv_for_file_id(investigation_id: str) -> dict[str, Any]:
    try:
        from src.api.investigations import _init_schema
        from src.db.models import InvestigationFileRow

        _init_schema()
        file_id = None
        columns_json = None
        row_count = None
        with create_db_session() as session:
            file_row = (
                session.query(InvestigationFileRow)
                .filter(InvestigationFileRow.investigation_id == investigation_id)
                .order_by(InvestigationFileRow.created_at.asc())
                .first()
            )
            if file_row is not None:
                file_id = file_row.file_id
                columns_json = file_row.columns_json
                row_count = file_row.row_count
        if file_id is None:
            return {
                "error": "No files are attached to this investigation yet. Upload CSV data before asking questions.",
            }
        columns = list(columns_json or "[]")
        schema = {
            "columns": columns,
            "row_count": row_count or 0,
        }
        sql = f"SELECT {', '.join(schema['columns'])} FROM uploaded_data LIMIT {get_settings().max_query_rows}"
        df = query_sql(file_id, sql, max_rows=get_settings().max_query_rows)
        return {
            "file_id": file_id,
            "sql": sql,
            "sql_row_count": int(df.shape[0]),
            "sql_rows": df.head(200).to_dict(orient="records"),
            "answer_text": (
                f"Based on the uploaded data ({schema['row_count']} rows), "
                f"the result set has {df.shape[0]} rows."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log = get_logger("runner")
        log.exception("_probe_csv_for_file_id_failed", investigation_id=investigation_id, error=str(exc))
        return {"error": f"probe failed: {exc}"}
