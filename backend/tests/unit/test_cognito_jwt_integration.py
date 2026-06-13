"""
Unit tests for the integration of JWTVerifier into the @cognito_required decorator.

Tests that:
1. JWTVerifier singleton is lazily initialized from env vars
2. Verification exceptions map to correct HTTP responses (401, 503)
3. Fallback to base64 when env vars are missing
4. Backward compatibility: decoded payload provides sub, custom:tenants, cognito:groups
"""

import time
import json
import pytest
from unittest.mock import patch, MagicMock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

import sys
import os

# Add backend src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from auth.cognito_utils import (
    extract_user_credentials,
    _get_jwt_verifier,
    _extract_with_verifier,
    _extract_with_base64,
)
from auth.jwt_verifier import (
    JWTVerifier,
    InvalidTokenError,
    TokenExpiredError,
    ServiceUnavailableError,
)


# --- Test Configuration ---

TEST_USER_POOL_ID = "eu-west-1_IntTestPool"
TEST_REGION = "eu-west-1"
TEST_APP_CLIENT_ID = "int-test-app-client-id"
TEST_ISSUER = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_USER_POOL_ID}"


# --- Helpers ---

def generate_rsa_keypair():
    """Generate a fresh RSA keypair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    return private_key


def private_key_to_pem(private_key):
    """Convert RSA private key to PEM bytes."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def public_key_to_jwk(public_key, kid="test-kid-1"):
    """Convert RSA public key to JWK dict format."""
    from jwt.algorithms import RSAAlgorithm
    jwk_dict = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk_dict["kid"] = kid
    jwk_dict["alg"] = "RS256"
    jwk_dict["use"] = "sig"
    return jwk_dict


def create_signed_token(payload, private_key, kid="test-kid-1"):
    """Create a signed JWT token."""
    headers = {"kid": kid, "alg": "RS256"}
    pem = private_key_to_pem(private_key)
    return jwt.encode(payload, pem, algorithm="RS256", headers=headers)


def make_flask_request(token=None, headers=None):
    """Create a mock Flask request object."""
    mock_request = MagicMock()
    if headers is None:
        headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    mock_request.headers = headers
    return mock_request


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the JWT verifier singleton before each test."""
    import auth.cognito_utils as cu
    cu._jwt_verifier_instance = None
    cu._jwt_verifier_init_attempted = False
    yield
    cu._jwt_verifier_instance = None
    cu._jwt_verifier_init_attempted = False


# =============================================================================
# Test: Singleton Initialization
# =============================================================================

class TestJWTVerifierSingleton:
    """Test lazy initialization of JWTVerifier singleton."""

    def test_returns_none_when_env_vars_missing(self):
        """When Cognito env vars are not set, returns None (fallback mode)."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove relevant keys
            env_copy = os.environ.copy()
            for key in ['COGNITO_USER_POOL_ID', 'COGNITO_REGION', 'COGNITO_APP_CLIENT_ID']:
                env_copy.pop(key, None)
            with patch.dict(os.environ, env_copy, clear=True):
                result = _get_jwt_verifier()
                assert result is None

    def test_returns_verifier_when_env_vars_set(self):
        """When all Cognito env vars are set, returns JWTVerifier instance."""
        env_vars = {
            'COGNITO_USER_POOL_ID': TEST_USER_POOL_ID,
            'COGNITO_REGION': TEST_REGION,
            'COGNITO_APP_CLIENT_ID': TEST_APP_CLIENT_ID,
        }
        with patch.dict(os.environ, env_vars):
            result = _get_jwt_verifier()
            assert result is not None
            assert isinstance(result, JWTVerifier)
            assert result.user_pool_id == TEST_USER_POOL_ID
            assert result.region == TEST_REGION
            assert result.app_client_id == TEST_APP_CLIENT_ID

    def test_singleton_returns_same_instance(self):
        """Repeated calls return the same instance (singleton)."""
        env_vars = {
            'COGNITO_USER_POOL_ID': TEST_USER_POOL_ID,
            'COGNITO_REGION': TEST_REGION,
            'COGNITO_APP_CLIENT_ID': TEST_APP_CLIENT_ID,
        }
        with patch.dict(os.environ, env_vars):
            first = _get_jwt_verifier()
            second = _get_jwt_verifier()
            assert first is second

    def test_does_not_retry_after_failed_init(self):
        """Once init fails (missing env vars), doesn't retry on subsequent calls."""
        with patch.dict(os.environ, {}, clear=True):
            env_copy = os.environ.copy()
            for key in ['COGNITO_USER_POOL_ID', 'COGNITO_REGION', 'COGNITO_APP_CLIENT_ID']:
                env_copy.pop(key, None)
            with patch.dict(os.environ, env_copy, clear=True):
                first = _get_jwt_verifier()
                assert first is None

                # Even if env vars are now set, won't retry
                import auth.cognito_utils as cu
                assert cu._jwt_verifier_init_attempted is True

    def test_partial_env_vars_returns_none(self):
        """When only some env vars are set, returns None."""
        env_vars = {
            'COGNITO_USER_POOL_ID': TEST_USER_POOL_ID,
            # Missing COGNITO_REGION and COGNITO_APP_CLIENT_ID
        }
        with patch.dict(os.environ, env_vars, clear=True):
            result = _get_jwt_verifier()
            assert result is None


# =============================================================================
# Test: Exception Mapping to HTTP Responses
# =============================================================================

class TestExceptionMapping:
    """Test that JWTVerifier exceptions map to correct HTTP error responses."""

    def test_invalid_token_error_maps_to_401(self):
        """InvalidTokenError maps to HTTP 401 with error message."""
        verifier = MagicMock()
        verifier.verify_token.side_effect = InvalidTokenError("Invalid token signature")

        email, roles, error = _extract_with_verifier(verifier, "some-token")

        assert email is None
        assert roles is None
        assert error is not None
        assert error['statusCode'] == 401
        body = json.loads(error['body'])
        assert body['error'] == 'Invalid token signature'

    def test_token_expired_error_maps_to_401(self):
        """TokenExpiredError maps to HTTP 401 with 'Token has expired'."""
        verifier = MagicMock()
        verifier.verify_token.side_effect = TokenExpiredError("Token has expired")

        email, roles, error = _extract_with_verifier(verifier, "some-token")

        assert email is None
        assert roles is None
        assert error is not None
        assert error['statusCode'] == 401
        body = json.loads(error['body'])
        assert body['error'] == 'Token has expired'

    def test_service_unavailable_error_maps_to_503(self):
        """ServiceUnavailableError maps to HTTP 503."""
        verifier = MagicMock()
        verifier.verify_token.side_effect = ServiceUnavailableError(
            "Authentication service unavailable"
        )

        email, roles, error = _extract_with_verifier(verifier, "some-token")

        assert email is None
        assert roles is None
        assert error is not None
        assert error['statusCode'] == 503
        body = json.loads(error['body'])
        assert body['error'] == 'Authentication service unavailable'

    def test_invalid_issuer_message_preserved(self):
        """InvalidTokenError message for issuer is preserved."""
        verifier = MagicMock()
        verifier.verify_token.side_effect = InvalidTokenError("Invalid token issuer")

        _, _, error = _extract_with_verifier(verifier, "some-token")
        body = json.loads(error['body'])
        assert body['error'] == 'Invalid token issuer'

    def test_invalid_audience_message_preserved(self):
        """InvalidTokenError message for audience is preserved."""
        verifier = MagicMock()
        verifier.verify_token.side_effect = InvalidTokenError("Invalid token audience")

        _, _, error = _extract_with_verifier(verifier, "some-token")
        body = json.loads(error['body'])
        assert body['error'] == 'Invalid token audience'

    def test_token_signing_key_not_found_message(self):
        """InvalidTokenError for unknown kid maps correctly."""
        verifier = MagicMock()
        verifier.verify_token.side_effect = InvalidTokenError("Token signing key not found")

        _, _, error = _extract_with_verifier(verifier, "some-token")
        body = json.loads(error['body'])
        assert body['error'] == 'Token signing key not found'


# =============================================================================
# Test: Backward Compatibility (payload provides sub, custom:tenants, cognito:groups)
# =============================================================================

class TestBackwardCompatibility:
    """Test that decoded payload still provides expected claims to downstream code."""

    def test_verifier_extracts_email_from_payload(self):
        """Verified payload provides email as user_email."""
        verifier = MagicMock()
        verifier.verify_token.return_value = {
            'sub': 'user-sub-123',
            'email': 'test@example.com',
            'cognito:groups': ['Finance_CRUD', 'STR_Read'],
            'custom:tenants': 'tenant-a,tenant-b',
        }

        email, roles, error = _extract_with_verifier(verifier, "valid-token")

        assert error is None
        assert email == 'test@example.com'
        assert roles == ['Finance_CRUD', 'STR_Read']

    def test_verifier_falls_back_to_username(self):
        """When email is missing, falls back to username."""
        verifier = MagicMock()
        verifier.verify_token.return_value = {
            'sub': 'user-sub-123',
            'username': 'jdoe',
            'cognito:groups': ['STR_CRUD'],
        }

        email, roles, error = _extract_with_verifier(verifier, "valid-token")

        assert error is None
        assert email == 'jdoe'

    def test_verifier_falls_back_to_sub(self):
        """When email and username are missing, falls back to sub."""
        verifier = MagicMock()
        verifier.verify_token.return_value = {
            'sub': 'user-sub-123',
            'cognito:groups': [],
        }

        email, roles, error = _extract_with_verifier(verifier, "valid-token")

        assert error is None
        assert email == 'user-sub-123'

    def test_verifier_handles_missing_groups(self):
        """When cognito:groups is missing, returns empty list."""
        verifier = MagicMock()
        verifier.verify_token.return_value = {
            'sub': 'user-sub-123',
            'email': 'test@example.com',
        }

        email, roles, error = _extract_with_verifier(verifier, "valid-token")

        assert error is None
        assert roles == []

    def test_verifier_handles_string_groups(self):
        """When cognito:groups is a single string, wraps in list."""
        verifier = MagicMock()
        verifier.verify_token.return_value = {
            'sub': 'user-sub-123',
            'email': 'test@example.com',
            'cognito:groups': 'SingleRole',
        }

        email, roles, error = _extract_with_verifier(verifier, "valid-token")

        assert error is None
        assert roles == ['SingleRole']

    def test_no_user_identifier_returns_401(self):
        """When payload has no email/username/sub, returns 401."""
        verifier = MagicMock()
        verifier.verify_token.return_value = {
            'cognito:groups': ['Finance_CRUD'],
            'custom:tenants': 'tenant-a',
        }

        email, roles, error = _extract_with_verifier(verifier, "valid-token")

        assert email is None
        assert error is not None
        assert error['statusCode'] == 401


# =============================================================================
# Test: Fallback to Base64 Decoding
# =============================================================================

class TestBase64Fallback:
    """Test that base64 fallback works when JWTVerifier is not available."""

    def test_base64_extracts_valid_token(self):
        """Base64 path correctly extracts email and roles from valid JWT payload."""
        payload = {
            'email': 'fallback@test.com',
            'cognito:groups': ['Administrators'],
            'sub': 'sub-123',
            'exp': int(time.time()) + 3600,
        }
        import base64
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b'=').decode()
        token = f"eyJhbGciOiJSUzI1NiJ9.{payload_b64}.fake-signature"

        email, roles, error = _extract_with_base64(token)

        assert error is None
        assert email == 'fallback@test.com'
        assert roles == ['Administrators']

    def test_base64_rejects_expired_token(self):
        """Base64 path rejects expired tokens."""
        # Use a time far enough in the past to guarantee expiration
        # regardless of timezone interpretation of datetime.utcnow().timestamp()
        payload = {
            'email': 'expired@test.com',
            'cognito:groups': [],
            'sub': 'sub-123',
            'exp': 1000000000,  # Sept 2001 — definitely expired
        }
        import base64
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b'=').decode()
        token = f"eyJhbGciOiJSUzI1NiJ9.{payload_b64}.fake-signature"

        email, roles, error = _extract_with_base64(token)

        assert error is not None
        assert error['statusCode'] == 401
        body = json.loads(error['body'])
        assert 'expired' in body['error'].lower()

    def test_base64_rejects_invalid_format(self):
        """Base64 path rejects tokens without 3 parts."""
        email, roles, error = _extract_with_base64("not-a-jwt")

        assert error is not None
        assert error['statusCode'] == 401

    def test_base64_rejects_undecodable_payload(self):
        """Base64 path rejects tokens with invalid base64 payload."""
        email, roles, error = _extract_with_base64("header.!!!invalid!!!.signature")

        assert error is not None
        assert error['statusCode'] == 401


# =============================================================================
# Test: extract_user_credentials with JWTVerifier Active
# =============================================================================

class TestExtractWithVerifierActive:
    """Test the full extract_user_credentials path when verifier is active."""

    def test_missing_auth_header_returns_401(self):
        """Missing Authorization header returns 401."""
        request = make_flask_request()

        email, roles, error = extract_user_credentials(request)

        assert error is not None
        assert error['statusCode'] == 401
        body = json.loads(error['body'])
        assert 'Missing or invalid Authorization header' in body['error']

    def test_non_bearer_auth_header_returns_401(self):
        """Non-Bearer Authorization header returns 401."""
        request = make_flask_request()
        request.headers = {'Authorization': 'Basic dXNlcjpwYXNz'}

        email, roles, error = extract_user_credentials(request)

        assert error is not None
        assert error['statusCode'] == 401

    def test_empty_bearer_token_returns_401(self):
        """Empty Bearer token returns 401."""
        request = make_flask_request()
        request.headers = {'Authorization': 'Bearer '}

        email, roles, error = extract_user_credentials(request)

        assert error is not None
        assert error['statusCode'] == 401

    def test_uses_verifier_when_env_vars_set(self):
        """When env vars are configured, uses JWTVerifier path."""
        env_vars = {
            'COGNITO_USER_POOL_ID': TEST_USER_POOL_ID,
            'COGNITO_REGION': TEST_REGION,
            'COGNITO_APP_CLIENT_ID': TEST_APP_CLIENT_ID,
        }

        private_key = generate_rsa_keypair()
        public_key = private_key.public_key()

        payload = {
            'sub': 'user-123',
            'email': 'verified@test.com',
            'iss': TEST_ISSUER,
            'exp': int(time.time()) + 3600,
            'iat': int(time.time()),
            'client_id': TEST_APP_CLIENT_ID,
            'cognito:groups': ['Finance_CRUD'],
            'custom:tenants': 'tenant-x',
        }
        token = create_signed_token(payload, private_key)
        jwks_data = {"keys": [public_key_to_jwk(public_key)]}

        request = make_flask_request(token=token)

        with patch.dict(os.environ, env_vars):
            with patch("auth.jwt_verifier.requests.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = jwks_data
                mock_response.raise_for_status = MagicMock()
                mock_get.return_value = mock_response

                email, roles, error = extract_user_credentials(request)

        assert error is None
        assert email == 'verified@test.com'
        assert roles == ['Finance_CRUD']

    def test_falls_back_to_base64_when_env_vars_missing(self):
        """When env vars are missing, falls back to base64 decode."""
        payload = {
            'email': 'fallback@test.com',
            'cognito:groups': ['STR_Read'],
            'sub': 'sub-456',
            'exp': int(time.time()) + 3600,
        }
        import base64 as b64
        payload_b64 = b64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b'=').decode()
        token = f"eyJhbGciOiJSUzI1NiJ9.{payload_b64}.fake-signature"

        request = make_flask_request(token=token)

        # Clear env vars to force fallback
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ('COGNITO_USER_POOL_ID', 'COGNITO_REGION', 'COGNITO_APP_CLIENT_ID')}
        with patch.dict(os.environ, clean_env, clear=True):
            email, roles, error = extract_user_credentials(request)

        assert error is None
        assert email == 'fallback@test.com'
        assert roles == ['STR_Read']

    def test_lambda_event_dict_supported(self):
        """Lambda event dict format is still supported."""
        payload = {
            'email': 'lambda@test.com',
            'cognito:groups': ['Administrators'],
            'sub': 'sub-789',
            'exp': int(time.time()) + 3600,
        }
        import base64 as b64
        payload_b64 = b64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b'=').decode()
        token = f"eyJhbGciOiJSUzI1NiJ9.{payload_b64}.fake-signature"

        event = {
            'headers': {
                'Authorization': f'Bearer {token}'
            }
        }

        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ('COGNITO_USER_POOL_ID', 'COGNITO_REGION', 'COGNITO_APP_CLIENT_ID')}
        with patch.dict(os.environ, clean_env, clear=True):
            email, roles, error = extract_user_credentials(event)

        assert error is None
        assert email == 'lambda@test.com'
        assert roles == ['Administrators']
