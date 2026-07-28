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
- If multiple tables are attached and a cross-file question is asked, JOIN only on exact common columns listed in the schema.
- Use JOIN clauses in the form `... JOIN ... AS alias ON alias.common_column = alias2.common_column`.
- Use LIMIT only. Do not use TOP. Do not use stacked queries.
- Do not join unrelated columns. If no common column exists, query each file separately and rely on synthesis instead of forcing a JOIN.

Return SQL only.