# Production Migration - Quick Start

Quick reference for running i18n database migrations on production.

---

## Prerequisites Checklist

- [ ] Production database backup completed
- [ ] Backend virtual environment activated
- [ ] Verified TEST_MODE=false in .env
- [ ] Database credentials available

---

## Quick Migration Steps

### 1. Test Connection

```bash
cd backend
.\.venv\Scripts\Activate.ps1
python -c "from src.database import DatabaseManager; db = DatabaseManager(); conn = db.get_connection(); print('✅ Connected'); conn.close()"
```

### 2. Run Migration 1 - Tenant Language

```bash
python scripts/database/add_tenant_language_column.py
```

**Expected**: `✅ Migration completed successfully!`

### 3. Run Migration 2 - Account Translations

```bash
python scripts/database/create_account_translations_table.py
```

**Expected**: `✅ Migration completed successfully!`

### 4. Quick Verification

```sql
-- Check both changes
SELECT
    COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_NAME = 'tenants'
AND COLUMN_NAME = 'default_language';

SELECT
    TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_NAME = 'account_translations';
```

**Expected**: Both queries return 1 row

### 5. Restart Backend

```bash
# Stop current backend process
# Start backend
python src/app.py
```

**Check logs for**: `✅ Flask-Babel initialized with locale selector`

### 6. Test Frontend

1. Open application in browser
2. Navigate to Dashboard
3. Verify language selector appears (🇳🇱 Nederlands / 🇬🇧 English)
4. Test switching languages
5. Verify UI updates correctly

---

## If Something Goes Wrong

### Rollback Commands

```sql
-- Rollback Migration 1
DROP INDEX idx_tenants_default_language ON tenants;
ALTER TABLE tenants DROP COLUMN default_language;

-- Rollback Migration 2
DROP TABLE IF EXISTS account_translations;
```

### Get Help

1. Check full guide: `PRODUCTION_MIGRATION_GUIDE.md`
2. Check backend logs for errors
3. Run verification queries from full guide

---

## Success Indicators

✅ Both Python scripts complete without errors
✅ Backend starts with Flask-Babel message
✅ Language selector visible on Dashboard
✅ Language switching works
✅ No errors in browser console

---

**Estimated Time**: 5-10 minutes
**Downtime Required**: None
**Risk Level**: Low (non-breaking changes)

For detailed instructions, see: `PRODUCTION_MIGRATION_GUIDE.md`
