# Diagnostic Pipeline Hardening — Design Document

**Goal:** Close all 15 architectural gaps identified in the app diagnostic workflow audit, transforming the system from a single-process in-memory application into a multi-instance, Redis-backed, resilient diagnostic platform with cross-repo dependency tracing.

**Constraints gathered during brainstorming:**
- Multi-instance deployment behind a load balancer (Redis-backed distributed primitives required)
- Full polyglot support for diagnosed services (Python, Node, Go, Java, Rust, .NET)
- Mix of active-watcher and fire-and-forget users (auto-approval + interactive gate)
- Redis already available in infrastructure
- LLM cost is not a concern — budget scales with repo count for cross-repo tracing
- Seasonal anomaly detection demoted to Tier 4 (simple same-hour-yesterday comparison is sufficient)
- Negative finding pruning stays Tier 4 (not worth the supervisor prompt complexity)

**Approach:** Infrastructure-first (Approach A). Lay the Redis foundation first, then build features on top. Each phase is independently deployable.

---

## Phase 1: Redis Foundation + Context Window Guard

**Addresses:** G9 (in-memory sessions), G3 (WebSocket FD leak), G8 (LLM call coordination), G2 (context window overflow)

### 1A. Redis Session Store

Replace the in-memory `sessions: dict` in `routes_v4.py` with a `RedisSessionStore` class.

```
RedisSessionStore
  ├── save(session_id, state: dict)     → Redis HSET + TTL (1 hour)
  ├── load(session_id) → dict | None    → Redis HGETALL
  ├── delete(session_id)                → Redis DEL
  ├── acquire_lock(session_id) → Lock   → Redis distributed lock (redlock pattern)
  └── extend_ttl(session_id)            → Redis EXPIRE
```

- Session state serialized as JSON into a Redis hash. Each field (phase, findings, confidence, token_usage) is a separate hash key so partial reads are cheap.
- Per-session distributed lock via `redis.lock()` replaces the current `asyncio.Lock`. Write operations acquire the lock; reads don't (eventual consistency is acceptable for UI polling).
- Session TTL auto-cleanup replaces the current `_cleanup_task()` background loop.

### 1B. WebSocket Coordination via Redis Pub/Sub

Each FastAPI instance holds its own WebSocket connections. If Instance A runs the diagnosis but the user's WebSocket connects to Instance B, events never arrive.

Solution: Redis Pub/Sub channel per session.

```
Instance A (runs diagnosis) → publishes event to Redis channel "session:{id}"
Instance B (holds WS conn) → subscribes to "session:{id}", forwards to client
```

- `ConnectionManager` gets a `RedisPubSubBridge` that subscribes on WS connect, unsubscribes on disconnect.
- WebSocket heartbeat: 30s ping/pong interval. 3 missed pongs → drop connection + unsubscribe. Fixes FD leak (G3).

### 1C. Distributed LLM Semaphore

```
RedisLLMSemaphore
  ├── acquire(timeout=30s)  → Redis INCR + TTL guard
  ├── release()             → Redis DECR
  └── max_concurrent: 10    → configurable per-instance or global
```

- Prevents thundering herd across instances. If 10 concurrent LLM calls are in flight globally, the 11th waits with jitter.
- TTL guard: if a process crashes while holding a slot, the slot auto-expires after 60s.

### 1D. Context Window Overflow Protection

A middleware layer in `react_base.py` before every `chat_with_tools()` call.

```
ContextWindowGuard
  ├── estimate_tokens(messages: list) → int     # tiktoken cl100k_base
  ├── model_limit(model_name: str) → int        # 128k Haiku, 200k Sonnet
  ├── truncate_if_needed(messages, limit) → messages
  └── THRESHOLD = 0.80                          # trigger at 80%
```

Truncation strategy (ordered by aggression):
1. Drop oldest tool results first — keep the most recent 3 tool call/response pairs, summarize earlier ones into a single "Prior investigation summary" message.
2. Tail logs instead of full fetch — if a single tool result exceeds 20k tokens, keep only the last 500 lines + a "truncated N lines" header.
3. Emergency summarization — if still over 80% after steps 1-2, inject a system prompt asking the LLM to produce a compressed summary of its findings so far, then restart the ReAct loop with the summary as context.

Hooks in at `react_base.py` line ~265, right before the LLM call in the ReAct loop. Every agent gets this for free.

### New Dependencies

- `redis[hiredis]` (async Redis client with C parser)
- `tiktoken` (token estimation)

### New Environment Variables

- `REDIS_URL` (default `redis://localhost:6379/0`)
- `MAX_CONCURRENT_LLM_CALLS` (default `10`)
- `WS_HEARTBEAT_INTERVAL_S` (default `30`)
- `SESSION_TTL_S` (default `3600`)

---

## Phase 2: Quick Reliability Wins

**Addresses:** G5 (no circuit breaker), G6 (tool errors swallowed), G4 (attestation timeout)

### 2A. Redis-Backed Circuit Breaker

Shared across all instances. When ES/Prometheus/GitHub is down, one instance's failure detection protects all others.

```
RedisCircuitBreaker
  ├── record_success(service_name)
  ├── record_failure(service_name)
  ├── is_open(service_name) → bool
  ├── state: CLOSED → OPEN → HALF_OPEN
  └── config per service:
        failure_threshold: 3 failures in 60s → OPEN
        recovery_timeout: 120s → HALF_OPEN (allow 1 probe)
        success_threshold: 2 consecutive → CLOSED
```

Wraps the existing `retry_with_backoff` decorator. If circuit is open, returns immediately with a structured error: `{"error": "circuit_open", "service": "elasticsearch", "retry_after_s": 120}`.

Agent behavior when circuit is open: receives a clear "data source unavailable" signal. The supervisor marks the affected phase as `"skipped_unavailable"` rather than `"failed"`.

### 2B. Tool Error Propagation

Replace generic catch-all in `tool_executor.py`:

```python
# Before:
except Exception:
    return "Error executing {tool}"

# After:
except Exception as e:
    error_detail = f"Tool '{tool}' failed: {type(e).__name__}: {str(e)}"
    logger.exception(f"[{session_id}] {error_detail}")
    return error_detail
```

Full stack trace stays in server logs only — never sent to the LLM.

### 2C. Attestation Timeout + Auto-Approval

**Timeout (10 minutes):** On expiry, session completes with `status="completed_no_fix"` — findings preserved, no fix generated. User can return and re-trigger.

**Auto-approval:** If composite confidence >= configurable threshold (default 0.85) and critic has no challenges, skip the gate entirely. Emit `"auto_approved"` event for transparency.

New env var: `ATTESTATION_AUTO_APPROVE_THRESHOLD` (default `0.85`, set to `1.0` to disable).

---

## Phase 3: Per-Finding Attestation + Audit Trail

**Addresses:** G7 (all-or-nothing attestation), G13 (no audit trail)

### 3A. Per-Finding Attestation

Data model:

```python
@dataclass
class AttestationDecision:
    finding_id: str
    decision: Literal["approved", "rejected", "skipped"]
    decided_by: str          # "user" | "auto_approve" | "timeout"
    decided_at: datetime
    confidence_at_decision: float

@dataclass
class AttestationGate:
    findings: list[FindingSummary]
    decisions: dict[str, AttestationDecision]
    status: Literal["pending", "partially_decided", "complete"]
    auto_approved: bool
    expires_at: datetime
```

API change:

```
POST /api/v4/sessions/{id}/attestation

# Before:
{"decision": "approve"}

# After:
{"decisions": [
    {"finding_id": "f1", "decision": "approved"},
    {"finding_id": "f2", "decision": "rejected"},
    {"finding_id": "f3", "decision": "skipped"}
]}
```

Fix generation behavior:
- **Approved** findings → proceed to Agent 3
- **Rejected** findings → dropped, not acted on
- **Skipped** findings → preserved in record, not acted on
- All rejected → session completes with `status="completed_no_fix"`

Frontend impact: `AttestationGateUI.tsx` renders per-finding approve/reject/skip buttons. Scoped to one component.

### 3B. Audit Trail (Redis Streams)

> **Why Redis Streams, not SQLite:** In a multi-instance deployment, each instance would write to its own local `.db` file — the query endpoint would return inconsistent data depending on which pod serves the request. Redis Streams (`XADD`/`XRANGE`) provide ordered, persistent, queryable audit logs shared across all instances with no new infrastructure.

Single persistence layer via Redis Streams:

```python
# Write: XADD to ordered stream with auto-trimming
await redis.xadd("audit:attestations", {
    "session_id": session_id,
    "finding_id": finding_id,
    "decision": decision,
    "decided_by": decided_by,
    "decided_at": datetime.utcnow().isoformat(),
    "confidence": str(confidence),
    "finding_summary": summary,
}, maxlen=10_000, approximate=True)

# Read: XRANGE with client-side filtering
entries = await redis.xrange("audit:attestations", min="-", max="+", count=500)
```

Query API:

```
GET /api/v4/audit/attestations?session_id=X
GET /api/v4/audit/attestations?decided_by=user&since=2026-04-01
```

Stream is capped at ~10k entries with approximate trimming. For long-term retention beyond Redis, a periodic export job can flush the stream to object storage (S3/GCS) — but this is out of scope for the initial implementation.

---

## Phase 4: Cross-Repo Dependency Tracing

**Addresses:** G1 (causal chain stops at repo boundary), G11 (no dependency manifest parsing)

### 4A. Dependency Manifest Parser

New module: `backend/src/tools/dependency_parser.py`

```python
@dataclass
class Dependency:
    name: str                    # "requests", "@types/node"
    version_spec: str            # ">=2.28,<3.0", "^18.0.0"
    source: str                  # "pypi", "npm", "go", "maven", "crates"
    manifest_file: str           # "requirements.txt"
    repo_url: str | None         # resolved GitHub URL if detectable
    is_internal: bool            # True if maps to a known service in repo_map
```

Supported formats:
- Python: `requirements.txt`, `pyproject.toml`, `setup.py`, `Pipfile`
- Node: `package.json`, `package-lock.json`, `yarn.lock`
- Go: `go.mod`, `go.sum`
- Java: `pom.xml`, `build.gradle`, `build.gradle.kts`
- Rust: `Cargo.toml`
- .NET: `*.csproj`, `packages.config`

Only `is_internal` dependencies (those mapping to another repo in `repo_map`) are traced across repos. External dependencies are logged but not followed.

### 4B. Cross-Repo Correlation Engine

New module: `backend/src/agents/cross_repo_tracer.py`

Trigger conditions (any of):
1. Code agent confidence < 0.6 after primary repo analysis
2. Dependency parser found internal dependencies with recent commits (< 7 days)
3. Change agent detected deployment of an upstream service within the failure window

Flow:
1. Parse primary repo's dependency manifests
2. Filter to internal dependencies (repos in `repo_map`)
3. For each internal dependency:
   - Clone upstream repo (shallow, sparse checkout of changed files only)
   - Fetch commits in the failure time window (failure_start - 24h → now)
   - If breaking commits found: diff changed files, check if changed APIs/functions are imported by primary repo
   - Score correlation: timestamp proximity × API overlap × test coverage
4. Build cross-repo evidence graph
5. Return `CrossRepoFindings` to supervisor

Budget: each upstream repo costs ~2-4 LLM calls. Budget scales linearly: `base_budget + (N_upstream_repos × 4 calls)`. New `cross_repo` profile in `llm_budget.py`.

### 4C. Evidence Graph Extension

Extend `causal_engine.py` with cross-repo edges:

```python
@dataclass
class CrossRepoEdge:
    source_repo: str
    source_file: str
    source_commit: str
    source_timestamp: datetime
    target_repo: str
    target_file: str
    target_import: str
    correlation_type: str     # "api_rename" | "version_bump" | "deleted_export" | "schema_change"
    correlation_score: float
```

### 4D. New LLM Tool

Added to `tool_registry.py`:

```
analyze_upstream_dependency
  Input:  service_name, dependency_name, time_window
  Output: {recent_commits: [], breaking_changes: [], api_diff: str}
```

Agents can explicitly request upstream analysis during their ReAct loop.

---

## Phase 5: Causal Reasoning Improvements

**Addresses:** G10 (spike detection false positives)

### 5A. Structured Cross-Agent Evidence Passing (Dual Representation)

> **Mandatory: No "Stringly-Typed AI State."** Structured data must never be collapsed into text and discarded. The system maintains two parallel representations: a machine-readable dict (source of truth for supervisor, causal graph, audit trail, frontend) and a formatted text version (strictly for LLM context, generated from the dict, never parsed back).

Replace unstructured text dumps between agents with dual-representation handoffs:

```python
@dataclass
class EvidenceHandoff:
    claim: str                          # "OOM killed pod-xyz at 14:32 UTC"
    domain: str                         # "k8s"
    timestamp: datetime | None
    confidence: float
    source_agent: str                   # "k8s_agent"
    finding_id: str                     # links to attestation
    corroborating_domains: list[str]
    contradicting_domains: list[str]
    open_questions: list[str]

# Machine-readable (supervisor, graph, audit, UI):
serialize_handoffs(handoffs) → {"handoffs": [asdict(h) for h in handoffs]}

# LLM-readable (context window only, generated from struct):
format_handoff_for_agent(handoffs, target_domain) → str
```

Supervisor wiring follows a strict dual path:
1. `serialize_handoffs()` → saved to session state, ingested by causal graph, pushed to Redis `audit:handoffs` stream
2. `format_handoff_for_agent()` → injected into LLM prompt only

The causal engine's `ingest_structured_handoffs()` method programmatically creates graph nodes from the dict — never from LLM text. The frontend polls the structured `audit:handoffs` stream to render a live investigation timeline.

Zero changes to individual agent code — only the supervisor's inter-agent routing logic changes.

### 5B. Critic Hypothesis Generation (Bounded Reasoning)

Add alternative hypothesis capability to critic output:

```python
@dataclass
class CriticVerdict:
    finding_id: str
    verdict: Literal["confirmed", "challenged", "insufficient_evidence"]
    confidence: float
    reasoning: str
    suggest_alternative: str | None   # "Check if OOM was in the istio-proxy sidecar"
    suggested_agent: str | None       # "k8s_agent"
```

When the critic suggests an alternative, the supervisor checks three guards before re-dispatching:

> **Critical: Loop prevention.** Without guards, a naive re-dispatch creates hidden cycles (`Critic → k8s_agent → Critic → metrics_agent → Critic → k8s_agent...`) that silently burn tokens and latency.

**HypothesisTracker** — a new module that tracks every `(agent, hypothesis)` pair:

```python
class HypothesisTracker:
    def should_dispatch(agent, hypothesis, budget_exhausted) -> bool:
        # Guard 1: reject if (agent, normalized_hypothesis) already tried
        # Guard 2: reject if budget.is_exhausted()
        # Guard 3: reject if total re-dispatches >= max (default 2)

    def record(agent, hypothesis) -> None  # log after dispatch
    def investigation_graph() -> list[tuple[str, str]]  # full trail for audit
```

Hypothesis normalization uses fuzzy matching (lowercase, strip articles/punctuation, collapse whitespace) so "Check if OOM was in the istio-proxy sidecar" and "Check OOM in istio-proxy sidecar container" are recognized as the same intent.

Re-dispatch events (`re_dispatch` and `re_dispatch_blocked`) are emitted to the WebSocket/audit stream for frontend visibility and compliance.

### 5C. Spike Detection — Same-Hour-Yesterday Comparison

No STL decomposition. Compare the anomaly window against the same hour from the previous day:

```python
def is_anomaly(current_window, previous_day_same_hour, threshold=2.0):
    current_zscore = (current_value - current_mean) / current_std
    previous_zscore = (previous_day_value - previous_mean) / previous_std
    if current_zscore > threshold and previous_zscore < threshold:
        return True   # genuine anomaly
    return False      # cyclical pattern
```

~20 lines in `metrics_agent.py`. No new dependencies.

---

## Phase 6: Operational Hardening

**Addresses:** remaining gaps for production readiness.

### 6A. Per-Tool Timeouts

```python
TOOL_TIMEOUTS = {
    "fetch_pod_logs": 30,
    "query_prometheus_range": 20,
    "query_prometheus_instant": 10,
    "search_elasticsearch": 30,
    "describe_resource": 15,
    "analyze_upstream_dependency": 45,
    "default": 20,
}
```

On timeout, agent receives: `"Tool 'fetch_pod_logs' timed out after 30s"`.

### 6B. Tool Result Caching (Redis)

```python
class ToolResultCache:
    def cache_key(self, session_id, tool_name, params) -> str:
        param_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
        return f"tool_cache:{session_id}:{tool_name}:{param_hash}"
    
    async def get_or_execute(self, session_id, tool_name, params, executor):
        key = self.cache_key(session_id, tool_name, params)
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)
        result = await executor(tool_name, params)
        await redis.setex(key, 300, json.dumps(result))  # 5-min TTL
        return result
```

### 6C. Health Check Endpoint

```
GET /api/v4/health

{
    "status": "healthy" | "degraded" | "unhealthy",
    "checks": {
        "redis": {"status": "up", "latency_ms": 2},
        "elasticsearch": {"status": "up", "latency_ms": 45},
        "prometheus": {"status": "down", "circuit": "open", "retry_after_s": 90},
        "anthropic_api": {"status": "up", "concurrent_calls": 3, "limit": 10}
    }
}
```

Circuit breaker state from Phase 2 feeds directly into this. Load balancer uses it to route traffic away from unhealthy instances.

### 6D. ES Query Result Cap

```python
ES_MAX_RESULTS = int(os.getenv("ES_MAX_RESULTS", "5000"))
```

Every ES query capped. Agent context includes: `"Showing newest 5000 of ~487,000 matching logs. Results sorted newest-first."`.

---

## Gap-to-Phase Mapping

| Gap | Description | Phase |
|-----|-------------|-------|
| G1 | No cross-repo dependency tracing | Phase 4 |
| G2 | Context window overflow unhandled | Phase 1 |
| G3 | WebSocket FD leak | Phase 1 |
| G4 | Attestation timeout missing | Phase 2 |
| G5 | No circuit breaker for data sources | Phase 2 |
| G6 | Tool errors swallow stack traces | Phase 2 |
| G7 | All-or-nothing attestation | Phase 3 |
| G8 | No concurrent LLM call coordination | Phase 1 |
| G9 | In-memory session store | Phase 1 |
| G10 | Spike detection false positives | Phase 5 |
| G11 | No dependency manifest parsing | Phase 4 |
| G12 | Negative findings underutilized | Deferred (Tier 4) |
| G13 | No attestation audit trail | Phase 3 |
| G14 | Budget adaptation only scales up | Deferred (Tier 4) |
| G15 | Iteration nudge logic undocumented | Deferred (Tier 4) |

## Estimated Effort

| Phase | Scope | Effort |
|-------|-------|--------|
| Phase 1 | Redis foundation + context window guard | 1-2 weeks |
| Phase 2 | Circuit breaker, tool errors, attestation timeout | 1 week |
| Phase 3 | Per-finding attestation + audit trail | 1 week |
| Phase 4 | Cross-repo dependency tracing | 2-4 weeks |
| Phase 5 | Causal reasoning improvements | 1-2 weeks |
| Phase 6 | Operational hardening | 1 week |
| **Total** | | **7-11 weeks** |

## New Dependencies

- `redis[hiredis]` — async Redis client
- `tiktoken` — token estimation for context window guard

## New Environment Variables

| Variable | Default | Phase |
|----------|---------|-------|
| `REDIS_URL` | `redis://localhost:6379/0` | 1 |
| `MAX_CONCURRENT_LLM_CALLS` | `10` | 1 |
| `WS_HEARTBEAT_INTERVAL_S` | `30` | 1 |
| `SESSION_TTL_S` | `3600` | 1 |
| `ATTESTATION_AUTO_APPROVE_THRESHOLD` | `0.85` | 2 |
| `ES_MAX_RESULTS` | `5000` | 6 |

## Deferred Items (Tier 4)

- G12: Negative finding pruning — not worth supervisor prompt complexity
- G14: Adaptive minimum budget — minor cost optimization
- G15: Document iteration nudge logic — code comment, no behavioral change
- Seasonal-aware anomaly detection (STL decomposition) — simple same-hour comparison is sufficient for now
