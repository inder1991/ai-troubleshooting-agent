"""Q8 violation — raw SELECT in non-analytics file with no justification."""

def report() -> str:
    return "SELECT id, name FROM customers WHERE deleted_at IS NULL"
