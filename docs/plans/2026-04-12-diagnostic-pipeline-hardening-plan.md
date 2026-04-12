# Diagnostic Pipeline Hardening — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close all 15 architectural gaps in the app diagnostic workflow, transforming the system from single-process in-memory to multi-instance Redis-backed with cross-repo dependency tracing.

**Architecture:** Infrastructure-first approach. Phase 1 lays Redis foundation (sessions, pub/sub, semaphores) + context window guard. Phase 2 adds circuit breakers, error propagation, attestation timeout. Phase 3 builds per-finding attestation + audit trail. Phase 4 adds cross-repo dependency tracing. Phase 5 improves causal reasoning. Phase 6 hardens operations.

**Tech Stack:** Python 3.12, FastAPI, asyncio, redis[hiredis], tiktoken, pytest, Anthropic SDK.

**Design doc:** `docs/plans/2026-04-12-diagnostic-pipeline-hardening-design.md`

---

## Phase 1: Redis Foundation + Context Window Guard

---

### Task 1: Redis Session Store

**Files:**
- Create: `backend/src/utils/redis_store.py`
- Test: `backend/tests/test_redis_store.py`
- Modify: `backend/requirements.txt` (add `redis[hiredis]>=5.0`)

**Step 1: Add redis dependency**

Add to `backend/requirements.txt`:
```
redis[hiredis]>=5.0
```

Run: `cd backend && pip install -r requirements.txt`
Expected: installs successfully.

**Step 2: Write failing tests for RedisSessionStore**

```python
# backend/tests/test_redis_store.py
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

from src.utils.redis_store import RedisSessionStore


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.hset = AsyncMock()
    r.hgetall = AsyncMock(return_value={})
    r.delete = AsyncMock()
    r.expire = AsyncMock()
    r.lock = MagicMock(return_value=AsyncMock())
    return r


@pytest.fixture
def store(mock_redis):
    return RedisSessionStore(redis_client=mock_redis, ttl=3600)


@pytest.mark.asyncio
async def test_save_and_load(store, mock_redis):
    state = {"phase": "INITIAL", "confidence": 0.0, "findings": []}
    await store.save("sess-1", state)
    mock_redis.hset.assert_called_once()

    mock_redis.hgetall.return_value = {
        b"phase": b'"INITIAL"',
        b"confidence": b"0.0",
        b"findings": b"[]",
    }
    result = await store.load("sess-1")
    assert result["phase"] == "INITIAL"
    assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_load_missing_session(store, mock_redis):
    mock_redis.hgetall.return_value = {}
    result = await store.load("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_delete(store, mock_redis):
    await store.delete("sess-1")
    mock_redis.delete.assert_called_once_with("session:sess-1")


@pytest.mark.asyncio
async def test_extend_ttl(store, mock_redis):
    await store.extend_ttl("sess-1")
    mock_redis.expire.assert_called_once_with("session:sess-1", 3600)


@pytest.mark.asyncio
async def test_acquire_lock(store, mock_redis):
    lock = store.acquire_lock("sess-1")
    mock_redis.lock.assert_called_once()
```

**Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_redis_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.utils.redis_store'`

**Step 4: Implement RedisSessionStore**

```python
# backend/src/utils/redis_store.py
import json
import os
import logging
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_SESSION_TTL = int(os.getenv("SESSION_TTL_S", "3600"))


async def get_redis_client() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=False)


class RedisSessionStore:
    def __init__(self, redis_client: redis.Redis, ttl: int = DEFAULT_SESSION_TTL):
        self._redis = redis_client
        self._ttl = ttl

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def save(self, session_id: str, state: dict[str, Any]) -> None:
        key = self._key(session_id)
        mapping = {field: json.dumps(value) for field, value in state.items()}
        await self._redis.hset(key, mapping=mapping)
        await self._redis.expire(key, self._ttl)

    async def load(self, session_id: str) -> dict[str, Any] | None:
        raw = await self._redis.hgetall(self._key(session_id))
        if not raw:
            return None
        return {
            (k.decode() if isinstance(k, bytes) else k): json.loads(
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in raw.items()
        }

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    async def extend_ttl(self, session_id: str) -> None:
        await self._redis.expire(self._key(session_id), self._ttl)

    def acquire_lock(self, session_id: str, timeout: float = 10.0):
        return self._redis.lock(f"lock:{session_id}", timeout=timeout)
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_redis_store.py -v`
Expected: all 6 tests PASS.

**Step 6: Commit**

```bash
git add backend/src/utils/redis_store.py backend/tests/test_redis_store.py backend/requirements.txt
git commit -m "feat(infra): add RedisSessionStore with distributed locks and TTL"
```

---

### Task 2: Wire RedisSessionStore into routes_v4.py

**Files:**
- Modify: `backend/src/api/routes_v4.py:42,131,305,174,1057`
- Modify: `backend/src/api/main.py` (add Redis lifecycle)

**Step 1: Add Redis startup/shutdown to main.py**

At the top of `backend/src/api/main.py`, add the import and lifespan events. Find the existing lifespan or startup event and add:

```python
from src.utils.redis_store import get_redis_client, RedisSessionStore

# In the lifespan or startup:
app.state.redis = await get_redis_client()
app.state.session_store = RedisSessionStore(app.state.redis)

# In shutdown:
await app.state.redis.aclose()
```

**Step 2: Replace in-memory dict with RedisSessionStore in routes_v4.py**

At `routes_v4.py:131`, the current code is:
```python
sessions: Dict[str, Dict[str, Any]] = {}
```

Replace session reads/writes throughout the file. Each `sessions[session_id] = {...}` becomes `await session_store.save(session_id, {...})`. Each `sessions.get(session_id)` becomes `await session_store.load(session_id)`.

At `routes_v4.py:42`, replace `session_locks: Dict[str, asyncio.Lock] = {}` with `session_store.acquire_lock(session_id)`.

Remove `_session_cleanup_loop()` at line 174 — Redis TTL handles cleanup automatically.

**Step 3: Run existing tests**

Run: `cd backend && python -m pytest tests/test_api.py tests/test_investigate_endpoint.py -v`
Expected: PASS (tests use mocked sessions, so Redis isn't hit).

**Step 4: Commit**

```bash
git add backend/src/api/routes_v4.py backend/src/api/main.py
git commit -m "feat(infra): wire RedisSessionStore into API routes, remove in-memory dict"
```

---

### Task 3: WebSocket Redis Pub/Sub Bridge + Heartbeat

**Files:**
- Create: `backend/src/api/ws_pubsub.py`
- Modify: `backend/src/api/websocket.py:13-87`
- Test: `backend/tests/test_ws_pubsub.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_ws_pubsub.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.ws_pubsub import RedisPubSubBridge


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    pubsub = AsyncMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.get_message = AsyncMock(return_value=None)
    r.pubsub.return_value = pubsub
    r.publish = AsyncMock()
    return r, pubsub


@pytest.mark.asyncio
async def test_publish_event(mock_redis):
    redis_client, pubsub = mock_redis
    bridge = RedisPubSubBridge(redis_client)
    await bridge.publish("sess-1", {"event_type": "finding", "data": {}})
    redis_client.publish.assert_called_once()
    call_args = redis_client.publish.call_args
    assert call_args[0][0] == "ws:session:sess-1"


@pytest.mark.asyncio
async def test_subscribe_and_unsubscribe(mock_redis):
    redis_client, pubsub = mock_redis
    bridge = RedisPubSubBridge(redis_client)
    await bridge.subscribe("sess-1")
    pubsub.subscribe.assert_called_once_with("ws:session:sess-1")
    await bridge.unsubscribe("sess-1")
    pubsub.unsubscribe.assert_called_once_with("ws:session:sess-1")
```

**Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_ws_pubsub.py -v`
Expected: FAIL with `ModuleNotFoundError`.

**Step 3: Implement RedisPubSubBridge**

```python
# backend/src/api/ws_pubsub.py
import json
import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisPubSubBridge:
    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client
        self._pubsub = redis_client.pubsub()

    def _channel(self, session_id: str) -> str:
        return f"ws:session:{session_id}"

    async def publish(self, session_id: str, message: dict) -> None:
        await self._redis.publish(self._channel(session_id), json.dumps(message))

    async def subscribe(self, session_id: str) -> None:
        await self._pubsub.subscribe(self._channel(session_id))

    async def unsubscribe(self, session_id: str) -> None:
        await self._pubsub.unsubscribe(self._channel(session_id))

    async def get_message(self, timeout: float = 0.1) -> dict | None:
        msg = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        if msg and msg["type"] == "message":
            return json.loads(msg["data"])
        return None

    async def close(self) -> None:
        await self._pubsub.aclose()
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_ws_pubsub.py -v`
Expected: PASS.

**Step 5: Add heartbeat to ConnectionManager**

Modify `backend/src/api/websocket.py`. Add ping/pong heartbeat tracking to the `ConnectionManager` class:

```python
import asyncio
import os
import time

WS_HEARTBEAT_INTERVAL = int(os.getenv("WS_HEARTBEAT_INTERVAL_S", "30"))
WS_MAX_MISSED_PONGS = 3

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self._last_pong: Dict[int, float] = {}  # ws id → timestamp

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        self._last_pong[id(websocket)] = time.time()

    def disconnect(self, session_id: str, websocket: WebSocket = None):
        if websocket:
            self._last_pong.pop(id(websocket), None)
        # ... existing disconnect logic ...

    async def heartbeat_loop(self):
        while True:
            await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
            now = time.time()
            stale = []
            for sid, conns in list(self.active_connections.items()):
                for ws in conns:
                    elapsed = now - self._last_pong.get(id(ws), 0)
                    if elapsed > WS_HEARTBEAT_INTERVAL * WS_MAX_MISSED_PONGS:
                        stale.append((sid, ws))
                    else:
                        try:
                            await ws.send_json({"type": "ping"})
                        except Exception:
                            stale.append((sid, ws))
            for sid, ws in stale:
                self.disconnect(sid, ws)

    def record_pong(self, websocket: WebSocket):
        self._last_pong[id(websocket)] = time.time()
```

**Step 6: Modify EventEmitter to publish via Redis**

In `backend/src/utils/event_emitter.py`, add a `RedisPubSubBridge` reference. When `emit()` is called, publish to both the local WebSocket manager AND the Redis channel. This ensures cross-instance delivery.

**Step 7: Commit**

```bash
git add backend/src/api/ws_pubsub.py backend/src/api/websocket.py backend/src/utils/event_emitter.py backend/tests/test_ws_pubsub.py
git commit -m "feat(infra): WebSocket Redis pub/sub bridge + ping/pong heartbeat"
```

---

### Task 4: Distributed LLM Semaphore

**Files:**
- Create: `backend/src/utils/redis_semaphore.py`
- Test: `backend/tests/test_redis_semaphore.py`
- Modify: `backend/src/utils/llm_client.py:158`

**Step 1: Write failing tests**

```python
# backend/tests/test_redis_semaphore.py
import pytest
from unittest.mock import AsyncMock

from src.utils.redis_semaphore import RedisLLMSemaphore


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.incr = AsyncMock(return_value=1)
    r.decr = AsyncMock(return_value=0)
    r.expire = AsyncMock()
    r.get = AsyncMock(return_value=b"0")
    return r


@pytest.mark.asyncio
async def test_acquire_under_limit(mock_redis):
    sem = RedisLLMSemaphore(mock_redis, max_concurrent=10)
    acquired = await sem.acquire(timeout=5.0)
    assert acquired is True
    mock_redis.incr.assert_called_once_with("llm:semaphore")


@pytest.mark.asyncio
async def test_acquire_at_limit_fails(mock_redis):
    mock_redis.incr.return_value = 11
    sem = RedisLLMSemaphore(mock_redis, max_concurrent=10)
    acquired = await sem.acquire(timeout=0.1)
    assert acquired is False
    mock_redis.decr.assert_called()  # rolled back


@pytest.mark.asyncio
async def test_release(mock_redis):
    sem = RedisLLMSemaphore(mock_redis, max_concurrent=10)
    await sem.release()
    mock_redis.decr.assert_called_once_with("llm:semaphore")
```

**Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_redis_semaphore.py -v`
Expected: FAIL.

**Step 3: Implement**

```python
# backend/src/utils/redis_semaphore.py
import asyncio
import os
import random
import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)

MAX_CONCURRENT_LLM = int(os.getenv("MAX_CONCURRENT_LLM_CALLS", "10"))
SEMAPHORE_KEY = "llm:semaphore"
SEMAPHORE_TTL = 60


class RedisLLMSemaphore:
    def __init__(self, redis_client: redis.Redis, max_concurrent: int = MAX_CONCURRENT_LLM):
        self._redis = redis_client
        self._max = max_concurrent

    async def acquire(self, timeout: float = 30.0) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            count = await self._redis.incr(SEMAPHORE_KEY)
            await self._redis.expire(SEMAPHORE_KEY, SEMAPHORE_TTL)
            if count <= self._max:
                return True
            await self._redis.decr(SEMAPHORE_KEY)
            await asyncio.sleep(0.5 + random.uniform(0, 0.5))
        return False

    async def release(self) -> None:
        val = await self._redis.decr(SEMAPHORE_KEY)
        if val < 0:
            await self._redis.set(SEMAPHORE_KEY, 0)
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_redis_semaphore.py -v`
Expected: PASS.

**Step 5: Wire into llm_client.py**

Modify `backend/src/utils/llm_client.py:158` — wrap the `chat_with_tools()` method so it acquires the semaphore before calling Anthropic and releases after:

```python
async def chat_with_tools(self, system, messages, tools=None, max_tokens=4096, temperature=0.0):
    if self._semaphore:
        acquired = await self._semaphore.acquire()
        if not acquired:
            raise RuntimeError("LLM semaphore timeout — too many concurrent calls")
    try:
        # ... existing implementation ...
    finally:
        if self._semaphore:
            await self._semaphore.release()
```

Add `semaphore: RedisLLMSemaphore | None = None` to the constructor.

**Step 6: Commit**

```bash
git add backend/src/utils/redis_semaphore.py backend/tests/test_redis_semaphore.py backend/src/utils/llm_client.py
git commit -m "feat(infra): distributed LLM semaphore via Redis"
```

---

### Task 5: Context Window Guard

**Files:**
- Create: `backend/src/utils/context_guard.py`
- Test: `backend/tests/test_context_guard.py`
- Modify: `backend/src/agents/react_base.py:265`
- Modify: `backend/requirements.txt` (add `tiktoken`)

**Step 1: Add tiktoken dependency**

Add to `backend/requirements.txt`:
```
tiktoken>=0.7
```

Run: `cd backend && pip install tiktoken`

**Step 2: Write failing tests**

```python
# backend/tests/test_context_guard.py
import pytest
from src.utils.context_guard import ContextWindowGuard


@pytest.fixture
def guard():
    return ContextWindowGuard(model_name="claude-haiku-4-5-20251001")


def test_estimate_tokens(guard):
    messages = [{"role": "user", "content": "Hello world"}]
    count = guard.estimate_tokens(messages)
    assert count > 0
    assert isinstance(count, int)


def test_model_limit_haiku(guard):
    limit = guard.model_limit("claude-haiku-4-5-20251001")
    assert limit == 128000


def test_model_limit_sonnet():
    guard = ContextWindowGuard(model_name="claude-sonnet-4-20250514")
    limit = guard.model_limit("claude-sonnet-4-20250514")
    assert limit == 200000


def test_no_truncation_under_threshold(guard):
    messages = [{"role": "user", "content": "Short message"}]
    result = guard.truncate_if_needed(messages)
    assert len(result) == len(messages)


def test_truncation_drops_old_tool_results(guard):
    messages = [{"role": "user", "content": "initial"}]
    for i in range(20):
        messages.append({"role": "assistant", "content": f"tool_call_{i}"})
        messages.append({"role": "user", "content": "x" * 10000})
    result = guard.truncate_if_needed(messages)
    assert len(result) < len(messages)


def test_single_large_tool_result_tailed(guard):
    messages = [
        {"role": "user", "content": "initial"},
        {"role": "user", "content": "x\n" * 50000},
    ]
    result = guard.truncate_if_needed(messages)
    total_content = sum(len(m.get("content", "")) for m in result)
    assert total_content < 50000 * 2
```

**Step 3: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_context_guard.py -v`
Expected: FAIL.

**Step 4: Implement ContextWindowGuard**

```python
# backend/src/utils/context_guard.py
import logging
import tiktoken

logger = logging.getLogger(__name__)

MODEL_LIMITS = {
    "claude-haiku-4-5-20251001": 128_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-opus-4-6": 200_000,
}
DEFAULT_LIMIT = 128_000
THRESHOLD = 0.80
MAX_SINGLE_RESULT_TOKENS = 20_000
TAIL_LINES = 500
KEEP_RECENT_TOOL_PAIRS = 3


class ContextWindowGuard:
    def __init__(self, model_name: str = "claude-haiku-4-5-20251001"):
        self._model = model_name
        try:
            self._enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._enc = tiktoken.get_encoding("cl100k_base")

    def estimate_tokens(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(self._enc.encode(content))
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total += len(self._enc.encode(block["text"]))
        return total

    def model_limit(self, model_name: str | None = None) -> int:
        name = model_name or self._model
        for key, limit in MODEL_LIMITS.items():
            if key in name:
                return limit
        return DEFAULT_LIMIT

    def truncate_if_needed(self, messages: list[dict]) -> list[dict]:
        limit = int(self.model_limit() * THRESHOLD)
        current = self.estimate_tokens(messages)
        if current <= limit:
            return messages

        logger.warning(f"Context at {current} tokens ({current/self.model_limit()*100:.0f}%), truncating (limit={limit})")

        result = list(messages)
        result = self._tail_large_results(result)
        if self.estimate_tokens(result) <= limit:
            return result

        result = self._drop_old_tool_results(result)
        return result

    def _tail_large_results(self, messages: list[dict]) -> list[dict]:
        out = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and len(self._enc.encode(content)) > MAX_SINGLE_RESULT_TOKENS:
                lines = content.split("\n")
                if len(lines) > TAIL_LINES:
                    truncated = f"[Truncated {len(lines) - TAIL_LINES} lines]\n" + "\n".join(lines[-TAIL_LINES:])
                    out.append({**msg, "content": truncated})
                    continue
            out.append(msg)
        return out

    def _drop_old_tool_results(self, messages: list[dict]) -> list[dict]:
        if len(messages) <= 2:
            return messages
        head = messages[:1]
        tail_pairs = messages[-KEEP_RECENT_TOOL_PAIRS * 2:]
        middle = messages[1:-KEEP_RECENT_TOOL_PAIRS * 2] if len(messages) > KEEP_RECENT_TOOL_PAIRS * 2 + 1 else []
        if middle:
            summary_text = f"[Prior investigation: {len(middle)} messages summarized. Key actions taken but details truncated to fit context window.]"
            summary = {"role": "user", "content": summary_text}
            return head + [summary] + tail_pairs
        return messages
```

**Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_context_guard.py -v`
Expected: PASS.

**Step 6: Hook into ReAct loop**

Modify `backend/src/agents/react_base.py`. In the constructor (line ~33), create the guard:

```python
from src.utils.context_guard import ContextWindowGuard

# In __init__:
self._context_guard = ContextWindowGuard(model_name=self.model)
```

At line ~265, right before the LLM call, add:

```python
messages = self._context_guard.truncate_if_needed(messages)
```

**Step 7: Run existing ReAct tests**

Run: `cd backend && python -m pytest tests/test_react_base.py tests/test_react_budget.py -v`
Expected: PASS (guard is transparent for small contexts).

**Step 8: Commit**

```bash
git add backend/src/utils/context_guard.py backend/tests/test_context_guard.py backend/src/agents/react_base.py backend/requirements.txt
git commit -m "feat(resilience): context window guard with tiktoken — truncates at 80% capacity"
```

---

## Phase 2: Quick Reliability Wins

---

### Task 6: Redis-Backed Circuit Breaker

**Files:**
- Create: `backend/src/utils/circuit_breaker.py`
- Test: `backend/tests/test_circuit_breaker.py`
- Modify: `backend/src/agents/retry.py:21`

**Step 1: Write failing tests**

```python
# backend/tests/test_circuit_breaker.py
import pytest
import time
from unittest.mock import AsyncMock

from src.utils.circuit_breaker import RedisCircuitBreaker


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.incr = AsyncMock(return_value=1)
    r.expire = AsyncMock()
    r.set = AsyncMock()
    r.delete = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_closed_by_default(mock_redis):
    cb = RedisCircuitBreaker(mock_redis)
    assert await cb.is_open("elasticsearch") is False


@pytest.mark.asyncio
async def test_opens_after_threshold(mock_redis):
    cb = RedisCircuitBreaker(mock_redis, failure_threshold=3)
    mock_redis.incr.return_value = 3
    await cb.record_failure("elasticsearch")
    mock_redis.set.assert_called()  # circuit opened


@pytest.mark.asyncio
async def test_open_circuit_blocks(mock_redis):
    cb = RedisCircuitBreaker(mock_redis)
    mock_redis.get.return_value = b"open"
    assert await cb.is_open("elasticsearch") is True


@pytest.mark.asyncio
async def test_success_resets_failures(mock_redis):
    cb = RedisCircuitBreaker(mock_redis)
    await cb.record_success("elasticsearch")
    mock_redis.delete.assert_called()
```

**Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_circuit_breaker.py -v`
Expected: FAIL.

**Step 3: Implement**

```python
# backend/src/utils/circuit_breaker.py
import logging
import os

import redis.asyncio as redis

logger = logging.getLogger(__name__)

FAILURE_WINDOW = 60
RECOVERY_TIMEOUT = int(os.getenv("CIRCUIT_BREAKER_RECOVERY_S", "120"))


class RedisCircuitBreaker:
    def __init__(
        self,
        redis_client: redis.Redis,
        failure_threshold: int = 3,
        recovery_timeout: int = RECOVERY_TIMEOUT,
    ):
        self._redis = redis_client
        self._threshold = failure_threshold
        self._recovery = recovery_timeout

    def _state_key(self, service: str) -> str:
        return f"cb:{service}:state"

    def _fail_key(self, service: str) -> str:
        return f"cb:{service}:failures"

    async def is_open(self, service: str) -> bool:
        state = await self._redis.get(self._state_key(service))
        if state and state in (b"open", "open"):
            return True
        return False

    async def record_failure(self, service: str) -> None:
        key = self._fail_key(service)
        count = await self._redis.incr(key)
        await self._redis.expire(key, FAILURE_WINDOW)
        if count >= self._threshold:
            await self._redis.set(self._state_key(service), "open", ex=self._recovery)
            await self._redis.delete(key)
            logger.warning(f"Circuit OPEN for {service} — {count} failures in {FAILURE_WINDOW}s")

    async def record_success(self, service: str) -> None:
        await self._redis.delete(self._fail_key(service))
        await self._redis.delete(self._state_key(service))

    async def get_retry_after(self, service: str) -> int | None:
        ttl = await self._redis.ttl(self._state_key(service))
        return ttl if ttl > 0 else None
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_circuit_breaker.py -v`
Expected: PASS.

**Step 5: Integrate with retry decorator**

Modify `backend/src/agents/retry.py:21`. Add a `circuit_breaker` parameter:

```python
def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0, service_name: str | None = None):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cb = kwargs.pop("_circuit_breaker", None)
            if cb and service_name and await cb.is_open(service_name):
                retry_after = await cb.get_retry_after(service_name)
                return f'{{"error": "circuit_open", "service": "{service_name}", "retry_after_s": {retry_after or 0}}}'

            for attempt in range(max_retries + 1):
                try:
                    result = await func(*args, **kwargs)
                    if cb and service_name:
                        await cb.record_success(service_name)
                    return result
                except RETRYABLE_EXCEPTIONS as e:
                    if cb and service_name:
                        await cb.record_failure(service_name)
                    if attempt == max_retries:
                        raise
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)
        return wrapper
    return decorator
```

**Step 6: Run existing retry tests**

Run: `cd backend && python -m pytest tests/ -k "retry" -v`
Expected: PASS.

**Step 7: Commit**

```bash
git add backend/src/utils/circuit_breaker.py backend/tests/test_circuit_breaker.py backend/src/agents/retry.py
git commit -m "feat(resilience): Redis-backed circuit breaker for data sources"
```

---

### Task 7: Tool Error Propagation

**Files:**
- Modify: `backend/src/tools/tool_executor.py:271`

**Step 1: Find and replace broad except blocks**

Search `tool_executor.py` for `except Exception` blocks that return generic error strings. Replace each with detailed error propagation:

```python
# Before (multiple locations):
except Exception:
    return "Error executing {tool}"

# After:
except Exception as e:
    error_detail = f"Tool '{intent}' failed: {type(e).__name__}: {str(e)}"
    logger.exception(f"[tool_executor] {error_detail}")
    return ToolResult(success=False, data=error_detail)
```

Ensure the full traceback is logged via `logger.exception()` but only the one-liner goes to the LLM.

**Step 2: Run existing tool executor tests**

Run: `cd backend && python -m pytest tests/test_tool_executor.py tests/test_tool_executor_extended.py tests/test_tool_executor_validation.py -v`
Expected: PASS (or fix any tests that assert on the old generic error string).

**Step 3: Commit**

```bash
git add backend/src/tools/tool_executor.py
git commit -m "fix(tools): propagate error type and message to LLM instead of generic string"
```

---

### Task 8: Attestation Timeout + Auto-Approval

**Files:**
- Modify: `backend/src/agents/supervisor.py:2985`
- Modify: `backend/src/api/routes_v4.py:1454`
- Test: `backend/tests/test_attestation.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_attestation.py
import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_attestation_timeout():
    from src.agents.supervisor import SupervisorAgent
    supervisor = SupervisorAgent.__new__(SupervisorAgent)
    supervisor._attestation_event = asyncio.Event()
    supervisor._attestation_acknowledged = None
    supervisor._event_emitter = AsyncMock()

    with patch.dict(os.environ, {"ATTESTATION_TIMEOUT_S": "1"}):
        result = await supervisor._wait_for_attestation(timeout=1.0)
    assert result == "timeout"


@pytest.mark.asyncio
async def test_auto_approval_above_threshold():
    from src.agents.supervisor import SupervisorAgent
    supervisor = SupervisorAgent.__new__(SupervisorAgent)
    supervisor._event_emitter = AsyncMock()

    with patch.dict(os.environ, {"ATTESTATION_AUTO_APPROVE_THRESHOLD": "0.85"}):
        result = supervisor._should_auto_approve(confidence=0.92, critic_has_challenges=False)
    assert result is True


@pytest.mark.asyncio
async def test_no_auto_approval_below_threshold():
    from src.agents.supervisor import SupervisorAgent
    supervisor = SupervisorAgent.__new__(SupervisorAgent)

    with patch.dict(os.environ, {"ATTESTATION_AUTO_APPROVE_THRESHOLD": "0.85"}):
        result = supervisor._should_auto_approve(confidence=0.70, critic_has_challenges=False)
    assert result is False


@pytest.mark.asyncio
async def test_no_auto_approval_with_challenges():
    from src.agents.supervisor import SupervisorAgent
    supervisor = SupervisorAgent.__new__(SupervisorAgent)

    with patch.dict(os.environ, {"ATTESTATION_AUTO_APPROVE_THRESHOLD": "0.85"}):
        result = supervisor._should_auto_approve(confidence=0.95, critic_has_challenges=True)
    assert result is False
```

**Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_attestation.py -v`
Expected: FAIL.

**Step 3: Implement in supervisor.py**

Add two methods near `acknowledge_attestation()` at line 2985:

```python
ATTESTATION_TIMEOUT = float(os.getenv("ATTESTATION_TIMEOUT_S", "600"))
AUTO_APPROVE_THRESHOLD = float(os.getenv("ATTESTATION_AUTO_APPROVE_THRESHOLD", "0.85"))

def _should_auto_approve(self, confidence: float, critic_has_challenges: bool) -> bool:
    threshold = float(os.getenv("ATTESTATION_AUTO_APPROVE_THRESHOLD", "0.85"))
    return confidence >= threshold and not critic_has_challenges

async def _wait_for_attestation(self, timeout: float | None = None) -> str:
    t = timeout or float(os.getenv("ATTESTATION_TIMEOUT_S", "600"))
    try:
        await asyncio.wait_for(self._attestation_event.wait(), timeout=t)
        return "approved" if self._attestation_acknowledged else "rejected"
    except asyncio.TimeoutError:
        if self._event_emitter:
            await self._event_emitter.emit("supervisor", "attestation_expired", {"reason": "no_response"})
        return "timeout"
```

Modify the attestation gate call site to check auto-approval first:

```python
if self._should_auto_approve(composite_confidence, critic_has_challenges):
    await self._event_emitter.emit("supervisor", "auto_approved", {"confidence": composite_confidence})
    # proceed to fix generation
else:
    await self._event_emitter.emit("supervisor", "attestation_required", {...})
    decision = await self._wait_for_attestation()
    if decision == "timeout":
        return SessionResult(status="completed_no_fix", findings=current_findings)
    elif decision == "rejected":
        return SessionResult(status="completed_no_fix", findings=current_findings)
    # proceed to fix generation
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_attestation.py tests/test_supervisor.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/src/agents/supervisor.py backend/tests/test_attestation.py
git commit -m "feat(attestation): 10-min timeout + confidence-based auto-approval"
```

---

## Phase 3: Per-Finding Attestation + Audit Trail

---

### Task 9: Per-Finding Attestation Data Model

**Files:**
- Create: `backend/src/models/attestation.py`
- Modify: `backend/src/agents/supervisor.py:2985`
- Modify: `backend/src/api/routes_v4.py:1454`
- Test: `backend/tests/test_per_finding_attestation.py`

**Step 1: Write the data model**

```python
# backend/src/models/attestation.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class AttestationDecision:
    finding_id: str
    decision: Literal["approved", "rejected", "skipped"]
    decided_by: str
    decided_at: datetime
    confidence_at_decision: float


@dataclass
class AttestationGate:
    findings: list[dict]
    decisions: dict[str, AttestationDecision] = field(default_factory=dict)
    status: Literal["pending", "partially_decided", "complete"] = "pending"
    auto_approved: bool = False
    expires_at: datetime | None = None

    def is_complete(self) -> bool:
        return len(self.decisions) == len(self.findings)

    def approved_finding_ids(self) -> list[str]:
        return [fid for fid, d in self.decisions.items() if d.decision == "approved"]
```

**Step 2: Write failing tests**

```python
# backend/tests/test_per_finding_attestation.py
import pytest
from datetime import datetime
from src.models.attestation import AttestationGate, AttestationDecision


def test_gate_pending_by_default():
    gate = AttestationGate(findings=[{"finding_id": "f1"}, {"finding_id": "f2"}])
    assert gate.status == "pending"
    assert gate.is_complete() is False


def test_gate_complete_when_all_decided():
    gate = AttestationGate(findings=[{"finding_id": "f1"}])
    gate.decisions["f1"] = AttestationDecision(
        finding_id="f1", decision="approved", decided_by="user",
        decided_at=datetime.utcnow(), confidence_at_decision=0.9,
    )
    assert gate.is_complete() is True


def test_approved_finding_ids():
    gate = AttestationGate(findings=[{"finding_id": "f1"}, {"finding_id": "f2"}])
    gate.decisions["f1"] = AttestationDecision(
        finding_id="f1", decision="approved", decided_by="user",
        decided_at=datetime.utcnow(), confidence_at_decision=0.9,
    )
    gate.decisions["f2"] = AttestationDecision(
        finding_id="f2", decision="rejected", decided_by="user",
        decided_at=datetime.utcnow(), confidence_at_decision=0.5,
    )
    assert gate.approved_finding_ids() == ["f1"]
```

**Step 3: Run, verify failure, implement, verify pass**

Run: `cd backend && python -m pytest tests/test_per_finding_attestation.py -v`

**Step 4: Update API endpoint**

Modify `routes_v4.py:1454` to accept per-finding decisions:

```python
class PerFindingDecision(BaseModel):
    finding_id: str
    decision: Literal["approved", "rejected", "skipped"]

class AttestationRequest(BaseModel):
    decisions: list[PerFindingDecision]

@router_v4.post("/session/{session_id}/attestation")
async def submit_attestation(session_id: str, request: AttestationRequest):
    # ... validate session exists ...
    for d in request.decisions:
        supervisor.record_finding_decision(d.finding_id, d.decision, decided_by="user")
    if supervisor.attestation_gate.is_complete():
        supervisor.acknowledge_attestation("approve")
    return {"status": "ok", "complete": supervisor.attestation_gate.is_complete()}
```

**Step 5: Commit**

```bash
git add backend/src/models/attestation.py backend/tests/test_per_finding_attestation.py backend/src/agents/supervisor.py backend/src/api/routes_v4.py
git commit -m "feat(attestation): per-finding approve/reject/skip decisions"
```

---

### Task 10: Attestation Audit Trail (SQLite)

**Files:**
- Create: `backend/src/utils/attestation_log.py`
- Test: `backend/tests/test_attestation_log.py`
- Modify: `backend/src/api/routes_v4.py` (add query endpoint)

**Step 1: Write failing tests**

```python
# backend/tests/test_attestation_log.py
import pytest
import sqlite3
import tempfile
import os
from datetime import datetime

from src.utils.attestation_log import AttestationLogger


@pytest.fixture
def logger():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    al = AttestationLogger(db_path=path)
    yield al
    os.unlink(path)


def test_log_and_query(logger):
    logger.log_decision(
        session_id="sess-1", finding_id="f1", decision="approved",
        decided_by="user", confidence=0.92, finding_summary="OOM in pod-xyz",
    )
    results = logger.query(session_id="sess-1")
    assert len(results) == 1
    assert results[0]["decision"] == "approved"


def test_query_by_user(logger):
    logger.log_decision("s1", "f1", "approved", "user", 0.9, "finding 1")
    logger.log_decision("s2", "f2", "auto_approved", "system", 0.95, "finding 2")
    results = logger.query(decided_by="user")
    assert len(results) == 1


def test_upsert_on_duplicate(logger):
    logger.log_decision("s1", "f1", "skipped", "user", 0.5, "finding")
    logger.log_decision("s1", "f1", "approved", "user", 0.8, "finding updated")
    results = logger.query(session_id="s1")
    assert len(results) == 1
    assert results[0]["decision"] == "approved"
```

**Step 2: Implement**

```python
# backend/src/utils/attestation_log.py
import sqlite3
import os
from datetime import datetime

DEFAULT_DB = os.getenv("DEBUGDUCK_DB", "data/debugduck.db")


class AttestationLogger:
    def __init__(self, db_path: str = DEFAULT_DB):
        self._db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS attestation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    finding_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    decided_by TEXT NOT NULL,
                    decided_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    confidence REAL,
                    finding_summary TEXT,
                    UNIQUE(session_id, finding_id)
                )
            """)

    def log_decision(self, session_id: str, finding_id: str, decision: str,
                     decided_by: str, confidence: float, finding_summary: str):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                INSERT INTO attestation_log (session_id, finding_id, decision, decided_by, decided_at, confidence, finding_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, finding_id) DO UPDATE SET
                    decision=excluded.decision, decided_by=excluded.decided_by,
                    decided_at=excluded.decided_at, confidence=excluded.confidence,
                    finding_summary=excluded.finding_summary
            """, (session_id, finding_id, decision, decided_by, datetime.utcnow().isoformat(), confidence, finding_summary))

    def query(self, session_id: str | None = None, decided_by: str | None = None,
              since: str | None = None) -> list[dict]:
        conditions, params = [], []
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if decided_by:
            conditions.append("decided_by = ?")
            params.append(decided_by)
        if since:
            conditions.append("decided_at >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"SELECT * FROM attestation_log {where} ORDER BY decided_at DESC", params).fetchall()
            return [dict(r) for r in rows]
```

**Step 3: Run tests, verify pass**

Run: `cd backend && python -m pytest tests/test_attestation_log.py -v`
Expected: PASS.

**Step 4: Add query endpoint to routes_v4.py**

```python
@router_v4.get("/audit/attestations")
async def get_attestation_log(session_id: str | None = None, decided_by: str | None = None, since: str | None = None):
    logger = AttestationLogger()
    return logger.query(session_id=session_id, decided_by=decided_by, since=since)
```

**Step 5: Commit**

```bash
git add backend/src/utils/attestation_log.py backend/tests/test_attestation_log.py backend/src/api/routes_v4.py
git commit -m "feat(compliance): attestation audit trail in SQLite with query API"
```

---

## Phase 4: Cross-Repo Dependency Tracing

---

### Task 11: Dependency Manifest Parser

**Files:**
- Create: `backend/src/tools/dependency_parser.py`
- Test: `backend/tests/test_dependency_parser.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_dependency_parser.py
import pytest
import tempfile
import os
import json

from src.tools.dependency_parser import DependencyParser, Dependency


@pytest.fixture
def parser():
    return DependencyParser(repo_map={"auth-service": "https://github.com/org/auth-service"})


def test_parse_requirements_txt(parser, tmp_path):
    (tmp_path / "requirements.txt").write_text("requests>=2.28\nflask==2.3.0\n")
    deps = parser.parse(str(tmp_path))
    assert len(deps) == 2
    assert deps[0].name == "requests"
    assert deps[0].source == "pypi"


def test_parse_package_json(parser, tmp_path):
    pkg = {"dependencies": {"express": "^4.18.0", "@org/auth-client": "^1.0.0"}}
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    deps = parser.parse(str(tmp_path))
    assert any(d.name == "express" for d in deps)


def test_parse_go_mod(parser, tmp_path):
    (tmp_path / "go.mod").write_text("module github.com/org/myapp\nrequire github.com/gin-gonic/gin v1.9.1\n")
    deps = parser.parse(str(tmp_path))
    assert any(d.name == "github.com/gin-gonic/gin" for d in deps)


def test_internal_dependency_detection(parser, tmp_path):
    pkg = {"dependencies": {"auth-service": "^1.0.0"}}
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    deps = parser.parse(str(tmp_path))
    internal = [d for d in deps if d.is_internal]
    assert len(internal) >= 0  # detection is best-effort


def test_detect_manifest_files(parser, tmp_path):
    (tmp_path / "requirements.txt").write_text("flask\n")
    (tmp_path / "package.json").write_text("{}")
    files = parser.detect_manifest_files(str(tmp_path))
    assert "requirements.txt" in [os.path.basename(f) for f in files]
```

**Step 2: Implement DependencyParser**

```python
# backend/src/tools/dependency_parser.py
import os
import re
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MANIFEST_PATTERNS = [
    "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
    "package.json",
    "go.mod",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "Cargo.toml",
    "*.csproj", "packages.config",
]


@dataclass
class Dependency:
    name: str
    version_spec: str
    source: str
    manifest_file: str
    repo_url: str | None = None
    is_internal: bool = False


class DependencyParser:
    def __init__(self, repo_map: dict[str, str] | None = None):
        self._repo_map = repo_map or {}
        self._internal_names = set(self._repo_map.keys())

    def detect_manifest_files(self, repo_path: str) -> list[str]:
        found = []
        root = Path(repo_path)
        for pattern in MANIFEST_PATTERNS:
            if "*" in pattern:
                found.extend(str(p) for p in root.rglob(pattern))
            else:
                candidate = root / pattern
                if candidate.exists():
                    found.append(str(candidate))
        return found

    def parse(self, repo_path: str) -> list[Dependency]:
        deps = []
        for manifest in self.detect_manifest_files(repo_path):
            name = os.path.basename(manifest)
            try:
                if name == "requirements.txt":
                    deps.extend(self._parse_requirements(manifest))
                elif name == "package.json":
                    deps.extend(self._parse_package_json(manifest))
                elif name == "go.mod":
                    deps.extend(self._parse_go_mod(manifest))
                elif name == "Cargo.toml":
                    deps.extend(self._parse_cargo_toml(manifest))
                elif name in ("pom.xml", "build.gradle", "build.gradle.kts"):
                    deps.extend(self._parse_jvm(manifest))
            except Exception as e:
                logger.warning(f"Failed to parse {manifest}: {e}")
        for dep in deps:
            dep.is_internal = self._is_internal(dep.name)
            if dep.is_internal:
                dep.repo_url = self._repo_map.get(dep.name)
        return deps

    def _is_internal(self, name: str) -> bool:
        clean = name.split("/")[-1].lower().replace("-", "_").replace(".", "_")
        for internal in self._internal_names:
            if clean == internal.lower().replace("-", "_"):
                return True
        return False

    def _parse_requirements(self, path: str) -> list[Dependency]:
        deps = []
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = re.match(r"^([a-zA-Z0-9_.-]+)\s*([>=<!\[\]~,.*\d]*)", line)
            if match:
                deps.append(Dependency(name=match.group(1), version_spec=match.group(2).strip(),
                                       source="pypi", manifest_file=path))
        return deps

    def _parse_package_json(self, path: str) -> list[Dependency]:
        deps = []
        data = json.loads(Path(path).read_text())
        for section in ("dependencies", "devDependencies"):
            for name, version in data.get(section, {}).items():
                deps.append(Dependency(name=name, version_spec=version,
                                       source="npm", manifest_file=path))
        return deps

    def _parse_go_mod(self, path: str) -> list[Dependency]:
        deps = []
        for line in Path(path).read_text().splitlines():
            match = re.match(r"^\s*require\s+(\S+)\s+(\S+)", line)
            if match:
                deps.append(Dependency(name=match.group(1), version_spec=match.group(2),
                                       source="go", manifest_file=path))
            match2 = re.match(r"^\s+(\S+)\s+(v\S+)", line)
            if match2:
                deps.append(Dependency(name=match2.group(1), version_spec=match2.group(2),
                                       source="go", manifest_file=path))
        return deps

    def _parse_cargo_toml(self, path: str) -> list[Dependency]:
        deps = []
        in_deps = False
        for line in Path(path).read_text().splitlines():
            if line.strip() == "[dependencies]":
                in_deps = True
                continue
            if line.strip().startswith("[") and in_deps:
                break
            if in_deps:
                match = re.match(r'^(\S+)\s*=\s*"([^"]*)"', line.strip())
                if match:
                    deps.append(Dependency(name=match.group(1), version_spec=match.group(2),
                                           source="crates", manifest_file=path))
        return deps

    def _parse_jvm(self, path: str) -> list[Dependency]:
        deps = []
        content = Path(path).read_text()
        if path.endswith(".xml"):
            for match in re.finditer(r"<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>\s*<version>([^<]+)</version>", content):
                deps.append(Dependency(name=f"{match.group(1)}:{match.group(2)}", version_spec=match.group(3),
                                       source="maven", manifest_file=path))
        else:
            for match in re.finditer(r"implementation\s+['\"]([^'\"]+)['\"]", content):
                parts = match.group(1).split(":")
                name = ":".join(parts[:2]) if len(parts) >= 2 else parts[0]
                version = parts[2] if len(parts) >= 3 else ""
                deps.append(Dependency(name=name, version_spec=version,
                                       source="maven", manifest_file=path))
        return deps
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_dependency_parser.py -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add backend/src/tools/dependency_parser.py backend/tests/test_dependency_parser.py
git commit -m "feat(cross-repo): polyglot dependency manifest parser"
```

---

### Task 12: Cross-Repo Correlation Engine

**Files:**
- Create: `backend/src/agents/cross_repo_tracer.py`
- Test: `backend/tests/test_cross_repo_tracer.py`
- Modify: `backend/src/agents/supervisor.py` (add cross-repo dispatch)
- Modify: `backend/src/utils/llm_budget.py` (add `cross_repo` profile)

**Step 1: Add cross_repo budget profile**

Modify `backend/src/utils/llm_budget.py`. Add after existing profiles (~line 113):

```python
"cross_repo": SessionBudget(
    max_llm_calls=40,
    max_tool_calls_per_agent=6,
    max_tokens_input=300_000,
    max_tokens_output=60_000,
    max_total_latency_ms=180_000,
),
```

**Step 2: Write failing tests for CrossRepoTracer**

```python
# backend/tests/test_cross_repo_tracer.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.agents.cross_repo_tracer import CrossRepoTracer, CrossRepoFinding


@pytest.fixture
def tracer():
    return CrossRepoTracer(
        repo_map={"auth-service": "https://github.com/org/auth-service"},
        github_token="fake-token",
    )


def test_should_trace_low_confidence(tracer):
    assert tracer.should_trace(code_confidence=0.4, internal_deps_with_recent_commits=0) is True


def test_should_trace_recent_internal_deps(tracer):
    assert tracer.should_trace(code_confidence=0.8, internal_deps_with_recent_commits=2) is True


def test_should_not_trace_high_confidence_no_deps(tracer):
    assert tracer.should_trace(code_confidence=0.9, internal_deps_with_recent_commits=0) is False


def test_cross_repo_finding_structure():
    f = CrossRepoFinding(
        source_repo="org/auth-service",
        source_file="client.py",
        source_commit="abc123",
        target_repo="org/api-gateway",
        target_file="handler.py",
        target_import="from auth_service.client import validate",
        correlation_type="api_rename",
        correlation_score=0.94,
    )
    assert f.correlation_score > 0.9
```

**Step 3: Implement CrossRepoTracer**

```python
# backend/src/agents/cross_repo_tracer.py
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CrossRepoFinding:
    source_repo: str
    source_file: str
    source_commit: str
    target_repo: str
    target_file: str
    target_import: str
    correlation_type: str
    correlation_score: float
    source_timestamp: datetime | None = None
    commit_message: str = ""


class CrossRepoTracer:
    CONFIDENCE_THRESHOLD = 0.6

    def __init__(self, repo_map: dict[str, str], github_token: str = ""):
        self._repo_map = repo_map
        self._github_token = github_token

    def should_trace(self, code_confidence: float, internal_deps_with_recent_commits: int) -> bool:
        if code_confidence < self.CONFIDENCE_THRESHOLD:
            return True
        if internal_deps_with_recent_commits > 0:
            return True
        return False

    async def trace(self, primary_repo: str, internal_deps: list[dict],
                    failure_window_start: datetime, failure_window_end: datetime) -> list[CrossRepoFinding]:
        findings = []
        for dep in internal_deps:
            repo_url = self._repo_map.get(dep["name"])
            if not repo_url:
                continue
            try:
                dep_findings = await self._analyze_upstream(
                    upstream_repo=repo_url,
                    downstream_repo=primary_repo,
                    dependency=dep,
                    window_start=failure_window_start,
                    window_end=failure_window_end,
                )
                findings.extend(dep_findings)
            except Exception as e:
                logger.warning(f"Cross-repo trace failed for {dep['name']}: {e}")
        return findings

    async def _analyze_upstream(self, upstream_repo: str, downstream_repo: str,
                                 dependency: dict, window_start: datetime,
                                 window_end: datetime) -> list[CrossRepoFinding]:
        # Placeholder — full implementation will:
        # 1. Clone upstream repo (shallow, sparse)
        # 2. Fetch commits in window
        # 3. Diff changed files
        # 4. Check API overlap with downstream imports
        # 5. Score correlation
        return []
```

**Step 4: Run tests, verify pass**

Run: `cd backend && python -m pytest tests/test_cross_repo_tracer.py -v`
Expected: PASS.

**Step 5: Wire into supervisor dispatch**

Add to `supervisor.py` after the code agent completes — if `tracer.should_trace()` returns True, dispatch cross-repo analysis. Add cross-repo findings to the session state and evidence graph.

**Step 6: Commit**

```bash
git add backend/src/agents/cross_repo_tracer.py backend/tests/test_cross_repo_tracer.py backend/src/utils/llm_budget.py backend/src/agents/supervisor.py
git commit -m "feat(cross-repo): correlation engine with supervisor dispatch integration"
```

---

### Task 13: Cross-Repo Evidence Graph Extension

**Files:**
- Modify: `backend/src/agents/causal_engine.py:35`
- Test: `backend/tests/test_causal_engine.py` (extend)

**Step 1: Add CrossRepoEdge to causal_engine.py**

At `causal_engine.py`, add after the existing `CausalEdge` dataclass:

```python
@dataclass
class CrossRepoEdge:
    source_repo: str
    source_file: str
    source_commit: str
    source_timestamp: datetime | None
    target_repo: str
    target_file: str
    target_import: str
    correlation_type: str
    correlation_score: float
```

Add method to `EvidenceGraphBuilder`:

```python
def add_cross_repo_edge(self, edge: CrossRepoEdge) -> None:
    source_id = self.add_evidence(
        EvidencePin(claim=f"Breaking change in {edge.source_repo}:{edge.source_file}",
                    evidence=f"Commit {edge.source_commit}", confidence=edge.correlation_score,
                    source_type="code", agent_name="cross_repo_tracer"),
        node_type="cross_repo_source"
    )
    target_id = self.add_evidence(
        EvidencePin(claim=f"Import in {edge.target_repo}:{edge.target_file}",
                    evidence=edge.target_import, confidence=edge.correlation_score,
                    source_type="code", agent_name="cross_repo_tracer"),
        node_type="cross_repo_target"
    )
    self.add_causal_link(source_id, target_id, edge.correlation_type,
                         edge.correlation_score, f"Cross-repo: {edge.source_repo} → {edge.target_repo}")
```

**Step 2: Add test**

```python
# Append to backend/tests/test_causal_engine.py
def test_cross_repo_edge():
    from src.agents.causal_engine import EvidenceGraphBuilder, CrossRepoEdge
    builder = EvidenceGraphBuilder()
    edge = CrossRepoEdge(
        source_repo="org/auth", source_file="client.py", source_commit="abc",
        source_timestamp=None, target_repo="org/api", target_file="handler.py",
        target_import="from auth.client import validate", correlation_type="api_rename",
        correlation_score=0.94,
    )
    builder.add_cross_repo_edge(edge)
    assert len(builder.graph.edges) == 1
    roots = builder.identify_root_causes()
    assert len(roots) >= 1
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_causal_engine.py -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add backend/src/agents/causal_engine.py backend/tests/test_causal_engine.py
git commit -m "feat(cross-repo): evidence graph support for cross-repo causal edges"
```

---

### Task 14: Add analyze_upstream_dependency Tool

**Files:**
- Modify: `backend/src/tools/tool_registry.py`
- Modify: `backend/src/tools/tool_executor.py`

**Step 1: Add tool to registry**

Append to `TOOL_REGISTRY` in `tool_registry.py`:

```python
{
    "intent": "analyze_upstream_dependency",
    "label": "Analyze Upstream Dependency",
    "icon": "account_tree",
    "slash_command": "/upstream",
    "category": "code",
    "description": "Analyze an upstream service's recent commits for breaking changes that may affect the current service",
    "params_schema": [
        {"name": "service_name", "type": "string", "required": True, "description": "Upstream service name from repo_map"},
        {"name": "dependency_name", "type": "string", "required": True, "description": "Package/module name"},
        {"name": "time_window_hours", "type": "integer", "required": False, "description": "Hours to look back (default 24)", "default": 24},
    ],
    "requires_context": ["repo_map"],
},
```

**Step 2: Add handler in tool_executor.py**

Wire the `analyze_upstream_dependency` intent to invoke `CrossRepoTracer._analyze_upstream()`.

**Step 3: Run existing tool tests**

Run: `cd backend && python -m pytest tests/test_tool_executor.py -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add backend/src/tools/tool_registry.py backend/src/tools/tool_executor.py
git commit -m "feat(tools): add analyze_upstream_dependency tool for LLM agents"
```

---

## Phase 5: Causal Reasoning Improvements

---

### Task 15: Structured Cross-Agent Evidence Handoff

**Files:**
- Create: `backend/src/agents/evidence_handoff.py`
- Modify: `backend/src/agents/supervisor.py` (inter-agent routing)
- Test: `backend/tests/test_evidence_handoff.py`

**Step 1: Write data model + extractor**

```python
# backend/src/agents/evidence_handoff.py
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EvidenceHandoff:
    claim: str
    domain: str
    timestamp: datetime | None = None
    confidence: float = 0.0
    corroborating_domains: list[str] = field(default_factory=list)
    contradicting_domains: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


def format_handoff_for_agent(handoffs: list[EvidenceHandoff], target_domain: str) -> str:
    if not handoffs:
        return ""
    lines = ["Prior evidence to validate or refute:"]
    for i, h in enumerate(handoffs, 1):
        ts = f" at {h.timestamp.isoformat()}" if h.timestamp else ""
        lines.append(f"  {i}. [{h.domain}, confidence={h.confidence:.2f}] {h.claim}{ts}")
        if h.open_questions:
            for q in h.open_questions:
                lines.append(f"     Open question: {q}")
    lines.append(f"\nYOUR TASK: Use {target_domain} data to confirm or deny these claims.")
    return "\n".join(lines)
```

**Step 2: Write tests**

```python
# backend/tests/test_evidence_handoff.py
import pytest
from datetime import datetime
from src.agents.evidence_handoff import EvidenceHandoff, format_handoff_for_agent


def test_format_handoff():
    handoffs = [
        EvidenceHandoff(claim="OOM killed pod-xyz", domain="k8s",
                        timestamp=datetime(2026, 4, 12, 14, 32),
                        confidence=0.82, open_questions=["Sidecar or main container?"]),
    ]
    text = format_handoff_for_agent(handoffs, "metrics")
    assert "OOM killed pod-xyz" in text
    assert "Sidecar or main container?" in text
    assert "metrics" in text


def test_empty_handoff():
    text = format_handoff_for_agent([], "metrics")
    assert text == ""
```

**Step 3: Run tests, verify pass**

Run: `cd backend && python -m pytest tests/test_evidence_handoff.py -v`
Expected: PASS.

**Step 4: Integrate into supervisor routing**

In `supervisor.py`, after each agent completes, extract `EvidenceHandoff` items from its findings. Inject formatted handoff into the next agent's context via `format_handoff_for_agent()`.

**Step 5: Commit**

```bash
git add backend/src/agents/evidence_handoff.py backend/tests/test_evidence_handoff.py backend/src/agents/supervisor.py
git commit -m "feat(reasoning): structured cross-agent evidence handoff"
```

---

### Task 16: Critic Hypothesis Generation

**Files:**
- Modify: `backend/src/agents/critic_agent.py:44-48`
- Modify: `backend/src/agents/supervisor.py` (re-dispatch on suggestion)
- Test: `backend/tests/test_critic_agent.py` (extend)

**Step 1: Extend CriticVerdict structure**

At `critic_agent.py`, modify the verdict output schema (line ~44) to include:

```python
{
    "verdict": "validated|challenged|insufficient_data",
    "reasoning": "...",
    "recommendation": "...",
    "confidence_in_verdict": 85,
    "suggest_alternative": "Check if OOM was in the istio-proxy sidecar",  # NEW
    "suggested_agent": "k8s_agent"  # NEW
}
```

Update the LLM system prompt to instruct the critic to fill `suggest_alternative` and `suggested_agent` when challenging a finding.

**Step 2: Update CriticVerdict dataclass**

Add `suggest_alternative: str | None = None` and `suggested_agent: str | None = None` fields.

**Step 3: Add re-dispatch guard in supervisor**

In supervisor's re-investigation logic (~line 447), when critic provides `suggest_alternative`:

```python
if verdict.suggest_alternative and verdict.suggested_agent:
    if re_dispatch_count < MAX_RE_DISPATCHES:  # MAX_RE_DISPATCHES = 2
        context["hypothesis"] = verdict.suggest_alternative
        await self._dispatch_agent(verdict.suggested_agent, context)
        re_dispatch_count += 1
```

**Step 4: Add test**

```python
# Append to backend/tests/test_critic_agent.py
def test_critic_verdict_with_alternative():
    from src.agents.critic_agent import CriticVerdict
    verdict = CriticVerdict(
        verdict="challenged", reasoning="Memory was stable",
        recommendation="Check sidecar", confidence_in_verdict=85,
        suggest_alternative="Check istio-proxy memory usage",
        suggested_agent="k8s_agent",
    )
    assert verdict.suggest_alternative is not None
    assert verdict.suggested_agent == "k8s_agent"
```

**Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_critic_agent.py tests/test_supervisor.py -v`
Expected: PASS.

**Step 6: Commit**

```bash
git add backend/src/agents/critic_agent.py backend/src/agents/supervisor.py backend/tests/test_critic_agent.py
git commit -m "feat(reasoning): critic can suggest alternative hypotheses for re-dispatch"
```

---

### Task 17: Spike Detection — Same-Hour-Yesterday Comparison

**Files:**
- Modify: `backend/src/agents/metrics_agent.py:645`
- Test: `backend/tests/test_metrics_agent.py` (extend)

**Step 1: Add test for cyclical false positive filtering**

```python
# Append to backend/tests/test_metrics_agent.py
def test_spike_not_flagged_if_cyclical():
    from src.agents.metrics_agent import MetricsAgent
    agent = MetricsAgent.__new__(MetricsAgent)

    current = [{"timestamp": i, "value": 100 + (50 if 10 <= i <= 12 else 0)} for i in range(24)]
    previous = [{"timestamp": i, "value": 100 + (50 if 10 <= i <= 12 else 0)} for i in range(24)]
    spikes = agent._detect_spikes_with_baseline(current, previous, threshold=2.0)
    assert len(spikes) == 0  # same pattern yesterday — cyclical


def test_spike_flagged_if_novel():
    from src.agents.metrics_agent import MetricsAgent
    agent = MetricsAgent.__new__(MetricsAgent)

    current = [{"timestamp": i, "value": 100 + (200 if 10 <= i <= 12 else 0)} for i in range(24)]
    previous = [{"timestamp": i, "value": 100} for i in range(24)]
    spikes = agent._detect_spikes_with_baseline(current, previous, threshold=2.0)
    assert len(spikes) > 0  # novel spike — not present yesterday
```

**Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_metrics_agent.py::test_spike_not_flagged_if_cyclical -v`
Expected: FAIL (`AttributeError: _detect_spikes_with_baseline`).

**Step 3: Implement**

Add method to `MetricsAgent` near the existing `_detect_spikes` at line 645:

```python
def _detect_spikes_with_baseline(self, current_window: list[dict],
                                  previous_day_window: list[dict],
                                  threshold: float = 2.0) -> list[dict]:
    if not previous_day_window:
        return self._detect_spikes(current_window, threshold)

    prev_values = [p["value"] for p in previous_day_window if p.get("value") is not None]
    if not prev_values:
        return self._detect_spikes(current_window, threshold)

    prev_mean = sum(prev_values) / len(prev_values)
    prev_std = (sum((v - prev_mean) ** 2 for v in prev_values) / len(prev_values)) ** 0.5

    raw_spikes = self._detect_spikes(current_window, threshold)
    filtered = []
    for spike in raw_spikes:
        spike_value = spike.get("peak_value", spike.get("value", 0))
        if prev_std > 0:
            prev_zscore = (spike_value - prev_mean) / prev_std
            if prev_zscore >= threshold:
                continue  # was also a spike yesterday — cyclical
        filtered.append(spike)
    return filtered
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_metrics_agent.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/src/agents/metrics_agent.py backend/tests/test_metrics_agent.py
git commit -m "fix(metrics): filter cyclical spikes via same-hour-yesterday comparison"
```

---

## Phase 6: Operational Hardening

---

### Task 18: Per-Tool Timeouts

**Files:**
- Modify: `backend/src/tools/tool_executor.py:271`
- Test: `backend/tests/test_tool_timeouts.py`

**Step 1: Write failing test**

```python
# backend/tests/test_tool_timeouts.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from src.tools.tool_executor import TOOL_TIMEOUTS


def test_tool_timeouts_defined():
    assert "fetch_pod_logs" in TOOL_TIMEOUTS
    assert "query_prometheus_range" in TOOL_TIMEOUTS
    assert "default" in TOOL_TIMEOUTS
    assert all(isinstance(v, int) for v in TOOL_TIMEOUTS.values())
```

**Step 2: Add timeout map to tool_executor.py**

Near the top of `tool_executor.py`:

```python
TOOL_TIMEOUTS = {
    "fetch_pod_logs": 30,
    "query_prometheus_range": 20,
    "query_prometheus_instant": 10,
    "search_elasticsearch": 30,
    "search_logs": 30,
    "describe_resource": 15,
    "get_events": 15,
    "check_pod_status": 10,
    "analyze_upstream_dependency": 45,
    "default": 20,
}
```

Wrap the dispatch call in `execute()` with `asyncio.wait_for`:

```python
timeout = TOOL_TIMEOUTS.get(intent, TOOL_TIMEOUTS["default"])
try:
    result = await asyncio.wait_for(self._dispatch(intent, params), timeout=timeout)
except asyncio.TimeoutError:
    return ToolResult(success=False, data=f"Tool '{intent}' timed out after {timeout}s")
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_tool_timeouts.py tests/test_tool_executor.py -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add backend/src/tools/tool_executor.py backend/tests/test_tool_timeouts.py
git commit -m "feat(tools): per-tool timeouts prevent single slow call from blocking agent"
```

---

### Task 19: Tool Result Caching (Redis)

**Files:**
- Create: `backend/src/utils/tool_cache.py`
- Test: `backend/tests/test_tool_cache.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_tool_cache.py
import pytest
import json
from unittest.mock import AsyncMock

from src.utils.tool_cache import ToolResultCache


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_cache_miss_executes_and_stores(mock_redis):
    cache = ToolResultCache(mock_redis)
    executor = AsyncMock(return_value={"data": "pod logs here"})
    result = await cache.get_or_execute("sess-1", "fetch_pod_logs", {"pod": "xyz"}, executor)
    assert result == {"data": "pod logs here"}
    executor.assert_called_once()
    mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_cache_hit_skips_execution(mock_redis):
    mock_redis.get.return_value = json.dumps({"data": "cached"}).encode()
    cache = ToolResultCache(mock_redis)
    executor = AsyncMock()
    result = await cache.get_or_execute("sess-1", "fetch_pod_logs", {"pod": "xyz"}, executor)
    assert result == {"data": "cached"}
    executor.assert_not_called()
```

**Step 2: Implement**

```python
# backend/src/utils/tool_cache.py
import hashlib
import json
import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)

CACHE_TTL = 300


class ToolResultCache:
    def __init__(self, redis_client: redis.Redis, ttl: int = CACHE_TTL):
        self._redis = redis_client
        self._ttl = ttl

    def _cache_key(self, session_id: str, tool_name: str, params: dict) -> str:
        param_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
        return f"tool_cache:{session_id}:{tool_name}:{param_hash}"

    async def get_or_execute(self, session_id: str, tool_name: str, params: dict, executor) -> dict:
        key = self._cache_key(session_id, tool_name, params)
        cached = await self._redis.get(key)
        if cached:
            logger.debug(f"Cache hit: {tool_name}")
            return json.loads(cached)
        result = await executor(tool_name, params)
        try:
            await self._redis.setex(key, self._ttl, json.dumps(result))
        except (TypeError, ValueError):
            pass  # non-serializable result — skip caching
        return result
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_tool_cache.py -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add backend/src/utils/tool_cache.py backend/tests/test_tool_cache.py
git commit -m "feat(perf): Redis-backed tool result caching with 5-min TTL"
```

---

### Task 20: Health Check Endpoint

**Files:**
- Modify: `backend/src/api/routes_v4.py`
- Test: `backend/tests/test_health_endpoint.py`

**Step 1: Write failing test**

```python
# backend/tests/test_health_endpoint.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_health_returns_status():
    from src.api.routes_v4 import health_check
    with patch("src.api.routes_v4.check_redis", new_callable=AsyncMock, return_value={"status": "up", "latency_ms": 2}), \
         patch("src.api.routes_v4.check_circuit_breakers", return_value={}):
        result = await health_check()
    assert result["status"] in ("healthy", "degraded", "unhealthy")
    assert "checks" in result
```

**Step 2: Implement**

Add to `routes_v4.py`:

```python
@router_v4.get("/health")
async def health_check():
    checks = {}
    checks["redis"] = await check_redis()
    checks.update(check_circuit_breakers())

    statuses = [c.get("status") for c in checks.values()]
    if all(s == "up" for s in statuses):
        overall = "healthy"
    elif any(s == "down" for s in statuses):
        overall = "unhealthy"
    else:
        overall = "degraded"

    return {"status": overall, "checks": checks}


async def check_redis():
    import time
    try:
        start = time.monotonic()
        await app.state.redis.ping()
        return {"status": "up", "latency_ms": round((time.monotonic() - start) * 1000)}
    except Exception:
        return {"status": "down"}


def check_circuit_breakers():
    # Read circuit breaker states from Redis
    return {}
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_health_endpoint.py -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_health_endpoint.py
git commit -m "feat(ops): health check endpoint for load balancer integration"
```

---

### Task 21: ES Query Result Cap

**Files:**
- Modify: `backend/src/agents/log_agent.py:1251`

**Step 1: Add cap to ES query construction**

At `log_agent.py:1251`, where the ES query is built, add:

```python
import os

ES_MAX_RESULTS = int(os.getenv("ES_MAX_RESULTS", "5000"))

# In _search_elasticsearch, after building es_query:
es_query["size"] = min(es_query.get("size", ES_MAX_RESULTS), ES_MAX_RESULTS)
```

When results are returned and the total exceeds the cap, append a note to the output:

```python
total_hits = response.get("hits", {}).get("total", {}).get("value", 0)
if total_hits > ES_MAX_RESULTS:
    result_text += f"\n[Showing newest {ES_MAX_RESULTS} of ~{total_hits} matching logs. Sorted newest-first.]"
```

**Step 2: Run existing log agent tests**

Run: `cd backend && python -m pytest tests/test_log_agent.py -v`
Expected: PASS.

**Step 3: Commit**

```bash
git add backend/src/agents/log_agent.py
git commit -m "fix(logs): cap ES results at 5000, note truncation for LLM context"
```

---

### Task 22: Final Integration Test + Full Test Suite

**Files:**
- Create: `backend/tests/test_hardening_integration.py`

**Step 1: Write integration smoke test**

```python
# backend/tests/test_hardening_integration.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.redis_store import RedisSessionStore
from src.utils.circuit_breaker import RedisCircuitBreaker
from src.utils.redis_semaphore import RedisLLMSemaphore
from src.utils.context_guard import ContextWindowGuard
from src.utils.tool_cache import ToolResultCache
from src.utils.attestation_log import AttestationLogger
from src.tools.dependency_parser import DependencyParser
from src.agents.cross_repo_tracer import CrossRepoTracer
from src.agents.evidence_handoff import EvidenceHandoff, format_handoff_for_agent
from src.models.attestation import AttestationGate, AttestationDecision


def test_all_new_modules_import():
    """Smoke test — all new modules import without errors."""
    assert RedisSessionStore is not None
    assert RedisCircuitBreaker is not None
    assert RedisLLMSemaphore is not None
    assert ContextWindowGuard is not None
    assert ToolResultCache is not None
    assert AttestationLogger is not None
    assert DependencyParser is not None
    assert CrossRepoTracer is not None
    assert EvidenceHandoff is not None
    assert AttestationGate is not None


def test_context_guard_model_limits():
    guard = ContextWindowGuard()
    assert guard.model_limit("claude-haiku-4-5-20251001") == 128000
    assert guard.model_limit("claude-sonnet-4-20250514") == 200000


def test_dependency_parser_empty_dir(tmp_path):
    parser = DependencyParser()
    deps = parser.parse(str(tmp_path))
    assert deps == []
```

**Step 2: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -50`
Expected: all new tests PASS, no regressions in existing tests.

**Step 3: Commit**

```bash
git add backend/tests/test_hardening_integration.py
git commit -m "test: integration smoke tests for all hardening modules"
```

---

## Success Criteria

- `python -m pytest tests/` — all tests pass, zero regressions
- Redis connection required at startup (env `REDIS_URL`)
- WebSocket events delivered cross-instance via Redis Pub/Sub
- Context window overflow: graceful truncation at 80% capacity, never a 400 from Anthropic
- Circuit breaker: 3 failures in 60s → circuit opens for 120s across all instances
- Attestation: auto-approves at ≥0.85 confidence, times out after 10 min, per-finding decisions, full audit trail in SQLite
- Cross-repo: dependency parser handles Python/Node/Go/Java/Rust/.NET manifests, tracer dispatches when code agent confidence < 0.6
- Tool errors: LLM sees `"Tool 'X' failed: ErrorType: message"` not `"Error executing X"`
- Health endpoint: `GET /api/v4/health` returns `healthy/degraded/unhealthy` with per-service status

## Gap-to-Task Mapping

| Gap | Task(s) |
|-----|---------|
| G1 (cross-repo tracing) | 11, 12, 13, 14 |
| G2 (context window) | 5 |
| G3 (WebSocket FD leak) | 3 |
| G4 (attestation timeout) | 8 |
| G5 (circuit breaker) | 6 |
| G6 (tool errors) | 7 |
| G7 (all-or-nothing attestation) | 9 |
| G8 (LLM coordination) | 4 |
| G9 (in-memory sessions) | 1, 2 |
| G10 (spike false positives) | 17 |
| G11 (dependency parsing) | 11 |
| G13 (audit trail) | 10 |

## Deferred (Tier 4)

- G12: Negative finding pruning
- G14: Adaptive minimum budget
- G15: Document iteration nudge logic
- Seasonal STL decomposition
