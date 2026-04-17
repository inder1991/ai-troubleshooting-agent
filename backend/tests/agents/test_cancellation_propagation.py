"""Task 4.25 — cancellation propagation utilities."""
from __future__ import annotations

import asyncio

import pytest

from src.agents.cancellation import (
    CancelToken,
    CancelledByToken,
    cancel_guard,
    cancellable_call,
    ensure_cancel_reraised,
)


class TestEnsureCancelReraised:
    def test_reraises_cancelled_error(self):
        with pytest.raises(asyncio.CancelledError):
            ensure_cancel_reraised(asyncio.CancelledError())

    def test_noop_on_other_exceptions(self):
        # Should NOT raise for ValueError etc.
        ensure_cancel_reraised(ValueError("unrelated"))
        ensure_cancel_reraised(RuntimeError("also fine"))

    def test_works_inside_except_exception(self):
        try:
            try:
                raise asyncio.CancelledError()
            except Exception as e:
                ensure_cancel_reraised(e)
                assert False, "should have re-raised"
        except asyncio.CancelledError:
            pass


class TestCancelToken:
    def test_starts_unset(self):
        assert CancelToken().is_set() is False

    def test_set_is_sticky(self):
        t = CancelToken()
        t.set()
        assert t.is_set() is True
        # No unset method — once cancelled, stays cancelled
        assert not hasattr(t, "unset")


class TestCancellableCall:
    @pytest.mark.asyncio
    async def test_token_trip_cancels_in_flight_awaitable(self):
        token = CancelToken()
        was_cancelled = {"v": False}

        async def slow():
            try:
                await asyncio.sleep(10)
                return "done"
            except asyncio.CancelledError:
                was_cancelled["v"] = True
                raise

        async def trigger():
            await asyncio.sleep(0.05)
            token.set()

        asyncio.ensure_future(trigger())
        with pytest.raises(CancelledByToken):
            await cancellable_call(slow(), token)
        assert was_cancelled["v"] is True

    @pytest.mark.asyncio
    async def test_awaitable_completes_normally_if_no_cancel(self):
        token = CancelToken()

        async def fast():
            await asyncio.sleep(0.01)
            return 42

        result = await cancellable_call(fast(), token)
        assert result == 42


class TestCancelGuard:
    @pytest.mark.asyncio
    async def test_raises_on_entry_if_already_cancelled(self):
        token = CancelToken()
        token.set()
        with pytest.raises(CancelledByToken):
            async with cancel_guard(token):
                pass

    @pytest.mark.asyncio
    async def test_raises_on_exit_if_cancelled_during_block(self):
        token = CancelToken()
        with pytest.raises(CancelledByToken):
            async with cancel_guard(token):
                token.set()

    @pytest.mark.asyncio
    async def test_no_raise_when_untripped(self):
        token = CancelToken()
        async with cancel_guard(token):
            pass


class TestCancelledByToken:
    def test_is_subclass_of_cancelled_error(self):
        assert issubclass(CancelledByToken, asyncio.CancelledError)
