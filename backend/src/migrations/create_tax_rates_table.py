"""
Migration: Create tax_rates table for time-versioned tax rate storage.

Stores tax rates with effective date ranges and tenant-specific overrides,
with fallback to system defaults.
Idempotent: checks if table exists before creating.

Requirements: 2.1, 2.2
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database import DatabaseManager

logger = logging.getLogger(__name__)


def table_exists(db, table_name):
    """Check if a table already exists in the current database."""
    result = db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        (table_name,),
        fetch=True
    )
    return result[0]['cnt'] > 0


def run_migration(db=None):
    """Create the tax_rates table if it does not exist."""
    if db is None:
        db = DatabaseManager()

    if table_exists(db, 'tax_rates'):
        logger.info("Table 'tax_rates' already exists, skipping creation.")
        return False

    create_sql = """
        CREATE TABLE tax_rates (
            id INT AUTO_INCREMENT PRIMARY KEY,
            administration VARCHAR(50) NOT NULL,
            tax_type VARCHAR(30) NOT NULL,
            tax_code VARCHAR(20) NOT NULL,
            rate DECIMAL(6,3) NOT NULL,
            ledger_account VARCHAR(10),
            effective_from DATE NOT NULL,
            effective_to DATE NOT NULL DEFAULT '9999-12-31',
            country_code VARCHAR(2) NOT NULL DEFAULT 'NL',
            description VARCHAR(100),
            calc_method VARCHAR(30) NOT NULL DEFAULT 'percentage',
            calc_params JSON DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by VARCHAR(100),
            UNIQUE KEY uq_tax_rate (administration, tax_type, tax_code, effective_from),
            INDEX idx_lookup (administration, tax_type, effective_from, effective_to)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
    db.execute_query(create_sql, fetch=False, commit=True)
    logger.info("Table 'tax_rates' created successfully.")
    return True


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_migration()
