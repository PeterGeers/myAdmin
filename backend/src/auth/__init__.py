"""
Authentication module for myAdmin
Provides AWS Cognito integration and JWT token handling
"""

from .cognito_utils import (
    cognito_required,
    cors_headers,
    create_error_response,
    create_success_response,
    extract_user_credentials,
    handle_options_request,
    log_successful_access,
    validate_permissions,
)
from .rate_limiter import RateLimiter, RateLimitResult
from .tenant_context import (
    add_tenant_filter,
    get_current_tenant,
    get_tenant_config,
    get_user_tenants,
    is_tenant_admin,
    set_tenant_config,
    tenant_required,
    validate_tenant_access,
)

__all__ = [
    "RateLimitResult",
    "RateLimiter",
    "add_tenant_filter",
    "cognito_required",
    "cors_headers",
    "create_error_response",
    "create_success_response",
    "extract_user_credentials",
    "get_current_tenant",
    "get_tenant_config",
    "get_user_tenants",
    "handle_options_request",
    "is_tenant_admin",
    "log_successful_access",
    "set_tenant_config",
    "tenant_required",
    "validate_permissions",
    "validate_tenant_access",
]
