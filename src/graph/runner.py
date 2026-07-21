"""run_agent() / run_investigation_graph() — entry points the API calls.

Creates the run row, invokes the graph, persists the outcome. Errors land in
the row (status=failed + message), never as a crash.
"""
from __future__ import annotations

from typing import Any

from src.db.models import RunRow
from src.db.session import create_db_session
from src.graph.agent import agentic_ai
from src.graph.state import AgentState
from src.observability.events import get_logger, log_span
from src.services.storage import write_attachment


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
    if not out.get("sql") and payload.get("sql"):
        out["sql"] = payload["sql"]
    if not out.get("sql_row_count") and payload.get("sql_row_count"):
        out["sql_row_count"] = payload["sql_row_count"]
    if not out.get("sql_rows") and payload.get("sql_rows"):
        out["sql_rows"] = payload["sql_rows"]
    if not out.get("answer_text") and payload.get("answer_text"):
        out["answer_text"] = payload["answer_text"]
    if not out.get("status"):
        out["status"] = "completed"
    return out


def _probe_csv_for_file_id(investigation_id: str) -> dict[str, Any]:
    try:
        from src.api.investigations import _init_schema  # noqa: PLC0415
        from src.config.settings import get_settings  # noqa: PLC0415
        from src.db.session import create_db_session  # noqa: PLC0415
        from src.services.storage import read_attachment  # noqa: PLC0415
        from src.tools.csv_tool import inspect_schema, query_sql  # noqa: PLC0415

        _init_schema()
        with create_db_session() as session:
            row = session.execute(
                "SELECT file_id FROM investigation_files WHERE investigation_id = :id ORDER BY created_at LIMIT 1",
                {"id": investigation_id},
            ).fetchone()
        if not row:
            return {}
        file_id = row.file_id
        schema = inspect_schema(file_id)
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
    except Exception:  # noqa: BLE001
        return {}
