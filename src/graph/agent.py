"""Graph assembly — StateGraph compiled once at import."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.graph.edges import after_classify, after_transform
from src.graph.nodes import (
    classify_source,
    execute_query,
    finalize,
    generate_sql,
    handle_error,
    plan,
    synthesize_answer,
    transform_text,
    validate_sql,
)
from src.graph.state import AgentState


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("transform_text", transform_text)
    g.add_node("classify_source", classify_source)
    g.add_node("plan", plan)
    g.add_node("generate_sql", generate_sql)
    g.add_node("validate_sql", validate_sql)
    g.add_node("execute_query", execute_query)
    g.add_node("synthesize_answer", synthesize_answer)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    g.set_entry_point("classify_source")
    g.add_conditional_edges("classify_source", after_classify, {"plan": "plan", "transform_text": "transform_text", "handle_error": "handle_error"})
    g.add_conditional_edges("plan", after_classify, {"generate_sql": "generate_sql", "handle_error": "handle_error"})
    g.add_conditional_edges("generate_sql", after_classify, {"validate_sql": "validate_sql", "handle_error": "handle_error"})
    g.add_edge("validate_sql", "execute_query")
    g.add_conditional_edges("execute_query", after_classify, {"synthesize_answer": "synthesize_answer", "handle_error": "handle_error"})
    g.add_conditional_edges("synthesize_answer", after_classify, {"finalize": "finalize", "handle_error": "handle_error"})
    g.add_conditional_edges("transform_text", after_transform, {"finalize": "finalize", "handle_error": "handle_error"})
    g.add_edge("handle_error", END)
    g.add_edge("finalize", END)
    return g.compile()


agentic_ai = _build_graph()
