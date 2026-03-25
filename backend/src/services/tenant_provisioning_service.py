"""
Tenant Provisioning Service

Shared logic for creating a new tenant, used by both:
- SysAdmin UI (sysadmin_tenants.py)
- Provisioning script (scripts/provision_tenant.py)

Handles:
1. Insert tenant record (idempotent)
2. Insert tenant modules (idempotent — skips existing, inserts missing)
3. Load chart of accounts from JSON template (idempotent — skips if rows exist)

Returns a results dict with created/skipped status per step so callers
can report exactly what happened.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Path to chart of accounts JSON templates
_TEMPLATE_DIR = Path(__file__).parent.parent / 'templates' / 'chart_of_accounts'


class TenantProvisioningService:
    """Shared tenant provisioning logic."""

    def __init__(self, db_manager):
        self.db = db_manager

    def create_and_provision_tenant(
        self,
        administration: str,
        display_name: str,
        contact_email: str,
        modules: list,
        created_by: str,
        locale: str = 'nl',
        phone_number: Optional[str] = None,
        street: Optional[str] = None,
        city: Optional[str] = None,
        zipcode: Optional[str] = None,
        country: str = 'Netherlands',
    ) -> dict:
        """
        Create and provision a new tenant.

        Idempotent — safe to rerun if a previous attempt partially completed.
        Each step checks before acting and skips if already done.

        Args:
            administration: Unique tenant identifier (PascalCase, alphanumeric)
            display_name:   Human-readable tenant name
            contact_email:  Primary contact email
            modules:        List of module names (e.g. ['FIN', 'STR', 'TENADMIN'])
            created_by:     Email of the user performing the action
            locale:         'nl' or 'en' — determines chart of accounts language
            phone_number:   Optional contact phone
            street:         Optional street address
            city:           Optional city
            zipcode:        Optional zipcode
            country:        Country (default: Netherlands)

        Returns:
            {
                'tenant':  'created' | 'skipped',
                'modules': [{'name': 'FIN', 'status': 'created' | 'skipped'}, ...],
                'chart':   'created' | 'skipped' | 'failed',
                'chart_rows': int,
                'warnings': []
            }
        """
        results = {
            'tenant': None,
            'modules': [],
            'chart': None,
            'chart_rows': 0,
            'warnings': [],
        }

        # Ensure TENADMIN is always included
        if 'TENADMIN' not in modules:
            modules = list(modules) + ['TENADMIN']

        # Step 1: Insert tenant record
        results['tenant'] = self._insert_tenant(
            administration, display_name, contact_email,
            created_by, phone_number, street, city, zipcode, country
        )

        # Step 2: Insert modules
        results['modules'] = self._insert_modules(administration, modules)

        # Step 3: Load chart of accounts from JSON template
        chart_result = self._load_chart_of_accounts(administration, locale, results['warnings'])
        results['chart'] = chart_result['status']
        results['chart_rows'] = chart_result['rows']

        logger.info(
            f"Provisioning complete for '{administration}': "
            f"tenant={results['tenant']}, "
            f"chart={results['chart']} ({results['chart_rows']} rows)"
        )
        return results

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _insert_tenant(
        self, administration, display_name, contact_email,
        created_by, phone_number, street, city, zipcode, country
    ) -> str:
        """Insert tenant record. Returns 'created' or 'skipped'."""
        existing = self.db.execute_query(
            "SELECT administration FROM tenants WHERE administration = %s",
            (administration,),
            fetch=True
        )
        if existing:
            logger.info(f"Tenant '{administration}' already exists — skipping insert")
            return 'skipped'

        self.db.execute_query(
            """
            INSERT INTO tenants (
                administration, display_name, status, contact_email,
                phone_number, street, city, zipcode, country,
                created_at, updated_at, updated_by
            ) VALUES (%s, %s, 'active', %s, %s, %s, %s, %s, %s, NOW(), NOW(), %s)
            """,
            (
                administration, display_name, contact_email,
                phone_number, street, city, zipcode, country, created_by
            ),
            commit=True
        )
        logger.info(f"Tenant '{administration}' inserted")
        return 'created'

    def _insert_modules(self, administration: str, modules: list) -> list:
        """Insert modules, skipping any that already exist."""
        results = []
        for module in modules:
            existing = self.db.execute_query(
                """
                SELECT id FROM tenant_modules
                WHERE administration = %s AND module_name = %s
                """,
                (administration, module),
                fetch=True
            )
            if existing:
                logger.info(f"Module '{module}' already exists for '{administration}' — skipping")
                results.append({'name': module, 'status': 'skipped'})
            else:
                self.db.execute_query(
                    """
                    INSERT INTO tenant_modules (administration, module_name, is_active, created_at)
                    VALUES (%s, %s, TRUE, NOW())
                    """,
                    (administration, module),
                    commit=True
                )
                logger.info(f"Module '{module}' inserted for '{administration}'")
                results.append({'name': module, 'status': 'created'})
        return results

    def _load_chart_of_accounts(
        self, administration: str, locale: str, warnings: list
    ) -> dict:
        """
        Load chart of accounts from JSON template and insert for tenant.
        Skips if the tenant already has chart rows.
        Falls back to 'nl' if the requested locale template doesn't exist.

        Returns {'status': 'created'|'skipped'|'failed', 'rows': int}
        """
        # Check if chart already exists for this tenant
        count_result = self.db.execute_query(
            "SELECT COUNT(*) as cnt FROM rekeningschema WHERE administration = %s",
            (administration,),
            fetch=True
        )
        existing_count = count_result[0]['cnt'] if count_result else 0
        if existing_count > 0:
            logger.info(
                f"Chart of accounts already exists for '{administration}' "
                f"({existing_count} rows) — skipping"
            )
            return {'status': 'skipped', 'rows': existing_count}

        # Resolve template path with locale fallback
        template_path = _TEMPLATE_DIR / f'{locale}.json'
        if not template_path.exists():
            fallback = _TEMPLATE_DIR / 'nl.json'
            if fallback.exists():
                msg = (
                    f"Chart template for locale '{locale}' not found, "
                    f"falling back to 'nl'"
                )
                logger.warning(msg)
                warnings.append(msg)
                template_path = fallback
            else:
                msg = (
                    f"Chart of accounts template not found at {template_path}. "
                    f"Tenant '{administration}' has no chart — add manually."
                )
                logger.error(msg)
                warnings.append(msg)
                return {'status': 'failed', 'rows': 0}

        # Load and insert
        try:
            with open(template_path, encoding='utf-8') as f:
                accounts = json.load(f)

            inserted = 0
            for account in accounts:
                self.db.execute_query(
                    """
                    INSERT INTO rekeningschema
                        (Account, AccountLookup, AccountName, SubParent, Parent,
                         VW, Belastingaangifte, administration, Pattern, parameters)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        account['Account'],
                        account.get('AccountLookup'),
                        account['AccountName'],
                        account['SubParent'],
                        account['Parent'],
                        account['VW'],
                        account.get('Belastingaangifte'),
                        administration,
                        account.get('Pattern', False),
                        json.dumps(account['parameters']) if account.get('parameters') else None,
                    ),
                    commit=True
                )
                inserted += 1

            logger.info(
                f"Chart of accounts loaded for '{administration}': "
                f"{inserted} rows from {template_path.name}"
            )
            return {'status': 'created', 'rows': inserted}

        except Exception as e:
            msg = (
                f"Failed to load chart of accounts for '{administration}': {e}. "
                f"Add chart manually."
            )
            logger.error(msg)
            warnings.append(msg)
            return {'status': 'failed', 'rows': 0}
