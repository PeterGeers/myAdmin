---
inclusion: auto
---

# Database Operations

On-demand context for Railway DB connections, migrations, and common database tasks.

## Railway MySQL Connection

```
Host:     shinkansen.proxy.rlwy.net
Port:     42375
User:     root
Password: <from `railway variables` → DB_PASSWORD on backend service>
Database: railway (then `USE finance` — data lives in the `finance` schema)
```

### Connect via bash (WSL)

```bash
# Interactive session
mysql -h shinkansen.proxy.rlwy.net -P 42375 -u root -p

# One-liner query
mysql -h shinkansen.proxy.rlwy.net -P 42375 -u root -p railway -e "USE finance; SELECT COUNT(*) FROM mutaties"

# Run a SQL file
mysql -h shinkansen.proxy.rlwy.net -P 42375 -u root -p railway < sql/migration.sql
```

### Python script against Railway

```bash
export DB_HOST='shinkansen.proxy.rlwy.net'
export DB_PORT='42375'
export DB_USER='root'
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
mysql -h 127.0.0.1 -P 3306 -u peter -p

# Or via docker-compose
docker-compose exec mysql mysql -u peter -p
```

## Environment Variables

| Variable | Local (Docker) | Production (Railway) |
|----------|---------------|---------------------|
| DB_HOST | 127.0.0.1 | shinkansen.proxy.rlwy.net |
| DB_PORT | 3306 | 42375 |
| DB_USER | peter | root |
| DB_NAME | finance | railway |
| TEST_MODE | true/false | true/false |

`TEST_MODE=true` uses `testfinance` database, `false` uses `finance`.
