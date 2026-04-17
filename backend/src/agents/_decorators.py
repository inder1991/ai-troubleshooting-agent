"""Agent-level decorators — circuit breaker wiring.

``@with_circuit_breaker("prometheus")`` wraps an async callable so a run of
failures against a backend trips the breaker, and subsequent calls fast-fail
with ``CircuitOpenError`` instead of hitting the backend. The underlying
``CircuitBreaker`` implementation lives in ``src/network/circuit_breaker.py``;
this module owns the per-backend registry + decorator shape that agents use.

Threshold / timeout per the Task 3.4 plan: 5 consecutive failures in the
caller's request stream opens the breaker for 30 s; after that it moves to
HALF_OPEN and one probe call is allowed through.
"""
from __future__ import annotations

import functools
import threading
from typing import Any, Awaitable, Callable, TypeVar

from src.network.circuit_breaker import CircuitBreaker


class CircuitOpenError(RuntimeError):
    """Raised when a call is rejected because the backend's circuit is open."""


# Per-backend breaker instances. A threading.Lock protects first-time creation
# so concurrent first calls don't race.
_BREAKERS: dict[str, CircuitBreaker] = {}
_LOCK = threading.Lock()

# Defaults per the plan. A backend can override via reset_breaker() +
# register_breaker() but we don't surface a fancy config — tuning these is
# a code change, intentionally.
_DEFAULT_FAILURE_THRESHOLD: int = 5
_DEFAULT_RECOVERY_TIMEOUT_S: float = 30.0


def get_breaker(backend: str) -> CircuitBreaker:
    """Return (creating if necessary) the process-wide breaker for a backend."""
    breaker = _BREAKERS.get(backend)
    if breaker is not None:
        return breaker
    with _LOCK:
        breaker = _BREAKERS.get(backend)
        if breaker is None:
            breaker = CircuitBreaker(
                failure_threshold=_DEFAULT_FAILURE_THRESHOLD,
                recovery_timeout=_DEFAULT_RECOVERY_TIMEOUT_S,
            )
            _BREAKERS[backend] = breaker
    return breaker


def reset_breakers_for_tests() -> None:
    """Test hook — drops every breaker so each test starts fresh."""
    with _LOCK:
        _BREAKERS.clear()


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def with_circuit_breaker(backend: str) -> Callable[[F], F]:
    """Decorator wrapping an async function with the per-backend breaker."""

    def _decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            breaker = get_breaker(backend)
            if not breaker.allow_request():
                raise CircuitOpenError(
                    f"circuit_open: backend={backend!r} state={breaker.state!r}; "
                    f"call rejected without hitting the backend"
                )
            try:
                result = await func(*args, **kwargs)
            except Exception:
                breaker.record_failure()
                raise
            breaker.record_success()
            return result

        return wrapper  # type: ignore[return-value]

    return _decorator
