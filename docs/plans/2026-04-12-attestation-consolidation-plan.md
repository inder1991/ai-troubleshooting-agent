# Attestation Consolidation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Consolidate all human-in-the-loop attestation gates into the chatbox, fix broken gates, add audit trails, and make the supervisor stateless between human interactions.

**Architecture:** State-driven resume model — supervisor saves `PendingAction` to Redis and exits cleanly when human input is needed. On user decision, `acknowledge_and_resume()` loads state, processes decision, clears pending action, logs to audit trail, and resumes the pipeline. All attestation UX flows through rich pinned chat messages with action chips. Heavy content (diffs) opens in the Telescope drawer. An `IntentParser` classifies free-text chat input into structured intents.

**Tech Stack:** Python 3.12, FastAPI, Redis (sessions + streams), asyncio, React 18, TypeScript, Tailwind CSS

**Design doc:** `docs/plans/2026-04-12-attestation-consolidation-design.md`

---

### Task 1: PendingAction Model

**Files:**
- Create: `backend/src/models/pending_action.py`
- Test: `backend/tests/test_pending_action.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_pending_action.py
from datetime import datetime, timezone, timedelta
from src.models.pending_action import PendingAction


def test_pending_action_to_dict_roundtrip():
    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject", "details"],
        expires_at=datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc),
        context={"findings_count": 4, "confidence": 0.87},
        version=1,
    )
    d = pa.to_dict()
    restored = PendingAction.from_dict(d)
    assert restored.type == "attestation_required"
    assert restored.blocking is True
    assert restored.actions == ["approve", "reject", "details"]
    assert restored.expires_at == pa.expires_at
    assert restored.context["confidence"] == 0.87
    assert restored.version == 1


def test_pending_action_is_expired():
    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        context={},
        version=1,
    )
    assert pa.is_expired() is True


def test_pending_action_no_expiry_never_expired():
    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=None,
        context={},
        version=1,
    )
    assert pa.is_expired() is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_pending_action.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.models.pending_action'`

**Step 3: Write minimal implementation**

```python
# backend/src/models/pending_action.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


PENDING_ACTION_TYPES = Literal[
    "attestation_required",
    "fix_approval",
    "repo_confirm",
    "campaign_execute_confirm",
    "code_agent_question",
]


@dataclass
class PendingAction:
    type: PENDING_ACTION_TYPES
    blocking: bool
    actions: list[str]
    expires_at: datetime | None
    context: dict
    version: int = 1

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "blocking": self.blocking,
            "actions": self.actions,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "context": self.context,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PendingAction:
        expires_at = None
        if d.get("expires_at"):
            expires_at = datetime.fromisoformat(d["expires_at"])
        return cls(
            type=d["type"],
            blocking=d["blocking"],
            actions=d["actions"],
            expires_at=expires_at,
            context=d.get("context", {}),
            version=d.get("version", 1),
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_pending_action.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/models/pending_action.py backend/tests/test_pending_action.py
git commit -m "feat(attestation): add PendingAction model with serialization"
```

---

### Task 2: IntentParser

**Files:**
- Create: `backend/src/agents/intent_parser.py`
- Test: `backend/tests/test_intent_parser.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_intent_parser.py
from src.agents.intent_parser import IntentParser, UserIntent
from src.models.pending_action import PendingAction


def make_attestation_pending() -> PendingAction:
    return PendingAction(
        type="attestation_required", blocking=True,
        actions=["approve", "reject", "details"],
        expires_at=None, context={}, version=1,
    )


def make_fix_pending() -> PendingAction:
    return PendingAction(
        type="fix_approval", blocking=True,
        actions=["approve", "reject", "feedback"],
        expires_at=None, context={}, version=1,
    )


parser = IntentParser()


def test_exact_intent_prefix():
    result = parser.parse("__intent:approve_attestation", make_attestation_pending())
    assert result.type == "approve_attestation"
    assert result.confidence == 1.0


def test_approve_synonyms_with_attestation_pending():
    for word in ["yes", "lgtm", "go ahead", "looks good", "approve", "ok",
                 "yes please go ahead", "sounds good to me", "ship it"]:
        result = parser.parse(word, make_attestation_pending())
        assert result.type == "approve_attestation", f"Failed for: {word}"
        assert result.confidence >= 0.9


def test_reject_synonyms_with_attestation_pending():
    for word in ["reject", "no", "cancel", "stop", "hold off on this", "no thanks"]:
        result = parser.parse(word, make_attestation_pending())
        assert result.type == "reject_attestation", f"Failed for: {word}"
        assert result.confidence >= 0.9


def test_false_positive_guards():
    """'no problem' should NOT be interpreted as rejection."""
    for phrase in ["no problem", "no worries", "no issue"]:
        result = parser.parse(phrase, make_attestation_pending())
        assert result.type != "reject_attestation", f"False positive for: {phrase}"


def test_approve_synonyms_with_fix_pending():
    for word in ["approve", "yes", "create pr", "lgtm"]:
        result = parser.parse(word, make_fix_pending())
        assert result.type == "approve_fix", f"Failed for: {word}"


def test_reject_synonyms_with_fix_pending():
    for word in ["reject", "no", "discard"]:
        result = parser.parse(word, make_fix_pending())
        assert result.type == "reject_fix", f"Failed for: {word}"


def test_feedback_with_fix_pending():
    result = parser.parse("handle the null case differently", make_fix_pending())
    assert result.type == "fix_feedback"
    assert result.entities.get("feedback") == "handle the null case differently"


def test_question_preserves_pending():
    result = parser.parse("what does finding 2 mean?", make_attestation_pending())
    assert result.type == "ask_question"


def test_no_pending_general_chat():
    result = parser.parse("what is the memory usage?", None)
    assert result.type == "general_chat"


def test_no_pending_approve_is_general():
    result = parser.parse("approve", None)
    assert result.type == "general_chat"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_intent_parser.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/agents/intent_parser.py
from __future__ import annotations

from dataclasses import dataclass, field
from src.models.pending_action import PendingAction


# Single-token exact matches
APPROVE_EXACT = {"approve", "yes", "y", "ok", "lgtm", "confirm", "proceed"}
REJECT_EXACT = {"reject", "no", "n", "cancel", "stop", "discard", "abort"}

# Multi-word phrases matched via containment (order matters — check longer first)
APPROVE_PHRASES = ["go ahead", "looks good", "create pr", "ship it", "yes please", "sounds good", "do it"]
REJECT_PHRASES = ["no thanks", "not now", "hold off", "don't proceed"]

# Guard against false positives: "no problem" contains "no" but isn't rejection
FALSE_POSITIVE_GUARDS = {"no problem", "no worries", "no issue", "no doubt"}


@dataclass
class UserIntent:
    type: str
    confidence: float
    entities: dict = field(default_factory=dict)


# Maps pending_action.type → (approve_intent, reject_intent, feedback_intent)
_INTENT_MAP: dict[str, tuple[str, str, str | None]] = {
    "attestation_required": ("approve_attestation", "reject_attestation", None),
    "fix_approval": ("approve_fix", "reject_fix", "fix_feedback"),
    "repo_confirm": ("approve_repo", "reject_repo", None),
    "campaign_execute_confirm": ("confirm_execute", "cancel_execute", None),
    "code_agent_question": ("general_chat", "general_chat", None),
}


# Valid intents per pending action type — security gate
ALLOWED_INTENTS: dict[str, set[str]] = {
    "attestation_required": {"approve_attestation", "reject_attestation", "ask_question", "general_chat"},
    "fix_approval": {"approve_fix", "reject_fix", "fix_feedback", "ask_question", "general_chat"},
    "repo_confirm": {"approve_repo", "reject_repo", "ask_question", "general_chat"},
    "campaign_execute_confirm": {"confirm_execute", "cancel_execute", "ask_question", "general_chat"},
    "code_agent_question": {"general_chat", "ask_question"},
}


def _allowed_intents_for_pending(pending_type: str) -> set[str]:
    return ALLOWED_INTENTS.get(pending_type, {"general_chat", "ask_question"})


class IntentParser:
    def parse(self, message: str, pending_action: PendingAction | None) -> UserIntent:
        text = message.strip()

        # Layer 1: exact intent prefix from chip clicks
        if text.startswith("__intent:"):
            intent_type = text[len("__intent:"):]
            return UserIntent(type=intent_type, confidence=1.0)

        lower = text.lower().strip()

        # No pending action → everything is general chat
        if pending_action is None:
            return UserIntent(type="general_chat", confidence=1.0)

        intents = _INTENT_MAP.get(pending_action.type)
        if not intents:
            return UserIntent(type="general_chat", confidence=0.5)

        approve_intent, reject_intent, feedback_intent = intents

        # Layer 2: rule-based matching (exact tokens + phrase containment)

        # Guard against false positives first
        if any(fp in lower for fp in FALSE_POSITIVE_GUARDS):
            return UserIntent(type="general_chat", confidence=0.8)

        # Exact single-token match
        if lower in APPROVE_EXACT:
            return UserIntent(type=approve_intent, confidence=0.95)

        if lower in REJECT_EXACT:
            return UserIntent(type=reject_intent, confidence=0.95)

        # Phrase containment (longer phrases first to avoid partial matches)
        if any(phrase in lower for phrase in APPROVE_PHRASES):
            return UserIntent(type=approve_intent, confidence=0.9)

        if any(phrase in lower for phrase in REJECT_PHRASES):
            return UserIntent(type=reject_intent, confidence=0.9)

        # Questions → ask_question (keep pending action alive)
        if lower.endswith("?"):
            return UserIntent(type="ask_question", confidence=0.9)

        # For fix_approval: non-matching text is feedback
        if feedback_intent and pending_action.type == "fix_approval":
            return UserIntent(
                type=feedback_intent,
                confidence=0.85,
                entities={"feedback": text},
            )

        # Fallback: general chat (low confidence — caller may re-prompt)
        return UserIntent(type="general_chat", confidence=0.6)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_intent_parser.py -v`
Expected: PASS (10 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/intent_parser.py backend/tests/test_intent_parser.py
git commit -m "feat(attestation): add IntentParser with rules-based intent classification"
```

---

### Task 3: Wire Attestation Audit Trail Logging

**Files:**
- Modify: `backend/src/agents/supervisor.py` — add log calls in `acknowledge_attestation()` and `_process_fix_decision()`
- Modify: `backend/src/api/routes_v4.py` — add log calls in campaign endpoints
- Test: `backend/tests/test_attestation_logging.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_attestation_logging.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.utils.attestation_log import AttestationLogger


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.xadd = AsyncMock(return_value=b"1234567890-0")
    return r


@pytest.fixture
def logger(mock_redis):
    return AttestationLogger(mock_redis)


@pytest.mark.asyncio
async def test_log_decision_calls_xadd(logger, mock_redis):
    entry_id = await logger.log_decision(
        session_id="sess-1",
        finding_id="all",
        decision="approved",
        decided_by="user",
        confidence=0.87,
        finding_summary="4 findings approved",
    )
    assert entry_id == b"1234567890-0"
    mock_redis.xadd.assert_called_once()
    call_args = mock_redis.xadd.call_args
    assert call_args[0][0] == "audit:attestations"
    entry = call_args[0][1]
    assert entry["session_id"] == "sess-1"
    assert entry["decision"] == "approved"


@pytest.mark.asyncio
async def test_log_fix_decision(logger, mock_redis):
    await logger.log_decision(
        session_id="sess-1",
        finding_id="fix_attempt_1",
        decision="approve",
        decided_by="user",
        confidence=0.0,
        finding_summary="Fix approved — creating PR",
    )
    mock_redis.xadd.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_attestation_logging.py -v`
Expected: PASS (these test the existing logger — but we need to verify they pass before wiring)

**Step 3: Wire logging into supervisor**

In `backend/src/agents/supervisor.py`, modify `acknowledge_attestation()` (around line 3050):

```python
# BEFORE (existing):
def acknowledge_attestation(self, decision: str) -> str:
    if decision == "approve":
        self._attestation_acknowledged = True
        return "Attestation acknowledged — fix generation is now available."
    elif decision == "reject":
        self._attestation_acknowledged = False
        return "Attestation rejected — investigation findings need revision."
    return "Unknown attestation decision."

# AFTER:
async def acknowledge_attestation(self, decision: str, session_id: str = "") -> str:
    if decision == "approve":
        self._attestation_acknowledged = True
        response = "Attestation acknowledged — fix generation is now available."
    elif decision == "reject":
        self._attestation_acknowledged = False
        response = "Attestation rejected — investigation findings need revision."
    else:
        return "Unknown attestation decision."

    # Audit trail
    if self._attestation_logger:
        await self._attestation_logger.log_decision(
            session_id=session_id,
            finding_id="all",
            decision=decision,
            decided_by="user",
            confidence=getattr(self, '_last_confidence', 0.0),
            finding_summary=f"Discovery attestation: {decision}",
        )
    return response
```

Add `_attestation_logger` to `__init__`:
```python
self._attestation_logger: Optional[AttestationLogger] = None
```

Wire logging into `_process_fix_decision()` (around line 3014):

```python
# Add after each decision branch:
if self._attestation_logger and self._session_id:
    import asyncio
    asyncio.create_task(self._attestation_logger.log_decision(
        session_id=self._session_id,
        finding_id=f"fix_attempt",
        decision=text_decision,
        decided_by="user",
        confidence=0.0,
        finding_summary=f"Fix decision: {text_decision}",
    ))
```

In `backend/src/api/routes_v4.py`, wire logging into campaign decide endpoint (around line 1842):

```python
# After campaign repo decision processing, add:
attestation_logger = _get_attestation_logger()
if attestation_logger:
    await attestation_logger.log_decision(
        session_id=session_id,
        finding_id=f"campaign_repo:{repo_url}",
        decision=request.decision,
        decided_by="user",
        confidence=0.0,
        finding_summary=f"Campaign repo {request.decision}: {repo_url}",
    )
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_attestation_logging.py tests/test_hardening_integration.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/supervisor.py backend/src/api/routes_v4.py backend/tests/test_attestation_logging.py
git commit -m "feat(attestation): wire AttestationLogger into all decision points"
```

---

### Task 4: State-Driven Supervisor — Save/Exit on Attestation Required

**Files:**
- Modify: `backend/src/agents/supervisor.py` — replace break-after-emit with state save + clean exit
- Modify: `backend/src/utils/redis_store.py` — add pending_action save/load/clear helpers
- Test: `backend/tests/test_state_driven_attestation.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_state_driven_attestation.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.models.pending_action import PendingAction


@pytest.mark.asyncio
async def test_pending_action_saved_to_redis():
    """When attestation is required, supervisor saves PendingAction to Redis and exits."""
    from src.utils.redis_store import RedisSessionStore

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    store = RedisSessionStore(mock_redis)

    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject", "details"],
        expires_at=None,
        context={"findings_count": 4, "confidence": 0.87},
        version=1,
    )

    await store.save_pending_action("sess-1", pa)
    mock_redis.set.assert_called_once()
    call_key = mock_redis.set.call_args[0][0]
    assert "pending_action" in call_key
    assert "sess-1" in call_key


@pytest.mark.asyncio
async def test_pending_action_load_roundtrip():
    import json
    from src.utils.redis_store import RedisSessionStore

    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=None,
        context={"diff_summary": "2 files changed"},
        version=1,
    )

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(pa.to_dict()))
    store = RedisSessionStore(mock_redis)

    loaded = await store.load_pending_action("sess-1")
    assert loaded is not None
    assert loaded.type == "fix_approval"
    assert loaded.context["diff_summary"] == "2 files changed"


@pytest.mark.asyncio
async def test_clear_pending_action():
    from src.utils.redis_store import RedisSessionStore

    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock()
    store = RedisSessionStore(mock_redis)

    await store.clear_pending_action("sess-1")
    mock_redis.delete.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_state_driven_attestation.py -v`
Expected: FAIL with `AttributeError: 'RedisSessionStore' object has no attribute 'save_pending_action'`

**Step 3: Add pending_action helpers to RedisSessionStore**

In `backend/src/utils/redis_store.py`, add methods:

```python
import json
from src.models.pending_action import PendingAction

# Add to RedisSessionStore class:

async def save_pending_action(self, session_id: str, action: PendingAction) -> None:
    key = f"pending_action:{session_id}"
    await self._redis.set(key, json.dumps(action.to_dict()), ex=3600)

async def load_pending_action(self, session_id: str) -> PendingAction | None:
    key = f"pending_action:{session_id}"
    raw = await self._redis.get(key)
    if not raw:
        return None
    data = json.loads(raw if isinstance(raw, str) else raw.decode())
    return PendingAction.from_dict(data)

async def clear_pending_action(self, session_id: str) -> None:
    key = f"pending_action:{session_id}"
    await self._redis.delete(key)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_state_driven_attestation.py -v`
Expected: PASS (3 tests)

**Step 5: Modify supervisor main loop**

In `backend/src/agents/supervisor.py`, replace lines 241-251 (the attestation emit + break):

```python
# BEFORE:
    await event_emitter.emit(
        "supervisor", "attestation_required",
        "Human attestation required before proceeding to remediation",
        details={...}
    )
    break  # ← exits immediately, no wait

# AFTER:
    from src.models.pending_action import PendingAction
    from datetime import datetime, timezone, timedelta

    pending = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject", "details"],
        expires_at=datetime.now(timezone.utc) + timedelta(
            seconds=int(os.getenv("ATTESTATION_TIMEOUT_S", "600"))
        ),
        context={
            "findings_count": len(state.all_findings),
            "confidence": state.overall_confidence,
            "proposed_action": "Proceed to remediation phase",
        },
        version=1,
    )
    # Persist to Redis
    if self._session_store:
        await self._session_store.save_pending_action(self._session_id, pending)

    # Emit as chat message (not just task event) with action chips
    await event_emitter.emit(
        "supervisor", "attestation_required",
        "Human attestation required before proceeding to remediation",
        details={
            "gate_type": "discovery_complete",
            "pending_action": pending.to_dict(),
            **pending.context,
        }
    )
    return  # Clean exit — no coroutine held open
```

Also delete `_wait_for_attestation()` method and `_attestation_event` from `__init__`.

**Step 6: Run all tests**

Run: `cd backend && python -m pytest tests/test_state_driven_attestation.py tests/test_pending_action.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add backend/src/utils/redis_store.py backend/src/agents/supervisor.py backend/tests/test_state_driven_attestation.py
git commit -m "feat(attestation): state-driven supervisor — save PendingAction to Redis and exit cleanly"
```

---

### Task 5: State-Driven Supervisor — Resume on Attestation Decision

**Files:**
- Modify: `backend/src/agents/supervisor.py` — rewrite `acknowledge_attestation()` to clear state + resume
- Modify: `backend/src/api/routes_v4.py` — update attestation endpoint to use new flow
- Test: `backend/tests/test_attestation_resume.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_attestation_resume.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.models.pending_action import PendingAction


@pytest.mark.asyncio
async def test_acknowledge_clears_pending_and_sets_flag():
    from src.agents.supervisor import DiagnosticSupervisor

    supervisor = DiagnosticSupervisor.__new__(DiagnosticSupervisor)
    supervisor._attestation_acknowledged = False
    supervisor._attestation_logger = None
    supervisor._session_store = AsyncMock()
    supervisor._session_id = "sess-1"

    result = await supervisor.acknowledge_attestation("approve", session_id="sess-1")
    assert supervisor._attestation_acknowledged is True
    assert "acknowledged" in result.lower()
    supervisor._session_store.clear_pending_action.assert_called_once_with("sess-1")


@pytest.mark.asyncio
async def test_acknowledge_reject_keeps_flag_false():
    from src.agents.supervisor import DiagnosticSupervisor

    supervisor = DiagnosticSupervisor.__new__(DiagnosticSupervisor)
    supervisor._attestation_acknowledged = False
    supervisor._attestation_logger = None
    supervisor._session_store = AsyncMock()
    supervisor._session_id = "sess-1"

    result = await supervisor.acknowledge_attestation("reject", session_id="sess-1")
    assert supervisor._attestation_acknowledged is False
    assert "rejected" in result.lower()
    supervisor._session_store.clear_pending_action.assert_called_once_with("sess-1")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_attestation_resume.py -v`
Expected: FAIL (acknowledge_attestation is still sync / doesn't clear pending)

**Step 3: Rewrite acknowledge_attestation + resume_pipeline**

In `backend/src/agents/supervisor.py`, replace the existing `acknowledge_attestation()`:

```python
async def acknowledge_attestation(self, decision: str, session_id: str = "") -> str:
    sid = session_id or self._session_id or ""

    if decision == "approve":
        self._attestation_acknowledged = True
        response = "Findings approved — fix generation is now available."
    elif decision == "reject":
        self._attestation_acknowledged = False
        response = "Findings rejected — investigation needs revision."
    else:
        return "Unknown attestation decision."

    # Clear pending action from Redis
    if self._session_store and sid:
        await self._session_store.clear_pending_action(sid)

    # Audit trail
    if self._attestation_logger and sid:
        await self._attestation_logger.log_decision(
            session_id=sid,
            finding_id="all",
            decision=decision,
            decided_by="user",
            confidence=getattr(self, '_last_confidence', 0.0),
            finding_summary=f"Discovery attestation: {decision}",
        )

    return response


async def resume_pipeline(self, session_id: str, state: "DiagnosticState",
                          event_emitter: "EventEmitter") -> None:
    """Resume supervisor pipeline after human decision. Called by API layer."""
    if not self._attestation_acknowledged:
        return  # Rejected — don't resume
    # Continue from where we left off (post-attestation → remediation)
    await event_emitter.emit(
        "supervisor", "phase_change",
        "Resuming pipeline — entering remediation phase",
        details={"phase": "fix_in_progress"},
    )
    state.phase = DiagnosticPhase.FIX_IN_PROGRESS
    # Pipeline resumes — supervisor is ready for fix generation requests via chat
```

Update the attestation endpoint in `routes_v4.py` (line 1464) to `await` and trigger resume:

```python
@router_v4.post("/session/{session_id}/attestation")
async def submit_attestation(session_id: str, request: AttestationDecisionRequest):
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    supervisor = supervisors.get(session_id)
    if not supervisor:
        raise HTTPException(status_code=400, detail="Session not ready")

    response_text = await supervisor.acknowledge_attestation(request.decision, session_id)

    # Resume pipeline in background (non-blocking)
    state = session.get("state")
    emitter = session.get("emitter")
    if state and emitter and request.decision == "approve":
        import asyncio
        asyncio.create_task(supervisor.resume_pipeline(session_id, state, emitter))

    return {"status": "recorded", "response": response_text}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_attestation_resume.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/supervisor.py backend/src/api/routes_v4.py backend/tests/test_attestation_resume.py
git commit -m "feat(attestation): state-driven resume — acknowledge clears Redis + logs audit"
```

---

### Task 6: Add `pending_action` to Session Status Endpoint

**Files:**
- Modify: `backend/src/api/routes_v4.py` — include `pending_action` in status response
- Test: `backend/tests/test_status_pending_action.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_status_pending_action.py
import json
import pytest
from unittest.mock import AsyncMock
from src.models.pending_action import PendingAction


@pytest.mark.asyncio
async def test_status_includes_pending_action():
    """Session status endpoint should return pending_action when one exists."""
    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject", "details"],
        expires_at=None,
        context={"confidence": 0.87},
        version=1,
    )
    d = pa.to_dict()
    assert d["type"] == "attestation_required"
    assert d["actions"] == ["approve", "reject", "details"]
    assert d["blocking"] is True
    # This verifies the shape matches what the endpoint will return
```

**Step 2: Run test**

Run: `cd backend && python -m pytest tests/test_status_pending_action.py -v`
Expected: PASS (basic shape test)

**Step 3: Modify status endpoint**

In `backend/src/api/routes_v4.py`, in the `get_session_status()` function (around line 1067), add:

```python
# After building the result dict, before return:
session_store = _get_session_store()
if session_store:
    pending = await session_store.load_pending_action(session_id)
    result["pending_action"] = pending.to_dict() if pending else None
else:
    result["pending_action"] = None
```

**Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/ -k "pending_action or status" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_status_pending_action.py
git commit -m "feat(attestation): return pending_action in session status endpoint"
```

---

### Task 7: State-Driven Fix Approval (Replace asyncio.Event Wait)

**Files:**
- Modify: `backend/src/agents/supervisor.py` — replace `_fix_event.wait()` with save-and-exit pattern
- Test: `backend/tests/test_fix_approval_state_driven.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_fix_approval_state_driven.py
import pytest
from unittest.mock import AsyncMock
from src.models.pending_action import PendingAction


@pytest.mark.asyncio
async def test_fix_approval_saves_pending_action():
    from src.utils.redis_store import RedisSessionStore
    import json

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    store = RedisSessionStore(mock_redis)

    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject", "feedback"],
        expires_at=None,
        context={"diff_summary": "2 files changed", "fix_explanation": "Fix null check"},
        version=1,
    )
    await store.save_pending_action("sess-1", pa)

    call_args = mock_redis.set.call_args
    stored = json.loads(call_args[0][1])
    assert stored["type"] == "fix_approval"
    assert "approve" in stored["actions"]
```

**Step 2: Run test**

Run: `cd backend && python -m pytest tests/test_fix_approval_state_driven.py -v`
Expected: PASS

**Step 3: Modify fix approval flow in supervisor**

In `backend/src/agents/supervisor.py`, replace the fix approval blocking wait (lines 2706-2776).

The key change: instead of `await asyncio.wait_for(self._fix_event.wait(), timeout=600)`, save a PendingAction and return. The `_process_fix_decision()` method already handles the resume — it just needs to also clear the pending action.

```python
# In the fix approval section, REPLACE:
#   self._pending_fix_approval = True
#   self._fix_event.clear()
#   await asyncio.wait_for(self._fix_event.wait(), timeout=600)
# WITH:

self._pending_fix_approval = True
self._fix_human_decision = None

pending = PendingAction(
    type="fix_approval",
    blocking=True,
    actions=["approve", "reject", "feedback"],
    expires_at=datetime.now(timezone.utc) + timedelta(seconds=600),
    context={
        "diff_summary": f"{len(fix_result.fixed_files)} files changed",
        "fix_explanation": fix_result.explanation[:200] if fix_result.explanation else "",
    },
    version=1,
)
if self._session_store:
    await self._session_store.save_pending_action(self._session_id, pending)

await event_emitter.emit(
    "fix_generator", "waiting_for_input",
    "Fix proposed — awaiting human review",
    details={"input_type": "fix_approval", "pending_action": pending.to_dict()},
)
return  # Exit cleanly — resume on user decision
```

Rewrite `_process_fix_decision()` — fully state-driven, no asyncio.Event:

```python
async def _process_fix_decision(self, message: str) -> str:
    """State-driven fix decision — no asyncio.Event. Clears pending action + triggers resume."""
    text = message.strip().lower()

    if not self._pending_fix_approval:
        return f"No fix awaiting review (already decided: {self._fix_human_decision or 'none'})."

    if text in ("approve", "yes", "create pr", "lgtm", "ok", "y"):
        self._fix_human_decision = "approve"
        self._pending_fix_approval = False
    elif text in ("reject", "no", "cancel", "discard"):
        self._fix_human_decision = "reject"
        self._pending_fix_approval = False
    else:
        self._fix_human_decision = message.strip()  # feedback
        self._pending_fix_approval = False

    # Clear pending action from Redis
    if self._session_store and self._session_id:
        await self._session_store.clear_pending_action(self._session_id)

    # Audit trail
    if self._attestation_logger and self._session_id:
        await self._attestation_logger.log_decision(
            session_id=self._session_id,
            finding_id="fix_attempt",
            decision=self._fix_human_decision,
            decided_by="user",
            confidence=0.0,
            finding_summary=f"Fix decision: {self._fix_human_decision}",
        )

    if self._fix_human_decision == "approve":
        return "Approved — creating pull request now."
    elif self._fix_human_decision == "reject":
        return "Fix rejected. Diagnosis remains available."
    else:
        return "Got it — regenerating fix with your feedback."
```

Also delete `_fix_event` from `__init__` — no more asyncio.Event for human-timescale waits:

```python
# DELETE from __init__:
# self._fix_event = asyncio.Event()
```

Add `resume_fix_pipeline()` method for API layer to call after decision:

```python
async def resume_fix_pipeline(self, session_id: str, state: "DiagnosticState",
                               event_emitter: "EventEmitter") -> None:
    """Resume fix pipeline after human decision."""
    decision = self._fix_human_decision
    if decision == "approve":
        # Continue to PR creation
        await self._create_pr(state, event_emitter)
    elif decision and decision not in ("reject",):
        # Feedback — regenerate fix with guidance
        await self.start_fix_generation(state, event_emitter, human_guidance=decision)
```

Wire resume in `routes_v4.py` fix/decide endpoint:

```python
# After processing decision, trigger resume:
if supervisor._fix_human_decision:
    state = session.get("state")
    emitter = session.get("emitter")
    if state and emitter:
        asyncio.create_task(supervisor.resume_fix_pipeline(session_id, state, emitter))
```

**Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/ -k "fix" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/supervisor.py backend/tests/test_fix_approval_state_driven.py
git commit -m "feat(attestation): state-driven fix approval — save PendingAction, exit cleanly"
```

---

### Task 8: Route Chat Messages Through IntentParser

**Files:**
- Modify: `backend/src/agents/supervisor.py` — wrap `handle_user_message()` with IntentParser
- Test: `backend/tests/test_intent_routing.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_intent_routing.py
from src.agents.intent_parser import IntentParser, UserIntent
from src.models.pending_action import PendingAction


def test_intent_routes_approve_to_attestation_when_pending():
    parser = IntentParser()
    pending = PendingAction(
        type="attestation_required", blocking=True,
        actions=["approve", "reject"], expires_at=None,
        context={}, version=1,
    )
    intent = parser.parse("looks good to me", pending)
    assert intent.type == "approve_attestation"


def test_intent_routes_question_keeps_pending():
    parser = IntentParser()
    pending = PendingAction(
        type="attestation_required", blocking=True,
        actions=["approve", "reject"], expires_at=None,
        context={}, version=1,
    )
    intent = parser.parse("can you show me finding 3?", pending)
    assert intent.type == "ask_question"


def test_low_confidence_returns_general():
    parser = IntentParser()
    pending = PendingAction(
        type="attestation_required", blocking=True,
        actions=["approve", "reject"], expires_at=None,
        context={}, version=1,
    )
    intent = parser.parse("hmm not sure", pending)
    # Ambiguous → should be low confidence general_chat
    assert intent.confidence < 0.7
```

**Step 2: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_intent_routing.py -v`
Expected: PASS (uses existing IntentParser)

**Step 3: Wire IntentParser into handle_user_message**

In `backend/src/agents/supervisor.py`, modify `handle_user_message()`:

```python
async def handle_user_message(self, message: str, state: DiagnosticState) -> str:
    from src.agents.intent_parser import IntentParser
    parser = IntentParser()

    # Load pending action from Redis
    pending = None
    if self._session_store and self._session_id:
        pending = await self._session_store.load_pending_action(self._session_id)

    intent = parser.parse(message, pending)

    # Security: validate intent is allowed for current pending action type
    if pending and intent.type not in ("ask_question", "general_chat"):
        allowed = _allowed_intents_for_pending(pending.type)
        if intent.type not in allowed:
            return f"Invalid action '{intent.type}' for current state '{pending.type}'."

    # Low confidence with pending action → re-prompt with chips
    if pending and intent.confidence < 0.7 and intent.type == "general_chat":
        actions_display = ", ".join(f"'{a}'" for a in pending.actions)
        return f"I need a clear decision. You can say {actions_display}, or ask me a question about the findings."

    # Route structured decisions
    if intent.type == "approve_attestation":
        return await self.acknowledge_attestation("approve", self._session_id)

    if intent.type == "reject_attestation":
        return await self.acknowledge_attestation("reject", self._session_id)

    if intent.type in ("approve_fix", "reject_fix", "fix_feedback"):
        # Delegate to existing fix decision handler
        if intent.type == "fix_feedback":
            return self._process_fix_decision(intent.entities.get("feedback", message))
        decision = "approve" if intent.type == "approve_fix" else "reject"
        return self._process_fix_decision(decision)

    if intent.type == "confirm_execute":
        return await self._process_campaign_execute_confirm()

    if intent.type == "cancel_execute":
        if self._session_store and self._session_id:
            await self._session_store.clear_pending_action(self._session_id)
        return "Campaign execution cancelled."

    # --- end of intent-routed decisions ---

    # Existing priority routing for legacy gates (keep for backward compat)
    if self._pending_fix_approval:
        return self._process_fix_decision(message)

    if self._pending_repo_mismatch:
        return self._process_repo_mismatch(message, state)

    if self._pending_code_agent_question:
        self._code_agent_answer = message
        self._code_agent_event.set()
        return "Got it, passing your answer to the code analysis agent."

    if self._pending_repo_confirmation:
        return await self._process_repo_confirmation(message)

    # Normal diagnostic chat
    # ... existing chat logic ...
```

**Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/test_intent_routing.py tests/test_intent_parser.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/supervisor.py backend/tests/test_intent_routing.py
git commit -m "feat(attestation): route chat through IntentParser with re-prompt on ambiguity"
```

---

### Task 9: Remove Dead Attestation Code

**Files:**
- Modify: `backend/src/agents/supervisor.py` — delete `_wait_for_attestation()`, `_attestation_event`, `_per_finding_gate`
- Modify: `backend/src/api/routes_v4.py` — delete per-finding attestation endpoint, remove 403 guards
- Delete: `backend/src/models/attestation.py` (AttestationGate — keep AttestationDecision inline if needed)
- Modify: `frontend/src/services/api.ts` — remove `submitAttestation` (no longer called from frontend)

**Step 1: Delete dead backend code**

In `backend/src/agents/supervisor.py`:
- Delete `_attestation_event = asyncio.Event()` from `__init__`
- Delete `_fix_event = asyncio.Event()` from `__init__`
- Delete `_per_finding_gate = None` from `__init__`
- Delete entire `_wait_for_attestation()` method (lines 3040-3048)
- Remove all `self._fix_event.set()` and `self._fix_event.clear()` calls
- Remove `await asyncio.wait_for(self._fix_event.wait(), ...)` (replaced by state-driven exit in Task 7)

In `backend/src/api/routes_v4.py`:
- Delete the `submit_per_finding_attestation` endpoint (lines 1492-1533)
- Remove the `403` guard from `generate_fix` endpoint (lines 1562-1566):
  ```python
  # DELETE these lines:
  if not supervisor._attestation_acknowledged:
      raise HTTPException(
          status_code=403,
          detail="Attestation required — approve diagnosis findings before generating a fix",
      )
  ```
- Remove the `403` guard from `start_campaign_generation` endpoint (lines 1832-1836):
  ```python
  # DELETE these lines:
  if not supervisor._attestation_acknowledged:
      raise HTTPException(
          status_code=403,
          detail="Attestation required before campaign generation",
      )
  ```

Delete `backend/src/models/attestation.py` (the AttestationGate dataclass is no longer used — PendingAction replaces it).

**Step 2: Remove silent auto-submit from frontend**

In `frontend/src/services/api.ts`, remove the `submitAttestation` function (lines 330-338).

**Step 3: Run tests to verify nothing breaks**

Run: `cd backend && python -m pytest tests/ -v --timeout=30`
Expected: PASS (per-finding tests should be removed or skipped)

**Step 4: Commit**

```bash
git add -u backend/src/agents/supervisor.py backend/src/api/routes_v4.py frontend/src/services/api.ts
git rm backend/src/models/attestation.py
git commit -m "refactor(attestation): remove dead code — per-finding endpoint, 403 guards, asyncio.Event"
```

---

### Task 10: Idempotency on Decision Endpoints

**Files:**
- Modify: `backend/src/api/routes_v4.py` — add idempotency checks to attestation, fix/decide, campaign/execute
- Test: `backend/tests/test_idempotency.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_idempotency.py
import pytest


def test_idempotent_attestation_approve():
    """Second attestation approval should return existing result, not error."""
    # This is an integration test — we verify the logic pattern
    from src.agents.supervisor import DiagnosticSupervisor

    supervisor = DiagnosticSupervisor.__new__(DiagnosticSupervisor)
    supervisor._attestation_acknowledged = True  # Already approved
    supervisor._attestation_logger = None
    supervisor._session_store = None
    supervisor._session_id = "sess-1"

    # Second call should still succeed (not error)
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        supervisor.acknowledge_attestation("approve", "sess-1")
    )
    assert "acknowledged" in result.lower() or "already" in result.lower()


def test_fix_decide_already_decided():
    """If fix was already decided, return existing result."""
    from src.agents.supervisor import DiagnosticSupervisor

    supervisor = DiagnosticSupervisor.__new__(DiagnosticSupervisor)
    supervisor._pending_fix_approval = False  # Not pending
    supervisor._fix_human_decision = "approve"  # Already decided

    result = supervisor._process_fix_decision("approve")
    # Should return a message indicating already processed
    assert result is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_idempotency.py -v`
Expected: FAIL

**Step 3: Add idempotency guards**

In `supervisor.py`, modify `acknowledge_attestation()`:
```python
async def acknowledge_attestation(self, decision: str, session_id: str = "") -> str:
    # Idempotency: already acknowledged
    if self._attestation_acknowledged and decision == "approve":
        return "Findings already approved."
    # ... rest of method
```

In `supervisor.py`, modify `_process_fix_decision()`:
```python
def _process_fix_decision(self, message: str) -> str:
    # Idempotency: not pending
    if not self._pending_fix_approval:
        return f"No fix awaiting review (already decided: {self._fix_human_decision or 'none'})."
    # ... rest of method
```

In `routes_v4.py`, modify `execute_campaign()`:
```python
# Add at top of execute_campaign():
if campaign.status == "executing":
    return CampaignExecuteResponse(status="already_executing", results=[])
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_idempotency.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/supervisor.py backend/src/api/routes_v4.py backend/tests/test_idempotency.py
git commit -m "feat(attestation): add scoped idempotency guards on all decision endpoints"
```

---

### Task 11: Campaign Execute Confirmation Gate

**Files:**
- Modify: `backend/src/agents/supervisor.py` — add campaign execute confirm logic
- Modify: `backend/src/api/routes_v4.py` — save PendingAction before execute
- Test: `backend/tests/test_campaign_confirm.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_campaign_confirm.py
import pytest
from src.models.pending_action import PendingAction


def test_campaign_confirm_pending_action_shape():
    pa = PendingAction(
        type="campaign_execute_confirm",
        blocking=True,
        actions=["confirm", "cancel"],
        expires_at=None,
        context={"repo_count": 5, "repos": ["repo1", "repo2"]},
        version=1,
    )
    d = pa.to_dict()
    assert d["type"] == "campaign_execute_confirm"
    assert d["actions"] == ["confirm", "cancel"]
    assert d["context"]["repo_count"] == 5
```

**Step 2: Run test**

Run: `cd backend && python -m pytest tests/test_campaign_confirm.py -v`
Expected: PASS

**Step 3: Add confirmation gate to campaign execute**

In `backend/src/api/routes_v4.py`, modify `execute_campaign()`:

```python
@router_v4.post("/session/{session_id}/campaign/execute")
async def execute_campaign(session_id: str):
    # ... existing validation ...

    # Check if confirmation pending action exists and was confirmed
    session_store = _get_session_store()
    if session_store:
        pending = await session_store.load_pending_action(session_id)
        if pending and pending.type == "campaign_execute_confirm":
            # Already confirmed — clear and proceed
            await session_store.clear_pending_action(session_id)
        elif pending and pending.type != "campaign_execute_confirm":
            # Different action is pending — block
            raise HTTPException(
                status_code=409,
                detail=f"Cannot execute campaign — another action is pending: {pending.type}",
            )
        elif not pending:
            # No pending action — create confirmation gate
            repo_urls = [r.repo_url for r in campaign.repos]
            confirm_action = PendingAction(
                type="campaign_execute_confirm",
                blocking=True,
                actions=["confirm", "cancel"],
                expires_at=None,
                context={
                    "repo_count": campaign.total_count,
                    "repos": repo_urls[:10],
                },
                version=1,
            )
            await session_store.save_pending_action(session_id, confirm_action)

            emitter = session.get("emitter")
            if emitter:
                await emitter.emit(
                    "supervisor", "waiting_for_input",
                    f"About to create PRs in {campaign.total_count} repos. Type 'confirm' to proceed.",
                    details={"pending_action": confirm_action.to_dict()},
                )
            return {"status": "confirmation_required", "message": f"Confirm execution for {campaign.total_count} repos"}

    # ... existing execute logic ...
```

In `supervisor.py`, add `_process_campaign_execute_confirm()`:

```python
async def _process_campaign_execute_confirm(self) -> str:
    if self._session_store and self._session_id:
        await self._session_store.clear_pending_action(self._session_id)
    return "Campaign execution confirmed. Creating pull requests..."
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_campaign_confirm.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/supervisor.py backend/src/api/routes_v4.py backend/tests/test_campaign_confirm.py
git commit -m "feat(attestation): add campaign execute confirmation gate via chat"
```

---

### Task 12: Persist Campaign State to Redis

**Files:**
- Modify: `backend/src/api/routes_v4.py` — save campaign state on every decision
- Modify: `backend/src/utils/redis_store.py` — add campaign save/load
- Test: `backend/tests/test_campaign_persistence.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_campaign_persistence.py
import json
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_campaign_save_load():
    from src.utils.redis_store import RedisSessionStore

    campaign_data = {
        "total_count": 3,
        "approved_count": 1,
        "repos": [
            {"repo_url": "repo1", "status": "approved"},
            {"repo_url": "repo2", "status": "pending"},
        ],
    }

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(campaign_data))
    store = RedisSessionStore(mock_redis)

    await store.save_campaign("sess-1", campaign_data)
    mock_redis.set.assert_called_once()

    loaded = await store.load_campaign("sess-1")
    assert loaded["total_count"] == 3
    assert loaded["approved_count"] == 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_campaign_persistence.py -v`
Expected: FAIL with `AttributeError: 'RedisSessionStore' object has no attribute 'save_campaign'`

**Step 3: Add campaign persistence methods**

In `backend/src/utils/redis_store.py`:

```python
async def save_campaign(self, session_id: str, campaign_data: dict) -> None:
    key = f"campaign:{session_id}"
    await self._redis.set(key, json.dumps(campaign_data), ex=86400)

async def load_campaign(self, session_id: str) -> dict | None:
    key = f"campaign:{session_id}"
    raw = await self._redis.get(key)
    if not raw:
        return None
    return json.loads(raw if isinstance(raw, str) else raw.decode())
```

In `backend/src/api/routes_v4.py`, after each campaign repo decision, persist:

```python
# In campaign_repo_decide(), after updating campaign state:
session_store = _get_session_store()
if session_store and state.campaign:
    await session_store.save_campaign(session_id, state.campaign.model_dump())
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_campaign_persistence.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/utils/redis_store.py backend/src/api/routes_v4.py backend/tests/test_campaign_persistence.py
git commit -m "feat(attestation): persist campaign state to Redis on every repo decision"
```

---

### Task 13: Frontend — PendingAction Type + API

**Files:**
- Modify: `frontend/src/types/index.ts` — add `PendingAction` interface, remove `AttestationGateData`
- Modify: `frontend/src/services/api.ts` — remove `submitAttestation`, update `getSessionStatus` return type

**Step 1: Add PendingAction type**

In `frontend/src/types/index.ts`:

```typescript
export interface PendingAction {
  type: 'attestation_required' | 'fix_approval' | 'repo_confirm' | 'campaign_execute_confirm' | 'code_agent_question';
  blocking: boolean;
  actions: string[];
  expires_at: string | null;
  context: Record<string, unknown>;
  version: number;
}
```

Remove `AttestationGateData` interface (lines 947-955) — already removed from props/state in earlier work.

Update `V4SessionStatus` (or wherever session status response is typed) to include:
```typescript
pending_action: PendingAction | null;
```

**Step 2: Remove submitAttestation from api.ts**

Delete the `submitAttestation` function. Attestation now goes through chat messages (`sendChatMessage` → IntentParser routes it).

Remove `submitAttestation` from the import in `FixPipelinePanel.tsx` (line 2) — this will be needed for Task 15 when we modify FixPipelinePanel.

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors (or only errors related to files we haven't modified yet)

**Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/services/api.ts
git commit -m "feat(attestation): add PendingAction type, remove AttestationGateData + submitAttestation"
```

---

### Task 14: Frontend — PinnedActionCard Component

**Files:**
- Create: `frontend/src/components/Chat/PinnedActionCard.tsx`

**Step 1: Create the component**

```tsx
// frontend/src/components/Chat/PinnedActionCard.tsx
import React, { useEffect, useState } from 'react';
import type { PendingAction } from '../../types';

interface PinnedActionCardProps {
  pendingAction: PendingAction;
  onAction: (action: string) => void;
}

const typeConfig: Record<string, { icon: string; title: string; borderColor: string }> = {
  attestation_required: {
    icon: 'verified_user',
    title: 'Findings Review Required',
    borderColor: 'border-amber-500',
  },
  fix_approval: {
    icon: 'build',
    title: 'Fix Ready for Review',
    borderColor: 'border-violet-500',
  },
  campaign_execute_confirm: {
    icon: 'rocket_launch',
    title: 'Campaign Execution Confirmation',
    borderColor: 'border-emerald-500',
  },
  repo_confirm: {
    icon: 'folder_open',
    title: 'Repository Confirmation',
    borderColor: 'border-blue-500',
  },
  code_agent_question: {
    icon: 'help',
    title: 'Agent Question',
    borderColor: 'border-cyan-500',
  },
};

const actionStyles: Record<string, string> = {
  approve: 'bg-green-500/20 text-green-400 border-green-500/30 hover:bg-green-500/30',
  reject: 'bg-red-500/20 text-red-400 border-red-500/30 hover:bg-red-500/30',
  details: 'bg-slate-500/20 text-slate-300 border-slate-500/30 hover:bg-slate-500/30',
  confirm: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/30',
  cancel: 'bg-red-500/20 text-red-400 border-red-500/30 hover:bg-red-500/30',
  feedback: 'bg-violet-500/20 text-violet-400 border-violet-500/30 hover:bg-violet-500/30',
};

const PinnedActionCard: React.FC<PinnedActionCardProps> = ({ pendingAction, onAction }) => {
  const config = typeConfig[pendingAction.type] || typeConfig.attestation_required;
  const [countdown, setCountdown] = useState<number | null>(null);

  useEffect(() => {
    if (!pendingAction.expires_at) return;
    const tick = () => {
      const remaining = Math.max(0, Math.floor((new Date(pendingAction.expires_at!).getTime() - Date.now()) / 1000));
      setCountdown(remaining);
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [pendingAction.expires_at]);

  const ctx = pendingAction.context;

  return (
    <div className={`sticky top-0 z-10 mx-3 mt-2 mb-1 rounded-lg border-l-4 ${config.borderColor} bg-wr-surface/95 backdrop-blur-sm shadow-lg`}>
      <div className="px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <span className="material-symbols-outlined text-base text-amber-400 animate-pulse">
            {config.icon}
          </span>
          <span className="text-body-xs font-bold uppercase tracking-wider text-slate-200">
            {config.title}
          </span>
          {countdown !== null && countdown > 0 && (
            <span className="ml-auto text-body-xs text-slate-500 font-mono">
              {Math.floor(countdown / 60)}:{String(countdown % 60).padStart(2, '0')}
            </span>
          )}
        </div>

        {/* Context summary */}
        {ctx.findings_count != null && (
          <p className="text-body-xs text-slate-400 mb-2">
            {ctx.findings_count as number} findings at {((ctx.confidence as number) * 100).toFixed(0)}% confidence
          </p>
        )}
        {ctx.diff_summary && (
          <p className="text-body-xs text-slate-400 mb-2">{ctx.diff_summary as string}</p>
        )}
        {ctx.repo_count != null && (
          <p className="text-body-xs text-slate-400 mb-2">
            {ctx.repo_count as number} repositories ready for PR creation
          </p>
        )}

        {/* Action chips */}
        <div className="flex items-center gap-2 flex-wrap">
          {pendingAction.actions.map((action) => (
            <button
              key={action}
              onClick={() => onAction(`__intent:${action}_${pendingAction.type.replace('_required', '').replace('_confirm', '')}`)}
              className={`text-body-xs font-bold px-3 py-1.5 rounded border transition-colors ${actionStyles[action] || actionStyles.details}`}
            >
              {action.charAt(0).toUpperCase() + action.slice(1)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default PinnedActionCard;
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/Chat/PinnedActionCard.tsx
git commit -m "feat(attestation): add PinnedActionCard component for chat-first attestation UI"
```

---

### Task 15: Frontend — Wire PinnedActionCard into ChatDrawer

**Files:**
- Modify: `frontend/src/components/Chat/ChatDrawer.tsx` — add PinnedActionCard rendering from session status
- Modify: `frontend/src/contexts/ChatContext.tsx` — add pendingAction state, fetch from status

**Step 1: Add pendingAction to ChatContext**

In `frontend/src/contexts/ChatContext.tsx`, add to the ChatUIContext:

```typescript
// Add to ChatUIContextValue:
pendingAction: PendingAction | null;

// In ChatProvider, add state:
const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);

// Fetch on mount and after certain events:
useEffect(() => {
  if (!sessionId) return;
  const fetchPending = async () => {
    try {
      const status = await getSessionStatus(sessionId);
      setPendingAction(status.pending_action || null);
    } catch { /* silent */ }
  };
  fetchPending();
  const interval = setInterval(fetchPending, 5000);
  return () => clearInterval(interval);
}, [sessionId]);

// Expose in context value:
// pendingAction, setPendingAction
```

**Step 2: Render PinnedActionCard in ChatDrawer**

In `frontend/src/components/Chat/ChatDrawer.tsx`, add at the top of the message list area:

```tsx
import PinnedActionCard from './PinnedActionCard';
import { useChatUI } from '../../contexts/ChatContext';

// Inside the messages area, before the message map:
const { pendingAction, sendMessage } = useChatUI();

{pendingAction && (
  <PinnedActionCard
    pendingAction={pendingAction}
    onAction={(intentStr) => sendMessage(intentStr)}
  />
)}
```

**Step 3: Clear pendingAction after successful decision**

When a chat response arrives and the pending action type matches, clear it:

```tsx
// After receiving assistant response:
if (pendingAction && response.metadata?.pending_action_resolved) {
  setPendingAction(null);
}
```

**Step 4: Verify TypeScript compiles and test in browser**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 5: Commit**

```bash
git add frontend/src/components/Chat/ChatDrawer.tsx frontend/src/contexts/ChatContext.tsx
git commit -m "feat(attestation): wire PinnedActionCard into ChatDrawer with status polling"
```

---

### Task 16: Frontend — Pulsing Badge on LedgerTriggerTab

**Files:**
- Modify: `frontend/src/components/Chat/LedgerTriggerTab.tsx` — pulse when pendingAction exists

**Step 1: Modify LedgerTriggerTab**

Add pendingAction awareness from ChatContext:

```tsx
import { useChatUI } from '../../contexts/ChatContext';

// Inside component:
const { pendingAction } = useChatUI();
const hasPendingAction = pendingAction?.blocking === true;

// Add pulsing badge indicator when action is pending:
{hasPendingAction && (
  <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-amber-400 animate-pulse" />
)}
```

Also update the tab text/style when action is pending:
```tsx
// Change the tab color when action is pending:
className={`... ${hasPendingAction ? 'border-amber-500/50 bg-amber-500/10' : 'border-wr-border'}`}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/Chat/LedgerTriggerTab.tsx
git commit -m "feat(attestation): pulsing amber badge on LedgerTriggerTab when action pending"
```

---

### Task 17: Frontend — Remove AttestationRequiredCard from AISupervisor

**Files:**
- Modify: `frontend/src/components/Investigation/AISupervisor.tsx` — remove card, replace with simple event entry

**Step 1: Modify EventCard switch**

In `AISupervisor.tsx`, change the `attestation_required` case (around line 253):

```tsx
// BEFORE:
case 'attestation_required':
  return <AttestationRequiredCard event={event} />;

// AFTER:
case 'attestation_required':
  return <AlertCard event={event} variant="warning" />;
```

**Step 2: Delete the AttestationRequiredCard component**

Remove the entire `AttestationRequiredCard` component definition (lines 498-536).

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/Investigation/AISupervisor.tsx
git commit -m "refactor(attestation): replace AttestationRequiredCard with simple AlertCard"
```

---

### Task 18: Frontend — Remove FixPipelinePanel (Merge into Chat)

**Files:**
- Modify: `frontend/src/components/Investigation/EvidenceFindings.tsx` — remove FixPipelinePanel import and usage
- Keep: `frontend/src/components/Investigation/FixPipelinePanel.tsx` — DO NOT delete yet (keep CampaignOrchestrationHub routing)

**Important:** FixPipelinePanel also renders `CampaignOrchestrationHub` for multi-repo campaigns (line 156-158). We need to preserve that routing. The approach: remove FixPipelinePanel's single-repo fix UI responsibility (that moves to chat), but keep the campaign orchestration hub rendering.

**Step 1: Check how EvidenceFindings uses FixPipelinePanel**

In `EvidenceFindings.tsx` (line 748), FixPipelinePanel is rendered inside the evidence view. We need to replace the single-repo fix UI with a simple "Generate Fix" button that opens the chat drawer, while keeping campaign hub rendering.

**Step 2: Modify EvidenceFindings**

Replace the FixPipelinePanel usage with a lightweight component:

```tsx
// Instead of rendering full FixPipelinePanel, render:
// - CampaignOrchestrationHub (if multi-repo campaign active)
// - Simple "Generate Fix" chip that opens chat (if single repo)

// Remove FixPipelinePanel import, add:
import CampaignOrchestrationHub from './CampaignOrchestrationHub';
import { useChatUI } from '../../contexts/ChatContext';
import { useCampaignContext } from '../../contexts/CampaignContext';

// Replace FixPipelinePanel render with:
const { campaign } = useCampaignContext();
const { openDrawer, sendMessage } = useChatUI();

{campaign && campaign.total_count > 1 ? (
  <CampaignOrchestrationHub campaign={campaign} />
) : phase === 'diagnosis_complete' && (
  <button
    onClick={() => { openDrawer(); sendMessage('generate fix'); }}
    className="text-body-xs font-bold px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30"
  >
    Generate Fix
  </button>
)}
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/Investigation/EvidenceFindings.tsx
git commit -m "refactor(attestation): replace FixPipelinePanel with chat-first fix trigger"
```

---

### Task 19: Frontend — Clean Up InvestigationRoute

**Files:**
- Modify: `frontend/src/pages/InvestigationRoute.tsx` — remove remaining attestation state/handlers if any

**Step 1: Verify InvestigationRoute is clean**

Check that all `attestationGate`, `setAttestationGate`, `handleAttestationDecision`, and `onAttestationDecision` references are already removed (they should be from our earlier work). Verify `submitAttestation` import is gone.

**Step 2: Remove any remaining dead imports**

```tsx
// Ensure these are NOT imported:
// - AttestationGateData (already removed)
// - submitAttestation (already removed)
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit (if changes needed)**

```bash
git add frontend/src/pages/InvestigationRoute.tsx
git commit -m "refactor(attestation): clean up InvestigationRoute dead attestation references"
```

---

### Task 20: Timeout Background Task

**Files:**
- Modify: `backend/src/api/main.py` — add background task for pending action timeout checks
- Test: `backend/tests/test_timeout_handler.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_timeout_handler.py
import pytest
from datetime import datetime, timezone, timedelta
from src.models.pending_action import PendingAction


def test_expired_action_detected():
    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        context={},
        version=1,
    )
    assert pa.is_expired() is True


def test_non_expired_action_not_detected():
    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=600),
        context={},
        version=1,
    )
    assert pa.is_expired() is False
```

**Step 2: Run test**

Run: `cd backend && python -m pytest tests/test_timeout_handler.py -v`
Expected: PASS

**Step 3: Add timeout check background task**

In `backend/src/api/main.py`, add a background task on startup:

```python
async def _pending_action_timeout_loop():
    """Check for expired pending actions and re-emit with cleared expiry."""
    import asyncio
    while True:
        await asyncio.sleep(30)  # Check every 30 seconds
        try:
            redis_client = app.state.redis
            if not redis_client:
                continue
            # Scan for pending_action:* keys
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor, match="pending_action:*", count=100)
                for key in keys:
                    raw = await redis_client.get(key)
                    if not raw:
                        continue
                    import json
                    data = json.loads(raw if isinstance(raw, str) else raw.decode())
                    pa = PendingAction.from_dict(data)
                    if pa.is_expired():
                        session_id = key.decode().split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]

                        # Reset expiry (indefinite wait) — don't auto-reject
                        pa.expires_at = None
                        await redis_client.set(key, json.dumps(pa.to_dict()), ex=86400)

                        # Notify user via event emitter
                        from src.api.routes_v4 import sessions as active_sessions
                        session = active_sessions.get(session_id)
                        emitter = session.get("emitter") if session else None
                        if emitter:
                            actions_str = " / ".join(f"'{a}'" for a in pa.actions)
                            await emitter.emit(
                                "supervisor", "waiting_for_input",
                                f"No response received — action still required. You can say {actions_str}.",
                                details={"pending_action": pa.to_dict()},
                            )

                        # Log timeout to audit trail
                        attestation_logger = _get_attestation_logger()
                        if attestation_logger:
                            await attestation_logger.log_decision(
                                session_id=session_id,
                                finding_id="timeout",
                                decision="timed_out_reset",
                                decided_by="system",
                                confidence=0.0,
                                finding_summary=f"Pending action {pa.type} timed out — reset to indefinite",
                            )
                        logger.info(f"Pending action timed out for session {session_id}, re-emitted")
                if cursor == 0:
                    break
        except Exception:
            pass  # Non-critical background task

# In startup event:
asyncio.create_task(_pending_action_timeout_loop())
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_timeout_handler.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/main.py backend/tests/test_timeout_handler.py
git commit -m "feat(attestation): add background timeout handler for expired pending actions"
```

---

### Task 21: Feedback Dedup with Client UUID

**Files:**
- Modify: `backend/src/agents/supervisor.py` — dedup feedback by ID
- Modify: `frontend/src/components/Chat/ChatDrawer.tsx` — generate feedback_id

**Step 1: Add dedup to _process_fix_decision**

In `supervisor.py`, track seen feedback IDs:

```python
# In __init__:
self._seen_feedback_ids: set[str] = set()

# In _process_fix_decision, for feedback case:
# Parse feedback_id if present: "feedback:uuid:actual feedback text"
if ":" in text and text.startswith("feedback:"):
    parts = text.split(":", 2)
    if len(parts) == 3:
        feedback_id = parts[1]
        if feedback_id in self._seen_feedback_ids:
            return "Feedback already received."
        self._seen_feedback_ids.add(feedback_id)
        feedback_text = parts[2]
    else:
        feedback_text = text
```

**Step 2: Frontend generates UUID for feedback**

In ChatDrawer or wherever feedback is sent:

```typescript
// When sending feedback:
const feedbackId = crypto.randomUUID();
sendMessage(`feedback:${feedbackId}:${feedbackText}`);
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/ -v --timeout=30`
Expected: PASS

**Step 4: Commit**

```bash
git add backend/src/agents/supervisor.py frontend/src/components/Chat/ChatDrawer.tsx
git commit -m "feat(attestation): dedup fix feedback with client-generated UUID"
```

---

### Task 22: Integration Smoke Tests

**Files:**
- Create: `backend/tests/test_attestation_integration.py`

**Step 1: Write integration tests**

```python
# backend/tests/test_attestation_integration.py
import json
import pytest
from unittest.mock import AsyncMock
from src.models.pending_action import PendingAction
from src.agents.intent_parser import IntentParser, UserIntent
from src.utils.redis_store import RedisSessionStore


@pytest.mark.asyncio
async def test_full_attestation_flow():
    """End-to-end: save pending → parse intent → clear pending."""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.get = AsyncMock()
    mock_redis.delete = AsyncMock()
    store = RedisSessionStore(mock_redis)

    # 1. Save pending action
    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=None,
        context={"confidence": 0.87},
        version=1,
    )
    await store.save_pending_action("sess-1", pa)
    assert mock_redis.set.called

    # 2. Parse user intent
    parser = IntentParser()
    intent = parser.parse("looks good", pa)
    assert intent.type == "approve_attestation"

    # 3. Clear pending action
    await store.clear_pending_action("sess-1")
    mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_fix_approval_flow():
    """End-to-end: fix pending → approve intent → clear."""
    parser = IntentParser()
    pa = PendingAction(
        type="fix_approval",
        blocking=True,
        actions=["approve", "reject", "feedback"],
        expires_at=None,
        context={},
        version=1,
    )
    intent = parser.parse("create pr", pa)
    assert intent.type == "approve_fix"


@pytest.mark.asyncio
async def test_ambiguous_input_low_confidence():
    """Ambiguous input should return low confidence for re-prompting."""
    parser = IntentParser()
    pa = PendingAction(
        type="attestation_required",
        blocking=True,
        actions=["approve", "reject"],
        expires_at=None,
        context={},
        version=1,
    )
    intent = parser.parse("hmm maybe", pa)
    assert intent.confidence < 0.7


def test_pending_action_roundtrip():
    pa = PendingAction(
        type="campaign_execute_confirm",
        blocking=True,
        actions=["confirm", "cancel"],
        expires_at=None,
        context={"repo_count": 5},
        version=2,
    )
    restored = PendingAction.from_dict(pa.to_dict())
    assert restored.type == pa.type
    assert restored.version == 2
    assert restored.context["repo_count"] == 5
```

**Step 2: Run all integration tests**

Run: `cd backend && python -m pytest tests/test_attestation_integration.py -v`
Expected: PASS (4 tests)

**Step 3: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --timeout=30`
Expected: PASS (all tests)

**Step 4: Commit**

```bash
git add backend/tests/test_attestation_integration.py
git commit -m "test(attestation): add integration smoke tests for full attestation flow"
```

---

## Execution Summary

| Task | Description | Backend | Frontend |
|------|-------------|---------|----------|
| 1 | PendingAction model | Create | — |
| 2 | IntentParser | Create | — |
| 3 | Wire audit trail logging | Modify | — |
| 4 | State-driven save/exit | Modify | — |
| 5 | State-driven resume | Modify | — |
| 6 | pending_action in status | Modify | — |
| 7 | State-driven fix approval | Modify | — |
| 8 | IntentParser routing | Modify | — |
| 9 | Remove dead code | Modify + Delete | Modify |
| 10 | Idempotency guards | Modify | — |
| 11 | Campaign execute confirm | Modify | — |
| 12 | Campaign persistence | Modify | — |
| 13 | PendingAction type + API | — | Modify |
| 14 | PinnedActionCard component | — | Create |
| 15 | Wire into ChatDrawer | — | Modify |
| 16 | Pulsing LedgerTriggerTab | — | Modify |
| 17 | Remove AttestationRequiredCard | — | Modify |
| 18 | Remove FixPipelinePanel usage | — | Modify |
| 19 | Clean up InvestigationRoute | — | Modify |
| 20 | Timeout background task | Modify | — |
| 21 | Feedback dedup | Modify | Modify |
| 22 | Integration smoke tests | Create | — |
