"""Q7 violation — handler files must not invoke asyncio.run().

This file simulates living under backend/src/api/ — the check uses path
match (`api/` segment) to scope the rule.
"""
# pretend-path: backend/src/api/routes_v4.py
import asyncio

async def _do_work() -> None:
    pass

def handler() -> None:
    asyncio.run(_do_work())
