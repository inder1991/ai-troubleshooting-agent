"""Execute tool calls against the Kubernetes cluster client."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Maximum result size per tool call (characters)
MAX_RESULT_SIZE = 8000


def _serialize_with_envelope(data: Any) -> str:
    """Serialize data into a TruncatedResult envelope. Always returns valid JSON."""
    if not isinstance(data, list):
        result = json.dumps(data, default=str)
        if len(result) > MAX_RESULT_SIZE:
            logger.info(
                "Dict result truncated: %d chars -> %d chars",
                len(result), MAX_RESULT_SIZE,
                extra={"action": "dict_truncated"},
            )
            return json.dumps({
                "data": str(data)[:MAX_RESULT_SIZE],
                "truncated": True,
                "truncation_reason": "DICT_SIZE_LIMIT",
                "original_size_chars": len(result),
            }, default=str)
        return result

    # Item-aware slicing for list results
    items: list = []
    total_size = 0
    for item in data:
        item_str = json.dumps(item, default=str)
        if total_size + len(item_str) > MAX_RESULT_SIZE:
            break
        items.append(item)
        total_size += len(item_str)

    truncated = len(items) < len(data)
    return json.dumps({
        "data": items,
        "total_available": len(data),
        "returned": len(items),
        "truncated": truncated,
        "truncation_reason": "SIZE_LIMIT" if truncated else None,
    }, default=str)


async def execute_tool_call(tool_name: str, tool_input: dict, cluster_client, tool_call_count: int = 0) -> str:
    """Execute a single tool call and return the result as a JSON string."""
    start = time.monotonic()
    logger.debug("Tool call: %s(%s)", tool_name, tool_input,
                 extra={"action": "tool_call_start", "extra": {"tool": tool_name}})
    try:
        if tool_name == "list_pods":
            result = await cluster_client.list_pods(namespace=tool_input.get("namespace", ""))
            data = result.data[:50]  # Cap at 50 pods per call
        elif tool_name == "describe_pod":
            # Use list_pods with specific name filter
            ns = tool_input.get("namespace", "")
            name = tool_input.get("name", "")
            result = await cluster_client.list_pods(namespace=ns)
            data = [p for p in result.data if p.get("name") == name]
            if not data:
                return json.dumps({"error": f"Pod {name} not found in namespace {ns}"})
            # Also get events for this pod
            events = await cluster_client.list_events(
                namespace=ns,
                field_selector=f"involvedObject.name={name}"
            )
            data = {"pod": data[0], "events": events.data[:10]}
        elif tool_name == "list_deployments":
            result = await cluster_client.list_deployments(namespace=tool_input.get("namespace", ""))
            data = result.data
        elif tool_name == "list_events":
            result = await cluster_client.list_events(
                namespace=tool_input.get("namespace", ""),
                field_selector=tool_input.get("field_selector", "")
            )
            data = result.data[:100]
        elif tool_name == "list_nodes":
            result = await cluster_client.list_nodes()
            data = result.data
        elif tool_name == "list_pvcs":
            result = await cluster_client.list_pvcs(namespace=tool_input.get("namespace", ""))
            data = result.data
        elif tool_name == "list_services":
            result = await cluster_client.list_services(namespace=tool_input.get("namespace", ""))
            data = result.data
        elif tool_name == "list_hpas":
            result = await cluster_client.list_hpas(namespace=tool_input.get("namespace", ""))
            data = result.data
        elif tool_name == "get_pod_logs":
            ns = tool_input.get("namespace", "")
            name = tool_input.get("name", "")
            tail = tool_input.get("tail_lines", 100)
            result = await cluster_client.query_logs("pod-logs", {"pod": name, "namespace": ns}, max_lines=tail)
            data = result.data
        elif tool_name == "query_prometheus":
            result = await cluster_client.query_prometheus(
                query=tool_input.get("query", ""),
                time_range=tool_input.get("time_range", "1h")
            )
            data = result.data
        elif tool_name == "list_network_policies":
            result = await cluster_client.list_network_policies(namespace=tool_input.get("namespace", ""))
            data = result.data
        elif tool_name == "list_rbac":
            ns = tool_input.get("namespace", "")
            roles = await cluster_client.list_roles(namespace=ns)
            bindings = await cluster_client.list_role_bindings(namespace=ns)
            sas = await cluster_client.list_service_accounts(namespace=ns)
            data = {
                "roles": roles.data[:50],
                "role_bindings": bindings.data[:50],
                "service_accounts": sas.data[:50],
            }
        elif tool_name == "list_statefulsets":
            result = await cluster_client.list_statefulsets(namespace=tool_input.get("namespace", ""))
            data = result.data
        elif tool_name == "list_daemonsets":
            result = await cluster_client.list_daemonsets(namespace=tool_input.get("namespace", ""))
            data = result.data
        elif tool_name == "list_jobs":
            result = await cluster_client.list_jobs(namespace=tool_input.get("namespace", ""))
            data = result.data
        elif tool_name == "list_cronjobs":
            result = await cluster_client.list_cronjobs(namespace=tool_input.get("namespace", ""))
            data = result.data
        elif tool_name == "submit_findings":
            # This is handled by the agent loop, not executed against cluster
            return json.dumps({"status": "findings_submitted"})
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        result_str = _serialize_with_envelope(data)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if isinstance(data, list):
            envelope = json.loads(result_str)
            if envelope.get("truncated"):
                logger.info("Tool %s result truncated: %d/%d items returned",
                            tool_name, envelope["returned"], envelope["total_available"],
                            extra={"action": "tool_truncated", "duration_ms": elapsed_ms})
            else:
                logger.debug("Tool %s returned %d items in %dms",
                             tool_name, len(data), elapsed_ms,
                             extra={"action": "tool_call_done", "duration_ms": elapsed_ms})
        else:
            logger.debug("Tool %s returned dict in %dms",
                         tool_name, elapsed_ms,
                         extra={"action": "tool_call_done", "duration_ms": elapsed_ms})

        return result_str

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.error("Tool execution failed: %s(%s): %s (took %dms)", tool_name, tool_input, e, elapsed_ms)
        return json.dumps({"error": str(e)})
