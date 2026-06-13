"""
Unit tests for JWT Verifier edge cases.

Feature: security-hardening, Task 1.4
Validates: Requirements 1.4, 1.8, 1.9

Tests cover:
- Kid refresh flow (unknown kid triggers single cache refresh)
- JWKS endpoint timeout (returns cached keys or 503)
- Specific error messages for each rejection reason
- Cache TTL expiration and refresh
"""

import time
import json
import pytest
from unittest.mock import patch, MagicMock, call

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from src.auth.jwt_verifier import (
    JWTVerifier,
    JWKSCache,
    InvalidTokenError,
    TokenExpiredError,
    ServiceUnavailableError,
)


# --- Test Configuration ---

TEST_USER_POOL_ID = "eu-west-1_TestPool"
TEST_REGION = "eu-west-1"
TEST_APP_CLIENT_ID = "test-app-client-id-123"
TEST_ISSUER = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_USER_POOL_ID}"

# Pre-generate keypairs for tests
_KEY_A = rsa.generate_private_key(
    public_exponent=65537, key_size=2048, backend=default_backend()
)
_KEY_B = rsa.generate_private_key(
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


def make_verifier(cache_ttl=3600, fetch_timeout=5):
    """Create a JWTVerifier instance with test configuration."""
    return JWTVerifier(
        user_pool_id=TEST_USER_POOL_ID,
        region=TEST_REGION,
        app_client_id=TEST_APP_CLIENT_ID,
        cache_ttl=cache_ttl,
        fetch_timeout=fetch_timeout,
    )


def valid_payload():
    """Create a valid JWT payload."""
    return {
        "sub": "user-123",
        "iss": TEST_ISSUER,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "client_id": TEST_APP_CLIENT_ID,
    }


def mock_jwks_response(*keys_with_kids):
    """Create a mock JWKS response containing multiple keys.

    Args:
        keys_with_kids: tuples of (public_key, kid)
    """
    keys = []
    for public_key, kid in keys_with_kids:
        keys.append(public_key_to_jwk(public_key, kid))
    return {"keys": keys}


def create_requests_mock(jwks_data):
    """Create a mock for requests.get that returns JWKS data."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = jwks_data
    mock_response.raise_for_status = MagicMock()
    return mock_response


# =============================================================================
# Test: Kid Refresh Flow
# Validates: Requirement 1.4
# =============================================================================


class TestKidRefreshFlow:
    """Test that unknown kid triggers a single cache refresh."""

    def test_unknown_kid_triggers_cache_refresh_and_succeeds(self):
        """When kid not in cache, verifier refreshes JWKS once and finds the key."""
        # Requirement 1.4: refresh JWKS cache once and retry verification
        verifier = make_verifier()

        # Initial JWKS only has key A with kid-A
        initial_jwks = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        # After refresh, JWKS has both key A and key B (new kid-B)
        refreshed_jwks = mock_jwks_response(
            (_KEY_A.public_key(), "kid-A"),
            (_KEY_B.public_key(), "kid-B"),
        )

        # Sign token with key B (kid-B) — not yet in cache
        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_B, kid="kid-B")

        # First call returns initial JWKS (no kid-B), second call returns refreshed JWKS
        mock_resp_initial = create_requests_mock(initial_jwks)
        mock_resp_refreshed = create_requests_mock(refreshed_jwks)

        with patch("src.auth.jwt_verifier.requests.get") as mock_get:
            mock_get.side_effect = [mock_resp_initial, mock_resp_refreshed]
            result = verifier.verify_token(token)

        assert result["sub"] == "user-123"
        # Should have called JWKS endpoint twice (initial fetch + refresh)
        assert mock_get.call_count == 2

    def test_unknown_kid_after_refresh_raises_invalid_token(self):
        """When kid not found even after refresh, raises InvalidTokenError."""
        # Requirement 1.4: reject the request with HTTP 401
        verifier = make_verifier()

        # JWKS only has kid-A, token is signed with kid-C (never available)
        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_B, kid="kid-C")

        mock_resp = create_requests_mock(jwks_data)

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp):
            with pytest.raises(InvalidTokenError) as exc_info:
                verifier.verify_token(token)

        assert exc_info.value.message == "Token signing key not found"
        assert exc_info.value.http_status == 401

    def test_kid_refresh_only_happens_once(self):
        """Verifier should refresh at most once per verify_token call for unknown kid."""
        # Requirement 1.4: refresh the JWKS cache ONCE and retry
        verifier = make_verifier()

        # Both initial and refreshed JWKS only have kid-A
        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_B, kid="kid-unknown")

        mock_resp = create_requests_mock(jwks_data)

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp) as mock_get:
            with pytest.raises(InvalidTokenError):
                verifier.verify_token(token)

        # Cache was empty initially -> first fetch + one refresh = 2 calls max
        assert mock_get.call_count == 2


# =============================================================================
# Test: JWKS Endpoint Timeout
# Validates: Requirement 1.9
# =============================================================================


class TestJWKSEndpointTimeout:
    """Test JWKS endpoint timeout handling (cached keys fallback or 503)."""

    def test_timeout_with_cached_keys_uses_cache(self):
        """When JWKS endpoint times out but cache has keys, verification succeeds."""
        # Requirement 1.9: continue using previously cached keys if available
        verifier = make_verifier()

        # First, populate the cache successfully
        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        mock_resp_ok = create_requests_mock(jwks_data)

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp_ok):
            result = verifier.verify_token(token)
        assert result["sub"] == "user-123"

        # Now simulate timeout on next request — cache should still work
        import requests as req_lib

        with patch(
            "src.auth.jwt_verifier.requests.get",
            side_effect=req_lib.Timeout("Connection timed out"),
        ):
            # Create a new token (same kid) — should use cached keys
            payload2 = valid_payload()
            payload2["sub"] = "user-456"
            token2 = create_signed_jwt(payload2, _KEY_A, kid="kid-A")

            # Force cache expiry so it tries to refresh
            verifier._cache.fetched_at = time.time() - 7200  # expired
            result2 = verifier.verify_token(token2)

        assert result2["sub"] == "user-456"

    def test_timeout_with_no_cache_raises_service_unavailable(self):
        """When JWKS endpoint times out and no cached keys exist, raises 503."""
        # Requirement 1.9: reject with HTTP 503 if no cached keys exist
        verifier = make_verifier()

        import requests as req_lib

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch(
            "src.auth.jwt_verifier.requests.get",
            side_effect=req_lib.Timeout("Connection timed out"),
        ):
            with pytest.raises(ServiceUnavailableError) as exc_info:
                verifier.verify_token(token)

        assert exc_info.value.message == "Authentication service unavailable"
        assert exc_info.value.http_status == 503

    def test_connection_error_with_no_cache_raises_service_unavailable(self):
        """When JWKS endpoint has connection error and no cache, raises 503."""
        # Requirement 1.9: reject with HTTP 503
        verifier = make_verifier()

        import requests as req_lib

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch(
            "src.auth.jwt_verifier.requests.get",
            side_effect=req_lib.ConnectionError("DNS resolution failed"),
        ):
            with pytest.raises(ServiceUnavailableError) as exc_info:
                verifier.verify_token(token)

        assert exc_info.value.http_status == 503

    def test_http_500_from_jwks_with_cache_uses_cached_keys(self):
        """When JWKS returns 500 but cache has keys, falls back to cache."""
        # Requirement 1.9: continue using previously cached keys
        verifier = make_verifier()

        # Populate cache
        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        mock_resp_ok = create_requests_mock(jwks_data)

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp_ok):
            verifier.verify_token(token)

        # Now JWKS returns HTTP 500
        import requests as req_lib

        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500
        mock_resp_500.raise_for_status.side_effect = req_lib.HTTPError("500 Server Error")

        # Expire cache to force refresh attempt
        verifier._cache.fetched_at = time.time() - 7200

        payload2 = valid_payload()
        payload2["sub"] = "user-789"
        token2 = create_signed_jwt(payload2, _KEY_A, kid="kid-A")

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp_500):
            result = verifier.verify_token(token2)

        assert result["sub"] == "user-789"


# =============================================================================
# Test: Specific Error Messages
# Validates: Requirements 1.3, 1.4, 1.5, 1.6, 1.7, 1.9
# =============================================================================


class TestErrorMessages:
    """Test that each rejection reason produces the correct error message."""

    def test_invalid_signature_message(self):
        """Invalid signature returns 'Invalid token signature'."""
        verifier = make_verifier()

        # Sign with key B but JWKS only has key A
        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        payload = valid_payload()
        # Use kid-A so it finds the key but signature won't match
        token = create_signed_jwt(payload, _KEY_B, kid="kid-A")

        mock_resp = create_requests_mock(jwks_data)

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp):
            with pytest.raises(InvalidTokenError) as exc_info:
                verifier.verify_token(token)

        assert exc_info.value.message == "Invalid token signature"

    def test_signing_key_not_found_message(self):
        """Unknown kid (after refresh) returns 'Token signing key not found'."""
        verifier = make_verifier()

        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_B, kid="kid-nonexistent")

        mock_resp = create_requests_mock(jwks_data)

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp):
            with pytest.raises(InvalidTokenError) as exc_info:
                verifier.verify_token(token)

        assert exc_info.value.message == "Token signing key not found"

    def test_invalid_issuer_message(self):
        """Wrong issuer returns 'Invalid token issuer'."""
        verifier = make_verifier()

        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        payload = valid_payload()
        payload["iss"] = "https://wrong-issuer.example.com/pool123"
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        mock_resp = create_requests_mock(jwks_data)

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp):
            with pytest.raises(InvalidTokenError) as exc_info:
                verifier.verify_token(token)

        assert exc_info.value.message == "Invalid token issuer"

    def test_invalid_audience_message(self):
        """Wrong audience returns 'Invalid token audience'."""
        verifier = make_verifier()

        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        payload = valid_payload()
        payload["client_id"] = "wrong-client-id"
        payload["aud"] = "wrong-audience"
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        mock_resp = create_requests_mock(jwks_data)

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp):
            with pytest.raises(InvalidTokenError) as exc_info:
                verifier.verify_token(token)

        assert exc_info.value.message == "Invalid token audience"

    def test_token_expired_message(self):
        """Expired token returns 'Token has expired'."""
        verifier = make_verifier()

        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        payload = valid_payload()
        payload["exp"] = int(time.time()) - 120  # Expired 2 minutes ago (beyond 30s skew)
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        mock_resp = create_requests_mock(jwks_data)

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp):
            with pytest.raises(TokenExpiredError) as exc_info:
                verifier.verify_token(token)

        assert exc_info.value.message == "Token has expired"

    def test_service_unavailable_message(self):
        """JWKS endpoint unreachable with no cache returns 'Authentication service unavailable'."""
        verifier = make_verifier()

        import requests as req_lib

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch(
            "src.auth.jwt_verifier.requests.get",
            side_effect=req_lib.ConnectionError("Failed to connect"),
        ):
            with pytest.raises(ServiceUnavailableError) as exc_info:
                verifier.verify_token(token)

        assert exc_info.value.message == "Authentication service unavailable"


# =============================================================================
# Test: Cache TTL Expiration and Refresh
# Validates: Requirement 1.8
# =============================================================================


class TestCacheTTLExpiration:
    """Test JWKS cache TTL behavior and refresh on expiration."""

    def test_cache_is_expired_after_ttl(self):
        """Cache is_expired returns True when fetched_at + TTL < now."""
        # Requirement 1.8: configurable TTL defaulting to 3600 seconds
        cache = JWKSCache(ttl=3600)
        cache.fetched_at = time.time() - 3601  # 1 second past TTL
        cache.keys = {"kid-A": {"kty": "RSA"}}

        assert cache.is_expired is True

    def test_cache_is_not_expired_within_ttl(self):
        """Cache is_expired returns False when within TTL window."""
        cache = JWKSCache(ttl=3600)
        cache.fetched_at = time.time() - 3500  # Within TTL
        cache.keys = {"kid-A": {"kty": "RSA"}}

        assert cache.is_expired is False

    def test_cache_empty_considered_expired(self):
        """Empty cache (fetched_at=0.0) is always considered expired."""
        cache = JWKSCache(ttl=3600)
        assert cache.is_expired is True
        assert cache.has_keys is False

    def test_expired_cache_triggers_refresh_on_verify(self):
        """When cache TTL expires, next verify_token call triggers JWKS refresh."""
        # Requirement 1.8: cache with configurable TTL
        verifier = make_verifier(cache_ttl=3600)

        # Populate cache
        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        mock_resp = create_requests_mock(jwks_data)

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp) as mock_get:
            verifier.verify_token(token)
            first_call_count = mock_get.call_count

        # Expire the cache manually
        verifier._cache.fetched_at = time.time() - 7200  # Well past TTL

        # Next verify should trigger refresh
        payload2 = valid_payload()
        payload2["sub"] = "user-refreshed"
        token2 = create_signed_jwt(payload2, _KEY_A, kid="kid-A")

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp) as mock_get:
            result = verifier.verify_token(token2)

        assert result["sub"] == "user-refreshed"
        # Should have made at least one call to refresh
        assert mock_get.call_count >= 1

    def test_cache_not_refreshed_when_within_ttl(self):
        """When cache is within TTL, verify_token does not call JWKS endpoint."""
        # Requirement 1.8: uses cache within TTL
        verifier = make_verifier(cache_ttl=3600)

        # Populate cache with a direct call
        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        mock_resp = create_requests_mock(jwks_data)

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp):
            verifier.verify_token(token)

        # Verify that cache is populated and not expired
        assert verifier._cache.has_keys is True
        assert verifier._cache.is_expired is False

        # Next call should NOT hit JWKS endpoint (cache is valid)
        payload2 = valid_payload()
        payload2["sub"] = "user-cached"
        token2 = create_signed_jwt(payload2, _KEY_A, kid="kid-A")

        with patch("src.auth.jwt_verifier.requests.get") as mock_get:
            result = verifier.verify_token(token2)

        assert result["sub"] == "user-cached"
        # No calls to JWKS endpoint — cache is still valid
        mock_get.assert_not_called()

    def test_custom_cache_ttl_respected(self):
        """Custom TTL values are respected in cache expiration logic."""
        # Requirement 1.8: configurable TTL
        verifier = make_verifier(cache_ttl=60)  # 60 seconds TTL

        # Populate cache
        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        mock_resp = create_requests_mock(jwks_data)

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp):
            verifier.verify_token(token)

        # Set fetched_at to 61 seconds ago (past the 60s TTL)
        verifier._cache.fetched_at = time.time() - 61
        assert verifier._cache.is_expired is True

        # Set fetched_at to 59 seconds ago (within the 60s TTL)
        verifier._cache.fetched_at = time.time() - 59
        assert verifier._cache.is_expired is False

    def test_fetch_timeout_configuration(self):
        """Fetch timeout is passed to requests.get."""
        # Requirement 1.8: fetch timeout of 5 seconds
        verifier = make_verifier(fetch_timeout=3)

        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        mock_resp = create_requests_mock(jwks_data)

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch("src.auth.jwt_verifier.requests.get", return_value=mock_resp) as mock_get:
            verifier.verify_token(token)

        # Verify timeout parameter was passed correctly
        mock_get.assert_called_with(verifier.jwks_url, timeout=3)
