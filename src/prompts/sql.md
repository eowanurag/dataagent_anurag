# SQL generation prompt

Source: {source}
Schema/columns:
{schema}
{relationships}

Question: {question}
Row limit: {row_limit}

Rules:
- Output one SQL statement only. No explanations.
- Use only the exact table names listed above. Do not invent new table names.
- Use only the exact column names listed for each table. Do not use columns from other tables even if they appear similar. Do not normalize, alias, or reuse column names across files.
- If a column is not listed for a table, do not reference it.
- Use explicit columns when meaningful.
- Use LIMIT only. Do not use TOP. Do not use LIMIT with OFFSET unless requested. Avoid nested SELECTs when possible.
- If multiple files/tables are attached and a cross-file query is needed, use explicit JOINs with table aliases only.
- No DDL/DML. No stacked queries. No system tables.

Return SQL only.
