# Year-End Closure Database Migration

Quick reference for running the year-end closure database migration.

## Quick Start

```bash
# Navigate to backend directory
cd backend

# Preview changes (dry run)
python scripts/database/create_year_closure_tables.py --dry-run

# Apply to production database
python scripts/database/create_year_closure_tables.py

# Apply to test database
python scripts/database/create_year_closure_tables.py --test-mode
```

## What This Migration Does

1. Creates `year_closure_status` table to track year closures
2. Adds `parameters` JSON column to `rekeningschema` table
3. Creates performance indexes for fast lookups

## Safety Features

- **Dry run mode**: Preview changes without applying
- **Idempotent**: Safe to run multiple times
- **Validation**: Verifies table structure after creation
- **Confirmation prompt**: Requires 'yes' to proceed (unless dry run)

## Expected Output

```
============================================================
Year-End Closure Database Migration
============================================================
Mode: PRODUCTION
Dry Run: NO
Timestamp: 2026-03-02 10:30:00
============================================================

⚠️  This will modify the database. Continue? (yes/no): yes

✅ Connected to database: finance

📋 Creating year_closure_status table...
✅ year_closure_status table created successfully

📋 Adding parameters column to rekeningschema...
✅ parameters column added successfully

📋 Creating performance indexes...
✅ Index idx_parameters_role created successfully

🔍 Verifying table structure...
✅ year_closure_status table exists
✅ parameters column exists in rekeningschema

📊 year_closure_status table structure:
  - id: int AUTO_INCREMENT PRIMARY KEY
  - administration: varchar(50) NOT NULL
  - year: int NOT NULL
  - closed_date: datetime NOT NULL
  - closed_by: varchar(255) NOT NULL
  - closure_transaction_id: int
  - opening_balance_transaction_id: int
  - notes: text

============================================================
✅ MIGRATION COMPLETE - All changes applied successfully
============================================================
```

## After Migration

Configure account roles for each tenant:

```python
from services.year_end_config import YearEndConfigService

config = YearEndConfigService()

# Configure for GoodwinSolutions
config.set_account_role('GoodwinSolutions', '3080', 'equity_result')
config.set_account_role('GoodwinSolutions', '8099', 'pl_closing')
config.set_account_role('GoodwinSolutions', '2001', 'interim_opening_balance')

# Validate
validation = config.validate_configuration('GoodwinSolutions')
if validation['valid']:
    print("✅ Configuration complete!")
```

## Troubleshooting

### Migration fails with "Table already exists"

This is normal if you've run the migration before. The script uses `CREATE TABLE IF NOT EXISTS`, so it's safe.

### Column already exists error

The script checks if the `parameters` column exists before adding it. If you see this error, the column may have been added manually.

### Permission denied

Ensure your database user has `CREATE`, `ALTER`, and `INDEX` privileges:

```sql
GRANT CREATE, ALTER, INDEX ON finance.* TO 'your_user'@'%';
FLUSH PRIVILEGES;
```

### Cannot connect to database

Check your `.env` file has correct database credentials:

```
DB_HOST=localhost
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=finance
DB_PORT=3306
```

## Rollback (if needed)

If you need to undo the migration:

```sql
-- Remove parameters column
ALTER TABLE rekeningschema DROP COLUMN parameters;

-- Drop year_closure_status table
DROP TABLE year_closure_status;
```

**Warning**: This will delete all year closure history and account role configurations.

## Related Documentation

- [Year-End Configuration Guide](../../docs/guides/YEAR_END_CONFIGURATION.md)
- [Phase 1 Complete Summary](../../../.kiro/specs/FIN/Year end closure/PHASE1_COMPLETE.md)
- [Design Document](../../../.kiro/specs/FIN/Year end closure/design-closure.md)
