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


def _infer_join_relationships(file_schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not file_schemas:
        return []
    relations: list[dict[str, Any]] = []
    for i, left in enumerate(file_schemas):
        for right in file_schemas[i + 1:]:
            common = sorted(set(left.get("columns") or []) & set(right.get("columns") or []))
            if not common:
                continue
            score = 0
            candidate = common[0]
            for col in common:
                if "_id" in col.lower() or col.lower().endswith("id"):
                    candidate = col
                    score += 2
                if col.lower() in {"id", "name", "sr_no", "sl_no"}:
                    score += 1
            if candidate:
                relations.append(
                    {
                        "from": left.get("file_id"),
                        "from_table": left.get("table_name"),
                        "from_col": candidate,
                        "to": right.get("file_id"),
                        "to_table": right.get("table_name"),
                        "to_col": candidate,
                        "confidence": min(100, 60 + score * 10),
                        "reason": f"shared column `{candidate}` between {left.get('table_name')} and {right.get('table_name')}",
                    }
                )
    return relations


def build_temp_schema(file_ids: list[str]) -> dict[str, Any]:
    tables = []
    for file_id in file_ids:
        schema = inspect_schema(file_id)
        tables.append(
            {
                "file_id": file_id,
                "table_name": _resolve_table_name(file_id),
                "columns": schema.get("columns") or [],
                "row_count": schema.get("row_count") or 0,
                "sample": schema.get("sample") or [],
            }
        )
    relations = _infer_join_relationships(tables)
    return {"tables": tables, "relationships": relations}


def query_sql(file_id: str, sql: str, max_rows: int = 5000) -> pd.DataFrame:
    if not sql.strip():
        raise CsvQueryError("sql is empty")
    if max_rows <= 0:
        raise CsvQueryError("max_rows must be > 0")
    for bad in ("--", ";", "/*", "*/", "@@", "\\", " DROP ", " DELETE ", " UPDATE ", " INSERT ", " ALTER ", " TRUNCATE ", " EXEC ", " EXECUTE "):
        if bad in sql:
            raise CsvQueryError(f"unsupported sql fragment: {bad}")
    path = read_attachment(file_id)
    conn = sqlite3.connect(":memory:")
    try:
        df = pd.read_csv(path)
        table = _resolve_table_name(file_id)
        df.to_sql(table, conn, index=False, if_exists="replace")
        sql = re.sub(r"(?i)\s+LIMIT\s+\d+(\s+OFFSET\s+\d+)?\s*$", "", sql.strip())
        result = pd.read_sql(f"{sql} LIMIT {int(max_rows)}", conn)
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


def query_sql_multi(file_ids: list[str], sql: str, max_rows: int = 5000) -> pd.DataFrame:
    if not file_ids:
        raise CsvQueryError("no file ids provided")
    if not sql.strip():
        raise CsvQueryError("sql is empty")
    if max_rows <= 0:
        raise CsvQueryError("max_rows must be > 0")
    conn = sqlite3.connect(":memory:")
    try:
        for file_id in file_ids:
            path = read_attachment(file_id)
            df = pd.read_csv(path)
            table = _resolve_table_name(file_id)
            df.to_sql(table, conn, index=False, if_exists="replace")
        sql = re.sub(r"(?i)\s+LIMIT\s+\d+(\s+OFFSET\s+\d+)?\s*$", "", sql.strip())
        result = pd.read_sql(f"{sql} LIMIT {int(max_rows)}", conn)
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
