"""Tests for session lifecycle: delete_session resource cleanup and lock helpers.

Note: The old _session_cleanup_loop tests have been removed because session
TTL is now managed by Redis expiry (RedisSessionStore).  In-memory cleanup
only happens on explicit delete_session calls.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.routes_v4 import (
    sessions,
    supervisors,
    session_locks,
    _investigation_routers,
    _critic_delta_tasks,
    _diagnosis_tasks,
    SESSION_TTL_HOURS,
    _acquire_lock,
)


@pytest.fixture(autouse=True)
def _clear_module_state():
    """Reset all module-level dicts before and after each test."""
    sessions.clear()
    supervisors.clear()
    session_locks.clear()
    _investigation_routers.clear()
    _critic_delta_tasks.clear()
    _diagnosis_tasks.clear()
    yield
    sessions.clear()
    supervisors.clear()
    session_locks.clear()
    _investigation_routers.clear()
    _critic_delta_tasks.clear()
    _diagnosis_tasks.clear()


def test_acquire_lock_fallback_returns_asyncio_lock():
    """_acquire_lock returns an asyncio.Lock when Redis session store is unavailable."""
    sid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    with patch("src.api.routes_v4._get_session_store", return_value=None):
        lock = _acquire_lock(sid)
    assert isinstance(lock, asyncio.Lock)
    # Same lock returned on second call (setdefault semantics)
    with patch("src.api.routes_v4._get_session_store", return_value=None):
        lock2 = _acquire_lock(sid)
    assert lock is lock2


@pytest.mark.asyncio
async def test_delete_session_cleans_all_resources():
    """delete_session must clean up critic tasks, investigation router, topology cache, SSE, store."""
    from src.api.routes_v4 import (
        sessions, session_locks, _diagnosis_tasks, _critic_delta_tasks,
        _investigation_routers, delete_session,
    )

    sid = "12345678-1234-4234-8234-123456789abc"

    # Set up all resources
    sessions[sid] = {"service_name": "test", "phase": "done", "confidence": 0, "created_at": "2026-01-01T00:00:00Z"}
    session_locks[sid] = asyncio.Lock()
    mock_task = MagicMock()
    mock_task.done.return_value = False
    mock_task.cancel = MagicMock()
    _critic_delta_tasks[sid] = [mock_task]
    _investigation_routers[sid] = MagicMock()

    # Create a mock store module to handle the lazy import inside delete_session
    mock_store_mod = MagicMock()
    mock_store_instance = AsyncMock()
    mock_store_mod.get_store.return_value = mock_store_instance

    with patch("src.api.routes_v4.manager") as mock_manager, \
         patch("src.agents.cluster.topology_resolver.clear_topology_cache", create=True), \
         patch.dict("sys.modules", {"src.observability.store": mock_store_mod}), \
         patch("src.api.routes_v4._delete_session_redis", new_callable=AsyncMock):
        result = await delete_session(sid)

    assert result["status"] == "deleted"
    assert sid not in sessions
    assert sid not in session_locks
    assert sid not in _critic_delta_tasks
    assert sid not in _investigation_routers
    mock_task.cancel.assert_called_once()
