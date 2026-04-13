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
