"""
Seed script: Populate tenant-scope parameters for all existing tenants.

Reads all active tenants from the tenants table and seeds the parameters
needed for task 8 (replacing hardcoded values). Also reads existing
tenant_config values (e.g. Google Drive folder IDs) and migrates them.

Idempotent: skips parameters that already exist at tenant scope.

Prerequisites: parameters table must exist (create_parameters_table.py).

Reference: .kiro/specs/parameter-driven-config/tasks.md - Task 8
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database import DatabaseManager

logger = logging.getLogger(__name__)


def get_all_tenants(db):
    """Get all tenant administration names from the tenants table."""
    rows = db.execute_query(
        "SELECT administration FROM tenants ORDER BY administration",
        fetch=True
    )
    return [r['administration'] for r in rows] if rows else []


def get_tenant_config_value(db, administration, config_key):
    """Read a value from the existing tenant_config table."""
    rows = db.execute_query(
        "SELECT config_value FROM tenant_config "
        "WHERE administration = %s AND config_key = %s",
        (administration, config_key),
        fetch=True
    )
    if rows and rows[0].get('config_value'):
        return rows[0]['config_value']
    return None


def param_exists(db, scope, scope_id, namespace, key):
    """Check if a parameter already exists."""
    rows = db.execute_query(
        "SELECT id FROM parameters "
        "WHERE scope = %s AND scope_id = %s AND namespace = %s AND `key` = %s",
        (scope, scope_id, namespace, key),
        fetch=True
    )
    return bool(rows)


def set_param(db, scope, scope_id, namespace, key, value, value_type='string'):
    """Insert a parameter if it doesn't already exist."""
    if param_exists(db, scope, scope_id, namespace, key):
        logger.info("  SKIP %s.%s (already exists)", namespace, key)
        return False

    json_value = json.dumps(value)
    db.execute_query(
        "INSERT INTO parameters (scope, scope_id, namespace, `key`, value, value_type, is_secret, created_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (scope, scope_id, namespace, key, json_value, value_type, False, 'seed_migration'),
        fetch=False, commit=True
    )
    logger.info("  SET  %s.%s = %s", namespace, key, value)
    return True


def seed_tenant(db, tenant):
    """Seed all required parameters for a single tenant."""
    seeded = 0

    # --- 8.3: report_output_path ---
    if os.getenv('DOCKER_ENV') or os.path.exists('/.dockerenv'):
        report_path = '/app/reports'
    else:
        report_path = os.path.join(os.getcwd(), 'reports')
    if set_param(db, 'tenant', tenant, 'storage', 'report_output_path', report_path):
        seeded += 1

    # --- 8.4: google_drive_folder_id ---
    # Try to read from existing tenant_config first
    gd_folder = get_tenant_config_value(db, tenant, 'google_drive_invoices_folder_id')
    if not gd_folder:
        # Fall back to env var
        use_test = os.getenv('TEST_MODE', 'false').lower() == 'true'
        gd_folder = (os.getenv('TEST_FACTUREN_FOLDER_ID') if use_test
                     else os.getenv('FACTUREN_FOLDER_ID', ''))
    if gd_folder:
        if set_param(db, 'tenant', tenant, 'storage', 'google_drive_folder_id', gd_folder):
            seeded += 1

    return seeded


def run_seed(db=None):
    """Seed parameters for all existing tenants."""
    if db is None:
        db = DatabaseManager()

    tenants = get_all_tenants(db)
    if not tenants:
        logger.warning("No tenants found in tenants table.")
        return 0

    logger.info("Seeding parameters for %d tenants...", len(tenants))
    total = 0
    for tenant in tenants:
        logger.info("Tenant: %s", tenant)
        count = seed_tenant(db, tenant)
        total += count
        logger.info("  -> %d parameters seeded", count)

    logger.info("Done. Total parameters seeded: %d across %d tenants.", total, len(tenants))
    return total


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    run_seed()
