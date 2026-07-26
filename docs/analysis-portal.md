# UP Police Data Analyst — Portal Analysis

## 1. Purpose
Single-page investigation portal for on-premises data analysis. Upload CSVs, run traced questions through an LLM-backed graph, inspect schema/ER assets, and export results. No auth/RBAC layer.

## 2. UI Layout

### 2.1 Top navigation
- Brand: `UP Police — Data Analyst`
- Operator badge: `Operator: demo-user`
- Provider badge: `Backend ready · <provider> · <model>`
- API link: `/docs`

### 2.2 Sidebar (left)
- **Navigation cards**
  - Analysis file
  - Ask
  - History
  - Audit
  - Live source
- **Model & usage panel**
  - Current provider / model display
  - Model dropdown
  - Provider dropdown
  - Apply model button
  - Last query In / Out
  - Today In / Out / Queries
  - Context window used / total
  - Datasets · Rows
  - Cost estimate
  - Error/toast area

### 2.3 Main content (center stack)
- **New data analysis file**
  - Title input
  - Create / rename file
  - Export CSV / Export PDF buttons
- **Ask a question**
  - Source selector: `CSV` / `Live DB`
  - Question input
  - Ask button
  - Status indicator
  - Answer block with citations, follow-ups, chart, meta
- **History**
  - Collapsible history turns with file previews and action buttons
- **Audit log**
  - Append-only event summary/list
- **Live source**
  - Connection status, details, refresh button

### 2.4 Right panels
- **Files**
  - Drop zone / file picker for multiple CSVs
  - Upload button, pending file cards with remove buttons
  - Validation and toast notifications
  - File preview modal
- **Data assets**
  - Dataset list with columns, row counts, sizes
  - Inline Mermaid ER diagram
  - Maximize/Restore overlay for ER diagram
  - ER assumptions and entity summary

## 3. Backend Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Status + effective provider/model |
| GET | `/models` | Model registry with deduplication |
| GET | `/settings` | User settings from SQLite store |
| POST | `/settings/provider-model` | Persist provider + model |
| POST | `/settings/cost-rates` | Persist per-model cost rates |
| DELETE | `/settings/cost-rates` | Reset cost rates |
| POST | `/investigations` | Create investigation |
| GET | `/investigations/{id}` | Fetch investigation |
| POST | `/investigations/{id}/files` | Upload CSV attachment |
| GET | `/investigations/{id}/files` | List files |
| POST | `/investigations/{id}/runs` | Run question through graph |
| GET | `/investigations/{id}/history` | Chat history |
| GET | `/investigations/{id}/assets/er` | ER diagram payload |
| GET | `/investigations/{id}/export/csv` | Export investigation CSV |
| POST | `/investigations/{id}/export/pdf` | Export investigation PDF |
| GET/POST | `/runs` | Legacy run endpoints |

## 4. Graph Workflow

```
classify_source
  ├─ build_temp_schema   (multi-file only)
  │     └─ plan
  ├─ transform_text      (non-CSV sources)
  │     └─ finalize
  └─ plan                (single CSV)
        ├─ generate_sql
        │     ├─ validate_sql
        │     │     └─ execute_query
        │     │           ├─ synthesize_answer
        │     │           │     └─ finalize
        │     │           └─ handle_error
        │     └─ handle_error
        └─ handle_error
```

### 4.1 Node responsibilities
- **classify_source** — route by source type and file presence
- **build_temp_schema** — inspect uploaded CSVs, infer temp schema + relationships for multi-file analysis
- **plan** — generate plan text from prompts
- **generate_sql** — produce SQL from plan, schema, and question; strip code fences and trailing semicolons
- **validate_sql** — forbid dangerous tokens; allow exactly one `JOIN ... AS ...` + `ON` for multi-file queries; forbid joins for single-file
- **execute_query** — run SQL against SQLite temp DB (single or multi-attach)
- **synthesize_answer** — turn rows + SQL into answer text, chart spec, citations, follow-ups
- **finalize** — mark run completed
- **handle_error** — record audit and surface error message

### 4.2 State model
`AgentState` carries:
- identification: `run_id`, `investigation_id`, `user_id`
- inputs: `source`, `question`, `file_id`, `file_ids`, `temp_schema`
- artifacts: `plan`, `sql`, `sql_rows`, `sql_row_count`, `chart_spec`
- outputs: `answer_text`, `citations`, `followup_suggestions`
- control: `status`, `checkpoint`, `provider`, `model`
- usage: `usage`, `chart_type`, `chart_x`, `chart_y`

## 5. Data Flow

### 5.1 Ask flow
1. Frontend sends `POST /investigations/{id}/runs` with `question` and optional `file_ids`
2. API validates investigation exists and has files
3. API creates `RunRow` with persisted provider/model
4. Graph seeds `file_ids` and `temp_schema` into initial state
5. For multi-file runs: `build_temp_schema` inspects files and infers relationships
6. LLM generates SQL from plan + schema + question
7. Validator enforces safe SQL and multi-file JOIN rules
8. SQL executed against in-memory SQLite with stable table names
9. Synthesizer builds answer, chart spec, citations, follow-ups
10. API returns run payload with provider/model, SQL, rows, and status
11. Frontend appends turn to history and renders chart/answer

### 5.2 Model switching flow
1. User selects provider/model in sidebar
2. Apply button calls `POST /settings/provider-model`
3. Backend persists to SQLite `settings_store`
4. `/health` reads store first, then env fallback
5. `create_llm_provider()` reads store first, then env fallback
6. Investigation runs emit store-backed provider/model in response and `RunRow`

### 5.3 File/assets flow
1. User selects/drops CSVs in Files panel
2. `POST /investigations/{id}/files` stores attachment and metadata
3. Data assets panel loads `/investigations/{id}/assets/er`
4. Backend infers schema, PK/FK candidates, relationships
5. Frontend renders inline Mermaid ER and overlay viewer

### 5.4 Export flow
1. User clicks Export CSV or Export PDF
2. Backend loads history and file metadata from DB
3. CSV: writes flat export with sections for files and messages
4. PDF: builds ReportLab document with text and optional chart images
5. Audit event recorded for each export

## 6. Storage Model
- **SQLite** via SQLAlchemy ORM
- Tables: `investigations`, `investigation_files`, `chat_messages`, `audit_events`, `runs`, `settings_store`
- All raw DDL/queries wrapped with `sql_text()`
- File attachments stored outside DB via `write_attachment` / `read_attachment`
- `settings_store` is a single-row key/value store for provider/model/cost rates

## 7. LLM Provider Model
- Supported providers: `openrouter`, `nvidia`, `anthropic`, `gemini`
- Provider resolution order: persisted `settings_store` → `.env` resolved provider
- Model normalization via `MODEL_ALIASES` per provider
- Token/cost tracking attached to run metadata
- Retry/backoff wrapper for transient HTTP errors
- Rate limiter for concurrency-bound free-tier providers

## 8. Frontend Behavior
- Vanilla JS in `frontend/public/app.js`
- Session restore from localStorage
- File validation with size/type checks and toast notifications
- Collapsible history turns with file previews and action buttons
- Chart rendering via canvas (bar, line, pie, table)
- Mermaid ER diagram with maximize/minimize overlay
- No auth/RBAC; operator identity is static `demo-user`

## 9. Non-Goals / Deferred
- Live MSSQL connection present in UI but not implemented in backend
- Auth/RBAC layer removed per on-prem/no-auth constraint
- Multi-user isolation not implemented
