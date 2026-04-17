"""Task 3.16 — Idempotency-Key on external POSTs."""
from __future__ import annotations

import pytest

from src.network.idempotency import (
    IDEMPOTENCY_KEY_HEADER,
    MIN_KEY_LENGTH,
    generate_idempotency_key,
    idempotency_scope,
    inject_idempotency_key,
)


class TestGenerateKey:
    def test_length_at_least_32(self):
        key = generate_idempotency_key()
        assert len(key) >= MIN_KEY_LENGTH

    def test_each_call_returns_new_key(self):
        keys = {generate_idempotency_key() for _ in range(100)}
        assert len(keys) == 100


class TestInject:
    def test_adds_header_when_absent(self):
        out = inject_idempotency_key(None, generate_idempotency_key())
        assert IDEMPOTENCY_KEY_HEADER in out

    def test_preserves_existing_header(self):
        user_key = "a" * 40
        out = inject_idempotency_key(
            {IDEMPOTENCY_KEY_HEADER: user_key},
            generate_idempotency_key(),
        )
        assert out[IDEMPOTENCY_KEY_HEADER] == user_key

    def test_does_not_mutate_input_dict(self):
        original = {"Authorization": "Bearer tok"}
        out = inject_idempotency_key(original, generate_idempotency_key())
        assert IDEMPOTENCY_KEY_HEADER not in original
        assert IDEMPOTENCY_KEY_HEADER in out
        assert out["Authorization"] == "Bearer tok"

    def test_short_key_rejected(self):
        with pytest.raises(ValueError):
            inject_idempotency_key(None, "short")


class TestScope:
    @pytest.mark.asyncio
    async def test_scope_yields_one_stable_key(self):
        async with idempotency_scope() as k1:
            async with idempotency_scope() as k2:
                assert k1 != k2
        # Within one scope, the key is stable across reads:
        async with idempotency_scope() as k:
            first_read = k
            second_read = k
            assert first_read == second_read

    @pytest.mark.asyncio
    async def test_retry_simulation_reuses_same_key(self):
        """Integration: all attempts within one scope send the same key."""
        sent_keys: list[str] = []

        async def simulate_post(*, headers: dict):
            sent_keys.append(headers[IDEMPOTENCY_KEY_HEADER])

        async with idempotency_scope() as key:
            for _ in range(3):
                await simulate_post(
                    headers=inject_idempotency_key({}, key)
                )

        assert len(set(sent_keys)) == 1
