-- Railway Migration: Create tenant_template_config table
-- This script creates the tenant_template_config table for storing template metadata
-- Part of Phase 2: Template Management Infrastructure
-- ============================================================================
-- ============================================================================
-- STEP 1: Create tenant_template_config table
-- ============================================================================
CREATE TABLE IF NOT EXISTS tenant_template_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    template_type VARCHAR(50) NOT NULL,
    template_file_id VARCHAR(255) NOT NULL,
    field_mappings JSON,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_tenant_template (administration, template_type),
    INDEX idx_tenant (administration)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Verify table was created
SELECT 'tenant_template_config table created successfully!' AS status;
-- Show table structure
DESCRIBE tenant_template_config;
-- Verify indexes
SELECT TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tenant_template_config'
ORDER BY INDEX_NAME,
    SEQ_IN_INDEX;