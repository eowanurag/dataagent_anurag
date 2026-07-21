# Architecture

> **Assumed:** Python 3.11+ · FastAPI · LangGraph · SQLAlchemy 2.0 · SQLite local dev /
> PostgreSQL app metadata · MsSQL live source via ODBC (read-only for queries) ·
> pandas 2.x for data shaping · OpenRouter as LLM provider · zero-build static frontend.

---

## System Overview

This is a **data analyst agent** for UP Police. It lets authorised users upload CSV exports,
attach them to an investigation, ask plain-English analytical questions, and receive cited
answers with charts. The same agent correctly distinguishes a CSV context from a live MsSQL
analytical database and executes the safer, latency-aware path for each source. Activity on
both sources is logged for compliance and audit.

## Component Map

```
[Client / Browser]
     │
     ▼
[FastAPI API layer]     ← authz, file ingest, schema registry, audit log writes
     │
     ├─► [SQLite / PostgreSQL]  — app metadata, chat history, audit, file registry
     ├─► [CSV → DuckDB/SQLite memory] — ad-hoc per-investigation analysis
     └─► [MsSQL (read-only)]     — live analytical queries via safe SQL tooling
              │
              ▼
         [LLM / OpenRouter]  — planning → SQL generation → answer synthesis
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| **UI** | Investigations list; upload; structured question composer; answers with cited tables/charts; history sidebar |
| **API** | FastAPI routes: authz, file upload, investigations CRUD, analytics run, export (CSV/PDF), audit log, source registry |
| **Agent graph** | LangGraph loop: classify source → plan → tool use (SQL/CSV) → validate → answer |
| **Tools** | Pure functions: schema_introspect, sql_query (read-only, sanitised), csv_upload, export_csv, export_pdf |
| **Storage** | App metadata (PostgreSQLpreferred in prod; SQLite for local dev); DuckDB or SQLite temp store for CSV analytics; read-only MsSQL adapter |
| **Observability** | Structured request/response logging + audit log; latency per node |

## Data Flow

1. User logs in / is assigned a session tied to rank + unit.
2. User uploads one or more CSV files; the backend validates headers, samples rows, and
   stores them under an investigation. Source switches to CSV mode by default.
3. User asks a question; the agent classifies whether the question targets the CSV store
   or the live MsSQL source.
4. The agent plans steps: schema lookup → SQL generation against the chosen source →
   optional pandas shaping → chart encoding → textual answer.
5. Safe SQL is executed in a budgeted, read-only context; a row cap protects large tables.
6. The answer is returned with cited table references, optional charts, and follow-up suggestions.
7. Every question, chosen SQL, row count, latency, and result summary is persisted in the audit log.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| OpenRouter LLM API | Answer + SQL generation | Return actionable "LLM unavailable" error; allow user to retry |
| Local CSV store | Per-investigation analysis | Surface "CSV not attached"; retain chat history |
| Live MsSQL |oltage analytical queries | Return readonly-safe error; never degrade to write; never surface credentials |
| PostgreSQL | App metadata / audit / chat | Surface DB error; never lose audit payload (retry + write-ahead) |

## Stack

- **Language:** Python 3.11+
- **Framework:** LangGraph 0.2+ on FastAPI
- **LLM provider + model:** OpenRouter with env-configurable model; default as configured in
  `.env` (prefer a low-latency instruct-capable model for SQL tasks; override via env)
- **Backend:** FastAPI + Uvicorn, single-origin static frontend at `/app`
- **Database + ORM:** SQLAlchemy 2.0; SQLite local dev; PostgreSQL recommended for app
  metadata/audit in production; read-only MsSQL access via pyodbc/aioodbc
- **Frontend:** zero-build static files (`frontend/public/`): index.html + app.js + styles.css
- **Dependency management:** uv + pyproject.toml
- **Key library additions:** pandas 2.x, pyodbc (or aiodbc), duckdb optional for CSV
  analytics; Chart.js via CDN for charts

| Key library | Version | Purpose |
|-------------|---------|---------|
| langgraph | 0.2+ | Agent loop + state |
| fastapi | latest stable | API + static serving |
| sqlalchemy | 2.0+ | ORM + Alembic migrations |
| pandas | 2.x | CSV schema inference + shaping |
| pyodbc / aiodbc | latest stable | Read-only MsSQL queries |
| duckdb | optional | In-memory SQL analytics over CSV parquet exports if needed |
| openrouter | httpx-only (no SDK) | LLM calls per baseline provider layer |

**Avoid:** write access to live MsSQL from user questions; naive `SELECT *` on large tables;
stubbing the LLM gate in tests; chasing Docker or npm toolchains for the baseline UI.

## Deployment Model

On-premises server(s) inside the police network. FastAPI serves the web UI and API. The
MsSQL analytical database is owned by an existing system; this app connects read-only with
credentials stored in `.env` / a secrets manager — never logged in full. Scaling is vertical
initially; read replicas or materialised views on the DB side are the preferred mitigation
for large-table latency.
