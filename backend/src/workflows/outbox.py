"""Transactional writer for the investigation DAG snapshot + outbox events.

Closes audit finding #6 (state vs. event split-brain): every emit is paired
with a DAG snapshot UPSERT inside a single Postgres transaction. Either both
land or neither does — readers (Task 1.4 OutboxRelay) never see an event
referencing a state that wasn't persisted.

Per project operating rules, there is no in-memory fallback: if Postgres is
unreachable, ``transaction()`` propagates the exception to the caller.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.database.engine import get_session
from src.database.models import DagSnapshot, Outbox


class _Tx:
    """Per-transaction handle exposing the two writes a caller is allowed.

    Instances are short-lived: created by ``OutboxWriter.transaction`` and
    discarded when the surrounding ``async with`` block exits.
    """

    def __init__(self, session, run_id: str) -> None:
        self._session = session
        self._run_id = run_id

    async def update_dag(self, payload: dict[str, Any]) -> None:
        """UPSERT the DAG snapshot row for this run.

        Repeated calls within the same transaction overwrite each other; only
        the final ``payload`` is visible to readers after commit.
        """
        schema_version = int(payload.get("schema_version", 1))
        stmt = pg_insert(DagSnapshot).values(
            run_id=self._run_id,
            payload=payload,
            schema_version=schema_version,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[DagSnapshot.run_id],
            set_={
                "payload": stmt.excluded.payload,
                "schema_version": stmt.excluded.schema_version,
                "updated_at": func.now(),
            },
        )
        await self._session.execute(stmt)

    async def append_event(
        self, seq: int, kind: str, payload: dict[str, Any]
    ) -> None:
        """INSERT one outbox row.

        Duplicate ``(run_id, seq)`` raises ``IntegrityError`` (the unique
        constraint from Task 1.2). That signals a planner bug — sequence
        numbers must be monotonic per run — and is intentionally not caught.
        """
        await self._session.execute(
            Outbox.__table__.insert().values(
                run_id=self._run_id,
                seq=seq,
                kind=kind,
                payload=payload,
            )
        )


_DEFAULT_DAG_TABLE = "investigation_dag_snapshot"
_DEFAULT_OUTBOX_TABLE = "investigation_outbox"


class OutboxWriter:
    """Async context manager that brackets DAG + outbox writes in one tx."""

    def __init__(
        self,
        dag_table: str = _DEFAULT_DAG_TABLE,
        outbox_table: str = _DEFAULT_OUTBOX_TABLE,
    ) -> None:
        # Args reserved for future test-injection of alternate table names; the
        # current writer talks to the ORM models (DagSnapshot/Outbox) which
        # encode the production table names. Validating here means a misuse
        # like ``OutboxWriter("wrong_dag_table")`` fails fast instead of
        # silently writing to the production tables.
        if dag_table != _DEFAULT_DAG_TABLE or outbox_table != _DEFAULT_OUTBOX_TABLE:
            raise NotImplementedError(
                f"Custom table names not yet wired through ORM models "
                f"(got dag_table={dag_table!r}, outbox_table={outbox_table!r}). "
                f"Open follow-up if test-injection is required."
            )
        self._dag_table = dag_table
        self._outbox_table = outbox_table

    @asynccontextmanager
    async def transaction(self, run_id: str) -> AsyncIterator[_Tx]:
        """Yield a ``_Tx`` bound to a fresh Postgres transaction.

        The transaction commits on normal exit and rolls back on any exception
        raised inside the ``async with`` block (including from
        ``update_dag`` / ``append_event`` themselves).
        """
        async with get_session() as session:
            async with session.begin():
                yield _Tx(session, run_id)
