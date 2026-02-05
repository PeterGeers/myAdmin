-- Create tenants table for SysAdmin Module
-- This table stores metadata about all tenants in the system
-- Only users with SysAdmin role can modify this table
-- ============================================================================
CREATE TABLE IF NOT EXISTS tenants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active',
    contact_email VARCHAR(255),
    phone_number VARCHAR(50),
    street VARCHAR(255),
    city VARCHAR(100),
    zipcode VARCHAR(20),
    country VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    updated_by VARCHAR(255),
    INDEX idx_status (status),
    INDEX idx_administration (administration),
    INDEX idx_country (country)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- Insert existing tenants
INSERT INTO tenants (
        administration,
        display_name,
        status,
        country,
        created_at,
        created_by
    )
VALUES (
        'GoodwinSolutions',
        'Goodwin Solutions',
        'active',
        'Netherlands',
        NOW(),
        'system'
    ),
    (
        'PeterPrive',
        'Peter Privé',
        'active',
        'Netherlands',
        NOW(),
        'system'
    ),
    (
        'myAdmin',
        'myAdmin System Tenant',
        'active',
        'Netherlands',
        NOW(),
        'system'
    ) ON DUPLICATE KEY
UPDATE updated_at = NOW();
-- Verify
SELECT *
FROM tenants
ORDER BY administration;