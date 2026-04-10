# CI/CD Integration (Jenkins + ArgoCD) — Design

**Goal:** Integrate Jenkins and ArgoCD into DebugDuck across four use cases — diagnostic evidence, remediation actions, proactive monitoring, and a standalone pipeline-debug capability — plus a real-time "flight board" Live Board dashboard.

**Context:** DebugDuck already has a `ChangeAgent` that correlates GitHub commits + k8s deployment history with incidents, and an integrations framework for Jira/Confluence/GitHub/ELK/Prometheus/Remedy. CI/CD signals (Jenkins builds, ArgoCD syncs) are missing. This design adds them as first-class evidence sources and exposes them through a new Live Board and a new investigation capability.

---

## 1. Decisions Made

| Decision | Choice | Reasoning |
|----------|--------|-----------|
| Use cases in scope | All 4 (evidence, remediation, monitoring, pipeline-debug) | User confirmed; #1 is the lead |
| Phasing | Phase A = read-path (evidence + pipeline capability). Phase B = write-path (remediation + webhooks) | Read/write share no infra; pair by path |
| Tools covered | Jenkins + ArgoCD together | Build the abstraction once |
| Architecture | Shared `CICDClient` library, two consumers (ChangeAgent + PipelineAgent) | Client is the reusable primitive, not the agent |
| Auth / config | Reuse existing integrations store; ArgoCD auto-discovered from cluster integration when present | Matches Prometheus pattern |
| Evidence signal set | Deploy events + artifacts (log tail, manifest diff, git SHA, sync status) | Enough for ChangeAgent and pipeline debug without token bloat |
| Normalization | At client boundary — all events → `DeployEvent` before reaching agents | Agents never see tool-specific shapes |
| Live Board model | Event model, flat chronological feed, newest-first | "What just changed?" is the question the board answers |
| Live Board content | Commits + builds + syncs interleaved | Single stream, distinguished by `kind` pill |
| Live Board transport | 10s HTTP poll | Ships fast; poll budget fine at expected scale |
| Row drill-down | Right-side drawer with Commit / Diff / Related tabs | Click deploy → see the commit and code diff it brought |
| Commit detail source | Existing GitHub integration, on-demand endpoint | No new credentials, keeps board payload small |

---

## 2. Architecture

Three layers, top to bottom:

```
┌─────────────────────────────────────────────────────────────┐
│  Consumers                                                  │
│  • ChangeAgent         (diagnostic evidence — Phase A)      │
│  • PipelineAgent       (troubleshoot_pipeline — Phase A)    │
│  • /cicd/stream        (Live Board backend — Phase A)       │
│  • RemediationExecutor (Phase B — trigger rollback)         │
│  • WebhookRouter       (Phase B — auto-open investigations) │
└─────────────────────────────────────────────────────────────┘
                            ↓ uses
┌─────────────────────────────────────────────────────────────┐
│  backend/src/integrations/cicd/                             │
│                                                             │
│  CICDClient  (Protocol)                                     │
│    ├─ list_deploy_events(since, until, filters) → [Event]   │
│    ├─ get_build_artifacts(event) → Build | SyncDiff         │
│    ├─ health_check() → bool                                 │
│    └─ trigger_action(...) → ActionResult    (Phase B)       │
│                                                             │
│  Implementations:                                           │
│    ├─ JenkinsClient   (REST API, token auth)                │
│    └─ ArgoCDClient    (CRD-via-kubeconfig OR REST API)      │
│                                                             │
│  Shared types: DeployEvent, Build, SyncDiff, DeliveryItem   │
│  Resolver: resolve_cicd_clients(session_context)            │
│  Cache: in-memory TTL (60s) for list queries                │
└─────────────────────────────────────────────────────────────┘
                            ↓ configured from
┌─────────────────────────────────────────────────────────────┐
│  Existing integrations framework                            │
│  • IntegrationStore adds service_types: "jenkins", "argocd" │
│  • Credentials via existing secret_store                    │
│  • ArgoCD auto-discovery via cluster IntegrationConfig      │
│  • Settings UI adds two forms                               │
└─────────────────────────────────────────────────────────────┘
```

### Key design choices

- `CICDClient` is a Python `Protocol` (duck-typed), matching DebugDuck's existing `cluster_client/base.py` style.
- Normalization at the client boundary — Jenkins builds and ArgoCD syncs both become `DeployEvent` before any agent sees them.
- `resolve_cicd_clients(session_context)` merges manually configured clients with auto-discovered ArgoCD from the active cluster integration. Consumers ask "give me the clients for this session" — they don't care about config plumbing.

---

## 3. Components

### New files

```
backend/src/integrations/cicd/
├── __init__.py
├── base.py              # CICDClient Protocol, shared types
├── jenkins_client.py    # JenkinsClient implementation
├── argocd_client.py     # ArgoCDClient (kubeconfig + REST modes)
├── resolver.py          # resolve_cicd_clients(session_context)
└── cache.py             # TTL cache for list queries

backend/src/agents/
└── pipeline_agent.py    # PipelineAgent for troubleshoot_pipeline capability

frontend/src/components/CICD/
├── CICDLiveBoard.tsx    # main /cicd view
├── DeliveryRow.tsx      # one row (COMMIT | BUILD | SYNC)
├── SplitFlapCell.tsx    # flight-board status cell animation
├── DeliveryFilters.tsx  # kind / status / source filter chips
└── DeliveryDrawer.tsx   # right-side drawer with Commit / Diff / Related tabs
```

### Modified files

- `backend/src/integrations/store.py` — register `"jenkins"` and `"argocd"` service types
- `backend/src/integrations/probe.py` — connection tests for both
- `backend/src/agents/change_agent.py` — pre-fetch adds `ci_cd_events` context block
- `backend/src/agents/supervisor.py` — route `troubleshoot_pipeline` to `PipelineAgent`
- `backend/src/models/schemas.py` — add `troubleshoot_pipeline` capability type
- `backend/src/api/routes_v4.py` — add `/cicd/stream` and `/cicd/commit/{owner}/{repo}/{sha}`
- `frontend/src/types/index.ts` — add `troubleshoot_pipeline` capability type + `DeliveryItem`
- `frontend/src/components/Settings/IntegrationSettings.tsx` — Jenkins + ArgoCD forms
- `frontend/src/components/ActionCenter/CapabilityForm.tsx` — pipeline-debug form variant
- `frontend/src/contexts/NavigationContext.tsx` — new sidebar entries
- `frontend/src/components/Layout/SidebarNav.tsx` — "Delivery" standalone link + "Pipeline" under Diagnostics
- `frontend/src/router.tsx` — `/cicd` route + `pipeline-diagnostics` capability route
- `frontend/src/components/Home/HomePage.tsx` — compact Live Board widget (top 8 rows)

### Core types (`cicd/base.py`)

```python
from typing import Protocol, Literal
from datetime import datetime
from pydantic import BaseModel

DeployStatus = Literal["success", "failed", "in_progress", "aborted", "unknown"]
SyncHealth = Literal["healthy", "degraded", "progressing", "suspended", "missing", "unknown"]

class DeployEvent(BaseModel):
    """Normalized deploy event from any CI/CD source."""
    source: Literal["jenkins", "argocd"]
    source_id: str              # build number or app+revision
    name: str                   # job name or app name
    status: DeployStatus
    started_at: datetime
    finished_at: datetime | None
    git_sha: str | None
    git_repo: str | None        # "owner/name" — needed for commit drawer
    git_ref: str | None         # branch or tag
    triggered_by: str | None
    url: str                    # deeplink back to tool
    target: str | None          # namespace, environment, or cluster

class Build(BaseModel):
    """Detailed Jenkins build state."""
    event: DeployEvent
    parameters: dict[str, str]
    log_tail: str               # last ~200 lines
    failed_stage: str | None

class SyncDiff(BaseModel):
    """ArgoCD sync diff."""
    event: DeployEvent
    health: SyncHealth
    out_of_sync_resources: list[dict]
    manifest_diff: str          # unified diff text

class DeliveryItem(BaseModel):
    """Unified row for the Live Board — commit, build, or sync."""
    kind: Literal["commit", "build", "sync"]
    id: str                     # sha for commits, build_id for builds, revision for syncs
    title: str                  # commit first line OR job name OR app name
    source: Literal["github", "jenkins", "argocd"]
    source_instance: str
    status: str
    author: str | None
    git_sha: str | None
    git_repo: str | None
    target: str | None
    timestamp: datetime
    duration_s: int | None
    url: str

class CICDClient(Protocol):
    source: Literal["jenkins", "argocd"]
    name: str

    async def list_deploy_events(
        self, since: datetime, until: datetime,
        target_filter: str | None = None,
    ) -> list[DeployEvent]: ...

    async def get_build_artifacts(self, event: DeployEvent) -> Build | SyncDiff: ...

    async def health_check(self) -> bool: ...
```

### JenkinsClient

- Auth: API token + username via existing `secret_store`
- Endpoints: `/api/json?tree=jobs[...]`, `/job/{name}/{n}/api/json`, `/job/{name}/{n}/consoleText`
- `list_deploy_events` walks jobs, filters builds inside the window, populates `git_sha`/`git_repo` from `GIT_COMMIT` + `GIT_URL` build env or parameters
- `get_build_artifacts` fetches log tail, parameters, and failed-stage detection
- Concurrency cap: 5 simultaneous job fetches (`asyncio.Semaphore`)

### ArgoCDClient

Two modes in one class:
- **Kubeconfig mode** (auto-discovered): reads `argoproj.io/v1alpha1` Applications via the existing cluster k8s client; no new credentials
- **REST mode** (manually configured): `/api/v1/session` for bearer token, `/api/v1/applications` for listing
- `list_deploy_events` reads `.status.operationState.syncResult` history; `git_sha` from `.status.sync.revision`, `git_repo` from `.spec.source.repoURL`
- `get_build_artifacts` returns `SyncDiff` with out-of-sync resources + manifest diff
- RBAC failure → falls off the resolver list with a descriptive `CICDClientError(kind="auth")`

### PipelineAgent

Thin `ReActAgent` (≤4 iterations). Tools exposed to the LLM:
- `list_recent_deploys(time_window)` → resolver + `list_deploy_events` fan-out
- `get_deploy_details(event_id)` → artifacts for one event
- `search_logs(pattern)` → grep build log or ArgoCD event messages

No new prompt infrastructure — reuses the existing `cluster/` agent prompt-template pattern.

---

## 4. Data Flow

### Flow A — ChangeAgent enrichment (diagnostic evidence)

```
User starts troubleshoot_app session
       ↓
Supervisor → ChangeAgent.run_two_pass()
       ↓
Phase 0 pre-fetch (existing) + NEW:
   clients, errors = await resolve_cicd_clients(ctx)
   events = []
   for client in clients:
       events += await client.list_deploy_events(
           since=incident_start - 2h,
           until=incident_start + 30m,
           target_filter=namespace,
       )
       ↓
Call 1 — Triage prompt
   Context block: "ci_cd_events": [normalized DeployEvents]
   LLM flags which events need full artifacts
       ↓
Phase 1b — Batch fetch artifacts for flagged events (log tails, diffs)
       ↓
Call 2 — Analyze
   LLM produces final finding
       ↓
Streams to WarRoom as AgentFindingCard with deeplink chip
```

Token budget: list-only pre-fetch (~3k tokens for 20 events). Artifacts only land in context when triage flags them — typically 0–3 events per investigation.

### Flow B — `troubleshoot_pipeline` capability

```
User clicks "Pipeline" under Diagnostics
   → /investigations/new?capability=troubleshoot_pipeline
       ↓
CapabilityForm variant asks for: CI/CD instance, job/app name, time window
       ↓
POST /api/v4/sessions → Supervisor → PipelineAgent
       ↓
PipelineAgent ReAct loop (≤4 iters) with 3 tools
       ↓
Finding streams to WarRoom
```

### Flow C — Live Board (`/cicd`)

```
Frontend mounts CICDLiveBoard
   ↓ useQuery with refetchInterval: 10_000
GET /api/v4/cicd/stream?since=<ts>
   ↓
Backend:
   clients, errors = await resolve_cicd_clients(ctx=None)
   github_clients = github_integration.get_all_configured()
   results = await asyncio.gather(
       *[c.list_deploy_events(since, now) for c in clients],
       *[gh.list_recent_commits(since, limit=50) for gh in github_clients],
       return_exceptions=True,
   )
   items = normalize_and_sort_desc(results)
   return { items: [...], source_errors: [...], server_ts }
   ↓
Frontend diffs new items by id, triggers SplitFlapCell animation on arrivals
and on in-progress → terminal transitions
   ↓
User clicks row → DeliveryDrawer opens
   ↓ GET /api/v4/cicd/commit/{owner}/{repo}/{sha}
Backend fetches commit + file diffs via GitHub integration
   ↓
Drawer renders Commit / Diff / Related tabs
```

### Resolver

```python
async def resolve_cicd_clients(ctx) -> ResolveResult:
    clients, errors = [], []

    for entry in gi_store.get_by_service_type("jenkins"):
        try:
            c = JenkinsClient(entry.url, entry.credentials)
            if await c.health_check():
                clients.append(c)
            else:
                errors.append(InstanceError(entry.name, "health_check_failed"))
        except CICDClientError as e:
            errors.append(InstanceError(entry.name, e.kind, e.message))

    for entry in gi_store.get_by_service_type("argocd"):
        try:
            c = ArgoCDClient.from_rest(entry.url, entry.credentials)
            if await c.health_check():
                clients.append(c)
        except CICDClientError as e:
            errors.append(InstanceError(entry.name, e.kind, e.message))

    # Auto-discover in-cluster ArgoCD if not already configured
    cluster = ctx.get("cluster_integration") if ctx else None
    if cluster and not any(c.source == "argocd" for c in clients):
        if await ArgoCDClient.probe_crds(cluster):
            clients.append(ArgoCDClient.from_kubeconfig(cluster))

    return ResolveResult(clients=clients, errors=errors)
```

---

## 5. Live Board Specification

### Route & sidebar
- New top-level sidebar link **"Delivery"** (icon `rocket_launch`) between Sessions and Diagnostics
- Route: `/cicd`
- Home page gets a compact top-8 widget

### Row model
Single chronological feed, newest-first. Each row is one event. Same app re-syncing → new row on top; previous row stays in place and scrolls down. Split-flap animation fires:
1. When a new item arrives in the poll response
2. When an in-progress row transitions to a terminal state

### Row layout
```
┌──────┬──────────────────────┬────────┬──────────┬─────────┬──────────┬──────────┐
│ KIND │ TITLE                │ SOURCE │ TARGET   │ STATUS  │ AUTHOR   │ TIME     │
├──────┼──────────────────────┼────────┼──────────┼─────────┼──────────┼──────────┤
│ SYNC │ checkout-api         │ argocd │ prod     │ HEALTHY │ —        │ 14:02:11 │
│ BUILD│ checkout-api #1847   │ jenkins│ build    │ SUCCESS │ ci-bot   │ 14:01:44 │
│COMMIT│ fix: null guard on…  │ github │ main     │COMMITTED│ gunjan   │ 14:00:31 │
└──────┴──────────────────────┴────────┴──────────┴─────────┴──────────┴──────────┘
```

- `kind` pill colors: COMMIT = slate, BUILD = amber, SYNC = cyan
- Status cell is the only `SplitFlapCell`
- FAILED / DEGRADED rows get an "Investigate ↗" button that opens `/investigations/new?capability=troubleshoot_app&...` with prefilled context

### Filters (top of board)
- Kind: `All | Deploys | Commits`
- Status: `All | Failed | In Progress | Success`
- Source: per-instance toggle
- Default: `All` × `All`

### Drawer tabs
- **Commit** — message, author, files changed summary, deeplink
- **Diff** — unified diff per file (fetched from `/cicd/commit/...`)
- **Related** — client-side SHA match against current feed (shows the commit's build + sync rows, or for commit rows, the deploys of that SHA)

---

## 6. Error Handling & Auth

### Client errors
```python
class CICDClientError(Exception):
    source: str
    instance: str
    kind: Literal["auth", "network", "timeout", "rate_limit", "parse", "unknown"]
    message: str
    retriable: bool
```

- Timeout: 10s per request (`aiohttp.ClientTimeout`)
- Retry: retriable errors → 2 retries with exponential backoff
- Non-retriable (401/403/404) → fail fast

### Resolver failure isolation
Never raises. Per-instance failures become `errors` entries; healthy instances become `clients`. Callers proceed with what succeeded.

### Fan-out tolerance in `/cicd/stream`
`asyncio.gather(..., return_exceptions=True)` — per-source failures don't poison the response. Frontend shows a warning chip in the board header when `source_errors` is non-empty.

### Auth
- **Jenkins**: API token + username → `secret_store` at `integrations/jenkins/{id}`
- **ArgoCD REST**: bearer via `/api/v1/session` → same storage path
- **ArgoCD kubeconfig**: no new credentials; uses existing cluster kubeconfig
- **GitHub (commit drawer)**: reuses existing `GITHUB_TOKEN` / integrations path

Credential rotation: clients constructed fresh each resolver call. No long-lived pool, no restart needed.

### Empty states
- Nothing configured → `/cicd` renders onboarding → Settings → Integrations
- Configured but no events in window → "No deploys or commits in the last N hours"
- ChangeAgent pre-fetch with empty resolver → no `ci_cd_events` block (no LLM confusion)

### Caching
TTL-only: 60s on list queries, 0 on artifacts. 10s board poll + 60s cache = backend absorbs bursts without hammering Jenkins/ArgoCD.

### Rate limiting
- Jenkins: 5 concurrent job fetches (`asyncio.Semaphore`)
- ArgoCD REST: respects `Retry-After` on 429
- GitHub commit drawer: standard 5000/hr token budget; graceful "rate limit reached" message

### Audit hook (Phase B prep)
Every `CICDClient` method records to `integrations/audit_store.py` at INFO with `{action: "read", source, instance, method, caller}`. Phase B write actions plug into the same store at higher severity.

---

## 7. Testing

### Backend unit tests
```
backend/tests/integrations/cicd/
├── test_jenkins_client.py      # mock aiohttp, parsing + retries
├── test_argocd_client.py       # mock k8s CRD + REST modes
├── test_resolver.py            # auto-discovery + failure isolation
├── test_normalization.py       # Jenkins + ArgoCD → DeployEvent
└── test_cache.py               # TTL behavior
backend/tests/agents/
└── test_pipeline_agent.py      # ReAct loop with mocked tools
```

Key cases (TDD, one per behavior):
- `test_jenkins_list_deploy_events_parses_builds_within_window`
- `test_jenkins_list_deploy_events_retries_on_5xx`
- `test_jenkins_list_deploy_events_fails_fast_on_401`
- `test_argocd_client_kubeconfig_mode_reads_crds`
- `test_argocd_client_rest_mode_uses_bearer_token`
- `test_resolver_isolates_failing_instance`
- `test_resolver_auto_discovers_argocd_when_cluster_has_crds`
- `test_resolver_skips_auto_discovery_when_argocd_already_configured`
- `test_normalize_jenkins_failed_build_to_deploy_event`
- `test_normalize_argocd_out_of_sync_to_sync_diff`
- `test_pipeline_agent_ends_after_finding_root_cause`
- `test_pipeline_agent_handles_empty_deploy_list`

### Backend integration tests
```
backend/tests/integrations/cicd/test_stream_endpoint.py
```
- `test_stream_endpoint_merges_all_sources_sorted_desc`
- `test_stream_endpoint_returns_partial_on_source_failure`
- `test_stream_endpoint_empty_when_nothing_configured`
- `test_commit_detail_endpoint_fetches_diff`
- `test_commit_detail_endpoint_handles_github_rate_limit`

### ChangeAgent enrichment
```
backend/tests/test_change_agent_cicd_enrichment.py
```
- `test_change_agent_prefetch_includes_cicd_events`
- `test_change_agent_prefetch_skips_when_no_clients`
- `test_change_agent_prefetch_fetches_artifacts_for_flagged_events`

### Frontend tests
```
frontend/src/components/CICD/__tests__/
├── CICDLiveBoard.test.tsx
├── DeliveryRow.test.tsx
├── SplitFlapCell.test.tsx
└── DeliveryDrawer.test.tsx
```
- Board renders sorted newest-first
- Board shows source_errors warning chip
- Board refetches every 10s, pauses when hidden
- Row pill colors per kind
- Row click opens drawer
- SplitFlapCell animates only on value change
- Drawer fetches commit detail on open
- "Related" tab filters current items by SHA
- Empty state links to Settings → Integrations

### Manual verification (before shipping Phase A)
1. Configure real Jenkins → board shows builds
2. Configure external ArgoCD (REST) → board shows syncs
3. In-cluster ArgoCD → auto-discovered with no config
4. Misconfigure one instance → other instance + warning chip shown
5. Click deploy row → drawer opens with commit + diff
6. `troubleshoot_app` session → ChangeAgent output has CI/CD evidence in WarRoom
7. `troubleshoot_pipeline` session → PipelineAgent produces a finding

---

## 8. Out of Scope for Phase A

- **Remediation actions** — `trigger_action` on `CICDClient` (rollback, rebuild, ArgoCD sync/rollback). Interface landed now, implementation in Phase B.
- **Webhook intake** — Jenkins post-build webhooks, ArgoCD notification controller → auto-open investigations on failure. Phase B.
- **`source_errors` UI in WarRoom** — ChangeAgent silently drops unreachable sources in Phase A; surfacing this per-finding is Phase B polish.
- **Multi-instance Jenkins folder/view hierarchies** — v1 supports flat root Jenkins only.
- **Unified pipeline flow rows** (threading commit → build → sync on one row) — evolved from Live Board later if needed.
- **WebSocket transport** — 10s poll is v1; upgrade to push only if scale demands it.

---

## 9. What Does NOT Change

- React Router v6 path-based routing — new routes slot into existing `router.tsx`
- WebSocket protocol for investigations — PipelineAgent streams via the same `/ws/troubleshoot/{sessionId}` endpoint
- Existing `ChangeAgent` two-pass structure — only the pre-fetch gains a third source
- Integrations framework design — new service types plug into the existing store, probe, and UI
- `secret_store` and credential model — reused as-is
- WarRoom `AgentFindingCard` — CI/CD findings render through the existing card
