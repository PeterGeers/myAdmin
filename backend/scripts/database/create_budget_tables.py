"""
Database migration script for Budget Management (fin-budget) feature.

Creates:
1. budget_versions table - Track budget versions per fiscal year
2. budget_templates table - Reusable budget template definitions
3. budget_template_lines table - Account configurations within templates
4. budget_lines table - Monthly budget amounts per account/version

All tables include administration column with standalone index for tenant isolation.

Usage:
    python scripts/database/create_budget_tables.py [--test-mode] [--dry-run]

Options:
    --test-mode: Use test database
    --dry-run: Preview changes without applying
"""

import sys
import os
from datetime import datetime

# Add backend/src to path so we can import DatabaseManager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager


# ---------------------------------------------------------------------------
# DDL Statements
# ---------------------------------------------------------------------------

DDL_BUDGET_VERSIONS = """
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

DDL_BUDGET_TEMPLATES = """
CREATE TABLE IF NOT EXISTS budget_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_administration (administration),
    UNIQUE INDEX idx_admin_name (administration, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

DDL_BUDGET_TEMPLATE_LINES = """
CREATE TABLE IF NOT EXISTS budget_template_lines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    template_id INT NOT NULL,
    administration VARCHAR(50) NOT NULL,
    account_code VARCHAR(10) NOT NULL,
    period_mode ENUM('Monthly', 'Annual') NOT NULL DEFAULT 'Monthly',
    has_detail_dimension BOOLEAN NOT NULL DEFAULT FALSE,
    dimension_type ENUM('platform', 'ReferenceNumber') NULL,
    annualization_method VARCHAR(20) NOT NULL DEFAULT 'equal-spread',
    INDEX idx_administration (administration),
    INDEX idx_template (template_id),
    UNIQUE INDEX idx_template_account (template_id, account_code),
    FOREIGN KEY (template_id) REFERENCES budget_templates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

DDL_BUDGET_LINES = """
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# Ordered list — parent tables first so foreign keys resolve correctly
TABLES = [
    ('budget_versions', DDL_BUDGET_VERSIONS),
    ('budget_templates', DDL_BUDGET_TEMPLATES),
    ('budget_template_lines', DDL_BUDGET_TEMPLATE_LINES),
    ('budget_lines', DDL_BUDGET_LINES),
]


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

def create_table(db, table_name, ddl, dry_run=False):
    """Create a single table."""
    print(f"\n📋 Creating {table_name} table...")

    if dry_run:
        print(f"  SQL: {ddl.strip()}")
        print(f"  ✅ [DRY RUN] Would create {table_name}")
        return True

    try:
        db.execute_query(ddl, fetch=False, commit=True)
        print(f"  ✅ {table_name} created (or already exists)")
        return True
    except Exception as e:
        print(f"  ❌ Error creating {table_name}: {e}")
        return False


def verify_tables(db):
    """Verify all budget tables exist and have correct structure."""
    print("\n🔍 Verifying table structures...")

    all_good = True
    for table_name, _ in TABLES:
        check_sql = """
            SELECT COUNT(*) AS count
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
        """
        result = db.execute_query(check_sql, (table_name,))
        if not result or result[0]['count'] == 0:
            print(f"  ❌ {table_name} not found")
            all_good = False
            continue

        print(f"  ✅ {table_name} exists")

        # Show column summary
        columns = db.execute_query(f"DESCRIBE {table_name}")
        print(f"     Columns: {len(columns)}")

        # Show indexes
        indexes = db.execute_query(f"SHOW INDEX FROM {table_name}")
        index_names = sorted(set(row['Key_name'] for row in indexes))
        print(f"     Indexes: {', '.join(index_names)}")

    return all_good


def main():
    """Main migration function."""
    test_mode = '--test-mode' in sys.argv or '--test' in sys.argv
    dry_run = '--dry-run' in sys.argv

    print("=" * 60)
    print("Budget Management — Database Migration")
    print("=" * 60)
    print(f"Mode: {'TEST' if test_mode else 'PRODUCTION'}")
    print(f"Dry Run: {'YES' if dry_run else 'NO'}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not dry_run:
        confirm = input("\n⚠️  This will modify the database. Continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ Migration cancelled")
            return 1

    # Connect
    try:
        db = DatabaseManager(test_mode=test_mode)
        print(f"\n✅ Connected to database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return 1

    # Create tables in dependency order
    success = True
    for table_name, ddl in TABLES:
        if not create_table(db, table_name, ddl, dry_run):
            success = False

    # Verify (only when not dry-run)
    if not dry_run and success:
        if not verify_tables(db):
            success = False

    # Summary
    print("\n" + "=" * 60)
    if dry_run:
        print("✅ DRY RUN COMPLETE — No changes made")
    elif success:
        print("✅ MIGRATION COMPLETE — All budget tables created successfully")
    else:
        print("❌ MIGRATION FAILED — Some changes may not have been applied")
    print("=" * 60)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
