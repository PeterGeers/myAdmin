"""
Authentication module for myAdmin
Provides AWS Cognito integration and JWT token handling
"""

from .cognito_utils import (
    extract_user_credentials,
    validate_permissions,
    cognito_required,
    cors_headers,
    handle_options_request,
    create_error_response,
    create_success_response,
    log_successful_access
)

from .tenant_context import (
    get_user_tenants,
    get_current_tenant,
    is_tenant_admin,
    validate_tenant_access,
    tenant_required,
    add_tenant_filter,
    get_tenant_config,
    set_tenant_config
)

__all__ = [
    'extract_user_credentials',
    'validate_permissions',
    'cognito_required',
    'cors_headers',
    'handle_options_request',
    'create_error_response',
    'create_success_response',
    'log_successful_access',
    'get_user_tenants',
    'get_current_tenant',
    'is_tenant_admin',
    'validate_tenant_access',
    'tenant_required',
    'add_tenant_filter',
    'get_tenant_config',
    'set_tenant_config'
]
