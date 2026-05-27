"""
Unit tests for EmailVerificationService

Tests all public methods with mocked SES client and DatabaseManager.
Validates: Requirements 1.1, 1.2, 1.3, 2.1–2.5, 3.1–3.4, 5.1–5.5
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.email_verification_service import EmailVerificationService, RESEND_COOLDOWN_SECONDS


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a mocked DatabaseManager."""
    db = Mock()
    db.execute_query = Mock(return_value=[])
    return db


@pytest.fixture
def mock_ses_client():
    """Create a mocked SES client."""
    client = Mock()
    client.verify_email_identity = Mock(return_value={})
    client.get_identity_verification_attributes = Mock(return_value={
        'VerificationAttributes': {}
    })
    return client


@pytest.fixture
def service(mock_db, mock_ses_client):
    """Create EmailVerificationService with mocked dependencies."""
    with patch('services.email_verification_service.boto3') as mock_boto3:
        mock_boto3.client.return_value = mock_ses_client
        svc = EmailVerificationService(db_manager=mock_db, region='eu-west-1')
    return svc


# ============================================================================
# _validate_email
# ============================================================================

@pytest.mark.unit
class TestValidateEmail:
    """Test _validate_email method."""

    def test_valid_simple_email(self, service):
        assert service._validate_email('user@example.com') is True

    def test_valid_email_with_dots(self, service):
        assert service._validate_email('first.last@example.com') is True

    def test_valid_email_with_plus(self, service):
        assert service._validate_email('user+tag@example.com') is True

    def test_valid_email_with_subdomain(self, service):
        assert service._validate_email('user@mail.example.co.uk') is True

    def test_invalid_no_at_sign(self, service):
        assert service._validate_email('userexample.com') is False

    def test_invalid_no_domain(self, service):
        assert service._validate_email('user@') is False

    def test_invalid_no_local_part(self, service):
        assert service._validate_email('@example.com') is False

    def test_invalid_no_tld(self, service):
        assert service._validate_email('user@example') is False

    def test_invalid_spaces(self, service):
        assert service._validate_email('user @example.com') is False

    def test_invalid_empty_string(self, service):
        assert service._validate_email('') is False

    def test_invalid_none(self, service):
        assert service._validate_email(None) is False

    def test_invalid_double_at(self, service):
        assert service._validate_email('user@@example.com') is False


# ============================================================================
# initiate_verification
# ============================================================================

@pytest.mark.unit
class TestInitiateVerification:
    """Test initiate_verification method."""

    def test_success_path(self, service, mock_ses_client, mock_db):
        """SES call succeeds → returns success with pending status, stores record."""
        result = service.initiate_verification('tenant1', 'user@example.com')

        assert result['success'] is True
        assert result['status'] == 'pending'
        assert result['error'] is None
        mock_ses_client.verify_email_identity.assert_called_once_with(
            EmailAddress='user@example.com'
        )
        # Verify DB record stored with pending status
        mock_db.execute_query.assert_called()
        call_args = mock_db.execute_query.call_args
        assert 'INSERT INTO email_verifications' in call_args[0][0]
        params = call_args[0][1]
        assert params[0] == 'tenant1'
        assert params[1] == 'user@example.com'
        assert params[2] == 'pending'

    def test_ses_client_error(self, service, mock_ses_client, mock_db):
        """SES ClientError → returns failure, stores failed record."""
        mock_ses_client.verify_email_identity.side_effect = ClientError(
            {'Error': {'Code': 'InvalidParameterValue', 'Message': 'Invalid email'}},
            'VerifyEmailIdentity'
        )

        result = service.initiate_verification('tenant1', 'user@example.com')

        assert result['success'] is False
        assert result['status'] == 'failed'
        assert 'InvalidParameterValue' in result['error']
        # Verify failed record stored
        mock_db.execute_query.assert_called()
        call_args = mock_db.execute_query.call_args
        params = call_args[0][1]
        assert params[2] == 'failed'

    def test_ses_unexpected_error(self, service, mock_ses_client, mock_db):
        """Unexpected exception → returns failure, stores failed record."""
        mock_ses_client.verify_email_identity.side_effect = Exception('Network timeout')

        result = service.initiate_verification('tenant1', 'user@example.com')

        assert result['success'] is False
        assert result['status'] == 'failed'
        assert 'Network timeout' in result['error']

    def test_invalid_email_rejected(self, service, mock_ses_client):
        """Invalid email → returns failure without calling SES."""
        result = service.initiate_verification('tenant1', 'not-an-email')

        assert result['success'] is False
        assert result['status'] == 'failed'
        assert 'Invalid email format' in result['error']
        mock_ses_client.verify_email_identity.assert_not_called()


# ============================================================================
# check_status
# ============================================================================

@pytest.mark.unit
class TestCheckStatus:
    """Test check_status method."""

    def test_ses_success_maps_to_verified(self, service, mock_ses_client, mock_db):
        """SES 'Success' → local status 'verified'."""
        mock_db.execute_query.side_effect = [
            # _get_active_record query
            [{'email': 'user@example.com', 'status': 'pending',
              'last_checked_at': None, 'last_resend_at': None,
              'initiated_at': datetime(2025, 1, 1), 'verified_at': None}],
            # _update_verification_status query
            []
        ]
        mock_ses_client.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {
                'user@example.com': {'VerificationStatus': 'Success'}
            }
        }

        result = service.check_status('tenant1')

        assert result['success'] is True
        assert result['email'] == 'user@example.com'
        assert result['status'] == 'verified'
        assert result['last_checked'] is not None

    def test_ses_pending_maps_to_pending(self, service, mock_ses_client, mock_db):
        """SES 'Pending' → local status 'pending'."""
        mock_db.execute_query.side_effect = [
            [{'email': 'user@example.com', 'status': 'pending',
              'last_checked_at': None, 'last_resend_at': None,
              'initiated_at': datetime(2025, 1, 1), 'verified_at': None}],
            []
        ]
        mock_ses_client.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {
                'user@example.com': {'VerificationStatus': 'Pending'}
            }
        }

        result = service.check_status('tenant1')

        assert result['success'] is True
        assert result['status'] == 'pending'

    def test_ses_failed_maps_to_failed(self, service, mock_ses_client, mock_db):
        """SES 'Failed' → local status 'failed'."""
        mock_db.execute_query.side_effect = [
            [{'email': 'user@example.com', 'status': 'pending',
              'last_checked_at': None, 'last_resend_at': None,
              'initiated_at': datetime(2025, 1, 1), 'verified_at': None}],
            []
        ]
        mock_ses_client.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {
                'user@example.com': {'VerificationStatus': 'Failed'}
            }
        }

        result = service.check_status('tenant1')

        assert result['success'] is True
        assert result['status'] == 'failed'

    def test_ses_temporary_failure_maps_to_pending(self, service, mock_ses_client, mock_db):
        """SES 'TemporaryFailure' → local status 'pending'."""
        mock_db.execute_query.side_effect = [
            [{'email': 'user@example.com', 'status': 'pending',
              'last_checked_at': None, 'last_resend_at': None,
              'initiated_at': datetime(2025, 1, 1), 'verified_at': None}],
            []
        ]
        mock_ses_client.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {
                'user@example.com': {'VerificationStatus': 'TemporaryFailure'}
            }
        }

        result = service.check_status('tenant1')

        assert result['success'] is True
        assert result['status'] == 'pending'

    def test_ses_not_started_maps_to_failed(self, service, mock_ses_client, mock_db):
        """SES 'NotStarted' → local status 'failed'."""
        mock_db.execute_query.side_effect = [
            [{'email': 'user@example.com', 'status': 'pending',
              'last_checked_at': None, 'last_resend_at': None,
              'initiated_at': datetime(2025, 1, 1), 'verified_at': None}],
            []
        ]
        mock_ses_client.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {
                'user@example.com': {'VerificationStatus': 'NotStarted'}
            }
        }

        result = service.check_status('tenant1')

        assert result['success'] is True
        assert result['status'] == 'failed'

    def test_no_record_returns_null_status(self, service, mock_db):
        """No active record → returns null email and status."""
        mock_db.execute_query.return_value = []

        result = service.check_status('tenant1')

        assert result['success'] is True
        assert result['email'] is None
        assert result['status'] is None
        assert result['last_checked'] is None

    def test_ses_error_returns_cached_status(self, service, mock_ses_client, mock_db):
        """SES API error → returns cached DB status."""
        last_checked = datetime(2025, 1, 10, 12, 0, 0)
        mock_db.execute_query.return_value = [
            {'email': 'user@example.com', 'status': 'pending',
             'last_checked_at': last_checked, 'last_resend_at': None,
             'initiated_at': datetime(2025, 1, 1), 'verified_at': None}
        ]
        mock_ses_client.get_identity_verification_attributes.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable', 'Message': 'SES down'}},
            'GetIdentityVerificationAttributes'
        )

        result = service.check_status('tenant1')

        assert result['success'] is True
        assert result['email'] == 'user@example.com'
        assert result['status'] == 'pending'
        assert result['last_checked'] == '2025-01-10T12:00:00Z'


# ============================================================================
# resend_verification
# ============================================================================

@pytest.mark.unit
class TestResendVerification:
    """Test resend_verification method."""

    def test_success_path(self, service, mock_ses_client, mock_db):
        """Resend succeeds when cooldown has passed."""
        mock_db.execute_query.side_effect = [
            # _get_active_record
            [{'email': 'user@example.com', 'status': 'pending',
              'last_checked_at': None,
              'last_resend_at': datetime.utcnow() - timedelta(seconds=120),
              'initiated_at': datetime(2025, 1, 1), 'verified_at': None}],
            # update last_resend_at
            []
        ]

        result = service.resend_verification('tenant1')

        assert result['success'] is True
        assert result['error'] is None
        mock_ses_client.verify_email_identity.assert_called_once_with(
            EmailAddress='user@example.com'
        )

    def test_success_when_no_previous_resend(self, service, mock_ses_client, mock_db):
        """Resend succeeds when last_resend_at is None (first resend)."""
        mock_db.execute_query.side_effect = [
            [{'email': 'user@example.com', 'status': 'pending',
              'last_checked_at': None, 'last_resend_at': None,
              'initiated_at': datetime(2025, 1, 1), 'verified_at': None}],
            []
        ]

        result = service.resend_verification('tenant1')

        assert result['success'] is True
        mock_ses_client.verify_email_identity.assert_called_once()

    def test_rate_limited(self, service, mock_ses_client, mock_db):
        """Resend rejected when within 60s cooldown."""
        mock_db.execute_query.return_value = [
            {'email': 'user@example.com', 'status': 'pending',
             'last_checked_at': None,
             'last_resend_at': datetime.utcnow() - timedelta(seconds=30),
             'initiated_at': datetime(2025, 1, 1), 'verified_at': None}
        ]

        result = service.resend_verification('tenant1')

        assert result['success'] is False
        assert '60 seconds' in result['error']
        mock_ses_client.verify_email_identity.assert_not_called()

    def test_ses_failure(self, service, mock_ses_client, mock_db):
        """SES error during resend → returns error."""
        mock_db.execute_query.return_value = [
            {'email': 'user@example.com', 'status': 'pending',
             'last_checked_at': None, 'last_resend_at': None,
             'initiated_at': datetime(2025, 1, 1), 'verified_at': None}
        ]
        mock_ses_client.verify_email_identity.side_effect = ClientError(
            {'Error': {'Code': 'Throttling', 'Message': 'Rate exceeded'}},
            'VerifyEmailIdentity'
        )

        result = service.resend_verification('tenant1')

        assert result['success'] is False
        assert 'Throttling' in result['error']

    def test_no_record_returns_error(self, service, mock_db):
        """No active record → returns error."""
        mock_db.execute_query.return_value = []

        result = service.resend_verification('tenant1')

        assert result['success'] is False
        assert 'No verification record' in result['error']


# ============================================================================
# update_email
# ============================================================================

@pytest.mark.unit
class TestUpdateEmail:
    """Test update_email method."""

    def test_valid_email_initiates_verification(self, service, mock_ses_client, mock_db):
        """Valid new email → marks old as replaced, initiates new verification."""
        mock_db.execute_query.side_effect = [
            # Mark old records as replaced
            [],
            # Store new pending record (from initiate_verification)
            []
        ]

        result = service.update_email('tenant1', 'new@example.com')

        assert result['success'] is True
        assert result['status'] == 'pending'
        # Verify old records marked as replaced
        first_call = mock_db.execute_query.call_args_list[0]
        assert 'replaced' in first_call[0][0]
        assert first_call[0][1] == ('tenant1',)
        # Verify SES called for new email
        mock_ses_client.verify_email_identity.assert_called_once_with(
            EmailAddress='new@example.com'
        )

    def test_invalid_email_rejected(self, service, mock_ses_client, mock_db):
        """Invalid email → returns error without calling SES or DB."""
        result = service.update_email('tenant1', 'not-valid')

        assert result['success'] is False
        assert result['status'] == 'failed'
        assert 'Invalid email format' in result['error']
        mock_ses_client.verify_email_identity.assert_not_called()

    def test_state_transition_old_to_replaced(self, service, mock_ses_client, mock_db):
        """Old records with active statuses are marked as 'replaced'."""
        mock_db.execute_query.side_effect = [[], []]

        service.update_email('tenant1', 'new@example.com')

        first_call = mock_db.execute_query.call_args_list[0]
        query = first_call[0][0]
        # Verify the UPDATE targets active statuses
        assert 'pending' in query
        assert 'verified' in query
        assert 'failed' in query
        assert 'expired' in query
        assert "SET status = 'replaced'" in query


# ============================================================================
# get_verified_sender
# ============================================================================

@pytest.mark.unit
class TestGetVerifiedSender:
    """Test get_verified_sender method."""

    def test_verified_tenant(self, service, mock_db):
        """Verified tenant → returns verified=True with email and company name."""
        mock_db.execute_query.side_effect = [
            # get verified email
            [{'email': 'tenant@example.com'}],
            # get company name
            [{'value': '"Acme Corp"}'}]
        ]

        result = service.get_verified_sender('tenant1')

        assert result['verified'] is True
        assert result['email'] == 'tenant@example.com'

    def test_no_verified_record(self, service, mock_db):
        """No verified record → returns verified=False."""
        mock_db.execute_query.return_value = []

        result = service.get_verified_sender('tenant1')

        assert result['verified'] is False
        assert result['email'] is None
        assert result['company_name'] is None

    def test_pending_status_not_returned(self, service, mock_db):
        """Only 'verified' status records are returned."""
        # The query filters by status = 'verified', so pending records won't match
        mock_db.execute_query.return_value = []

        result = service.get_verified_sender('tenant1')

        assert result['verified'] is False

    def test_query_filters_by_verified_status(self, service, mock_db):
        """Verify the SQL query filters by status='verified'."""
        mock_db.execute_query.return_value = []

        service.get_verified_sender('tenant1')

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert "status = 'verified'" in query

    def test_query_filters_by_administration(self, service, mock_db):
        """Verify tenant isolation — query includes administration filter."""
        mock_db.execute_query.return_value = []

        service.get_verified_sender('tenant1')

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration = %s' in query
        assert params == ('tenant1',)


# ============================================================================
# mark_expired
# ============================================================================

@pytest.mark.unit
class TestMarkExpired:
    """Test mark_expired method."""

    def test_updates_status_to_expired(self, service, mock_db):
        """mark_expired updates verified record to expired."""
        service.mark_expired('tenant1', 'user@example.com')

        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert "SET status = 'expired'" in query
        assert "status = 'verified'" in query
        assert params == ('tenant1', 'user@example.com')

    def test_only_targets_verified_records(self, service, mock_db):
        """mark_expired only changes records with status='verified'."""
        service.mark_expired('tenant1', 'user@example.com')

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert "AND status = 'verified'" in query

    def test_includes_tenant_isolation(self, service, mock_db):
        """mark_expired includes administration filter."""
        service.mark_expired('tenant1', 'user@example.com')

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert 'administration = %s' in query
