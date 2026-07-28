# UP Police Data Analyst — Hermes-Native Build

This repo is the **Hermes-native** implementation surface for the UP Police Data Analyst
agent. It started from the zero-shot SDD harness and is now a concrete FastAPI +
LangGraph service with a static frontend served at `/app`.

## What This Is

- **Backend**: FastAPI app in `src/` with a LangGraph agent for investigation runs,
  multi-file SQL over SQLite temp schemas, provider/model persistence, PDF export,
  and structured logging.
- **Frontend**: zero-build static UI in `frontend/public/` — `index.html`,
  `styles.css`, `app.js` — served by the backend at `/app`.
- **Tests**: pytest suites in `tests/unit/`. The targeted subset is the reliable
  verification path on this Windows host; the full suite can exceed the default
  timeout during live-key integration coverage.
- **Provider support**: OpenRouter-backed models via `.env`. Provider/model selection
  is persisted through the backend settings store and reflected in `/health`.

## How to Run

```bash
# from repo root
uv sync
cp .env.example .env      # set OpenRouter key + model preference
```

### Verify setup

```bash
uv run python agent.py
```

### Start the server

```bash
uv run python agent.py --run
```

Default URL: `http://localhost:8001/app/`

Other useful endpoints:

- `http://localhost:8001/health`
- `http://localhost:8001/docs`

### Run tests

```bash
uv run pytest tests/unit -q
```

If the full suite times out on Windows, use the targeted subset used during
development:

```bash
uv run pytest tests/unit/test_graph.py tests/unit/test_investigations.py tests/unit/test_graph_charts.py tests/unit/test_pdf_export_repro.py -q
```

## Repo Layout

```
src/api/             ← FastAPI routes
src/graph/           ← LangGraph nodes/edges/state/runner
src/prompts/         ← prompt templates
frontend/public/     ← static UI
tests/unit/          ← pytest suites
.env.example         ← provider/model config template
```

## Session Workflow Notes

- This repo is meant to be driven from a Hermes root session.
- The root owns git/PR, server lifecycle, and live verification.
- Within a phase, delegate or inline specialist work, then verify with real tests.
- Prefer root-cause fixes and explicit Windows/async boundary handling.
