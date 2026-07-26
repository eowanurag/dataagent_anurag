# SQL generation prompt

Source: {source}
Schema/columns:
{schema}
Question: {question}
Row limit: {row_limit}

Rules:
- Output one SQL statement only. No explanations.
- Use explicit columns and ORDER BY when meaningful.
- Apply LIMIT or TOP to stay within the row limit.
- If multiple files/tables are attached and a cross-file query is needed, use explicit JOINs with table aliases only.
- No DDL/DML. No stacked queries. No system tables.

Return SQL only.
