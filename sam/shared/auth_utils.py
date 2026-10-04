"""
Module-plane JWT verification (S2 / T8) — self-contained, Lambda-flavored.

This is the shared authentication utility for the h-dcn SAM stack (the ``members`` /
``events`` / ``webshop`` modules, one shared deployment). It **replaces the historical
base64-only decode** in the module plane's ``auth_utils.py`` with **full JWKS-based
RS256 signature verification**, mirroring the myAdmin Flask plane's verification
contract (``backend/src/auth/`` T3/T4/T5) — but **without importing** anything from
``backend/src``. h-dcn vendors this module (or ships it as a Lambda layer) so all
three modules share one verifier.

Design contract (see ``.kiro/specs/multi-tenant/s2-jwt-verification/design.md``,
"Verification contract" + "Module plane" + "JWKS fetch + cache"):

1. Decode the header for ``kid`` + ``alg`` (**RS256 only**).
2. Read the **unverified** ``iss`` *only* to select the pool via an env-driven
   issuer->pool registry (fail-fast, config-not-code — mirrors T3). Unknown issuer
   -> **401**.
3. Fetch that pool's **JWKS** through a cache held in **module/global scope** so warm
   Lambda invocations reuse it; a ``kid`` cache-miss triggers exactly **one** refetch
   (rotation — mirrors T4). Never fetch per request on the hot path.
4. Verify **RS256 signature** + ``iss`` + audience/``client_id`` + ``exp`` (30s
   leeway). Any failure -> **401, no fallback, no partial trust** (R1.3).
5. Only then read claims (``sub``, ``email``, ``cognito:groups`` for roles). Never
   from headers.

**No base64-only trust path (R1.3).** There is no code path that accepts a token
without a successful RS256 verification. The old "decode the payload and trust it"
behavior is gone.

**Prefer the API Gateway Cognito authorizer (design.md, "Module plane").**
:func:`get_verified_claims` first reads claims from the API Gateway authorizer's
**verified** request context (``event.requestContext.authorizer.claims`` /
``authorizer.jwt.claims``). Only if that context is absent does it verify the raw
``Authorization: Bearer`` token itself with :class:`JWTVerifier`. Either way the
handler reads claims **only from verified material**.

**Tenant-from-token is deferred to S5 (R2.4).** This module reads roles
(``cognito:groups``) but deliberately does **not** read or trust any tenant claim.

**No unverified-header trust.** ``X-Enhanced-Groups`` / ``X-Tenant`` and similar
client-supplied headers are never consulted here (T9 finalizes header removal; this
module simply never introduces header trust).

Dependencies (Lambda-appropriate, same as the Flask plane): ``PyJWT``,
``cryptography``, ``requests``. Only public, non-secret Cognito identifiers are used;
nothing here is a credential.

Internal layout (code-quality split M2 — a pure structural refactor, no behaviour
change). This module is the **stable facade**: its full public import surface is
preserved and re-exported here, so every ``from sam.shared.auth_utils import ...`` is
unchanged. The verification machinery lives in cohesive sub-modules:

- :mod:`sam.shared._auth_errors` — the exception types.
- :mod:`sam.shared._pool_registry` — the issuer->pool registry (:class:`PoolConfig`,
  :class:`PoolRegistry`, :func:`load_pool_registry`).
- :mod:`sam.shared._jwks` — the JWKS fetch + cache (:class:`JWKSCache`, ``JwksFetcher``).
- :mod:`sam.shared._verifier` — the RS256 :class:`JWTVerifier` + the global verifier.

The handler-facing claims API (``get_verified_claims`` / ``get_groups`` /
``get_verified_identity``) and the S4 entitlement reader (``has_capability`` and
friends) stay **defined here** — they are the module's primary surface and a guard test
pins ``has_capability.__module__ == "sam.shared.auth_utils"``.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Vendored, dependency-free decoder for the S4 entitlement claim (T14). It mirrors the
# decode half of backend/src/auth/entitlement_claim_codec.py WITHOUT importing
# backend/src, keeping this shared layer standalone (see entitlement_claim.py's
# docstring; a drift test asserts the vendored copy decodes identically to the source).
from sam.shared.entitlement_claim import (
    CLAIM_NAME as ENTITLEMENT_CLAIM_NAME,
)
from sam.shared.entitlement_claim import (
    DecodedEntitlements,
    decode_entitlements,
)

# ── Extracted verification machinery (re-exported — stable import surface) ─────────────
from sam.shared._auth_errors import (
    InvalidTokenError,
    JWKSFetchError,
    PoolRegistryError,
    ServiceUnavailableError,
    UnknownIssuerError,
    UnknownKidError,
)
from sam.shared._pool_registry import (
    PoolConfig,
    PoolRegistry,
    load_pool_registry,
)
from sam.shared._jwks import (
    JWKSCache,
    JwksFetcher,
)
from sam.shared._verifier import (
    JWTVerifier,
    get_global_verifier,
    reset_global_verifier,
)

logger = logging.getLogger(__name__)

__all__ = [
    # Errors
    "InvalidTokenError",
    "ServiceUnavailableError",
    "PoolRegistryError",
    "UnknownIssuerError",
    "UnknownKidError",
    "JWKSFetchError",
    # Registry
    "PoolConfig",
    "PoolRegistry",
    "load_pool_registry",
    # Cache + verifier
    "JWKSCache",
    "JWTVerifier",
    "get_global_verifier",
    "reset_global_verifier",
    # Handler-facing API
    "get_verified_claims",
    "get_groups",
    "get_verified_identity",
    "VerifiedIdentity",
    # Entitlement reader (S4 / T14) — per-tenant capability from the VERIFIED token
    "DecodedEntitlements",
    "ENTITLEMENT_CLAIM_NAME",
    "get_entitlements",
    "get_entitlements_from_claims",
    "has_capability",
]


# --------------------------------------------------------------------------- #
# Handler-facing API: prefer the API Gateway Cognito authorizer
# --------------------------------------------------------------------------- #


def _claims_from_authorizer_context(event: Mapping[str, Any]) -> dict | None:
    """Return API Gateway Cognito-authorizer verified claims, or ``None`` if absent.

    Supports both API Gateway integrations:

    - **REST API / HTTP API v1 Cognito authorizer:**
      ``event.requestContext.authorizer.claims``
    - **HTTP API v2 JWT authorizer:**
      ``event.requestContext.authorizer.jwt.claims``

    These claims were verified by API Gateway against the Cognito pool before the
    handler ran, so they are trusted **without re-verification** (design.md "prefer
    verification at the API Gateway Cognito authorizer"). We do not fall back to any
    unverified source.
    """
    if not isinstance(event, Mapping):
        return None
    request_context = event.get("requestContext")
    if not isinstance(request_context, Mapping):
        return None
    authorizer = request_context.get("authorizer")
    if not isinstance(authorizer, Mapping):
        return None

    # HTTP API v2 JWT authorizer: authorizer.jwt.claims
    jwt_block = authorizer.get("jwt")
    if isinstance(jwt_block, Mapping):
        claims = jwt_block.get("claims")
        if isinstance(claims, Mapping) and claims:
            return dict(claims)

    # REST / HTTP API v1 Cognito authorizer: authorizer.claims
    claims = authorizer.get("claims")
    if isinstance(claims, Mapping) and claims:
        return dict(claims)

    return None


def _bearer_token_from_event(event: Mapping[str, Any]) -> str | None:
    """Extract the raw bearer token from the event's Authorization header.

    Handles the case-insensitive header name and both single-value (``headers``) and
    multi-value (``multiValueHeaders``) API Gateway shapes. Returns the token with the
    ``Bearer `` scheme stripped, or ``None`` if no bearer header is present.
    """
    if not isinstance(event, Mapping):
        return None

    def _find(headers: Mapping[str, Any]) -> str | None:
        for name, value in headers.items():
            if isinstance(name, str) and name.lower() == "authorization":
                if isinstance(value, list):
                    value = value[0] if value else None
                if isinstance(value, str):
                    return value
        return None

    raw = None
    headers = event.get("headers")
    if isinstance(headers, Mapping):
        raw = _find(headers)
    if raw is None:
        multi = event.get("multiValueHeaders")
        if isinstance(multi, Mapping):
            raw = _find(multi)

    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if stripped.lower().startswith("bearer "):
        return stripped[7:].strip()
    return stripped or None


def get_verified_claims(
    event: Mapping[str, Any],
    verifier: JWTVerifier | None = None,
) -> dict:
    """Return verified JWT claims for a Lambda handler — API-GW-authorizer preferred.

    Resolution order (design.md "Module plane"):

    1. **Preferred:** if the request passed through an API Gateway **Cognito
       authorizer**, its already-verified claims are read from the request context
       (``requestContext.authorizer.claims`` or ``authorizer.jwt.claims``) and
       returned **without re-verification**.
    2. **Fallback (still verified):** otherwise the raw ``Authorization: Bearer``
       token is verified here via :class:`JWTVerifier` (full RS256 + iss + aud +
       exp). There is **no base64-only path** — an in-handler decode always verifies.

    A missing/failed token raises :class:`InvalidTokenError` (401). This never trusts
    ``X-Enhanced-Groups`` / ``X-Tenant`` or any other client-supplied header, and it
    never reads a tenant claim (tenant-from-token is deferred to S5).

    Args:
        event: The Lambda event (API Gateway proxy integration shape).
        verifier: Optional verifier for the fallback path (tests inject one). Defaults
            to the execution-environment-wide :func:`get_global_verifier`.

    Returns:
        The verified claims dict (contains ``sub``, ``cognito:groups``, etc.).

    Raises:
        InvalidTokenError: No token present, or the token failed verification (401).
        ServiceUnavailableError: JWKS could not be obtained on the fallback path (503).
    """
    # (1) Prefer the API Gateway Cognito authorizer's verified claims.
    claims = _claims_from_authorizer_context(event)
    if claims is not None:
        return claims

    # (2) Fallback: verify the raw bearer token ourselves (never base64-only).
    token = _bearer_token_from_event(event)
    if not token:
        raise InvalidTokenError("Missing bearer token")

    active_verifier = verifier or get_global_verifier()
    return active_verifier.verify_token(token)


def get_groups(claims: Mapping[str, Any]) -> list[str]:
    """Return the roles from a verified token's ``cognito:groups`` claim (R2.2).

    Groups come **only** from the verified token — never from ``X-Enhanced-Groups`` or
    any client-supplied header. Cognito may serialize ``cognito:groups`` as a JSON
    list (raw token) or, via an API Gateway authorizer, as a bracketed string; both
    are normalized to a list of group names.

    Args:
        claims: Verified claims (from :func:`get_verified_claims`).

    Returns:
        A list of group names (empty if the token carries no groups).
    """
    raw = claims.get("cognito:groups")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(g) for g in raw]
    if isinstance(raw, str):
        # API Gateway can surface list claims as a string like "[admin manager]".
        inner = raw.strip().strip("[]").strip()
        if not inner:
            return []
        # Cognito uses space- or comma-separated group lists in the string form.
        separators = "," if "," in inner else None
        parts = inner.split(separators) if separators else inner.split()
        return [p.strip() for p in parts if p.strip()]
    return []


# --------------------------------------------------------------------------- #
# Single correct entry point: verified identity (T9 — no header trust)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VerifiedIdentity:
    """A module-plane caller's identity and roles, sourced **only** from a verified token.

    Every field is derived from the API-Gateway-verified authorizer context or a full
    RS256 verification performed here — **never** from a client-supplied header
    (``X-Enhanced-Groups`` / ``X-Tenant`` and the like are ignored, T9 / R2.1).

    Deliberately carries **no tenant** field: tenant-from-token is deferred to S5
    (R2.4), so this module never reads or exposes a tenant claim.

    Attributes:
        sub: The Cognito subject (stable user id) from the verified token.
        email: The verified ``email`` claim if present, else ``None``.
        groups: Roles from the verified ``cognito:groups`` (R2.2); empty if none.
        claims: The full verified claims dict (for callers that need more).
    """

    sub: str | None
    email: str | None
    groups: list[str]
    claims: Mapping[str, Any]


def get_verified_identity(
    event: Mapping[str, Any],
    verifier: JWTVerifier | None = None,
) -> VerifiedIdentity:
    """Return the caller's identity + roles from the verified token — the one correct entry point.

    This is the single, header-free way a module-plane handler should learn *who* is
    calling and *what roles* they hold. It composes
    :func:`get_verified_claims` (API-GW-authorizer preferred, else full RS256
    verification) with :func:`get_groups`, so there is **no path** by which
    ``X-Enhanced-Groups`` / ``X-Tenant`` or any other client-supplied header can
    influence identity or roles (T9 / R2.1, R2.2).

    Prefer this over reading ``event["headers"]`` in a handler: it removes the
    temptation to trust a header and keeps every handler on the verified-token path.

    Tenant is intentionally **not** returned (deferred to S5, R2.4).

    Args:
        event: The Lambda event (API Gateway proxy integration shape).
        verifier: Optional verifier for the fallback path (tests inject one).

    Returns:
        A :class:`VerifiedIdentity` with ``sub`` / ``email`` / ``groups`` / ``claims``
        all sourced from the verified token only.

    Raises:
        InvalidTokenError: No token present, or the token failed verification (401).
        ServiceUnavailableError: JWKS could not be obtained on the fallback path (503).
    """
    claims = get_verified_claims(event, verifier=verifier)
    sub = claims.get("sub")
    email = claims.get("email")
    return VerifiedIdentity(
        sub=str(sub) if sub is not None else None,
        email=str(email) if email is not None else None,
        groups=get_groups(claims),
        claims=claims,
    )


# --------------------------------------------------------------------------- #
# Entitlement reader (S4 / T14) — per-tenant capability from the VERIFIED token
# --------------------------------------------------------------------------- #
#
# S4 stamps each user's resolved per-tenant entitlement into the Pool A token at
# issuance (the PreTokenGen Lambda, sam/pretokengen). The module plane authorizes the
# PER-USER answer from that VERIFIED token claim alone — NO request-time MySQL and NO
# S3 DynamoDB read for the per-user question (R5.2). (S3/DynamoDB is the TENANT-level
# path; do not conflate the two.)
#
# Verified-only (R5.1): entitlement is read ONLY from claims that came out of
# get_verified_claims / get_verified_identity — i.e. the API-Gateway-verified
# authorizer context or a full in-handler RS256 verification. There is deliberately NO
# code path that reads custom:entitlements from a raw/unverified header; the reader's
# input is always the verified claims dict.
#
# Decode via the vendored codec (entitlement_claim.py). The decoder is TOTAL: an
# unknown/missing version or a malformed value yields fallback_required=True, and an
# over-budget token yields is_overflow=True. In BOTH cases the token does NOT answer
# the per-user question and the reader surfaces that state (capabilities_for -> None)
# rather than silently allowing or denying — see has_capability's caller contract.


def get_entitlements_from_claims(
    claims: Mapping[str, Any],
) -> DecodedEntitlements:
    """Decode the ``custom:entitlements`` claim from an already-verified claims dict.

    Reads the claim ONLY from ``claims`` — which callers must obtain from
    :func:`get_verified_claims` / :func:`get_verified_identity` (the
    API-Gateway-verified authorizer context or a full RS256 verification). It never
    consults a header (R5.1). Decoding is delegated to the vendored, total decoder, so
    an absent claim, an unknown version, a malformed value, or an overflow signal all
    return a well-defined :class:`DecodedEntitlements` rather than raising.

    Args:
        claims: Verified claims (from :func:`get_verified_claims`).

    Returns:
        A :class:`DecodedEntitlements`. When the claim is **absent**, the result is the
        safe fallback (``fallback_required=True``, empty map) — identical to an
        unknown-version claim: the token does not answer the per-user question, so the
        caller must consult its own source of truth (the S3 projection / server) or
        deny per the module's policy. Never a silent allow.
    """
    raw = claims.get(ENTITLEMENT_CLAIM_NAME)
    if raw is None:
        # No claim at all is treated exactly like an unrecognised claim: the token
        # does not carry the per-user answer -> fallback_required (never a silent map).
        return decode_entitlements(None)
    return decode_entitlements(raw)


def get_entitlements(
    event: Mapping[str, Any],
    verifier: JWTVerifier | None = None,
) -> DecodedEntitlements:
    """Return the decoded entitlement from the request's VERIFIED token (R5.1, R5.2).

    Convenience wrapper that first resolves the verified claims for the request
    (:func:`get_verified_claims` — API-GW-authorizer preferred, else full RS256
    verification) and then decodes ``custom:entitlements`` from them via
    :func:`get_entitlements_from_claims`. The claim is therefore read **only** from
    verified material; a client-supplied header carrying an entitlement is never
    consulted (R5.1).

    This does **no** MySQL query and **no** S3 read for the per-user answer — the token
    is the per-user path (R5.2). If the token does not answer the question (absent /
    unknown-version / malformed claim, or an overflow signal), the returned
    :class:`DecodedEntitlements` says so (``fallback_required`` / ``is_overflow``); the
    caller then decides to consult the S3 projection / server or deny.

    Args:
        event: The Lambda event (API Gateway proxy integration shape).
        verifier: Optional verifier for the in-handler fallback path (tests inject one).

    Returns:
        A :class:`DecodedEntitlements` decoded from the verified token.

    Raises:
        InvalidTokenError: No token present, or the token failed verification (401).
        ServiceUnavailableError: JWKS could not be obtained on the fallback path (503).
    """
    claims = get_verified_claims(event, verifier=verifier)
    return get_entitlements_from_claims(claims)


def has_capability(
    claims: Mapping[str, Any],
    tenant: str,
    capability: str,
) -> bool | None:
    """Answer "does this verified user hold ``capability`` for ``tenant``?" from the token.

    Reads the per-user answer from the VERIFIED token's ``custom:entitlements`` claim
    only (R5.1) — no MySQL, no S3 read (R5.2). The return is deliberately **three-state**
    so an "the token can't answer this" case is never mistaken for a decision:

    - ``True``  — the token authoritatively grants ``capability`` for ``tenant``.
    - ``False`` — the token authoritatively denies it: the claim is present and usable,
      lists ``tenant``, and ``capability`` is not among that tenant's capabilities.
    - ``None``  — **the token does not answer this**; the caller must CONSULT its
      fallback (the S3 DynamoDB projection / a server endpoint) or deny per the
      module's policy. ``None`` arises when the claim is absent, an unknown version, or
      malformed (``fallback_required``), when it is an **overflow** signal
      (``is_overflow`` — the user's entitlement exceeded the token budget), or when the
      usable claim simply does not list ``tenant`` (the token carries no per-user answer
      for that tenant). It is NEVER a silent allow or deny.

    Caller contract (document at the call site): treat ``None`` as "consult server / S3
    or deny" — never as ``True`` and never as a blanket ``False``. A ``False`` from this
    function is an authoritative token-backed denial; a ``None`` is an absence of an
    answer that the caller must resolve elsewhere.

    Args:
        claims: Verified claims (from :func:`get_verified_claims` /
            :func:`get_verified_identity`). The claim is read only from here (R5.1).
        tenant: The administration / tenant key to check.
        capability: The capability token (e.g. ``"finance_read"``).

    Returns:
        ``True`` / ``False`` for an authoritative token-backed decision, or ``None``
        when the token does not answer (consult S3 / server or deny).
    """
    decoded = get_entitlements_from_claims(claims)
    caps = decoded.capabilities_for(tenant)
    if caps is None:
        # fallback_required, overflow, or tenant not listed -> token doesn't answer.
        return None
    return capability in caps
