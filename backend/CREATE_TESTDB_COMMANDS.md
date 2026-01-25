# Create testfinance Database - Manual Commands

## Quick Commands (Copy & Paste)

### Option 1: Using PowerShell Script (Recommended)

```powershell
cd backend
.\scripts\create_testfinance_db.ps1
```

### Option 2: Using MySQL Command Line

#### Step 1: Create the database

```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS testfinance;"
```

#### Step 2: Export finance database

```bash
mysqldump -u root -p --databases finance --add-drop-table --routines --triggers > finance_backup.sql
```

#### Step 3: Modify the dump file

Open `finance_backup.sql` in a text editor and replace:

- `CREATE DATABASE` line with: `CREATE DATABASE IF NOT EXISTS testfinance;`
- `USE `finance`` with: `USE `testfinance``

Or use this PowerShell one-liner:

```powershell
(Get-Content finance_backup.sql -Raw) -replace "CREATE DATABASE.*finance", "CREATE DATABASE IF NOT EXISTS testfinance" -replace "USE ``finance``", "USE ``testfinance``" | Set-Content finance_backup_modified.sql
```

#### Step 4: Import into testfinance

```bash
mysql -u root -p < finance_backup_modified.sql
```

#### Step 5: Verify

```bash
mysql -u root -p -e "USE testfinance; SHOW TABLES;"
mysql -u root -p -e "SELECT COUNT(*) FROM testfinance.mutaties;"
```

### Option 3: Using MySQL Workbench

1. Open MySQL Workbench
2. Connect to your database server
3. Go to **Server** → **Data Export**
4. Select `finance` database
5. Choose "Export to Self-Contained File"
6. Export to `finance_backup.sql`
7. Open the SQL file and replace `finance` with `testfinance`
8. Go to **Server** → **Data Import**
9. Select "Import from Self-Contained File"
10. Choose the modified SQL file
11. Click "Start Import"

### Option 4: Quick Copy (Single Command)

If you have MySQL 8.0+, you can use this single command:

```sql
-- Run this in MySQL command line or MySQL Workbench
CREATE DATABASE IF NOT EXISTS testfinance;

-- Then run this stored procedure
DELIMITER $$
CREATE PROCEDURE copy_finance_to_test()
BEGIN
    DECLARE done INT DEFAULT FALSE;
    DECLARE tbl VARCHAR(64);
    DECLARE cur CURSOR FOR
        SELECT TABLE_NAME FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = 'finance' AND TABLE_TYPE = 'BASE TABLE';
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    OPEN cur;
    read_loop: LOOP
        FETCH cur INTO tbl;
        IF done THEN LEAVE read_loop; END IF;

        SET @sql = CONCAT('DROP TABLE IF EXISTS testfinance.', tbl);
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

        SET @sql = CONCAT('CREATE TABLE testfinance.', tbl, ' LIKE finance.', tbl);
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

        SET @sql = CONCAT('INSERT INTO testfinance.', tbl, ' SELECT * FROM finance.', tbl);
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END LOOP;
    CLOSE cur;
END$$
DELIMITER ;

-- Execute the procedure
CALL copy_finance_to_test();

-- Clean up
DROP PROCEDURE copy_finance_to_test;
```

## Verification Commands

After creating the testfinance database, verify it was created correctly:

```sql
-- Check table count
SELECT
    'finance' as db, COUNT(*) as tables
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'finance' AND TABLE_TYPE = 'BASE TABLE'
UNION ALL
SELECT
    'testfinance' as db, COUNT(*) as tables
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'testfinance' AND TABLE_TYPE = 'BASE TABLE';

-- Check record counts
SELECT 'finance' as db, COUNT(*) as records FROM finance.mutaties
UNION ALL
SELECT 'testfinance' as db, COUNT(*) as records FROM testfinance.mutaties;

-- Check tenant data
SELECT administration, COUNT(*) as count
FROM testfinance.mutaties
GROUP BY administration;
```

## Environment Variables

Make sure your `.env` file has the test database configured:

```env
# Test Database Configuration
TEST_DB_NAME=testfinance
TEST_MODE=false

# Production Database Configuration
DB_NAME=finance
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
```

## Running Tests

After creating the testfinance database, run the integration tests:

```bash
cd backend
python -m pytest tests/integration/test_multitenant_phase5.py -v
```

## Cleanup (Optional)

To remove the test database:

```sql
DROP DATABASE IF EXISTS testfinance;
```
