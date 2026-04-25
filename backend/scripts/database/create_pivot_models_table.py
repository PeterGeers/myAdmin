"""
Migration: Create pivot_models table for Dynamic Pivot Views.

Usage:
    python create_pivot_models_table.py [--test]

Flags:
    --test  Run against the test database instead of production.
"""

import sys
import os

# Add backend/src to path so we can import DatabaseManager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager


DDL = """
CREATE TABLE IF NOT EXISTS pivot_models (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    data_source VARCHAR(100) NOT NULL,
    definition JSON NOT NULL,
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_admin_user_name (administration, created_by, name),
    INDEX idx_administration (administration)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def main():
    test_mode = '--test' in sys.argv
    mode_label = 'TEST' if test_mode else 'PRODUCTION'

    print(f"[pivot_models migration] Running against {mode_label} database...")

    db = DatabaseManager(test_mode=test_mode)

    try:
        db.execute_query(DDL, fetch=False, commit=True)
        print("[pivot_models migration] ✅ pivot_models table created (or already exists).")
    except Exception as e:
        print(f"[pivot_models migration] ❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
