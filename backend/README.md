# Backend

## Local Postgres (dev)

The hardening track uses a Postgres 15 instance for new durable stores
(outbox, audit log, agent priors, eval). Legacy SQLite at `data/debugduck.db`
is **not** affected.

```bash
# Start (from repo root)
docker-compose -f docker-compose.dev.yml up -d postgres

# Default URL (matches backend/src/database/engine.py)
export DATABASE_URL='postgresql+asyncpg://diagnostic:diagnostic@localhost:5432/diagnostic_dev'

# Apply migrations
cd backend && alembic upgrade head

# Verify
python3 -m pytest backend/tests/database/ -v   # run from REPO ROOT
```

Stop with `docker-compose -f docker-compose.dev.yml down` (add `-v` to wipe
the `diagnostic_pg_data` volume).
