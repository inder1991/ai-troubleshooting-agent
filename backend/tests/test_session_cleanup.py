"""Tests for session cleanup loop: router cleanup (B2) and critic task cancellation (B3)."""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from src.api.routes_v4 import (
    _session_cleanup_loop,
    sessions,
    supervisors,
    session_locks,
    _investigation_routers,
    _critic_delta_tasks,
    _diagnosis_tasks,
    SESSION_TTL_HOURS,
    SESSION_CLEANUP_INTERVAL_SECONDS,
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


def _make_expired_session(sid: str) -> None:
    """Insert a session that is older than SESSION_TTL_HOURS into the sessions dict."""
    expired_time = (
        datetime.now(timezone.utc) - timedelta(hours=SESSION_TTL_HOURS + 1)
    ).isoformat()
    sessions[sid] = {"created_at": expired_time}
    session_locks[sid] = asyncio.Lock()


def _make_live_session(sid: str) -> None:
    """Insert a session that is still within the TTL window."""
    live_time = datetime.now(timezone.utc).isoformat()
    sessions[sid] = {"created_at": live_time}
    session_locks[sid] = asyncio.Lock()


@pytest.mark.asyncio
async def test_router_cleaned_on_session_expiry():
    """B2: _investigation_routers entry is removed when session expires."""
    sid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    _make_expired_session(sid)

    # Plant a mock investigation router for this session
    mock_router = MagicMock()
    _investigation_routers[sid] = mock_router

    # Also plant a live session to make sure it is NOT cleaned up
    live_sid = "11111111-2222-4333-8444-555555555555"
    _make_live_session(live_sid)
    live_router = MagicMock()
    _investigation_routers[live_sid] = live_router

    # Patch asyncio.sleep to break out of the infinite loop after one iteration
    call_count = 0

    async def _fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise asyncio.CancelledError()

    # Patch manager.disconnect so it doesn't try real WebSocket ops
    with patch("src.api.routes_v4.asyncio.sleep", side_effect=_fake_sleep), \
         patch("src.api.routes_v4.manager") as mock_manager:
        mock_manager.disconnect = MagicMock()
        try:
            await _session_cleanup_loop()
        except asyncio.CancelledError:
            pass

    # Expired session's router should be removed
    assert sid not in _investigation_routers
    assert sid not in sessions

    # Live session's router should remain
    assert live_sid in _investigation_routers
    assert _investigation_routers[live_sid] is live_router
    assert live_sid in sessions


@pytest.mark.asyncio
async def test_critic_tasks_cancelled_on_cleanup():
    """B3: All critic delta tasks for a session are cancelled when it expires."""
    sid = "cccccccc-dddd-4eee-8fff-000000000000"
    _make_expired_session(sid)

    # Create mock asyncio.Task objects that look like running critic tasks
    task1 = MagicMock(spec=asyncio.Task)
    task1.done.return_value = False
    task1.cancel = MagicMock()

    task2 = MagicMock(spec=asyncio.Task)
    task2.done.return_value = False
    task2.cancel = MagicMock()

    # One already-done task that should NOT be cancelled
    task3_done = MagicMock(spec=asyncio.Task)
    task3_done.done.return_value = True
    task3_done.cancel = MagicMock()

    _critic_delta_tasks[sid] = [task1, task2, task3_done]

    call_count = 0

    async def _fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise asyncio.CancelledError()

    with patch("src.api.routes_v4.asyncio.sleep", side_effect=_fake_sleep), \
         patch("src.api.routes_v4.manager") as mock_manager:
        mock_manager.disconnect = MagicMock()
        try:
            await _session_cleanup_loop()
        except asyncio.CancelledError:
            pass

    # Running tasks should have been cancelled
    task1.cancel.assert_called_once()
    task2.cancel.assert_called_once()

    # Already-done task should NOT be cancelled
    task3_done.cancel.assert_not_called()

    # Session's critic task list should be removed from the dict
    assert sid not in _critic_delta_tasks


@pytest.mark.asyncio
async def test_cleanup_handles_session_without_critic_tasks():
    """B3: Cleanup does not crash when a session has no critic tasks entry."""
    sid = "dddddddd-eeee-4fff-8000-111111111111"
    _make_expired_session(sid)
    # Deliberately do NOT add anything to _critic_delta_tasks for this session

    call_count = 0

    async def _fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise asyncio.CancelledError()

    with patch("src.api.routes_v4.asyncio.sleep", side_effect=_fake_sleep), \
         patch("src.api.routes_v4.manager") as mock_manager:
        mock_manager.disconnect = MagicMock()
        try:
            await _session_cleanup_loop()
        except asyncio.CancelledError:
            pass

    # Session should still be cleaned up without error
    assert sid not in sessions
    assert sid not in _critic_delta_tasks


@pytest.mark.asyncio
async def test_cleanup_handles_session_without_router():
    """B2: Cleanup does not crash when a session has no router entry."""
    sid = "eeeeeeee-ffff-4000-8111-222222222222"
    _make_expired_session(sid)
    # Deliberately do NOT add anything to _investigation_routers for this session

    call_count = 0

    async def _fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise asyncio.CancelledError()

    with patch("src.api.routes_v4.asyncio.sleep", side_effect=_fake_sleep), \
         patch("src.api.routes_v4.manager") as mock_manager:
        mock_manager.disconnect = MagicMock()
        try:
            await _session_cleanup_loop()
        except asyncio.CancelledError:
            pass

    # Session should still be cleaned up without error
    assert sid not in sessions
    assert sid not in _investigation_routers
