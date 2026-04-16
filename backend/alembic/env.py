"""Alembic environment.

The migration runtime here is intentionally synchronous (Alembic's CLI
expects a sync DBAPI). The application stack uses ``asyncpg`` via
``src.database.engine`` — for the CLI we translate that URL to the
``psycopg2`` driver. ``DATABASE_URL`` is the single source of truth.

Operating rules (see plan §"Operating rules"):
- No silent fallbacks: if ``DATABASE_URL`` is unset *and* no value is
  configured in ``alembic.ini``, alembic will raise — that is intentional.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_sync_url() -> str | None:
    """Return a sync (psycopg2) Postgres URL, or ``None`` if not configured.

    Priority:
      1. ``DATABASE_URL`` environment variable (translated from asyncpg).
      2. ``sqlalchemy.url`` from alembic.ini (left blank in this repo).
    """
    raw = os.environ.get("DATABASE_URL")
    if raw:
        # asyncpg URL → psycopg2 URL for the CLI
        return raw.replace("+asyncpg", "+psycopg2")
    return config.get_main_option("sqlalchemy.url") or None


# Application MetaData will be wired here as models are introduced
# (Task 1.2 outbox, Task 2.4 priors, Task 3.15 audit, ...).
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL, no engine)."""
    url = _resolve_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    url = _resolve_sync_url()
    if url is None:
        raise RuntimeError(
            "Alembic could not resolve a database URL. Set DATABASE_URL "
            "(e.g. postgresql+asyncpg://diagnostic:diagnostic@localhost:5432/"
            "diagnostic_dev) or populate sqlalchemy.url in alembic.ini."
        )

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
