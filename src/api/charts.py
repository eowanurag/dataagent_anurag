"""Backend page that renders chart specs for model answers."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.graph.explore import CandidateResult, ExploreOutcome, run_explore_phase

router = APIRouter()


@router.get("/charts")
def list_charts() -> dict:
    return {
        "types": ["table", "bar", "line", "pie", "empty"],
        "render_default": "bar",
    }


@router.post("/investigations/{investigation_id}/explore")
def explore_models(investigation_id: str, payload: dict | None = None) -> dict:
    question = (payload or {}).get("question") or "Summarize this dataset"
    source = (payload or {}).get("source") or "csv"
    file_id = (payload or {}).get("file_id")
    candidates = (payload or {}).get("candidate_models") or None
    outcome = run_explore_phase(
        investigation_id=investigation_id,
        question=question,
        source=source,
        file_id=file_id,
        candidate_model_ids=candidates,
    )
    return JSONResponse(_to_payload(outcome))


def _to_payload(outcome: ExploreOutcome) -> dict:
    return {
        "investigation_id": outcome.investigation_id,
        "run_id": outcome.run_id,
        "question": outcome.question,
        "latency_ms": outcome.latency_ms,
        "winner": _result_to_dict(outcome.winner),
        "candidates": [_result_to_dict(c) for c in outcome.candidates],
    }


def _result_to_dict(result: CandidateResult | None) -> dict | None:
    if result is None:
        return None
    return {
        "model_id": result.model_id,
        "provider": result.provider,
        "status": result.status,
        "latency_ms": result.latency_ms,
        "answer_text": result.answer_text,
        "chart_spec": result.chart_spec,
        "sql": result.sql,
        "sql_row_count": result.sql_row_count,
        "error": result.error,
    }
