"""
Unit tests for Tenant Isolation Enforcement on Unprotected Routes.

Tests verify:
- HTTP 403 when user lacks access to requested tenant (Requirement 2.8)
- HTTP 400 when check_sequence called without administration parameter (Requirement 2.10)
- Default tenant behavior when administration param is missing on PDF validation routes (Requirement 2.9)

Feature: security-hardening
Requirements: 2.8, 2.9, 2.10
Reference: .kiro/specs/security-hardening/design.md
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from flask import Flask
from routes.banking_routes import banking_bp, set_test_mode as banking_set_test_mode
from routes.pdf_validation_routes import pdf_validation_bp, set_test_mode as pdf_set_test_mode


# --- Helpers ---

def make_jwt_token(email='test@example.com', tenants=None, groups=None):
    """Create a fake JWT token with specified claims encoded in base64."""
    import base64
    if tenants is None:
        tenants = ['TenantA', 'TenantB']
    if groups is None:
        groups = ['Accountants']

    header = base64.urlsafe_b64encode(json.dumps({
        'alg': 'RS256', 'kid': 'test-kid'
    }).encode()).rstrip(b'=').decode()

    payload = base64.urlsafe_b64encode(json.dumps({
        'sub': 'user-uuid-123',
        'email': email,
        'cognito:groups': groups,
        'custom:tenants': json.dumps(tenants)
    }).encode()).rstrip(b'=').decode()

    signature = base64.urlsafe_b64encode(b'fake-signature').rstrip(b'=').decode()

    return f"{header}.{payload}.{signature}"


def bypass_cognito_required(user_email, user_roles):
    """
    Creates a decorator that bypasses cognito_required and injects
    user_email and user_roles into the route function.
    """
    def decorator_factory(required_roles=None, required_permissions=None):
        def decorator(f):
            import functools

            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                kwargs['user_email'] = user_email
                kwargs['user_roles'] = user_roles
                return f(*args, **kwargs)
            return wrapper
        return decorator
    return decorator_factory


# --- Test Fixtures ---

@pytest.fixture
def app_with_banking():
    """Create Flask app with banking blueprint and mocked auth."""
    test_email = 'test@example.com'
    test_roles = ['Accountants']
    test_tenants = ['TenantA', 'TenantB']

    with patch('routes.banking_routes.cognito_required',
               bypass_cognito_required(test_email, test_roles)):
        # We need to re-import the module to apply the patch on decorator
        # Instead, create a minimal Flask app and register a patched route
        pass

    # Use a different approach: patch extract_user_credentials and tenant_context
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(banking_bp)
    banking_set_test_mode(True)
    return app, test_email, test_roles, test_tenants


@pytest.fixture
def app_with_pdf():
    """Create Flask app with PDF validation blueprint and mocked auth."""
    test_email = 'test@example.com'
    test_roles = ['Accountants']
    test_tenants = ['TenantA', 'TenantB']

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(pdf_validation_bp)
    pdf_set_test_mode(True)
    return app, test_email, test_roles, test_tenants


# --- Tests: check_sequence endpoint (banking_routes.py) ---

class TestCheckSequenceTenantIsolation:
    """Tests for check_sequence endpoint tenant isolation."""

    def _make_request(self, app, params, tenant='TenantA', user_tenants=None):
        """Helper to make a request to check_sequence with mocked auth."""
        if user_tenants is None:
            user_tenants = ['TenantA', 'TenantB']

        token = make_jwt_token(tenants=user_tenants)

        with app.test_client() as client:
            with patch('auth.cognito_utils.extract_user_credentials') as mock_extract, \
                 patch('auth.tenant_context.get_current_tenant') as mock_tc, \
                 patch('auth.tenant_context.get_user_tenants') as mock_ut, \
                 patch('auth.role_cache.get_tenant_roles') as mock_roles:
                mock_extract.return_value = ('test@example.com', ['Finance_CRUD'], None)
                mock_tc.return_value = tenant
                mock_ut.return_value = user_tenants
                mock_roles.return_value = ['Finance_CRUD']

                response = client.get(
                    '/api/banking/check-sequence',
                    query_string=params,
                    headers={
                        'Authorization': f'Bearer {token}',
                        'X-Tenant': tenant
                    }
                )
            return response

    def test_check_sequence_403_when_administration_not_in_user_tenants(self, app_with_banking):
        """
        Requirement 2.8: If user does not have access to the requested tenant,
        return HTTP 403 with access denied message.
        """
        app, email, roles, tenants = app_with_banking

        # User has access to TenantA and TenantB, but requests TenantC
        response = self._make_request(
            app,
            params={'administration': 'TenantC', 'account_code': '1234'},
            tenant='TenantA',
            user_tenants=['TenantA', 'TenantB']
        )

        assert response.status_code == 403
        data = response.get_json()
        assert 'error' in data
        assert 'Access denied' in data['error'] or 'access denied' in data['error'].lower()

    def test_check_sequence_400_when_administration_missing(self, app_with_banking):
        """
        Requirement 2.10: If check_sequence receives request with missing
        administration parameter, return HTTP 400 with error message.
        """
        app, email, roles, tenants = app_with_banking

        # No administration parameter at all
        response = self._make_request(
            app,
            params={'account_code': '1234'},
            tenant='TenantA',
            user_tenants=['TenantA', 'TenantB']
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'Administration parameter is required' in data['error']

    def test_check_sequence_400_when_administration_empty(self, app_with_banking):
        """
        Requirement 2.10: If check_sequence receives request with empty
        administration parameter, return HTTP 400 with error message.
        """
        app, email, roles, tenants = app_with_banking

        # Empty administration parameter
        response = self._make_request(
            app,
            params={'administration': '', 'account_code': '1234'},
            tenant='TenantA',
            user_tenants=['TenantA', 'TenantB']
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'Administration parameter is required' in data['error']

    def test_check_sequence_400_when_administration_whitespace_only(self, app_with_banking):
        """
        Requirement 2.10: Whitespace-only administration is treated as missing.
        """
        app, email, roles, tenants = app_with_banking

        response = self._make_request(
            app,
            params={'administration': '   ', 'account_code': '1234'},
            tenant='TenantA',
            user_tenants=['TenantA', 'TenantB']
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'Administration parameter is required' in data['error']

    @patch('banking_processor.BankingProcessor', autospec=True)
    def test_check_sequence_success_when_administration_in_user_tenants(
            self, mock_processor_cls, app_with_banking):
        """
        Verify check_sequence succeeds when administration is in user's tenants.
        """
        app, email, roles, tenants = app_with_banking

        mock_processor = MagicMock()
        mock_processor.check_sequence_numbers.return_value = {'success': True, 'gaps': []}
        mock_processor_cls.return_value = mock_processor

        response = self._make_request(
            app,
            params={'administration': 'TenantA', 'account_code': '1234'},
            tenant='TenantA',
            user_tenants=['TenantA', 'TenantB']
        )

        assert response.status_code == 200


# --- Tests: PDF validation routes ---

class TestPdfValidationTenantIsolation:
    """Tests for PDF validation endpoint tenant isolation."""

    def _make_request(self, app, endpoint, params, tenant='TenantA', user_tenants=None):
        """Helper to make a request to PDF validation with mocked auth."""
        if user_tenants is None:
            user_tenants = ['TenantA', 'TenantB']

        token = make_jwt_token(tenants=user_tenants)

        with app.test_client() as client:
            with patch('auth.cognito_utils.extract_user_credentials') as mock_extract, \
                 patch('auth.tenant_context.get_current_tenant') as mock_tc, \
                 patch('auth.tenant_context.get_user_tenants') as mock_ut, \
                 patch('auth.role_cache.get_tenant_roles') as mock_roles:
                mock_extract.return_value = ('test@example.com', ['Finance_CRUD'], None)
                mock_tc.return_value = tenant
                mock_ut.return_value = user_tenants
                mock_roles.return_value = ['Finance_CRUD']

                response = client.get(
                    endpoint,
                    query_string=params,
                    headers={
                        'Authorization': f'Bearer {token}',
                        'X-Tenant': tenant
                    }
                )
            return response

    def test_pdf_validate_urls_stream_403_when_administration_not_in_tenants(self, app_with_pdf):
        """
        Requirement 2.8: pdf_validate_urls_stream returns 403 when user
        requests administration they don't have access to.
        """
        app, email, roles, tenants = app_with_pdf

        response = self._make_request(
            app,
            endpoint='/api/pdf/validate-urls-stream',
            params={'administration': 'UnauthorizedTenant', 'year': '2025'},
            tenant='TenantA',
            user_tenants=['TenantA', 'TenantB']
        )

        assert response.status_code == 403
        # SSE endpoint may return JSON or stream, check for 403 status
        data = response.get_json()
        if data:
            assert 'error' in data or 'Access denied' in str(data)

    def test_pdf_validate_urls_403_when_administration_not_in_tenants(self, app_with_pdf):
        """
        Requirement 2.8: pdf_validate_urls returns 403 when user
        requests administration they don't have access to.
        """
        app, email, roles, tenants = app_with_pdf

        response = self._make_request(
            app,
            endpoint='/api/pdf/validate-urls',
            params={'administration': 'UnauthorizedTenant', 'year': '2025'},
            tenant='TenantA',
            user_tenants=['TenantA', 'TenantB']
        )

        assert response.status_code == 403
        data = response.get_json()
        assert data is not None
        assert 'error' in data or 'Access denied' in str(data)

    @patch('routes.pdf_validation_routes.PDFValidator')
    def test_pdf_validate_urls_defaults_to_tenant_when_no_administration(
            self, mock_validator_cls, app_with_pdf):
        """
        Requirement 2.9: When administration parameter is missing,
        PDF validation routes default to user's current tenant.
        """
        app, email, roles, tenants = app_with_pdf

        mock_validator = MagicMock()
        mock_validator.validate_pdf_urls_with_progress.return_value = iter([
            {'validation_results': [], 'total': 0, 'ok_count': 0, 'failed_count': 0}
        ])
        mock_validator_cls.return_value = mock_validator

        response = self._make_request(
            app,
            endpoint='/api/pdf/validate-urls',
            params={'year': '2025'},  # No administration param
            tenant='TenantA',
            user_tenants=['TenantA', 'TenantB']
        )

        # Should NOT return 400 or 403 - should succeed with default tenant
        assert response.status_code == 200
        # Verify the validator was called with the default tenant (TenantA)
        mock_validator.validate_pdf_urls_with_progress.assert_called_once_with('2025', 'TenantA')

    @patch('routes.pdf_validation_routes.PDFValidator')
    def test_pdf_validate_urls_defaults_to_tenant_when_administration_empty(
            self, mock_validator_cls, app_with_pdf):
        """
        Requirement 2.9: When administration parameter is empty string,
        PDF validation routes default to user's current tenant.
        """
        app, email, roles, tenants = app_with_pdf

        mock_validator = MagicMock()
        mock_validator.validate_pdf_urls_with_progress.return_value = iter([
            {'validation_results': [], 'total': 0, 'ok_count': 0, 'failed_count': 0}
        ])
        mock_validator_cls.return_value = mock_validator

        response = self._make_request(
            app,
            endpoint='/api/pdf/validate-urls',
            params={'year': '2025', 'administration': ''},  # Empty administration
            tenant='TenantA',
            user_tenants=['TenantA', 'TenantB']
        )

        # Should succeed with default tenant, not error
        assert response.status_code == 200
        mock_validator.validate_pdf_urls_with_progress.assert_called_once_with('2025', 'TenantA')

    @patch('routes.pdf_validation_routes.PDFValidator')
    def test_pdf_validate_urls_stream_defaults_to_tenant_when_no_administration(
            self, mock_validator_cls, app_with_pdf):
        """
        Requirement 2.9: pdf_validate_urls_stream defaults to user's
        current tenant when administration parameter is missing.
        """
        app, email, roles, tenants = app_with_pdf

        mock_validator = MagicMock()
        mock_validator.validate_pdf_urls_with_progress.return_value = iter([
            {'validation_results': [], 'total': 0, 'ok_count': 0, 'failed_count': 0}
        ])
        mock_validator_cls.return_value = mock_validator

        response = self._make_request(
            app,
            endpoint='/api/pdf/validate-urls-stream',
            params={'year': '2025'},  # No administration param
            tenant='TenantA',
            user_tenants=['TenantA', 'TenantB']
        )

        # Should NOT return 400 or 403 - the endpoint streams, so check it's 200
        assert response.status_code == 200
