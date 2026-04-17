"""Task 3.4 — circuit breaker decorator wiring."""
from __future__ import annotations

import asyncio

import pytest

from src.agents._decorators import (
    CircuitOpenError,
    get_breaker,
    reset_breakers_for_tests,
    with_circuit_breaker,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_breakers_for_tests()
    yield
    reset_breakers_for_tests()


class TestBreakerOpening:
    @pytest.mark.asyncio
    async def test_breaker_opens_after_threshold_failures(self):
        hits = 0

        @with_circuit_breaker("fake_backend")
        async def call():
            nonlocal hits
            hits += 1
            raise RuntimeError("down")

        for _ in range(5):
            with pytest.raises(RuntimeError):
                await call()

        # 6th call should fast-fail without hitting the backend
        hits_before = hits
        with pytest.raises(CircuitOpenError):
            await call()
        assert hits == hits_before  # no new backend call

    @pytest.mark.asyncio
    async def test_successful_calls_do_not_trip_breaker(self):
        @with_circuit_breaker("fake_backend")
        async def call():
            return "ok"

        for _ in range(20):
            assert await call() == "ok"
        assert get_breaker("fake_backend").state == "closed"

    @pytest.mark.asyncio
    async def test_intermittent_failures_reset_counter_on_success(self):
        attempts = iter([Exception, Exception, None, Exception, Exception])

        @with_circuit_breaker("fake_backend")
        async def call():
            v = next(attempts)
            if v is Exception:
                raise RuntimeError("boom")
            return "ok"

        for _ in range(5):
            try:
                await call()
            except RuntimeError:
                pass
        # 2 failures, 1 success, 2 failures — the success resets the
        # consecutive-failure counter, so the total consecutive streak
        # never reached 5 and the breaker stays closed.
        assert get_breaker("fake_backend").state == "closed"


class TestPerBackendIsolation:
    @pytest.mark.asyncio
    async def test_one_backend_opening_does_not_affect_others(self):
        @with_circuit_breaker("prometheus")
        async def prom_call():
            raise RuntimeError("prom down")

        @with_circuit_breaker("elasticsearch")
        async def elk_call():
            return "elk ok"

        for _ in range(5):
            with pytest.raises(RuntimeError):
                await prom_call()

        # Prom breaker opens; ELK is untouched
        with pytest.raises(CircuitOpenError):
            await prom_call()
        assert await elk_call() == "elk ok"
        assert get_breaker("elasticsearch").state == "closed"


class TestDecoratorPreservesSignature:
    @pytest.mark.asyncio
    async def test_wrapped_function_still_receives_args(self):
        @with_circuit_breaker("fake_backend")
        async def call(a: int, b: int) -> int:
            return a + b

        assert await call(2, 3) == 5
        assert await call(a=1, b=4) == 5
