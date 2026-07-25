"""Graph nodes — analytical Q&A over CSV / future MsSQL.

Node contract: ``(state) -> partial state``. Failures must set ``error`` and
return; never raise through the graph.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from src.graph.state import AgentState
from src.llm.client import LLMClient, load_prompt
from src.llm.providers.base import LLMError
from src.observability.events import get_logger, log_span
from src.services.audit import record_audit
from src.services.storage import read_attachment
from src.tools.csv_tool import (
    CsvQueryError,
    _resolve_table_name,
    build_temp_schema,
    inspect_schema,
    query_sql,
    query_sql_multi,
)

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

    file_ids = list(state.get("file_ids") or [])
    if not file_ids:
        return {
            "error": "No files are attached to this investigation yet. Upload CSV data before asking questions.",
            "status": "failed",
            "checkpoint": "classify_source",
        }

    out: dict[str, Any] = {"source": "csv", "checkpoint": "classify_source"}
    if len(file_ids) > 1:
        out["file_ids"] = file_ids
        try:
            out["temp_schema"] = build_temp_schema(file_ids)
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"temp schema build failed: {exc}"
            out["status"] = "failed"
    else:
        out["file_id"] = file_ids[0]
    return out


def build_temp_schema_node(state: AgentState) -> AgentState:
    file_ids = list(state.get("file_ids") or [])
    if not file_ids:
        return {"error": "No files are attached to this investigation yet. Upload CSV data before asking questions.", "status": "failed", "checkpoint": "build_temp_schema"}
    try:
        temp_schema = build_temp_schema(file_ids)
        return {"temp_schema": temp_schema, "checkpoint": "build_temp_schema"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"temp schema build failed: {exc}", "status": "failed", "checkpoint": "build_temp_schema"}


def plan(state: AgentState) -> AgentState:
    investigation_id = state.get("investigation_id")
    question = state.get("question") or ""
    source = state.get("source") or "csv"
    temp_schema = state.get("temp_schema")
    file_ids = state.get("file_ids") or ([state.get("file_id")] if state.get("file_id") else [])
    file_ids = [fid for fid in file_ids if fid]

    schema_summary = ""
    files_context = "none"
    try:
        if source == "csv":
            if not file_ids:
                return {
                    "error": "No files are attached to this investigation yet. Upload CSV data before asking questions.",
                    "status": "failed",
                    "checkpoint": "plan",
                }
            if temp_schema and isinstance(temp_schema.get("tables"), list) and temp_schema["tables"]:
                tables = temp_schema["tables"]
                schema_summary = "\n".join(
                    f"table={t.get('table_name')}, columns={', '.join(t.get('columns') or [])}, row_count={t.get('row_count') or 0}"
                    for t in tables
                )
                files_context = f"attached files: {', '.join(t.get('table_name') for t in tables)}"
            else:
                inspected = []
                for file_id in file_ids:
                    schema = inspect_schema(file_id)
                    inspected.append((_resolve_table_name(file_id), schema))
                schema_summary = "\n".join(
                    f"table={table}, columns={', '.join(schema['columns'])}, row_count={schema['row_count']}"
                    for table, schema in inspected
                )
                files_context = f"attached files: {', '.join(table for table, _ in inspected)}"
    except Exception as exc:  # noqa: BLE001
        return {"error": f"schema lookup failed: {exc}", "status": "failed", "checkpoint": "plan"}

    system = load_prompt("plan")
    user = (
        f"Investigation ID: {investigation_id}\n"
        f"Source: {source}\n"
        f"Attached files: {files_context}\n"
        f"Schema summary:\n{schema_summary}\n"
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
    temp_schema = state.get("temp_schema")
    file_ids = state.get("file_ids") or ([state.get("file_id")] if state.get("file_id") else [])
    file_ids = [fid for fid in file_ids if fid]

    schema_summary = ""
    try:
        if source == "csv":
            if not file_ids:
                return {
                    "error": "No files are attached to this investigation yet. Upload CSV data before asking questions.",
                    "status": "failed",
                    "checkpoint": "generate_sql",
                }
            if temp_schema and isinstance(temp_schema.get("tables"), list) and temp_schema["tables"]:
                schema_summary = "\n".join(
                    f"table={t.get('table_name')}, columns={', '.join(t.get('columns') or [])}"
                    for t in temp_schema["tables"]
                )
            else:
                inspected = []
                for file_id in file_ids:
                    schema = inspect_schema(file_id)
                    inspected.append((_resolve_table_name(file_id), schema))
                schema_summary = "\n".join(
                    f"table={table}, columns={', '.join(schema['columns'])}"
                    for table, schema in inspected
                )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"schema lookup failed: {exc}", "status": "failed", "checkpoint": "generate_sql"}

    system = load_prompt("sql")
    user = (
        f"Source: {source}\n"
        f"Schema/columns:\n{schema_summary}\n"
        f"Question: {question}\n"
        f"Row limit: {row_limit}\n"
    )
    if len(file_ids) > 1:
        user += (
            "Multiple files are attached. If a cross-file query is needed, use explicit JOINs with table aliases only.\n"
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
    forbidden = [
        "--", ";", "/*", "*/", "@@", "\\",
        "DROP ", "DELETE ", "UPDATE ", "INSERT ", "ALTER ", "TRUNCATE ", "EXEC ", "EXECUTE ",
    ]
    for token in forbidden:
        if token in normalized:
            return {"error": f"sql contains forbidden token: {token}", "status": "failed", "checkpoint": "validate_sql"}

    file_ids = [fid for fid in (state.get("file_ids") or []) if fid]
    if len(file_ids) <= 1:
        single_file_forbidden = [" JOIN ", " ON ", " AS "]
        for token in single_file_forbidden:
            if token in normalized:
                return {"error": f"sql contains forbidden token for single-file query: {token.strip()}", "status": "failed", "checkpoint": "validate_sql"}
        return {"checkpoint": "validate_sql"}

    join_pattern = re.compile(r"\bJOIN\b\s+\w+\s+\bAS\b\s+\w+", normalized)
    join_count = len(re.findall(r"\bJOIN\b", normalized))
    if join_count != 1:
        return {"error": "multi-file sql requires exactly one JOIN with one alias", "status": "failed", "checkpoint": "validate_sql"}
    if not join_pattern.search(normalized):
        return {"error": "multi-file sql requires JOIN with a single alias", "status": "failed", "checkpoint": "validate_sql"}
    if not re.search(r"\bON\b", normalized):
        return {"error": "multi-file sql requires ON with join keys", "status": "failed", "checkpoint": "validate_sql"}
    join_keys = re.findall(r"\bON\b\s+[^=]+=\s*[^=]+", normalized)
    if len(join_keys) != 1:
        return {"error": "multi-file sql requires one join condition", "status": "failed", "checkpoint": "validate_sql"}
    return {"checkpoint": "validate_sql"}


def execute_query(state: AgentState) -> AgentState:
    source = state.get("source") or "csv"
    sql = (state.get("sql") or "").strip()
    investigation_id = state.get("investigation_id")
    run_id = state.get("run_id")
    max_rows = 5000

    if source != "csv":
        return {"error": "unsupported source in phase 1", "status": "failed", "checkpoint": "execute_query"}

    file_ids = state.get("file_ids") or ([state.get("file_id")] if state.get("file_id") else [])
    file_ids = [fid for fid in file_ids if fid]
    if not file_ids:
        msg = "No files are attached to this investigation yet. Upload CSV data before asking questions."
        return {"error": msg, "status": "failed", "checkpoint": "execute_query"}
    if not sql:
        return {"error": "sql is empty", "status": "failed", "checkpoint": "execute_query"}

    try:
        if len(file_ids) > 1:
            df = query_sql_multi(file_ids, sql, max_rows=max_rows)
        else:
            df = query_sql(file_ids[0], sql, max_rows=max_rows)
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
    sql = (state.get("sql") or "").strip()
    sql_rows = state.get("sql_rows") or []
    sql_row_count = state.get("sql_row_count") or 0
    source = state.get("source") or "csv"

    chart_spec = _build_chart_spec(sql_rows)
    sample_rows = sql_rows[:50]
    system = load_prompt("synthesize")
    user = (
        f"Question: {question}\n"
        f"SQL: {sql}\n"
        f"Row count returned: {sql_row_count}\n"
        f"Row count available: {sql_row_count}\n"
        f"Rows sample (JSON array, first {len(sample_rows)} rows): {json.dumps(sample_rows)}\n"
        f"Chart type: {chart_spec.get('type')}"
    )
    try:
        answer_text = _complete("synthesize_answer", system, user, max_tokens=1024)
    except LLMError as exc:
        return {"error": str(exc), "status": "failed", "checkpoint": "synthesize_answer"}

    citations = [f"{source}: {sql}"] if sql else ([f"{source}: data"] if source else [])
    followups = [
        "Show a chart view of these results",
        "Filter these results by a specific value",
        "Show the top/bottom ranked rows",
    ]

    return {
        "answer_text": answer_text,
        "citations": citations,
        "followup_suggestions": followups,
        "chart_spec": chart_spec,
        "chart_type": chart_spec.get("type"),
        "chart_x": chart_spec.get("x"),
        "chart_y": chart_spec.get("y"),
        "status": "completed",
        "checkpoint": "synthesize_answer",
    }


def _build_chart_spec(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {"type": "empty", "data": []}
    numeric_keys = _infer_numeric_keys(rows)
    string_keys = _infer_string_keys(rows)
    chart_type = "table"
    x = string_keys[0] if string_keys else (list(rows[0].keys())[0] if rows[0] else None)
    y = numeric_keys[0] if numeric_keys else None
    if len(rows) <= 20 and x and y:
        chart_type = "bar"
    if chart_type == "table" and len(rows) > 0:
        return {"type": "table", "data": rows[:250], "columns": list(rows[0].keys())}
    return {
        "type": chart_type,
        "data": rows[:250],
        "x": x,
        "y": y,
        "columns": list(rows[0].keys()) if rows else [],
    }


def _infer_numeric_keys(rows: list[dict]) -> list[str]:
    if not rows:
        return []
    candidates = list(rows[0].keys())
    out: list[str] = []
    for key in candidates:
        values = [r.get(key) for r in rows[:200]]
        numeric_count = sum(_is_number(v) for v in values if v is not None)
        ratio = numeric_count / max(len(values), 1)
        if ratio >= 0.85:
            out.append(key)
    return out


def _infer_string_keys(rows: list[dict]) -> list[str]:
    if not rows:
        return []
    numeric_keys = _infer_numeric_keys(rows)
    candidates = list(rows[0].keys())
    return [key for key in candidates if key.lower() not in {"id", "row_id", "index"} and key not in numeric_keys][:5]


def _is_number(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str) and value.strip().replace(".", "", 1).replace("-", "", 1).isdigit():
        return True
    return False


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

