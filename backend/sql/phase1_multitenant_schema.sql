-- Phase 1: Multi-Tenant Database Schema Migration
-- This script adds the 'administration' field to all tables for tenant isolation
-- All identifiers use lowercase for PostgreSQL compatibility
-- ============================================================================
-- STEP 1: Add 'administration' field to tables that don't have it
-- ============================================================================
-- Check and add administration to bnb table
SET @column_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'bnb'
            AND COLUMN_NAME = 'administration'
    );
SET @sql = IF(
        @column_exists = 0,
        'ALTER TABLE bnb ADD COLUMN administration VARCHAR(50) DEFAULT ''GoodwinSolutions'' AFTER sourceFile',
        'SELECT ''Column administration already exists in bnb'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Check and add administration to bnbfuture table
SET @column_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'bnbfuture'
            AND COLUMN_NAME = 'administration'
    );
SET @sql = IF(
        @column_exists = 0,
        'ALTER TABLE bnbfuture ADD COLUMN administration VARCHAR(50) DEFAULT ''GoodwinSolutions'' AFTER date',
        'SELECT ''Column administration already exists in bnbfuture'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Check and add administration to bnblookup table
SET @column_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'bnblookup'
            AND COLUMN_NAME = 'administration'
    );
SET @sql = IF(
        @column_exists = 0,
        'ALTER TABLE bnblookup ADD COLUMN administration VARCHAR(50) DEFAULT ''GoodwinSolutions'' AFTER lookUp',
        'SELECT ''Column administration already exists in bnblookup'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Check and add administration to bnbplanned table
SET @column_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'bnbplanned'
            AND COLUMN_NAME = 'administration'
    );
SET @sql = IF(
        @column_exists = 0,
        'ALTER TABLE bnbplanned ADD COLUMN administration VARCHAR(50) DEFAULT ''GoodwinSolutions'' AFTER sourceFile',
        'SELECT ''Column administration already exists in bnbplanned'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Check and add administration to listings table
SET @column_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'listings'
            AND COLUMN_NAME = 'administration'
    );
SET @sql = IF(
        @column_exists = 0,
        'ALTER TABLE listings ADD COLUMN administration VARCHAR(50) DEFAULT ''GoodwinSolutions'' AFTER id',
        'SELECT ''Column administration already exists in listings'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Check and add administration to pricing_events table
SET @column_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'pricing_events'
            AND COLUMN_NAME = 'administration'
    );
SET @sql = IF(
        @column_exists = 0,
        'ALTER TABLE pricing_events ADD COLUMN administration VARCHAR(50) DEFAULT ''GoodwinSolutions'' AFTER id',
        'SELECT ''Column administration already exists in pricing_events'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Check and add administration to pricing_recommendations table
SET @column_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'pricing_recommendations'
            AND COLUMN_NAME = 'administration'
    );
SET @sql = IF(
        @column_exists = 0,
        'ALTER TABLE pricing_recommendations ADD COLUMN administration VARCHAR(50) DEFAULT ''GoodwinSolutions'' AFTER id',
        'SELECT ''Column administration already exists in pricing_recommendations'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- ============================================================================
-- STEP 2: Rename uppercase 'Administration' to lowercase 'administration'
-- ============================================================================
-- Rename in mutaties table (if uppercase exists)
SET @column_exists_upper = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'mutaties'
            AND COLUMN_NAME = 'Administration'
    );
SET @column_exists_lower = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'mutaties'
            AND COLUMN_NAME = 'administration'
    );
SET @sql = IF(
        @column_exists_upper = 1
        AND @column_exists_lower = 0,
        'ALTER TABLE mutaties CHANGE Administration administration VARCHAR(50)',
        'SELECT ''Column Administration already renamed or does not exist in mutaties'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Rename in rekeningschema table (if uppercase exists)
SET @column_exists_upper = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'rekeningschema'
            AND COLUMN_NAME = 'Administration'
    );
SET @column_exists_lower = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'rekeningschema'
            AND COLUMN_NAME = 'administration'
    );
SET @sql = IF(
        @column_exists_upper = 1
        AND @column_exists_lower = 0,
        'ALTER TABLE rekeningschema CHANGE Administration administration VARCHAR(50)',
        'SELECT ''Column Administration already renamed or does not exist in rekeningschema'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- ============================================================================
-- STEP 3: Create tenant_config table for tenant-specific settings
-- ============================================================================
CREATE TABLE IF NOT EXISTS tenant_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    config_key VARCHAR(100) NOT NULL,
    config_value TEXT,
    is_secret BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    UNIQUE KEY unique_tenant_config (administration, config_key),
    INDEX idx_administration (administration)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- STEP 4: Add indexes for performance on administration field
-- ============================================================================
-- Add index to bnb table
SET @index_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'bnb'
            AND INDEX_NAME = 'idx_administration'
    );
SET @sql = IF(
        @index_exists = 0,
        'ALTER TABLE bnb ADD INDEX idx_administration (administration)',
        'SELECT ''Index idx_administration already exists on bnb'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Add index to bnbfuture table
SET @index_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'bnbfuture'
            AND INDEX_NAME = 'idx_administration'
    );
SET @sql = IF(
        @index_exists = 0,
        'ALTER TABLE bnbfuture ADD INDEX idx_administration (administration)',
        'SELECT ''Index idx_administration already exists on bnbfuture'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Add index to bnblookup table
SET @index_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'bnblookup'
            AND INDEX_NAME = 'idx_administration'
    );
SET @sql = IF(
        @index_exists = 0,
        'ALTER TABLE bnblookup ADD INDEX idx_administration (administration)',
        'SELECT ''Index idx_administration already exists on bnblookup'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Add index to bnbplanned table
SET @index_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'bnbplanned'
            AND INDEX_NAME = 'idx_administration'
    );
SET @sql = IF(
        @index_exists = 0,
        'ALTER TABLE bnbplanned ADD INDEX idx_administration (administration)',
        'SELECT ''Index idx_administration already exists on bnbplanned'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Add index to listings table
SET @index_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'listings'
            AND INDEX_NAME = 'idx_administration'
    );
SET @sql = IF(
        @index_exists = 0,
        'ALTER TABLE listings ADD INDEX idx_administration (administration)',
        'SELECT ''Index idx_administration already exists on listings'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Add index to pricing_events table
SET @index_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'pricing_events'
            AND INDEX_NAME = 'idx_administration'
    );
SET @sql = IF(
        @index_exists = 0,
        'ALTER TABLE pricing_events ADD INDEX idx_administration (administration)',
        'SELECT ''Index idx_administration already exists on pricing_events'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Add index to pricing_recommendations table
SET @index_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'pricing_recommendations'
            AND INDEX_NAME = 'idx_administration'
    );
SET @sql = IF(
        @index_exists = 0,
        'ALTER TABLE pricing_recommendations ADD INDEX idx_administration (administration)',
        'SELECT ''Index idx_administration already exists on pricing_recommendations'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Add index to mutaties table
SET @index_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'mutaties'
            AND INDEX_NAME = 'idx_administration'
    );
SET @sql = IF(
        @index_exists = 0,
        'ALTER TABLE mutaties ADD INDEX idx_administration (administration)',
        'SELECT ''Index idx_administration already exists on mutaties'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- Add index to rekeningschema table
SET @index_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'rekeningschema'
            AND INDEX_NAME = 'idx_administration'
    );
SET @sql = IF(
        @index_exists = 0,
        'ALTER TABLE rekeningschema ADD INDEX idx_administration (administration)',
        'SELECT ''Index idx_administration already exists on rekeningschema'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
-- ============================================================================
-- STEP 5: Update views to use lowercase 'administration'
-- ============================================================================
-- Drop and recreate vw_bnb_total view with administration field
DROP VIEW IF EXISTS vw_bnb_total;
CREATE VIEW vw_bnb_total AS
SELECT id,
    sourceFile,
    administration,
    channel,
    listing,
    checkinDate,
    checkoutDate,
    nights,
    guests,
    amountGross,
    amountNett,
    amountChannelFee,
    amountTouristTax,
    amountVat,
    guestName,
    phone,
    reservationCode,
    reservationDate,
    status,
    pricePerNight,
    daysBeforeReservation,
    addInfo,
    year,
    q,
    m,
    country,
    'actual' AS source_type
FROM bnb
UNION ALL
SELECT id,
    sourceFile,
    administration,
    channel,
    listing,
    checkinDate,
    checkoutDate,
    nights,
    guests,
    amountGross,
    amountNett,
    amountChannelFee,
    amountTouristTax,
    amountVat,
    guestName,
    phone,
    reservationCode,
    reservationDate,
    status,
    pricePerNight,
    daysBeforeReservation,
    addInfo,
    year,
    q,
    m,
    country,
    'planned' AS source_type
FROM bnbplanned;
-- Verify vw_readreferences uses lowercase (it should already)
-- This view should already use lowercase 'administration' based on architecture doc
-- ============================================================================
-- STEP 6: Set default values for existing data
-- ============================================================================
-- Update NULL values in bnb
UPDATE bnb
SET administration = 'GoodwinSolutions'
WHERE administration IS NULL;
-- Update NULL values in bnbfuture
UPDATE bnbfuture
SET administration = 'GoodwinSolutions'
WHERE administration IS NULL;
-- Update NULL values in bnblookup
UPDATE bnblookup
SET administration = 'GoodwinSolutions'
WHERE administration IS NULL;
-- Update NULL values in bnbplanned
UPDATE bnbplanned
SET administration = 'GoodwinSolutions'
WHERE administration IS NULL;
-- Update NULL values in listings
UPDATE listings
SET administration = 'GoodwinSolutions'
WHERE administration IS NULL;
-- Update NULL values in pricing_events
UPDATE pricing_events
SET administration = 'GoodwinSolutions'
WHERE administration IS NULL;
-- Update NULL values in pricing_recommendations
UPDATE pricing_recommendations
SET administration = 'GoodwinSolutions'
WHERE administration IS NULL;
-- Update NULL values in mutaties
UPDATE mutaties
SET administration = 'GoodwinSolutions'
WHERE administration IS NULL;
-- Update NULL values in rekeningschema
UPDATE rekeningschema
SET administration = 'GoodwinSolutions'
WHERE administration IS NULL;
-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Verify all tables have administration field
SELECT TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
    AND COLUMN_NAME = 'administration'
ORDER BY TABLE_NAME;
-- Verify indexes were created
SELECT TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
    AND INDEX_NAME = 'idx_administration'
ORDER BY TABLE_NAME;
-- Verify tenant_config table exists
SHOW CREATE TABLE tenant_config;
SELECT 'Phase 1 Migration Complete!' AS status;