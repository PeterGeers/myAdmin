"""
Integration Tests for SES Email Verification

Tests the full integration of the email verification feature:
1. Full provisioning flow triggers verification initiation
2. API endpoint authentication and authorization
3. End-to-end status check flow (API → Service → SES mock → DB → response)

Requirements: 1.1, 8.4, 8.5
Reference: .kiro/specs/ses-email-verification/design.md
"""

import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock, call
from functools import wraps
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from flask import Flask
from routes.verification_routes import verification_bp


# ---------------------------------------------------------------------------
# Auth helper: passthrough decorators for integration tests
# ---------------------------------------------------------------------------

def _passthrough_cognito(required_roles=None, required_permissions=None):
    """Mock cognito_required to inject test user credentials."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'admin@test-tenant.com'
            kwargs['user_roles'] = ['Tenant_Admin']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant(allow_sysadmin=False):
    """Mock tenant_required to inject test tenant context."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = 'IntegrationTestTenant'
            kwargs['user_tenants'] = ['IntegrationTestTenant']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_cognito_no_permission(required_roles=None, required_permissions=None):
    """Mock cognito_required that simulates a user without admin_manage permission."""
    from flask import jsonify

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Simulate permission check failure
            return jsonify({
                'error': 'Insufficient permissions',
                'details': 'Missing permissions: admin_manage'
            }), 403
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Test: Full provisioning flow triggers verification initiation
# Requirements: 1.1
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestProvisioningTriggersVerification:
    """Test that the full provisioning flow triggers email verification."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock DatabaseManager that simulates DB operations."""
        db = MagicMock()
        # Default: no existing tenant, no existing modules, no existing chart
        db.execute_query.return_value = []
        return db

    @pytest.fixture
    def mock_ses_client(self):
        """Create a mock SES client."""
        client = MagicMock()
        client.verify_email_identity.return_value = {}
        return client

    def test_provisioning_calls_initiate_verification(self, mock_db, mock_ses_client):
        """When a tenant is provisioned, initiate_verification is called with contact email."""
        from services.tenant_provisioning_service import TenantProvisioningService

        service = TenantProvisioningService(db_manager=mock_db)

        # Mock the template directory to avoid file system dependency
        with patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir, \
             patch('services.email_verification_service.boto3.client', return_value=mock_ses_client), \
             patch('services.parameter_service.ParameterService') as MockParamService:

            mock_dir.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
            MockParamService.return_value.seed_module_params.return_value = 0
            MockParamService.return_value.set_param.return_value = None

            result = service.create_and_provision_tenant(
                administration='NewTestTenant',
                display_name='New Test Tenant',
                contact_email='contact@newtenant.com',
                modules=['FIN', 'TENADMIN'],
                created_by='sysadmin@test.com',
                locale='nl',
            )

        # Verify email verification was initiated
        assert 'email_verification' in result
        assert result['email_verification']['success'] is True
        assert result['email_verification']['status'] == 'pending'

        # Verify SES was called with the contact email
        mock_ses_client.verify_email_identity.assert_called_once_with(
            EmailAddress='contact@newtenant.com'
        )

    def test_provisioning_continues_on_verification_failure(self, mock_db):
        """Provisioning does not fail when email verification fails."""
        from services.tenant_provisioning_service import TenantProvisioningService

        service = TenantProvisioningService(db_manager=mock_db)

        # Make SES client raise an error
        mock_ses_failing = MagicMock()
        from botocore.exceptions import ClientError
        mock_ses_failing.verify_email_identity.side_effect = ClientError(
            {'Error': {'Code': 'Throttling', 'Message': 'Rate exceeded'}},
            'VerifyEmailIdentity'
        )

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir, \
             patch('services.email_verification_service.boto3.client', return_value=mock_ses_failing), \
             patch('services.parameter_service.ParameterService') as MockParamService:

            mock_dir.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
            MockParamService.return_value.seed_module_params.return_value = 0
            MockParamService.return_value.set_param.return_value = None

            result = service.create_and_provision_tenant(
                administration='FailVerifyTenant',
                display_name='Fail Verify Tenant',
                contact_email='fail@tenant.com',
                modules=['FIN', 'TENADMIN'],
                created_by='sysadmin@test.com',
                locale='nl',
            )

        # Provisioning should still complete (tenant record created)
        assert result['tenant'] is not None
        # Verification should report failure but not raise
        assert result['email_verification']['success'] is False
        assert result['email_verification']['status'] == 'failed'

    def test_provisioning_stores_pending_record_in_db(self, mock_ses_client):
        """Provisioning stores a pending verification record in the database."""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = []

        from services.tenant_provisioning_service import TenantProvisioningService

        service = TenantProvisioningService(db_manager=mock_db)

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir, \
             patch('services.email_verification_service.boto3.client', return_value=mock_ses_client), \
             patch('services.parameter_service.ParameterService') as MockParamService:

            mock_dir.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
            MockParamService.return_value.seed_module_params.return_value = 0
            MockParamService.return_value.set_param.return_value = None

            service.create_and_provision_tenant(
                administration='DBRecordTenant',
                display_name='DB Record Tenant',
                contact_email='record@tenant.com',
                modules=['FIN', 'TENADMIN'],
                created_by='sysadmin@test.com',
                locale='nl',
            )

        # Find the INSERT call for email_verifications
        insert_calls = [
            c for c in mock_db.execute_query.call_args_list
            if c[0] and 'email_verifications' in str(c[0][0])
            and 'INSERT' in str(c[0][0]).upper()
        ]
        assert len(insert_calls) >= 1, "Expected INSERT into email_verifications"

        # Verify the record contains the correct data
        insert_call = insert_calls[0]
        params = insert_call[0][1]  # positional args: (query, params)
        assert 'DBRecordTenant' in params
        assert 'record@tenant.com' in params
        assert 'pending' in params


# ---------------------------------------------------------------------------
# Test: API endpoint authentication and authorization
# Requirements: 8.4, 8.5
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAPIEndpointAuthIntegration:
    """Test API endpoint authentication and authorization in an integrated context."""

    @pytest.fixture
    def authenticated_client(self):
        """Create Flask test client with authenticated admin user."""
        with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
             patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant):
            import importlib
            import routes.verification_routes as vr
            importlib.reload(vr)

            app = Flask(__name__)
            app.config['TESTING'] = True
            app.register_blueprint(vr.verification_bp)
            yield app.test_client()

    @pytest.fixture
    def unauthenticated_client(self):
        """Create Flask test client without authentication (no auth bypass)."""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(verification_bp)
        return app.test_client()

    @pytest.fixture
    def no_permission_client(self):
        """Create Flask test client with user lacking admin_manage permission."""
        with patch('auth.cognito_utils.cognito_required',
                   side_effect=_passthrough_cognito_no_permission), \
             patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant):
            import importlib
            import routes.verification_routes as vr
            importlib.reload(vr)

            app = Flask(__name__)
            app.config['TESTING'] = True
            app.register_blueprint(vr.verification_bp)
            yield app.test_client()

    def test_get_status_accessible_with_admin_manage(self, authenticated_client):
        """GET /sender-verification is accessible with admin_manage permission."""
        mock_service = MagicMock()
        mock_service.check_status.return_value = {
            'email': 'admin@test-tenant.com',
            'status': 'verified',
            'last_checked': '2025-01-15T10:30:00Z',
        }

        with patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService',
                   return_value=mock_service):
            resp = authenticated_client.get('/api/tenant-admin/sender-verification')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['status'] == 'verified'

    def test_resend_accessible_with_admin_manage(self, authenticated_client):
        """POST /sender-verification/resend is accessible with admin_manage permission."""
        mock_service = MagicMock()
        mock_service.resend_verification.return_value = {
            'success': True,
            'error': None,
        }

        with patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService',
                   return_value=mock_service):
            resp = authenticated_client.post('/api/tenant-admin/sender-verification/resend')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_update_email_accessible_with_admin_manage(self, authenticated_client):
        """PUT /sender-verification/email is accessible with admin_manage permission."""
        mock_service = MagicMock()
        mock_service.update_email.return_value = {
            'success': True,
            'status': 'pending',
        }

        with patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService',
                   return_value=mock_service):
            resp = authenticated_client.put(
                '/api/tenant-admin/sender-verification/email',
                json={'email': 'new@example.com'},
                content_type='application/json',
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['status'] == 'pending'

    def test_unauthenticated_request_returns_401(self, unauthenticated_client):
        """Request without Authorization header returns 401."""
        resp = unauthenticated_client.get('/api/tenant-admin/sender-verification')
        assert resp.status_code == 401

    def test_no_permission_returns_403(self, no_permission_client):
        """Request without admin_manage permission returns 403."""
        resp = no_permission_client.get('/api/tenant-admin/sender-verification')
        assert resp.status_code == 403

    def test_all_endpoints_enforce_tenant_isolation(self, authenticated_client):
        """All endpoints pass the authenticated tenant to the service layer."""
        mock_service = MagicMock()
        mock_service.check_status.return_value = {
            'email': 'test@example.com',
            'status': 'pending',
            'last_checked': None,
        }
        mock_service.resend_verification.return_value = {'success': True, 'error': None}
        mock_service.update_email.return_value = {'success': True, 'status': 'pending'}

        with patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService',
                   return_value=mock_service):

            # GET
            authenticated_client.get('/api/tenant-admin/sender-verification')
            mock_service.check_status.assert_called_with('IntegrationTestTenant')

            # POST resend
            authenticated_client.post('/api/tenant-admin/sender-verification/resend')
            mock_service.resend_verification.assert_called_with('IntegrationTestTenant')

            # PUT email
            authenticated_client.put(
                '/api/tenant-admin/sender-verification/email',
                json={'email': 'new@example.com'},
                content_type='application/json',
            )
            mock_service.update_email.assert_called_with(
                'IntegrationTestTenant', 'new@example.com'
            )


# ---------------------------------------------------------------------------
# Test: End-to-end status check flow
# (API → Service → SES mock → DB → response)
# Requirements: 1.1, 8.4, 8.5
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestEndToEndStatusCheckFlow:
    """Test the full status check flow from API through service to SES and DB."""

    @pytest.fixture
    def app_and_client(self):
        """Create Flask app with mocked auth but real service wiring."""
        with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
             patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant):
            import importlib
            import routes.verification_routes as vr
            importlib.reload(vr)

            app = Flask(__name__)
            app.config['TESTING'] = True
            app.register_blueprint(vr.verification_bp)
            yield app, app.test_client()

    def test_status_check_verified_flow(self, app_and_client):
        """
        End-to-end: GET status → service queries SES → SES returns 'Success'
        → DB updated to 'verified' → response contains verified status.
        """
        app, client = app_and_client

        mock_db = MagicMock()
        # Simulate existing pending record in DB
        mock_db.execute_query.side_effect = self._db_side_effect_with_record(
            email='tenant@example.com',
            status='pending',
        )

        mock_ses = MagicMock()
        mock_ses.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {
                'tenant@example.com': {
                    'VerificationStatus': 'Success'
                }
            }
        }

        with patch('routes.verification_routes.DatabaseManager', return_value=mock_db), \
             patch('services.email_verification_service.boto3.client', return_value=mock_ses):
            resp = client.get('/api/tenant-admin/sender-verification')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['email'] == 'tenant@example.com'
        assert data['data']['status'] == 'verified'
        assert data['data']['last_checked'] is not None
        assert data['data']['fallback_sender'] == 'myAdmin <support@jabaki.nl>'

    def test_status_check_pending_flow(self, app_and_client):
        """
        End-to-end: GET status → SES returns 'Pending' → response shows pending.
        """
        app, client = app_and_client

        mock_db = MagicMock()
        mock_db.execute_query.side_effect = self._db_side_effect_with_record(
            email='waiting@example.com',
            status='pending',
        )

        mock_ses = MagicMock()
        mock_ses.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {
                'waiting@example.com': {
                    'VerificationStatus': 'Pending'
                }
            }
        }

        with patch('routes.verification_routes.DatabaseManager', return_value=mock_db), \
             patch('services.email_verification_service.boto3.client', return_value=mock_ses):
            resp = client.get('/api/tenant-admin/sender-verification')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['data']['status'] == 'pending'
        assert data['data']['email'] == 'waiting@example.com'

    def test_status_check_failed_flow(self, app_and_client):
        """
        End-to-end: GET status → SES returns 'Failed' → response shows failed.
        """
        app, client = app_and_client

        mock_db = MagicMock()
        mock_db.execute_query.side_effect = self._db_side_effect_with_record(
            email='failed@example.com',
            status='pending',
        )

        mock_ses = MagicMock()
        mock_ses.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {
                'failed@example.com': {
                    'VerificationStatus': 'Failed'
                }
            }
        }

        with patch('routes.verification_routes.DatabaseManager', return_value=mock_db), \
             patch('services.email_verification_service.boto3.client', return_value=mock_ses):
            resp = client.get('/api/tenant-admin/sender-verification')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['data']['status'] == 'failed'

    def test_status_check_no_record_flow(self, app_and_client):
        """
        End-to-end: GET status → no DB record → response shows null status.
        """
        app, client = app_and_client

        mock_db = MagicMock()
        # No records in DB
        mock_db.execute_query.return_value = []

        mock_ses = MagicMock()

        with patch('routes.verification_routes.DatabaseManager', return_value=mock_db), \
             patch('services.email_verification_service.boto3.client', return_value=mock_ses):
            resp = client.get('/api/tenant-admin/sender-verification')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['email'] is None
        assert data['data']['status'] is None

        # SES should NOT be called when there's no record
        mock_ses.get_identity_verification_attributes.assert_not_called()

    def test_status_check_ses_failure_returns_cached(self, app_and_client):
        """
        End-to-end: GET status → SES call fails → response returns cached DB status.
        """
        app, client = app_and_client

        mock_db = MagicMock()
        mock_db.execute_query.side_effect = self._db_side_effect_with_record(
            email='cached@example.com',
            status='pending',
            last_checked_at=datetime(2025, 1, 10, 8, 0, 0),
        )

        mock_ses = MagicMock()
        from botocore.exceptions import ClientError
        mock_ses.get_identity_verification_attributes.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable', 'Message': 'SES is down'}},
            'GetIdentityVerificationAttributes'
        )

        with patch('routes.verification_routes.DatabaseManager', return_value=mock_db), \
             patch('services.email_verification_service.boto3.client', return_value=mock_ses):
            resp = client.get('/api/tenant-admin/sender-verification')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        # Should return cached status from DB
        assert data['data']['email'] == 'cached@example.com'
        assert data['data']['status'] == 'pending'

    def test_resend_end_to_end_success(self, app_and_client):
        """
        End-to-end: POST resend → service checks rate limit → calls SES → updates DB.
        """
        app, client = app_and_client

        mock_db = MagicMock()
        # Return a record with no recent resend (last_resend_at is None)
        mock_db.execute_query.side_effect = self._db_side_effect_with_record(
            email='resend@example.com',
            status='pending',
            last_resend_at=None,
        )

        mock_ses = MagicMock()
        mock_ses.verify_email_identity.return_value = {}

        with patch('routes.verification_routes.DatabaseManager', return_value=mock_db), \
             patch('services.email_verification_service.boto3.client', return_value=mock_ses):
            resp = client.post('/api/tenant-admin/sender-verification/resend')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['message'] == 'Verification email resent'

        # SES should have been called
        mock_ses.verify_email_identity.assert_called_once_with(
            EmailAddress='resend@example.com'
        )

    def test_resend_end_to_end_rate_limited(self, app_and_client):
        """
        End-to-end: POST resend → rate limit hit (resent < 60s ago) → 429.
        """
        app, client = app_and_client

        mock_db = MagicMock()
        # Return a record with very recent resend
        mock_db.execute_query.side_effect = self._db_side_effect_with_record(
            email='ratelimit@example.com',
            status='pending',
            last_resend_at=datetime.utcnow() - timedelta(seconds=10),
        )

        mock_ses = MagicMock()

        with patch('routes.verification_routes.DatabaseManager', return_value=mock_db), \
             patch('services.email_verification_service.boto3.client', return_value=mock_ses):
            resp = client.post('/api/tenant-admin/sender-verification/resend')

        assert resp.status_code == 429
        data = resp.get_json()
        assert data['success'] is False
        assert '60 seconds' in data['error']

        # SES should NOT have been called
        mock_ses.verify_email_identity.assert_not_called()

    def test_update_email_end_to_end(self, app_and_client):
        """
        End-to-end: PUT email → marks old as replaced → initiates new verification.
        """
        app, client = app_and_client

        mock_db = MagicMock()
        mock_db.execute_query.return_value = []

        mock_ses = MagicMock()
        mock_ses.verify_email_identity.return_value = {}

        with patch('routes.verification_routes.DatabaseManager', return_value=mock_db), \
             patch('services.email_verification_service.boto3.client', return_value=mock_ses):
            resp = client.put(
                '/api/tenant-admin/sender-verification/email',
                json={'email': 'updated@newdomain.com'},
                content_type='application/json',
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['email'] == 'updated@newdomain.com'
        assert data['data']['status'] == 'pending'

        # SES should have been called with the new email
        mock_ses.verify_email_identity.assert_called_once_with(
            EmailAddress='updated@newdomain.com'
        )

        # DB should have been called to mark old records as replaced
        update_calls = [
            c for c in mock_db.execute_query.call_args_list
            if c[0] and "status = 'replaced'" in str(c[0][0])
        ]
        assert len(update_calls) >= 1, "Expected UPDATE to mark old records as replaced"

    # -------------------------------------------------------------------------
    # Helper: DB side effect factory
    # -------------------------------------------------------------------------

    @staticmethod
    def _db_side_effect_with_record(email, status, last_checked_at=None,
                                    last_resend_at=None):
        """
        Create a side_effect function for mock_db.execute_query that returns
        a verification record for SELECT queries and None for writes.
        """
        record = {
            'email': email,
            'status': status,
            'last_checked_at': last_checked_at,
            'last_resend_at': last_resend_at,
            'initiated_at': datetime(2025, 1, 1, 12, 0, 0),
            'verified_at': None,
        }

        def side_effect(query, params=None, fetch=True, commit=False):
            query_upper = query.strip().upper()
            if query_upper.startswith('SELECT') and 'email_verifications' in query:
                return [record]
            return []

        return side_effect


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
