"""
SQLite-backed stores for ClusterProfile and GlobalIntegration entities.
"""

import os
import sqlite3
from typing import Optional

from .profile_models import (
    ClusterProfile,
    GlobalIntegration,
    DEFAULT_GLOBAL_INTEGRATIONS,
)

DEFAULT_DB_PATH = "./data/debugduck.db"


class ProfileStore:
    """SQLite store for ClusterProfile entities."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    def _ensure_tables(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cluster_profiles (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                is_active INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def add(self, profile: ClusterProfile) -> ClusterProfile:
        conn = self._conn()
        conn.execute(
            "INSERT INTO cluster_profiles (id, data, is_active) VALUES (?, ?, ?)",
            (profile.id, profile.model_dump_json(), 1 if profile.is_active else 0),
        )
        conn.commit()
        conn.close()
        return profile

    def get(self, profile_id: str) -> Optional[ClusterProfile]:
        conn = self._conn()
        row = conn.execute(
            "SELECT data FROM cluster_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        conn.close()
        return ClusterProfile.model_validate_json(row[0]) if row else None

    def list_all(self) -> list[ClusterProfile]:
        conn = self._conn()
        rows = conn.execute("SELECT data FROM cluster_profiles ORDER BY rowid DESC").fetchall()
        conn.close()
        return [ClusterProfile.model_validate_json(r[0]) for r in rows]

    def update(self, profile: ClusterProfile) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE cluster_profiles SET data = ?, is_active = ? WHERE id = ?",
            (profile.model_dump_json(), 1 if profile.is_active else 0, profile.id),
        )
        conn.commit()
        conn.close()

    def delete(self, profile_id: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM cluster_profiles WHERE id = ?", (profile_id,))
        conn.commit()
        conn.close()

    def get_active_profile(self) -> Optional[ClusterProfile]:
        conn = self._conn()
        row = conn.execute(
            "SELECT data FROM cluster_profiles WHERE is_active = 1 LIMIT 1"
        ).fetchone()
        conn.close()
        return ClusterProfile.model_validate_json(row[0]) if row else None

    def set_active(self, profile_id: str) -> None:
        conn = self._conn()
        conn.execute("UPDATE cluster_profiles SET is_active = 0")
        conn.execute(
            "UPDATE cluster_profiles SET is_active = 1 WHERE id = ?", (profile_id,)
        )
        conn.commit()
        conn.close()
        # Also update the JSON data
        profile = self.get(profile_id)
        if profile:
            # Deactivate all others in JSON
            for p in self.list_all():
                if p.id != profile_id and p.is_active:
                    p.is_active = False
                    self.update(p)
            profile.is_active = True
            self.update(profile)


class GlobalIntegrationStore:
    """SQLite store for GlobalIntegration entities."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    def _ensure_tables(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS global_integrations (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def add(self, integration: GlobalIntegration) -> GlobalIntegration:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO global_integrations (id, data) VALUES (?, ?)",
            (integration.id, integration.model_dump_json()),
        )
        conn.commit()
        conn.close()
        return integration

    def get(self, integration_id: str) -> Optional[GlobalIntegration]:
        conn = self._conn()
        row = conn.execute(
            "SELECT data FROM global_integrations WHERE id = ?", (integration_id,)
        ).fetchone()
        conn.close()
        return GlobalIntegration.model_validate_json(row[0]) if row else None

    def list_all(self) -> list[GlobalIntegration]:
        conn = self._conn()
        rows = conn.execute("SELECT data FROM global_integrations ORDER BY rowid").fetchall()
        conn.close()
        return [GlobalIntegration.model_validate_json(r[0]) for r in rows]

    def update(self, integration: GlobalIntegration) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE global_integrations SET data = ? WHERE id = ?",
            (integration.model_dump_json(), integration.id),
        )
        conn.commit()
        conn.close()

    def delete(self, integration_id: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM global_integrations WHERE id = ?", (integration_id,))
        conn.commit()
        conn.close()

    def get_by_service_type(self, service_type: str) -> Optional[GlobalIntegration]:
        for gi in self.list_all():
            if gi.service_type == service_type:
                return gi
        return None

    def seed_defaults(self):
        """Pre-populate default global integrations if the table is empty."""
        if self.list_all():
            return
        for defaults in DEFAULT_GLOBAL_INTEGRATIONS:
            gi = GlobalIntegration(**defaults)
            self.add(gi)
