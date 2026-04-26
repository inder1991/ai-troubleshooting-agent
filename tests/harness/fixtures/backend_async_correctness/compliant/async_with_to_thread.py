"""Q7 compliant — CPU-bound work delegated to to_thread."""
import asyncio
import time

def cpu_bound(n: int) -> int:
    time.sleep(0.01)  # OK: this is sync def, not async def
    return n * n

async def runner() -> int:
    return await asyncio.to_thread(cpu_bound, 5)
