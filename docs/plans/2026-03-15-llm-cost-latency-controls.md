# LLM Cost, Latency & Failure Mode Controls

## Problem

Tool-calling with up to 5 calls/agent × 4-6 agents × concurrent sessions creates:
- **Cost risk:** Each Sonnet call ~$0.01-0.03, Haiku ~$0.002. A deep cluster scan with 4 agents doing 5 tool calls each + synthesizer = ~$0.20-0.50 per scan. 50 concurrent users = $10-25/hour.
- **Latency risk:** Each LLM call is 2-8 seconds. 5 calls × 4 agents = potentially 40-80 seconds just in LLM calls, plus K8s API calls.
- **Failure risk:** LLM timeouts, rate limits, malformed responses, hallucinations — all cascade into broken diagnostics.

## Design: Session Budget System

### Budget Model

```python
@dataclass
class SessionBudget:
    max_llm_calls: int          # Total LLM API calls allowed
    max_tool_calls_per_agent: int  # Tool calls per individual agent
    max_tokens_input: int       # Total input tokens budget
    max_tokens_output: int      # Total output tokens budget
    max_total_latency_ms: int   # Total wall-clock time for all LLM calls
    current_llm_calls: int = 0
    current_tokens_input: int = 0
    current_tokens_output: int = 0
    current_latency_ms: int = 0

    def can_call(self) -> bool:
        return (self.current_llm_calls < self.max_llm_calls
                and self.current_tokens_input < self.max_tokens_input)

    def record(self, input_tokens: int, output_tokens: int, latency_ms: int):
        self.current_llm_calls += 1
        self.current_tokens_input += input_tokens
        self.current_tokens_output += output_tokens
        self.current_latency_ms += latency_ms

    def remaining_budget_pct(self) -> float:
        return 1.0 - (self.current_llm_calls / self.max_llm_calls)
```

### Scan Modes

| Mode | Use Case | Budget | Agent Tool Calls | Synthesizer | Est. Cost | Est. Time |
|---|---|---|---|---|---|---|
| **Quick Scan** | Routine health check, CI/CD gate | 8 total LLM calls, 3 tool calls/agent | Heuristic-only agents, LLM synthesizer only | Haiku | ~$0.02 | 15-30s |
| **Standard Scan** | Incident investigation | 20 total LLM calls, 4 tool calls/agent | Haiku agents with tools | Sonnet | ~$0.10 | 45-90s |
| **Deep Scan** | Root cause analysis, post-mortem | 40 total LLM calls, 5 tool calls/agent | Sonnet agents with tools | Sonnet | ~$0.30-0.50 | 90-180s |

```python
SCAN_BUDGETS = {
    "quick": SessionBudget(
        max_llm_calls=8,
        max_tool_calls_per_agent=0,  # Heuristic only for agents
        max_tokens_input=50_000,
        max_tokens_output=10_000,
        max_total_latency_ms=30_000,
    ),
    "standard": SessionBudget(
        max_llm_calls=20,
        max_tool_calls_per_agent=4,
        max_tokens_input=150_000,
        max_tokens_output=30_000,
        max_total_latency_ms=90_000,
    ),
    "deep": SessionBudget(
        max_llm_calls=40,
        max_tool_calls_per_agent=5,
        max_tokens_input=300_000,
        max_tokens_output=60_000,
        max_total_latency_ms=180_000,
    ),
}
```

### Cluster Size Adaptation

Large clusters need more budget but should also be smarter about what they query:

```python
def adapt_budget(base_budget: SessionBudget, cluster_size: dict) -> SessionBudget:
    """Adjust budget based on cluster size."""
    node_count = cluster_size.get("nodes", 0)
    pod_count = cluster_size.get("pods", 0)
    namespace_count = cluster_size.get("namespaces", 0)

    # Large clusters: increase budget but also increase timeouts
    if node_count > 100 or pod_count > 5000:
        base_budget.max_llm_calls = int(base_budget.max_llm_calls * 1.5)
        base_budget.max_total_latency_ms = int(base_budget.max_total_latency_ms * 1.5)
        # But REDUCE tool calls per agent to stay within budget
        base_budget.max_tool_calls_per_agent = max(2, base_budget.max_tool_calls_per_agent - 1)

    # Small clusters: reduce budget (less to analyze)
    if node_count < 5 and pod_count < 50:
        base_budget.max_llm_calls = max(4, base_budget.max_llm_calls // 2)

    return base_budget
```

## Design: LLM Call Instrumentation

### Per-Call Telemetry

Every LLM call records:

```python
@dataclass
class LLMCallRecord:
    call_id: str                # Unique ID
    session_id: str
    agent_name: str             # "ctrl_plane_agent", "synthesizer"
    model: str                  # "claude-haiku-4-5-20251001"
    call_type: str              # "tool_calling", "analysis", "synthesis"

    # Request
    input_tokens: int
    input_messages_count: int
    tools_provided: int
    system_prompt_tokens: int

    # Response
    output_tokens: int
    tool_calls_made: int
    stop_reason: str            # "end_turn", "tool_use", "max_tokens"

    # Performance
    latency_ms: int
    time_to_first_token_ms: int

    # Status
    success: bool
    error: str = ""             # "timeout", "rate_limit", "parse_error", "hallucination"
    retried: bool = False
    fallback_used: bool = False # Did we fall back to heuristic?

    # Cost (computed)
    estimated_cost_usd: float = 0.0

    timestamp: str = ""
```

### Session-Level Summary

```python
@dataclass
class SessionLLMSummary:
    total_calls: int
    successful_calls: int
    failed_calls: int
    fallback_calls: int         # Calls where heuristic was used instead

    total_input_tokens: int
    total_output_tokens: int
    total_latency_ms: int

    total_cost_usd: float
    budget_used_pct: float      # How much of the budget was consumed

    per_agent: dict[str, AgentLLMStats]

    # Anomalies
    slowest_call_ms: int
    most_expensive_call_usd: float
    rate_limit_hits: int
    timeout_count: int
    parse_failures: int
```

### Cost Calculation

```python
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": {
        "input_per_1k": 0.0008,
        "output_per_1k": 0.004,
    },
    "claude-sonnet-4-20250514": {
        "input_per_1k": 0.003,
        "output_per_1k": 0.015,
    },
}

def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["claude-sonnet-4-20250514"])
    return (input_tokens / 1000 * pricing["input_per_1k"] +
            output_tokens / 1000 * pricing["output_per_1k"])
```

## Design: Failure Mode Handling

### Failure Cascade Prevention

```
LLM Call Failed?
    │
    ├─ Timeout (>15s for Haiku, >30s for Sonnet)
    │   ├─ Attempt 1: Retry once with reduced context (truncate input by 40%)
    │   └─ Attempt 2: Fall back to heuristic analyzer
    │
    ├─ Rate Limited (429)
    │   ├─ Wait: exponential backoff (1s, 2s, 4s)
    │   └─ Max 3 retries, then fall back to heuristic
    │
    ├─ Parse Error (malformed JSON from LLM)
    │   ├─ Attempt 1: Retry with stricter prompt ("respond ONLY with JSON")
    │   ├─ Attempt 2: Extract JSON from response with regex
    │   └─ Attempt 3: Fall back to heuristic
    │
    ├─ Hallucination Detected (references non-existent resources)
    │   ├─ Critic agent flags → discard finding
    │   └─ Reduce confidence of all findings from this agent by 50%
    │
    ├─ Budget Exhausted
    │   ├─ Remaining agents use heuristic-only mode
    │   ├─ Synthesizer uses Haiku instead of Sonnet
    │   └─ Emit warning: "Budget limit reached — analysis may be incomplete"
    │
    └─ API Key Missing/Invalid
        └─ ALL agents use heuristic-only mode (zero LLM cost)
```

### Heuristic Fallback Quality

Every agent must have TWO implementations:

```python
class NodeAgent:
    async def run_llm(self, state, budget) -> DomainReport:
        """LLM-powered analysis with tool calling."""
        if not budget.can_call():
            return await self.run_heuristic(state)
        # ... LLM tool-calling loop

    async def run_heuristic(self, state) -> DomainReport:
        """Deterministic rule-based analysis. No LLM calls."""
        # Current implementation — always works, always fast
        # Lower confidence but zero cost
```

**Heuristic findings get:**
- `confidence *= 0.7` (lower than LLM findings)
- `meta.source = "heuristic"` (tagged for UI display)
- `meta.reason = "budget_exhausted"` or `"llm_timeout"` or `"api_key_missing"`

### Anti-Hallucination Controls

```python
class HallucinationDetector:
    def validate_finding(self, finding, known_resources: set[str]) -> bool:
        """Check if finding references real K8s resources."""
        # Extract resource references from finding detail
        referenced = extract_resource_refs(finding.detail)

        for ref in referenced:
            if ref not in known_resources:
                logger.warning("Hallucination detected: %s references non-existent %s",
                    finding.finding_id, ref)
                return False

        return True

    def validate_kubectl_command(self, command: str) -> tuple[bool, str]:
        """Check if kubectl command is syntactically valid."""
        # Parse: kubectl <verb> <resource> <name> [flags]
        # Verify verb, resource type, required flags
        ...
```

## Design: Frontend Cost/Latency Display

### Session Summary Badge (in War Room header)

```
◐ Standard Scan │ $0.08 │ 12 LLM calls │ 67s total │ Budget: 60% used
```

### Per-Agent Breakdown (expandable)

```
Agent            Calls  Tokens   Cost   Time   Status
ctrl_plane         3    12K/2K   $0.01  8.2s   ✓ LLM
node               4    18K/4K   $0.02  12.1s  ✓ LLM
network            2    8K/1K    $0.01  5.4s   ⚠ Heuristic (timeout)
storage            3    14K/3K   $0.02  9.8s   ✓ LLM
synthesizer        1    25K/6K   $0.02  15.3s  ✓ LLM
─────────────────────────────────────────────────
Total             13    77K/16K  $0.08  50.8s
```

### Budget Warning Banner

When budget > 80% consumed:
```
⚠ LLM budget 85% consumed — remaining agents using heuristic analysis
```

## Implementation Files

**New files:**
- `backend/src/agents/cluster/budget.py` — SessionBudget, SCAN_BUDGETS, adapt_budget
- `backend/src/agents/cluster/llm_telemetry.py` — LLMCallRecord, SessionLLMSummary, cost calculation
- `backend/src/agents/cluster/hallucination_detector.py` — resource validation, command validation
- `frontend/src/components/ClusterDiagnostic/LLMCostBadge.tsx` — session cost display
- `frontend/src/components/ClusterDiagnostic/AgentCostBreakdown.tsx` — per-agent breakdown

**Modified files:**
- `backend/src/agents/cluster/graph.py` — pass budget through state, check before each LLM call
- All domain agents — check `budget.can_call()` before LLM, fall back to heuristic
- `backend/src/agents/cluster/synthesizer.py` — downgrade model when budget low
- `backend/src/utils/llm_client.py` — instrument every call with LLMCallRecord
- `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx` — show cost badge + budget warnings

## Applies To Both Cluster AND Database Diagnostics

This budget/telemetry system should be **shared infrastructure** used by:
- Cluster diagnostics (this plan)
- Database diagnostics (existing LLM agents)
- Homepage assistant (existing)

Create as a shared module in `backend/src/utils/llm_budget.py` and `backend/src/utils/llm_telemetry.py`.
