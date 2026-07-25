from src.graph.agent import agentic_ai
from src.graph.edges import after_classify
from src.graph.state import AgentState
from src.graph.nodes import classify_source, validate_sql


def test_graph_compiles_with_new_nodes():
    assert agentic_ai is not None
    node_names = set(agentic_ai.get_graph().nodes)
    for name in [
        "classify_source",
        "build_temp_schema",
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


def test_validate_sql_requires_join_alias_and_on_for_multi_file():
    base: AgentState = {"file_ids": ["a", "b"]}
    ok = validate_sql({**base, "sql": "SELECT * FROM t1 AS a JOIN t2 AS b ON a.id = b.id LIMIT 10"})
    assert "error" not in ok, ok.get("error")

    bad = validate_sql({**base, "sql": "SELECT * FROM t1 JOIN t2 ON t1.id = t2.id LIMIT 10"})
    assert bad["error"] is not None

    too_many = validate_sql({**base, "sql": "SELECT * FROM t1 AS a JOIN t2 AS b ON a.id = b.id JOIN t3 AS c ON b.id = c.id LIMIT 10"})
    assert too_many["error"] is not None

    missing_on = validate_sql({**base, "sql": "SELECT * FROM t1 AS a JOIN t2 AS b LIMIT 10"})
    assert missing_on["error"] is not None


def test_validate_sql_blocks_join_tokens_in_single_file():
    state: AgentState = {"sql": "SELECT * FROM t AS x JOIN y ON x.id = y.id"}
    out = validate_sql(state)
    assert out["error"] is not None
