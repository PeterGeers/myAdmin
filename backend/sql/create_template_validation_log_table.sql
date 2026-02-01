-- Railway Migration: Create template_validation_log table
-- This script creates the template_validation_log table for tracking template validation history
-- Part of Phase 2.6: Template Preview and Validation
-- ============================================================================
-- ============================================================================
-- STEP 1: Create template_validation_log table
-- ============================================================================
CREATE TABLE IF NOT EXISTS template_validation_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    template_type VARCHAR(50) NOT NULL,
    validation_result ENUM('success', 'warning', 'error') NOT NULL,
    errors JSON,
    warnings JSON,
    validated_by VARCHAR(255) NOT NULL,
    validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_administration_template (administration, template_type),
    INDEX idx_validated_at (validated_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Verify table was created
SELECT 'template_validation_log table created successfully!' AS status;
-- Show table structure
DESCRIBE template_validation_log;
-- Verify indexes
SELECT TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'template_validation_log'
ORDER BY INDEX_NAME,
    SEQ_IN_INDEX;