"""
Shared module-plane authentication layer (S2, module plane).

This package is the **self-contained** JWKS-based JWT verifier that the h-dcn SAM
stack (the ``members`` / ``events`` / ``webshop`` modules, one shared deployment)
vendors. It deliberately has **no dependency on myAdmin's ``backend/src``** — it
mirrors the Flask plane's verification *contract* (issuer->pool registry, JWKS
fetch + cache, RS256 verifier) in a Lambda-appropriate shape so h-dcn can import it
as a shared module/layer.

S2 scope on the module plane is **signature verification only**. Reading tenant from
the token (tenant-from-token binding) is **deferred to S5** — nothing in this package
reads or trusts a tenant claim.

Public API (see :mod:`sam.shared.auth_utils`):

- ``get_verified_claims(event, ...)`` — the preferred entry point. Uses the API
  Gateway Cognito authorizer's verified claims when present; otherwise verifies the
  raw ``Authorization: Bearer`` token itself via the JWKS verifier.
- ``get_groups(claims)`` — read ``cognito:groups`` (roles) from verified claims.
- ``JWTVerifier`` — the RS256 + iss + aud/client_id + exp verifier.
- ``load_pool_registry`` / ``PoolRegistry`` — the env-driven issuer->pool registry.
- Typed errors: ``InvalidTokenError`` (401), ``ServiceUnavailableError`` (503),
  ``UnknownIssuerError``, ``UnknownKidError``, ``PoolRegistryError``.
"""

from sam.shared.auth_utils import (
    InvalidTokenError,
    JWTVerifier,
    PoolConfig,
    PoolRegistry,
    PoolRegistryError,
    ServiceUnavailableError,
    UnknownIssuerError,
    UnknownKidError,
    get_groups,
    get_verified_claims,
    load_pool_registry,
)

__all__ = [
    "InvalidTokenError",
    "JWTVerifier",
    "PoolConfig",
    "PoolRegistry",
    "PoolRegistryError",
    "ServiceUnavailableError",
    "UnknownIssuerError",
    "UnknownKidError",
    "get_groups",
    "get_verified_claims",
    "load_pool_registry",
]
