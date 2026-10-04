"""
Module-plane JWT verification — error types (extracted from ``auth_utils`` for cohesion).

These are the exception types the shared verifier raises; they are re-exported from
:mod:`sam.shared.auth_utils` (its public import surface is unchanged). Keeping them in one
small module lets the registry / JWKS cache / verifier sub-modules import them without a
circular dependency back onto the facade.

Each rejection maps to a stable HTTP status (401 for "who are you / bad token", 503 for
"auth service can't answer"); the failure *reason* is logged server-side only (never the
token contents), per the S2 design "Failure behavior (R1.3)".
"""

from __future__ import annotations


class InvalidTokenError(Exception):
    """Raised when signature/issuer/audience/expiry verification fails (HTTP 401).

    Every rejection maps to a 401 with a generic message; the failure *reason* is
    logged server-side only (never the token contents), per design.md
    "Failure behavior (R1.3)".
    """

    def __init__(self, message: str = "Invalid token"):
        self.message = message
        self.http_status = 401
        super().__init__(self.message)


class ServiceUnavailableError(Exception):
    """Raised when a pool's JWKS cannot be obtained at all (HTTP 503).

    This *rejects* the request — it is never a way to skip verification (R1.3).
    """

    def __init__(self, message: str = "Authentication service unavailable"):
        self.message = message
        self.http_status = 503
        super().__init__(self.message)


class PoolRegistryError(RuntimeError):
    """Raised when the issuer->pool registry is misconfigured (hard config error).

    Fail loudly rather than fall back to an empty/partial registry
    (no-dangerous-fallbacks).
    """


class UnknownIssuerError(PoolRegistryError):
    """Raised when a token's ``iss`` has no registered pool (mapped to 401)."""

    def __init__(self, iss: str):
        self.iss = iss
        super().__init__(
            f"No pool is registered for issuer '{iss}'. The token's issuer is not in "
            f"the configured issuer->pool registry; reject it."
        )


class JWKSFetchError(RuntimeError):
    """Raised when JWKS cannot be fetched/parsed from a pool's ``jwks_uri`` (503)."""

    def __init__(self, jwks_uri: str, reason: str):
        self.jwks_uri = jwks_uri
        self.reason = reason
        super().__init__(f"Failed to fetch JWKS from '{jwks_uri}': {reason}")


class UnknownKidError(RuntimeError):
    """Raised when a ``kid`` is absent even after one rotation refetch (mapped 401)."""

    def __init__(self, iss: str, kid: str):
        self.iss = iss
        self.kid = kid
        super().__init__(
            f"Signing key id '{kid}' is not published by issuer '{iss}' even after a "
            f"single refetch; reject the token."
        )


__all__ = [
    "InvalidTokenError",
    "ServiceUnavailableError",
    "PoolRegistryError",
    "UnknownIssuerError",
    "JWKSFetchError",
    "UnknownKidError",
]
