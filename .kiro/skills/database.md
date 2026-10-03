---
inclusion: auto
---

# Database Operations

On-demand context for Railway DB connections, migrations, and common database tasks.

> **DynamoDB (SAM plane) note:** this skill covers the Flask/MySQL (Railway) plane. For
> the module plane's DynamoDB tables (`sam-members`, `governance_projection` in the
> `nonprofit-deploy` account), beware: the repo-root `.env` static AWS keys override
> `AWS_PROFILE` and point you at the WRONG account (a silent `ResourceNotFoundException`).
> The strip-and-verify invocation is documented in `41-shell-environment.md`
> (§"`.env` credentials override `AWS_PROFILE`").

## Railway MySQL Connection

```
Host:     <RAILWAY_DB_HOST>   (public TCP proxy, e.g. *.proxy.rlwy.net)
Port:     <RAILWAY_DB_PORT>
User:     <RAILWAY_DB_USER>
Password: <RAILWAY_DB_PASSWORD>
Database: finance  (data lives in the `finance` schema; Railway's default
                    `railway` DB is empty)
```

> Real values live in the repo-root `.env` (gitignored) under `RAILWAY_DB_*`
> keys, or in Railway service variables — never commit them here.

### Wrapper: run a command against Railway (recommended)

`backend/scripts/railway-db.sh` reads the `RAILWAY_DB_*` keys from `.env` and
maps them onto `DB_*` for a **single** command, so your local Docker `DB_*`
config is never disturbed:

```bash
# from repo root, venv active
PYTHONPATH=backend/src backend/scripts/railway-db.sh python backend/scripts/verify_schema.py
PYTHONPATH=backend/src backend/scripts/railway-db.sh python -c "from database import DatabaseManager; print(DatabaseManager().execute_query('SELECT COUNT(*) c FROM mutaties', None, fetch=True))"
```

Targets the `finance` schema (the only schema the app uses — see
"Environments" below). The wrapper still accepts a legacy `TEST_MODE=true` /
`RAILWAY_DB_NAME=testfinance` escape hatch for ad-hoc access to an old
`testfinance` schema if one still exists on Railway, but that is NOT the
environment model: the app selects TEST vs PRODUCTION by resolved DB *target*
(local Docker vs Railway), both on schema `finance`, never by a schema switch.

### Connect via bash (WSL)

```bash
# Interactive session
mysql -h <RAILWAY_DB_HOST> -P <RAILWAY_DB_PORT> -u <RAILWAY_DB_USER> -p

# One-liner query
mysql -h <RAILWAY_DB_HOST> -P <RAILWAY_DB_PORT> -u <RAILWAY_DB_USER> -p railway -e "USE finance; SELECT COUNT(*) FROM mutaties"

# Run a SQL file
mysql -h <RAILWAY_DB_HOST> -P <RAILWAY_DB_PORT> -u <RAILWAY_DB_USER> -p railway < sql/migration.sql
```

### Python script against Railway

Prefer the wrapper (above) — it pulls the `RAILWAY_DB_*` values from `.env` and
isolates them to one command:

```bash
cd /home/peter/projects/myAdmin && source backend/.venv/bin/activate
PYTHONPATH=backend/src backend/scripts/railway-db.sh python your_script.py
```

## Migration System

Migrations are JSON files in `backend/src/migrations/`, applied by `DatabaseMigration.run_all_migrations()`.

### Run migrations

```bash
cd backend && source .venv/bin/activate
# The target DB is selected by APP_ENV / the DB_* env vars — there is NO
# test_mode argument (removed in the test-environment Phase 3 refactor).
PYTHONPATH=src python -c "from database_migrations import DatabaseMigration; DatabaseMigration().run_all_migrations()"
```

### Key facts

- Migrations are NOT auto-applied on app startup — run manually
- The `database_migrations` table tracks which migrations have been applied (won't re-run)
- Migrations are idempotent via the tracking system, not via SQL syntax

### MySQL 9.4 Limitations

- **No `IF NOT EXISTS` on `CREATE INDEX`** — never use it
- **No `IF EXISTS` on `DROP INDEX`** — never use it
- Use plain `CREATE INDEX idx_name ON table (columns)` and `DROP INDEX idx_name ON table`
- Idempotency is handled by the migration system skipping already-applied migrations

## Common Queries

```sql
-- Check migration status
SELECT * FROM database_migrations ORDER BY applied_at DESC LIMIT 10;

-- List all tables
SHOW TABLES;

-- Check table structure
DESCRIBE mutaties;

-- Count transactions per tenant
SELECT administration, COUNT(*) FROM mutaties GROUP BY administration;

-- View definition
SHOW CREATE VIEW vw_mutaties;
```

## Local Docker MySQL

```bash
# Connect to local Docker MySQL
mysql -h 127.0.0.1 -P 3306 -u <LOCAL_DB_USER> -p

# Or via docker-compose
docker-compose exec mysql mysql -u <LOCAL_DB_USER> -p
```

## Environments (APP_ENV + resolved target)

The app has ONE environment selector, `APP_ENV` (`test` | `production`), from
which the Environment_Resolver derives a single resolved DB **target**. There is
no `test_mode` flag and no `finance`/`testfinance` schema split — the schema is
`finance` for BOTH environments. TEST and PRODUCTION are distinguished by their
resolved target and credentials, not by physical hosting location or schema name.

Current operational mapping (non-normative — the targets can be relocated without
changing the model, by changing the resolver mapping/config):

| Variable | TEST target (APP_ENV=test) | PRODUCTION target (APP_ENV=production) |
|----------|----------------------------|----------------------------------------|
| resolved via | `DB_HOST_TEST` / `DB_PORT_TEST` / `DB_USER_TEST` / `DB_PASSWORD_TEST` | `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` |
| current host | local Docker MySQL (127.0.0.1:3306) | Railway proxy (`<RAILWAY_DB_HOST>:<RAILWAY_DB_PORT>`) |
| schema | `finance` | `finance` |

(Railway provisions a default empty `railway` database — the app's data lives in
`finance`, so the schema is `finance` in both environments.) The legacy
`TEST_MODE` / `testfinance` escape hatch on `railway-db.sh` is NOT this model; see
the wrapper note above.
