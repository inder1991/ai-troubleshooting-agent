"""Test doubles shared across workflow unit tests.

``FakeOutboxWriter`` mirrors the public surface of
``src.workflows.outbox.OutboxWriter`` (an async context manager yielding a
handle with ``update_dag`` and ``append_event``) but records every call in
memory instead of touching Postgres. Use it anywhere a test wants to assert
"the executor emitted X" without paying the per-test DB round-trip cost.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


class _FakeTx:
    def __init__(self, recorder: "FakeOutboxWriter", run_id: str) -> None:
        self._recorder = recorder
        self._run_id = run_id

    async def update_dag(self, payload: dict[str, Any]) -> None:
        self._recorder.dag_updates.append({"run_id": self._run_id, "payload": payload})

    async def append_event(
        self, seq: int, kind: str, payload: dict[str, Any]
    ) -> None:
        self._recorder.events.append(
            {"run_id": self._run_id, "seq": seq, "kind": kind, "payload": payload}
        )


class FakeOutboxWriter:
    def __init__(self) -> None:
        self.dag_updates: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.transactions_started = 0

    @asynccontextmanager
    async def transaction(self, run_id: str) -> AsyncIterator[_FakeTx]:
        self.transactions_started += 1
        yield _FakeTx(self, run_id)
