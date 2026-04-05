# Database Administration

> MySQL management, migrations, and backups.

## Overview

myAdmin uses MySQL 8.0 as its database. The database runs in a Docker container with data stored on the host. This page describes common administration tasks.

## Connecting

### Via Docker

```bash
docker-compose exec mysql mysql -u peter -p
```

### Locally (if MySQL runs on the host)

```bash
mysql -u peter -p -h localhost -P 3306
```

## Key tables

| Table                     | Description              |
| ------------------------- | ------------------------ |
| `mutaties`                | Financial transactions   |
| `bnb`                     | Realized STR bookings    |
| `bnbplanned`              | Planned STR bookings     |
| `bnbfuture`               | Future revenue summary   |
| `listings`                | Rental properties        |
| `tenants`                 | Tenant configuration     |
| `pricing_recommendations` | Pricing recommendations  |
| `pricing_events`          | Events for price uplifts |
| `audit_log`               | Audit trail              |

### Views

| View          | Description                                     |
| ------------- | ----------------------------------------------- |
| `vw_mutaties` | Reporting view with ledger accounts and periods |

## Test and production database

The system uses two databases:

| Mode       | Database                   | Configuration |
| ---------- | -------------------------- | ------------- |
| Production | `DB_NAME` from `.env`      | Real data     |
| Test       | `TEST_DB_NAME` from `.env` | Test data     |

The mode is determined by the `TEST_MODE` variable in `backend/.env`.

!!! warning
Never run test scripts on the production database. Always check the `TEST_MODE` setting before making changes.

## Migrations

Database migrations are executed via scripts in `backend/scripts/database/`:

```bash
python scripts/database/fix_database_views.py
```

## Backups

### Manual backup

```bash
docker-compose exec mysql mysqldump -u peter -p finance > backup_$(date +%Y%m%d).sql
```

### Restore backup

```bash
docker-compose exec -T mysql mysql -u peter -p finance < backup_20260401.sql
```

## Tips

!!! tip
Always create a backup before running migrations or making major database changes.

- MySQL data is in `./mysql_data/` — make regular copies of this directory
- Use `vw_mutaties` for reporting instead of querying the `mutaties` table directly
- The `--lower-case-table-names=2` setting ensures case-insensitive table names

## Troubleshooting

| Problem         | Cause                       | Solution                                                |
| --------------- | --------------------------- | ------------------------------------------------------- |
| Can't connect   | MySQL container not running | Start containers with `docker-compose up -d`            |
| Table not found | View not created            | Run `fix_database_views.py`                             |
| Slow queries    | Missing indexes             | Check indexes on frequently used columns                |
| Disk full       | MySQL data too large        | Check the size of `./mysql_data/` and clean up old data |
