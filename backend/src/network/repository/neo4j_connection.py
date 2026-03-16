"""Neo4j connection manager for the knowledge-graph repository layer.

Usage::

    with Neo4jConnectionManager(uri="bolt://localhost:7687") as mgr:
        rows = mgr.execute_read("MATCH (n) RETURN count(n) AS cnt")
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


class Neo4jConnectionManager:
    """Thin wrapper around the Neo4j Python driver.

    Provides convenience helpers for read, write, and multi-statement
    transactional writes, plus context-manager support for automatic cleanup.
    """

    def __init__(
        self,
        uri: str,
        username: str = "neo4j",
        password: str = "debugduck",
        database: str = "neo4j",
    ) -> None:
        self._database = database
        self._driver = GraphDatabase.driver(uri, auth=(username, password))
        self._driver.verify_connectivity()
        logger.info("Neo4j connection verified: %s (database=%s)", uri, database)

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "Neo4jConnectionManager":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying driver and release all resources."""
        self._driver.close()
        logger.info("Neo4j driver closed.")

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def execute_read(self, query: str, params: dict | None = None) -> list[dict]:
        """Run a read-only Cypher query and return results as dicts."""
        with self._driver.session(database=self._database) as session:
            result = session.run(query, parameters=params or {})
            return [record.data() for record in result]

    def execute_write(self, query: str, params: dict | None = None) -> list[dict]:
        """Run a single write Cypher query and return results as dicts."""
        with self._driver.session(database=self._database) as session:
            result = session.run(query, parameters=params or {})
            return [record.data() for record in result]

    def execute_write_tx(self, queries: list[tuple[str, dict]]) -> None:
        """Execute multiple write statements inside a single transaction.

        Parameters
        ----------
        queries:
            A list of ``(cypher_query, params_dict)`` tuples that will all
            be executed within one explicit transaction.  If any statement
            fails the entire transaction is rolled back.
        """
        with self._driver.session(database=self._database) as session:
            tx = session.begin_transaction()
            try:
                for query, params in queries:
                    tx.run(query, parameters=params or {})
                tx.commit()
            except Exception:
                tx.rollback()
                raise
