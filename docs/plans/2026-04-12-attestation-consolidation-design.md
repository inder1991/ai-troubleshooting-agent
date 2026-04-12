# Attestation Consolidation Design — Chat-First Human-in-the-Loop

**Goal:** Consolidate all human-in-the-loop attestation gates into the chatbox as the single interaction surface, fix broken/dead attestation code, and add proper audit trails.

**Architecture:** State-driven resume model (not blocking coroutines). Supervisor saves state to Redis and exits cleanly when human input is needed. On user decision, a separate code path loads state and resumes the pipeline. All attestation interactions render as rich pinned chat messages with action chips. Heavy content (diffs, findings detail) opens in the Telescope drawer.

**Core Principles:**
- Chat is the single pane of glass for all human decisions
- Supervisor is stateless between human interactions (state in Redis)
- Frontend is a dumb renderer of `pending_action` objects from backend
- Every decision is logged to the attestation audit trail (Redis Streams)

---

## Issue 1: Discovery Attestation Gate is Unreachable Dead Code

**Problem:** `supervisor.py` emits `attestation_required` event then immediately `break`s out of the loop. `_wait_for_attestation()` is defined but never called. The gate exists in code but never executes.

**Root Cause:** The wait call was never wired into the main loop.

**Solution — State-Driven Resume:**
- On attestation required (and not auto-approved): save `PendingAction` to Redis, emit a rich chat message with action chips `[Approve Findings] [Reject] [Show Details]`, then `return` — exit the supervisor loop cleanly.
- On user decision: `acknowledge_attestation()` loads state, clears `pending_action`, sets `attestation_acknowledged = True`, saves to Redis, logs to audit trail, calls `supervisor.resume(session_id)` to re-enter the pipeline at the remediation phase.
- Delete `_wait_for_attestation()` and `_attestation_event` entirely. No asyncio.Event for human-timescale waits.
- Delete `AttestationRequiredCard` from `AISupervisor.tsx` — replaced by pinned chat message.
- Delete silent auto-submit in `FixPipelinePanel.handleGenerateFix()`.

**Files:**
- Modify: `backend/src/agents/supervisor.py` — state-driven exit/resume
- Modify: `backend/src/models/schemas.py` — add `PendingAction` model
- Modify: `backend/src/utils/redis_store.py` — save/load pending_action
- Delete card: `frontend/src/components/Investigation/AISupervisor.tsx` (AttestationRequiredCard)
- Modify: `frontend/src/components/Chat/ChatDrawer.tsx` — pinned action card rendering

---

## Issue 2: `_attestation_event.set()` Never Called

**Problem:** `acknowledge_attestation()` sets `_attestation_acknowledged = True` but never signals `_attestation_event`. Any code waiting on it would timeout.

**Root Cause:** Missing event signal line.

**Solution:** Delete `_attestation_event` entirely (per Issue 1 — state-driven model replaces asyncio.Event for human waits). `acknowledge_attestation()` becomes a state mutation + resume trigger, not an event signal.

**Files:**
- Modify: `backend/src/agents/supervisor.py` — remove `_attestation_event`, rewrite `acknowledge_attestation()` as state-driven

---

## Issue 3: Attestation Decisions Never Logged

**Problem:** `AttestationLogger.log_decision()` exists with Redis Streams, `GET /audit/attestations` endpoint works, but `log_decision()` is never called. Zero audit trail.

**Root Cause:** Logger built but never wired into decision handlers.

**Solution:** Call `attestation_logger.log_decision()` at every decision point:
- `acknowledge_attestation()` — discovery gate
- `_process_fix_decision()` — fix approval/reject/feedback
- Campaign repo decide endpoint — each repo approval/reject
- Campaign execute confirm — final execution decision
- Timeout events — log with `decision: "timed_out_reset"`

**Files:**
- Modify: `backend/src/agents/supervisor.py` — add log calls
- Modify: `backend/src/api/routes_v4.py` — add log calls in campaign endpoints

---

## Issue 4: No UI Buttons for Discovery Attestation

**Problem:** `AttestationRequiredCard` in `AISupervisor.tsx` renders "Human Review Needed" with zero action buttons. User sees the gate but can't interact.

**Root Cause:** Card was display-only; assumed a modal (now deleted) would handle actions.

**Solution:** Delete `AttestationRequiredCard` entirely. Under chat-first design, discovery attestation is a pinned chat message with action chips rendered from `pending_action.actions[]`. The Investigator timeline shows a regular event entry "Awaiting human attestation" with no buttons.

**Files:**
- Delete: `AttestationRequiredCard` block in `frontend/src/components/Investigation/AISupervisor.tsx`
- Add: `PinnedActionCard` component in `frontend/src/components/Chat/PinnedActionCard.tsx`

---

## Issue 5: No Timeout Recovery for Discovery Attestation

**Problem:** `ATTESTATION_TIMEOUT_S` (600s) is defined but on timeout the session stays in `DIAGNOSIS_COMPLETE` forever. No recovery path.

**Root Cause:** No timeout handler defined.

**Solution:**
- On timeout: emit chat message "Attestation window expired. Findings are still available for review."
- Re-show the same action chips `[Approve Findings] [Reject] [Show Details]` — don't degrade to text-only
- Update `pending_action.expires_at = null` (no longer time-bound, waits indefinitely)
- Log `decision: "timed_out_reset"` to audit trail
- User clicks chip whenever ready — normal flow resumes via state-driven resume

**Implementation:** Background task checks `pending_action.expires_at`. On expiry, emits timeout chat message and resets expiry. Supervisor stays exited — no coroutine held.

**Files:**
- Modify: `backend/src/agents/supervisor.py` — timeout handler in background task
- Modify: `backend/src/utils/attestation_log.py` — log timeout events

---

## Issue 6: WebSocket Disconnect During `waiting_for_input`

**Problem:** User clicks "Approve" as WS drops. POST may succeed but frontend doesn't get confirmation. On reconnect, UI re-shows "awaiting_review". User clicks again — duplicate processed.

**Root Cause:** No idempotency. Frontend state derived from WS events, not backend truth.

**Solution:**

**Idempotency — scoped per action type:**

| Action | Idempotent? | Behavior | Mechanism |
|--------|-------------|----------|-----------|
| Attestation approve/reject | Strict | Ignore duplicates | `if state.attestation_acknowledged: return existing` |
| Fix approve/reject | Strict | Ignore duplicates | `if state.fix_decided: return existing` |
| Fix feedback | Append with dedup | Accept new, skip same | `feedback_id` client UUID |
| Repo approval | Mutable | Allow override | `decision_version` counter, `new > current` |
| Campaign execute | Strict | Prevent double execution | `if campaign.status == "executing": return existing` |

**Frontend reconnect:** On WS reconnect, fetch `GET /session/{id}/status` which includes `pending_action` object. If `pending_action` is null, clear pinned card. If present, re-render card from `pending_action`.

**`pending_action` shape:**
```python
class PendingAction:
    type: Literal[
        "attestation_required", "fix_approval",
        "repo_confirm", "campaign_execute_confirm",
        "code_agent_question"
    ]
    blocking: bool           # True = pipeline paused
    actions: list[str]       # ["approve", "reject", "details"]
    expires_at: datetime | None  # UTC expiry, null = indefinite
    context: dict            # Gate-specific data
    version: int             # For idempotency
```

Frontend renders this as a dumb card — no gate-specific logic needed.

**Files:**
- Add: `backend/src/models/pending_action.py` — PendingAction dataclass
- Modify: `backend/src/api/routes_v4.py` — return `pending_action` in status endpoint, add idempotency checks
- Modify: `frontend/src/hooks/useWebSocket.ts` — fetch status on reconnect
- Modify: `frontend/src/components/Chat/ChatDrawer.tsx` — render from pending_action

---

## Issue 7: Per-Finding Attestation Has No UI

**Problem:** `POST /session/{id}/attestation/findings` endpoint exists but no frontend invokes it. Dead endpoint.

**Root Cause:** Built speculatively without UI work.

**Solution:** Remove the endpoint. Under chat-first design, per-finding decisions happen naturally in conversation:
- Discovery attestation chat card shows findings summary
- `[Show Details]` opens telescope with findings list
- User types "reject the memory leak finding" in chat
- IntentParser extracts `{type: "reject_attestation", entities: {finding_id: "memory_leak"}}`
- Backend handles per-finding logic inline
- Or user clicks `[Approve Findings]` to approve all

Remove: `AttestationGate` dataclass, `/attestation/findings` endpoint, `_per_finding_gate` from supervisor.

**Files:**
- Delete: `backend/src/models/attestation.py` (AttestationGate, keep AttestationDecision for logger)
- Modify: `backend/src/api/routes_v4.py` — remove per-finding endpoint
- Modify: `backend/src/agents/supervisor.py` — remove `_per_finding_gate`

---

## Issue 8: Campaign State is Memory-Only

**Problem:** Campaign repo approvals live in RAM. Page refresh or server restart loses all approvals.

**Root Cause:** Campaign state never persisted.

**Solution:** Persist campaign state to Redis via `RedisSessionStore`:
- On every repo decision: `session_store.save(f"campaign:{session_id}", campaign.to_dict())`
- On session load: restore campaign state from Redis
- TTL matches session TTL (24h default)
- Frontend fetches via existing `GET /session/{id}/campaign` which now reads from Redis

**Files:**
- Modify: `backend/src/api/routes_v4.py` — persist campaign state on every decision
- Modify: `backend/src/agents/agent3/campaign_orchestrator.py` — add `to_dict()`/`from_dict()`
- Modify: `backend/src/utils/redis_store.py` — campaign save/load helpers

---

## Issue 9: Fix Feedback Lost on Disconnect

**Problem:** User sends revision feedback, WS drops mid-generation. Feedback may be duplicated on reconnect.

**Root Cause:** No dedup on feedback submissions.

**Solution:**
- Each feedback submission gets a client-generated UUID (`feedback_id`)
- Backend deduplicates: if `feedback_id` already in `fix_result.human_feedback`, skip
- Frontend stores last `feedback_id` in state; on reconnect, if generation still in progress, don't re-submit
- Piggybacks on idempotency model from Issue 6

**Files:**
- Modify: `backend/src/agents/supervisor.py` — dedup feedback by ID
- Modify: `frontend/src/components/Chat/ChatDrawer.tsx` — generate and track feedback_id

---

## Issue 10: No Final Confirmation Before Campaign Execute

**Problem:** "Execute Campaign" creates PRs across 5+ repos with one click. No safety gate.

**Root Cause:** Campaign execute built as simple POST trigger.

**Solution:** Chat-first confirmation gate:
- User clicks "Execute Campaign" or types "execute campaign"
- Backend saves `PendingAction(type="campaign_execute_confirm", actions=["confirm", "cancel"], context={repos: [...], pr_count: 5})`
- Emits chat message: "About to create PRs in 5 repos: [list]. This will push branches and open pull requests."
- Action chips: `[Confirm Execute] [Cancel]`
- On confirm → execute. On cancel → abort with message.
- Uses state-driven resume (same as Issue 1). No blocking wait.
- Log to audit trail.

**Files:**
- Modify: `backend/src/api/routes_v4.py` — add confirmation gate before execute
- Modify: `backend/src/agents/supervisor.py` — handle campaign_execute_confirm intent

---

## Issue 11: Double Attestation on Fix Generation

**Problem:** Two gates before a fix: (a) discovery attestation, (b) `403` guard on `/fix/generate`. FixPipelinePanel silently auto-submits (a) to bypass it.

**Root Cause:** Gate (b) was a band-aid for broken gate (a).

**Solution:** Keep only gate (a) — the discovery attestation via chat. Remove:
- `403` guard from `/fix/generate` endpoint
- `403` guard from `/campaign/generate` endpoint
- Silent auto-submit from `FixPipelinePanel.handleGenerateFix()`
- `FixPipelinePanel` entirely — its responsibilities merge into chat card + telescope drawer + chat input

Once supervisor has `attestation_acknowledged = True` from the chat approval, fix generation proceeds without redundant checks.

**Files:**
- Modify: `backend/src/api/routes_v4.py` — remove 403 guards
- Delete: `frontend/src/components/Remediation/FixPipelinePanel.tsx`
- Modify: `frontend/src/components/Chat/ChatDrawer.tsx` — add fix approval card rendering
- Modify: `frontend/src/components/Investigation/InvestigationView.tsx` — remove FixPipelinePanel import/usage

---

## Issue 12: Ambiguous Chat Input Not Re-Prompted

**Problem:** Free-text chat passes ambiguous responses ("maybe", "I guess") directly to LLM without validation. No re-prompt.

**Root Cause:** `handle_user_message()` forwards non-matching responses without parsing.

**Solution — Formal Intent Parser Layer:**

```python
class UserIntent:
    type: Literal[
        "approve_attestation", "reject_attestation",
        "approve_fix", "reject_fix", "fix_feedback",
        "approve_repo", "reject_repo",
        "confirm_execute", "cancel_execute",
        "ask_question", "general_chat"
    ]
    confidence: float
    entities: dict  # {"finding_id": "2", "feedback": "handle null case"}
```

**Three-layer parsing:**
1. **Exact match:** Chips send literal `__intent:approve_attestation` — no parsing needed
2. **Rules:** "yes", "lgtm", "go ahead" → approve if pending action exists. Context-aware: "yes" means "approve attestation" when attestation is pending, "general_chat" when nothing is pending.
3. **LLM fallback:** Ambiguous input → classify with pending_action context

**Low-confidence handling:** If LLM confidence < 0.7, re-show action chips: "I want to make sure I understand. Did you mean:" `[Approve] [Reject] [Just asking a question]`

**Entity extraction:** "reject the memory leak finding" → `{type: "reject_attestation", entities: {finding_id: "memory_leak"}}` — replaces per-finding endpoint with natural language.

**Files:**
- Create: `backend/src/agents/intent_parser.py` — IntentParser class
- Modify: `backend/src/agents/supervisor.py` — route through IntentParser before handle_user_message
- Modify: `frontend/src/components/Chat/ChatDrawer.tsx` — chip clicks send `__intent:` prefixed strings

---

## New Component: PinnedActionCard

A single reusable component that renders any `PendingAction` as a pinned card at the top of the chat.

**Behavior:**
- Sticky-positioned at top of chat scroll area
- Visually distinct (amber border, darker background)
- Renders `actions[]` as ActionChips
- Shows `context` summary (findings count, confidence, file list, etc.)
- Shows countdown if `expires_at` is set
- Pulses LedgerTriggerTab badge when chat drawer is closed
- On chip click: sends `__intent:{action}` via chat message
- On action resolved: card slides away, replaced by confirmation message in chat flow

**Files:**
- Create: `frontend/src/components/Chat/PinnedActionCard.tsx`

---

## Files Removed (Total)

| File | Reason |
|------|--------|
| `AttestationGateUI.tsx` | Already deleted (popup modal) |
| `FixPipelinePanel.tsx` | Merged into chat + telescope |
| `AttestationRequiredCard` (in AISupervisor.tsx) | Replaced by PinnedActionCard |
| `AttestationGate` dataclass | Replaced by PendingAction |
| `/attestation/findings` endpoint | Replaced by natural language in chat |
| `_wait_for_attestation()` | Replaced by state-driven resume |
| `_attestation_event` | No human-timescale asyncio.Event |

---

## Data Flow Summary

```
User clicks chip or types message
  → Frontend sends chat message (with __intent: prefix for chips)
  → POST /api/v4/session/{id}/chat
  → IntentParser.parse(message, pending_action) → UserIntent
  → If confidence < 0.7: re-prompt with chips
  → If structured decision: route to handler
      → acknowledge_attestation() / process_fix_decision() / etc.
      → Clear pending_action in Redis
      → Log to AttestationLogger (Redis Streams)
      → Call supervisor.resume(session_id)
      → Emit confirmation chat message
  → If question: answer normally, keep pending_action alive
  → If general_chat: route to normal LLM handler
```

```
Supervisor hits attestation point
  → Check auto-approval (confidence >= 0.85, no critic challenges)
  → If auto-approved: log, set acknowledged, continue pipeline
  → If human needed:
      → Save PendingAction to Redis
      → Emit rich chat message with action chips
      → return (exit supervisor loop cleanly)
      → No coroutine held open
```

```
Frontend on load / reconnect
  → GET /session/{id}/status → includes pending_action
  → If pending_action exists: render PinnedActionCard
  → If null: no card
  → LedgerTriggerTab pulses if pending_action.blocking == true
```
