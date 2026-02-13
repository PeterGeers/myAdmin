# Database Migration - Handling Dependent Views

## Problem

You have views that depend on other views:
- `vw_mutaties` depends on `vw_debetmutaties` and `vw_creditmutaties`

When importing, MySQL tries to create views in alphabetical order, which fails if dependencies aren't created first.

---

## Solution Options

### Option 1: Export and Import in Correct Order (Recommended)

#### Step 1: Export Tables First (No Views)
```bash
# Export only tables (no views, no triggers, no procedures)
mysqldump -u peter -p finance \
  --no-create-db \
  --skip-triggers \
  --no-data=false \
  --routines=false \
  --events=false \
  --ignore-table=finance.vw_mutaties \
  --ignore-table=finance.vw_debetmutaties \
  --ignore-table=finance.vw_creditmutaties \
  > railway_tables_only.sql
```

#### Step 2: Export Views Separately in Dependency Order
```bash
# Export base views first (no dependencies)
mysqldump -u peter -p finance vw_debetmutaties vw_creditmutaties \
  --no-create-info \
  --no-data \
  --skip-triggers \
  > railway_base_views.sql

# Export dependent view
mysqldump -u peter -p finance vw_mutaties \
  --no-create-info \
  --no-data \
  --skip-triggers \
  > railway_dependent_views.sql
```

#### Step 3: Import in Correct Order
```bash
# 1. Import tables and data
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < railway_tables_only.sql

# 2. Import base views (vw_debetmutaties, vw_creditmutaties)
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < railway_base_views.sql

# 3. Import dependent view (vw_mutaties)
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < railway_dependent_views.sql
```

---

### Option 2: Manual View Creation (Safest)

#### Step 1: Export Tables Only
```bash
mysqldump -u peter -p finance \
  --no-create-db \
  --skip-triggers \
  --routines=false \
  --events=false \
  > railway_tables_only.sql
```

#### Step 2: Get View Definitions
```sql
-- Connect to local database
mysql -u peter -p finance

-- Get view definitions
SHOW CREATE VIEW vw_debetmutaties\G
SHOW CREATE VIEW vw_creditmutaties\G
SHOW CREATE VIEW vw_mutaties\G
```

Copy the `CREATE VIEW` statements to separate files:
- `create_vw_debetmutaties.sql`
- `create_vw_creditmutaties.sql`
- `create_vw_mutaties.sql`

#### Step 3: Import Tables
```bash
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < railway_tables_only.sql
```

#### Step 4: Create Views Manually in Order
```bash
# Create base views first
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < create_vw_debetmutaties.sql
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < create_vw_creditmutaties.sql

# Create dependent view last
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < create_vw_mutaties.sql
```

---

### Option 3: Use mysqldump with --force (Quick but Risky)

```bash
# Export everything
mysqldump -u peter -p finance > railway_full_backup.sql

# Import with --force (continues on errors)
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> --force < railway_full_backup.sql

# Then manually fix failed views
mysql -h <railway-host> -P <port> -u <username> -p<password> <database>

-- Drop and recreate views in correct order
DROP VIEW IF EXISTS vw_mutaties;
DROP VIEW IF EXISTS vw_debetmutaties;
DROP VIEW IF EXISTS vw_creditmutaties;

-- Recreate in dependency order
CREATE VIEW vw_debetmutaties AS ...;
CREATE VIEW vw_creditmutaties AS ...;
CREATE VIEW vw_mutaties AS ...;
```

---

## Recommended Approach

**Use Option 2 (Manual View Creation)** because:
1. ✅ Most reliable
2. ✅ You have full control
3. ✅ Easy to troubleshoot
4. ✅ Views are small and few in number
5. ✅ Can verify each step

---

## Step-by-Step Guide (Recommended)

### 1. Export Tables Only
```bash
cd C:\Users\peter\aws\myAdmin

mysqldump -u peter -p finance \
  --no-create-db \
  --skip-triggers \
  --routines=false \
  --events=false \
  --ignore-table=finance.vw_mutaties \
  --ignore-table=finance.vw_debetmutaties \
  --ignore-table=finance.vw_creditmutaties \
  > railway_tables_only.sql
```

### 2. Save View Definitions
```bash
# Connect to local database
mysql -u peter -p finance

# Save each view definition to a file
```

```sql
-- Get vw_debetmutaties definition
SHOW CREATE VIEW vw_debetmutaties\G

-- Copy the CREATE VIEW statement and save to:
-- railway_view_debetmutaties.sql
```

```sql
-- Get vw_creditmutaties definition
SHOW CREATE VIEW vw_creditmutaties\G

-- Copy the CREATE VIEW statement and save to:
-- railway_view_creditmutaties.sql
```

```sql
-- Get vw_mutaties definition
SHOW CREATE VIEW vw_mutaties\G

-- Copy the CREATE VIEW statement and save to:
-- railway_view_mutaties.sql
```

### 3. Import Tables to Railway
```bash
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < railway_tables_only.sql
```

### 4. Verify Tables Imported
```bash
mysql -h <railway-host> -P <port> -u <username> -p<password> <database>
```

```sql
SHOW TABLES;
SELECT COUNT(*) FROM mutaties;
```

### 5. Create Views in Dependency Order
```bash
# Create base views first
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < railway_view_debetmutaties.sql
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < railway_view_creditmutaties.sql

# Create dependent view last
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < railway_view_mutaties.sql
```

### 6. Verify Views Work
```bash
mysql -h <railway-host> -P <port> -u <username> -p<password> <database>
```

```sql
-- Check views exist
SHOW FULL TABLES WHERE Table_type = 'VIEW';

-- Test each view
SELECT COUNT(*) FROM vw_debetmutaties;
SELECT COUNT(*) FROM vw_creditmutaties;
SELECT COUNT(*) FROM vw_mutaties;

-- Test a sample query
SELECT * FROM vw_mutaties LIMIT 5;
```

---

## Alternative: Script to Extract View Definitions

Create a helper script to extract all view definitions:

```bash
# save_views.sh
#!/bin/bash

VIEWS=("vw_debetmutaties" "vw_creditmutaties" "vw_mutaties")

for view in "${VIEWS[@]}"; do
  echo "Extracting $view..."
  mysql -u peter -p finance -e "SHOW CREATE VIEW $view\G" | \
    grep -A 1000 "Create View:" | \
    sed 's/Create View: //' > "railway_view_${view}.sql"
done

echo "View definitions saved!"
```

---

## Troubleshooting

### Error: "View references invalid table(s) or column(s)"
**Cause**: Base tables don't exist yet  
**Solution**: Import tables first, then views

### Error: "View 'vw_mutaties' references invalid view 'vw_debetmutaties'"
**Cause**: Dependent view created before base views  
**Solution**: Create views in dependency order

### Error: "Access denied for user"
**Cause**: User doesn't have CREATE VIEW privilege  
**Solution**: Grant privileges:
```sql
GRANT CREATE VIEW ON database.* TO 'username'@'%';
FLUSH PRIVILEGES;
```

---

## Summary

**Best Practice for Your Case**:
1. Export tables without views
2. Manually save view definitions (3 views only)
3. Import tables to Railway
4. Create views in order: `vw_debetmutaties` → `vw_creditmutaties` → `vw_mutaties`
5. Verify all views work

**Time Estimate**: Add 15-20 minutes to database migration for view handling

---

## Quick Reference

**View Dependency Chain**:
```
vw_debetmutaties (base view)
vw_creditmutaties (base view)
    ↓
vw_mutaties (depends on both above)
```

**Creation Order**:
1. Tables (all)
2. vw_debetmutaties
3. vw_creditmutaties
4. vw_mutaties

**Verification**:
```sql
-- Check all views exist
SELECT TABLE_NAME, TABLE_TYPE 
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'finance' 
AND TABLE_TYPE = 'VIEW';

-- Test dependent view works
SELECT * FROM vw_mutaties LIMIT 1;
```
