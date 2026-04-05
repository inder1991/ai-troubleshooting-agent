"""@traced_node decorator: timeout enforcement, failure classification, execution tracing."""

import asyncio
import time
import functools
from typing import Any, Callable, Optional

from langchain_core.runnables import RunnableConfig

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


def _build_error_report(domain: str, trace: NodeExecution) -> dict:
    """Build a minimal DomainReport dict for a failed agent node."""
    return {
        "domain": domain,
        "status": "FAILED",
        "failure_reason": trace.failure_reason.value if trace.failure_reason else "EXCEPTION",
        "confidence": 0,
        "anomalies": [],
        "ruled_out": [],
        "evidence_refs": [],
        "data_gathered_before_failure": [],
        "token_usage": 0,
        "duration_ms": trace.duration_ms,
    }


_NODE_DEFAULT_OUTPUTS = {
    "signal_normalizer": {"normalized_signals": []},
    "failure_pattern_matcher": {"pattern_matches": []},
    "temporal_analyzer": {"temporal_analysis": {}},
    "diagnostic_graph_builder": {"diagnostic_graph": {"nodes": {}, "edges": []}},
    "issue_lifecycle_classifier": {"diagnostic_issues": []},
    "hypothesis_engine": {"ranked_hypotheses": [], "hypotheses_by_issue": {}, "hypothesis_selection": {"root_causes": [], "selection_method": "timeout", "llm_reasoning_needed": False}},
    "critic_validator": {"critic_result": {"validations": [], "dropped_hypotheses": [], "weakened_hypotheses": [], "warnings": []}},
    "solution_validator": {},
}

_AGENT_NODE_NAMES = frozenset({"node_agent", "ctrl_plane_agent", "network_agent", "storage_agent", "rbac_agent"})


def traced_node(timeout_seconds: float = 60):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(state: dict, config: RunnableConfig | None = None) -> dict:
            node_name = func.__name__
            is_agent_node = node_name in _AGENT_NODE_NAMES
            start = time.monotonic()
            trace = NodeExecution(node_name=node_name, status="RUNNING")
            logger.debug("Node %s starting (timeout=%ss)", node_name, timeout_seconds,
                         extra={"action": "node_start", "extra": {"node": node_name}})

            try:
                result = await asyncio.wait_for(func(state, config or {}), timeout=timeout_seconds)
                elapsed = int((time.monotonic() - start) * 1000)
                trace.status = "SUCCESS"
                trace.duration_ms = elapsed

                logger.info("Node %s completed successfully in %dms", node_name, elapsed,
                            extra={"action": "node_success", "duration_ms": elapsed, "extra": {"node": node_name}})

                if isinstance(result, dict):
                    result["_trace"] = [trace.model_dump(mode="json")]
                return result
            except asyncio.TimeoutError:
                elapsed = int((time.monotonic() - start) * 1000)
                trace.status = "FAILED"
                trace.failure_reason = FailureReason.TIMEOUT
                trace.failure_detail = f"Timed out after {timeout_seconds}s"
                trace.duration_ms = elapsed
                logger.warning("Node timed out", extra={"node": node_name, "action": "timeout", "extra": f"{timeout_seconds}s"})
                if is_agent_node:
                    domain = node_name.replace("_agent", "")
                    error_result: dict[str, Any] = {"_trace": [trace.model_dump(mode="json")]}
                    error_result["domain_reports"] = [_build_error_report(domain, trace)]
                else:
                    defaults = _NODE_DEFAULT_OUTPUTS.get(node_name, {})
                    error_result = {**defaults, "_trace": [trace.model_dump(mode="json")]}
                return error_result
            except Exception as e:
                elapsed = int((time.monotonic() - start) * 1000)
                trace.status = "FAILED"
                trace.failure_reason = FailureReason.EXCEPTION
                trace.failure_detail = str(e)
                trace.duration_ms = elapsed
                logger.error("Node failed", extra={"node": node_name, "action": "exception", "extra": str(e)})
                if is_agent_node:
                    domain = node_name.replace("_agent", "")
                    error_result = {"_trace": [trace.model_dump(mode="json")]}
                    error_result["domain_reports"] = [_build_error_report(domain, trace)]
                else:
                    defaults = _NODE_DEFAULT_OUTPUTS.get(node_name, {})
                    error_result = {**defaults, "_trace": [trace.model_dump(mode="json")]}
                return error_result
        return wrapper
    return decorator
