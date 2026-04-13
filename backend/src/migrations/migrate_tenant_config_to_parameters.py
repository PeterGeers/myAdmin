"""
Migration: tenant_config → parameters table

Copies all tenant_config rows into the parameters table using ParameterService.
Maps keys to namespaces:
  - google_drive_*  → storage namespace
  - storage_*       → storage namespace (strip prefix)
  - company_logo_*  → branding namespace
  - all others      → config namespace

Safe to run multiple times (upsert logic).

Usage:
  cd backend
  python -m src.migrations.migrate_tenant_config_to_parameters [--dry-run]
"""

import os
import sys
import json
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database import DatabaseManager
from services.parameter_service import ParameterService

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def map_key_to_namespace(config_key: str) -> tuple:
    """Map a tenant_config key to (namespace, key) in parameters table."""
    if config_key.startswith('google_drive_'):
        return ('storage', config_key)
    if config_key.startswith('storage_'):
        return ('storage', config_key[len('storage_'):])
    if config_key.startswith('company_logo'):
        return ('branding', config_key)
    return ('config', config_key)


def migrate(dry_run: bool = False):
    """Migrate all tenant_config rows to parameters table."""
    test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
    db = DatabaseManager(test_mode=test_mode)
    param_service = ParameterService(db)

    # Read all tenant_config rows
    rows = db.execute_query(
        "SELECT administration, config_key, config_value, is_secret FROM tenant_config ORDER BY administration, config_key",
        fetch=True
    )

    if not rows:
        logger.info("No tenant_config rows found. Nothing to migrate.")
        return

    logger.info(f"Found {len(rows)} tenant_config rows to migrate.")
    migrated = 0
    skipped = 0

    for row in rows:
        tenant = row['administration']
        config_key = row['config_key']
        config_value = row['config_value']
        is_secret = bool(row.get('is_secret', False))

        namespace, key = map_key_to_namespace(config_key)

        # Determine value type
        value = config_value
        value_type = 'string'
        if config_value:
            try:
                parsed = json.loads(config_value)
                if isinstance(parsed, bool):
                    value = parsed
                    value_type = 'boolean'
                elif isinstance(parsed, (int, float)):
                    value = parsed
                    value_type = 'number'
                elif isinstance(parsed, (dict, list)):
                    value = parsed
                    value_type = 'json'
            except (json.JSONDecodeError, TypeError):
                pass  # Keep as string

        if dry_run:
            logger.info(f"  [DRY RUN] {tenant}: {config_key} -> parameters(scope=tenant, ns={namespace}, key={key}, type={value_type}, secret={is_secret})")
            migrated += 1
            continue

        try:
            param_service.set_param(
                scope='tenant',
                scope_id=tenant,
                namespace=namespace,
                key=key,
                value=value,
                value_type=value_type,
                is_secret=is_secret,
                created_by='migration_r17',
            )
            migrated += 1
            logger.info(f"  OK {tenant}: {config_key} -> {namespace}.{key}")
        except Exception as e:
            logger.error(f"  FAIL {tenant}: {config_key} -> {e}")
            skipped += 1

    logger.info(f"\nMigration complete: {migrated} migrated, {skipped} skipped.")


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        logger.info("=== DRY RUN MODE ===")
    migrate(dry_run=dry_run)
