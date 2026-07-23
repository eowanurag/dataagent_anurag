"""Assets API — dataset schema and ER diagram metadata."""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from src.config.settings import get_settings
from src.db.session import get_session
from src.db.schema import init_schema
from src.observability.events import get_logger
from src.services.storage import read_attachment

router = APIRouter()
log = get_logger("assets")
_init_schema = init_schema


def _ok(payload: dict):
    return JSONResponse({"data": payload})


def _error(code: str, message: str, status: int = 400):
    return JSONResponse({"detail": {"code": code, "message": message}}, status_code=status)


def _safe_table_name(name: str) -> str:
    base = re.sub(r"\W+", "_", name or "TABLE").strip("_").upper()
    if not base:
        base = "TABLE"
    if base[0].isdigit():
        base = f"T_{base}"
    return base[:64]


def _infer_pk_candidate(columns: list[str]) -> str | None:
    lowered = [c.lower().strip() for c in columns]
    for idx, col in enumerate(lowered):
        if col in ("id",) or re.match(r"^\w+_(id|uuid)$", col):
            return columns[idx]
    for idx, col in enumerate(lowered):
        if re.search(r"(code|number|sl_no|sr_no|serial)$", col):
            return columns[idx]
    return None


def _escape(value: str) -> str:
    return value.replace('"', "'").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").strip()


def _relation_label(src: str, dst: str) -> str:
    if not src and not dst:
        return "related"
    label = "related"
    source_with = src.split(":")[-1].replace("_", " ")
    target_with = dst.split(":")[-1].replace("_", " ")
    if source_with.lower() in target_with.lower() or target_with.lower() in source_with.lower():
        label = "relates_to"
    if any(token in src.upper() or token in dst.upper() for token in ["DISTRICT","CIRCLE","POLICE"]):
        label = "contains"
    elif any(token in src.upper() or token in dst.upper() for token in ["PLACED","ORDERED","PURCHASED","ASSIGNED_BY"]):
        label = "placed_by"
    elif any(token in src.upper() or token in dst.upper() for token in ["ASSIGNED","ALLOCATED","POSTED"]):
        label = "assigned_to"
    elif any(token in src.upper() or token in dst.upper() for token in ["INVOLVES","RELATED","ASSOCIATED"]):
        label = "involves"
    elif any(token in src.upper() or token in dst.upper() for token in ["BELONGS","OWNED","LINKED"]):
        label = "belongs_to"
    return label


def infer_relations(datasets: list[dict]) -> list[dict]:
    relations: list[dict] = []
    for i in range(len(datasets)):
        for j in range(len(datasets)):
            if i == j:
                continue
            src_cols = datasets[i].get("columns", [])
            dst_cols = datasets[j].get("columns", [])
            if not src_cols or not dst_cols:
                continue
            src_names = {c.lower() for c in src_cols}
            relation_type = "1:1"
            if any("id" in c or "key" in c for c in src_names):
                relation_type = "1:N"
                if any("id" in c or "key" in c for c in {c.lower() for c in dst_cols}):
                    if len(src_cols) > len(dst_cols):
                        relation_type = "N:1"
                    elif len(src_cols) == len(dst_cols):
                        relation_type = "1:1"
            confidence = 0.6 if _relation_label(datasets[i].get("id",""), datasets[j].get("id","")) == "related" else 0.9
            relations.append({
                "src": datasets[i]["id"],
                "dst": datasets[j]["id"],
                "label": _relation_label(datasets[i].get("id",""), datasets[j].get("id","")),
                "type": relation_type,
                "confidence": confidence,
            })
    return relations[:25]


def summarize_file(file_id: str) -> dict:
    storage_root = Path(get_settings().storage_root).expanduser().resolve()
    path = storage_root / file_id
    try:
        import pandas as _pd

        df = _pd.read_csv(path, nrows=250)
        cols = [str(c) for c in df.columns]
        sample_rows = df.head(5).fillna("").to_dict(orient="records")
        return {
            "summary": f"{len(df)} sample rows",
            "columns": [{"name": c, "type": "unknown"} for c in cols],
            "sample_rows": sample_rows,
        }
    except Exception as exc:
        log.warning("file_summary_failed", file_id=file_id, error=str(exc))
        return {"summary": "Summary unavailable", "columns": [], "sample_rows": []}


@router.get("/investigations/{investigation_id}/assets/er")
def get_er_diagram(investigation_id: str, session: Session = Depends(get_session)):
    _init_schema()
    inv = session.execute(
        sql_text("SELECT investigation_id FROM investigations WHERE investigation_id = :id"), {"id": investigation_id}
    ).fetchone()
    if inv is None:
        return _error("not_found", "investigation not found", 404)

    rows = session.execute(
        sql_text("SELECT * FROM investigation_files WHERE investigation_id = :iid ORDER BY created_at"),
        {"iid": investigation_id},
    ).fetchall()

    datasets = []
    for r in rows:
        columns = json.loads(r.columns_json) if r.columns_json else []
        datasets.append(
            {
                "id": r.file_id,
                "name": r.original_filename or r.filename,
                "status": "uploaded",
                "columns": columns,
                "row_count": r.row_count or 0,
                "size_bytes": r.size_bytes or 0,
            }
        )

    relation_pool = [{"id": d["id"], "columns": d["columns"]} for d in datasets]
    summary_tables: list[dict] = []
    for dataset in datasets:
        for table in dataset.get("derived", {}).get("tables", []):
            summary_tables.append({"id": f"{dataset['id']}:{table['name']}", "columns": [c["name"] for c in table.get("columns", [])]})
    relation_pool.extend(summary_tables)

    relations = infer_relations(relation_pool)
    entity_summary = [
        {
            "source_id": d["id"],
            "name": _safe_table_name(d.get("name") or d.get("original_filename") or d.get("filename") or d.get("id", "DATASET")),
            "pk": next(iter(_infer_pk_candidate(d.get("columns", [])) or d.get("columns", []) or ["id"])),
            "fk": [c for c in _infer_fk_candidates(d.get("columns", []))],
            "columns": d.get("columns", []),
        }
        for d in datasets
    ]

    assumed_normalization = [
        "Normalization assumed to be 3NF for visualization unless file metadata indicates otherwise.",
        "Relationships inferred purely from column names; constraints may vary.",
    ]

    entities_for_mermaid = []
    seen_names = set()
    for d in datasets:
        raw = d.get("name") or d.get("original_filename") or d.get("filename") or d.get("id", "DATASET")
        name = _safe_table_name(raw)
        if name in seen_names:
            suffix = 2
            base = name
            while f"{base}_{suffix}" in seen_names:
                suffix += 1
            name = f"{base}_{suffix}"
        seen_names.add(name)
        columns = list(dict.fromkeys(d.get("columns") or []))
        pk = _infer_pk_candidate(columns) or (columns[0] if columns else "ID")
        fk_cols = _infer_fk_candidates(columns)
        entities_for_mermaid.append({
            "id": name,
            "name": raw,
            "source_id": d.get("id"),
            "pk": pk,
            "fk": fk_cols,
            "columns": columns,
        })

    name_by_id = {e.get("source_id"): e.get("id") for e in entities_for_mermaid if e.get("source_id")}

    mermaid_lines = ["erDiagram"]
    for entity in entities_for_mermaid:
        mermaid_lines.append("")
        mermaid_lines.append(f"    {entity['id']} {{")
        for col in entity.get("columns") or []:
            mermaid_lines.append(f"        {_escape(str(col))}")
        mermaid_lines.append("    }")

    mermaid_lines.append("")
    seen_pairs = set()
    for rel in relations[:50]:
        src_id = name_by_id.get(rel.get("src") or "")
        dst_id = name_by_id.get(rel.get("dst") or "")
        if not src_id or not dst_id or src_id == dst_id:
            continue
        pair = (src_id, dst_id)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        rel_label = rel.get("label") or "related"
        if rel_label in ("contains", "involves"):
            sym = "||--o{"
        elif rel_label in ("placed_by", "belongs_to"):
            sym = "o|--||"
        elif rel_label == "assigned_to":
            sym = "||--o|"
        else:
            sym = "||--o{"
        mermaid_lines.append(f"    {src_id} {sym} {dst_id} : \"{_escape(str(rel_label))}\"")

    mermaid_diagram = "\n".join(mermaid_lines).strip() + "\n"
    payload = {
        "investigation_id": investigation_id,
        "datasets": datasets,
        "relations": relations,
        "summary": f"{len(datasets)} datasets, {len(relations)} relations",
        "assumptions": assumed_normalization,
        "entity_summary": entity_summary,
        "normalization": "3NF",
        "mermaid_er": mermaid_diagram,
    }
    return _ok(payload)


def _infer_fk_candidates(columns: list[str]) -> list[str]:
    return [c for c in columns if (c.lower().strip() not in ("id",)) and
            (re.match(r"^\w+_(id|uuid)$", c.lower().strip()))]


