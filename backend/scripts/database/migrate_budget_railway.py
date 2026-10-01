"""Create budget tables on Railway (production).

Database configuration comes entirely from env vars via DatabaseManager
(DB_* locally, RAILWAY_DB_* mapped onto DB_* by scripts/railway-db.sh) — no
hardcoded host/port/credentials.
"""
import os
import sys

# Add backend/src to path so we can import DatabaseManager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from database import DatabaseManager

db = DatabaseManager()

# Create budget_versions
db.execute_ddl("""
CREATE TABLE IF NOT EXISTS budget_versions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    fiscal_year SMALLINT NOT NULL,
    status ENUM('Draft', 'Approved', 'Revised') NOT NULL DEFAULT 'Draft',
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    status_changed_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_administration (administration),
    INDEX idx_admin_year (administration, fiscal_year),
    UNIQUE INDEX idx_admin_year_name (administration, fiscal_year, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")
print("budget_versions created")

# Create budget_lines with notes column
db.execute_ddl("""
CREATE TABLE IF NOT EXISTS budget_lines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    version_id INT NOT NULL,
    administration VARCHAR(50) NOT NULL,
    account_code VARCHAR(10) NOT NULL,
    period_mode ENUM('Monthly', 'Annual') NOT NULL,
    detail_dimension_type ENUM('platform', 'ReferenceNumber') NULL,
    detail_dimension_value VARCHAR(100) NULL,
    notes TEXT NULL,
    month_01 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    month_02 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    month_03 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    month_04 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    month_05 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    month_06 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    month_07 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    month_08 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    month_09 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    month_10 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    month_11 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    month_12 DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_administration (administration),
    INDEX idx_version (version_id),
    INDEX idx_version_account (version_id, account_code),
    UNIQUE INDEX idx_version_account_dim (version_id, account_code, detail_dimension_type, detail_dimension_value),
    FOREIGN KEY (version_id) REFERENCES budget_versions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")
print("budget_lines created")

# Drop template tables if they exist
db.execute_ddl("DROP TABLE IF EXISTS budget_template_lines")
db.execute_ddl("DROP TABLE IF EXISTS budget_templates")
print("Template tables dropped (if existed)")

print("Railway DB migration complete")
