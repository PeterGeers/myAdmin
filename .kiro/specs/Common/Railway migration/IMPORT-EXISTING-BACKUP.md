# Import Existing Database Backup to Railway

## Your Backup File

**Location**: `.kiro/specs/Common/Railway migration/myDatabaseForRailway.zip`  
**Extracted**: `.kiro/specs/Common/Railway migration/extracted/myDatabaseForRailway.sql`  
**Size**: 13.87 MB (13,870,543 bytes)  
**Format**: HeidiSQL export (MySQL 8.0.44)  
**Status**: ✅ Ready to import  
**Last Modified**: February 13, 2026

---

## 🚀 Quick Start (3 Steps)

**Total Time**: 10-15 minutes

1. **Get Railway MySQL credentials** (2 min)
2. **Import the backup file** (5-8 min)
3. **Verify and fix vw_mutaties view if needed** (3-5 min)

---

## Quick Import Steps

### 1. Get Railway MySQL Connection Details

Go to Railway Dashboard → MySQL service → Connect tab

Copy these details:

```
Host: _____________________
Port: _____________________
Username: _____________________
Password: _____________________
Database: _____________________
```

### 2. Import the Database

```bash
cd "C:\Users\peter\aws\myAdmin\.kiro\specs\Common\Railway migration\extracted"

# Import to Railway
mysql -h <host> -P <port> -u <username> -p<password> <database> < myDatabaseForRailway.sql
```

**Example:**

```bash
mysql -h containers-us-west-123.railway.app -P 5432 -u root -pYourPassword finance < myDatabaseForRailway.sql
```

### 3. Monitor Import Progress

The import will take 2-5 minutes for a 13 MB file. You'll see:

- Table creation statements
- Data insertion progress
- View creation (might see error for vw_mutaties - that's OK)

### 4. Verify Import

```bash
# Connect to Railway database
mysql -h <host> -P <port> -u <username> -p<password> <database>
```

```sql
-- Check tables exist
SHOW TABLES;

-- Check row counts
SELECT 'mutaties' AS table_name, COUNT(*) AS rows FROM mutaties
UNION ALL SELECT 'bnb', COUNT(*) FROM bnb
UNION ALL SELECT 'bnbplanned', COUNT(*) FROM bnbplanned
UNION ALL SELECT 'bnbfuture', COUNT(*) FROM bnbfuture
UNION ALL SELECT 'listings', COUNT(*) FROM listings
UNION ALL SELECT 'tenants', COUNT(*) FROM tenants
UNION ALL SELECT 'users', COUNT(*) FROM users;

-- Test a sample query
SELECT * FROM mutaties LIMIT 5;
```

---

## If vw_mutaties View Fails

The backup includes views, but `vw_mutaties` might fail because it depends on other views.

**If you see an error like:**

```
ERROR 1146 (42S02): Table 'finance.vw_debetmutaties' doesn't exist
```

**Solution - Recreate vw_mutaties manually:**

```sql
-- Connect to Railway database
mysql -h <host> -P <port> -u <username> -p<password> <database>

-- Drop the failed view
DROP VIEW IF EXISTS vw_mutaties;

-- Recreate it (after base views are created)
CREATE VIEW vw_mutaties AS
SELECT r.Belastingaangifte AS Aangifte,
    d.TransactionNumber,
    d.TransactionDate,
    d.TransactionDescription,
    - d.TransactionAmount AS Amount,
    d.Reknum,
    d.AccountName,
    d.Parent,
    d.VW,
    d.jaar,
    d.kwartaal,
    d.maand,
    d.week,
    d.ReferenceNumber,
    d.administration,
    d.Ref3,
    d.Ref4
FROM vw_debetmutaties d
    LEFT JOIN rekeningschema r ON d.Reknum = r.Account
    AND d.administration = r.administration
UNION ALL
SELECT r.Belastingaangifte AS Aangifte,
    c.TransactionNumber,
    c.TransactionDate,
    c.TransactionDescription,
    c.TransactionAmount AS Amount,
    c.Reknum,
    c.AccountName,
    c.Parent,
    c.VW,
    c.jaar,
    c.kwartaal,
    c.maand,
    c.week,
    c.ReferenceNumber,
    c.administration,
    c.Ref3,
    c.Ref4
FROM vw_creditmutaties c
    LEFT JOIN rekeningschema r ON c.Reknum = r.Account
    AND c.administration = r.administration;

-- Verify it works
SELECT COUNT(*) FROM vw_mutaties;
```

---

## Alternative: Use Railway CLI (If Working)

```bash
cd "C:\Users\peter\aws\myAdmin\.kiro\specs\Common\Railway migration\extracted"

# Link to Railway project
railway link

# Import database
railway run mysql -u root -p < myDatabaseForRailway.sql
```

---

## Troubleshooting

### Error: "Access denied"

**Solution**: Check username/password are correct

### Error: "Unknown database"

**Solution**: The backup creates the database, so this shouldn't happen. If it does:

```sql
CREATE DATABASE IF NOT EXISTS finance;
USE finance;
```

Then import again.

### Error: "Lost connection to MySQL server"

**Solution**: File might be too large for single connection. Split import:

```bash
# Split the file (if needed)
split -l 10000 myDatabaseForRailway.sql part_

# Import each part
mysql -h <host> -P <port> -u <user> -p<pass> <db> < part_aa
mysql -h <host> -P <port> -u <user> -p<pass> <db> < part_ab
# etc.
```

### Import is very slow

**Normal**: 13 MB can take 2-5 minutes depending on:

- Network speed
- Railway server load
- Number of indexes

---

## Post-Import Checklist

- [ ] All tables imported
- [ ] Row counts match expectations
- [ ] Views created (or manually recreated)
- [ ] Sample queries work
- [ ] Backend can connect to database
- [ ] No errors in Railway logs

---

## Quick Command Reference

```bash
# Extract zip (already done)
Expand-Archive -Path "myDatabaseForRailway.zip" -DestinationPath "extracted"

# Import to Railway
cd extracted
mysql -h <host> -P <port> -u <user> -p<pass> <db> < myDatabaseForRailway.sql

# Verify
mysql -h <host> -P <port> -u <user> -p<pass> <db> -e "SHOW TABLES;"
mysql -h <host> -P <port> -u <user> -p<pass> <db> -e "SELECT COUNT(*) FROM mutaties;"

# Test backend connection
curl https://invigorating-celebration-production.up.railway.app/api/health
```

---

## Time Estimate

- Get Railway connection details: 2 minutes
- Run import command: 2-5 minutes
- Verify import: 3 minutes
- Fix vw_mutaties (if needed): 5 minutes

**Total**: 12-15 minutes

---

## Success Criteria

✅ Import completes without critical errors  
✅ All tables exist  
✅ Row counts look reasonable  
✅ Sample queries return data  
✅ Backend health check still works  
✅ Backend can query database

---

## Next Step After Import

Once database is imported and verified, proceed to frontend deployment (see NEXT-STEPS.md Phase 2).

**You're almost there!** 🚀
