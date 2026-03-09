# Findings-Aware Chat Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable findings-aware multi-turn chat for both cluster and app diagnostics so users can ask questions grounded in actual diagnostic findings.

**Architecture:** Add `_handle_cluster_chat()` in routes_v4.py for cluster sessions, enrich `supervisor.handle_user_message()` with serialized findings for app sessions, wire ChatProvider into ClusterWarRoom frontend, and initialize `chat_history` on both session types.

**Tech Stack:** Python FastAPI, AnthropicClient (LLM), React ChatProvider/ChatDrawer, TypeScript

---

### Task 1: Initialize `chat_history` on session creation

**Files:**
- Modify: `backend/src/api/routes_v4.py:165-176` (cluster session dict)
- Modify: `backend/src/api/routes_v4.py:196-205` (app session dict)
- Test: `backend/tests/test_cluster_routing.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_cluster_routing.py`:

```python
class TestChatHistory:
    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_cluster_session_has_chat_history(self, mock_build, mock_run, client):
        """Cluster session should be created with empty chat_history."""
        mock_build.return_value = MagicMock()
        resp = client.post("/api/v4/session/start", json={
            "service_name": "Cluster Diagnostics",
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.cluster.example.com",
        })
        assert resp.status_code == 200
        from src.api.routes_v4 import sessions
        session = sessions[resp.json()["session_id"]]
        assert session["chat_history"] == []

    @patch("src.api.routes_v4.run_diagnosis", new_callable=AsyncMock)
    def test_app_session_has_chat_history(self, mock_run, client):
        """App session should be created with empty chat_history."""
        resp = client.post("/api/v4/session/start", json={
            "service_name": "my-app",
        })
        assert resp.status_code == 200
        from src.api.routes_v4 import sessions
        session = sessions[resp.json()["session_id"]]
        assert session["chat_history"] == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_cluster_routing.py::TestChatHistory -v`
Expected: FAIL with `KeyError: 'chat_history'`

**Step 3: Add `chat_history` to both session dicts**

In `backend/src/api/routes_v4.py`, add `"chat_history": []` to the cluster session dict (after line 175):

```python
        sessions[session_id] = {
            "service_name": request.serviceName or "Cluster Diagnostics",
            "incident_id": incident_id,
            "phase": "initial",
            "confidence": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "emitter": emitter,
            "state": None,
            "profile_id": profile_id,
            "capability": "cluster_diagnostics",
            "graph": graph,
            "chat_history": [],
        }
```

And to the app session dict (after line 204):

```python
    sessions[session_id] = {
        "service_name": request.serviceName,
        "incident_id": incident_id,
        "phase": "initial",
        "confidence": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "emitter": emitter,
        "state": None,
        "profile_id": profile_id,
        "chat_history": [],
    }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_cluster_routing.py::TestChatHistory -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_cluster_routing.py
git commit -m "feat: initialize chat_history on both session types"
```

---

### Task 2: Add `_handle_cluster_chat()` in routes_v4.py

**Files:**
- Modify: `backend/src/api/routes_v4.py:414-438` (chat endpoint)
- Test: `backend/tests/test_cluster_routing.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_cluster_routing.py`:

```python
class TestClusterChat:
    def _make_cluster_session(self, sid, state=None):
        """Helper to insert a cluster session with optional state."""
        from src.api.routes_v4 import sessions
        sessions[sid] = {
            "service_name": "Cluster Diagnostics",
            "incident_id": "INC-100",
            "phase": "complete" if state else "initial",
            "confidence": 80 if state else 0,
            "created_at": "2026-01-01T00:00:00Z",
            "capability": "cluster_diagnostics",
            "state": state,
            "chat_history": [],
        }

    def test_cluster_chat_no_state(self, client):
        """Chat returns canned message when diagnostics haven't started."""
        sid = "00000000-0000-4000-8000-000000000020"
        self._make_cluster_session(sid, state=None)
        resp = client.post(f"/api/v4/session/{sid}/chat", json={"message": "What's wrong?"})
        assert resp.status_code == 200
        data = resp.json()
        assert "still starting" in data["response"].lower()

    @patch("src.api.routes_v4.AnthropicClient")
    def test_cluster_chat_with_state(self, MockClient, client):
        """Chat returns LLM response grounded in cluster findings."""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(text="The control plane has high latency."))
        MockClient.return_value = mock_llm

        sid = "00000000-0000-4000-8000-000000000021"
        state = {
            "domain_reports": [{"domain": "ctrl_plane", "status": "DEGRADED", "confidence": 0.7}],
            "causal_chains": [{"chain": "etcd slow -> apiserver timeout"}],
            "health_report": {"overall_status": "DEGRADED"},
        }
        self._make_cluster_session(sid, state=state)
        resp = client.post(f"/api/v4/session/{sid}/chat", json={"message": "Why is the cluster slow?"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["response"]) > 0
        assert data["phase"] == "complete"

    @patch("src.api.routes_v4.AnthropicClient")
    def test_cluster_chat_stores_history(self, MockClient, client):
        """Chat appends user and assistant messages to chat_history."""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(text="Here is the answer."))
        MockClient.return_value = mock_llm

        sid = "00000000-0000-4000-8000-000000000022"
        state = {"domain_reports": [], "health_report": {"overall_status": "OK"}}
        self._make_cluster_session(sid, state=state)

        client.post(f"/api/v4/session/{sid}/chat", json={"message": "Hello"})

        from src.api.routes_v4 import sessions
        history = sessions[sid]["chat_history"]
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Here is the answer."

    def test_cluster_chat_history_cap(self, client):
        """Chat history is capped at 20 messages."""
        sid = "00000000-0000-4000-8000-000000000023"
        state = {"domain_reports": []}
        self._make_cluster_session(sid, state=state)

        from src.api.routes_v4 import sessions
        # Pre-fill with 20 messages
        sessions[sid]["chat_history"] = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"}
            for i in range(20)
        ]
        # The next chat call should trim oldest messages
        with patch("src.api.routes_v4.AnthropicClient") as MockClient:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=MagicMock(text="Reply"))
            MockClient.return_value = mock_llm

            client.post(f"/api/v4/session/{sid}/chat", json={"message": "New question"})

        history = sessions[sid]["chat_history"]
        assert len(history) <= 20

    def test_cluster_chat_unknown_session(self, client):
        """Chat returns 404 for unknown session."""
        resp = client.post("/api/v4/session/nonexistent/chat", json={"message": "Hello"})
        assert resp.status_code == 422 or resp.status_code == 404
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_cluster_routing.py::TestClusterChat -v`
Expected: FAIL — cluster sessions hit 404 ("Session supervisor not found")

**Step 3: Implement `_handle_cluster_chat()` and branch the chat endpoint**

In `backend/src/api/routes_v4.py`, add the import at the top (near other imports):

```python
from src.utils.llm_client import AnthropicClient
import json
```

Add the `_handle_cluster_chat` helper function before the chat endpoint:

```python
CLUSTER_CHAT_HISTORY_CAP = 20


async def _handle_cluster_chat(session: dict, message: str) -> str:
    """Handle chat for cluster diagnostics sessions using full cluster state as context."""
    state = session.get("state")
    if not state:
        return "Diagnostics are still starting. Please wait for initial results before asking questions."

    chat_history = session.setdefault("chat_history", [])

    # Build system prompt with cluster state context
    state_context = json.dumps(state, indent=2, default=str)
    # Cap context to avoid token overflow (~8000 chars ≈ ~2000 tokens)
    if len(state_context) > 8000:
        state_context = state_context[:8000] + "\n... (truncated)"

    system_prompt = f"""You are a cluster diagnostics assistant for an AI-powered SRE platform.
You have access to the full diagnostic state below. Use it to answer questions accurately.

Answer questions about diagnostic findings, help interpret causal chains, explain domain-specific
issues (control plane, node health, networking, storage), guide remediation steps, and suggest
re-analysis when the user provides new context.

Be concise. Reference specific findings from the state when answering.

## Current Cluster Diagnostic State
{state_context}"""

    # Build messages list from history + new user message
    messages = [{"role": m["role"], "content": m["content"]} for m in chat_history]
    messages.append({"role": "user", "content": message})

    # Call LLM
    try:
        llm = AnthropicClient(agent_name="cluster_chat")
        response = await llm.chat(
            prompt=message,
            system=system_prompt,
            messages=messages,
            max_tokens=1024,
        )
        response_text = response.text
    except Exception as e:
        logger.error("Cluster chat LLM call failed", extra={"error": str(e)})
        return "I couldn't process your question. Please try again."

    # Append to history and cap
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": response_text})
    if len(chat_history) > CLUSTER_CHAT_HISTORY_CAP:
        session["chat_history"] = chat_history[-CLUSTER_CHAT_HISTORY_CAP:]

    return response_text
```

Then modify the existing `chat()` endpoint to branch by capability:

```python
@router_v4.post("/session/{session_id}/chat", response_model=ChatResponse)
async def chat(session_id: str, request: ChatRequest):
    _validate_session_id(session_id)
    logger.info("Chat message received", extra={"session_id": session_id, "action": "chat"})

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Branch by capability
    if session.get("capability") == "cluster_diagnostics":
        response_text = await _handle_cluster_chat(session, request.message)
        return ChatResponse(
            response=response_text,
            phase=session.get("phase", "initial"),
            confidence=session.get("confidence", 0),
        )

    # App diagnostics — existing supervisor flow
    supervisor = supervisors.get(session_id)
    if not supervisor:
        raise HTTPException(status_code=404, detail="Session supervisor not found")

    state = session.get("state")
    if state:
        response_text = await supervisor.handle_user_message(request.message, state)
    else:
        response_text = "Analysis is still starting up. Please wait a moment."

    return ChatResponse(
        response=response_text,
        phase=session.get("phase", "initial"),
        confidence=session.get("confidence", 0),
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_cluster_routing.py::TestClusterChat -v`
Expected: PASS

**Step 5: Run full test suite to check for regressions**

Run: `cd backend && python3 -m pytest tests/ -v --tb=short`
Expected: All pass

**Step 6: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_cluster_routing.py
git commit -m "feat: add findings-aware chat for cluster diagnostics"
```

---

### Task 3: Enrich app chat with findings context and conversation history

**Files:**
- Modify: `backend/src/agents/supervisor.py:2264-2274` (handle_user_message prompt)
- Test: `backend/tests/test_cluster_routing.py` (add app chat test)

**Step 1: Write the failing test**

Add to `backend/tests/test_cluster_routing.py`:

```python
class TestAppChatFindings:
    """Verify app chat includes actual findings in the LLM prompt."""

    @patch("src.agents.supervisor.SupervisorAgent.handle_user_message")
    def test_app_chat_calls_handle_user_message(self, mock_handle, client):
        """App chat routes through supervisor.handle_user_message()."""
        mock_handle.return_value = "Here's an answer based on findings."

        from src.api.routes_v4 import sessions, supervisors
        sid = "00000000-0000-4000-8000-000000000030"
        mock_supervisor = MagicMock()
        mock_supervisor.handle_user_message = AsyncMock(return_value="Findings-based answer")

        sessions[sid] = {
            "service_name": "my-app",
            "incident_id": "INC-030",
            "phase": "diagnosis_complete",
            "confidence": 85,
            "created_at": "2026-01-01T00:00:00Z",
            "state": MagicMock(),  # SupervisorAgent state object
            "chat_history": [],
        }
        supervisors[sid] = mock_supervisor

        resp = client.post(f"/api/v4/session/{sid}/chat", json={"message": "Why is memory spiking?"})
        assert resp.status_code == 200
        mock_supervisor.handle_user_message.assert_called_once()
```

**Step 2: Run test to verify it passes (baseline — existing behavior)**

Run: `cd backend && python3 -m pytest tests/test_cluster_routing.py::TestAppChatFindings -v`
Expected: PASS (this is a baseline test)

**Step 3: Enrich `handle_user_message()` with findings context and conversation history**

In `backend/src/agents/supervisor.py`, replace the prompt section (lines 2264-2274) with findings-aware context:

```python
        # ── Serialize findings context for the LLM ──
        findings_context = self._serialize_findings_for_chat(state)

        # ── Build conversation history ──
        session = None
        from src.api.routes_v4 import sessions
        for sid, s in sessions.items():
            if s.get("state") is state:
                session = s
                break

        chat_history = session.get("chat_history", []) if session else []

        # Build messages with history
        history_messages = [{"role": m["role"], "content": m["content"]} for m in chat_history]
        history_messages.append({"role": "user", "content": message})

        system_text = f"""You are an AI SRE assistant helping diagnose application issues.
You have access to the full diagnostic findings below. Use them to answer questions accurately.

Explain findings, interpret root causes, clarify metric anomalies, guide remediation, and
suggest follow-up investigation when appropriate. Be concise and reference specific findings.

## Current Diagnostic State
- Phase: {state.phase.value}
- Service: {state.service_name}
- Agents completed: {state.agents_completed}
- Overall confidence: {state.overall_confidence}%

## Diagnostic Findings
{findings_context}"""

        # Stream LLM response — emit chat_chunk messages via WebSocket for live typing
        ws_mgr = self._event_emitter._websocket_manager if self._event_emitter else None
        full_response = ""
        async for chunk in self.llm_client.chat_stream(
            prompt=message,
            system=system_text,
            messages=history_messages,
        ):
            full_response += chunk
            if ws_mgr:
                await ws_mgr.send_message(
                    state.session_id,
                    {"type": "chat_chunk", "data": {"content": chunk, "done": False}},
                )
```

Also keep the existing final chat_chunk and return (lines 2286-2302 remain unchanged).

**After the `return full_response` line**, add conversation history storage:

```python
        # Store conversation history
        if session:
            chat_history.append({"role": "user", "content": message})
            chat_history.append({"role": "assistant", "content": full_response})
            if len(chat_history) > 20:
                session["chat_history"] = chat_history[-20:]
```

**Step 4: Add the `_serialize_findings_for_chat()` helper method**

Add this method to the `SupervisorAgent` class (after `handle_user_message`):

```python
    def _serialize_findings_for_chat(self, state: DiagnosticState) -> str:
        """Serialize diagnostic findings into a concise text block for chat LLM context.

        Prioritizes high-severity findings. Caps at ~2000 tokens (~8000 chars).
        """
        sections = []
        char_budget = 8000

        # Top findings sorted by severity
        if state.all_findings:
            sorted_findings = sorted(
                state.all_findings,
                key=lambda f: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
                    getattr(f, "severity", "low"), 3
                ),
            )
            findings_lines = []
            for f in sorted_findings[:10]:  # Top 10 findings
                agent = getattr(f, "agent_name", "unknown")
                severity = getattr(f, "severity", "unknown")
                summary = getattr(f, "summary", str(f))
                confidence = getattr(f, "confidence", 0)
                findings_lines.append(
                    f"- [{severity.upper()}] ({agent}, {confidence}% conf) {summary}"
                )
            if findings_lines:
                sections.append("### Top Findings\n" + "\n".join(findings_lines))

        # Metrics anomalies
        if hasattr(state, "metrics_anomalies") and state.metrics_anomalies:
            metrics_lines = []
            for m in state.metrics_anomalies[:5]:
                name = getattr(m, "metric_name", str(m))
                severity = getattr(m, "severity", "unknown")
                peak = getattr(m, "peak_value", "N/A")
                metrics_lines.append(f"- {name}: peak={peak}, severity={severity}")
            if metrics_lines:
                sections.append("### Metrics Anomalies\n" + "\n".join(metrics_lines))

        # Log error patterns
        if hasattr(state, "log_patterns") and state.log_patterns:
            log_lines = []
            for lp in state.log_patterns[:5]:
                pattern = getattr(lp, "pattern", str(lp))
                count = getattr(lp, "count", "N/A")
                log_lines.append(f"- {pattern} (count: {count})")
            if log_lines:
                sections.append("### Log Error Patterns\n" + "\n".join(log_lines))

        # K8s issues
        if hasattr(state, "k8s_issues") and state.k8s_issues:
            k8s_lines = []
            for k in state.k8s_issues[:5]:
                k8s_lines.append(f"- {k}")
            if k8s_lines:
                sections.append("### K8s Issues\n" + "\n".join(k8s_lines))

        # Code analysis root cause
        if hasattr(state, "code_analysis") and state.code_analysis:
            ca = state.code_analysis
            location = getattr(ca, "root_cause_location", None)
            if location:
                sections.append(f"### Code Analysis\nRoot cause location: {location}")

        # Causal reasoning
        if hasattr(state, "causal_chain") and state.causal_chain:
            sections.append(f"### Causal Chain\n{state.causal_chain}")

        result = "\n\n".join(sections) if sections else "No findings yet."

        # Enforce char budget
        if len(result) > char_budget:
            result = result[:char_budget] + "\n... (truncated)"

        return result
```

**Step 5: Run tests to verify everything passes**

Run: `cd backend && python3 -m pytest tests/ -v --tb=short`
Expected: All pass

**Step 6: Commit**

```bash
git add backend/src/agents/supervisor.py backend/tests/test_cluster_routing.py
git commit -m "feat: enrich app chat with findings context and conversation history"
```

---

### Task 4: Wire ChatProvider into ClusterWarRoom frontend

**Files:**
- Modify: `frontend/src/App.tsx:414-423` (ClusterWarRoom rendering)
- Modify: `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx` (add ChatDrawer + LedgerTriggerTab)

**Step 1: Wrap ClusterWarRoom in ChatProvider in App.tsx**

In `frontend/src/App.tsx`, replace the cluster-diagnostics view block (lines 414-423):

```tsx
        {viewState === 'cluster-diagnostics' && activeSession && (
          <ChatProvider sessionId={activeSessionId} events={currentTaskEvents} onRegisterChatHandler={chatResponseRef} onRegisterStreamStart={streamStartRef} onRegisterStreamAppend={streamAppendRef} onRegisterStreamFinish={streamFinishRef} onPhaseUpdate={handleChatPhaseUpdate}>
            <ClusterWarRoom
              session={activeSession}
              events={currentTaskEvents}
              wsConnected={wsConnected}
              phase={currentPhase}
              confidence={confidence}
              onGoHome={handleGoHome}
            />
          </ChatProvider>
        )}
```

**Step 2: Add ChatDrawer and LedgerTriggerTab to ClusterWarRoom**

In `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx`, add imports:

```tsx
import ChatDrawer from '../Chat/ChatDrawer';
import LedgerTriggerTab from '../Chat/LedgerTriggerTab';
```

Then add the components at the bottom of ClusterWarRoom's return JSX (just before the closing wrapper `</div>`):

```tsx
      <ChatDrawer />
      <LedgerTriggerTab />
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Verify build succeeds**

Run: `cd frontend && npx vite build`
Expected: Build succeeds

**Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx
git commit -m "feat: wire ChatProvider and ChatDrawer into ClusterWarRoom"
```

---

### Task 5: Full verification

**Step 1: Run backend tests**

Run: `cd backend && python3 -m pytest tests/ -v --tb=short`
Expected: All pass, 0 failures

**Step 2: Run frontend TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Run frontend build**

Run: `cd frontend && npx vite build`
Expected: Build succeeds

**Step 4: Commit any remaining changes**

If any fixes were needed, commit them.

---

## Summary

| Task | Files | Description |
|------|-------|-------------|
| 1 | routes_v4.py, test_cluster_routing.py | Init `chat_history: []` on both session types |
| 2 | routes_v4.py, test_cluster_routing.py | `_handle_cluster_chat()` + branch chat endpoint by capability |
| 3 | supervisor.py, test_cluster_routing.py | Enrich app chat with `_serialize_findings_for_chat()` + conversation history |
| 4 | App.tsx, ClusterWarRoom.tsx | Wrap ClusterWarRoom in ChatProvider, add ChatDrawer + LedgerTriggerTab |
| 5 | — | Full verification (tests + tsc + build) |
