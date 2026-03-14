# Diagnostic Intelligence Bugfixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 27 bugs, gaps, and edge cases found in the diagnostic intelligence pipeline audit (3 critical, 10 high, 14 medium).

**Architecture:** All fixes are in existing files — no new files needed. Fixes are ordered by severity (critical first) and grouped by file to minimize context switching.

**Tech Stack:** Python/Pydantic (backend), React/TypeScript (frontend)

---

## Task 1: Fix hypothesis_engine.py (Critical #1, #2 + High #25 + Medium #16)

**Files:**
- Modify: `backend/src/agents/cluster/hypothesis_engine.py`

**Fixes:**

**1a. Clamp logistic function input (Critical #1)**

The `_logistic(x)` function can overflow with `math.exp(-x)` when x is very large or very negative.

```python
# Find the _logistic function and replace with:
def _logistic(x: float) -> float:
    """Logistic sigmoid with input clamping to prevent overflow."""
    x = max(-10.0, min(10.0, x))  # Clamp to safe range
    return 1.0 / (1.0 + math.exp(-x))
```

**1b. Handle empty hypotheses gracefully (Critical #2)**

After all three hypothesis sources run (patterns, graph, correlation), if `all_hypotheses` is empty, return meaningful defaults instead of passing empty list through the pipeline.

```python
# In the hypothesis_engine traced node function, after merging all sources:
if not all_hypotheses:
    logger.warning("No hypotheses generated from any source")
    return {
        "ranked_hypotheses": [],
        "hypotheses_by_issue": {},
        "hypothesis_selection": {
            "root_causes": [],
            "selection_method": "no_hypotheses",
            "llm_reasoning_needed": False,
        },
    }
```

**1c. Fix dedup merge key — too coarse (Medium #25)**

Currently merges by `(resource_key, signal_family)` which conflates distinct node pressures (disk vs memory). Change to merge by `(resource_key, cause_type)` — only truly identical causes merge.

```python
# In deduplicate_hypotheses, change merge key from:
#   family = SIGNAL_FAMILIES.get(h.cause_type, h.cause_type)
#   key = f"{h.root_resource}||{family}"
# To:
key = f"{h.root_resource}||{h.cause_type}"
```

**1d. Fix empty issues causing hypothesis unlinking (Medium #16)**

After the hypothesis-to-issue linking loop, add fallback: if a hypothesis has empty `affected_issues`, link based on matching signals.

```python
# After the issue-linking loop:
for h in all_hypotheses:
    if not h.affected_issues:
        # Fallback: link to any issue containing signals that match hypothesis evidence
        for issue in diagnostic_issues:
            issue_signals = set(issue.get("signals", []))
            h_signals = {e.signal_type for e in h.supporting_evidence}
            if issue_signals & h_signals:
                h.affected_issues.append(issue.get("issue_id", ""))
```

**Commit:** `fix(hypothesis): clamp logistic, handle empty hypotheses, fix dedup merge key`

---

## Task 2: Fix failure_patterns.py (High #5, #6)

**Files:**
- Modify: `backend/src/agents/cluster/failure_patterns.py`

**Fixes:**

**2a. Make resolve_priority_conflicts actually filter (High #5)**

Currently just sorts but keeps all patterns. Change to actually remove lower-priority patterns when they conflict on the same resource.

```python
def resolve_priority_conflicts(matches: list[PatternMatch]) -> list[PatternMatch]:
    """When multiple patterns match the same resource, keep highest priority only."""
    if len(matches) <= 1:
        return matches

    priority_map = {p.pattern_id: p.priority for p in FAILURE_PATTERNS}

    # Group by affected resource
    resource_best: dict[str, str] = {}  # resource -> best pattern_id
    for m in matches:
        pri = priority_map.get(m.pattern_id, 0)
        for res in m.affected_resources:
            current_best = resource_best.get(res)
            if not current_best or pri > priority_map.get(current_best, 0):
                resource_best[res] = m.pattern_id

    # Keep patterns that are the best for at least one resource
    keep_ids = set(resource_best.values())
    return [m for m in matches if m.pattern_id in keep_ids]
```

**2b. Fix NETPOL_BLOCKING pattern — make conditions more flexible (High #6)**

Split into two patterns: one for the combined signal (high confidence), one for NETPOL alone (lower confidence).

```python
# Replace the single NETPOL_BLOCKING pattern with two:
FailurePattern(
    pattern_id="NETPOL_BLOCKING_CONFIRMED",
    name="NetworkPolicy confirmed blocking traffic",
    version="1.0", scope="namespace", priority=8,
    conditions=[{"signal": "NETPOL_EMPTY_INGRESS"}, {"signal": "SERVICE_ZERO_ENDPOINTS"}],
    probable_causes=["Overly restrictive NetworkPolicy with default-deny"],
    known_fixes=["Review NetworkPolicy ingress rules", "Add allow rules for required traffic"],
    severity="high", confidence_boost=0.25,
),
FailurePattern(
    pattern_id="NETPOL_SUSPICIOUS",
    name="NetworkPolicy with empty rules (potential blocking)",
    version="1.0", scope="namespace", priority=4,
    conditions=[{"signal": "NETPOL_EMPTY_INGRESS"}],
    probable_causes=["NetworkPolicy may be blocking traffic", "Default-deny without allow rules"],
    known_fixes=["Review NetworkPolicy ingress rules", "Check if services are affected"],
    severity="medium", confidence_boost=0.1,
),
```

**Commit:** `fix(patterns): filter priority conflicts, split NETPOL pattern`

---

## Task 3: Fix diagnostic_graph_builder.py (High #12 + Medium #14)

**Files:**
- Modify: `backend/src/agents/cluster/diagnostic_graph_builder.py`

**Fixes:**

**3a. Fix SYMPTOM_OF edge causality inversion (High #12)**

The current code assumes first pattern condition is root cause — wrong for patterns like CRASHLOOP_OOM where OOM is the root.

Add a `ROOT_SIGNAL` mapping that specifies which signal is the root in multi-condition patterns:

```python
# Add at module level:
# When a pattern has multiple conditions, this maps pattern_id to the root signal
PATTERN_ROOT_SIGNALS = {
    "CRASHLOOP_OOM": "OOM_KILLED",        # OOM causes the crash loop
    "NODE_DISK_FULL": "NODE_DISK_PRESSURE",  # Disk pressure causes NotReady
    "STUCK_ROLLOUT": "ROLLOUT_STUCK",      # Rollout stuck is the root
    "NODE_PRESSURE_EVICTION": "NODE_DISK_PRESSURE",  # Pressure causes eviction
    "NODE_MEMORY_EVICTION": "NODE_MEMORY_PRESSURE",  # Memory pressure causes eviction
    "NETPOL_BLOCKING_CONFIRMED": "NETPOL_EMPTY_INGRESS",  # Policy causes zero endpoints
}
```

Then in Rule 5, use this mapping instead of assuming first condition is root:

```python
# Rule 5: Pattern match links signals → SYMPTOM_OF
for pm_dict in pattern_matches:
    pattern_id = pm_dict.get("pattern_id", "")
    pm_conditions = pm_dict.get("matched_conditions", [])
    if len(pm_conditions) <= 1:
        continue

    root_signal = PATTERN_ROOT_SIGNALS.get(pattern_id, pm_conditions[0])
    symptom_signals = [c for c in pm_conditions if c != root_signal]

    root_nodes = [nid for nid, n in nodes.items() if n.signal_type == root_signal]
    for symptom_type in symptom_signals:
        symptom_nodes = [nid for nid, n in nodes.items() if n.signal_type == symptom_type]
        for r in root_nodes:
            for s in symptom_nodes:
                edges.append(DiagnosticEdge(
                    from_id=r, to_id=s, edge_type="SYMPTOM_OF",
                    confidence=0.7, evidence=f"Pattern {pattern_id}: {root_signal} → {symptom_type}"
                ))
```

**3b. Validate edges reference existing nodes (Medium #14)**

After edge creation, filter out edges with dangling node references:

```python
# Before returning, validate edges:
valid_edges = [e for e in edges if e.from_id in nodes and e.to_id in nodes]
if len(valid_edges) < len(edges):
    logger.warning("Removed %d dangling edges", len(edges) - len(valid_edges))
edges = valid_edges
```

**Commit:** `fix(graph): correct SYMPTOM_OF causality, validate edge nodes`

---

## Task 4: Fix issue_lifecycle.py (High #7, #13)

**Files:**
- Modify: `backend/src/agents/cluster/issue_lifecycle.py`

**Fixes:**

**4a. Guard for empty/malformed diagnostic_graph (High #7)**

```python
# At start of build_diagnostic_issues:
def build_diagnostic_issues(diagnostic_graph, signals, pattern_matches, temporal_data, thresholds=None):
    if not diagnostic_graph or not isinstance(diagnostic_graph, dict):
        logger.warning("Empty or invalid diagnostic graph — returning empty issues")
        return []

    nodes_data = diagnostic_graph.get("nodes", {})
    if not nodes_data:
        logger.warning("Diagnostic graph has no nodes — returning empty issues")
        return []

    try:
        graph = DiagnosticGraph(**diagnostic_graph)
    except Exception as e:
        logger.error("Failed to parse diagnostic graph: %s", e)
        return []
```

**4b. Prevent SYMPTOM from ranking above root causes (High #13)**

Change priority scoring to enforce that symptoms never outrank root causes, regardless of severity or blast radius:

```python
def compute_priority_score(state, severity, blast_radius, is_root_cause, is_symptom=False):
    base = (
        SEVERITY_WEIGHT.get(severity, 2)
        + 0.5 * blast_radius
        + STATE_WEIGHT.get(state, 0.0)
        + (2.0 if is_root_cause else 0)
    )
    # Hard cap: symptoms can never exceed 3.0 regardless of other factors
    if is_symptom:
        return min(base, 3.0)
    return base
```

Also update the call site to pass `is_symptom`:

```python
priority = compute_priority_score(state, severity, blast_radius, is_root_cause, is_symptom=is_symptom)
```

**Commit:** `fix(lifecycle): guard empty graph, cap symptom priority`

---

## Task 5: Fix temporal_analyzer.py (High #11)

**Files:**
- Modify: `backend/src/agents/cluster/temporal_analyzer.py`

**Fix: Log timestamp parse failures instead of silently returning 0 (High #11)**

```python
def _parse_timestamp(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError) as e:
        logger.warning("Failed to parse timestamp '%s': %s", ts, e)
        return None


def _seconds_since(ts: str) -> int:
    dt = _parse_timestamp(ts)
    if not dt:
        return -1  # Return -1 to distinguish "unknown" from "just now"
    now = datetime.now(timezone.utc)
    return max(0, int((now - dt).total_seconds()))
```

Then update downstream usage to handle -1:

```python
# In compute_temporal_attributes, when building resource_temporals:
event_age = _seconds_since(sig.timestamp)
if event_age < 0:
    event_age = 3600  # Default to 1 hour if timestamp unparseable (safe middle ground)
    logger.debug("Using default age for %s (unparseable timestamp)", sig.resource_key)
```

**Commit:** `fix(temporal): log timestamp failures, use safe default age`

---

## Task 6: Fix critic_agent.py (High #10 + Medium #19)

**Files:**
- Modify: `backend/src/agents/cluster/critic_agent.py`
- Create: `backend/src/agents/cluster/graph_utils.py` (extract shared utilities)

**Fixes:**

**6a. Extract bfs_reachable to shared graph_utils.py (High #10)**

Create `backend/src/agents/cluster/graph_utils.py` with `bfs_reachable` and `graph_has_path` extracted from `diagnostic_graph_builder.py`:

```python
"""Shared graph traversal utilities for diagnostic pipeline."""
from __future__ import annotations
from collections import defaultdict, deque
from src.agents.cluster.state import DiagnosticGraph


def bfs_reachable(graph: DiagnosticGraph, start_id: str) -> set[str]:
    """BFS to find all reachable nodes from start."""
    adj: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        adj[edge.from_id].add(edge.to_id)
    visited = set()
    queue = deque([start_id])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adj.get(current, set()):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited


def graph_has_path(graph: DiagnosticGraph, from_id: str, to_id: str) -> bool:
    """Check if a directed path exists between two nodes."""
    return to_id in bfs_reachable(graph, from_id)
```

Update imports in:
- `critic_agent.py`: change `from src.agents.cluster.diagnostic_graph_builder import bfs_reachable` to `from src.agents.cluster.graph_utils import bfs_reachable`
- `diagnostic_graph_builder.py`: change local functions to import from `graph_utils`
- `hypothesis_engine.py`: change import to `from src.agents.cluster.graph_utils import graph_has_path, bfs_reachable`

**6b. Fix timestamp string comparison in temporal consistency check (Medium #19)**

```python
# In the temporal consistency check, replace string comparison:
#   if fs < root_first:
# With proper datetime comparison:

def _compare_timestamps(ts1: str, ts2: str) -> int:
    """Compare two ISO timestamps. Returns -1, 0, or 1."""
    try:
        dt1 = datetime.fromisoformat(ts1.replace("Z", "+00:00"))
        dt2 = datetime.fromisoformat(ts2.replace("Z", "+00:00"))
        if dt1 < dt2: return -1
        if dt1 > dt2: return 1
        return 0
    except (ValueError, TypeError):
        return 0  # Can't compare, assume equal

# Then use:
if _compare_timestamps(fs, root_first) < 0:
    # Effect before cause — temporal violation
```

Add `from datetime import datetime` import if not already present.

**Commit:** `fix(critic): extract graph_utils, fix timestamp comparison`

---

## Task 7: Fix command_validator.py + solution_validator.py (Medium #8, #9, #20)

**Files:**
- Modify: `backend/src/agents/cluster/command_validator.py`
- Modify: `backend/src/agents/cluster/solution_validator.py`

**Fixes:**

**7a. Fix forbidden command check substring matching (Medium #8)**

```python
import re

def check_forbidden(command: str) -> tuple[bool, str]:
    cmd_lower = command.lower().strip()
    for forbidden in FORBIDDEN_COMMANDS:
        # Use word boundary matching instead of substring
        pattern = r'\b' + re.escape(forbidden) + r'\b'
        if re.search(pattern, cmd_lower):
            return True, f"Blocked: '{forbidden}' requires manual execution"
    return False, ""
```

**7b. Handle missing/empty hypothesis in confidence calculation (Medium #9)**

```python
def compute_remediation_confidence(step, hypothesis, simulation, risk):
    if not hypothesis or not hypothesis.get("hypothesis_id"):
        logger.debug("No hypothesis available for remediation confidence")
        return 0.3  # Default: speculative without hypothesis context

    score = hypothesis.get("confidence", 0) * 0.4
    # ... rest of function unchanged
```

**7c. Move low-confidence remediations to speculative list instead of dropping (Medium #20)**

In `solution_validator.py`:

```python
# Instead of:
#   if conf >= 0.3 or not validated.get("validation"):
#       validated_immediate.append(validated)

# Change to:
speculative = []
for step in remediation.get("immediate", []):
    validated = validate_solution_step(step, topology, domain_reports, hypothesis_selection)
    conf = validated.get("validation", {}).get("remediation_confidence", 0)
    if conf >= 0.3 or not validated.get("validation"):
        validated_immediate.append(validated)
    else:
        speculative.append(validated)

remediation["immediate"] = validated_immediate
remediation["speculative"] = speculative  # Visible to frontend with low-confidence label
```

**Commit:** `fix(validator): word-boundary forbidden check, handle missing hypothesis, keep speculative fixes`

---

## Task 8: Fix synthesizer.py (Medium #22, #24)

**Files:**
- Modify: `backend/src/agents/cluster/synthesizer.py`

**Fixes:**

**8a. Log warnings when critical health report fields are empty (Medium #22)**

After building the health_report:

```python
# Validation logging
if not health_report.remediation.get("immediate"):
    logger.warning("No immediate remediations in health report")
if not health_report.causal_chains:
    logger.warning("No causal chains identified in health report")
if health_report.data_completeness < 0.5:
    logger.warning("Low data completeness: %.0f%%", health_report.data_completeness * 100)
```

**8b. Add timeout to individual LLM calls (Medium #24)**

```python
import asyncio

# In _llm_causal_reasoning:
try:
    response = await asyncio.wait_for(
        client.chat(prompt=prompt, system=system, max_tokens=3000, temperature=0.1),
        timeout=30  # 30s per LLM call
    )
except asyncio.TimeoutError:
    logger.warning("LLM causal reasoning timed out after 30s")
    return {"causal_chains": [], "uncorrelated_findings": []}

# Same pattern in _llm_verdict:
try:
    response = await asyncio.wait_for(
        client.chat(prompt=prompt, system=system, max_tokens=2000, temperature=0.1),
        timeout=30
    )
except asyncio.TimeoutError:
    logger.warning("LLM verdict timed out after 30s")
    return {default verdict dict}
```

**Commit:** `fix(synthesizer): add LLM call timeouts, log empty report fields`

---

## Task 9: Fix graph.py state + routes_v4.py API (Critical #4 + Medium #23)

**Files:**
- Modify: `backend/src/agents/cluster/graph.py`
- Modify: `backend/src/api/routes_v4.py`

**Fixes:**

**9a. Remove unused session_budget/llm_telemetry from State TypedDict (Critical #4)**

These fields are never written to state by any node — budget and telemetry flow through `config["configurable"]` instead.

```python
# Remove these two lines from State TypedDict:
#     session_budget: Optional[dict]
#     llm_telemetry: Optional[dict]
```

**9b. Add hypothesis_selection to API findings response (Medium #23)**

In the cluster findings endpoint, add:

```python
"hypothesis_selection": health_report.get("hypothesis_selection") if health_report else None,
```

**Commit:** `fix(graph): remove dead state fields, add hypothesis_selection to API`

---

## Task 10: Fix traced_node.py + signal_normalizer.py (Medium #15, #17)

**Files:**
- Modify: `backend/src/agents/cluster/traced_node.py`
- Modify: `backend/src/agents/cluster/signal_normalizer.py`

**Fixes:**

**10a. Return empty placeholder fields on timeout (Medium #15)**

In `traced_node.py`, when a non-agent node times out, include empty defaults for known output fields:

```python
# Known output fields per node (for graceful timeout)
_NODE_DEFAULT_OUTPUTS = {
    "signal_normalizer": {"normalized_signals": []},
    "failure_pattern_matcher": {"pattern_matches": []},
    "temporal_analyzer": {"temporal_analysis": {}},
    "diagnostic_graph_builder": {"diagnostic_graph": {"nodes": {}, "edges": []}},
    "issue_lifecycle_classifier": {"diagnostic_issues": []},
    "hypothesis_engine": {"ranked_hypotheses": [], "hypotheses_by_issue": {}, "hypothesis_selection": {"root_causes": [], "selection_method": "timeout", "llm_reasoning_needed": False}},
}

# In the timeout handler, merge defaults:
defaults = _NODE_DEFAULT_OUTPUTS.get(func.__name__, {})
return {**defaults, "_trace": [trace]}
```

**10b. Add structured signal_type field support to signal_normalizer (Medium #17)**

The signal normalizer currently relies on text substring matching. Add a fast-path that uses structured data from anomaly fields before falling back to text matching:

```python
# At the top of the anomaly loop in extract_signals:
for anomaly in report.get("anomalies", []):
    # Fast path: use structured signal_type if domain agent provided it
    explicit_type = anomaly.get("signal_type")
    if explicit_type:
        signals.append(_make_signal(
            explicit_type, ref, domain,
            SIGNAL_RELIABILITY.get(explicit_type, "k8s_event_warning"),
            namespace=ns
        ))
        continue

    # Slow path: infer from description text (existing code)
    desc = anomaly.get("description", "").lower()
    # ... existing text matching code ...
```

This allows future agents to emit structured signal types, while keeping backward compatibility.

**Commit:** `fix(traced_node): timeout defaults, signal_normalizer structured fast-path`

---

## Task 11: Fix mock_client.py fixture gap (Medium #18)

**Files:**
- Modify: `backend/src/agents/cluster_client/mock_client.py`

**Fix: Ensure mock anomaly descriptions match signal extraction patterns**

The mock heuristic analyzers in domain agents (node_agent, network_agent, etc.) generate anomaly descriptions. These descriptions need to contain the keywords that `signal_normalizer` looks for.

Update the mock fixture data to include realistic failure descriptions:

In the mock fixtures (loaded from `cluster_node_mock.json` etc.), ensure the pod/event data includes:
- A pod with status "CrashLoopBackOff" and high restarts
- A node with DiskPressure condition
- An event with reason "FailedScheduling"
- A service with 0 endpoints

This is a fixture data update, not code logic. Read the current fixture files and add failure scenario data that exercises the signal extraction pipeline.

If fixtures are JSON files, add entries like:
```json
{"name": "failing-pod", "namespace": "production", "status": "CrashLoopBackOff", "restarts": 45}
{"name": "worker-3", "status": "NotReady", "disk_pressure": true}
```

**Commit:** `fix(mock): add failure scenario data to exercise signal pipeline`

---

## Implementation Order

Tasks are independent and can be parallelized:
- **Group 1 (Critical):** Tasks 1, 9 — hypothesis engine + graph state
- **Group 2 (High):** Tasks 2, 3, 4, 5, 6 — patterns, graph builder, lifecycle, temporal, critic
- **Group 3 (Medium):** Tasks 7, 8, 10, 11 — validators, synthesizer, traced_node, mock

All 11 tasks, ~27 fixes total.
