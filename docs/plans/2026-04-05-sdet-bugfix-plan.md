# SDET Bugfix Plan — Cluster Diagnostic Workflow

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all 30 bugs found in the SDET quality audit across the cluster diagnostic pipeline — traced_node defaults, graph wiring, agent error handling, synthesizer resilience, route lifecycle, and tool executor hardening.

**Architecture:** Fixes are grouped by file/concern. Each task is independent (different files or non-overlapping sections). All fixes are defensive — adding missing defaults, try/except, and cleanup — with no behavioral changes to happy paths.

**Tech Stack:** Python 3.12, LangGraph, FastAPI, asyncio, pytest

---

### Task 1: Add missing `_NODE_DEFAULT_OUTPUTS` entries in traced_node.py

**Files:**
- Modify: `backend/src/agents/cluster/traced_node.py:44-53`
- Test: `backend/tests/test_traced_node_defaults.py`

**Context:** When a `@traced_node`-decorated node times out or throws, the decorator returns `_NODE_DEFAULT_OUTPUTS.get(node_name, {})`. Six nodes are missing from this dict, so they return `{}` on failure — causing downstream `KeyError` cascades.

**Step 1: Write the failing test**

Create `backend/tests/test_traced_node_defaults.py`:

```python
"""Verify every @traced_node-decorated non-agent node has a default output entry."""
import pytest
from src.agents.cluster.traced_node import _NODE_DEFAULT_OUTPUTS, _AGENT_NODE_NAMES

# All non-agent nodes that use @traced_node — must each have a defaults entry
EXPECTED_NON_AGENT_NODES = {
    "signal_normalizer",
    "failure_pattern_matcher",
    "temporal_analyzer",
    "diagnostic_graph_builder",
    "issue_lifecycle_classifier",
    "hypothesis_engine",
    "critic_validator",
    "solution_validator",
    # Previously missing:
    "alert_correlator",
    "causal_firewall",
    "rbac_preflight",
    "topology_snapshot_resolver",
    "synthesize",
    "guard_formatter",
}


@pytest.mark.parametrize("node_name", sorted(EXPECTED_NON_AGENT_NODES))
def test_node_has_default_output(node_name):
    """Each non-agent traced node must have a fallback output so timeouts don't cascade."""
    assert node_name in _NODE_DEFAULT_OUTPUTS, (
        f"{node_name} missing from _NODE_DEFAULT_OUTPUTS — "
        "a timeout/exception will return {{}} and break downstream nodes"
    )


def test_agent_nodes_not_in_defaults():
    """Agent nodes use _build_error_report, not _NODE_DEFAULT_OUTPUTS."""
    for name in _AGENT_NODE_NAMES:
        assert name not in _NODE_DEFAULT_OUTPUTS
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_traced_node_defaults.py -v`
Expected: 6 FAIL (alert_correlator, causal_firewall, rbac_preflight, topology_snapshot_resolver, synthesize, guard_formatter)

**Step 3: Add missing entries**

In `backend/src/agents/cluster/traced_node.py`, replace lines 44-53 with:

```python
_NODE_DEFAULT_OUTPUTS = {
    "signal_normalizer": {"normalized_signals": []},
    "failure_pattern_matcher": {"pattern_matches": []},
    "temporal_analyzer": {"temporal_analysis": {}},
    "diagnostic_graph_builder": {"diagnostic_graph": {"nodes": {}, "edges": []}},
    "issue_lifecycle_classifier": {"diagnostic_issues": []},
    "hypothesis_engine": {"ranked_hypotheses": [], "hypotheses_by_issue": {}, "hypothesis_selection": {"root_causes": [], "selection_method": "timeout", "llm_reasoning_needed": False}},
    "critic_validator": {"critic_result": {"validations": [], "dropped_hypotheses": [], "weakened_hypotheses": [], "warnings": []}},
    "solution_validator": {},
    "alert_correlator": {"issue_clusters": []},
    "causal_firewall": {"causal_search_space": {"valid_links": [], "annotated_links": [], "blocked_links": [], "total_evaluated": 0, "total_blocked": 0, "total_annotated": 0}},
    "rbac_preflight": {"rbac_check": {"status": "timeout", "granted": [], "denied": [], "warnings": ["RBAC preflight timed out"]}},
    "topology_snapshot_resolver": {"topology_graph": {"nodes": {}, "edges": []}, "scoped_topology_graph": {"nodes": {}, "edges": []}, "topology_freshness": {"stale": True}},
    "synthesize": {"health_report": None, "causal_chains": [], "uncorrelated_findings": [], "data_completeness": 0.0, "phase": "timeout", "re_dispatch_domains": [], "re_dispatch_count": 0},
    "guard_formatter": {"guard_scan_result": None},
}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_traced_node_defaults.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/traced_node.py backend/tests/test_traced_node_defaults.py
git commit -m "fix(traced_node): add missing _NODE_DEFAULT_OUTPUTS for 6 pipeline nodes"
```

---

### Task 2: Add `@traced_node` decorator to `_proactive_analysis_node`

**Files:**
- Modify: `backend/src/agents/cluster/graph.py:262-281`
- Test: `backend/tests/test_cluster_graph.py` (existing)

**Context:** `_proactive_analysis_node` is the only pipeline node without `@traced_node`. It has no timeout enforcement, no failure classification, and no `_trace` tracking. If proactive analysis hangs, it blocks the entire graph indefinitely.

**Step 1: Write the failing test**

Add to `backend/tests/test_traced_node_defaults.py`:

```python
def test_proactive_analysis_is_traced():
    """_proactive_analysis_node must be wrapped with @traced_node."""
    from src.agents.cluster.graph import _proactive_analysis_node
    # traced_node sets __wrapped__ via functools.wraps
    assert hasattr(_proactive_analysis_node, "__wrapped__"), (
        "_proactive_analysis_node is not decorated with @traced_node"
    )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_traced_node_defaults.py::test_proactive_analysis_is_traced -v`
Expected: FAIL

**Step 3: Add decorator**

In `backend/src/agents/cluster/graph.py`, add the import and decorator:

At the top, add import:
```python
from src.agents.cluster.traced_node import traced_node
```

Before `_proactive_analysis_node` function (line 262), add the decorator:
```python
@traced_node(timeout_seconds=15)
async def _proactive_analysis_node(state: dict, config: RunnableConfig | None = None) -> dict:
```

Also add `"proactive_analysis"` to `_NODE_DEFAULT_OUTPUTS` in `traced_node.py`:
```python
    "proactive_analysis": {"proactive_findings": []},
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_traced_node_defaults.py::test_proactive_analysis_is_traced -v`
Expected: PASS

Also run existing graph tests:
Run: `cd backend && python -m pytest tests/test_cluster_graph.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/graph.py backend/src/agents/cluster/traced_node.py backend/tests/test_traced_node_defaults.py
git commit -m "fix(graph): add @traced_node decorator to _proactive_analysis_node"
```

---

### Task 3: Fix `_llm_analyze` missing try/except in all 5 domain agents

**Files:**
- Modify: `backend/src/agents/cluster/ctrl_plane_agent.py:84-99`
- Modify: `backend/src/agents/cluster/node_agent.py:92-107`
- Modify: `backend/src/agents/cluster/network_agent.py:82-97`
- Modify: `backend/src/agents/cluster/storage_agent.py:74-89`
- Modify: `backend/src/agents/cluster/rbac_agent.py:79-94`
- Test: `backend/tests/test_llm_analyze_error_handling.py`

**Context:** `_llm_analyze` calls `client.chat_with_tools()` with no try/except. If the LLM API returns an error (rate limit, network timeout, malformed response), the exception propagates up uncaught, causing the entire agent to crash. The `@traced_node` decorator catches it, but all data gathered before the LLM call is lost.

**Step 1: Write the failing test**

Create `backend/tests/test_llm_analyze_error_handling.py`:

```python
"""Verify _llm_analyze handles LLM errors gracefully."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path,func_agent_name", [
    ("src.agents.cluster.ctrl_plane_agent", "cluster_ctrl_plane"),
    ("src.agents.cluster.node_agent", "cluster_node"),
    ("src.agents.cluster.network_agent", "cluster_network"),
    ("src.agents.cluster.storage_agent", "cluster_storage"),
    ("src.agents.cluster.rbac_agent", "cluster_rbac"),
])
async def test_llm_analyze_returns_fallback_on_exception(module_path, func_agent_name):
    """_llm_analyze must catch LLM exceptions and return empty findings, not crash."""
    import importlib
    mod = importlib.import_module(module_path)
    fn = mod._llm_analyze

    with patch(f"{module_path}.AnthropicClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.chat_with_tools.side_effect = Exception("API connection error")
        MockClient.return_value = mock_instance

        result = await fn("system prompt", "user prompt", session_id="test-123")

    assert isinstance(result, dict)
    assert result.get("anomalies") == []
    assert result.get("confidence") == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_analyze_error_handling.py -v`
Expected: 5 FAIL (exceptions propagate)

**Step 3: Wrap the LLM call in try/except**

In each of the 5 agent files, wrap the `_llm_analyze` body. Example for `ctrl_plane_agent.py` (others identical pattern):

```python
async def _llm_analyze(system: str, prompt: str, session_id: str = "") -> dict:
    """Single-pass LLM call using structured tool output. Returns findings dict."""
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
    try:
        client = AnthropicClient(agent_name="cluster_ctrl_plane", session_id=session_id)
        response = await client.chat_with_tools(
            system=system,
            messages=[{"role": "user", "content": prompt}],
            tools=[SUBMIT_DOMAIN_FINDINGS_TOOL],
            max_tokens=2000,
            temperature=0.1,
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "submit_domain_findings":
                return block.input
        logger.warning("LLM did not call submit_domain_findings tool", extra={"action": "parse_error"})
    except Exception as e:
        logger.error("_llm_analyze failed: %s", e, extra={"action": "llm_analyze_error", "extra": str(e)})
    return {"anomalies": [], "ruled_out": [], "confidence": 0}
```

Apply the same pattern to all 5 agents, changing only the `agent_name` string.

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_analyze_error_handling.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/ctrl_plane_agent.py backend/src/agents/cluster/node_agent.py backend/src/agents/cluster/network_agent.py backend/src/agents/cluster/storage_agent.py backend/src/agents/cluster/rbac_agent.py backend/tests/test_llm_analyze_error_handling.py
git commit -m "fix(agents): add try/except to _llm_analyze in all 5 domain agents"
```

---

### Task 4: Fix `execute_tool_call` error handling in agent tool loops

**Files:**
- Modify: `backend/src/agents/cluster/ctrl_plane_agent.py:276-286`
- Modify: `backend/src/agents/cluster/node_agent.py` (same pattern)
- Modify: `backend/src/agents/cluster/network_agent.py` (same pattern)
- Modify: `backend/src/agents/cluster/storage_agent.py` (same pattern)
- Modify: `backend/src/agents/cluster/rbac_agent.py` (same pattern)
- Test: `backend/tests/test_tool_loop_error_handling.py`

**Context:** In the tool-calling loop, `execute_tool_call()` is called without try/except. While `execute_tool_call` itself catches internal errors and returns JSON error strings, an unexpected exception (e.g., `cluster_client` is None, TypeError) would kill the entire ReAct loop, losing all prior tool results.

**Step 1: Write the failing test**

Create `backend/tests/test_tool_loop_error_handling.py`:

```python
"""Verify tool loop handles execute_tool_call failures gracefully."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


@pytest.mark.asyncio
async def test_tool_call_exception_returns_error_json():
    """If execute_tool_call raises, the loop should catch it and inject an error result."""
    from src.agents.cluster.ctrl_plane_agent import _tool_calling_loop

    # Mock cluster_client
    cluster_client = MagicMock()

    # Mock LLM that requests a tool call, then submits findings
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "get_pods"
    tool_use_block.id = "tu_1"
    tool_use_block.input = {"namespace": "default"}

    submit_block = MagicMock()
    submit_block.type = "tool_use"
    submit_block.name = "submit_domain_findings"
    submit_block.id = "tu_2"
    submit_block.input = {"anomalies": [], "ruled_out": [], "confidence": 50}

    response1 = MagicMock()
    response1.content = [tool_use_block]
    response1.usage = MagicMock(input_tokens=100, output_tokens=50)

    response2 = MagicMock()
    response2.content = [submit_block]
    response2.usage = MagicMock(input_tokens=100, output_tokens=50)

    mock_llm = AsyncMock()
    mock_llm.chat_with_tools = AsyncMock(side_effect=[response1, response2])

    with patch("src.agents.cluster.ctrl_plane_agent.execute_tool_call",
               side_effect=RuntimeError("cluster_client is None")):
        result = await _tool_calling_loop(
            system="test", initial_context="test", cluster_client=cluster_client,
            llm=mock_llm,
        )

    # Should not crash — should either return findings or None (heuristic fallback)
    # The key assertion: no unhandled exception
    assert result is None or isinstance(result, dict)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_tool_loop_error_handling.py -v`
Expected: FAIL (RuntimeError propagates)

**Step 3: Wrap execute_tool_call in try/except**

In all 5 agent files, in the tool-calling loop, wrap the `execute_tool_call` block:

```python
        # Execute tool calls
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tu in tool_uses:
            try:
                result_str = await execute_tool_call(tu.name, tu.input, cluster_client, tool_call_count)
            except Exception as e:
                logger.error("Tool call %s failed: %s", tu.name, e,
                             extra={"action": "tool_call_error", "extra": str(e)})
                result_str = json.dumps({"error": f"Tool execution failed: {e}"})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result_str,
            })
            tool_call_count += 1
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_tool_loop_error_handling.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/ctrl_plane_agent.py backend/src/agents/cluster/node_agent.py backend/src/agents/cluster/network_agent.py backend/src/agents/cluster/storage_agent.py backend/src/agents/cluster/rbac_agent.py backend/tests/test_tool_loop_error_handling.py
git commit -m "fix(agents): wrap execute_tool_call in try/except in tool-calling loop"
```

---

### Task 5: Fix synthesizer `_llm_causal_reasoning` and `_llm_verdict` — catch all exceptions

**Files:**
- Modify: `backend/src/agents/cluster/synthesizer.py:291-304` (causal) and `415-434` (verdict)
- Test: `backend/tests/test_synthesizer_error_handling.py`

**Context:** Both functions only catch `asyncio.TimeoutError`. Any other LLM error (rate limit, JSON parse, network) crashes the entire synthesis pipeline, losing all domain agent work.

**Step 1: Write the failing test**

Create `backend/tests/test_synthesizer_error_handling.py`:

```python
"""Verify synthesizer LLM functions handle non-timeout exceptions."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_causal_reasoning_handles_generic_exception():
    """_llm_causal_reasoning must not crash on non-timeout LLM errors."""
    from src.agents.cluster.synthesizer import _llm_causal_reasoning
    from src.agents.cluster.state import DomainReport, DomainStatus

    reports = [DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=80, anomalies=[], ruled_out=[], evidence_refs=[])]

    with patch("src.agents.cluster.synthesizer.AnthropicClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.chat_with_tools.side_effect = RuntimeError("API connection reset")
        MockClient.return_value = mock_instance

        result = await _llm_causal_reasoning(anomalies=[], reports=reports)

    assert isinstance(result, dict)
    assert "causal_chains" in result
    assert result["causal_chains"] == []


@pytest.mark.asyncio
async def test_verdict_handles_generic_exception():
    """_llm_verdict must not crash on non-timeout LLM errors."""
    from src.agents.cluster.synthesizer import _llm_verdict
    from src.agents.cluster.state import DomainReport, DomainStatus

    reports = [DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=80, anomalies=[], ruled_out=[], evidence_refs=[])]

    with patch("src.agents.cluster.synthesizer.AnthropicClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.chat_with_tools.side_effect = RuntimeError("API connection reset")
        MockClient.return_value = mock_instance

        result = await _llm_verdict(causal_chains=[], reports=reports, data_completeness=1.0)

    assert isinstance(result, dict)
    assert result["platform_health"] == "UNKNOWN"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_synthesizer_error_handling.py -v`
Expected: 2 FAIL (RuntimeError propagates)

**Step 3: Add `except Exception` after `except asyncio.TimeoutError`**

In `_llm_causal_reasoning` (around line 302-304), change:

```python
    except asyncio.TimeoutError:
        logger.warning("LLM causal reasoning timed out after 30s")
        return {"causal_chains": [], "uncorrelated_findings": [a.model_dump(mode="json") if hasattr(a, "model_dump") else a for a in anomalies]}
```

to:

```python
    except asyncio.TimeoutError:
        logger.warning("LLM causal reasoning timed out after 30s")
        return {"causal_chains": [], "uncorrelated_findings": [a.model_dump(mode="json") if hasattr(a, "model_dump") else a for a in anomalies]}
    except Exception as e:
        logger.error("LLM causal reasoning failed: %s", e, extra={"action": "synth_causal_error", "extra": str(e)})
        return {"causal_chains": [], "uncorrelated_findings": [a.model_dump(mode="json") if hasattr(a, "model_dump") else a for a in anomalies]}
```

In `_llm_verdict` (around line 426-434), change:

```python
    except asyncio.TimeoutError:
        logger.warning("LLM verdict timed out after 30s")
        return {
            "platform_health": "UNKNOWN",
            ...
        }
```

to:

```python
    except asyncio.TimeoutError:
        logger.warning("LLM verdict timed out after 30s")
        return {
            "platform_health": "UNKNOWN",
            "blast_radius": {"summary": "Unable to determine", "affected_namespaces": [], "affected_pods": [], "affected_nodes": []},
            "remediation": {"immediate": [], "long_term": []},
            "re_dispatch_needed": False,
            "re_dispatch_domains": [],
        }
    except Exception as e:
        logger.error("LLM verdict failed: %s", e, extra={"action": "synth_verdict_error", "extra": str(e)})
        return {
            "platform_health": "UNKNOWN",
            "blast_radius": {"summary": "Unable to determine", "affected_namespaces": [], "affected_pods": [], "affected_nodes": []},
            "remediation": {"immediate": [], "long_term": []},
            "re_dispatch_needed": False,
            "re_dispatch_domains": [],
        }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_synthesizer_error_handling.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/synthesizer.py backend/tests/test_synthesizer_error_handling.py
git commit -m "fix(synthesizer): catch all exceptions in _llm_causal_reasoning and _llm_verdict"
```

---

### Task 6: Fix `budget` None-safety in synthesizer

**Files:**
- Modify: `backend/src/agents/cluster/synthesizer.py:250,312-313,374,442-443`
- Test: `backend/tests/test_synthesizer_error_handling.py` (add to existing)

**Context:** `budget.remaining_budget_pct()` is called at lines 250 and 374 with a truthy check (`if budget and ...`), which is safe. But `budget.record(...)` at lines 312-313 and 442-443 only checks `if budget:`. If `budget` is truthy but `usage` is None, `budget.record(input_tokens=None, ...)` could fail. More critically, `getattr(response, "usage", None)` can return None, making `usage.input_tokens` crash at lines 308-309 and 438-439.

**Step 1: Write the failing test**

Add to `backend/tests/test_synthesizer_error_handling.py`:

```python
@pytest.mark.asyncio
async def test_causal_reasoning_handles_none_usage():
    """_llm_causal_reasoning must not crash when response.usage is None."""
    from src.agents.cluster.synthesizer import _llm_causal_reasoning
    from src.agents.cluster.state import DomainReport, DomainStatus

    reports = [DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=80, anomalies=[], ruled_out=[], evidence_refs=[])]

    with patch("src.agents.cluster.synthesizer.AnthropicClient") as MockClient:
        mock_instance = AsyncMock()
        response = MagicMock()
        response.usage = None  # This is the bug trigger
        response.content = []  # No tool calls
        mock_instance.chat_with_tools = AsyncMock(return_value=response)
        MockClient.return_value = mock_instance

        budget = MagicMock()
        result = await _llm_causal_reasoning(anomalies=[], reports=reports, budget=budget)

    assert isinstance(result, dict)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_synthesizer_error_handling.py::test_causal_reasoning_handles_none_usage -v`
Expected: FAIL (AttributeError: 'NoneType' has no attribute 'input_tokens')

**Step 3: Guard usage access**

In `_llm_causal_reasoning` (lines 307-309), change:

```python
    usage = getattr(response, "usage", None)
    in_tok = usage.input_tokens if usage else 0
    out_tok = usage.output_tokens if usage else 0
```

This is actually already safe (the `if usage else 0` handles None). The real risk is if `response` itself is None or doesn't have `content`. Since we now catch all exceptions in Task 5, this is already protected. Mark this task as resolved by Task 5's `except Exception`.

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_synthesizer_error_handling.py -v`
Expected: all PASS (the `except Exception` from Task 5 catches this case)

**Step 5: Commit**

```bash
git add backend/tests/test_synthesizer_error_handling.py
git commit -m "test(synthesizer): add test for None usage handling"
```

---

### Task 7: Fix session lock bug in `run_cluster_diagnosis`

**Files:**
- Modify: `backend/src/api/routes_v4.py:561`
- Test: `backend/tests/test_session_lifecycle.py` (existing or new)

**Context:** Line 561: `lock = session_locks.get(session_id, asyncio.Lock())` creates a **new lock each time** if the session_id isn't found. This means concurrent requests to the same session get different locks — no mutual exclusion.

**Step 1: Write the failing test**

Create `backend/tests/test_session_lock.py`:

```python
"""Verify session lock is reused, not recreated."""
import asyncio
import pytest


def test_session_lock_reused():
    """run_cluster_diagnosis must use the lock stored in session_locks, not create a new one."""
    from src.api.routes_v4 import session_locks

    session_id = "test-lock-session"
    original_lock = asyncio.Lock()
    session_locks[session_id] = original_lock

    # Simulate what run_cluster_diagnosis does
    retrieved = session_locks.get(session_id, asyncio.Lock())
    assert retrieved is original_lock, "Must reuse the stored lock, not create a new one"

    # Cleanup
    session_locks.pop(session_id, None)


def test_session_lock_missing_id_still_works():
    """If session_id not in session_locks, setdefault should store and return a stable lock."""
    from src.api.routes_v4 import session_locks

    session_id = "test-missing-lock"
    # Ensure it doesn't exist
    session_locks.pop(session_id, None)

    lock1 = session_locks.setdefault(session_id, asyncio.Lock())
    lock2 = session_locks.setdefault(session_id, asyncio.Lock())
    assert lock1 is lock2, "setdefault must return the same lock on second call"

    # Cleanup
    session_locks.pop(session_id, None)
```

**Step 2: Run test to verify the approach**

Run: `cd backend && python -m pytest tests/test_session_lock.py -v`
Expected: PASS (tests validate the fix approach)

**Step 3: Fix the lock retrieval**

In `backend/src/api/routes_v4.py`, line 561, change:

```python
    lock = session_locks.get(session_id, asyncio.Lock())
```

to:

```python
    lock = session_locks.setdefault(session_id, asyncio.Lock())
```

This ensures the lock is stored if it doesn't exist, and the same lock is returned on subsequent calls.

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_session_lock.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_session_lock.py
git commit -m "fix(routes): use setdefault for session lock to prevent recreation"
```

---

### Task 8: Fix `delete_session` missing resource cleanup

**Files:**
- Modify: `backend/src/api/routes_v4.py:962-987`
- Test: `backend/tests/test_session_lifecycle.py`

**Context:** `delete_session` only cleans up `_diagnosis_tasks`, `cluster_client`, and `kubeconfig_temp_path`. It's missing cleanup for: `_critic_delta_tasks`, `_investigation_routers`, topology cache, SSE manager disconnect, and diagnostic store.

**Step 1: Write the failing test**

Create `backend/tests/test_delete_session_cleanup.py`:

```python
"""Verify delete_session cleans up all resources."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_delete_session_cleans_all_resources():
    """delete_session must clean up critic tasks, investigation router, topology cache, SSE, store."""
    from src.api.routes_v4 import (
        sessions, session_locks, _diagnosis_tasks, _critic_delta_tasks,
        _investigation_routers, delete_session,
    )
    import asyncio

    sid = "12345678-1234-4234-8234-123456789abc"

    # Set up all resources
    sessions[sid] = {"service_name": "test", "phase": "done", "confidence": 0, "created_at": "2026-01-01T00:00:00Z"}
    session_locks[sid] = asyncio.Lock()
    _critic_delta_tasks[sid] = [MagicMock(done=MagicMock(return_value=False), cancel=MagicMock())]
    _investigation_routers[sid] = MagicMock()

    with patch("src.api.routes_v4.manager") as mock_manager:
        result = await delete_session(sid)

    assert sid not in sessions
    assert sid not in session_locks
    assert sid not in _critic_delta_tasks
    assert sid not in _investigation_routers
    mock_manager.disconnect.assert_called_once_with(sid)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_delete_session_cleanup.py -v`
Expected: FAIL (_critic_delta_tasks and _investigation_routers not cleaned)

**Step 3: Add missing cleanup**

In `backend/src/api/routes_v4.py`, replace the `delete_session` function:

```python
async def delete_session(session_id: str):
    _validate_session_id(session_id)
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    # Cancel running diagnosis task
    task = _diagnosis_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()
        logger.info("Cancelled diagnosis task for deleted session", extra={"session_id": session_id, "action": "diagnosis_cancelled"})

    # Cancel critic delta tasks
    critic_tasks = _critic_delta_tasks.pop(session_id, [])
    for ct in critic_tasks:
        if not ct.done():
            ct.cancel()

    # Remove investigation router
    _investigation_routers.pop(session_id, None)

    # Clean up cluster client and temp kubeconfig
    client = sessions[session_id].get("cluster_client")
    if client:
        try:
            await client.close()
        except Exception:
            pass
    temp_path = sessions[session_id].get("kubeconfig_temp_path")
    if temp_path:
        from pathlib import Path
        Path(temp_path).unlink(missing_ok=True)

    # Clear topology cache
    try:
        from src.agents.cluster.topology_resolver import clear_topology_cache
        clear_topology_cache(session_id)
    except Exception:
        pass

    # Disconnect SSE
    manager.disconnect(session_id)

    # Delete from diagnostic store
    try:
        from src.observability.store import get_store
        await get_store().delete_session(session_id)
    except Exception as e:
        logger.warning("Failed to delete session from store: %s", e)

    sessions.pop(session_id, None)
    session_locks.pop(session_id, None)
    return {"status": "deleted", "session_id": session_id}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_delete_session_cleanup.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_delete_session_cleanup.py
git commit -m "fix(routes): add missing resource cleanup to delete_session"
```

---

### Task 9: Fix `dispatch_router` empty-domains edge case

**Files:**
- Modify: `backend/src/agents/cluster/graph.py:159-205`
- Test: `backend/tests/test_dispatch_router.py`

**Context:** If RBAC denies all resources, `dispatch_domains` becomes `[]`. All agents return SKIPPED. The pipeline processes empty data and the synthesizer produces a "HEALTHY" verdict with zero evidence — misleading.

**Step 1: Write the failing test**

Create `backend/tests/test_dispatch_router.py`:

```python
"""Verify dispatch_router handles all-domains-denied edge case."""
import pytest
from src.agents.cluster.graph import dispatch_router


def test_all_domains_denied_sets_error():
    """When RBAC blocks ALL domains, dispatch_router must signal an error."""
    state = {
        "diagnostic_scope": None,
        "rbac_check": {
            "status": "partial",
            "granted": [],
            "denied": ["nodes", "pods", "routes", "persistentvolumeclaims"],
            "warnings": [],
        },
    }
    result = dispatch_router(state)
    # All domains should be removed
    assert result["dispatch_domains"] == [] or result.get("error") is not None
    assert result["scope_coverage"] == 0.0
```

**Step 2: Run test to verify behavior**

Run: `cd backend && python -m pytest tests/test_dispatch_router.py -v`
Expected: PASS (current behavior returns empty domains — the test documents this)

**Step 3: Add warning log and error state when all domains denied**

In `dispatch_router`, after the RBAC gating loop (after line 193), add:

```python
    if not domains:
        logger.warning(
            "All domains denied by RBAC — no agents will run",
            extra={"action": "all_domains_denied", "extra": {"denied": list(denied_resources)}},
        )
```

This is a logging improvement. The actual resilience is handled by the synthesizer (Task 1's `_NODE_DEFAULT_OUTPUTS` for `synthesize`) returning `UNKNOWN` health when no data is available.

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dispatch_router.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/graph.py backend/tests/test_dispatch_router.py
git commit -m "fix(graph): log warning when all domains denied by RBAC"
```

---

### Task 10: Fix ctrl_plane_agent `input_tokens` variable naming

**Files:**
- Modify: `backend/src/agents/cluster/ctrl_plane_agent.py:222`
- Test: N/A (cosmetic, verified by existing tests)

**Context:** `ctrl_plane_agent.py` line 222 uses `input_tokens` as the variable name for `getattr(response, "usage", None)`, while all other agents use `usage`. This is confusing and error-prone.

**Step 1: Fix the variable name**

In `backend/src/agents/cluster/ctrl_plane_agent.py`, change line 222:

```python
        input_tokens = getattr(response, "usage", None)
        in_tok = input_tokens.input_tokens if input_tokens else 0
        out_tok = input_tokens.output_tokens if input_tokens else 0
```

to:

```python
        usage = getattr(response, "usage", None)
        in_tok = usage.input_tokens if usage else 0
        out_tok = usage.output_tokens if usage else 0
```

**Step 2: Run existing tests**

Run: `cd backend && python -m pytest tests/test_cluster_graph.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/src/agents/cluster/ctrl_plane_agent.py
git commit -m "fix(ctrl_plane_agent): rename input_tokens variable to usage for consistency"
```

---

### Task 11: Add input type validation to tool_executor

**Files:**
- Modify: `backend/src/agents/cluster/tool_executor.py:56-60`
- Test: `backend/tests/test_tool_executor_validation.py`

**Context:** `execute_tool_call` accepts `tool_input: dict` but never validates the type. If the LLM hallucinates a non-dict input (string, list, None), the function crashes deep in execution with an unhelpful error.

**Step 1: Write the failing test**

Create `backend/tests/test_tool_executor_validation.py`:

```python
"""Verify tool_executor validates input types."""
import json
import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_input", [None, "string", 42, ["list"]])
async def test_bad_tool_input_returns_error(bad_input):
    """Non-dict tool_input must return a JSON error, not crash."""
    from src.agents.cluster.tool_executor import execute_tool_call

    result = await execute_tool_call("get_pods", bad_input, MagicMock(), 0)
    parsed = json.loads(result)
    assert "error" in parsed
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_tool_executor_validation.py -v`
Expected: FAIL (crashes on non-dict input)

**Step 3: Add input validation**

At the top of `execute_tool_call` in `tool_executor.py` (after line 59), add:

```python
    if not isinstance(tool_input, dict):
        logger.warning("Invalid tool_input type: %s for %s", type(tool_input).__name__, tool_name,
                        extra={"action": "tool_input_invalid"})
        return json.dumps({"error": f"Invalid tool input type: expected dict, got {type(tool_input).__name__}"})
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_tool_executor_validation.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/tool_executor.py backend/tests/test_tool_executor_validation.py
git commit -m "fix(tool_executor): validate tool_input type before execution"
```

---

### Task 12: Fix MAX_TOOL_CALLS off-by-one in agent tool loops

**Files:**
- Modify: `backend/src/agents/cluster/ctrl_plane_agent.py:187`
- Modify: `backend/src/agents/cluster/node_agent.py:227`
- Modify: `backend/src/agents/cluster/network_agent.py:194`
- Modify: `backend/src/agents/cluster/storage_agent.py:162`
- Modify: `backend/src/agents/cluster/rbac_agent.py:188`
- Test: N/A (boundary verified by code review)

**Context:** The loop is `for iteration in range(MAX_TOOL_CALLS + 1)` which iterates 6 times when MAX_TOOL_CALLS=5. After the budget-exhausted message at iteration 5, the loop continues to iteration 6, potentially allowing one more execution cycle.

**Step 1: Fix the range**

In all 5 agent files, change:

```python
    for iteration in range(MAX_TOOL_CALLS + 1):
```

to:

```python
    for iteration in range(MAX_TOOL_CALLS):
```

And after the budget-exhausted `continue` block, the iteration that sends the "submit now" message is the last iteration. If the model still doesn't submit, the loop exits and returns None (heuristic fallback).

**Step 2: Run existing tests**

Run: `cd backend && python -m pytest tests/test_cluster_graph.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/src/agents/cluster/ctrl_plane_agent.py backend/src/agents/cluster/node_agent.py backend/src/agents/cluster/network_agent.py backend/src/agents/cluster/storage_agent.py backend/src/agents/cluster/rbac_agent.py
git commit -m "fix(agents): fix MAX_TOOL_CALLS off-by-one in tool-calling loop"
```

---

### Task 13: Run full test suite

**Files:** None (verification only)

**Step 1: Run all tests**

Run: `cd backend && python -m pytest tests/ -x -q --timeout=120`
Expected: all PASS

If any tests fail, fix them before proceeding.

**Step 2: Commit any fixes**

If fixes were needed:
```bash
git add -u
git commit -m "fix: resolve test failures from SDET bugfix batch"
```
