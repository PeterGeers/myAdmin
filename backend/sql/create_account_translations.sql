-- Create account_translations table for i18n support
-- This allows Chart of Accounts to be displayed in multiple languages
-- ============================================================================
CREATE TABLE IF NOT EXISTS account_translations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_code VARCHAR(10) NOT NULL,
    language VARCHAR(5) NOT NULL,
    account_name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    -- Foreign key to rekeningschema table
    FOREIGN KEY (account_code) REFERENCES rekeningschema(Account) ON DELETE CASCADE ON UPDATE CASCADE,
    -- Unique constraint: one translation per account per language
    UNIQUE KEY unique_account_lang (account_code, language),
    -- Indexes for performance
    INDEX idx_language (language),
    INDEX idx_account_code (account_code)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- Verify table created
DESCRIBE account_translations;
-- Show count
SELECT COUNT(*) as translation_count
FROM account_translations;