"""
Shared fixtures for API tests.

Provides Flask test client, mock authentication, and mock AWS service fixtures
for all tests under backend/tests/api/.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask


@pytest.fixture
def app(mock_env):
    """
    Create Flask app with all blueprints registered for testing.

    Uses mock_env to ensure no real environment variables leak in.
    Patches auth internals so blueprint registration doesn't trigger
    real Cognito or DB calls.
    """
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.role_cache.get_tenant_roles', return_value=['TenantAdmin']), \
         patch('database.DatabaseManager') as mock_db_class:

        mock_creds.return_value = ('test@example.com', ['TenantAdmin'], None)
        mock_db_class.return_value = MagicMock()

        from src.app import app as flask_app
        flask_app.config['TESTING'] = True
        yield flask_app


@pytest.fixture
def client(app):
    """
    Flask test client with application context.

    Wraps app.test_client() inside an application context so that
    request-scoped operations (like url_for) work correctly.
    """
    with app.test_client() as test_client:
        with app.app_context():
            yield test_client


@pytest.fixture
def mock_auth():
    """
    Mock authentication returning TenantAdmin credentials.

    Patches extract_user_credentials to return a valid TenantAdmin user
    without requiring a real JWT token. Also patches tenant validation
    and role cache to allow tenant-scoped requests.

    Yields a dict with the Authorization header to include in requests
    and an X-Tenant header for tenant context.
    """
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['TenantAdmin']):

        mock_creds.return_value = ('test@example.com', ['TenantAdmin'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


@pytest.fixture
def mock_auth_sysadmin():
    """
    Mock authentication returning SysAdmin credentials.

    Patches extract_user_credentials to return a SysAdmin user who
    bypasses tenant validation. Useful for testing sysadmin-only routes.

    Yields a dict with the Authorization header to include in requests.
    """
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=[]), \
         patch('auth.role_cache.get_tenant_roles', return_value=['SysAdmin']):

        mock_creds.return_value = ('admin@myadmin.com', ['SysAdmin'], None)
        yield {
            'Authorization': 'Bearer sysadmin-token',
        }


@pytest.fixture
def mock_sns():
    """
    Mock AWS SNS publish calls.

    Patches boto3.client to return a mock SNS client with a successful
    publish response. Useful for testing notification-related endpoints.

    Yields the mock SNS client instance for assertion on publish calls.
    """
    with patch('boto3.client') as mock_client:
        mock_sns_client = MagicMock()
        mock_client.return_value = mock_sns_client
        mock_sns_client.publish.return_value = {'MessageId': 'test-msg-id'}
        yield mock_sns_client
