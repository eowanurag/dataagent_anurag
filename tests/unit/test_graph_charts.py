from src.graph.nodes import _build_chart_spec, _infer_string_keys, _infer_numeric_keys, _is_number


def test_infer_numeric_keys_detects_int_like_values():
    rows = [{"district": "A", "count": 10}, {"district": "B", "count": 25}]
    assert _infer_numeric_keys(rows) == ["count"]


def test_infer_string_keys_ignores_id_like_columns():
    rows = [{"id": 1, "district": "A", "count": 10}]
    assert _infer_string_keys(rows) == ["district"]


def test_is_number_handles_strings():
    assert _is_number("10") is True
    assert _is_number("-3") is True
    assert _is_number("3.5") is True
    assert _is_number("abc") is False


def test_build_chart_spec_returns_bar_for_numeric_rows():
    rows = [{"district": f"D{k}", "count": k} for k in range(1, 26)]
    spec = _build_chart_spec(rows)
    assert spec["type"] == "bar"
    assert spec["x"] == "district"
    assert "y" in spec


def test_build_chart_spec_returns_table_when_no_numeric_keys():
    rows = [{"district": "A", "name": "alpha"}, {"district": "B", "name": "beta"}]
    spec = _build_chart_spec(rows)
    assert spec["type"] == "table"


def test_build_chart_spec_prefers_pie_for_share_question():
    rows = [{"category": "A", "count": 10}, {"category": "B", "count": 20}]
    spec = _build_chart_spec(rows, question="Show a pie chart of share by category")
    assert spec["type"] == "pie"


def test_build_chart_spec_prefers_line_for_trend_question():
    rows = [{"month": "Jan", "count": 10}, {"month": "Feb", "count": 20}]
    spec = _build_chart_spec(rows, question="Line chart of trend over time")
    assert spec["type"] == "line"


def test_build_chart_spec_prefers_bar_when_question_asks_for_chart():
    rows = [{"district": "A", "count": 10}, {"district": "B", "count": 20}]
    spec = _build_chart_spec(rows, question="Show a chart of counts by district")
    assert spec["type"] == "bar"
