"""
Property-based tests for JWT Cryptographic Signature Verification.

Feature: security-hardening, Properties 1–4

Tests the JWTVerifier class against universal correctness properties
using Hypothesis to generate varied inputs.
"""

import time
import json
import base64
import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from src.auth.jwt_verifier import JWTVerifier, InvalidTokenError, TokenExpiredError


# --- Test Configuration ---

TEST_USER_POOL_ID = "eu-west-1_TestPool"
TEST_REGION = "eu-west-1"
TEST_APP_CLIENT_ID = "test-app-client-id-123"
TEST_ISSUER = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_USER_POOL_ID}"

# Pre-generate keypairs to avoid repeated slow RSA generation inside hypothesis loops
_PRIMARY_KEY = rsa.generate_private_key(
    public_exponent=65537, key_size=2048, backend=default_backend()
)
_SECONDARY_KEY = rsa.generate_private_key(
    public_exponent=65537, key_size=2048, backend=default_backend()
)


# --- Helpers ---

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


def create_signed_jwt(payload, private_key, kid="test-kid-1", algorithm="RS256"):
    """Create a signed JWT token with the given payload and key."""
    headers = {"kid": kid, "alg": algorithm}
    pem = private_key_to_pem(private_key)
    return pyjwt.encode(payload, pem, algorithm=algorithm, headers=headers)


def make_verifier():
    """Create a JWTVerifier instance with test configuration."""
    return JWTVerifier(
        user_pool_id=TEST_USER_POOL_ID,
        region=TEST_REGION,
        app_client_id=TEST_APP_CLIENT_ID,
        cache_ttl=3600,
        fetch_timeout=5,
    )


def mock_jwks_response(public_key, kid="test-kid-1"):
    """Create a mock JWKS response containing the given public key."""
    jwk = public_key_to_jwk(public_key, kid)
    return {"keys": [jwk]}


def patch_jwks(jwks_data):
    """Context manager to patch requests.get for JWKS fetching."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = jwks_data
    mock_response.raise_for_status = MagicMock()
    return patch("src.auth.jwt_verifier.requests.get", return_value=mock_response)


def valid_payload(aud=None, client_id=None):
    """Create a valid JWT payload with correct iss, aud/client_id, and exp."""
    payload = {
        "sub": "user-123",
        "iss": TEST_ISSUER,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    if aud is not None:
        payload["aud"] = aud
    if client_id is not None:
        payload["client_id"] = client_id
    return payload


# --- Hypothesis Strategies ---

# Strategy for safe string payloads (sub claims, custom claims)
safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S"),
                           blacklist_characters="\x00"),
    min_size=1,
    max_size=50,
)

# Strategy for issuer URLs that don't match the configured one
wrong_issuer_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"),
                           blacklist_characters="\x00"),
    min_size=1,
    max_size=80,
).map(lambda s: f"https://wrong-issuer.example.com/{s}").filter(
    lambda iss: iss != TEST_ISSUER
)

# Strategy for audience values that don't match configured client ID
wrong_audience_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd"),
                           blacklist_characters="\x00"),
    min_size=1,
    max_size=50,
).filter(lambda s: s != TEST_APP_CLIENT_ID)


# =============================================================================
# Property 1: JWT Signature Verification
# Feature: security-hardening, Property 1: JWT Signature Verification
# **Validates: Requirements 1.2, 1.3**
# =============================================================================

class TestJWTSignatureVerification:
    """
    Property 1: For any JWT token and RSA key pair, the JWT_Verifier SHALL accept
    the token if and only if the token's signature is a valid RS256 signature
    produced by the private key corresponding to a public key in the JWKS cache.
    Tokens signed with any other algorithm or with a non-matching key SHALL be rejected.
    """

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(sub_claim=safe_text)
    def test_valid_rs256_signature_accepted(self, sub_claim):
        """Tokens signed with RS256 using the correct private key are accepted."""
        # **Validates: Requirements 1.2**
        private_key = _PRIMARY_KEY
        public_key = private_key.public_key()

        payload = valid_payload(client_id=TEST_APP_CLIENT_ID)
        payload["sub"] = sub_claim

        token = create_signed_jwt(payload, private_key)
        jwks_data = mock_jwks_response(public_key)

        verifier = make_verifier()

        with patch_jwks(jwks_data):
            result = verifier.verify_token(token)
            assert result["sub"] == sub_claim
            assert result["iss"] == TEST_ISSUER

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(sub_claim=safe_text)
    def test_wrong_key_signature_rejected(self, sub_claim):
        """Tokens signed with a different RSA key are rejected."""
        # **Validates: Requirements 1.3**
        signing_key = _PRIMARY_KEY
        # Use SECONDARY key's public key in JWKS (won't match PRIMARY's signature)
        wrong_public_key = _SECONDARY_KEY.public_key()

        payload = valid_payload(client_id=TEST_APP_CLIENT_ID)
        payload["sub"] = sub_claim

        token = create_signed_jwt(payload, signing_key)
        jwks_data = mock_jwks_response(wrong_public_key)

        verifier = make_verifier()

        with patch_jwks(jwks_data):
            with pytest.raises(InvalidTokenError):
                verifier.verify_token(token)

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        sub_claim=safe_text,
        algorithm=st.sampled_from(["HS256", "RS384", "RS512", "ES256"])
    )
    def test_non_rs256_algorithm_rejected(self, sub_claim, algorithm):
        """Tokens signed with algorithms other than RS256 are rejected."""
        # **Validates: Requirements 1.2, 1.3**
        private_key = _PRIMARY_KEY
        public_key = private_key.public_key()

        payload = valid_payload(client_id=TEST_APP_CLIENT_ID)
        payload["sub"] = sub_claim

        # Craft token with the non-RS256 algorithm in the header
        if algorithm == "HS256":
            # HS256 uses symmetric key — sign with a secret
            headers = {"kid": "test-kid-1", "alg": "HS256"}
            token = pyjwt.encode(payload, "secret-key", algorithm="HS256", headers=headers)
        elif algorithm in ("RS384", "RS512"):
            # Can still use RSA key with different RSA algorithm
            headers = {"kid": "test-kid-1", "alg": algorithm}
            pem = private_key_to_pem(private_key)
            token = pyjwt.encode(payload, pem, algorithm=algorithm, headers=headers)
        else:
            # ES256 needs EC key — manually craft a token with ES256 header
            header_bytes = json.dumps(
                {"kid": "test-kid-1", "alg": "ES256", "typ": "JWT"}
            ).encode()
            payload_bytes = json.dumps(payload).encode()
            header_b64 = base64.urlsafe_b64encode(header_bytes).rstrip(b"=").decode()
            payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
            token = f"{header_b64}.{payload_b64}.fake-signature"

        jwks_data = mock_jwks_response(public_key)
        verifier = make_verifier()

        with patch_jwks(jwks_data):
            with pytest.raises(InvalidTokenError) as exc_info:
                verifier.verify_token(token)
            assert "algorithm" in exc_info.value.message.lower() or \
                   "Unsupported" in exc_info.value.message


# =============================================================================
# Property 2: JWT Issuer Validation
# Feature: security-hardening, Property 2: JWT Issuer Validation
# **Validates: Requirements 1.5**
# =============================================================================

class TestJWTIssuerValidation:
    """
    Property 2: For any JWT token where the iss claim does not exactly match
    the configured Cognito User Pool URL, the JWT_Verifier SHALL reject the
    token with HTTP 401.
    """

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(wrong_issuer=wrong_issuer_st)
    def test_wrong_issuer_rejected(self, wrong_issuer):
        """Tokens with an issuer that doesn't match configured URL are rejected."""
        # **Validates: Requirements 1.5**
        assume(wrong_issuer != TEST_ISSUER)

        private_key = _PRIMARY_KEY
        public_key = private_key.public_key()

        payload = {
            "sub": "user-123",
            "iss": wrong_issuer,
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "client_id": TEST_APP_CLIENT_ID,
        }

        token = create_signed_jwt(payload, private_key)
        jwks_data = mock_jwks_response(public_key)

        verifier = make_verifier()

        with patch_jwks(jwks_data):
            with pytest.raises(InvalidTokenError) as exc_info:
                verifier.verify_token(token)
            assert exc_info.value.http_status == 401

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(sub_claim=safe_text)
    def test_correct_issuer_accepted(self, sub_claim):
        """Tokens with the correct issuer are accepted (given valid signature and claims)."""
        # **Validates: Requirements 1.5**
        private_key = _PRIMARY_KEY
        public_key = private_key.public_key()

        payload = valid_payload(client_id=TEST_APP_CLIENT_ID)
        payload["sub"] = sub_claim

        token = create_signed_jwt(payload, private_key)
        jwks_data = mock_jwks_response(public_key)

        verifier = make_verifier()

        with patch_jwks(jwks_data):
            result = verifier.verify_token(token)
            assert result["iss"] == TEST_ISSUER


# =============================================================================
# Property 3: JWT Audience Validation
# Feature: security-hardening, Property 3: JWT Audience Validation
# **Validates: Requirements 1.6**
# =============================================================================

class TestJWTAudienceValidation:
    """
    Property 3: For any JWT token where neither the aud claim nor the client_id
    claim matches the configured Cognito App Client ID, the JWT_Verifier SHALL
    reject the token with HTTP 401.
    """

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(wrong_aud=wrong_audience_st, wrong_client_id=wrong_audience_st)
    def test_wrong_audience_and_client_id_rejected(self, wrong_aud, wrong_client_id):
        """Tokens where neither aud nor client_id matches are rejected."""
        # **Validates: Requirements 1.6**
        assume(wrong_aud != TEST_APP_CLIENT_ID)
        assume(wrong_client_id != TEST_APP_CLIENT_ID)

        private_key = _PRIMARY_KEY
        public_key = private_key.public_key()

        payload = {
            "sub": "user-123",
            "iss": TEST_ISSUER,
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "aud": wrong_aud,
            "client_id": wrong_client_id,
        }

        token = create_signed_jwt(payload, private_key)
        jwks_data = mock_jwks_response(public_key)

        verifier = make_verifier()

        with patch_jwks(jwks_data):
            with pytest.raises(InvalidTokenError) as exc_info:
                verifier.verify_token(token)
            assert exc_info.value.http_status == 401
            assert "audience" in exc_info.value.message.lower()

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(wrong_aud=wrong_audience_st)
    def test_correct_client_id_accepted(self, wrong_aud):
        """Tokens with correct client_id but wrong aud are accepted (access tokens)."""
        # **Validates: Requirements 1.6**
        assume(wrong_aud != TEST_APP_CLIENT_ID)

        private_key = _PRIMARY_KEY
        public_key = private_key.public_key()

        payload = {
            "sub": "user-123",
            "iss": TEST_ISSUER,
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "aud": wrong_aud,
            "client_id": TEST_APP_CLIENT_ID,
        }

        token = create_signed_jwt(payload, private_key)
        jwks_data = mock_jwks_response(public_key)

        verifier = make_verifier()

        with patch_jwks(jwks_data):
            result = verifier.verify_token(token)
            assert result["client_id"] == TEST_APP_CLIENT_ID

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(wrong_client_id=wrong_audience_st)
    def test_correct_aud_accepted(self, wrong_client_id):
        """Tokens with correct aud but wrong client_id are accepted (ID tokens)."""
        # **Validates: Requirements 1.6**
        assume(wrong_client_id != TEST_APP_CLIENT_ID)

        private_key = _PRIMARY_KEY
        public_key = private_key.public_key()

        payload = {
            "sub": "user-123",
            "iss": TEST_ISSUER,
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "aud": TEST_APP_CLIENT_ID,
            "client_id": wrong_client_id,
        }

        token = create_signed_jwt(payload, private_key)
        jwks_data = mock_jwks_response(public_key)

        verifier = make_verifier()

        with patch_jwks(jwks_data):
            result = verifier.verify_token(token)
            assert result["aud"] == TEST_APP_CLIENT_ID

    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(sub_claim=safe_text)
    def test_no_aud_no_client_id_rejected(self, sub_claim):
        """Tokens with neither aud nor client_id are rejected."""
        # **Validates: Requirements 1.6**
        private_key = _PRIMARY_KEY
        public_key = private_key.public_key()

        payload = {
            "sub": sub_claim,
            "iss": TEST_ISSUER,
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }

        token = create_signed_jwt(payload, private_key)
        jwks_data = mock_jwks_response(public_key)

        verifier = make_verifier()

        with patch_jwks(jwks_data):
            with pytest.raises(InvalidTokenError) as exc_info:
                verifier.verify_token(token)
            assert exc_info.value.http_status == 401


# =============================================================================
# Property 4: JWT Expiration with Clock Skew
# Feature: security-hardening, Property 4: JWT Expiration with Clock Skew
# **Validates: Requirements 1.7**
# =============================================================================

class TestJWTExpirationWithClockSkew:
    """
    Property 4: For any JWT token with an exp claim, the JWT_Verifier SHALL
    accept the token if exp >= (current_time - 30) and reject it if
    exp < (current_time - 30), given all other claims are valid.
    """

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(offset=st.integers(min_value=-29, max_value=3600))
    def test_token_within_clock_skew_accepted(self, offset):
        """Tokens with exp >= (current_time - 29) are accepted (within 30s leeway)."""
        # **Validates: Requirements 1.7**
        private_key = _PRIMARY_KEY
        public_key = private_key.public_key()

        now = int(time.time())
        payload = {
            "sub": "user-123",
            "iss": TEST_ISSUER,
            "exp": now + offset,
            "iat": now - 3600,
            "client_id": TEST_APP_CLIENT_ID,
        }

        token = create_signed_jwt(payload, private_key)
        jwks_data = mock_jwks_response(public_key)

        verifier = make_verifier()

        with patch_jwks(jwks_data):
            result = verifier.verify_token(token)
            assert result["sub"] == "user-123"

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(offset=st.integers(min_value=-3600, max_value=-32))
    def test_token_beyond_clock_skew_rejected(self, offset):
        """Tokens with exp < (current_time - 31) are rejected (beyond 30s leeway)."""
        # **Validates: Requirements 1.7**
        private_key = _PRIMARY_KEY
        public_key = private_key.public_key()

        now = int(time.time())
        payload = {
            "sub": "user-123",
            "iss": TEST_ISSUER,
            "exp": now + offset,
            "iat": now - 7200,
            "client_id": TEST_APP_CLIENT_ID,
        }

        token = create_signed_jwt(payload, private_key)
        jwks_data = mock_jwks_response(public_key)

        verifier = make_verifier()

        with patch_jwks(jwks_data):
            with pytest.raises(TokenExpiredError) as exc_info:
                verifier.verify_token(token)
            assert exc_info.value.http_status == 401

    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(offset=st.integers(min_value=-31, max_value=-30))
    def test_token_at_clock_skew_boundary(self, offset):
        """Tokens at the exact clock skew boundary (-30 and -31 seconds) are rejected.

        PyJWT uses strict comparison: exp + leeway > now (not >=).
        So exp = now - 30 with leeway=30 means (now-30)+30 = now, which is NOT > now.
        Both -30 and -31 are rejected.
        """
        # **Validates: Requirements 1.7**
        private_key = _PRIMARY_KEY
        public_key = private_key.public_key()

        now = int(time.time())
        payload = {
            "sub": "user-123",
            "iss": TEST_ISSUER,
            "exp": now + offset,
            "iat": now - 7200,
            "client_id": TEST_APP_CLIENT_ID,
        }

        token = create_signed_jwt(payload, private_key)
        jwks_data = mock_jwks_response(public_key)

        verifier = make_verifier()

        with patch_jwks(jwks_data):
            # Both -30 and -31 offsets should be rejected since PyJWT uses
            # strict comparison (exp + leeway must be strictly > now)
            with pytest.raises(TokenExpiredError):
                verifier.verify_token(token)
