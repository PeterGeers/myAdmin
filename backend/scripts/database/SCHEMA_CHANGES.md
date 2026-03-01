# Database Schema Changes - Year-End Closure

## Overview

This document tracks database schema changes for the year-end closure feature.

## Changes

### 1. Add parameters Column to rekeningschema Table

**Date**: 2026-03-01  
**Migration Script**: `add_parameters_column.sql`  
**Purpose**: Support flexible account configuration for year-end closure and future features

**Change Details**:

```sql
ALTER TABLE rekeningschema
ADD COLUMN parameters JSON DEFAULT NULL
COMMENT 'JSON configuration for account roles';
```

**Column Specification**:

- **Name**: `parameters`
- **Type**: `JSON`
- **Nullable**: `YES`
- **Default**: `NULL`
- **Comment**: JSON configuration for account roles (e.g., {"roles": ["equity_result", "pl_closing"]})

**Index Added**:

```sql
CREATE INDEX idx_parameters_roles ON rekeningschema
((CAST(JSON_EXTRACT(parameters, '$.roles') AS CHAR(255) ARRAY)));
```

This index improves performance when querying accounts by role.

## JSON Structure

### Parameters Column Format

```json
{
  "roles": ["role_name_1", "role_name_2"]
}
```

### Supported Roles

For year-end closure:

- `equity_result` - Equity result account (e.g., 3080) - VW='N'
- `pl_closing` - P&L closing account (e.g., 8099) - VW='Y'
- `interim_opening_balance` - Interim account for opening balances (e.g., 2001) - VW='N'

Future features may add additional roles (e.g., VAT, tourist tax).

### Example Values

**Single role**:

```json
{ "roles": ["equity_result"] }
```

**Multiple roles**:

```json
{ "roles": ["equity_result", "interim_opening_balance"] }
```

**No roles** (default):

```json
null
```

## Usage Examples

### Setting Account Roles

```sql
-- Set equity result account
UPDATE rekeningschema
SET parameters = JSON_OBJECT('roles', JSON_ARRAY('equity_result'))
WHERE Account = '3080' AND administration = 'MyTenant';

-- Set P&L closing account
UPDATE rekeningschema
SET parameters = JSON_OBJECT('roles', JSON_ARRAY('pl_closing'))
WHERE Account = '8099' AND administration = 'MyTenant';

-- Set interim account
UPDATE rekeningschema
SET parameters = JSON_OBJECT('roles', JSON_ARRAY('interim_opening_balance'))
WHERE Account = '2001' AND administration = 'MyTenant';

-- Set multiple roles
UPDATE rekeningschema
SET parameters = JSON_OBJECT('roles', JSON_ARRAY('equity_result', 'interim_opening_balance'))
WHERE Account = '3080' AND administration = 'MyTenant';
```

### Querying by Role

```sql
-- Find equity result account
SELECT Account, AccountName, VW, parameters
FROM rekeningschema
WHERE administration = 'MyTenant'
AND JSON_CONTAINS(parameters->'$.roles', '"equity_result"')
LIMIT 1;

-- Find all accounts with any role
SELECT Account, AccountName, parameters
FROM rekeningschema
WHERE administration = 'MyTenant'
AND parameters IS NOT NULL;

-- Extract roles from parameters
SELECT Account, AccountName,
       JSON_EXTRACT(parameters, '$.roles') as roles
FROM rekeningschema
WHERE administration = 'MyTenant'
AND parameters IS NOT NULL;
```

### Python Helper Function

```python
def get_account_by_role(cursor, administration, role):
    """
    Get account code by role name.

    Args:
        cursor: Database cursor
        administration: Tenant identifier
        role: Role name (e.g., 'equity_result')

    Returns:
        Account code or None if not found
    """
    import json

    cursor.execute("""
        SELECT Account, AccountName, VW
        FROM rekeningschema
        WHERE administration = %s
        AND JSON_CONTAINS(parameters->'$.roles', %s)
        LIMIT 1
    """, (administration, json.dumps(role)))

    result = cursor.fetchone()
    return result['Account'] if result else None
```

## Testing

### Run Migration

```bash
# Connect to MySQL
docker-compose exec mysql mysql -u peter -p myAdmin_test

# Run migration
source /path/to/add_parameters_column.sql

# Verify
DESCRIBE rekeningschema;
```

### Run Tests

```bash
# In container
docker-compose exec backend bash
cd /app
source .venv/bin/activate

# Run test script
python scripts/database/test_parameters_column.py
```

Expected output:

```
============================================================
Testing parameters JSON column in rekeningschema
============================================================
Testing parameters column existence...
✓ Parameters column exists
  Type: json
  Nullable: YES
  Comment: JSON configuration for account roles

Testing JSON operations...
  Using test account: 1000 (Bank Account)

  Test 1: Setting JSON value...
  ✓ JSON value set

  Test 2: Reading JSON value...
  ✓ Parameters: {"roles": ["test_role"]}
  ✓ Roles: ["test_role"]

  Test 3: JSON_CONTAINS query...
  ✓ Found 1 account(s) with 'test_role'

  Test 4: Setting multiple roles...
  ✓ Multiple roles: {"roles": ["equity_result", "test_role"]}

  Test 5: Clearing parameters...
  ✓ Parameters cleared

Testing get_account_by_role helper function...
  ✓ Found account for role 'equity_result': 1000 (Bank Account)
    VW: N
    Parameters: {"roles": ["equity_result"]}

============================================================
Test Summary
============================================================
✓ PASS: Column exists
✓ PASS: JSON operations
✓ PASS: Helper function

============================================================
All tests passed!
```

## Rollback

If needed, the change can be rolled back:

```sql
-- Remove index
DROP INDEX idx_parameters_roles ON rekeningschema;

-- Remove column
ALTER TABLE rekeningschema DROP COLUMN parameters;
```

## Performance Considerations

- JSON column adds minimal storage overhead (NULL for most accounts)
- Index on roles array improves query performance
- JSON operations are efficient in MySQL 8.0+
- Typical query time: < 1ms for finding account by role

## Compatibility

- **MySQL Version**: 8.0+ (required for JSON support)
- **Backward Compatibility**: Existing queries not affected (new column is nullable)
- **Forward Compatibility**: Extensible for future features (VAT, tourist tax, etc.)

## Migration Checklist

- [x] Create migration SQL script
- [x] Create test script
- [x] Document schema changes
- [ ] Test on development database
- [ ] Test on staging database
- [ ] Deploy to production
- [ ] Verify in production

## Related Files

- Migration: `backend/scripts/database/add_parameters_column.sql`
- Tests: `backend/scripts/database/test_parameters_column.py`
- Documentation: This file
- Design: `.kiro/specs/FIN/Year end closure/design-migration.md`
- Requirements: `.kiro/specs/FIN/Year end closure/requirements.md`
