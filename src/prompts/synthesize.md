# Synthesis prompt — answer from rows

Question: {question}
SQL: {sql}
Row count returned: {row_count}
Row count available: {row_count_available}
Rows sample (JSON array, first {sample_rows} rows): {rows_sample}
Chart type: {chart_type}

Write a concise plain-English answer with cited numbers. If the result is a sample, say so.
If multiple files were used, mention which tables contributed.
Include up to 3 follow-up suggestions.