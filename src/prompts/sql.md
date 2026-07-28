# SQL generation prompt

Source: {source}
Schema/columns:
{schema}
{relationships}

Question: {question}
Row limit: {row_limit}

Rules:
- Output one SQL statement only. No explanations.
- Use only the exact table names and exact column names listed above. Do not invent new columns or normalize names across files.
- Use explicit columns when meaningful.
- Use LIMIT only. Do not use TOP. Do not use stacked queries.
- Prefer explicit JOINs with table aliases when multiple tables are attached.

Return SQL only.