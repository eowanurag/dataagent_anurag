# Phase 1 — UP Police Data Analyst

## Summary
Implements the Phase-1 MVP for an on-premises-first data analyst agent for UP Police. This slices in a FastAPI + LangGraph backend, zero-build static frontend, CSV-only investigation workflow, and the minimal operational surface needed for first-time-right testing.

## What’s included
- **Investigations API**: create investigations, upload CSV attachments, run questions, chat history, exports/responses
- **LangGraph agent slice**: classify → plan → SQL → validate → execute → synthesize ReAct loop with OpenRouter provider support
- **CSV tooling**: schema inspection and read-only SQL execution over uploaded CSVs via SQLite in-memory execution with row budget enforcement (`AGENT_MAX_QUERY_ROWS`, default 5000)
- **Audit + storage**: append-only audit logging, local file attachment storage, run/message persistence
- **Frontend**: static `frontend/public/` UI served at `/app` — investigation creation, CSV upload, Q&A, history/run list, loading and error states
- **Tests**: unit coverage for graph compilation, investigations API, API frontend routing, settings/resolution, and graceful failure behavior without external keys

## Configuration
- Provider/model are configured via `.env` with `AGENT_` prefix
- Defaults: SQLite dev metadata DB, local storage root, provider auto-detection across Anthropic/Gemini/OpenRouter
- Without an LLM key configured, the run path fails gracefully with an actionable error instead of crashing

## Verification
- `pytest tests/unit -q --cache-clear` → **22 passed**
- Boot gate verified: server starts, `/health` responds, `/app` serves full UI
- Rendered browser smoke test completed against live server

## Deployment notes
- On-premises-first; no cloud-only dependencies introduced
- No external services required for dev/test beyond optional LLM provider credentials
- Frontend is zero-build static files; no Node/build step required

## Risks / follow-ups
- LLM-backed end-to-end completion path requires a real provider key in `.env`
- Live MsSQL read-only integration is explicitly deferred to Phase 3
