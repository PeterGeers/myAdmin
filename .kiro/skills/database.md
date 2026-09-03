---
inclusion: auto
---

# Database Operations

On-demand context for Railway DB connections, migrations, and common database tasks.

## Railway MySQL Connection

```
Host:     <RAILWAY_DB_HOST>
Port:     <RAILWAY_DB_PORT>
User:     <RAILWAY_DB_USER>
Password: <from `railway variables` → DB_PASSWORD on backend service>
Database: railway (then `USE finance` — data lives in the `finance` schema)
```

> Real values are stored in `.env` (gitignored) or Railway service variables — never commit them here.

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

```bash
export DB_HOST='<RAILWAY_DB_HOST>'
export DB_PORT='<RAILWAY_DB_PORT>'
export DB_USER='<RAILWAY_DB_USER>'
export DB_PASSWORD='<password>'
export DB_NAME='railway'
cd backend && source .venv/bin/activate && python your_script.py
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
| DB_NAME | finance | railway |
| TEST_MODE | true/false | true/false |

`TEST_MODE=true` uses `testfinance` database, `false` uses `finance`.
