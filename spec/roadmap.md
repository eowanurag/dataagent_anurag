# Roadmap

> **Assumed:** production-grade, full audit trail, RBAC by rank/unit, on-premises-first.

---

## What This Agent Does

A data analyst assistant for UP Police that lets analysts upload CSV exports and/or connect
to a live MsSQL analytical database, then ask analytical questions in plain English. The
agent plans each question, builds/sanitises SQL when needed over the dataset, executes safely,
and returns a cited answer with optional charts, follow-ups, and an audit log of every
query asked. Complex investigations are threaded across turns with preserved history.

## Who Uses It

Police analysts, investigators, and officers with rank/unit-based access who need fast
answers from criminal, traffic, or administrative datasets without writing SQL or leaving
audit gaps.

## Core Problem Being Solved

Analysts manually export CSVs, open them in Excel/Power BI, and rebuild similar filters
many times a day. Large MsSQL analytical databases are sensitive; ad-hoc queries and full
data dumps risk load spikes and unaudited access. This agent provides a governed,
question-first interface with complete audit trail and live-DB minimisation built in.

## Success Criteria

- [ ] An analyst uploads a CSV and gets a real cited answer to a natural-language question
- [ ] The agent produces charts and follow-up suggestions when relevant
- [ ] A full investigation thread is preserved across 5+ follow-up questions
- [ ] Every SQL/stat query and its result is recorded in an audit log
- [ ] Role/unit-based access is enforced on uploads, investigations, and live DB access
- [ ] Against a large live MsSQL source, the agent produces answers without fan-out full-table
  reads or unbounded `SELECT *` queries

## What This Agent Does NOT Do (Out of Scope)

- Execute writes, DDL, or stored procedures on the live MsSQL
- Replace structured BI dashboards; it supplements ad-hoc questions
- Train models on police data or perform predictive scoring
- Expose row-level security modelled after MsSQL's own permissions; it adds an application
  layer on top

## Key Constraints

- On-prem / air-gapped-first design; no third-party data exfil
- Read-only access to live MsSQL; no write operations ever
- Full audit trail for every analytics query executed
- Latency-conscious against large tables (hundreds of thousands to millions of rows)
- RBAC by rank/unit on every query and investigation
- End-to-end encryption at application layer where required

---

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** It must work the first
> time the user tests it — zero rough edges on the tested path. Its frontend is visually
> complete: real UI for the one working path PLUS clearly-labelled NON-FUNCTIONAL stubs for
> everything coming later.

### Phase 1 — CSV Chat MVP

- **Goal:** One real end-to-end flow: upload CSV → ask a plain-English question →
  receive a cited answer with optional chart; investigation persists in session.
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — RBAC + file ingestion + schema acquisition artefacts + chat-history
    persistence (SQLite); deps: none
  - `slice-b` (backend) — LangGraph ReAct agent with tool-use nodes: plan question, generate
    SQL via LLM, execute via SQLite/pandas, render textual answer; deps: none
  - `slice-c` (frontend) — Replace `/app` with investigation UI: upload, chat, results,
    history sidebar; deps: none
- **Key surfaces / files:**
  - `src/api/`, `src/db/`, `src/graph/nodes.py`, `src/prompts/`, `src/llm/`, `src/tools/`
  - `frontend/public/index.html`, `frontend/public/app.js`, `frontend/public/styles.css`
- **Gate command:** `uv run pytest tests -q && uv run pytest tests/integration -q`
- **How the user tests it (handoff seed):**
  - `cp .env.example .env`; set `AGENT_OPENROUTER_API_KEY`; run `uv run python -m src`
  - Open `http://localhost:8001/app/`
  - Log in via RBAC form (demo credentials); upload a CSV; ask "Show top 5 districts by
    count"; expect a table + chart + cited numbers. History appears in sidebar.

### Phase 2 — Investigations + Outputs

- **Goal:** Cross-session investigations with full chat history, downloadable reports
  (CSV / PDF), and chart gallery.
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — investigation threading model + PDF export via HTML-to-PDF; deps: Phase 1
  - `slice-b` (backend) — CSV export + follow-up suggestion engine; deps: Phase 1
  - `slice-c` (frontend) — chart renderer, history browser, export buttons; deps: Phase 1
- **Key surfaces / files:** upgrades to `src/graph/`, `src/api/`, `src/db/models.py`,
  `frontend/public/`
- **Gate command:** `uv run pytest tests -q`
- **How the user tests it:**
  - Reopen a saved investigation; ask a follow-up; chart updates; export CSV + PDF from UI;
  audit log shows both export events.

### Phase 4 — Multi-Model + Auto Charts

- **Goal:** Enable real multi-model selection and automatic chart output from query results.
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — model registry + `/models` endpoint + candidate model metadata; deps: Phase 1
  - `slice-b` (backend) — explore-phase execution across candidate models with winner selection + audit metadata; deps: Phase 1
  - `slice-c` (backend + frontend) — structured `chart_spec` generation and canvas chart renderer; deps: Phase 1
- **Key surfaces / files:** `src/llm/registry.py`, `src/api/models.py`, `src/api/charts.py`, `src/graph/explore.py`, `frontend/public/app.js`, `tests/unit/test_models.py`, `tests/unit/test_graph_charts.py`
- **Gate command:** `uv run pytest tests/unit -q`
- **How the user tests it:**
  - Open `/app`; confirm the left-panel model dropdown is populated from `/models`
  - Upload CSV, ask a question, and confirm the answer includes a rendered chart when results support it

### Phase 5 — Live MsSQL Integration

- **Goal:** Add a live MsSQL analytical source as a queryable data source with protections:
- **Independent slices (parallel build units):**
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — read-only MsSQL driver integration, schema introspection, SQL
    sanitisation layer, query budget + safety checks; deps: Phase 2
  - `slice-b` (backend) — agent routing between CSV/PDB and MsSQL; cost/latency-aware tool
    selection; deps: Phase 2
  - `slice-c` (frontend) — source switcher, live-DB status indicator, query audit viewer;
    deps: Phase 2
- **Key surfaces / files:** new `src/db/repositories/`, `src/graph/tools/ms_sql_tool.py`,
  `src/api/sources.py`, `spec/architecture.md` updated
- **Gate command:** `uv run pytest tests -q`
- **How the user tests it:**
  - Add MsSQL connection string in `.env`; approve schema; ask "Compare FIR counts by
    district for last quarter"; expect answer + row-count filter + audit log entry with SQL.
  Confirm no DDML passes sanitisation.

