-- Create tenant_role_allocation table for SysAdmin Module
-- This table tracks which roles are allocated to which tenants
-- Only users with SysAdmin role can modify this table
-- ============================================================================
CREATE TABLE IF NOT EXISTS tenant_role_allocation (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    role_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    UNIQUE KEY unique_tenant_role (administration, role_name),
    FOREIGN KEY (administration) REFERENCES tenants(administration) ON DELETE CASCADE,
    INDEX idx_tenant (administration),
    INDEX idx_role (role_name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
-- Insert default role allocations for existing tenants
INSERT INTO tenant_role_allocation (administration, role_name, created_by)
VALUES ('GoodwinSolutions', 'Finance_Read', 'system'),
    ('GoodwinSolutions', 'Finance_CRUD', 'system'),
    ('GoodwinSolutions', 'Finance_Export', 'system'),
    ('GoodwinSolutions', 'STR_Read', 'system'),
    ('GoodwinSolutions', 'STR_CRUD', 'system'),
    ('GoodwinSolutions', 'STR_Export', 'system'),
    ('PeterPrive', 'Finance_Read', 'system'),
    ('PeterPrive', 'Finance_CRUD', 'system'),
    ('PeterPrive', 'Finance_Export', 'system'),
    ('PeterPrive', 'STR_Read', 'system'),
    ('PeterPrive', 'STR_CRUD', 'system'),
    ('PeterPrive', 'STR_Export', 'system'),
    ('myAdmin', 'SysAdmin', 'system') ON DUPLICATE KEY
UPDATE created_at = created_at;
-- Verify
DESCRIBE tenant_role_allocation;
SELECT *
FROM tenant_role_allocation
ORDER BY administration,
    role_name;
SELECT 'tenant_role_allocation table created successfully' AS status;