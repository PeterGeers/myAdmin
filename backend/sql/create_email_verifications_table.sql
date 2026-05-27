-- Railway Migration: Create email_verifications table
-- This script creates the email_verifications table for tracking SES email identity verification per tenant
-- Part of SES Email Verification feature
-- ============================================================================
-- ============================================================================
-- STEP 1: Create email_verifications table
-- ============================================================================
CREATE TABLE IF NOT EXISTS email_verifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    email VARCHAR(255) NOT NULL,
    status ENUM(
        'pending',
        'verified',
        'failed',
        'expired',
        'replaced'
    ) NOT NULL DEFAULT 'pending',
    initiated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at DATETIME NULL,
    last_checked_at DATETIME NULL,
    last_resend_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_administration (administration),
    INDEX idx_admin_status (administration, status),
    INDEX idx_email (email)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Verify table was created
SELECT 'email_verifications table created successfully!' AS status;
-- Show table structure
DESCRIBE email_verifications;
-- Verify indexes
SELECT TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'email_verifications'
ORDER BY INDEX_NAME,
    SEQ_IN_INDEX;