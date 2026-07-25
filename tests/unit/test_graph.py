from src.graph.agent import agentic_ai
from src.graph.edges import after_classify
from src.graph.state import AgentState
from src.graph.nodes import classify_source, validate_sql


def test_graph_compiles_with_new_nodes():
    assert agentic_ai is not None
    node_names = set(agentic_ai.get_graph().nodes)
    for name in [
        "classify_source",
        "plan",
        "generate_sql",
        "validate_sql",
        "execute_query",
        "synthesize_answer",
        "handle_error",
        "finalize",
    ]:
        assert name in node_names


def test_error_edge_routes_to_handler():
    state: AgentState = {"error": "boom"}
    assert after_classify(state) == "handle_error"
    state = {"error": None, "file_ids": ["f1"]}
    assert after_classify(state) == "build_temp_schema"


def test_classify_requires_question():
    state: AgentState = {"investigation_id": "inv-1", "question": ""}
    out = classify_source(state)
    assert out["error"] is not None
    assert out["status"] == "failed"


def test_validate_sql_blocks_dangerous_sql():
    state: AgentState = {"sql": "DROP TABLE t;"}
    out = validate_sql(state)
    assert out["error"] is not None
