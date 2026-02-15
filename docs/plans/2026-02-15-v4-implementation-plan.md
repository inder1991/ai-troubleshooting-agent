# AI SRE Platform v4.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the AI troubleshooting system from a linear pipeline to a Supervisor + ReAct multi-agent architecture with cross-validation, Prometheus metrics, K8s health checks, distributed tracing, interactive chat UI, and evidence-backed diagnostics.

**Architecture:** Supervisor state machine orchestrates 6 specialized ReAct agents (Log, Metrics, K8s, Tracing, Code Navigator, Fix Generator) with a read-only Critic agent for cross-validation. All LLM calls use Anthropic Claude exclusively.

**Tech Stack:** Python/FastAPI, LangGraph, Anthropic SDK, Pydantic, Kubernetes Python client, Prometheus HTTP API, React/TypeScript, Recharts, Mermaid

**Design Doc:** `docs/plans/2026-02-15-supervisor-react-architecture-design.md`

---

## Phase 1: Foundation — Shared Models & Anthropic Client

### Task 1: Create shared Pydantic schemas

**Files:**
- Create: `backend/src/models/schemas.py`
- Test: `backend/tests/test_schemas.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_schemas.py
import pytest
from src.models.schemas import (
    Breadcrumb, NegativeFinding, Finding, CriticVerdict,
    TokenUsage, TaskEvent, ErrorPattern, LogEvidence,
    MetricAnomaly, DataPoint, TimeRange, PodHealthStatus,
    K8sEvent, SpanInfo, ImpactedFile, LineRange, FixArea,
    DiagnosticPhase, DiagnosticState
)
from datetime import datetime


def test_breadcrumb_creation():
    b = Breadcrumb(
        agent_name="log_agent",
        action="queried_elasticsearch",
        source_type="log",
        source_reference="app-logs-2025.12.26, ID: R3znW5",
        raw_evidence="ConnectionTimeout after 30000ms",
        timestamp=datetime.now()
    )
    assert b.agent_name == "log_agent"
    assert b.source_type == "log"


def test_finding_with_confidence_score():
    f = Finding(
        finding_id="f1",
        agent_name="log_agent",
        category="database_timeout",
        summary="DB connection timed out",
        confidence_score=85,
        severity="critical",
        breadcrumbs=[],
        negative_findings=[]
    )
    assert f.confidence_score == 85
    assert f.severity == "critical"


def test_diagnostic_state_phases():
    assert DiagnosticPhase.INITIAL == "initial"
    assert DiagnosticPhase.DIAGNOSIS_COMPLETE == "diagnosis_complete"


def test_error_pattern_priority():
    p = ErrorPattern(
        pattern_id="p1",
        exception_type="ConnectionTimeout",
        error_message="DB timeout after 30s",
        frequency=47,
        severity="critical",
        affected_components=["order-service"],
        sample_logs=[],
        confidence_score=87,
        priority_rank=1,
        priority_reasoning="Highest frequency and severity"
    )
    assert p.priority_rank == 1


def test_token_usage():
    t = TokenUsage(
        agent_name="log_agent",
        input_tokens=1500,
        output_tokens=800,
        total_tokens=2300
    )
    assert t.total_tokens == 2300
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_schemas.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/models/schemas.py` with all shared Pydantic models from the design doc: Breadcrumb, NegativeFinding, Finding, CriticVerdict, TokenUsage, TaskEvent, ErrorPattern, LogEvidence, MetricAnomaly, DataPoint, TimeRange, PodHealthStatus, K8sEvent, SpanInfo, ImpactedFile, LineRange, FixArea, DiagnosticPhase (Enum), DiagnosticState, LogAnalysisResult, MetricsAnalysisResult, K8sAnalysisResult, TraceAnalysisResult, CodeAnalysisResult, SessionTokenSummary.

**Step 4: Run test to verify it passes**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_schemas.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/models/schemas.py backend/tests/test_schemas.py
git commit -m "feat: add shared Pydantic schemas for v4 multi-agent architecture"
```

---

### Task 2: Create Anthropic client wrapper with token tracking

**Files:**
- Create: `backend/src/utils/llm_client.py`
- Test: `backend/tests/test_llm_client.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_llm_client.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.utils.llm_client import AnthropicClient
from src.models.schemas import TokenUsage


@pytest.mark.asyncio
async def test_client_tracks_tokens():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="test response")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch("src.utils.llm_client.AsyncAnthropic") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_instance

        client = AnthropicClient()
        result = await client.chat("Analyze this log")
        assert result.text == "test response"
        assert client.get_total_usage().total_tokens == 150


@pytest.mark.asyncio
async def test_client_accumulates_tokens():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="response")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch("src.utils.llm_client.AsyncAnthropic") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_instance

        client = AnthropicClient(agent_name="log_agent")
        await client.chat("Query 1")
        await client.chat("Query 2")
        usage = client.get_total_usage()
        assert usage.input_tokens == 200
        assert usage.output_tokens == 100
        assert usage.agent_name == "log_agent"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_llm_client.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/utils/llm_client.py`: AnthropicClient class wrapping `anthropic.AsyncAnthropic`. Methods: `chat(prompt, system=None, messages=None)`, `get_total_usage() -> TokenUsage`, `reset_usage()`. Tracks cumulative input/output tokens. Uses `ANTHROPIC_API_KEY` env var. Model: `claude-sonnet-4-5-20250929`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_llm_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/utils/llm_client.py backend/tests/test_llm_client.py
git commit -m "feat: add Anthropic client wrapper with token tracking"
```

---

### Task 3: Create WebSocket event emitter for real-time task logging

**Files:**
- Modify: `backend/src/api/websocket.py`
- Create: `backend/src/utils/event_emitter.py`
- Test: `backend/tests/test_event_emitter.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_event_emitter.py
import pytest
from unittest.mock import AsyncMock
from src.utils.event_emitter import EventEmitter
from src.models.schemas import TaskEvent


@pytest.mark.asyncio
async def test_emit_task_event():
    mock_ws = AsyncMock()
    emitter = EventEmitter(session_id="test-123", websocket_manager=mock_ws)
    await emitter.emit("log_agent", "started", "Querying Elasticsearch...")
    mock_ws.send_message.assert_called_once()
    call_args = mock_ws.send_message.call_args
    assert call_args[0][0] == "test-123"
    msg = call_args[0][1]
    assert msg["type"] == "task_event"
    assert msg["data"]["agent_name"] == "log_agent"


@pytest.mark.asyncio
async def test_emit_collects_events():
    mock_ws = AsyncMock()
    emitter = EventEmitter(session_id="test-123", websocket_manager=mock_ws)
    await emitter.emit("log_agent", "started", "Starting analysis")
    await emitter.emit("log_agent", "success", "Found 847 entries")
    assert len(emitter.get_all_events()) == 2
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_event_emitter.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/utils/event_emitter.py`: EventEmitter class. Methods: `emit(agent_name, event_type, message, details=None)`, `get_all_events() -> list[TaskEvent]`. Sends TaskEvent via WebSocket and stores locally.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_event_emitter.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/utils/event_emitter.py backend/tests/test_event_emitter.py
git commit -m "feat: add event emitter for real-time task logging"
```

---

## Phase 2: Log Analysis Agent (ReAct Rebuild)

### Task 4: Create ReAct base class for all agents

**Files:**
- Create: `backend/src/agents/react_base.py`
- Test: `backend/tests/test_react_base.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_react_base.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.react_base import ReActAgent


class TestAgent(ReActAgent):
    """Concrete test implementation"""
    async def _define_tools(self):
        return [{"name": "search_logs", "description": "Search ES logs"}]

    async def _build_system_prompt(self):
        return "You are a test agent."

    async def _build_initial_prompt(self, context):
        return "Analyze this."


@pytest.mark.asyncio
async def test_react_agent_tracks_steps():
    agent = TestAgent(agent_name="test_agent")
    assert agent.agent_name == "test_agent"
    assert len(agent.breadcrumbs) == 0
    assert len(agent.negative_findings) == 0


def test_react_agent_add_breadcrumb():
    agent = TestAgent(agent_name="test_agent")
    agent.add_breadcrumb(
        action="searched_logs",
        source_type="log",
        source_reference="app-logs-2025",
        raw_evidence="ConnectionTimeout"
    )
    assert len(agent.breadcrumbs) == 1
    assert agent.breadcrumbs[0].agent_name == "test_agent"


def test_react_agent_add_negative_finding():
    agent = TestAgent(agent_name="test_agent")
    agent.add_negative_finding(
        what_was_checked="DB logs for trace abc-123",
        result="Zero errors found",
        implication="Issue is NOT in DB layer",
        source_reference="db-logs-2025"
    )
    assert len(agent.negative_findings) == 1
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_react_base.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/agents/react_base.py`: Abstract `ReActAgent` class. Fields: `agent_name`, `llm_client` (AnthropicClient), `event_emitter`, `breadcrumbs`, `negative_findings`, `max_iterations` (default 10). Abstract methods: `_define_tools()`, `_build_system_prompt()`, `_build_initial_prompt(context)`. Concrete methods: `add_breadcrumb(...)`, `add_negative_finding(...)`, `get_token_usage()`, `async run(context, event_emitter) -> dict`. The `run` method implements the ReAct loop: reason -> pick tool -> execute -> observe -> repeat until done or max iterations.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_react_base.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/react_base.py backend/tests/test_react_base.py
git commit -m "feat: add ReAct base class for all specialized agents"
```

---

### Task 5: Rebuild Log Analysis Agent with ReAct pattern

**Files:**
- Create: `backend/src/agents/log_agent.py` (new file, keep old `agent1_*` for reference)
- Test: `backend/tests/test_log_agent.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_log_agent.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.agents.log_agent import LogAnalysisAgent
from src.models.schemas import LogAnalysisResult


@pytest.mark.asyncio
async def test_log_agent_returns_structured_result():
    mock_emitter = AsyncMock()
    with patch("src.agents.log_agent.AnthropicClient") as mock_llm:
        mock_client = AsyncMock()
        mock_client.get_total_usage.return_value = MagicMock(
            agent_name="log_agent", input_tokens=100, output_tokens=50, total_tokens=150
        )
        # Mock the ReAct loop to return a pre-built result
        mock_llm.return_value = mock_client

        agent = LogAnalysisAgent()
        # Test that the agent produces a LogAnalysisResult
        result = agent._parse_patterns_from_logs([
            {"level": "ERROR", "message": "ConnectionTimeout after 30s", "timestamp": "2025-12-26T14:00:33", "service": "order-service"},
            {"level": "ERROR", "message": "ConnectionTimeout after 30s", "timestamp": "2025-12-26T14:00:34", "service": "order-service"},
            {"level": "ERROR", "message": "NullPointerException in UserService", "timestamp": "2025-12-26T14:00:35", "service": "user-service"},
        ])
        assert len(result) >= 2  # At least 2 distinct patterns


def test_log_agent_groups_by_exception_type():
    agent = LogAnalysisAgent()
    logs = [
        {"level": "ERROR", "message": "ConnectionTimeout after 30s", "service": "order-service"},
        {"level": "ERROR", "message": "ConnectionTimeout after 30s", "service": "order-service"},
        {"level": "ERROR", "message": "ConnectionTimeout after 25s", "service": "payment-service"},
        {"level": "ERROR", "message": "NullPointerException at line 45", "service": "user-service"},
    ]
    patterns = agent._parse_patterns_from_logs(logs)
    # Should group the 3 ConnectionTimeout together and NullPointer separately
    assert any(p["exception_type"] == "ConnectionTimeout" for p in patterns)
    assert any(p["exception_type"] == "NullPointerException" for p in patterns)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_log_agent.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/agents/log_agent.py`: `LogAnalysisAgent(ReActAgent)`. Tools: `search_elasticsearch(query, index, time_range)`, `search_by_error_message(message, index)`, `search_by_trace_id(trace_id, index)`, `get_log_context(log_id, index, before=5, after=5)`. Key methods: `_parse_patterns_from_logs(logs)` groups by exception type + fuzzy message similarity. The ReAct loop: query ERROR logs → group into patterns → query WARN logs before errors → search by trace_id if available → build negative findings for empty queries → call LLM to prioritize patterns. Output: `LogAnalysisResult`.

Reuse `LogFingerprinter`, `BreadcrumbExtractor`, `StackTraceParser` from existing `agent1_log_analyzer.py`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_log_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/log_agent.py backend/tests/test_log_agent.py
git commit -m "feat: rebuild log analysis agent with ReAct pattern and error pattern detection"
```

---

## Phase 3: Metrics Agent (Prometheus)

### Task 6: Rebuild Metrics Agent with ReAct pattern and chart data

**Files:**
- Create: `backend/src/agents/metrics_agent.py` (new ReAct version)
- Test: `backend/tests/test_metrics_agent.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_metrics_agent.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from src.agents.metrics_agent import MetricsAgent


def test_spike_detection():
    agent = MetricsAgent()
    # Simulate time-series data with a spike
    data_points = [
        {"timestamp": 1000, "value": 30.0},  # normal
        {"timestamp": 1060, "value": 32.0},  # normal
        {"timestamp": 1120, "value": 95.0},  # spike
        {"timestamp": 1180, "value": 93.0},  # spike
        {"timestamp": 1240, "value": 31.0},  # normal
    ]
    spikes = agent._detect_spikes(data_points, baseline_threshold=2.0)
    assert len(spikes) >= 1
    assert spikes[0]["peak_value"] == 95.0


def test_build_promql_queries():
    agent = MetricsAgent()
    queries = agent._build_default_queries(
        namespace="prod",
        service_name="order-service"
    )
    assert any("cpu" in q["query"].lower() for q in queries)
    assert any("memory" in q["query"].lower() for q in queries)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_metrics_agent.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/agents/metrics_agent.py`: `MetricsAgent(ReActAgent)`. Tools: `query_prometheus(promql, start, end, step)`, `query_instant(promql)`. Key methods: `_build_default_queries(namespace, service_name)` returns CPU/memory/error-rate/latency PromQL queries, `_detect_spikes(data_points, baseline_threshold)` detects anomalies by comparing to baseline mean+stddev. ReAct loop: run default queries → detect spikes → LLM decides if more queries needed based on findings → build chart data with highlights. Uses `PROMETHEUS_URL` env var. Output: `MetricsAnalysisResult`.

Reuse Prometheus HTTP client from existing `agent4_metrics_analyzer.py`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_metrics_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/metrics_agent.py backend/tests/test_metrics_agent.py
git commit -m "feat: add Prometheus metrics agent with spike detection and chart data"
```

---

## Phase 4: K8s/OpenShift Agent

### Task 7: Create K8s/OpenShift Agent

**Files:**
- Create: `backend/src/agents/k8s_agent.py`
- Test: `backend/tests/test_k8s_agent.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_k8s_agent.py
import pytest
from unittest.mock import MagicMock, patch
from src.agents.k8s_agent import K8sAgent


def test_detect_crashloopbackoff():
    agent = K8sAgent()
    pod_statuses = [
        {"name": "order-svc-abc", "phase": "Running", "restart_count": 0,
         "container_statuses": [{"state": {"running": {}}}]},
        {"name": "order-svc-def", "phase": "Running", "restart_count": 8,
         "container_statuses": [{"state": {"waiting": {"reason": "CrashLoopBackOff"}}}]},
    ]
    result = agent._analyze_pod_statuses(pod_statuses)
    assert result["is_crashloop"] is True
    assert result["total_restarts"] == 8


def test_detect_oom_killed():
    agent = K8sAgent()
    pod_statuses = [
        {"name": "order-svc-abc", "phase": "Running", "restart_count": 3,
         "container_statuses": [{"last_state": {"terminated": {"reason": "OOMKilled"}}}]},
    ]
    result = agent._analyze_pod_statuses(pod_statuses)
    assert any("OOMKilled" in f for f in result["termination_reasons"])
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_k8s_agent.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/agents/k8s_agent.py`: `K8sAgent(ReActAgent)`. Tools: `get_pod_status(namespace, label_selector)`, `get_events(namespace, field_selector)`, `get_deployment(namespace, name)`, `get_resource_specs(namespace, name)`. Key methods: `_analyze_pod_statuses(pods)`. ReAct loop: check pod status → check restarts/OOM → get events → get resource limits → cross-reference with metrics if available. Uses `kubernetes` Python client with configurable API URL and token. Output: `K8sAnalysisResult`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_k8s_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/k8s_agent.py backend/tests/test_k8s_agent.py
git commit -m "feat: add K8s/OpenShift agent for pod health and cluster events"
```

---

## Phase 5: Tracing Agent (Jaeger + ELK Fallback)

### Task 8: Create Tracing Agent

**Files:**
- Create: `backend/src/agents/tracing_agent.py`
- Test: `backend/tests/test_tracing_agent.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_tracing_agent.py
import pytest
from src.agents.tracing_agent import TracingAgent


def test_reconstruct_chain_from_elk_logs():
    agent = TracingAgent()
    logs = [
        {"timestamp": "2025-12-26T14:00:01", "service": "api-gateway", "message": "Received request", "trace_id": "abc"},
        {"timestamp": "2025-12-26T14:00:02", "service": "order-service", "message": "Processing order", "trace_id": "abc"},
        {"timestamp": "2025-12-26T14:00:03", "service": "inventory-service", "message": "Checking stock", "trace_id": "abc"},
        {"timestamp": "2025-12-26T14:00:33", "service": "inventory-service", "message": "ConnectionTimeout to postgres", "trace_id": "abc", "level": "ERROR"},
    ]
    chain = agent._reconstruct_chain_from_logs(logs)
    assert len(chain) == 4
    assert chain[0]["service_name"] == "api-gateway"
    assert chain[-1]["status"] == "error"


def test_jaeger_fallback_to_elk():
    agent = TracingAgent()
    # When Jaeger returns None, should set source to elasticsearch
    assert agent._should_fallback_to_elk(None) is True
    assert agent._should_fallback_to_elk({"data": []}) is True
    assert agent._should_fallback_to_elk({"data": [{"spans": []}]}) is True
    assert agent._should_fallback_to_elk({"data": [{"spans": [{"spanID": "s1"}]}]}) is False
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_tracing_agent.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/agents/tracing_agent.py`: `TracingAgent(ReActAgent)`. Tools: `query_jaeger(trace_id)`, `query_elasticsearch_trace(trace_id, field_names, indices)`. Key methods: `_should_fallback_to_elk(jaeger_response)`, `_reconstruct_chain_from_logs(logs)`, `_parse_jaeger_spans(data)`. ReAct loop: query Jaeger → if no data/invalid, fallback to ELK → search by trace_id/correlation_id/request_id → reconstruct chain → identify failure point. Uses `TRACING_URL` and `ELASTICSEARCH_URL` env vars. Output: `TraceAnalysisResult`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_tracing_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/tracing_agent.py backend/tests/test_tracing_agent.py
git commit -m "feat: add tracing agent with Jaeger-first, ELK-fallback strategy"
```

---

## Phase 6: Code Navigator Agent (ReAct Rebuild)

### Task 9: Rebuild Code Navigator with multi-file impact analysis

**Files:**
- Create: `backend/src/agents/code_agent.py` (new, keep old `agent2_*` for reference)
- Test: `backend/tests/test_code_agent.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_code_agent.py
import pytest
import tempfile
import os
from src.agents.code_agent import CodeNavigatorAgent


def test_find_callers(tmp_path):
    # Create test files
    main_file = tmp_path / "main.py"
    main_file.write_text("from service import process_order\n\ndef handler():\n    process_order(data)\n")
    svc_file = tmp_path / "service.py"
    svc_file.write_text("def process_order(data):\n    db.get_connection()\n    return data\n")

    agent = CodeNavigatorAgent()
    callers = agent._find_callers(str(tmp_path), "process_order")
    assert len(callers) >= 1
    assert any("main.py" in c["file_path"] for c in callers)


def test_classify_impact_type():
    agent = CodeNavigatorAgent()
    assert agent._classify_impact("direct error location") == "direct_error"
    assert agent._classify_impact("calls the broken function") == "caller"
    assert agent._classify_impact("configuration file") == "config"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_code_agent.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/agents/code_agent.py`: `CodeNavigatorAgent(ReActAgent)`. Tools: `search_file(repo_path, filename)`, `read_file(path, start_line, end_line)`, `search_code(repo_path, pattern)`, `find_callers(repo_path, function_name)`, `find_callees(repo_path, function_name)`. Key methods: `_find_callers(repo_path, func_name)`, `_classify_impact(description)`. ReAct loop: find error file → read function → find callers (N levels) → find callees → find config files → find test files → build dependency graph → generate Mermaid diagram. Output: `CodeAnalysisResult`.

Reuse `CodebaseMapper`, `ContextRetriever`, `CallChainAnalyzer` from existing `agent2_code_navigator.py`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_code_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/code_agent.py backend/tests/test_code_agent.py
git commit -m "feat: rebuild code navigator with ReAct pattern and multi-file impact analysis"
```

---

## Phase 7: Critic Agent

### Task 10: Create Critic Agent (read-only cross-validator)

**Files:**
- Create: `backend/src/agents/critic_agent.py`
- Test: `backend/tests/test_critic_agent.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_critic_agent.py
import pytest
from src.agents.critic_agent import CriticAgent
from src.models.schemas import Finding, Breadcrumb, MetricsAnalysisResult, MetricAnomaly
from datetime import datetime


def test_critic_detects_contradiction():
    critic = CriticAgent()
    finding = Finding(
        finding_id="f1", agent_name="log_agent",
        category="database_down", summary="Database is down",
        confidence_score=80, severity="critical",
        breadcrumbs=[], negative_findings=[]
    )
    # Metrics show DB is healthy
    metrics_context = {
        "db_cpu": {"value": 5.0, "status": "healthy"},
        "db_connections": {"value": 10, "status": "normal"}
    }
    verdict = critic._evaluate_finding(finding, metrics_context=metrics_context)
    assert verdict.verdict == "challenged"


def test_critic_validates_consistent_finding():
    critic = CriticAgent()
    finding = Finding(
        finding_id="f2", agent_name="log_agent",
        category="oom_killed", summary="Pod OOM killed",
        confidence_score=90, severity="critical",
        breadcrumbs=[], negative_findings=[]
    )
    k8s_context = {"oom_kills": 3, "memory_percent": 95}
    verdict = critic._evaluate_finding(finding, k8s_context=k8s_context)
    assert verdict.verdict == "validated"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_critic_agent.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/agents/critic_agent.py`: `CriticAgent`. NOT a ReAct agent — simpler. Methods: `async validate(finding, diagnostic_state) -> CriticVerdict`, `_evaluate_finding(finding, **agent_contexts)`. Uses LLM to compare a finding against all other agent data. Read-only — no tool access that modifies state. Output: `CriticVerdict`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_critic_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/critic_agent.py backend/tests/test_critic_agent.py
git commit -m "feat: add Critic agent for cross-validation of findings"
```

---

## Phase 8: Supervisor Agent

### Task 11: Create Supervisor Agent with state machine

**Files:**
- Create: `backend/src/agents/supervisor.py`
- Test: `backend/tests/test_supervisor.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_supervisor.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agents.supervisor import SupervisorAgent
from src.models.schemas import DiagnosticState, DiagnosticPhase, LogAnalysisResult, ErrorPattern


def test_supervisor_initial_dispatch():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.INITIAL,
        service_name="order-service", time_window={"start": "now-1h", "end": "now"},
        all_findings=[], all_negative_findings=[], all_breadcrumbs=[],
        critic_verdicts=[], token_usage=[], task_events=[],
        supervisor_reasoning=[], agents_completed=[], agents_pending=[],
        overall_confidence=0
    )
    next_agents = supervisor._decide_next_agents(state)
    assert "log_agent" in next_agents


def test_supervisor_dispatches_parallel_after_logs():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.LOGS_ANALYZED,
        service_name="order-service", time_window={"start": "now-1h", "end": "now"},
        all_findings=[MagicMock(category="database_timeout", confidence_score=87)],
        all_negative_findings=[], all_breadcrumbs=[],
        critic_verdicts=[], token_usage=[], task_events=[],
        supervisor_reasoning=[], agents_completed=["log_agent"], agents_pending=[],
        overall_confidence=87
    )
    next_agents = supervisor._decide_next_agents(state)
    # Should dispatch metrics and potentially k8s in parallel
    assert "metrics_agent" in next_agents


def test_supervisor_low_confidence_asks_user():
    supervisor = SupervisorAgent()
    state = DiagnosticState(
        session_id="test-123", phase=DiagnosticPhase.LOGS_ANALYZED,
        service_name="order-service", time_window={"start": "now-1h", "end": "now"},
        all_findings=[MagicMock(confidence_score=40)],
        all_negative_findings=[], all_breadcrumbs=[],
        critic_verdicts=[], token_usage=[], task_events=[],
        supervisor_reasoning=[], agents_completed=["log_agent"], agents_pending=[],
        overall_confidence=40
    )
    action = supervisor._decide_action_for_confidence(state)
    assert action == "ask_user"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_supervisor.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/agents/supervisor.py`: `SupervisorAgent`. Manages `DiagnosticState` as a state machine. Methods: `async run(initial_input, event_emitter, ws_manager)`, `_decide_next_agents(state) -> list[str]`, `_decide_action_for_confidence(state) -> str`, `async _dispatch_agent(agent_name, state)`, `async _handle_user_message(message, state)`, `_update_phase(state)`. Uses LLM to make routing decisions. Dispatches agents, runs Critic after each, handles re-investigation if challenged.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_supervisor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/supervisor.py backend/tests/test_supervisor.py
git commit -m "feat: add Supervisor agent with state machine orchestration"
```

---

### Task 12: Create LangGraph workflow wiring

**Files:**
- Create: `backend/src/workflow.py`
- Test: `backend/tests/test_workflow.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_workflow.py
import pytest
from src.workflow import build_workflow


def test_workflow_has_required_nodes():
    graph = build_workflow()
    # Verify all agent nodes exist
    node_names = list(graph.nodes.keys())
    assert "supervisor" in node_names
    assert "log_agent" in node_names
    assert "metrics_agent" in node_names
    assert "k8s_agent" in node_names
    assert "tracing_agent" in node_names
    assert "code_agent" in node_names
    assert "critic" in node_names
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_workflow.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `backend/src/workflow.py`: `build_workflow() -> StateGraph`. Defines LangGraph StateGraph with DiagnosticState. Nodes: supervisor, log_agent, metrics_agent, k8s_agent, tracing_agent, code_agent, critic, fix_generator. Edges: supervisor routes conditionally to agents based on state. Each agent node wraps the agent's `run()` method and updates DiagnosticState.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_workflow.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/workflow.py backend/tests/test_workflow.py
git commit -m "feat: add LangGraph workflow with Supervisor routing"
```

---

## Phase 9: API Layer Updates

### Task 13: Update API for multi-session chat and enhanced WebSocket

**Files:**
- Modify: `backend/src/api/main.py`
- Modify: `backend/src/api/routes.py`
- Modify: `backend/src/api/models.py`
- Test: `backend/tests/test_api.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from src.api.main import create_app


@pytest.mark.asyncio
async def test_start_session_returns_session_id():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/troubleshoot/start", json={
            "serviceName": "order-service",
            "elkIndex": "app-logs-*",
            "timeframe": "1h"
        })
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data


@pytest.mark.asyncio
async def test_send_chat_message():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Start session first
        start_resp = await client.post("/api/troubleshoot/start", json={
            "serviceName": "order-service",
            "elkIndex": "app-logs-*",
            "timeframe": "1h"
        })
        session_id = start_resp.json()["session_id"]

        # Send chat message
        response = await client.post(f"/api/session/{session_id}/chat", json={
            "message": "What's the current status?"
        })
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_sessions():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/sessions")
        assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_api.py -v`
Expected: FAIL

**Step 3: Modify implementation**

Update `backend/src/api/models.py`: Add `ChatRequest(BaseModel)` with `message: str`, update `TroubleshootRequest` to include `serviceName`, `clusterUrl`, `namespace`, `repoUrl`, `traceId`. Add `ChatResponse`, `SessionListResponse`.

Update `backend/src/api/routes.py`: Add `POST /api/session/{session_id}/chat` endpoint that passes messages to Supervisor. Update `POST /api/troubleshoot/start` to use new workflow. Each session gets its own `DiagnosticState` and Supervisor instance.

Update `backend/src/api/main.py`: WebSocket now handles both task events and chat messages. Add message type routing.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/main.py backend/src/api/routes.py backend/src/api/models.py backend/tests/test_api.py
git commit -m "feat: update API for multi-session chat and Supervisor integration"
```

---

## Phase 10: Fix Generator Update

### Task 14: Update Fix Generator for new architecture

**Files:**
- Modify: `backend/src/agents/agent3/fix_generator.py`
- Test: `backend/tests/test_fix_generator.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_fix_generator.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agents.agent3.fix_generator import Agent3FixGenerator
from src.models.schemas import DiagnosticState, ErrorPattern


@pytest.mark.asyncio
async def test_fix_generator_uses_anthropic():
    with pytest.raises(Exception):
        # Should fail if no Anthropic client configured (no OpenAI)
        gen = Agent3FixGenerator(repo_path="/tmp/test")
        assert gen.llm_client is not None


def test_fix_generator_accepts_diagnostic_state():
    # Verify the interface accepts the new state model
    from src.agents.agent3.fix_generator import Agent3FixGenerator
    assert hasattr(Agent3FixGenerator, 'run_verification_phase')
```

**Step 2-5:** Update `fix_generator.py` to use `AnthropicClient` instead of LangChain OpenAI. Accept `DiagnosticState` as input context. Keep the two-phase approach (verification + action). Track tokens via `AnthropicClient.get_total_usage()`. Commit.

```bash
git add backend/src/agents/agent3/fix_generator.py backend/tests/test_fix_generator.py
git commit -m "feat: update fix generator to use Anthropic client and new state model"
```

---

## Phase 11: Frontend — Chat + Tabbed Dashboard

### Task 15: Create session sidebar and routing

**Files:**
- Create: `frontend/src/components/SessionSidebar.tsx`
- Modify: `frontend/src/App.tsx`
- Test: Manual — verify sessions list renders

**Step 1:** Create `SessionSidebar.tsx`: Lists sessions from `/api/sessions`. "New Chat" button. Click selects active session. Shows session service name and status.

**Step 2:** Update `App.tsx`: Add session state management. Route to active session. Layout: sidebar left, main content right.

**Step 3: Commit**

```bash
git add frontend/src/components/SessionSidebar.tsx frontend/src/App.tsx
git commit -m "feat: add session sidebar with multi-session support"
```

---

### Task 16: Create Chat tab component

**Files:**
- Create: `frontend/src/components/Chat/ChatTab.tsx`
- Create: `frontend/src/components/Chat/ChatMessage.tsx`
- Create: `frontend/src/components/Chat/InlineCard.tsx`
- Modify: `frontend/src/services/api.ts`

**Step 1:** Create `ChatTab.tsx`: Scrollable message list. Input box at bottom (always visible). Receives messages via WebSocket. Renders user messages and AI responses. AI responses can contain inline summary cards with "View in Dashboard" links.

**Step 2:** Create `ChatMessage.tsx`: Renders individual message. Supports markdown. Renders inline cards for agent summaries (error pattern count, metrics summary, k8s status badge).

**Step 3:** Create `InlineCard.tsx`: Compact card for inline agent results. Shows title, key stat, confidence badge, "View Details" button.

**Step 4:** Update `api.ts`: Add `sendChatMessage(sessionId, message)`, update WebSocket handler to route `chat_response` and `task_event` message types.

**Step 5: Commit**

```bash
git add frontend/src/components/Chat/ frontend/src/services/api.ts
git commit -m "feat: add Chat tab with inline agent summary cards"
```

---

### Task 17: Create Dashboard tab with agent result cards

**Files:**
- Create: `frontend/src/components/Dashboard/DashboardTab.tsx`
- Create: `frontend/src/components/Dashboard/ErrorPatternsCard.tsx`
- Create: `frontend/src/components/Dashboard/MetricsChartCard.tsx`
- Create: `frontend/src/components/Dashboard/K8sStatusCard.tsx`
- Create: `frontend/src/components/Dashboard/TraceCard.tsx`
- Create: `frontend/src/components/Dashboard/CodeImpactCard.tsx`
- Create: `frontend/src/components/Dashboard/DiagnosisSummaryCard.tsx`

**Step 1:** Install Recharts: `npm install recharts`

**Step 2:** Create `DashboardTab.tsx`: Grid layout. Renders cards dynamically as agents complete. Shows empty state with "Waiting for analysis..." until data arrives.

**Step 3:** Create `ErrorPatternsCard.tsx`: Table of patterns. Priority rank, severity badge, frequency, confidence. Primary highlighted. Secondary with "Investigate" button. Expandable rows show raw log breadcrumbs.

**Step 4:** Create `MetricsChartCard.tsx`: Recharts `LineChart` for CPU/memory. `ReferenceArea` components for spike highlighting. Annotations for correlation callouts. Toggle between metrics.

**Step 5:** Create `K8sStatusCard.tsx`: Pod status table. CrashLoopBackOff/OOMKilled badges. Events timeline. Resource mismatch callout.

**Step 6:** Create `TraceCard.tsx`: Mermaid sequence diagram (reuse existing `Mermaid.tsx`). Failed span in red. Latency annotations. Source label (Jaeger/ELK).

**Step 7:** Create `CodeImpactCard.tsx`: File tree with impact badges. Expandable code snippets with syntax highlighting. Mermaid dependency graph.

**Step 8:** Create `DiagnosisSummaryCard.tsx`: Root cause with confidence. Evidence breadcrumbs. Negative findings. Critic validation status.

**Step 9: Commit**

```bash
git add frontend/src/components/Dashboard/
git commit -m "feat: add Dashboard tab with all agent result cards and charts"
```

---

### Task 18: Create Activity Log tab

**Files:**
- Create: `frontend/src/components/ActivityLog/ActivityLogTab.tsx`
- Create: `frontend/src/components/ActivityLog/TokenSummary.tsx`

**Step 1:** Create `ActivityLogTab.tsx`: Scrollable log of TaskEvents received via WebSocket. Color-coded by event type (started=blue, success=green, warning=orange, error=red). Auto-scrolls to bottom. Shows timestamp, agent name, message.

**Step 2:** Create `TokenSummary.tsx`: Table showing tokens per agent. Grand total row. Displayed at bottom of Activity Log tab and in the status bar.

**Step 3: Commit**

```bash
git add frontend/src/components/ActivityLog/
git commit -m "feat: add Activity Log tab with token usage summary"
```

---

### Task 19: Wire tabs together and update main layout

**Files:**
- Create: `frontend/src/components/TabLayout.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/components/StatusBar.tsx`
- Modify: `frontend/src/types/index.ts`

**Step 1:** Create `TabLayout.tsx`: Tab bar with Chat / Dashboard / Activity Log. Input box persists across all tabs. Manages active tab state.

**Step 2:** Create `StatusBar.tsx`: Bottom bar showing: total tokens, current phase, overall confidence.

**Step 3:** Update `types/index.ts`: Add all new TypeScript interfaces matching backend Pydantic models (ErrorPattern, MetricAnomaly, PodHealthStatus, SpanInfo, etc.).

**Step 4:** Update `App.tsx`: Integrate SessionSidebar + TabLayout + StatusBar. WebSocket connection per session. Route data to correct tab components.

**Step 5: Commit**

```bash
git add frontend/src/components/TabLayout.tsx frontend/src/components/StatusBar.tsx frontend/src/types/index.ts frontend/src/App.tsx
git commit -m "feat: wire tabs, status bar, and session management together"
```

---

## Phase 12: Integration & Cleanup

### Task 20: Update requirements and environment config

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/.env.example`

**Step 1:** Update `requirements.txt`: Add `anthropic>=0.40.0`, `kubernetes>=28.0.0`, `recharts` (frontend). Remove `langchain-openai`, `openai`. Keep `langgraph`, `langchain-core`.

**Step 2:** Create `backend/.env.example` with all required env vars:
```
ANTHROPIC_API_KEY=
ELASTICSEARCH_URL=
PROMETHEUS_URL=
TRACING_URL=
OPENSHIFT_API_URL=
OPENSHIFT_TOKEN=
```

**Step 3: Commit**

```bash
git add backend/requirements.txt backend/.env.example
git commit -m "feat: update dependencies and add env config template"
```

---

### Task 21: End-to-end integration test

**Files:**
- Create: `backend/tests/test_integration.py`

**Step 1: Write integration test**

```python
# backend/tests/test_integration.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.agents.supervisor import SupervisorAgent
from src.models.schemas import DiagnosticState, DiagnosticPhase


@pytest.mark.asyncio
async def test_full_workflow_mock():
    """Test that Supervisor dispatches agents in correct order with mocked agents"""
    mock_emitter = AsyncMock()
    mock_ws = AsyncMock()

    with patch("src.agents.supervisor.LogAnalysisAgent") as mock_log, \
         patch("src.agents.supervisor.MetricsAgent") as mock_metrics, \
         patch("src.agents.supervisor.CriticAgent") as mock_critic:

        # Configure mock returns
        mock_log.return_value.run = AsyncMock(return_value={
            "primary_pattern": MagicMock(confidence_score=85),
            "secondary_patterns": [],
            "overall_confidence": 85
        })
        mock_metrics.return_value.run = AsyncMock(return_value={
            "anomalies": [],
            "overall_confidence": 75
        })
        mock_critic.return_value.validate = AsyncMock(return_value=MagicMock(verdict="validated"))

        supervisor = SupervisorAgent()
        state = DiagnosticState(
            session_id="integration-test",
            phase=DiagnosticPhase.INITIAL,
            service_name="order-service",
            time_window={"start": "now-1h", "end": "now"},
            all_findings=[], all_negative_findings=[], all_breadcrumbs=[],
            critic_verdicts=[], token_usage=[], task_events=[],
            supervisor_reasoning=[], agents_completed=[], agents_pending=[],
            overall_confidence=0
        )

        # Verify log agent is dispatched first
        next_agents = supervisor._decide_next_agents(state)
        assert "log_agent" in next_agents
```

**Step 2: Run test**

Run: `python -m pytest backend/tests/test_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/tests/test_integration.py
git commit -m "test: add end-to-end integration test for Supervisor workflow"
```

---

### Task 22: Remove hardcoded API keys and clean up old code

**Files:**
- Modify: `backend/src/orchestrator.py` — add deprecation comment, keep for reference
- Modify: `backend/src/agents/agent1_node.py` — remove hardcoded API keys
- Modify: `backend/src/agents/agent1_log_analyzer.py` — remove hardcoded API keys

**Step 1:** Replace all hardcoded API keys with `os.getenv()` calls.

**Step 2:** Add comment to old `orchestrator.py`: `# DEPRECATED: Replaced by supervisor.py + workflow.py in v4.0`

**Step 3: Commit**

```bash
git add backend/src/orchestrator.py backend/src/agents/agent1_node.py backend/src/agents/agent1_log_analyzer.py
git commit -m "chore: remove hardcoded API keys, deprecate old orchestrator"
```

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | 1-3 | Foundation: schemas, Anthropic client, event emitter |
| 2 | 4-5 | Log Agent: ReAct base + log analyzer rebuild |
| 3 | 6 | Metrics Agent: Prometheus + spike detection |
| 4 | 7 | K8s Agent: Pod health + OpenShift events |
| 5 | 8 | Tracing Agent: Jaeger + ELK fallback |
| 6 | 9 | Code Navigator: Multi-file impact analysis |
| 7 | 10 | Critic Agent: Cross-validation |
| 8 | 11-12 | Supervisor + LangGraph workflow |
| 9 | 13 | API: Multi-session chat + WebSocket |
| 10 | 14 | Fix Generator: Anthropic migration |
| 11 | 15-19 | Frontend: Chat + Dashboard + Activity Log |
| 12 | 20-22 | Integration, cleanup, config |

**Total: 22 tasks across 12 phases**
