# Findings-Aware Chat for Cluster & App Diagnostics

**Date:** 2026-02-27
**Status:** Approved
**Approach:** Lightweight chat handler in routes_v4 (Approach A)

## Problem

Neither diagnostic capability has findings-aware chat:

- **Cluster diagnostics** has no chat at all. The `/chat` endpoint returns 404 because cluster sessions don't have a supervisor. The ClusterWarRoom UI doesn't render the chat drawer.
- **App diagnostics** has chat wired end-to-end, but `supervisor.handle_user_message()` only passes `len(state.all_findings)` (a count) to the LLM. Users cannot ask "why is memory spiking?" and get an answer grounded in actual findings.

Both capabilities also lack multi-turn conversation history.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Chat location | Reuse existing ChatDrawer | Frontend chat system is already session-agnostic |
| Chat scope | Clarify findings + guide re-analysis + remediation help | Full assistant experience |
| LLM context | Full diagnostic state | Accuracy over token cost |
| Conversation | Multi-turn (20-message cap) | Users need follow-up ability |
| Scope | Fix both cluster and app diagnostics | Same pattern, same gap |

## Architecture

### Backend: Cluster Chat (new)

Add `_handle_cluster_chat()` in `routes_v4.py`. The `/chat` endpoint branches by capability before looking up the supervisor:

```
POST /api/v4/session/{session_id}/chat
  if capability == "cluster_diagnostics" -> _handle_cluster_chat()
  else -> existing supervisor flow
```

`_handle_cluster_chat()`:
1. Reads `session["state"]` (cluster state dict: domain reports, causal chains, health report, remediation)
2. Reads/appends `session["chat_history"]` (list of `{role, content}` dicts)
3. Builds system prompt with full cluster state as JSON context
4. Calls `AnthropicClient.chat()` with conversation history + system prompt
5. Appends user message and assistant response to `chat_history`
6. Returns `ChatResponse(response=..., phase=..., confidence=...)`

System prompt instructs the LLM: "You are a cluster diagnostics assistant. Answer questions about diagnostic findings, help interpret causal chains, guide remediation steps, and suggest re-analysis when appropriate."

### Backend: App Chat (enhance existing)

Enhance `supervisor.handle_user_message()` to serialize actual findings into the prompt:

- Top findings: summary, severity, agent name, confidence
- Metrics anomalies: metric name, peak value, severity
- Log error patterns (if present)
- K8s issues: pod statuses, crashloops, OOM kills
- Code analysis root cause location (if present)
- Causal reasoning chain

Cap serialized context to ~2000 tokens, prioritize high-severity findings.

Add multi-turn conversation history:
- Store in `session["chat_history"]` (same pattern as cluster)
- Pass to LLM alongside findings context
- 20-message cap

### Frontend: Wire ChatProvider into ClusterWarRoom

Wrap ClusterWarRoom in `<ChatProvider sessionId={...}>` in App.tsx. Render `<ChatDrawer />` and `<LedgerTriggerTab />` alongside it. No changes to ChatContext, ChatDrawer, or the API service.

### Session Initialization

Add `"chat_history": []` to session dict for both app and cluster sessions in `start_session()`.

## State Freshness

The system prompt is rebuilt on every chat call from `session["state"]`:
- Mid-diagnosis: answers based on partial results (whatever agents have reported so far)
- After completion: full picture with all findings
- No stale context

## Error Handling

| Scenario | Behavior |
|----------|----------|
| State is None (diagnosis not started) | Canned message: "Diagnostics are still starting. Please wait." No LLM call. |
| LLM call fails | Return: "I couldn't process your question. Please try again." |
| Diagnosis failed (`phase == "error"`) | LLM sees partial state + error context, can acknowledge the failure |

## Out of Scope

- **Re-analysis from chat**: Chat is read-only. The LLM can *suggest* re-running diagnostics but cannot trigger graph re-runs. Tool-use integration is a future enhancement.
- **Streaming responses**: Use simple request/response for now, matching existing chat behavior.

## Testing

Add to `test_cluster_routing.py`:
1. Chat returns 200 for a cluster session (mock `AnthropicClient`)
2. Chat returns "still starting" message when state is None
3. Chat returns 404 for unknown session

Existing app chat tests remain valid; add a test verifying findings are included in the LLM prompt.

## Files Changed

| File | Change |
|------|--------|
| `backend/src/api/routes_v4.py` | Branch `/chat` by capability, add `_handle_cluster_chat()`, init `chat_history` |
| `backend/src/agents/supervisor.py` | Enrich `handle_user_message()` with findings context + conversation history |
| `frontend/src/App.tsx` | Wrap ClusterWarRoom in ChatProvider, render ChatDrawer |
| `backend/tests/test_cluster_routing.py` | Add cluster chat tests |
