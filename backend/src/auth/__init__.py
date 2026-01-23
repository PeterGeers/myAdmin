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

__all__ = [
    'extract_user_credentials',
    'validate_permissions',
    'cognito_required',
    'cors_headers',
    'handle_options_request',
    'create_error_response',
    'create_success_response',
    'log_successful_access'
]
