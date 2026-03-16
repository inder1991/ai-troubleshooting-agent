"""ReconciliationService — detects and fixes drift between SQLite and Neo4j.

Compares device IDs in both stores, marks stale Neo4j nodes, identifies
missing nodes, then runs a full sync to bring Neo4j back in line with SQLite.

Usage::

    svc = ReconciliationService(sqlite_repo, neo4j_manager)
    report = svc.reconcile()
"""

from __future__ import annotations

import logging
from typing import Any

from .sqlite_repository import SQLiteRepository
from .neo4j_connection import Neo4jConnectionManager
from .graph_sync import GraphSyncService

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Detects drift between SQLite (source of truth) and Neo4j, then fixes it."""

    def __init__(
        self,
        repo: SQLiteRepository,
        neo4j: Neo4jConnectionManager,
    ) -> None:
        self._repo = repo
        self._neo4j = neo4j
        self._sync = GraphSyncService(repo, neo4j)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reconcile(self) -> dict[str, Any]:
        """Compare SQLite and Neo4j, mark stale nodes, re-sync, and return a report."""

        # 1. Device IDs in SQLite
        sqlite_ids: set[str] = {d.id for d in self._repo.get_devices()}

        # 2. Device IDs in Neo4j
        rows = self._neo4j.execute_read("MATCH (d:Device) RETURN d.id AS id")
        neo4j_ids: set[str] = {r["id"] for r in rows}

        # 3. Stale = in Neo4j but not in SQLite → mark stale
        stale_ids: set[str] = neo4j_ids - sqlite_ids
        for sid in stale_ids:
            logger.warning("Stale Neo4j device (not in SQLite): %s", sid)
            self._neo4j.execute_write(
                "MATCH (d:Device {id: $id}) SET d.stale = true",
                {"id": sid},
            )

        # 4. Missing = in SQLite but not in Neo4j → note for re-sync
        missing_ids: set[str] = sqlite_ids - neo4j_ids
        for mid in missing_ids:
            logger.info("Missing Neo4j device (will be synced): %s", mid)

        # 5. Full sync to fix all drift
        sync_report = self._sync.full_sync()

        # 6. Count Neo4j devices after sync
        rows = self._neo4j.execute_read("MATCH (d:Device) RETURN count(d) AS cnt")
        neo4j_count_after = rows[0]["cnt"]

        # 7. Build report
        report: dict[str, Any] = {
            "status": "ok",
            "devices_in_sqlite": len(sqlite_ids),
            "devices_in_neo4j": neo4j_count_after,
            "stale_in_neo4j": sorted(stale_ids),
            "missing_in_neo4j": sorted(missing_ids),
            **sync_report,
        }

        logger.info("Reconciliation complete: %s", report)
        return report
