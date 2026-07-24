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


def test_build_chart_spec_defaults_to_table_for_many_rows():
    rows = [{"district": k, "count": k} for k in range(1, 26)]
    assert _build_chart_spec(rows)["type"] == "table"


def test_build_chart_spec_returns_bar_for_small_numeric_set():
    rows = [{"district": "A", "count": 5}, {"district": "B", "count": 9}]
    spec = _build_chart_spec(rows)
    assert spec["type"] == "bar"
    assert spec["x"] == "district"
    assert spec["y"] == "count"
