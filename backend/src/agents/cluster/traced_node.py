"""@traced_node decorator: timeout enforcement, failure classification, execution tracing."""

from __future__ import annotations

import asyncio
import time
import functools
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field
from src.agents.cluster.state import FailureReason
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NodeExecution(BaseModel):
    node_name: str
    status: str = "PENDING"
    duration_ms: int = 0
    failure_reason: Optional[FailureReason] = None
    failure_detail: str = ""
    token_usage: int = 0
    input_summary: str = ""
    output_summary: str = ""


def traced_node(timeout_seconds: float = 60):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(state: dict, config: dict | None = None) -> dict:
            node_name = func.__name__
            start = time.monotonic()
            trace = NodeExecution(node_name=node_name, status="RUNNING")
            try:
                result = await asyncio.wait_for(func(state, config or {}), timeout=timeout_seconds)
                elapsed = int((time.monotonic() - start) * 1000)
                trace.status = "SUCCESS"
                trace.duration_ms = elapsed
                if isinstance(result, dict):
                    result["_trace"] = trace.model_dump(mode="json")
                return result
            except asyncio.TimeoutError:
                elapsed = int((time.monotonic() - start) * 1000)
                trace.status = "FAILED"
                trace.failure_reason = FailureReason.TIMEOUT
                trace.failure_detail = f"Timed out after {timeout_seconds}s"
                trace.duration_ms = elapsed
                logger.warning("Node timed out", extra={"node": node_name, "action": "timeout", "extra": f"{timeout_seconds}s"})
                return {"_trace": trace.model_dump(mode="json")}
            except Exception as e:
                elapsed = int((time.monotonic() - start) * 1000)
                trace.status = "FAILED"
                trace.failure_reason = FailureReason.EXCEPTION
                trace.failure_detail = str(e)
                trace.duration_ms = elapsed
                logger.error("Node failed", extra={"node": node_name, "action": "exception", "extra": str(e)})
                return {"_trace": trace.model_dump(mode="json")}
        return wrapper
    return decorator
