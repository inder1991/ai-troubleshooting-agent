"""Q11 violation — spine file imports an off-list dep.

Pretend-path: backend/src/api/routes_v4.py
"""
import some_unlisted_pkg

def handler() -> None:
    some_unlisted_pkg.do()
