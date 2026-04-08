CREATE TABLE IF NOT EXISTS user_tenant_roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    administration VARCHAR(50) NOT NULL,
    role VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    UNIQUE KEY uk_user_tenant_role (email, administration, role),
    INDEX idx_email (email),
    INDEX idx_administration (administration),
    FOREIGN KEY (administration) REFERENCES tenants(administration)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;