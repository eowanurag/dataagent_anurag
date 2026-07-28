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
    state = {"error": None, "file_ids": ["f1"], "investigation_id": "inv1"}
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
    assert "error" not in bad

    two_joins = validate_sql({**base, "sql": "SELECT * FROM t1 AS a JOIN t2 AS b ON a.id = b.id JOIN t3 AS c ON b.id = c.id LIMIT 10"})
    assert "error" not in two_joins

    too_many = validate_sql({**base, "sql": "SELECT * FROM t1 AS a " + " ".join(f"JOIN t{i} AS a{i} ON a.id = a{i}.id" for i in range(2, 14)) + " LIMIT 10"})
    assert too_many["error"] is not None

    missing_on = validate_sql({**base, "sql": "SELECT * FROM t1 AS a JOIN t2 AS b LIMIT 10"})
    assert missing_on["error"] is not None


def test_validate_sql_blocks_join_tokens_in_single_file():
    state: AgentState = {"sql": "SELECT * FROM t AS x JOIN y ON x.id = y.id"}
    out = validate_sql(state)
    assert out["error"] is not None


def test_validate_sql_columns_against_schema_allows_exact_columns_and_rejects_bad_aliases():
    state: AgentState = {
        "file_ids": ["f1", "f2"],
        "temp_schema": {
            "tables": [
                {"table_name": "files", "columns": ["DISTRICT", "CRIME_HEAD_CD"]},
                {"table_name": "incidents", "columns": ["DISTRICT", "INCIDENT_ID"]},
            ]
        },
        "sql": "SELECT T1.DISTRICT, T1.CRIME_HEAD_CD, T2.DISTRICT, COUNT(T2.INCIDENT_ID) FROM files AS T1 INNER JOIN incidents AS T2 ON T1.DISTRICT = T2.DISTRICT GROUP BY T1.DISTRICT, T1.CRIME_HEAD_CD ORDER BY COUNT(T2.INCIDENT_ID) DESC LIMIT 5000",
    }
    out = validate_sql(state)
    assert "error" not in out, out.get("error")

    bad_alias_state = {
        **state,
        "sql": "SELECT T2.DISTRICT, T2.CRIME_HEAD_CD FROM files AS T1 INNER JOIN incidents AS T2 ON T1.DISTRICT = T2.CRIME_HEAD_CD",
    }
    bad = validate_sql(bad_alias_state)
    assert bad["error"] is not None
    assert "unlisted columns" in bad["error"]

    bare_token_state = {
        **state,
        "sql": "SELECT crime, cyber, 5000, DISTRICT FROM files",
    }
    out = validate_sql(bare_token_state)
    assert "error" not in out, out.get("error")
