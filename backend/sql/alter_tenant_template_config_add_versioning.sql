-- Railway Migration: Add versioning columns to tenant_template_config table
-- This script extends the tenant_template_config table with versioning support
-- Part of Phase 2.6: Template Preview and Validation
-- ============================================================================
-- ============================================================================
-- STEP 1: Add versioning columns
-- ============================================================================
-- Add version column (INT, default 1)
ALTER TABLE tenant_template_config
ADD COLUMN version INT DEFAULT 1 NOT NULL
AFTER field_mappings;
-- Add approved_by column (VARCHAR(255))
ALTER TABLE tenant_template_config
ADD COLUMN approved_by VARCHAR(255) NULL
AFTER version;
-- Add approved_at column (TIMESTAMP)
ALTER TABLE tenant_template_config
ADD COLUMN approved_at TIMESTAMP NULL
AFTER approved_by;
-- Add approval_notes column (TEXT)
ALTER TABLE tenant_template_config
ADD COLUMN approval_notes TEXT NULL
AFTER approved_at;
-- Add previous_file_id column (VARCHAR(255))
ALTER TABLE tenant_template_config
ADD COLUMN previous_file_id VARCHAR(255) NULL
AFTER approval_notes;
-- Add status column (ENUM: 'draft', 'active', 'archived', default 'active')
ALTER TABLE tenant_template_config
ADD COLUMN status ENUM('draft', 'active', 'archived') DEFAULT 'active' NOT NULL
AFTER previous_file_id;
-- ============================================================================
-- STEP 2: Update existing records to have status 'active'
-- ============================================================================
-- Ensure all existing records have status 'active' (should already be default)
UPDATE tenant_template_config
SET status = 'active'
WHERE status IS NULL;
-- ============================================================================
-- STEP 3: Add indexes for performance
-- ============================================================================
-- Add index on status for filtering active/draft/archived templates
CREATE INDEX idx_status ON tenant_template_config(status);
-- Add index on approved_by for audit queries
CREATE INDEX idx_approved_by ON tenant_template_config(approved_by);
-- Add composite index for common queries (administration + status)
CREATE INDEX idx_admin_status ON tenant_template_config(administration, status);
-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Verify columns were added
SELECT 'Versioning columns added successfully!' AS status;
-- Show updated table structure
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
-- Show sample data with new columns
SELECT id,
    administration,
    template_type,
    version,
    status,
    approved_by,
    approved_at,
    is_active,
    created_at,
    updated_at
FROM tenant_template_config
LIMIT 5;
-- ============================================================================
-- ROLLBACK SCRIPT (if needed)
-- ============================================================================
-- To rollback these changes, run:
-- 
-- DROP INDEX idx_status ON tenant_template_config;
-- DROP INDEX idx_approved_by ON tenant_template_config;
-- DROP INDEX idx_admin_status ON tenant_template_config;
-- ALTER TABLE tenant_template_config DROP COLUMN status;
-- ALTER TABLE tenant_template_config DROP COLUMN previous_file_id;
-- ALTER TABLE tenant_template_config DROP COLUMN approval_notes;
-- ALTER TABLE tenant_template_config DROP COLUMN approved_at;
-- ALTER TABLE tenant_template_config DROP COLUMN approved_by;
-- ALTER TABLE tenant_template_config DROP COLUMN version;
-- ============================================================================