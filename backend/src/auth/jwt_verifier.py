"""
JWT Cryptographic Signature Verification for myAdmin (multi-pool, S2 / T5).

This module verifies JWT access tokens against the *issuing* Cognito pool's JWKS.
It is **multi-pool aware** (R3): instead of a single hard-coded pool, the verifier
resolves the pool by the token's ``iss`` claim through the issuer->pool registry
(T3, :mod:`auth.pool_registry`) and verifies against **that** pool's JWKS via the
shared fail-fast cache (T4, :mod:`auth.jwks_cache`). Adding a pool (the standing test
pool now, production Pool A in Phase 6, Pool B later) is a **registry entry, not a
code change** (R3.2).

Verification contract (design.md "Verification contract", R1.2):

1. Decode the header for ``kid`` + ``alg`` (must be RS256).
2. Read the **unverified** ``iss`` *only* to select the pool via
   :meth:`PoolRegistry.require` (unknown issuer -> 401).
3. Fetch that pool's JWKS through the T4 cache and select the signing key by ``kid``
   (unknown kid after one refetch -> 401).
4. Verify the **RS256 signature**, ``iss`` matches the resolved pool, the
   audience/``client_id`` matches the pool's audience, and ``exp`` (30s clock-skew
   leeway). Any failure -> **401, no fallback, no partial trust** (R1.3).
5. Only then return the decoded payload for claim reading (roles/tenant) upstream.

**No dangerous fallback (R1.3):** there is no path that accepts a token without a
successful RS256 signature verification. JWKS is obtained only through the T4 cache,
which is fail-fast — a genuine inability to obtain keys surfaces as
:class:`ServiceUnavailableError` (503) and *rejects* the request; it is never a way
to skip verification.

Backward compatibility: the historical single-pool constructor
``JWTVerifier(user_pool_id, region, app_client_id, ...)`` still works — it builds a
one-entry registry internally (:meth:`JWTVerifier.from_single_pool`) so existing
callers (``cognito_utils.py``) and tests keep working unchanged.
"""

import logging
import time
from dataclasses import dataclass, field

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from auth.jwks_cache import (
    JWKSCache as PoolJWKSCache,
)
from auth.jwks_cache import (
    JWKSFetchError,
    UnknownIssuerError,
    UnknownKidError,
)
from auth.pool_registry import PoolRegistry
from auth.test_pool_config import PoolConfig

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
    """Raised when JWKS endpoint is unreachable so keys cannot be obtained (HTTP 503).

    This is a genuine "cannot obtain the signing keys at all" outcome — it *rejects*
    the request. It is **never** a way to skip signature verification (R1.3).
    """

    def __init__(self, message: str = "Authentication service unavailable"):
        self.message = message
        self.http_status = 503
        super().__init__(self.message)


# --- Legacy JWKS cache dataclass (kept for backward-compatible imports) ---


@dataclass
class JWKSCache:
    """In-memory JWKS cache shape retained for backward-compatible imports/tests.

    The live verification path uses the shared, fail-fast per-issuer cache in
    :mod:`auth.jwks_cache` (T4). This dataclass is preserved so existing imports
    (``from auth.jwt_verifier import JWKSCache``) and TTL-behaviour tests keep working.
    """

    keys: dict[str, dict] = field(default_factory=dict)  # kid -> JWK dict
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
    """Multi-pool cryptographic JWT verification via the issuer->pool registry (R3).

    The verifier resolves the issuing pool from the token's ``iss`` claim using the
    injected :class:`~auth.pool_registry.PoolRegistry`, then verifies the RS256
    signature and standard claims against **that** pool's JWKS, obtained through the
    shared fail-fast cache (:class:`auth.jwks_cache.JWKSCache`, T4). Adding a pool is
    configuration (a registry entry), never a code change.

    Prefer composition: construct with a ``registry`` (and optionally a shared
    ``jwks_cache``) so one verifier serves every registered issuer::

        verifier = JWTVerifier(registry=load_pool_registry())
        payload = verifier.verify_token(token)

    Backward compatibility: the historical single-pool signature
    ``JWTVerifier(user_pool_id, region, app_client_id, ...)`` still works — it builds a
    one-entry registry internally (see :meth:`from_single_pool`).

    Args:
        registry: The issuer->pool registry (T3). Required unless the legacy
            single-pool positional args are supplied.
        jwks_cache: Optional shared :class:`auth.jwks_cache.JWKSCache`. If omitted,
            the verifier creates its own instance bound to ``registry``.
        user_pool_id: (legacy) AWS Cognito User Pool ID for the single-pool path.
        region: (legacy) AWS region for the single-pool path.
        app_client_id: (legacy) Cognito App Client ID (audience) for the single-pool
            path.
        cache_ttl: JWKS cache TTL in seconds (default 3600).
        fetch_timeout: Retained for signature compatibility (the T4 cache owns the
            HTTP timeout).
    """

    CLOCK_SKEW_SECONDS = 30
    ALGORITHM = "RS256"

    def __init__(
        self,
        user_pool_id: str | None = None,
        region: str | None = None,
        app_client_id: str | None = None,
        cache_ttl: int = 3600,
        fetch_timeout: int = 5,
        *,
        registry: PoolRegistry | None = None,
        jwks_cache: PoolJWKSCache | None = None,
    ):
        self.fetch_timeout = fetch_timeout

        if registry is not None:
            # --- Preferred multi-pool path (composition). ---
            self._registry = registry
            self._legacy_single_pool = False
            self.user_pool_id = user_pool_id
            self.region = region
            self.app_client_id = app_client_id
            self.issuer = None
            self.jwks_url = None
        elif (
            user_pool_id is not None
            and region is not None
            and app_client_id is not None
        ):
            # --- Backward-compatible single-pool path: build a one-entry registry. ---
            self._legacy_single_pool = True
            self.user_pool_id = user_pool_id
            self.region = region
            self.app_client_id = app_client_id
            self.issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
            self.jwks_url = f"{self.issuer}/.well-known/jwks.json"
            pool = PoolConfig(
                iss=self.issuer,
                jwks_uri=self.jwks_url,
                audience=app_client_id,
                pool_label=f"single-pool:{user_pool_id}",
            )
            self._registry = PoolRegistry([pool])
        else:
            raise ValueError(
                "JWTVerifier requires either a `registry` (multi-pool) or the "
                "single-pool args (user_pool_id, region, app_client_id)."
            )

        # The shared, fail-fast JWKS cache (T4). If not injected, build a private
        # instance bound to this verifier's registry. A per-instance cache is used
        # (rather than the process-wide module cache) so each verifier — including
        # the legacy single-pool ones in tests — keeps an isolated key-set.
        self._cache = jwks_cache or PoolJWKSCache(
            registry=self._registry, ttl_seconds=cache_ttl
        )

    @classmethod
    def from_single_pool(
        cls,
        user_pool_id: str,
        region: str,
        app_client_id: str,
        cache_ttl: int = 3600,
        fetch_timeout: int = 5,
    ) -> "JWTVerifier":
        """Build a verifier for a single Cognito pool (a one-entry registry).

        Convenience for callers that only know one pool's coordinates. Internally
        this is identical to the multi-pool path with a registry of one entry, so
        there is a single verification code path.
        """
        return cls(
            user_pool_id=user_pool_id,
            region=region,
            app_client_id=app_client_id,
            cache_ttl=cache_ttl,
            fetch_timeout=fetch_timeout,
        )

    def verify_token(self, token: str) -> dict:
        """Verify a JWT's signature and claims against its issuing pool.

        Resolves the pool from the token's (unverified) ``iss``, fetches that pool's
        JWKS through the fail-fast T4 cache, and verifies RS256 signature + ``iss`` +
        audience/``client_id`` + ``exp`` (30s leeway). Any failure -> 401, with no
        fallback path that would accept an unverified token (R1.3).

        Args:
            token: Raw JWT token string (without the 'Bearer ' prefix).

        Returns:
            The decoded, verified JWT payload as a dict.

        Raises:
            InvalidTokenError: Malformed token, wrong algorithm, unknown issuer,
                unknown signing key, bad signature, wrong issuer/audience (HTTP 401).
            TokenExpiredError: Token expired beyond the clock-skew leeway (HTTP 401).
            ServiceUnavailableError: The pool's JWKS could not be obtained at all
                (HTTP 503) — the request is rejected, never trusted.
        """
        # (1) Decode the header for kid + alg (no signature trust yet).
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

        # (2) Read the UNVERIFIED iss ONLY to select the pool. We do not trust any
        # claim here — selection just picks which pool's keys/audience to verify
        # against. Signature verification below is what establishes trust.
        try:
            unverified_claims = jwt.decode(token, options={"verify_signature": False})
        except jwt.exceptions.DecodeError:
            raise InvalidTokenError("Invalid token format")

        iss = unverified_claims.get("iss")
        if not iss:
            raise InvalidTokenError("Token missing issuer (iss)")

        # Resolve the pool (unknown issuer -> 401, no guessed endpoint).
        try:
            pool = self._registry.require(iss)
        except UnknownIssuerError:
            logger.warning("Rejecting token from unregistered issuer '%s'", iss)
            raise InvalidTokenError("Invalid token issuer")

        # (3) Get the signing key for this (iss, kid) from the fail-fast T4 cache.
        signing_key = self._get_signing_key(iss, kid)

        # (4) Verify signature + iss + exp against the resolved pool's key.
        try:
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=[self.ALGORITHM],
                issuer=pool.iss,
                options={
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": False,  # aud/client_id handled explicitly below
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
            raise InvalidTokenError(f"Invalid token: {e!s}")

        # (4b) Verify audience/client_id against THIS pool's configured audience.
        self._validate_audience(payload, pool.audience)

        return payload

    def _validate_audience(self, payload: dict, expected_audience: str) -> None:
        """Validate ``aud`` or ``client_id`` matches the resolved pool's audience.

        Cognito access tokens carry ``client_id``; ID tokens carry ``aud``. Either
        matching the pool's configured app-client id is accepted.

        Args:
            payload: The decoded (signature-verified) JWT payload.
            expected_audience: The resolved pool's app-client id.

        Raises:
            InvalidTokenError: Neither ``aud`` nor ``client_id`` matches.
        """
        aud = payload.get("aud")
        client_id = payload.get("client_id")

        if aud == expected_audience:
            return
        if client_id == expected_audience:
            return
        if isinstance(aud, list) and expected_audience in aud:
            return

        raise InvalidTokenError("Invalid token audience")

    def _get_signing_key(self, iss: str, kid: str) -> RSAPublicKey:
        """Resolve the RSA public key for ``(iss, kid)`` via the fail-fast T4 cache.

        The T4 cache owns fetching/caching and single-refetch rotation handling. Its
        failures map to this verifier's contract:

        - :class:`UnknownIssuerError` / :class:`UnknownKidError` -> 401
          (:class:`InvalidTokenError`): the token was not signed by any key the pool
          publishes.
        - :class:`JWKSFetchError` -> 503 (:class:`ServiceUnavailableError`): keys
          could not be obtained at all — the request is rejected, never trusted.

        Args:
            iss: The token issuer (already resolved to a registered pool).
            kid: The signing key id from the token header.

        Returns:
            The RSA public key for signature verification.
        """
        try:
            jwk_data = self._cache.get_signing_key(iss, kid)
        except UnknownIssuerError:
            # Defensive: iss was resolvable moments ago; treat as 401.
            raise InvalidTokenError("Invalid token issuer")
        except UnknownKidError:
            raise InvalidTokenError("Token signing key not found")
        except JWKSFetchError:
            # Genuine "cannot obtain keys" — reject with 503, never skip verification.
            logger.warning("JWKS unavailable for issuer '%s'; rejecting request", iss)
            raise ServiceUnavailableError("Authentication service unavailable")

        return self._build_public_key(jwk_data)

    def _build_public_key(self, jwk_data: dict) -> RSAPublicKey:
        """Convert a JWK dict to an RSA public key object for PyJWT verification."""
        from jwt import algorithms

        return algorithms.RSAAlgorithm.from_jwk(jwk_data)
