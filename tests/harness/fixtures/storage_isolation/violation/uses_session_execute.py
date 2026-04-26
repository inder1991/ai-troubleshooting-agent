"""Storage isolation violation — session.execute outside storage/.

Pretend-path: backend/src/api/admin.py
"""
def adhoc(session) -> None:
    session.execute("SELECT 1")
