"""AgentState — the TypedDict flowing through the graph."""
from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    investigation_id: str
    user_id: str
    source: str | None
    question: str
    plan: str | None
    sql: str | None
    sql_rows: list[dict] | None
    sql_row_count: int | None
    chart_spec: dict | None
    followup_suggestions: list[str] | None
    answer_text: str | None
    citations: list[str] | None
    error: str | None
    status: str | None
    checkpoint: str | None
    provider: str | None
    model: str | None
    input_text: str | None
