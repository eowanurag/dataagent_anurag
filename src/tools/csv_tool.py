"""Pure CSV tooling: schema inference and SQL query over uploaded files."""
from __future__ import annotations

import re
import sqlite3
from typing import Any

import pandas as pd

from src.services.storage import read_attachment


class CsvQueryError(Exception):
    pass


def _resolve_table_name(file_id: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", file_id)
    if not sanitized or sanitized[0].isdigit():
        sanitized = f"t_{sanitized}"
    return sanitized


def inspect_schema(file_id: str) -> dict[str, Any]:
    path = read_attachment(file_id)
    try:
        df = pd.read_csv(path, nrows=1000)
    except Exception as exc:
        raise CsvQueryError("invalid csv") from exc
    return {
        "columns": list(df.columns),
        "row_count": int(pd.read_csv(path).shape[0]),
        "sample": df.head(5).to_dict(orient="records"),
    }


def query_sql(file_id: str, sql: str, max_rows: int = 5000) -> pd.DataFrame:
    if not sql.strip():
        raise CsvQueryError("sql is empty")
    if max_rows <= 0:
        raise CsvQueryError("max_rows must be > 0")
    for bad in ("--", ";", "/*", "*/", "@@", "\\"):
        if bad in sql:
            raise CsvQueryError(f"unsupported sql fragment: {bad}")
    path = read_attachment(file_id)
    try:
        df = pd.read_csv(path)
        conn = sqlite3.connect(":memory:")
        df.to_sql(_resolve_table_name(file_id), conn, index=False, if_exists="replace")
        query = f"SELECT * FROM {_resolve_table_name(file_id)} LIMIT {int(max_rows)}"
        result = pd.read_sql(query, conn)
        return result
    except CsvQueryError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CsvQueryError(str(exc)) from exc
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
