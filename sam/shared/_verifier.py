"""
Module-plane JWT verification — the RS256 verifier + global instance (from ``auth_utils``).

RS256 + iss + aud/client_id + exp — mirrors the Flask plane T5. Re-exported from
:mod:`sam.shared.auth_utils`; the public import surface is unchanged.

The module plane is Lambda: hold ONE verifier (and its JWKS cache) in module/global scope
(see :func:`get_global_verifier`) so warm invocations reuse cached keys and never re-read
the registry or refetch JWKS on the hot path.
"""

from __future__ import annotations

import logging
import threading

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt import algorithms

from sam.shared._auth_errors import (
    InvalidTokenError,
    JWKSFetchError,
    ServiceUnavailableError,
    UnknownIssuerError,
    UnknownKidError,
)
from sam.shared._jwks import _DEFAULT_TTL_SECONDS, JWKSCache, JwksFetcher
from sam.shared._pool_registry import PoolRegistry, load_pool_registry

logger = logging.getLogger(__name__)


class JWTVerifier:
    """Multi-pool RS256 JWT verification via the issuer->pool registry.

    Resolves the issuing pool from the token's ``iss`` claim, then verifies the RS256
    signature and standard claims against **that** pool's JWKS (obtained through the
    :class:`JWKSCache`). Adding a pool is configuration (a registry entry), never a
    code change.

    Args:
        registry: The issuer->pool registry.
        jwks_cache: Optional shared :class:`JWKSCache`. If omitted, the verifier
            builds its own instance bound to ``registry``.
        cache_ttl: JWKS cache TTL in seconds (used only if a cache is created here).
    """

    CLOCK_SKEW_SECONDS = 30
    ALGORITHM = "RS256"

    def __init__(
        self,
        registry: PoolRegistry,
        jwks_cache: JWKSCache | None = None,
        cache_ttl: int = _DEFAULT_TTL_SECONDS,
    ):
        self._registry = registry
        self._cache = jwks_cache or JWKSCache(registry=registry, ttl_seconds=cache_ttl)

    def verify_token(self, token: str) -> dict:
        """Verify a JWT's signature and claims against its issuing pool.

        Resolves the pool from the token's (unverified) ``iss``, fetches that pool's
        JWKS through the cache, and verifies RS256 signature + ``iss`` +
        audience/``client_id`` + ``exp`` (30s leeway). Any failure -> 401, with no
        fallback that would accept an unverified token (R1.3).

        Args:
            token: Raw JWT string (without the ``Bearer `` prefix).

        Returns:
            The decoded, verified JWT payload as a dict.

        Raises:
            InvalidTokenError: Malformed token, wrong algorithm, unknown issuer,
                unknown signing key, bad signature, wrong issuer/audience, or expiry
                (HTTP 401).
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

        # (2) Read the UNVERIFIED iss ONLY to select the pool. No claim is trusted
        # here — signature verification below is what establishes trust.
        try:
            unverified_claims = jwt.decode(token, options={"verify_signature": False})
        except jwt.exceptions.DecodeError:
            raise InvalidTokenError("Invalid token format")

        iss = unverified_claims.get("iss")
        if not iss:
            raise InvalidTokenError("Token missing issuer (iss)")

        try:
            pool = self._registry.require(iss)
        except UnknownIssuerError:
            logger.warning("Rejecting token from unregistered issuer '%s'", iss)
            raise InvalidTokenError("Invalid token issuer")

        # (3) Resolve the signing key for (iss, kid) via the fail-fast cache.
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
            raise InvalidTokenError("Token has expired")
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
        """Resolve the RSA public key for ``(iss, kid)`` via the fail-fast cache.

        Cache failures map to this verifier's contract: unknown issuer/kid -> 401;
        a genuine inability to fetch keys -> 503 (rejects, never skips verification).
        """
        try:
            jwk_data = self._cache.get_signing_key(iss, kid)
        except UnknownIssuerError:
            raise InvalidTokenError("Invalid token issuer")
        except UnknownKidError:
            raise InvalidTokenError("Token signing key not found")
        except JWKSFetchError:
            logger.warning("JWKS unavailable for issuer '%s'; rejecting request", iss)
            raise ServiceUnavailableError("Authentication service unavailable")

        return algorithms.RSAAlgorithm.from_jwk(jwk_data)


# --------------------------------------------------------------------------- #
# Global (execution-environment) verifier — warm Lambda reuse
# --------------------------------------------------------------------------- #
#
# The module plane is Lambda: hold ONE verifier (and its JWKS cache) in module/global
# scope so warm invocations reuse cached keys and never re-read the registry or
# refetch JWKS on the hot path.

_GLOBAL_VERIFIER: JWTVerifier | None = None
_GLOBAL_VERIFIER_LOCK = threading.Lock()


def get_global_verifier(
    registry: PoolRegistry | None = None,
    fetcher: JwksFetcher | None = None,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> JWTVerifier:
    """Return the execution-environment-wide :class:`JWTVerifier`, building it once.

    On first call it loads the issuer->pool registry from the environment (fail-fast)
    unless a ``registry`` is injected, and builds a verifier whose JWKS cache lives in
    global scope. Subsequent (warm) calls reuse the same instance and **ignore** later
    arguments (use :func:`reset_global_verifier` to rebuild, e.g. between tests).

    Args:
        registry: Optional pre-built registry (tests inject one). Defaults to
            :func:`load_pool_registry` reading the environment.
        fetcher: Optional JWKS fetcher (tests inject a fake; defaults to HTTPS).
        ttl_seconds: JWKS cache TTL used only when the verifier is created now.

    Returns:
        The shared :class:`JWTVerifier` instance.
    """
    global _GLOBAL_VERIFIER
    if _GLOBAL_VERIFIER is None:
        with _GLOBAL_VERIFIER_LOCK:
            if _GLOBAL_VERIFIER is None:
                resolved_registry = registry or load_pool_registry()
                cache = JWKSCache(
                    registry=resolved_registry,
                    fetcher=fetcher,
                    ttl_seconds=ttl_seconds,
                )
                _GLOBAL_VERIFIER = JWTVerifier(
                    registry=resolved_registry, jwks_cache=cache
                )
    return _GLOBAL_VERIFIER


def reset_global_verifier() -> None:
    """Drop the global verifier (test isolation / forced rebuild)."""
    global _GLOBAL_VERIFIER
    with _GLOBAL_VERIFIER_LOCK:
        _GLOBAL_VERIFIER = None


__all__ = [
    "JWTVerifier",
    "get_global_verifier",
    "reset_global_verifier",
]
