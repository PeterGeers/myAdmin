-- Railway Migration: Create tenant_credentials table
-- This script creates the tenant_credentials table for storing encrypted credentials
-- Part of Phase 1: Credentials Infrastructure
-- ============================================================================
-- ============================================================================
-- STEP 1: Create tenant_credentials table
-- ============================================================================
CREATE TABLE IF NOT EXISTS tenant_credentials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    credential_type VARCHAR(50) NOT NULL,
    encrypted_value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_tenant_cred (administration, credential_type),
    INDEX idx_administration (administration)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Verify table was created
SELECT 'tenant_credentials table created successfully!' AS status;
-- Show table structure
DESCRIBE tenant_credentials;
-- Verify indexes
SELECT TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tenant_credentials'
ORDER BY INDEX_NAME,
    SEQ_IN_INDEX;