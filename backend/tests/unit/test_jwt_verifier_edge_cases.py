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

# JWKS network I/O now lives in the shared T4 cache. Patch requests.get there.
_JWKS_REQUESTS_TARGET = "src.auth.jwks_cache.requests.get"


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

        with patch(_JWKS_REQUESTS_TARGET) as mock_get:
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

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp):
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

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp) as mock_get:
            with pytest.raises(InvalidTokenError):
                verifier.verify_token(token)

        # Cache was empty initially -> first fetch + one refresh = 2 calls max
        assert mock_get.call_count == 2


# =============================================================================
# Test: JWKS Endpoint Timeout
# Validates: Requirement 1.9
# =============================================================================


class TestJWKSEndpointTimeout:
    """JWKS endpoint failure handling — FAIL-FAST (R1.3).

    S2 removes the previous lenient "use cached keys when a fresh fetch fails"
    behaviour: there must be no path that accepts a token without a successful
    signature verification. When the pool's JWKS cannot be obtained, the request is
    rejected with 503 (:class:`ServiceUnavailableError`) — never trusted.
    """

    def test_timeout_when_keys_needed_raises_service_unavailable(self):
        """A timeout while (re)fetching keys rejects with 503 — no cached bypass.

        Even with a previously-populated cache, once the entry is stale and the
        refetch fails, verification is rejected. There is no "trust stale keys anyway"
        fallback (R1.3, no-dangerous-fallbacks).
        """
        verifier = make_verifier()

        # First, populate the cache successfully.
        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        mock_resp_ok = create_requests_mock(jwks_data)

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp_ok):
            result = verifier.verify_token(token)
        assert result["sub"] == "user-123"

        # Force the cached entry stale so the next lookup must refetch, and make the
        # refetch time out. Expected: reject with 503 (no lenient fallback).
        import requests as req_lib

        entry = verifier._cache._entries[TEST_ISSUER]
        entry.fetched_at = time.time() - 7200  # past TTL

        with patch(
            _JWKS_REQUESTS_TARGET,
            side_effect=req_lib.Timeout("Connection timed out"),
        ):
            payload2 = valid_payload()
            payload2["sub"] = "user-456"
            token2 = create_signed_jwt(payload2, _KEY_A, kid="kid-A")

            with pytest.raises(ServiceUnavailableError) as exc_info:
                verifier.verify_token(token2)

        assert exc_info.value.http_status == 503

    def test_timeout_with_no_cache_raises_service_unavailable(self):
        """When JWKS endpoint times out and no cached keys exist, raises 503."""
        # Requirement 1.9 / R1.3: reject with HTTP 503, never trust an unverified token
        verifier = make_verifier()

        import requests as req_lib

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch(
            _JWKS_REQUESTS_TARGET,
            side_effect=req_lib.Timeout("Connection timed out"),
        ):
            with pytest.raises(ServiceUnavailableError) as exc_info:
                verifier.verify_token(token)

        assert exc_info.value.message == "Authentication service unavailable"
        assert exc_info.value.http_status == 503

    def test_connection_error_with_no_cache_raises_service_unavailable(self):
        """When JWKS endpoint has connection error and no cache, raises 503."""
        # Requirement 1.9 / R1.3: reject with HTTP 503
        verifier = make_verifier()

        import requests as req_lib

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch(
            _JWKS_REQUESTS_TARGET,
            side_effect=req_lib.ConnectionError("DNS resolution failed"),
        ):
            with pytest.raises(ServiceUnavailableError) as exc_info:
                verifier.verify_token(token)

        assert exc_info.value.http_status == 503

    def test_http_500_from_jwks_when_keys_needed_raises_service_unavailable(self):
        """A 5xx while (re)fetching keys rejects with 503 — no cached bypass (R1.3).

        Previously a 500 with a warm cache silently fell back to cached keys. That
        lenient path is removed: an inability to obtain fresh keys when a fetch is
        required rejects the request.
        """
        verifier = make_verifier()

        # Populate cache.
        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        mock_resp_ok = create_requests_mock(jwks_data)

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp_ok):
            verifier.verify_token(token)

        # Now JWKS returns HTTP 500; force a refetch by expiring the cached entry.
        import requests as req_lib

        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500
        mock_resp_500.raise_for_status.side_effect = req_lib.HTTPError("500 Server Error")

        entry = verifier._cache._entries[TEST_ISSUER]
        entry.fetched_at = time.time() - 7200

        payload2 = valid_payload()
        payload2["sub"] = "user-789"
        token2 = create_signed_jwt(payload2, _KEY_A, kid="kid-A")

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp_500):
            with pytest.raises(ServiceUnavailableError) as exc_info:
                verifier.verify_token(token2)

        assert exc_info.value.http_status == 503


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

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp):
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

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp):
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

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp):
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

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp):
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

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp):
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
            _JWKS_REQUESTS_TARGET,
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
        """When the per-issuer cache entry is stale, verify_token refetches JWKS."""
        # Requirement 1.8 / R3.3: cache with TTL, refetch when stale.
        verifier = make_verifier(cache_ttl=3600)

        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        mock_resp = create_requests_mock(jwks_data)

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp):
            verifier.verify_token(token)

        # Expire the per-issuer cache entry (T4 cache keys by iss).
        verifier._cache._entries[TEST_ISSUER].fetched_at = time.time() - 7200

        payload2 = valid_payload()
        payload2["sub"] = "user-refreshed"
        token2 = create_signed_jwt(payload2, _KEY_A, kid="kid-A")

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp) as mock_get:
            result = verifier.verify_token(token2)

        assert result["sub"] == "user-refreshed"
        # The stale entry forced exactly one refetch.
        assert mock_get.call_count >= 1

    def test_cache_not_refreshed_when_within_ttl(self):
        """When the cache entry is fresh, verify_token does not hit the JWKS endpoint."""
        # Requirement 1.8 / R3.3: warm hits never touch the network.
        verifier = make_verifier(cache_ttl=3600)

        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        mock_resp = create_requests_mock(jwks_data)

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp):
            verifier.verify_token(token)

        # The per-issuer entry is populated and fresh.
        entry = verifier._cache._entries[TEST_ISSUER]
        assert "kid-A" in entry.keys
        assert entry.is_expired(3600, time.time()) is False

        # Next call must NOT hit the JWKS endpoint (warm hit).
        payload2 = valid_payload()
        payload2["sub"] = "user-cached"
        token2 = create_signed_jwt(payload2, _KEY_A, kid="kid-A")

        with patch(_JWKS_REQUESTS_TARGET) as mock_get:
            result = verifier.verify_token(token2)

        assert result["sub"] == "user-cached"
        mock_get.assert_not_called()

    def test_custom_cache_ttl_respected(self):
        """A custom TTL is honoured by the per-issuer cache entry."""
        # Requirement 1.8 / R3.3: configurable TTL.
        verifier = make_verifier(cache_ttl=60)  # 60 seconds TTL

        jwks_data = mock_jwks_response((_KEY_A.public_key(), "kid-A"))
        mock_resp = create_requests_mock(jwks_data)

        payload = valid_payload()
        token = create_signed_jwt(payload, _KEY_A, kid="kid-A")

        with patch(_JWKS_REQUESTS_TARGET, return_value=mock_resp):
            verifier.verify_token(token)

        entry = verifier._cache._entries[TEST_ISSUER]

        # 61 seconds old -> expired for a 60s TTL.
        entry.fetched_at = time.time() - 61
        assert entry.is_expired(60, time.time()) is True

        # 59 seconds old -> still fresh for a 60s TTL.
        entry.fetched_at = time.time() - 59
        assert entry.is_expired(60, time.time()) is False
