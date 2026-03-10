"""SQLite-backed CRUD store for database connection profiles."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Optional


class DBProfileStore:
    def __init__(self, db_path: str = "data/debugduck.db"):
        self._db_path = db_path
        self._ensure_table()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS db_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    database_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL DEFAULT '',
                    connection_uri TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            # Migrate: add connection_uri column if missing (existing DBs)
            try:
                conn.execute("SELECT connection_uri FROM db_profiles LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE db_profiles ADD COLUMN connection_uri TEXT NOT NULL DEFAULT ''")

    def create(
        self,
        *,
        name: str,
        engine: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        connection_uri: str = "",
        tags: dict | None = None,
    ) -> dict:
        profile_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO db_profiles (id, name, engine, host, port, database_name, username, password, connection_uri, tags, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    profile_id,
                    name,
                    engine,
                    host,
                    port,
                    database,
                    username,
                    password,
                    connection_uri,
                    json.dumps(tags or {}),
                    now,
                ),
            )
        return self.get(profile_id)  # type: ignore

    def get(self, profile_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM db_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_dict(row, include_password=True)

    def list_all(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM db_profiles ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_dict(r, include_password=False) for r in rows]

    def update(self, profile_id: str, **fields) -> Optional[dict]:
        allowed = {
            "name",
            "engine",
            "host",
            "port",
            "database",
            "username",
            "password",
            "connection_uri",
            "tags",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get(profile_id)
        # Map 'database' field to column name
        if "database" in updates:
            updates["database_name"] = updates.pop("database")
        if "tags" in updates and isinstance(updates["tags"], dict):
            updates["tags"] = json.dumps(updates["tags"])
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [profile_id]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE db_profiles SET {set_clause} WHERE id = ?", values
            )
        return self.get(profile_id)

    def delete(self, profile_id: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM db_profiles WHERE id = ?", (profile_id,)
            )
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_dict(
        row: sqlite3.Row, include_password: bool = False
    ) -> dict:
        d = {
            "id": row["id"],
            "name": row["name"],
            "engine": row["engine"],
            "host": row["host"],
            "port": row["port"],
            "database": row["database_name"],
            "username": row["username"],
            "connection_uri": row["connection_uri"] if "connection_uri" in row.keys() else "",
            "tags": json.loads(row["tags"]) if row["tags"] else {},
            "created_at": row["created_at"],
        }
        if include_password:
            d["password"] = row["password"]
        return d
