# Simple Solution for vw_mutaties View

## Problem

`vw_mutaties` depends on `vw_debetmutaties` and `vw_creditmutaties`, causing import order issues.

## Simple Solution: Recreate After Import

Since only `vw_mutaties` is the problem, just recreate it after the main import.

---

## Step-by-Step

### 1. Export Everything (Including Views)

```bash
mysqldump -u peter -p finance > railway_full_backup.sql
```

### 2. Import to Railway (Will Fail on vw_mutaties)

```bash
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < railway_full_backup.sql
```

**Expected**: Import succeeds for tables and base views, but `vw_mutaties` might fail. That's OK!

### 3. Get vw_mutaties Definition from Local Database

```bash
mysql -u peter -p finance -e "SHOW CREATE VIEW vw_mutaties\G" > vw_mutaties_definition.txt
```

### 4. Recreate vw_mutaties on Railway

```bash
# Copy the CREATE VIEW statement from vw_mutaties_definition.txt
# Then run it on Railway:

mysql -h <railway-host> -P <port> -u <username> -p<password> <database>
```

```sql
-- Drop if exists (in case partial creation happened)
DROP VIEW IF EXISTS vw_mutaties;

-- Paste the CREATE VIEW statement here
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
```

### 5. Verify It Works

```sql
-- Check view exists
SHOW FULL TABLES WHERE Table_type = 'VIEW';

-- Test the view
SELECT COUNT(*) FROM vw_mutaties;
SELECT * FROM vw_mutaties LIMIT 5;
```

---

## Alternative: Combine Into Single View (If You Want)

If you want to eliminate the dependency entirely, you could replace all three views with one combined view. But this requires knowing what `vw_debetmutaties` and `vw_creditmutaties` do.

**To get their definitions:**

```bash
mysql -u peter -p finance

SHOW CREATE VIEW vw_debetmutaties\G
SHOW CREATE VIEW vw_creditmutaties\G
```

Then you could create a single `vw_mutaties` that doesn't reference the other views, but instead directly queries the base tables.

---

## Recommendation

**Use the simple solution**:

1. Import everything normally
2. If `vw_mutaties` fails, just recreate it manually after import
3. Takes 5 extra minutes

**Don't combine views** unless:

- You're having persistent issues
- You want to simplify the database structure
- The base views aren't used elsewhere

---

## Quick Commands

```bash
# 1. Export
mysqldump -u peter -p finance > railway_full_backup.sql

# 2. Import (ignore vw_mutaties error if it happens)
mysql -h <host> -P <port> -u <user> -p<pass> <db> < railway_full_backup.sql

# 3. If vw_mutaties failed, get its definition
mysql -u peter -p finance -e "SHOW CREATE VIEW vw_mutaties\G"

# 4. Recreate on Railway
mysql -h <host> -P <port> -u <user> -p<pass> <db>
DROP VIEW IF EXISTS vw_mutaties;
-- Paste CREATE VIEW statement
```

**Time**: 5 minutes extra

---

## Summary

**Simplest approach**:

- Do normal import
- Manually recreate `vw_mutaties` if it fails
- No need to combine views or change structure

This is the path of least resistance and gets you up and running fastest! 🚀
