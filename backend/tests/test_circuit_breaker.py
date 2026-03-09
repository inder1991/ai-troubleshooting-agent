"""Tests for Circuit Breaker — Task 61."""
import time
import pytest
from unittest.mock import patch


class TestCircuitBreakerInitialState:
    def test_starts_closed(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker()
        assert cb.state == "closed"

    def test_allows_requests_when_closed(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker()
        assert cb.allow_request() is True


class TestCircuitBreakerClosed:
    def test_stays_closed_on_success(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_success()
        cb.record_success()
        assert cb.state == "closed"

    def test_stays_closed_below_threshold(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == "closed"
        assert cb.allow_request() is True

    def test_success_resets_failure_count(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        cb.record_success()
        # After success, should reset counter; 4 more failures shouldn't open
        for _ in range(4):
            cb.record_failure()
        assert cb.state == "closed"


class TestCircuitBreakerOpen:
    def test_opens_after_threshold_failures(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"

    def test_rejects_when_open(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.allow_request() is False

    def test_opens_with_default_threshold(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker()  # default is 5
        for _ in range(5):
            cb.record_failure()
        assert cb.state == "open"


class TestCircuitBreakerHalfOpen:
    def test_transitions_to_half_open_after_timeout(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        time.sleep(0.15)
        assert cb.state == "half_open"

    def test_half_open_allows_limited_requests(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1, half_open_max=1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.allow_request() is True
        # Second request should be rejected (only 1 allowed in half_open)
        assert cb.allow_request() is False

    def test_half_open_success_closes_circuit(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1, half_open_max=1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == "half_open"
        cb.record_success()
        assert cb.state == "closed"
        assert cb.allow_request() is True

    def test_half_open_failure_reopens_circuit(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == "half_open"
        cb.record_failure()
        assert cb.state == "open"


class TestCircuitBreakerReset:
    def test_reset_returns_to_closed(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        cb.reset()
        assert cb.state == "closed"
        assert cb.allow_request() is True

    def test_reset_clears_failure_count(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.reset()
        # Only 1 failure after reset, should still be closed
        cb.record_failure()
        assert cb.state == "closed"


class TestCircuitBreakerEdgeCases:
    def test_multiple_successes_after_half_open(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.record_success()
        assert cb.state == "closed"
        # Multiple successes should keep it closed
        for _ in range(10):
            cb.record_success()
        assert cb.state == "closed"

    def test_custom_half_open_max(self):
        from src.network.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1, half_open_max=3)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.allow_request() is True
        assert cb.allow_request() is True
        assert cb.allow_request() is True
        assert cb.allow_request() is False
