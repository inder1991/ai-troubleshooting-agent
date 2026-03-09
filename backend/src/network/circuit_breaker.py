"""Three-state circuit breaker for adapter integrations.

States:
    CLOSED   -- normal operation, requests flow through
    OPEN     -- tripped after consecutive failures, all requests rejected
    HALF_OPEN -- recovery probe window, limited requests allowed

Transitions:
    CLOSED  --[failure_threshold consecutive failures]--> OPEN
    OPEN    --[recovery_timeout elapsed]----------------> HALF_OPEN
    HALF_OPEN --[success]-------------------------------> CLOSED
    HALF_OPEN --[failure]-------------------------------> OPEN
"""
from __future__ import annotations

import time


class CircuitBreaker:
    """Three-state circuit breaker: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 1,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max = half_open_max

        self._state: str = "closed"
        self._consecutive_failures: int = 0
        self._opened_at: float = 0.0
        self._half_open_requests: int = 0

    # ── Public API ──

    @property
    def state(self) -> str:
        """Return the current state, auto-transitioning OPEN -> HALF_OPEN if timeout elapsed."""
        if self._state == "open" and self._timeout_elapsed():
            self._state = "half_open"
            self._half_open_requests = 0
        return self._state

    def allow_request(self) -> bool:
        """Check whether a request should be allowed through."""
        current = self.state  # triggers auto-transition
        if current == "closed":
            return True
        if current == "half_open":
            if self._half_open_requests < self._half_open_max:
                self._half_open_requests += 1
                return True
            return False
        # open
        return False

    def record_success(self) -> None:
        """Record a successful request."""
        if self._state == "half_open" or self.state == "half_open":
            # Half-open success -> close the circuit
            self._state = "closed"
            self._consecutive_failures = 0
            self._half_open_requests = 0
        else:
            # Reset consecutive failure counter on any success
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed request."""
        current = self.state  # triggers auto-transition
        if current == "half_open":
            # Half-open failure -> reopen
            self._state = "open"
            self._opened_at = time.monotonic()
            self._half_open_requests = 0
        elif current == "closed":
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                self._state = "open"
                self._opened_at = time.monotonic()

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self._state = "closed"
        self._consecutive_failures = 0
        self._half_open_requests = 0
        self._opened_at = 0.0

    # ── Internal ──

    def _timeout_elapsed(self) -> bool:
        return (time.monotonic() - self._opened_at) >= self._recovery_timeout
