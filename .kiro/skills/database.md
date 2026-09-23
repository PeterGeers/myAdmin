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

Targets production `finance` by default. For test data pass `TEST_MODE=true`
(uses `testfinance`) or `RAILWAY_DB_NAME=testfinance`.

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
PYTHONPATH=src python -c "from database_migrations import DatabaseMigration; DatabaseMigration(test_mode=False).run_all_migrations()"
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

## Environment Variables

| Variable | Local (Docker) | Production (Railway) |
|----------|---------------|---------------------|
| DB_HOST | 127.0.0.1 | <RAILWAY_DB_HOST> |
| DB_PORT | 3306 | <RAILWAY_DB_PORT> |
| DB_USER | <LOCAL_DB_USER> | <RAILWAY_DB_USER> |
| DB_NAME | finance | finance |
| TEST_MODE | true/false | true/false |

`TEST_MODE=true` uses `testfinance` database, `false` uses `finance`. (Railway
provisions a default empty `railway` database — the app's data lives in
`finance`, so `DB_NAME=finance` in both environments.)
