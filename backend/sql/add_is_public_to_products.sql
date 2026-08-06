-- Task 3.13: Add is_public column to products for landing page integration
-- Allows tenants to mark specific ZZP services/products as visible on their public landing page.
SET @col_exists = (
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'products'
            AND COLUMN_NAME = 'is_public'
    );
SET @sql = IF(
        @col_exists = 0,
        'ALTER TABLE products ADD COLUMN is_public BOOLEAN DEFAULT FALSE',
        'SELECT ''Column is_public already exists on products'' AS message'
    );
PREPARE stmt
FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;