# Planning prompt — investigation analysis

Context:
- Investigation ID: {investigation_id}
- Source: {source}
- Attached files: {files}
- Question: {question}

Create a 3-step plan:
1. Confirm which file/table to use.
2. Draft one safe SELECT query with row limit.
3. Shape the result for a concise answer with citations.

Do not return SQL in this step. Return numbered plan steps only.
