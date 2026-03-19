"""
Test Signup Routes

Tests for Trial Signup API endpoints using pytest with mocked dependencies.
Covers all 3 endpoints: POST /api/signup, /api/signup/verify, /api/signup/resend
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from flask import Flask


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def signup_env():
    """Environment variables for signup service"""
    return {
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
def app(signup_env):
    """Create Flask app with signup blueprint, mocking out rate limiter"""
    with patch.dict('os.environ', signup_env):
        # Reset the singleton so each test gets a fresh service
        import routes.signup_routes as sr
        sr._signup_service = None

        app = Flask(__name__)
        app.config['TESTING'] = True

        # Import limiter and init with app (no actual limiting in tests)
        from shared_limiter import limiter
        limiter.init_app(app)

        from routes.signup_routes import signup_bp
        app.register_blueprint(signup_bp)

    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


def _valid_signup_payload():
    """Return a valid signup request body"""
    return {
        'firstName': 'Test',
        'lastName': 'User',
        'email': 'test@example.com',
        'password': 'SecurePass123!',
        'acceptedTerms': True,
        'locale': 'nl',
        'companyName': 'TestCo',
        'propertyRange': '1-5',
        'referralSource': 'google',
        'honeypot': '',
    }


# ============================================================================
# POST /api/signup Tests (6.2)
# ============================================================================

@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_signup_valid_201(mock_mysql, mock_boto3, client):
    """Test valid signup returns 201 with userId"""
    # Mock Cognito sign_up
    mock_cognito = MagicMock()
    mock_cognito.sign_up.return_value = {'UserSub': 'test-user-sub-123'}
    mock_boto3.client.return_value = mock_cognito

    # Mock DB connection
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_mysql.connect.return_value = mock_conn

    # Mock SNS (no-op)
    mock_cognito.publish = MagicMock()

    resp = client.post('/api/signup',
        data=json.dumps(_valid_signup_payload()),
        content_type='application/json',
        headers={'X-CSRF-Token': 'test-csrf-secret'})

    assert resp.status_code == 201
    data = resp.get_json()
    assert data['success'] is True
    assert data['userId'] == 'test-user-sub-123'
    assert data['message'] == 'Verification email sent'


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_signup_missing_fields_422(mock_mysql, mock_boto3, client):
    """Test missing required fields returns 422"""
    mock_boto3.client.return_value = MagicMock()
    mock_mysql.connect.return_value = MagicMock()

    resp = client.post('/api/signup',
        data=json.dumps({'email': 'test@example.com'}),
        content_type='application/json',
        headers={'X-CSRF-Token': 'test-csrf-secret'})

    assert resp.status_code == 422
    data = resp.get_json()
    assert data['error'] == 'Validation failed'
    assert 'firstName' in data['errors']
    assert 'lastName' in data['errors']
    assert 'password' in data['errors']
    assert 'acceptedTerms' in data['errors']


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_signup_invalid_email_422(mock_mysql, mock_boto3, client):
    """Test invalid email format returns 422"""
    mock_boto3.client.return_value = MagicMock()
    mock_mysql.connect.return_value = MagicMock()

    payload = _valid_signup_payload()
    payload['email'] = 'not-an-email'

    resp = client.post('/api/signup',
        data=json.dumps(payload),
        content_type='application/json',
        headers={'X-CSRF-Token': 'test-csrf-secret'})

    assert resp.status_code == 422
    data = resp.get_json()
    assert 'email' in data['errors']


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_signup_terms_false_422(mock_mysql, mock_boto3, client):
    """Test acceptedTerms=false returns 422"""
    mock_boto3.client.return_value = MagicMock()
    mock_mysql.connect.return_value = MagicMock()

    payload = _valid_signup_payload()
    payload['acceptedTerms'] = False

    resp = client.post('/api/signup',
        data=json.dumps(payload),
        content_type='application/json',
        headers={'X-CSRF-Token': 'test-csrf-secret'})

    assert resp.status_code == 422
    data = resp.get_json()
    assert 'acceptedTerms' in data['errors']


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_signup_duplicate_email_409(mock_mysql, mock_boto3, client):
    """Test duplicate email returns 409"""
    from botocore.exceptions import ClientError

    mock_cognito = MagicMock()
    mock_cognito.sign_up.side_effect = ClientError(
        {'Error': {'Code': 'UsernameExistsException', 'Message': 'User exists'}},
        'SignUp')
    mock_boto3.client.return_value = mock_cognito

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = MagicMock()
    mock_mysql.connect.return_value = mock_conn

    resp = client.post('/api/signup',
        data=json.dumps(_valid_signup_payload()),
        content_type='application/json',
        headers={'X-CSRF-Token': 'test-csrf-secret'})

    assert resp.status_code == 409
    assert resp.get_json()['error'] == 'Email already registered'


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_signup_honeypot_200(mock_mysql, mock_boto3, client):
    """Test honeypot filled returns silent 200"""
    mock_boto3.client.return_value = MagicMock()
    mock_mysql.connect.return_value = MagicMock()

    payload = _valid_signup_payload()
    payload['honeypot'] = 'I am a bot'

    resp = client.post('/api/signup',
        data=json.dumps(payload),
        content_type='application/json',
        headers={'X-CSRF-Token': 'test-csrf-secret'})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['userId'] == 'ok'


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_signup_invalid_csrf_403(mock_mysql, mock_boto3, signup_env, client):
    """Test invalid CSRF token returns 403"""
    mock_cognito = MagicMock()
    mock_boto3.client.return_value = mock_cognito
    mock_mysql.connect.return_value = MagicMock()

    # Reset singleton so it picks up the env with CSRF_SECRET set
    import routes.signup_routes as sr
    with patch.dict('os.environ', signup_env):
        sr._signup_service = None

        resp = client.post('/api/signup',
            data=json.dumps(_valid_signup_payload()),
            content_type='application/json',
            headers={'X-CSRF-Token': 'wrong-token'})

    assert resp.status_code == 403
    assert resp.get_json()['error'] == 'Invalid CSRF token'


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_signup_invalid_property_range_422(mock_mysql, mock_boto3, client):
    """Test invalid propertyRange returns 422"""
    mock_boto3.client.return_value = MagicMock()
    mock_mysql.connect.return_value = MagicMock()

    payload = _valid_signup_payload()
    payload['propertyRange'] = 'invalid'

    resp = client.post('/api/signup',
        data=json.dumps(payload),
        content_type='application/json',
        headers={'X-CSRF-Token': 'test-csrf-secret'})

    assert resp.status_code == 422
    assert 'propertyRange' in resp.get_json()['errors']


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_signup_field_length_limits_422(mock_mysql, mock_boto3, client):
    """Test field length limits (firstName > 50, companyName > 100)"""
    mock_boto3.client.return_value = MagicMock()
    mock_mysql.connect.return_value = MagicMock()

    payload = _valid_signup_payload()
    payload['firstName'] = 'A' * 51
    payload['companyName'] = 'B' * 101

    resp = client.post('/api/signup',
        data=json.dumps(payload),
        content_type='application/json',
        headers={'X-CSRF-Token': 'test-csrf-secret'})

    assert resp.status_code == 422
    errors = resp.get_json()['errors']
    assert 'firstName' in errors
    assert 'companyName' in errors


# ============================================================================
# POST /api/signup/verify Tests (6.3)
# ============================================================================

@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_verify_valid_200(mock_mysql, mock_boto3, client):
    """Test valid verification returns 200 with redirectUrl"""
    mock_cognito = MagicMock()
    mock_cognito.confirm_sign_up.return_value = {}
    mock_boto3.client.return_value = mock_cognito

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    # _get_pending_signup returns a pending row
    mock_cursor.fetchone.return_value = {
        'id': 1, 'email': 'test@example.com', 'status': 'pending',
        'first_name': 'Test', 'last_name': 'User'
    }
    mock_conn.cursor.return_value = mock_cursor
    mock_mysql.connect.return_value = mock_conn

    resp = client.post('/api/signup/verify',
        data=json.dumps({'email': 'test@example.com', 'code': '123456'}),
        content_type='application/json')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'redirectUrl' in data


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_verify_not_found_404(mock_mysql, mock_boto3, client):
    """Test verify with unknown email returns 404"""
    mock_boto3.client.return_value = MagicMock()

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # Not found
    mock_conn.cursor.return_value = mock_cursor
    mock_mysql.connect.return_value = mock_conn

    resp = client.post('/api/signup/verify',
        data=json.dumps({'email': 'unknown@example.com', 'code': '123456'}),
        content_type='application/json')

    assert resp.status_code == 404
    assert resp.get_json()['error'] == 'Signup not found'


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_verify_already_verified_410(mock_mysql, mock_boto3, client):
    """Test verify on already verified signup returns 410"""
    mock_boto3.client.return_value = MagicMock()

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        'id': 1, 'email': 'test@example.com', 'status': 'verified',
        'first_name': 'Test', 'last_name': 'User'
    }
    mock_conn.cursor.return_value = mock_cursor
    mock_mysql.connect.return_value = mock_conn

    resp = client.post('/api/signup/verify',
        data=json.dumps({'email': 'test@example.com', 'code': '123456'}),
        content_type='application/json')

    assert resp.status_code == 410
    assert resp.get_json()['error'] == 'Already verified'


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_verify_invalid_code_400(mock_mysql, mock_boto3, client):
    """Test verify with wrong code returns 400"""
    from botocore.exceptions import ClientError

    mock_cognito = MagicMock()
    mock_cognito.confirm_sign_up.side_effect = ClientError(
        {'Error': {'Code': 'CodeMismatchException', 'Message': 'Invalid code'}},
        'ConfirmSignUp')
    mock_boto3.client.return_value = mock_cognito

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        'id': 1, 'email': 'test@example.com', 'status': 'pending',
        'first_name': 'Test', 'last_name': 'User'
    }
    mock_conn.cursor.return_value = mock_cursor
    mock_mysql.connect.return_value = mock_conn

    resp = client.post('/api/signup/verify',
        data=json.dumps({'email': 'test@example.com', 'code': '000000'}),
        content_type='application/json')

    assert resp.status_code == 400


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_verify_expired_code_400(mock_mysql, mock_boto3, client):
    """Test verify with expired code returns 400"""
    from botocore.exceptions import ClientError

    mock_cognito = MagicMock()
    mock_cognito.confirm_sign_up.side_effect = ClientError(
        {'Error': {'Code': 'ExpiredCodeException', 'Message': 'Code expired'}},
        'ConfirmSignUp')
    mock_boto3.client.return_value = mock_cognito

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        'id': 1, 'email': 'test@example.com', 'status': 'pending',
        'first_name': 'Test', 'last_name': 'User'
    }
    mock_conn.cursor.return_value = mock_cursor
    mock_mysql.connect.return_value = mock_conn

    resp = client.post('/api/signup/verify',
        data=json.dumps({'email': 'test@example.com', 'code': '999999'}),
        content_type='application/json')

    assert resp.status_code == 400


# ============================================================================
# POST /api/signup/resend Tests (6.4)
# ============================================================================

@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_resend_valid_200(mock_mysql, mock_boto3, client):
    """Test valid resend returns 200"""
    mock_cognito = MagicMock()
    mock_cognito.resend_confirmation_code.return_value = {}
    mock_boto3.client.return_value = mock_cognito

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        'id': 1, 'email': 'test@example.com', 'status': 'pending',
        'last_resend_at': None
    }
    mock_conn.cursor.return_value = mock_cursor
    mock_mysql.connect.return_value = mock_conn

    resp = client.post('/api/signup/resend',
        data=json.dumps({'email': 'test@example.com'}),
        content_type='application/json')

    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_resend_not_found_404(mock_mysql, mock_boto3, client):
    """Test resend with unknown email returns 404"""
    mock_boto3.client.return_value = MagicMock()

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cursor
    mock_mysql.connect.return_value = mock_conn

    resp = client.post('/api/signup/resend',
        data=json.dumps({'email': 'unknown@example.com'}),
        content_type='application/json')

    assert resp.status_code == 404
    assert resp.get_json()['error'] == 'Signup not found'


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_resend_already_verified_410(mock_mysql, mock_boto3, client):
    """Test resend on verified signup returns 410"""
    mock_boto3.client.return_value = MagicMock()

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        'id': 1, 'email': 'test@example.com', 'status': 'verified',
        'last_resend_at': None
    }
    mock_conn.cursor.return_value = mock_cursor
    mock_mysql.connect.return_value = mock_conn

    resp = client.post('/api/signup/resend',
        data=json.dumps({'email': 'test@example.com'}),
        content_type='application/json')

    assert resp.status_code == 410
    assert resp.get_json()['error'] == 'Already verified'


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_resend_rate_limited_429(mock_mysql, mock_boto3, client):
    """Test resend within 60 seconds returns 429"""
    from datetime import datetime, timedelta
    mock_boto3.client.return_value = MagicMock()

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        'id': 1, 'email': 'test@example.com', 'status': 'pending',
        'last_resend_at': datetime.utcnow() - timedelta(seconds=10)  # 10s ago
    }
    mock_conn.cursor.return_value = mock_cursor
    mock_mysql.connect.return_value = mock_conn

    resp = client.post('/api/signup/resend',
        data=json.dumps({'email': 'test@example.com'}),
        content_type='application/json')

    assert resp.status_code == 429


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_verify_missing_fields_422(mock_mysql, mock_boto3, client):
    """Test verify with missing email/code returns 422"""
    mock_boto3.client.return_value = MagicMock()
    mock_mysql.connect.return_value = MagicMock()

    resp = client.post('/api/signup/verify',
        data=json.dumps({}),
        content_type='application/json')

    assert resp.status_code == 422
    assert resp.get_json()['error'] == 'Email and code are required'


@patch('services.signup_service.boto3')
@patch('services.signup_service.mysql.connector')
def test_resend_missing_email_422(mock_mysql, mock_boto3, client):
    """Test resend with missing email returns 422"""
    mock_boto3.client.return_value = MagicMock()
    mock_mysql.connect.return_value = MagicMock()

    resp = client.post('/api/signup/resend',
        data=json.dumps({}),
        content_type='application/json')

    assert resp.status_code == 422
    assert resp.get_json()['error'] == 'Email is required'
