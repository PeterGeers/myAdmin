-- Create tenant_slugs table for Landing Page feature
-- Maps each tenant (administration) to a unique URL slug for their public landing page
-- The slug is used in the public URL: /p/{slug}
-- ============================================================================
CREATE TABLE IF NOT EXISTS tenant_slugs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_slug (slug),
    FOREIGN KEY (administration) REFERENCES tenants(administration)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;