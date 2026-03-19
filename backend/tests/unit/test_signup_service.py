"""
Test Signup Service (Unit Tests)

Tests for SignupService business logic: validation, Cognito calls, DB operations.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


SIGNUP_ENV = {
    'SIGNUP_COGNITO_USER_POOL_ID': 'eu-west-1_TestPool',
    'SIGNUP_COGNITO_APP_CLIENT_ID': 'test-client-id',
    'CSRF_SECRET': 'test-csrf-secret',
    'SIGNUP_REDIRECT_URL': 'https://app.test.com/welcome',
    'DB_HOST': 'localhost',
    'DB_USER': 'test',
    'DB_PASSWORD': 'test',
    'PROMO_DB_NAME': 'test_promo',
    'AWS_REGION': 'eu-west-1',
}


@pytest.fixture
def service():
    """Create a SignupService with mocked boto3 and mysql"""
    with patch.dict('os.environ', SIGNUP_ENV), \
         patch('services.signup_service.boto3') as mock_boto3, \
         patch('services.signup_service.mysql.connector') as mock_mysql:

        mock_cognito = MagicMock()
        mock_boto3.client.return_value = mock_cognito

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_mysql.connect.return_value = mock_conn

        from services.signup_service import SignupService
        svc = SignupService()

        # Expose mocks for assertions
        svc._mock_cognito = mock_cognito
        svc._mock_conn = mock_conn
        svc._mock_cursor = mock_cursor
        svc._mock_mysql = mock_mysql

        yield svc


def _valid_data():
    return {
        'firstName': 'Test',
        'lastName': 'User',
        'email': 'test@example.com',
        'password': 'SecurePass123!',
        'acceptedTerms': True,
        'locale': 'nl',
        'companyName': '',
        'propertyRange': '',
        'referralSource': '',
        'honeypot': '',
    }


# ============================================================================
# Input Validation Tests
# ============================================================================

class TestValidation:

    def test_valid_input_passes(self, service):
        is_valid, errors = service.validate_signup_input(_valid_data())
        assert is_valid is True
        assert errors is None

    def test_missing_first_name(self, service):
        data = _valid_data()
        data['firstName'] = ''
        is_valid, errors = service.validate_signup_input(data)
        assert is_valid is False
        assert 'firstName' in errors

    def test_missing_last_name(self, service):
        data = _valid_data()
        data['lastName'] = ''
        is_valid, errors = service.validate_signup_input(data)
        assert is_valid is False
        assert 'lastName' in errors

    def test_invalid_email(self, service):
        data = _valid_data()
        data['email'] = 'not-valid'
        is_valid, errors = service.validate_signup_input(data)
        assert is_valid is False
        assert 'email' in errors

    def test_short_password(self, service):
        data = _valid_data()
        data['password'] = 'short'
        is_valid, errors = service.validate_signup_input(data)
        assert is_valid is False
        assert 'password' in errors

    def test_terms_not_accepted(self, service):
        data = _valid_data()
        data['acceptedTerms'] = False
        is_valid, errors = service.validate_signup_input(data)
        assert is_valid is False
        assert 'acceptedTerms' in errors

    def test_invalid_locale(self, service):
        data = _valid_data()
        data['locale'] = 'xx'
        is_valid, errors = service.validate_signup_input(data)
        assert is_valid is False
        assert 'locale' in errors

    def test_invalid_property_range(self, service):
        data = _valid_data()
        data['propertyRange'] = 'invalid'
        is_valid, errors = service.validate_signup_input(data)
        assert is_valid is False
        assert 'propertyRange' in errors

    def test_first_name_too_long(self, service):
        data = _valid_data()
        data['firstName'] = 'A' * 51
        is_valid, errors = service.validate_signup_input(data)
        assert is_valid is False
        assert 'firstName' in errors

    def test_company_name_too_long(self, service):
        data = _valid_data()
        data['companyName'] = 'B' * 101
        is_valid, errors = service.validate_signup_input(data)
        assert is_valid is False
        assert 'companyName' in errors

    def test_multiple_errors_returned(self, service):
        """All errors returned at once, not just the first"""
        data = {'email': 'bad', 'password': 'x', 'acceptedTerms': False, 'locale': 'zz'}
        is_valid, errors = service.validate_signup_input(data)
        assert is_valid is False
        assert len(errors) >= 4


# ============================================================================
# create_signup Tests
# ============================================================================

class TestCreateSignup:

    def test_calls_cognito_sign_up(self, service):
        service._mock_cognito.sign_up.return_value = {'UserSub': 'sub-123'}
        result = service.create_signup(_valid_data(), ip_address='127.0.0.1')

        service._mock_cognito.sign_up.assert_called_once()
        call_kwargs = service._mock_cognito.sign_up.call_args[1]
        assert call_kwargs['ClientId'] == 'test-client-id'
        assert call_kwargs['Username'] == 'test@example.com'

    def test_inserts_db_row(self, service):
        service._mock_cognito.sign_up.return_value = {'UserSub': 'sub-123'}
        service.create_signup(_valid_data(), ip_address='127.0.0.1')

        service._mock_cursor.execute.assert_called()
        sql = service._mock_cursor.execute.call_args[0][0]
        assert 'INSERT INTO pending_signups' in sql

    def test_returns_user_id(self, service):
        service._mock_cognito.sign_up.return_value = {'UserSub': 'sub-abc'}
        result = service.create_signup(_valid_data())
        assert result == {'userId': 'sub-abc'}

    def test_duplicate_raises_username_exists(self, service):
        from botocore.exceptions import ClientError
        from services.signup_service import UsernameExistsError

        service._mock_cognito.sign_up.side_effect = ClientError(
            {'Error': {'Code': 'UsernameExistsException', 'Message': 'exists'}},
            'SignUp')

        with pytest.raises(UsernameExistsError):
            service.create_signup(_valid_data())


# ============================================================================
# verify_signup Tests
# ============================================================================

class TestVerifySignup:

    def test_calls_cognito_confirm(self, service):
        service._mock_cursor.fetchone.return_value = {
            'id': 1, 'email': 'test@example.com', 'status': 'pending',
            'first_name': 'Test', 'last_name': 'User'
        }
        service._mock_cognito.confirm_sign_up.return_value = {}

        result = service.verify_signup('test@example.com', '123456')

        service._mock_cognito.confirm_sign_up.assert_called_once()
        assert 'redirectUrl' in result

    def test_updates_db_status(self, service):
        service._mock_cursor.fetchone.return_value = {
            'id': 1, 'email': 'test@example.com', 'status': 'pending',
            'first_name': 'Test', 'last_name': 'User'
        }
        service._mock_cognito.confirm_sign_up.return_value = {}

        service.verify_signup('test@example.com', '123456')

        # Second execute call should be the UPDATE
        calls = service._mock_cursor.execute.call_args_list
        update_call = [c for c in calls if 'UPDATE' in str(c)]
        assert len(update_call) > 0

    def test_not_found_raises(self, service):
        from services.signup_service import SignupNotFoundError
        service._mock_cursor.fetchone.return_value = None

        with pytest.raises(SignupNotFoundError):
            service.verify_signup('unknown@example.com', '123456')

    def test_already_verified_raises(self, service):
        from services.signup_service import AlreadyVerifiedError
        service._mock_cursor.fetchone.return_value = {
            'id': 1, 'email': 'test@example.com', 'status': 'verified',
            'first_name': 'Test', 'last_name': 'User'
        }

        with pytest.raises(AlreadyVerifiedError):
            service.verify_signup('test@example.com', '123456')


# ============================================================================
# resend_verification Tests
# ============================================================================

class TestResendVerification:

    def test_calls_cognito_resend(self, service):
        service._mock_cursor.fetchone.return_value = {
            'id': 1, 'email': 'test@example.com', 'status': 'pending',
            'last_resend_at': None
        }
        service._mock_cognito.resend_confirmation_code.return_value = {}

        result = service.resend_verification('test@example.com')

        service._mock_cognito.resend_confirmation_code.assert_called_once()
        assert result == {'message': 'Verification email resent'}

    def test_rate_limit_raises(self, service):
        from services.signup_service import ResendRateLimitError
        service._mock_cursor.fetchone.return_value = {
            'id': 1, 'email': 'test@example.com', 'status': 'pending',
            'last_resend_at': datetime.utcnow() - timedelta(seconds=10)
        }

        with pytest.raises(ResendRateLimitError):
            service.resend_verification('test@example.com')

    def test_rate_limit_allows_after_60s(self, service):
        service._mock_cursor.fetchone.return_value = {
            'id': 1, 'email': 'test@example.com', 'status': 'pending',
            'last_resend_at': datetime.utcnow() - timedelta(seconds=61)
        }
        service._mock_cognito.resend_confirmation_code.return_value = {}

        result = service.resend_verification('test@example.com')
        assert result == {'message': 'Verification email resent'}

    def test_not_found_raises(self, service):
        from services.signup_service import SignupNotFoundError
        service._mock_cursor.fetchone.return_value = None

        with pytest.raises(SignupNotFoundError):
            service.resend_verification('unknown@example.com')

    def test_already_verified_raises(self, service):
        from services.signup_service import AlreadyVerifiedError
        service._mock_cursor.fetchone.return_value = {
            'id': 1, 'email': 'test@example.com', 'status': 'verified',
            'last_resend_at': None
        }

        with pytest.raises(AlreadyVerifiedError):
            service.resend_verification('test@example.com')
