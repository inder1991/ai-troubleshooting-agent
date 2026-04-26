"""Q8 compliant — analytics file with raw SQL + justification comment.

Pretend-path: backend/src/storage/analytics.py
"""

# RAW-SQL-JUSTIFIED: aggregations cannot be expressed via SQLModel safely.

def cohort_sql() -> str:
    return "SELECT COUNT(*), strftime('%Y-%m', created_at) FROM incidents GROUP BY 2"
