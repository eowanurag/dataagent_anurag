"""Conditional routing functions."""
from __future__ import annotations

from src.graph.state import AgentState


# Legacy alias for the baseline transform-text graph node.
def after_transform(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"


def after_classify(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "plan"


def after_plan(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "generate_sql"


def after_generate_sql(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "validate_sql"


def after_validate_sql(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "execute_query"


def after_execute_query(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "synthesize_answer"


def after_synthesize_answer(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"
