"""
JWT Cryptographic Signature Verification for myAdmin

This module provides cryptographic verification of JWT tokens against the
AWS Cognito JWKS (JSON Web Key Set) endpoint, replacing the previous
base64 payload decoding approach.

Implements:
- RS256 signature verification using Cognito public keys
- JWKS caching with configurable TTL
- Single refresh-on-miss for unknown key IDs
- Claim validation (iss, aud/client_id, exp with clock skew)
- Graceful degradation when JWKS endpoint is unreachable
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

logger = logging.getLogger(__name__)


# --- Custom Exceptions ---


class InvalidTokenError(Exception):
    """Raised when JWT signature, issuer, or audience validation fails (HTTP 401)."""

    def __init__(self, message: str = "Invalid token"):
        self.message = message
        self.http_status = 401
        super().__init__(self.message)


class TokenExpiredError(Exception):
    """Raised when JWT has expired beyond clock skew tolerance (HTTP 401)."""

    def __init__(self, message: str = "Token has expired"):
        self.message = message
        self.http_status = 401
        super().__init__(self.message)


class ServiceUnavailableError(Exception):
    """Raised when JWKS endpoint is unreachable and no cached keys exist (HTTP 503)."""

    def __init__(self, message: str = "Authentication service unavailable"):
        self.message = message
        self.http_status = 503
        super().__init__(self.message)


# --- JWKS Cache ---


@dataclass
class JWKSCache:
    """In-memory cache for JWKS public keys."""

    keys: Dict[str, dict] = field(default_factory=dict)  # kid -> JWK dict
    fetched_at: float = 0.0
    ttl: int = 3600

    @property
    def is_expired(self) -> bool:
        """Check if cache has exceeded its TTL."""
        if self.fetched_at == 0.0:
            return True
        return (time.time() - self.fetched_at) > self.ttl

    @property
    def has_keys(self) -> bool:
        """Check if cache contains any keys."""
        return len(self.keys) > 0


# --- JWT Verifier ---


class JWTVerifier:
    """Cryptographic JWT verification against AWS Cognito JWKS.

    Fetches and caches the Cognito User Pool's public keys,
    then uses them to verify RS256 JWT token signatures and claims.

    Args:
        user_pool_id: AWS Cognito User Pool ID (e.g., 'eu-west-1_abc123')
        region: AWS region (e.g., 'eu-west-1')
        app_client_id: Cognito App Client ID for audience validation
        cache_ttl: JWKS cache TTL in seconds (default 3600)
        fetch_timeout: HTTP timeout for JWKS endpoint in seconds (default 5)
    """

    CLOCK_SKEW_SECONDS = 30
    ALGORITHM = "RS256"

    def __init__(
        self,
        user_pool_id: str,
        region: str,
        app_client_id: str,
        cache_ttl: int = 3600,
        fetch_timeout: int = 5,
    ):
        self.user_pool_id = user_pool_id
        self.region = region
        self.app_client_id = app_client_id
        self.fetch_timeout = fetch_timeout
        self.issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        self.jwks_url = f"{self.issuer}/.well-known/jwks.json"
        self._cache = JWKSCache(ttl=cache_ttl)

    def verify_token(self, token: str) -> dict:
        """Verify JWT token signature and claims.

        Decodes and validates the token against Cognito JWKS public keys.
        Checks RS256 signature, issuer, audience/client_id, and expiration.

        Args:
            token: Raw JWT token string (without 'Bearer ' prefix)

        Returns:
            Decoded JWT payload as a dictionary.

        Raises:
            InvalidTokenError: Signature, issuer, or audience validation failed.
            TokenExpiredError: Token has expired beyond clock skew tolerance.
            ServiceUnavailableError: JWKS endpoint unreachable with no cached keys.
        """
        # Decode header to get kid
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError:
            raise InvalidTokenError("Invalid token format")

        kid = unverified_header.get("kid")
        if not kid:
            raise InvalidTokenError("Token missing key ID (kid)")

        algorithm = unverified_header.get("alg")
        if algorithm != self.ALGORITHM:
            raise InvalidTokenError(
                f"Unsupported algorithm: {algorithm}. Only {self.ALGORITHM} is accepted"
            )

        # Get the signing key for this kid
        signing_key = self._get_signing_key(kid)

        # Verify and decode the token
        try:
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=[self.ALGORITHM],
                issuer=self.issuer,
                options={
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": False,  # We handle aud/client_id manually
                    "require": ["exp", "iss"],
                },
                leeway=self.CLOCK_SKEW_SECONDS,
            )
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidIssuerError:
            raise InvalidTokenError("Invalid token issuer")
        except jwt.InvalidSignatureError:
            raise InvalidTokenError("Invalid token signature")
        except jwt.DecodeError:
            raise InvalidTokenError("Invalid token signature")
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Invalid token: {str(e)}")

        # Validate audience (aud) or client_id claim
        self._validate_audience(payload)

        return payload

    def _validate_audience(self, payload: dict) -> None:
        """Validate the aud or client_id claim matches the app client ID.

        Cognito access tokens use 'client_id', while ID tokens use 'aud'.

        Args:
            payload: Decoded JWT payload.

        Raises:
            InvalidTokenError: Neither aud nor client_id matches.
        """
        aud = payload.get("aud")
        client_id = payload.get("client_id")

        # Check if either matches
        if aud == self.app_client_id:
            return
        if client_id == self.app_client_id:
            return

        # For aud as a list (rare but possible)
        if isinstance(aud, list) and self.app_client_id in aud:
            return

        raise InvalidTokenError("Invalid token audience")

    def _get_signing_key(self, kid: str) -> RSAPublicKey:
        """Get the RSA public key for the given key ID.

        Performs cache lookup first. If the kid is not found,
        refreshes the cache once and retries.

        Args:
            kid: Key ID from the JWT header.

        Returns:
            RSA public key for signature verification.

        Raises:
            InvalidTokenError: Key not found even after refresh.
            ServiceUnavailableError: Cannot fetch keys and no cache available.
        """
        # Ensure we have keys in cache
        if not self._cache.has_keys or self._cache.is_expired:
            self._refresh_cache()

        # Look up kid in cache
        if kid in self._cache.keys:
            return self._build_public_key(self._cache.keys[kid])

        # Kid not found — refresh once and retry
        self._refresh_cache()

        if kid in self._cache.keys:
            return self._build_public_key(self._cache.keys[kid])

        # Still not found after refresh
        raise InvalidTokenError("Token signing key not found")

    def _build_public_key(self, jwk_data: dict) -> RSAPublicKey:
        """Convert a JWK dictionary to an RSA public key object.

        Args:
            jwk_data: JWK key dictionary from JWKS endpoint.

        Returns:
            RSA public key suitable for PyJWT verification.
        """
        from jwt import algorithms

        return algorithms.RSAAlgorithm.from_jwk(jwk_data)

    def _fetch_jwks(self) -> dict:
        """Fetch JWKS from the Cognito endpoint.

        Makes an HTTP GET request to the JWKS URL with the configured timeout.

        Returns:
            JWKS response as a dictionary containing 'keys' array.

        Raises:
            ServiceUnavailableError: Endpoint unreachable with no cached keys.
        """
        try:
            response = requests.get(self.jwks_url, timeout=self.fetch_timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"Failed to fetch JWKS from {self.jwks_url}: {e}")
            # If we have cached keys, we can continue with those
            if self._cache.has_keys:
                logger.info("Using cached JWKS keys due to endpoint failure")
                return None
            # No cache available — service unavailable
            raise ServiceUnavailableError("Authentication service unavailable")

    def _refresh_cache(self) -> None:
        """Refresh the JWKS cache from the Cognito endpoint.

        Fetches fresh keys and updates the cache. If fetch fails but
        cached keys exist, the cache remains unchanged.
        """
        jwks_data = self._fetch_jwks()

        if jwks_data is None:
            # Fetch failed but we have cached keys — keep using them
            return

        keys = jwks_data.get("keys", [])
        key_map = {}
        for key in keys:
            kid = key.get("kid")
            if kid:
                key_map[kid] = key

        self._cache.keys = key_map
        self._cache.fetched_at = time.time()
