-- Phase 5: Tenant-Specific Module Access
-- Create table to define which modules each tenant has access to
-- Create tenant_modules table
CREATE TABLE IF NOT EXISTS tenant_modules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    module_name VARCHAR(50) NOT NULL,
    -- 'FIN' (Finance) or 'STR' (Short-term Rental)
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    UNIQUE KEY unique_tenant_module (administration, module_name),
    INDEX idx_administration (administration),
    INDEX idx_module_name (module_name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- Insert initial tenant-module mappings
-- PeterPrive: FIN only
INSERT INTO tenant_modules (
        administration,
        module_name,
        is_active,
        created_by
    )
VALUES ('PeterPrive', 'FIN', TRUE, 'system') ON DUPLICATE KEY
UPDATE is_active = TRUE;
-- GoodwinSolutions: FIN and STR
INSERT INTO tenant_modules (
        administration,
        module_name,
        is_active,
        created_by
    )
VALUES ('GoodwinSolutions', 'FIN', TRUE, 'system') ON DUPLICATE KEY
UPDATE is_active = TRUE;
INSERT INTO tenant_modules (
        administration,
        module_name,
        is_active,
        created_by
    )
VALUES ('GoodwinSolutions', 'STR', TRUE, 'system') ON DUPLICATE KEY
UPDATE is_active = TRUE;
-- InterimManagement: FIN only (default)
INSERT INTO tenant_modules (
        administration,
        module_name,
        is_active,
        created_by
    )
VALUES ('InterimManagement', 'FIN', TRUE, 'system') ON DUPLICATE KEY
UPDATE is_active = TRUE;
-- Verify the data
SELECT *
FROM tenant_modules
ORDER BY administration,
    module_name;