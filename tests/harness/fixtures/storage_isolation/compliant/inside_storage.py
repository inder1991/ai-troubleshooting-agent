"""Storage isolation compliant — execute inside storage/ module.

Pretend-path: backend/src/storage/gateway.py
"""
def query(session) -> None:
    session.execute("SELECT 1")
