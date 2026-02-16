import sqlite3
from typing import Optional
from .models import IntegrationConfig


class IntegrationStore:
    def __init__(self, db_path: str = "./data/integrations.db"):
        self._db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS integrations (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def add(self, config: IntegrationConfig) -> IntegrationConfig:
        conn = sqlite3.connect(self._db_path)
        conn.execute("INSERT INTO integrations (id, data) VALUES (?, ?)",
                     (config.id, config.model_dump_json()))
        conn.commit()
        conn.close()
        return config

    def get(self, integration_id: str) -> Optional[IntegrationConfig]:
        conn = sqlite3.connect(self._db_path)
        row = conn.execute("SELECT data FROM integrations WHERE id = ?",
                          (integration_id,)).fetchone()
        conn.close()
        return IntegrationConfig.model_validate_json(row[0]) if row else None

    def list_all(self) -> list[IntegrationConfig]:
        conn = sqlite3.connect(self._db_path)
        rows = conn.execute("SELECT data FROM integrations").fetchall()
        conn.close()
        return [IntegrationConfig.model_validate_json(r[0]) for r in rows]

    def update(self, config: IntegrationConfig) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.execute("UPDATE integrations SET data = ? WHERE id = ?",
                     (config.model_dump_json(), config.id))
        conn.commit()
        conn.close()

    def delete(self, integration_id: str) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.execute("DELETE FROM integrations WHERE id = ?", (integration_id,))
        conn.commit()
        conn.close()
