# Planning prompt — investigation analysis

Context:
- Investigation ID: {investigation_id}
- Source: {source}
- Attached files: {files}
- Schema summary:
{schema}
- Question: {question}

Create a 3-step plan:
1. Confirm which files/tables to use and whether a cross-file join is required.
2. Draft one safe SELECT query with row limit; if joining, use explicit table aliases.
3. Shape the result for a concise answer with citations.

Do not return SQL in this step. Return numbered plan steps only.
