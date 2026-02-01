-- Railway Migration: Create ai_usage_log table
-- This script creates the ai_usage_log table for tracking AI API usage and cost
-- Part of Phase 2.6: Template Preview and Validation - AI Template Assistant
-- ============================================================================
-- ============================================================================
-- STEP 1: Create ai_usage_log table
-- ============================================================================
CREATE TABLE IF NOT EXISTS ai_usage_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    feature VARCHAR(100) NOT NULL,
    tokens_used INT NOT NULL DEFAULT 0,
    cost_estimate DECIMAL(10, 6) NOT NULL DEFAULT 0.000000,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_administration (administration),
    INDEX idx_created_at (created_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Verify table was created
SELECT 'ai_usage_log table created successfully!' AS status;
-- Show table structure
DESCRIBE ai_usage_log;
-- Verify indexes
SELECT TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ai_usage_log'
ORDER BY INDEX_NAME,
    SEQ_IN_INDEX;