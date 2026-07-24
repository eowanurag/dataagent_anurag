# Phase-1 Plus — Multi-Model + Auto Chart Extension

## Goal
Enable real multi-model usability and automatic chart output while preserving the
existing single-model execution model.

## Workstream

### MDX Implementation Steps

1. **Model registry surface**
   - Add `src/llm/registry.py`: `ModelRegistry` with model metadata.
   - Add `src/api/models.py`: `/models` endpoint returning selectable candidates.
   - Add `frontend/public/app.js`: populate model dropdown from `/models`.
   - Add chart-spec type registry and renderer mapping.

2. **Candidate selection**
   - Add candidate sets per authorized context in config layer.
   - Implement explore-phase fan-out over candidate models.
   - Log `run_id`, `model`, `provider`, `latency_ms`, `tokens_in`, `tokens_out`, `cost`.

3. **Explore-phase lifecycle**
   - Save run state to database until all candidate models complete.
   - Annotate results with metadata from model layer.
   - Choose the best result using annotations/composite scores and security audit.

4. **Chart augmentation**
   - Shape chart spec in backend (`synthesize_answer` or dedicated node).
   - Frontend renders bar, line, pie, or table based on `chart_spec`.
   - Table fallback when chart type isn't available.

## Anchor Points
- **Registry file:** `src/config/models/registry.json` write-back only if changed; read-only otherwise.
- **Sibling file sampler:** `chart_spec` should attach to the model chosen for the run.
- **Auth guard:** never add auth into direct registry accesses.
