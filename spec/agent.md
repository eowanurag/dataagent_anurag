# Agent

> Required because the project uses LangGraph.

---

## Agent Architecture Pattern

| Pattern | When to use |
|---------|-------------|
| **ReAct loop + tool use** | Multi-step analytical questions requiring real data access |

**Chosen:** ReAct loop with tool calling. The LLM answers plain-English questions by
planning, calling read-only data tools against CSV or MsSQL, validating, then synthesising
a cited answer. This pattern avoids op-list mapping and handles arbitrary analytical questions
safely.

**Also used:** Memory Management (conversation history within an investigation) and
Guardrails / Safety Patterns (SQL sanitisation, row budgets, RBAC checks before every tool
call).

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|--------------|----------|----------|-----------|
| All nodes | OpenRouter | env-configured (`AGENT_LLM_MODEL`) | User-selected; default low-latency instruct-capable model |
| SQL generation sub-step | OpenRouter | same model | One batched call to generate SQL; validate deterministically |

> **Assumed:** Use a model that reliably emits structured SQL and follows safety rules in
> one pass (e.g., an OpenRouter instruct-capable model).

**Fallback behaviour:** On 401/404/429, surface actionable error to the UI and allow retry.
On repeated failure, surface "LLM generation unavailable" without exposing provider credentials.
A fallback provider could be added later; Phase 1 uses a single configured key.

**Prompt strategy:** Split prompts into system scaffold + per-node instructions. The planning
and SQL nodes each get one batched call per turn; loop control is wired via LangGraph state,
not by LLM restructuring.

---

## Tools & Tool Calling

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `classify_source` | Choose CSV vs MsSQL based on question + session state | question text, investigation summary | source tag | none |
| `list_attached_files` | Return schemas/samples of uploaded CSVs for this investigation | investigation id | schema summary | none |
| `csv_query` | Execute a SQL query against the per-investigation CSV SQLite/duckdb store | sql, row_limit | rows + sql | log to audit |
| `schema_introspect` | Inspect tables/columns for the chosen MsSQL schema | schema allow-list | columns/types/samples | none |
| `ms_sql_query` | Execute a read-only, sanitised SQL query against MsSQL; enforce row budget | sql, max_rows, schema | rows + sql | log to audit |
| `render_chart` | Encode chart spec from result set for the frontend renderer | result rows, question | chart spec | none |
| `suggest_followups` | Generate ranked follow-up questions | question, answer, schema | follow-up bullets | none |

**Tool selection strategy:** The LLM plans and selects tools via LangGraph tool-binding. The
graph enforces a read-only classifier before any DB tool returns rows.

**Tool failure handling:** Tool errors set `state["error"]`; graph routes to `handle_error`
which returns a structured message + persists the failed audit record.

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    run_id: str                          # set at initialisation
    investigation_id: str                # user session / investigation
    user_id: str                         # authenticated user (rank+unit)
    source: str | None                   # "csv" | "mssql"
    question: str                        # current user question
    plan: str | None                     # generated plan
    sql: str | None                      # generated SQL for chosen source
    sql_rows: list[dict] | None          # executed rows
    sql_row_count: int | None            # total available rows (before limit)
    chart_spec: dict | None              # Chart.js-compatible spec
    followup_suggestions: list[str] | None
    answer_text: str | None              # final textual answer
    citations: list[str] | None          # table/view/source(s) referenced
    error: str | None                    # fatal error message
    status: str | None                   # completed | failed
    checkpoint: str | None               # last completed node
```

---

## Nodes / Steps

### `node_classify_source`

**Reads from state:** `question`, `investigation_id`

**Writes to state:** `source`

**LLM call:** No.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| App DB | lookup attached files/live source config | fatal (set error) |

**Behaviour:** Pick CSV when files are attached and the question refers to them; pick MsSQL
when explicitly requested or when no CSV context is available and live source is enabled.

---

### `node_plan`

**Reads from state:** `source`, `question`, `plan_context`

**Writes to state:** `plan`

**LLM call:** Yes — planning prompt summarising available schemas and the user question.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| App DB | schema/lookup for attached CSV / live source | retry once, then abort |

**Behaviour:** Produce a 3–6 step plan: confirm schema location → draft SQL → validate -> shape → answer. Never fan out to full-table reads here.

---

### `node_generate_sql`

**Reads from state:** `plan`, `source`, `schemas`

**Writes to state:** `sql`, `citations`

**LLM call:** Yes — SQL generation prompt constrained by schema + guardrails.

**External calls:** none

**Behaviour:** Emit one SQL statement aligned to the chosen source. Include explicit column
references, row limit, and avoid `SELECT *`. Reject write/DDL. If generation fails, set
`error` and route to `handle_error`.

---

### `node_validate_sql`

**Reads from state:** `sql`, `source`

**Writes to state:** `sql` (passed through) or `error`

**LLM call:** No.

**External calls:** none

**Behaviour:** Rule-based safety check: no DDL/DML, no stacked queries, no system tables
unless allow-listed, row budget enforced by wrapping SQL with `TOP`/`LIMIT`. Any violation
sets `error` and prevents execution.

---

### `node_execute_query`

**Reads from state:** `sql`, `source`, `user_id`, `investigation_id`

**Writes to state:** `sql_rows`, `sql_row_count`, `citations`

**LLM call:** No.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| CSV store | run query | partial (log + return "query failed") |
| MsSQL | run query (read-only role) | partial (log + return "source unavailable") |

**Behaviour:** Execute within budget. For MsSQL, capture execution plan when cheap. Always
append an audit record with user, investigation, sql, row count, latency.

---

### `node_synthesize_answer`

**Reads from state:** `sql_rows`, `question`, `source`, `citations`

**Writes to state:** `answer_text`, `chart_spec`

**LLM call:** Yes — answer prompt receives rows summary + question + citations.

**External calls:** none

**Behaviour:** Produce a concise plain-English answer with cited numbers. Do not invent rows.
Flag if result looks like a sample rather than the full population. Suggest follow-ups.

---

### `node_handle_error`

**Reads from state:** `error`, `run_id`, `investigation_id`

**Writes to state:** `status` = "failed"

**Behaviour:** Surface a structured error message with recommended action. Persist failure in
audit log.

---

## Graph / Flow Topology

```
START
  │
  ▼
node_classify_source ──(error)──► node_handle_error ──► END
  │
  ▼
node_plan ──(error)──► node_handle_error ──► END
  │
  ▼
node_generate_sql ──(error)──► node_handle_error ──► END
  │
  ▼
node_validate_sql ──(invalid)──► node_handle_error ──► END
  │
  ▼
node_execute_query ──(error)──► node_handle_error ──► END
  │
  ▼
node_synthesize_answer ──(error)──► node_handle_error ──► END
  │
  ▼
END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `node_classify_source` | `state["error"] is not None` | `node_handle_error` |
| `node_plan` | `state["error"] is not None` | `node_handle_error` |
| `node_generate_sql` | `state["error"] is not None` | `node_handle_error` |
| `node_validate_sql` | sql invalid | `node_handle_error` |
| `node_execute_query` | `state["error"] is not None` | `node_handle_error` |
| `node_synthesize_answer` | `state["error"] is not None` | `node_handle_error` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph state | Plan, SQL, rows, answer, chart spec |
| **Within an investigation** | App DB (chat_history) | Full Q&A pairs, selected SQL, row counts, follow-ups |
| **Across investigations** | App DB (investigation metadata) | Attached files, live source config, user+unit tag |

**Context window management:** Summarise long chat histories when they exceed a summary
threshold; keep raw rows only for the current turn. The audit log persists full SQL and row
counts outside the prompt.

## Human-in-the-Loop Checkpoints

| Checkpoint | What is shown to the user | Expected user action | Timeout / default |
|------------|---------------------------|----------------------|-------------------|
| **Source selection** | "This question seems to target the live DB. Proceed?" | Approve / switch to CSV | Auto-classify if unambiguous |
| **High-cost query** | "MsSQL query touches >500K rows. Approve?" | Approve / modify / cancel | Block until action |
| **Answer attribution** | Cited sources + row counts | Accept / ask follow-up | n/a |

---

## Error Handling & Recovery

- **Node-level:** Each node catches its own exceptions; fatal errors set `state["error"]`.
- **Graph-level (`node_handle_error`):**
  - Reads: `state["error"]`, `run_id`, `investigation_id`
  - Updates: `status = "failed"`, error message, audit record
  - Logs error with `run_id` + `investigation_id`
  - Terminates graph
- **Resume / retry strategy:** Retry transient 429/5xx at the API/proxy layer; the graph
  itself is not checkpointed across retries in Phase 1.
- **Partial failure:** If CSV is available but MsSQL is down, fall back to CSV and flag the
  degraded mode in the answer.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One trace per run, one span per node | Structured stdout log |
| **LLM calls** | Prompt tokens, completion tokens, latency, model | Structured log |
| **Tool calls** | Tool name, inputs, success/error, latency | Structured log + audit DB |
| **Run outcome** | Status, total duration, error if any | DB + structured log |
| **SQL audit** | Full SQL, source, row counts, user, unit, investigation | App DB |

---

## Concurrency Model

- **Run isolation:** One user can own many investigations; an investigation can queue
  multiple runs. Never run the same investigation concurrently; queue with `status = "queued"`.
- **Parallel nodes within a run:** Where safe, planning and follow-up suggestion generation
  may fan out; the main execution path stays serial until results exist.
- **Checkpointing:** SQLiteSaver is sufficient in Phase 1; PostgresSaver if using PostgreSQL
  app DB in production.

---

## Graph Assembly (`src/graph/agent.py`) *(plan shape — adapt to actual files changed)*

```python
from langgraph.graph import END, StateGraph

from src.graph.state import AgentState
from src.graph.nodes import (
    classify_source,
    plan,
    generate_sql,
    validate_sql,
    execute_query,
    synthesize_answer,
    handle_error,
)

compiled_graph = (
    StateGraph(AgentState)
    .add_node("classify_source", classify_source)
    .add_node("plan", plan)
    .add_node("generate_sql", generate_sql)
    .add_node("validate_sql", validate_sql)
    .add_node("execute_query", execute_query)
    .add_node("synthesize_answer", synthesize_answer)
    .add_node("handle_error", handle_error)
    .set_entry_point("classify_source")
    .add_conditional_edges("classify_source", route_on_error, {"next": "plan", "error": "handle_error"})
    .add_conditional_edges("plan", route_on_error, {"next": "generate_sql", "error": "handle_error"})
    .add_conditional_edges("generate_sql", route_on_error, {"next": "validate_sql", "error": "handle_error"})
    .add_edge("validate_sql", "execute_query")  # invalid SQL handled by node directly
    .add_conditional_edges("execute_query", route_on_error, {"next": "synthesize_answer", "error": "handle_error"})
    .add_conditional_edges("synthesize_answer", route_on_error, {"next": END, "error": "handle_error"})
    .add_edge("handle_error", END)
    .compile()
)
```
