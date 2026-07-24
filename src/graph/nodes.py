"""Graph nodes — analytical Q&A over CSV / future MsSQL.

Node contract: ``(state) -> partial state``. Failures must set ``error`` and
return; never raise through the graph.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.graph.state import AgentState
from src.llm.client import LLMClient, load_prompt
from src.llm.providers.base import LLMError
from src.observability.events import get_logger, log_span
from src.services.audit import record_audit
from src.services.storage import read_attachment
from src.tools.csv_tool import CsvQueryError, inspect_schema, query_sql

log = get_logger("graph")


def _actor() -> dict[str, Any]:
    return {"user_id": "demo-user", "rank": None, "unit": None}


def _audit_kwargs(*, investigation_id: str | None, run_id: str | None) -> dict[str, Any]:
    actor = _actor()
    return {
        "investigation_id": investigation_id,
        "run_id": run_id,
        "actor_user_id": actor["user_id"],
        "actor_rank": actor["rank"],
    }


def _complete(node: str, system: str, user: str, max_tokens: int = 1024) -> str:
    client = LLMClient()
    with log_span(log, node, provider=client.provider_name, model=client.model, input_chars=len(user)) as span:
        text = client.complete(system, user, max_tokens=max_tokens)
        span["output_chars"] = len(text)
        return text


def transform_text(state: AgentState) -> AgentState:
    """Baseline capability slot: apply instruction to input text."""
    try:
        client = LLMClient()
        system = load_prompt("transform")
        user = (
            f"INSTRUCTION:\n{state['instruction']}\n\n"
            f"TEXT:\n{state['input_text']}"
        )
        output = client.complete(system, user, max_tokens=2048)
        return {
            "output_text": output,
            "provider": client.provider_name,
            "model": client.model,
            "error": None,
        }
    except LLMError as exc:
        return {"error": str(exc)}


def classify_source(state: AgentState) -> AgentState:
    investigation_id = state.get("investigation_id")
    question = (state.get("question") or "").strip()
    if not question:
        return {"error": "question is required", "status": "failed", "checkpoint": "classify_source"}

    if not investigation_id:
        return {"source": "csv", "checkpoint": "classify_source"}

    source = "csv"
    return {"source": source, "checkpoint": "classify_source"}


def plan(state: AgentState) -> AgentState:
    investigation_id = state.get("investigation_id")
    question = state.get("question") or ""
    source = state.get("source") or "csv"

    schema_summary = ""
    files_context = "none"
    try:
        if source == "csv":
            file_id = state.get("file_id")
            if not file_id:
                return {"error": "No files are attached to this investigation yet. Upload CSV data before asking questions.", "status": "failed", "checkpoint": "plan"}
            schema = inspect_schema(file_id)
            schema_summary = f"columns={schema['columns']}, row_count={schema['row_count']}"
            files_context = "uploaded CSV"
    except Exception as exc:  # noqa: BLE001
        return {"error": f"schema lookup failed: {exc}", "status": "failed", "checkpoint": "plan"}

    system = load_prompt("plan")
    user = (
        f"Investigation ID: {investigation_id}\n"
        f"Source: {source}\n"
        f"Attached files: {files_context}\n"
        f"Schema summary: {schema_summary}\n"
        f"Question: {question}\n"
    )
    try:
        plan_text = _complete("plan", system, user, max_tokens=512)
        if not plan_text:
            plan_text = "shortcut: answer directly from CSV data without further planning"
        return {"plan": plan_text, "checkpoint": "plan"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "status": "failed", "checkpoint": "plan"}


def generate_sql(state: AgentState) -> AgentState:
    source = state.get("source") or "csv"
    question = state.get("question") or ""
    investigation_id = state.get("investigation_id")
    row_limit = 5000

    schema_summary = ""
    try:
        if source == "csv":
            file_id = state.get("file_id")
            if not file_id:
                return {"error": "No files are attached to this investigation yet. Upload CSV data before asking questions.", "status": "failed", "checkpoint": "generate_sql"}
            schema = inspect_schema(file_id)
            schema_summary = ", ".join(schema["columns"])
    except Exception as exc:  # noqa: BLE001
        return {"error": f"schema lookup failed: {exc}", "status": "failed", "checkpoint": "generate_sql"}

    system = load_prompt("sql")
    user = (
        f"Source: {source}\n"
        f"Schema/columns: {schema_summary}\n"
        f"Question: {question}\n"
        f"Row limit: {row_limit}\n"
    )
    try:
        sql_text = _complete("generate_sql", system, user, max_tokens=256)
        sql_text = sql_text.strip()
        if not sql_text:
            return {"error": "sql generation returned empty", "status": "failed", "checkpoint": "generate_sql"}
        return {"sql": sql_text, "checkpoint": "generate_sql"}
    except LLMError as exc:
        return {"error": str(exc), "status": "failed", "checkpoint": "generate_sql"}


def validate_sql(state: AgentState) -> AgentState:
    sql = (state.get("sql") or "").strip()
    if not sql:
        return {"error": "sql is empty", "status": "failed", "checkpoint": "validate_sql"}

    normalized = sql.upper()
    forbidden = ["--", ";", "/*", "*/", "@@", "\\", "DROP ", "DELETE ", "UPDATE ", "INSERT ", "ALTER ", "TRUNCATE ", "EXEC ", "EXECUTE "]
    for token in forbidden:
        if token in normalized:
            return {"error": f"sql contains forbidden token: {token}", "status": "failed", "checkpoint": "validate_sql"}

    return {"checkpoint": "validate_sql"}


def execute_query(state: AgentState) -> AgentState:
    source = state.get("source") or "csv"
    sql = (state.get("sql") or "").strip()
    investigation_id = state.get("investigation_id")
    run_id = state.get("run_id")
    max_rows = 5000

    if source != "csv":
        return {"error": "unsupported source in phase 1", "status": "failed", "checkpoint": "execute_query"}

    file_id = state.get("file_id")
    if not file_id:
        msg = "No files are attached to this investigation yet. Upload CSV data before asking questions."
        return {"error": msg, "status": "failed", "checkpoint": "execute_query"}
    if not sql:
        return {"error": "sql is empty", "status": "failed", "checkpoint": "execute_query"}

    try:
        df = query_sql(file_id, sql, max_rows=max_rows)
    except CsvQueryError as exc:
        return {"error": f"csv query failed: {exc}", "status": "failed", "checkpoint": "execute_query"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"csv query failed: {exc}", "status": "failed", "checkpoint": "execute_query"}

    try:
        record_audit(
            **_audit_kwargs(investigation_id=investigation_id, run_id=run_id),
            action="csv_query_executed",
            source="csv",
            sql=sql,
            row_count=int(df.shape[0]),
        )
    except Exception:  # noqa: BLE001
        pass
    return {
        "sql_rows": df.head(500).to_dict(orient="records"),
        "sql_row_count": int(df.shape[0]),
        "checkpoint": "execute_query",
    }


def synthesize_answer(state: AgentState) -> AgentState:
    question = state.get("question") or ""
    sql = state.get("sql") or ""
    sql_rows = state.get("sql_rows") or []
    sql_row_count = state.get("sql_row_count") or 0
    source = state.get("source") or "csv"

    sample_rows = sql_rows[:50]
    system = load_prompt("synthesize")
    user = (
        f"Question: {question}\n"
        f"SQL: {sql}\n"
        f"Row count returned: {sql_row_count}\n"
        f"Row count available: {sql_row_count}\n"
        f"Rows sample (JSON array, first {len(sample_rows)} rows): {json.dumps(sample_rows)}\n"
    )
    try:
        answer_text = _complete("synthesize_answer", system, user, max_tokens=1024)
    except LLMError as exc:
        return {"error": str(exc), "status": "failed", "checkpoint": "synthesize_answer"}

    citations = [f"{source}: {sql}"] if sql else ([f"{source}: data"] if source else [])
    followups = [
        "Show top-ranked results with a limit",
        "Filter by a specific column value",
        "Group and aggregate the result",
    ]
    chart_spec = {"type": "table", "data": sample_rows}

    return {
        "answer_text": answer_text,
        "citations": citations,
        "followup_suggestions": followups,
        "chart_spec": chart_spec,
        "status": "completed",
        "checkpoint": "synthesize_answer",
    }


def handle_error(state: AgentState) -> AgentState:
    investigation_id = state.get("investigation_id")
    run_id = state.get("run_id")
    error_message = state.get("error")
    try:
        record_audit(
            **_audit_kwargs(investigation_id=investigation_id, run_id=run_id),
            action="run_failed",
            source=state.get("source"),
            sql=state.get("sql"),
            row_count=state.get("sql_row_count"),
            error_message=error_message,
            payload={"checkpoint": state.get("checkpoint")},
        )
    except Exception:  # noqa: BLE001
        pass
    return {"status": "failed", "error": error_message, "checkpoint": "handle_error"}


def finalize(state: AgentState) -> AgentState:
    return {"status": "completed", "checkpoint": "finalize"}

