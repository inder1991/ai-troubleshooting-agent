"""Q7 violation — time.sleep inside async def is a blocking syscall.

Use `await asyncio.sleep(...)` or `await asyncio.to_thread(time.sleep, ...)`.
"""
import time

async def slow() -> None:
    time.sleep(0.5)
