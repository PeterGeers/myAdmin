"""
ModuleRegistry: In-code Python dictionary defining required parameters,
tax rates, and roles per module.

Provides has_module() to check if a tenant has a module enabled, and
module_required() decorator to enforce module access on Flask routes.

Requirements: 4.1, 4.4, 4.5, 4.6
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import functools
import logging
import os
from typing import Dict

from flask import jsonify

logger = logging.getLogger(__name__)

MODULE_REGISTRY: Dict[str, dict] = {
    'FIN': {
        'description': 'Financial Administration',
        'required_params': {
            'fin.default_currency': {'type': 'string', 'default': 'EUR'},
            'fin.fiscal_year_start_month': {'type': 'number', 'default': 1},
            'fin.locale': {'type': 'string', 'default': 'nl'},
        },
        'required_tax_rates': ['btw'],
        'required_roles': ['Finance_Read', 'Finance_Write'],
    },
    'STR': {
        'description': 'Short-Term Rental Management',
        'required_params': {
            'str.aantal_kamers': {'type': 'number', 'default': None},
            'str.aantal_slaapplaatsen': {'type': 'number', 'default': None},
            'str.platforms': {'type': 'json', 'default': ['airbnb', 'booking']},
        },
        'required_tax_rates': ['tourist_tax', 'btw_accommodation'],
        'required_roles': ['STR_Read', 'STR_Write'],
    },
    'TENADMIN': {
        'description': 'Tenant Administration',
        'required_params': {},
        'required_tax_rates': [],
        'required_roles': ['Tenant_Admin'],
    },
    'ZZP': {
        'description': 'ZZP Freelancer Administration',
        'depends_on': ['FIN'],
        'required_params': {
            'zzp.invoice_prefix': {'type': 'string', 'default': 'INV'},
            'zzp.credit_note_prefix': {'type': 'string', 'default': 'CN'},
            'zzp.default_payment_terms_days': {'type': 'number', 'default': 30},
            'zzp.default_currency': {'type': 'string', 'default': 'EUR'},
            'zzp.invoice_number_padding': {'type': 'number', 'default': 4},
            'zzp.debtor_account': {'type': 'string', 'default': '1300'},
            'zzp.creditor_account': {'type': 'string', 'default': '1600'},
            'zzp.email_subject_template': {
                'type': 'string',
                'default': 'Factuur {invoice_number} - {company_name}',
            },
            'zzp.invoice_email_bcc': {'type': 'string', 'default': ''},
            'zzp.retention_years': {'type': 'number', 'default': 7},
            'zzp.time_tracking_enabled': {'type': 'boolean', 'default': True},
            'zzp.product_types': {'type': 'json', 'default': ['service', 'product', 'hours', 'subscription']},
            'zzp.contact_types': {'type': 'json', 'default': ['client', 'supplier', 'both', 'other']},
            'zzp.contact_field_config': {
                'type': 'json',
                'default': {
                    'client_id': 'required',
                    'contact_type': 'required',
                    'company_name': 'required',
                    'contact_person': 'optional',
                    'street_address': 'optional',
                    'postal_code': 'optional',
                    'city': 'optional',
                    'country': 'optional',
                    'vat_number': 'optional',
                    'kvk_number': 'optional',
                    'phone': 'optional',
                    'iban': 'optional',
                    'emails': 'optional',
                }
            },
            'zzp.product_field_config': {
                'type': 'json',
                'default': {
                    'product_code': 'required',
                    'name': 'required',
                    'product_type': 'required',
                    'unit_price': 'required',
                    'vat_code': 'required',
                    'description': 'optional',
                    'unit_of_measure': 'optional',
                    'external_reference': 'optional',
                }
            },
            'zzp.invoice_field_config': {
                'type': 'json',
                'default': {
                    'contact_id': 'required',
                    'invoice_date': 'required',
                    'payment_terms_days': 'required',
                    'currency': 'optional',
                    'exchange_rate': 'hidden',
                    'notes': 'optional',
                }
            },
            'zzp.time_entry_field_config': {
                'type': 'json',
                'default': {
                    'contact_id': 'required',
                    'entry_date': 'required',
                    'hours': 'required',
                    'hourly_rate': 'required',
                    'product_id': 'optional',
                    'project_name': 'optional',
                    'description': 'optional',
                    'is_billable': 'optional',
                }
            },
        },
        'required_tax_rates': ['btw'],
        'required_roles': ['ZZP_Read', 'ZZP_Write'],
    },
}


def has_module(db, tenant: str, module_name: str) -> bool:
    """
    Check if a tenant has a specific module enabled.
    Replaces the duplicated has_fin_module() function.

    Args:
        db: DatabaseManager instance
        tenant: The tenant administration name
        module_name: Module name (e.g. 'FIN', 'STR', 'TENADMIN')

    Returns:
        True if the module exists and is active for the tenant.
    """
    try:
        query = """
            SELECT is_active
            FROM tenant_modules
            WHERE administration = %s AND module_name = %s
        """
        result = db.execute_query(query, (tenant, module_name))
        return bool(result and result[0].get('is_active'))
    except Exception as e:
        logger.error("Error checking module %s for tenant %s: %s", module_name, tenant, e)
        return False


def module_required(module_name: str):
    """
    Decorator that checks whether the current tenant has the specified module enabled.
    Returns HTTP 403 if the module is not active.

    Must be used after @tenant_required() which injects 'tenant' into kwargs.

    Usage:
        @app.route('/api/fin/accounts')
        @cognito_required(required_permissions=[])
        @tenant_required()
        @module_required('FIN')
        def get_accounts(user_email, user_roles, tenant, user_tenants):
            ...
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            tenant = kwargs.get('tenant')
            if not tenant:
                return jsonify({'error': 'Tenant context required'}), 403

            from database import DatabaseManager
            test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
            db = DatabaseManager(test_mode=test_mode)

            if not has_module(db, tenant, module_name):
                return jsonify({
                    'error': f'{module_name} module not enabled for this tenant'
                }), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator



def activate_module(db, tenant: str, module_name: str, activated_by: str = 'system') -> bool:
    """
    Activate a module for a tenant, enforcing dependency checks.

    Checks that all modules listed in 'depends_on' are already active
    for the tenant before allowing activation.

    Args:
        db: DatabaseManager instance
        tenant: The tenant administration name
        module_name: Module name to activate (e.g. 'ZZP')
        activated_by: User or system identifier

    Returns:
        True if activation succeeded.

    Raises:
        ValueError: If module is unknown or dependencies are not met.
    """
    module_def = MODULE_REGISTRY.get(module_name)
    if not module_def:
        raise ValueError(f"Unknown module: {module_name}")

    for dep in module_def.get('depends_on', []):
        if not has_module(db, tenant, dep):
            raise ValueError(
                f"Module '{dep}' must be active before enabling '{module_name}'"
            )

    try:
        query = """
            INSERT INTO tenant_modules (administration, module_name, is_active, created_by)
            VALUES (%s, %s, TRUE, %s)
            ON DUPLICATE KEY UPDATE is_active = TRUE, updated_at = CURRENT_TIMESTAMP
        """
        db.execute_query(query, (tenant, module_name, activated_by), fetch=False, commit=True)
        logger.info("Module %s activated for tenant %s by %s", module_name, tenant, activated_by)
        return True
    except Exception as e:
        logger.error("Failed to activate module %s for tenant %s: %s", module_name, tenant, e)
        raise
