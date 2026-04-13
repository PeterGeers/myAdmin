"""
Migration: Create parameters table for parameter-driven configuration.

Stores flat key-value parameters with scope inheritance (user -> role -> tenant -> system).
Idempotent: checks if table exists before creating.

Requirements: 1.1
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
    """Create the parameters table if it does not exist."""
    if db is None:
        db = DatabaseManager()

    if table_exists(db, 'parameters'):
        logger.info("Table 'parameters' already exists, skipping creation.")
        return False

    create_sql = """
        CREATE TABLE parameters (
            id INT AUTO_INCREMENT PRIMARY KEY,
            scope ENUM('system', 'tenant', 'role', 'user') NOT NULL,
            scope_id VARCHAR(100),
            namespace VARCHAR(50) NOT NULL,
            `key` VARCHAR(100) NOT NULL,
            value JSON NOT NULL,
            value_type ENUM('string', 'number', 'boolean', 'json') NOT NULL DEFAULT 'string',
            is_secret BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            created_by VARCHAR(100),
            UNIQUE KEY uq_param (scope, scope_id, namespace, `key`),
            INDEX idx_tenant_ns (scope, scope_id, namespace)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
    db.execute_query(create_sql, fetch=False, commit=True)
    logger.info("Table 'parameters' created successfully.")
    return True


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_migration()
