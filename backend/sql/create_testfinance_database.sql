-- Create testfinance database as a copy of finance database
-- This script creates a test database for integration testing
-- Run this script to set up the test environment
-- Step 1: Create the testfinance database
CREATE DATABASE IF NOT EXISTS testfinance;
-- Step 2: Copy the structure and data from finance to testfinance
-- Note: This uses mysqldump internally, but here's the SQL approach
USE testfinance;
-- Copy all tables from finance database
-- This will copy structure and data
-- Method 1: Using CREATE TABLE ... LIKE and INSERT ... SELECT
-- You need to run this for each table
-- Example for mutaties table:
-- CREATE TABLE testfinance.mutaties LIKE finance.mutaties;
-- INSERT INTO testfinance.mutaties SELECT * FROM finance.mutaties;
-- Method 2: Use mysqldump (recommended - run from command line)
-- mysqldump -u root -p finance > finance_backup.sql
-- mysql -u root -p testfinance < finance_backup.sql
-- Method 3: Automated copy of all tables (run this in MySQL)
-- This creates a stored procedure to copy all tables
DELIMITER $$ DROP PROCEDURE IF EXISTS copy_database $$ CREATE PROCEDURE copy_database(
    IN source_db VARCHAR(64),
    IN target_db VARCHAR(64)
) BEGIN
DECLARE done INT DEFAULT FALSE;
DECLARE table_name VARCHAR(64);
DECLARE cur CURSOR FOR
SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = source_db
    AND TABLE_TYPE = 'BASE TABLE';
DECLARE CONTINUE HANDLER FOR NOT FOUND
SET done = TRUE;
-- Create target database if not exists
SET @sql = CONCAT('CREATE DATABASE IF NOT EXISTS ', target_db);
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
OPEN cur;
read_loop: LOOP FETCH cur INTO table_name;
IF done THEN LEAVE read_loop;
END IF;
-- Drop table if exists in target
SET @sql = CONCAT(
        'DROP TABLE IF EXISTS ',
        target_db,
        '.',
        table_name
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Create table structure
SET @sql = CONCAT(
        'CREATE TABLE ',
        target_db,
        '.',
        table_name,
        ' LIKE ',
        source_db,
        '.',
        table_name
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Copy data
SET @sql = CONCAT(
        'INSERT INTO ',
        target_db,
        '.',
        table_name,
        ' SELECT * FROM ',
        source_db,
        '.',
        table_name
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SELECT CONCAT('Copied table: ', table_name) AS status;
END LOOP;
CLOSE cur;
SELECT CONCAT(
        'Database copy complete: ',
        source_db,
        ' -> ',
        target_db
    ) AS result;
END $$ DELIMITER;
-- Step 3: Execute the procedure to copy finance to testfinance
CALL copy_database('finance', 'testfinance');
-- Step 4: Verify the copy
SELECT 'finance' as database_name,
    COUNT(*) as table_count
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'finance'
    AND TABLE_TYPE = 'BASE TABLE'
UNION ALL
SELECT 'testfinance' as database_name,
    COUNT(*) as table_count
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'testfinance'
    AND TABLE_TYPE = 'BASE TABLE';
-- Step 5: Show tables in testfinance
USE testfinance;
SHOW TABLES;
-- Step 6: Verify data was copied (example with mutaties table)
SELECT 'finance' as db,
    COUNT(*) as record_count
FROM finance.mutaties
UNION ALL
SELECT 'testfinance' as db,
    COUNT(*) as record_count
FROM testfinance.mutaties;