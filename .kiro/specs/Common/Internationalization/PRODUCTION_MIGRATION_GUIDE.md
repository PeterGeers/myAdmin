# Production Database Migration Guide

This guide provides step-by-step instructions for running the i18n database migrations on the production database.

---

## Prerequisites

✅ **Before starting**:

- [ ] Production database backup completed
- [ ] Access to production database (MySQL credentials)
- [ ] Backend virtual environment activated
- [ ] Verified TEST_MODE=false in production .env

---

## Migration Overview

### Changes Required

1. **tenants table**: Add `default_language` column (VARCHAR(5), DEFAULT 'nl')
2. **account_translations table**: Create new table for future chart of accounts translations

### Impact Assessment

- **Downtime**: None required (non-breaking changes)
- **Data loss risk**: None (only adding columns/tables)
- **Rollback**: Simple (drop column/table if needed)

---

## Step 1: Verify Database Connection

Test connection to production database:

```bash
cd backend
.\.venv\Scripts\Activate.ps1  # Windows
# or
source .venv/bin/activate  # Linux/Mac

python -c "from src.database import DatabaseManager; db = DatabaseManager(); conn = db.get_connection(); print('✅ Connected to:', conn.get_server_info()); conn.close()"
```

**Expected output**: `✅ Connected to: 8.0.x`

---

## Step 2: Run Migration 1 - Add Tenant Language Column

### Option A: Using Python Script (Recommended)

```bash
cd backend
python scripts/database/add_tenant_language_column.py
```

**Expected output**:

```
Adding default_language column to tenants table...
✅ Added default_language column
✅ Added index on default_language
✅ Updated existing tenants to 'nl'

Current tenants:
  GoodwinSolutions: Goodwin Solutions - Language: nl - Status: active
  JaBaKi: JaBaKi - Language: nl - Status: active
  PeterGeers: Peter Geers - Language: nl - Status: active
  TestTenant: Test Tenant - Language: nl - Status: active

✅ Migration completed successfully!
```

### Option B: Using SQL Script

```bash
mysql -u [username] -p [database_name] < backend/sql/add_tenant_default_language.sql
```

### Verification

Check the column was added:

```sql
DESCRIBE tenants;
```

Should show:

```
+------------------+--------------+------+-----+---------+
| Field            | Type         | Null | Key | Default |
+------------------+--------------+------+-----+---------+
| ...
| default_language | varchar(5)   | YES  | MUL | nl      |
| ...
+------------------+--------------+------+-----+---------+
```

Check all tenants have the column:

```sql
SELECT administration, display_name, default_language, status
FROM tenants
ORDER BY administration;
```

**Expected**: All tenants should have `default_language = 'nl'`

---

## Step 3: Run Migration 2 - Create Account Translations Table

### Option A: Using Python Script (Recommended)

```bash
cd backend
python scripts/database/create_account_translations_table.py
```

**Expected output**:

```
Creating account_translations table...
✅ Created account_translations table

Table structure:
  id                   int
  account_code         varchar(10)
  language             varchar(5)
  account_name         varchar(255)
  description          text
  created_at           timestamp
  updated_at           timestamp

Current translations: 0

✅ Migration completed successfully!
```

### Option B: Using SQL Script

```bash
mysql -u [username] -p [database_name] < backend/sql/create_account_translations.sql
```

### Verification

Check the table was created:

```sql
SHOW TABLES LIKE 'account_translations';
```

Check the table structure:

```sql
DESCRIBE account_translations;
```

Check foreign key constraint:

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_NAME = 'account_translations'
AND REFERENCED_TABLE_NAME IS NOT NULL;
```

**Expected**: Foreign key to `rekeningschema(Account)`

---

## Step 4: Verify Migrations

### Check All Changes

Run this verification script:

```sql
-- Check tenants table
SELECT
    'tenants.default_language' as check_item,
    CASE
        WHEN COUNT(*) > 0 THEN '✅ Column exists'
        ELSE '❌ Column missing'
    END as status
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
AND TABLE_NAME = 'tenants'
AND COLUMN_NAME = 'default_language'

UNION ALL

-- Check account_translations table
SELECT
    'account_translations table' as check_item,
    CASE
        WHEN COUNT(*) > 0 THEN '✅ Table exists'
        ELSE '❌ Table missing'
    END as status
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
AND TABLE_NAME = 'account_translations'

UNION ALL

-- Check all tenants have language set
SELECT
    'All tenants have language' as check_item,
    CASE
        WHEN COUNT(*) = 0 THEN '✅ All set'
        ELSE CONCAT('❌ ', COUNT(*), ' tenants missing language')
    END as status
FROM tenants
WHERE default_language IS NULL OR default_language = '';
```

**Expected output**:

```
+---------------------------+------------------+
| check_item                | status           |
+---------------------------+------------------+
| tenants.default_language  | ✅ Column exists |
| account_translations table| ✅ Table exists  |
| All tenants have language | ✅ All set       |
+---------------------------+------------------+
```

---

## Step 5: Test Application

### Backend Test

1. **Restart backend** (if running):

   ```bash
   # Stop backend
   # Start backend
   cd backend
   python src/app.py
   ```

2. **Check logs** for i18n initialization:

   ```
   ✅ Flask-Babel initialized with locale selector
   ```

3. **Test API endpoints**:

   ```bash
   # Test user language endpoint
   curl -X GET http://localhost:5000/api/user/language \
     -H "Authorization: Bearer [token]" \
     -H "X-Tenant: GoodwinSolutions"

   # Test tenant language endpoint
   curl -X GET http://localhost:5000/api/tenant-admin/language \
     -H "Authorization: Bearer [token]" \
     -H "X-Tenant: GoodwinSolutions"
   ```

### Frontend Test

1. **Open application** in browser
2. **Navigate to Dashboard**
3. **Verify language selector** appears in header
4. **Test language switching**:
   - Click language selector
   - Select "English"
   - Verify UI updates to English
   - Verify localStorage updated: `localStorage.getItem('i18nextLng')`
5. **Test persistence**:
   - Refresh page
   - Verify language remains selected

---

## Rollback Procedure (If Needed)

### Rollback Migration 1 (Tenant Language Column)

```sql
-- Remove index
DROP INDEX idx_tenants_default_language ON tenants;

-- Remove column
ALTER TABLE tenants DROP COLUMN default_language;

-- Verify
DESCRIBE tenants;
```

### Rollback Migration 2 (Account Translations Table)

```sql
-- Drop table (foreign key will be dropped automatically)
DROP TABLE IF EXISTS account_translations;

-- Verify
SHOW TABLES LIKE 'account_translations';
```

---

## Troubleshooting

### Issue: Column already exists

**Error**: `Duplicate column name 'default_language'`

**Solution**: Column was already added. Verify with:

```sql
DESCRIBE tenants;
```

If column exists, migration is complete. Skip to verification step.

### Issue: Table already exists

**Error**: `Table 'account_translations' already exists`

**Solution**: Table was already created. Verify with:

```sql
DESCRIBE account_translations;
```

If table exists, migration is complete. Skip to verification step.

### Issue: Foreign key constraint fails

**Error**: `Cannot add foreign key constraint`

**Possible causes**:

1. `rekeningschema` table doesn't exist
2. `Account` column doesn't exist in `rekeningschema`
3. Data type mismatch

**Solution**:

```sql
-- Check if rekeningschema table exists
SHOW TABLES LIKE 'rekeningschema';

-- Check Account column
DESCRIBE rekeningschema;

-- Check data types match
SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
FROM information_schema.COLUMNS
WHERE TABLE_NAME = 'rekeningschema'
AND COLUMN_NAME = 'Account';
```

### Issue: Permission denied

**Error**: `Access denied for user`

**Solution**: Ensure database user has ALTER and CREATE privileges:

```sql
GRANT ALTER, CREATE, INDEX ON [database_name].* TO '[username]'@'%';
FLUSH PRIVILEGES;
```

---

## Post-Migration Checklist

- [ ] Migration 1 completed (tenants.default_language added)
- [ ] Migration 2 completed (account_translations table created)
- [ ] All tenants have default_language = 'nl'
- [ ] Foreign key constraint verified
- [ ] Backend restarted successfully
- [ ] Frontend language selector visible
- [ ] Language switching works
- [ ] User language preference persists
- [ ] Email templates use correct language
- [ ] No errors in backend logs
- [ ] No errors in browser console

---

## Migration Summary

### What Changed

**Database Schema**:

1. `tenants` table: Added `default_language` column (VARCHAR(5), DEFAULT 'nl')
2. `account_translations` table: Created new table for future use

**Application Behavior**:

- New users inherit tenant's default language
- Language selector appears on Dashboard
- User language preference saved to Cognito
- Email templates sent in user's preferred language

### What Didn't Change

- Existing data remains unchanged
- No data migration required
- No breaking changes to existing functionality
- Application continues to work if migrations fail (graceful degradation)

---

## Support

If you encounter issues during migration:

1. **Check logs**: Backend logs will show detailed error messages
2. **Verify prerequisites**: Ensure database connection and permissions
3. **Run verification queries**: Use SQL queries in Step 4
4. **Rollback if needed**: Use rollback procedures above
5. **Contact support**: Provide error messages and verification query results

---

**Last Updated**: February 18, 2026
**Version**: 1.0
