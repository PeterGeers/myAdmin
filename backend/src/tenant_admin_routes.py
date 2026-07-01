"""
Tenant Administration Routes — Shared Middleware and Helpers

This module provides the shared tenant_admin_bp blueprint with:
- Content Security Policy headers (applied to all routes in this blueprint)
- Shared helper functions for tenant admin operations

Route endpoints have been extracted to focused modules:
- Template endpoints → routes/tenant_admin_templates.py
- User management → routes/tenant_admin_users.py
- Config endpoints → routes/tenant_admin_config.py

Based on the architecture at .kiro/specs/Common/Multitennant/architecture.md
"""

from flask import Blueprint
from database import DatabaseManager
import os
import json
import boto3
import logging
from typing import Dict, Any, List

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint for tenant admin routes
# Note: This blueprint now only contains shared middleware (security headers).
# All route endpoints have been moved to dedicated modules.
tenant_admin_bp = Blueprint('tenant_admin', __name__)

# Initialize Cognito client
cognito_client = boto3.client('cognito-idp', region_name=os.getenv('AWS_REGION', 'eu-west-1'))
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')


# ============================================================================
# Shared Constants
# ============================================================================

# Canonical list of valid template types used across all template endpoints.
# Any new template type must be added here (Requirements 3.1, 3.2).
VALID_TEMPLATE_TYPES = [
    'str_invoice_nl', 'str_invoice_en',
    'btw_aangifte', 'aangifte_ib',
    'toeristenbelasting', 'financial_report',
    'zzp_invoice',
]


# ============================================================================
# Security: Content Security Policy Headers
# ============================================================================


@tenant_admin_bp.after_request
def add_security_headers(response):
    """
    Add Content Security Policy headers to all tenant admin responses.

    This provides defense-in-depth security for template preview and validation:
    - Prevents execution of inline scripts
    - Restricts resource loading to same origin
    - Blocks external resources
    - Prevents clickjacking

    Applied to all routes in this blueprint.
    """
    csp_policy = (
        "default-src 'self'; "
        "script-src 'none'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers['Content-Security-Policy'] = csp_policy

    # Additional security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    return response


# ============================================================================
# Helper Functions
# ============================================================================


def has_fin_module(tenant: str) -> bool:
    """
    Check if a tenant has the FIN module enabled.

    Args:
        tenant: The tenant administration name (e.g., 'GoodwinSolutions')

    Returns:
        True if tenant has FIN module and it's active, False otherwise
    """
    try:
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        query = """
            SELECT is_active
            FROM tenant_modules
            WHERE administration = %s AND module_name = 'FIN'
        """
        result = db.execute_query(query, (tenant,))

        return bool(result and result[0].get('is_active'))

    except Exception as e:
        logger.error(f"Error checking FIN module for tenant {tenant}: {e}")
        return False


def validate_account_number(account: str) -> str:
    """
    Validate and clean an account number.

    Args:
        account: The account number to validate

    Returns:
        The cleaned account number (trimmed of whitespace)

    Raises:
        ValueError: If account is None, empty, or only whitespace
    """
    if account is None:
        raise ValueError("Account number is required")

    cleaned = account.strip()

    if not cleaned:
        raise ValueError("Account number is required")

    return cleaned


def validate_account_name(name: str) -> str:
    """
    Validate and clean an account name.

    Args:
        name: The account name to validate

    Returns:
        The cleaned account name (trimmed of whitespace)

    Raises:
        ValueError: If name is None, empty, or only whitespace
    """
    if name is None:
        raise ValueError("Account name is required")

    cleaned = name.strip()

    if not cleaned:
        raise ValueError("Account name is required")

    return cleaned


def is_account_used_in_transactions(tenant: str, account: str) -> int:
    """
    Check if an account is used in any transactions.

    Queries the mutaties table to count how many transactions reference the
    given account in either the Debet or Credit columns.

    Args:
        tenant: The tenant administration name
        account: The account number to check

    Returns:
        Count of transactions using this account (0 if not used)
    """
    try:
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        query = """
            SELECT COUNT(*) as count
            FROM mutaties
            WHERE administration = %s
            AND (Debet = %s OR Credit = %s)
        """
        result = db.execute_query(query, (tenant, account, account))

        return result[0].get('count', 0) if result else 0

    except Exception as e:
        logger.error(f"Error checking account usage for {account} in tenant {tenant}: {e}")
        return 0


def get_user_attribute(user: Dict[str, Any], attribute_name: str) -> Any:
    """Extract attribute value from Cognito user object"""
    for attr in user.get('Attributes', []):
        if attr['Name'] == attribute_name:
            value = attr['Value']
            if attribute_name == 'custom:tenants':
                try:
                    return json.loads(value)
                except Exception:
                    return [value] if value else []
            return value
    return None


def get_user_groups(username: str) -> List[str]:
    """Get Cognito groups for a user"""
    try:
        response = cognito_client.admin_list_groups_for_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        return [group['GroupName'] for group in response.get('Groups', [])]
    except Exception as e:
        print(f"Error getting user groups: {e}", flush=True)
        return []
