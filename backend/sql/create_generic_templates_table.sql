-- Create generic_templates table for SysAdmin Module
-- This table stores metadata for generic templates stored on Railway filesystem
-- Only users with SysAdmin role can modify this table
-- ============================================================================
CREATE TABLE IF NOT EXISTS generic_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    template_name VARCHAR(100) NOT NULL,
    template_type VARCHAR(50) NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    field_mappings JSON,
    version INT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_template_version (template_name, version),
    INDEX idx_type (template_type),
    INDEX idx_active (is_active),
    INDEX idx_name (template_name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- Verify
DESCRIBE generic_templates;
SELECT 'generic_templates table created successfully' AS status;