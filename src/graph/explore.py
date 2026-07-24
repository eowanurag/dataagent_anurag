"""Explore-phase execution across candidate models."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.config.settings import get_settings
from src.graph.runner import run_investigation_graph
from src.llm.registry import canonicalize, list_variants


@dataclass
class CandidateResult:
    model_id: str
    provider: str
    status: str
    latency_ms: int
    answer_text: str | None = None
    chart_spec: dict | None = None
    sql: str | None = None
    sql_row_count: int | None = None
    error: str | None = None


@dataclass
class ExploreOutcome:
    investigation_id: str
    run_id: str
    question: str
    candidates: list[CandidateResult] = field(default_factory=list)
    winner: CandidateResult | None = None
    latency_ms: int = 0

    def select_winner(self) -> CandidateResult | None:
        completed = [c for c in self.candidates if c.status == "completed" and c.answer_text]
        if not completed:
            failed = [c for c in self.candidates if c.status == "failed"]
            return failed[0] if failed else None
        completed.sort(key=lambda c: (c.latency_ms, -(c.sql_row_count or 0)))
        return completed[0]


def _variant_for(model_id: str) -> dict[str, Any]:
    for variant in list_variants():
        if variant["id"] == model_id:
            return variant
    return {"id": model_id, "provider": "openrouter", "label": model_id}


def run_explore_phase(
    investigation_id: str,
    question: str,
    source: str = "csv",
    file_id: str | None = None,
    candidate_model_ids: list[str] | None = None,
    user_id: str = "demo-user",
) -> ExploreOutcome:
    start = time.perf_counter()
    candidates = candidate_model_ids or [get_settings().resolve_model()]
    outcome = ExploreOutcome(
        investigation_id=investigation_id,
        run_id=f"explore-{uuid.uuid4().hex[:12]}",
        question=question,
    )

    for model_id in candidates:
        model_id = canonicalize(model_id)
        variant = _variant_for(model_id)
        candidate_run_id = f"{outcome.run_id}-{variant['provider']}-{uuid.uuid4().hex[:8]}"
        t0 = time.perf_counter()
        try:
            result = run_investigation_graph(
                investigation_id=investigation_id,
                run_id=candidate_run_id,
                user_id=user_id,
                question=question,
                source=source,
                file_id=file_id,
                provider_override=variant["provider"],
                model_override=model_id,
            )
            outcome.candidates.append(CandidateResult(
                model_id=model_id,
                provider=variant["provider"],
                status=result.get("status") or "failed",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                answer_text=result.get("answer_text"),
                chart_spec=result.get("chart_spec"),
                sql=result.get("sql"),
                sql_row_count=result.get("sql_row_count"),
                error=result.get("error"),
            ))
        except Exception as exc:  # noqa: BLE001
            outcome.candidates.append(CandidateResult(
                model_id=model_id,
                provider=variant["provider"],
                status="failed",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error=str(exc),
            ))

    outcome.winner = outcome.select_winner()
    outcome.latency_ms = int((time.perf_counter() - start) * 1000)
    return outcome
