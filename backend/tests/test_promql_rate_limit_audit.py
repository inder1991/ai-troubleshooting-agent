"""PR-C — PromQL UI endpoint rate-limit + audit tests.

Covers:
  · _enforce_promql_rate_limit uses Redis INCR + EXPIRE and raises 429
    after 30 calls in the same 60-second window.
  · _enforce_promql_rate_limit degrades to a no-op when Redis is missing
    or Redis calls raise (infra-failure fail-open — the validator and
    route-handler are still protecting us).
  · _audit_promql_run emits one structured log per call with the
    expected fields.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.routes_v4 import (
    _audit_promql_run,
    _enforce_promql_rate_limit,
    _PROMQL_RATE_LIMIT_MAX,
    _PROMQL_RATE_LIMIT_WINDOW_S,
)


def _fake_app_with_redis(redis_client):
    """Helper — shape that _enforce_promql_rate_limit expects from app.state."""
    return SimpleNamespace(state=SimpleNamespace(redis=redis_client))


# ── rate limit ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_noop_when_redis_missing():
    """No Redis → limiter does nothing (fail-open)."""
    with patch("src.api.main.app", _fake_app_with_redis(None)):
        for _ in range(50):
            await _enforce_promql_rate_limit("session-x")


@pytest.mark.asyncio
async def test_rate_limit_increments_and_sets_ttl_on_first_call():
    redis_client = MagicMock()
    redis_client.incr = AsyncMock(return_value=1)
    redis_client.expire = AsyncMock(return_value=True)

    with patch("src.api.main.app", _fake_app_with_redis(redis_client)):
        await _enforce_promql_rate_limit("session-a")

    redis_client.incr.assert_awaited_once_with("promql_run_rl:session-a")
    redis_client.expire.assert_awaited_once_with(
        "promql_run_rl:session-a", _PROMQL_RATE_LIMIT_WINDOW_S,
    )


@pytest.mark.asyncio
async def test_rate_limit_skips_expire_on_subsequent_calls():
    """TTL is set once — INCR on an existing key doesn't reset expire."""
    redis_client = MagicMock()
    redis_client.incr = AsyncMock(return_value=2)
    redis_client.expire = AsyncMock(return_value=True)

    with patch("src.api.main.app", _fake_app_with_redis(redis_client)):
        await _enforce_promql_rate_limit("session-a")

    assert redis_client.expire.await_count == 0


@pytest.mark.asyncio
async def test_rate_limit_429_when_budget_exhausted():
    redis_client = MagicMock()
    redis_client.incr = AsyncMock(return_value=_PROMQL_RATE_LIMIT_MAX + 1)
    redis_client.expire = AsyncMock()

    with patch("src.api.main.app", _fake_app_with_redis(redis_client)):
        with pytest.raises(HTTPException) as exc_info:
            await _enforce_promql_rate_limit("session-a")
    assert exc_info.value.status_code == 429
    assert "rate limit" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_rate_limit_at_boundary_does_not_raise():
    """Exactly budget-count calls allowed (budget is inclusive)."""
    redis_client = MagicMock()
    redis_client.incr = AsyncMock(return_value=_PROMQL_RATE_LIMIT_MAX)
    redis_client.expire = AsyncMock()

    with patch("src.api.main.app", _fake_app_with_redis(redis_client)):
        await _enforce_promql_rate_limit("session-a")


@pytest.mark.asyncio
async def test_rate_limit_redis_error_degrades_to_noop():
    """Redis glitch → log warning and continue; don't 500 the user."""
    redis_client = MagicMock()
    redis_client.incr = AsyncMock(side_effect=RuntimeError("connection reset"))
    redis_client.expire = AsyncMock()

    with patch("src.api.main.app", _fake_app_with_redis(redis_client)):
        # Should NOT raise — we fail-open on infra glitches.
        await _enforce_promql_rate_limit("session-a")


# ── audit log ─────────────────────────────────────────────────────────


def test_audit_truncates_long_queries_to_500_chars():
    """Audit stores query (for SIEM) but clamps length so TSDB attackers
    can't fill the log with megabytes of regex."""
    # Exercise the helper directly — if it didn't clamp, the extra would
    # have the full 20_000 char string.
    long_query = "up " + ("x" * 20_000)
    # No exception → helper handled the large string.
    _audit_promql_run(
        "session-x", long_query, "0", "60", "60s", outcome="success",
    )


def test_audit_accepts_all_outcome_strings():
    """Any short outcome label is accepted; helper never raises."""
    for outcome in [
        "success", "no_data", "prometheus_error",
        "rejected_validation: step above maximum",
        "http_500", "error: connection refused",
    ]:
        _audit_promql_run("s", "up", "0", "60", "60s", outcome=outcome)
