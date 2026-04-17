"""Reader for the persisted investigation virtual DAG.

Audit P0 #5 close-out: the previous in-memory + Redis fallback masked Postgres
unavailability and let producers/consumers see different DAG states. Writes
now go through ``OutboxWriter`` (atomic with the outbox event); this class is
the read-side counterpart and queries ``investigation_dag_snapshot`` directly.

Per project operating rules there is no fallback: if Postgres is unreachable
the underlying SQLAlchemy exception propagates.
"""
from __future__ import annotations

from sqlalchemy import delete, select

from src.database.engine import get_session
from src.database.models import DagSnapshot
from src.workflows.investigation_types import VirtualDag


class InvestigationStore:
    async def load_dag(self, run_id: str) -> VirtualDag | None:
        async with get_session() as session:
            result = await session.execute(
                select(DagSnapshot.payload).where(DagSnapshot.run_id == run_id)
            )
            row = result.first()
            if row is None:
                return None
            return VirtualDag.from_dict(row[0])

    async def delete_dag(self, run_id: str) -> None:
        async with get_session() as session:
            async with session.begin():
                await session.execute(
                    delete(DagSnapshot).where(DagSnapshot.run_id == run_id)
                )
