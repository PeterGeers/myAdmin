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
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt import algorithms

# Vendored, dependency-free decoder for the S4 entitlement claim (T14). It mirrors the
# decode half of backend/src/auth/entitlement_claim_codec.py WITHOUT importing
# backend/src, keeping this shared layer standalone (see entitlement_claim.py's
# docstring; a drift test asserts the vendored copy decodes identically to the source).
from sam.shared.entitlement_claim import (
    CLAIM_NAME as ENTITLEMENT_CLAIM_NAME,
    DecodedEntitlements,
    decode_entitlements,
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
# Errors
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Issuer -> pool registry (config-not-code, fail-fast — mirrors Flask plane T3)
# --------------------------------------------------------------------------- #

# The env var that declares which pools exist: a comma-separated list of pool keys.
# Each key K prefixes that pool's four required vars ({K}_COGNITO_ISSUER, etc.).
_POOL_KEYS_ENV_VAR = "COGNITO_POOL_KEYS"

_POOL_VAR_SUFFIXES = (
    "COGNITO_ISSUER",
    "COGNITO_JWKS_URI",
    "COGNITO_CLIENT_ID",
    "COGNITO_POOL_LABEL",
)


@dataclass(frozen=True)
class PoolConfig:
    """A single issuer->pool registry entry.

    Attributes:
        iss: The token issuer (the ``iss`` claim value) — the registry key.
        jwks_uri: JWKS endpoint used to fetch signing keys for this pool.
        audience: App-client id, matched against ``aud`` / ``client_id``.
        pool_label: Human-readable label for logs/diagnostics.
    """

    iss: str
    jwks_uri: str
    audience: str
    pool_label: str


def _require_pool_env(pool_key: str, suffix: str, environ: Mapping[str, str]) -> str:
    """Return a required per-pool env var, or raise if missing/blank (no defaults)."""
    name = f"{pool_key}_{suffix}"
    value = environ.get(name)
    if value is None or value.strip() == "":
        expected = ", ".join(f"{pool_key}_{s}" for s in _POOL_VAR_SUFFIXES)
        raise PoolRegistryError(
            f"Required env var '{name}' for pool '{pool_key}' is missing or blank. "
            f"Every pool declared in {_POOL_KEYS_ENV_VAR} must set all of: {expected}. "
            f"There is no default fallback (no-dangerous-fallbacks)."
        )
    return value.strip()


def _load_pool_entry(pool_key: str, environ: Mapping[str, str]) -> PoolConfig:
    """Build one :class:`PoolConfig` from a declared pool key's env vars."""
    return PoolConfig(
        iss=_require_pool_env(pool_key, "COGNITO_ISSUER", environ),
        jwks_uri=_require_pool_env(pool_key, "COGNITO_JWKS_URI", environ),
        audience=_require_pool_env(pool_key, "COGNITO_CLIENT_ID", environ),
        pool_label=_require_pool_env(pool_key, "COGNITO_POOL_LABEL", environ),
    )


def _parse_pool_keys(raw: Optional[str]) -> List[str]:
    """Split COGNITO_POOL_KEYS into a clean, ordered, de-duplicated list (fail-fast)."""
    if raw is None or raw.strip() == "":
        raise PoolRegistryError(
            f"'{_POOL_KEYS_ENV_VAR}' is missing or blank. Declare at least one pool "
            f"key; an empty registry is a misconfiguration, not a valid state "
            f"(no-dangerous-fallbacks)."
        )
    keys: List[str] = []
    for token in raw.split(","):
        key = token.strip()
        if key and key not in keys:
            keys.append(key)
    if not keys:
        raise PoolRegistryError(
            f"'{_POOL_KEYS_ENV_VAR}' contained no usable pool key (value: {raw!r})."
        )
    return keys


class PoolRegistry:
    """An immutable issuer->pool map with explicit unknown-issuer handling.

    :meth:`get` returns ``None`` for an unknown issuer; :meth:`require` raises
    :class:`UnknownIssuerError`. The verifier turns either into a 401. The registry
    never guesses a pool for an unrecognized ``iss``.
    """

    def __init__(self, entries: Iterable[PoolConfig]):
        by_iss: Dict[str, PoolConfig] = {}
        for entry in entries:
            if entry.iss in by_iss:
                raise PoolRegistryError(
                    f"Two pools declare the same issuer '{entry.iss}' "
                    f"({by_iss[entry.iss].pool_label} and {entry.pool_label}); "
                    f"issuers must be unique in the registry."
                )
            by_iss[entry.iss] = entry
        self._by_iss = by_iss

    def get(self, iss: str) -> Optional[PoolConfig]:
        """Return the pool for ``iss``, or ``None`` if the issuer is unknown."""
        return self._by_iss.get(iss)

    def require(self, iss: str) -> PoolConfig:
        """Return the pool for ``iss`` or raise :class:`UnknownIssuerError`."""
        pool = self._by_iss.get(iss)
        if pool is None:
            raise UnknownIssuerError(iss)
        return pool

    def issuers(self) -> List[str]:
        """Return the registered issuers (diagnostics only, not decisions)."""
        return list(self._by_iss.keys())

    def __len__(self) -> int:
        return len(self._by_iss)

    def __contains__(self, iss: object) -> bool:
        return iss in self._by_iss


def load_pool_registry(environ: Optional[Mapping[str, str]] = None) -> PoolRegistry:
    """Load the issuer->pool registry from the environment (fail-fast, no defaults).

    Reads ``COGNITO_POOL_KEYS`` for the declared pool keys, then loads each pool's
    four required vars into a :class:`PoolConfig`. Any missing/blank var — or a blank
    ``COGNITO_POOL_KEYS`` — raises :class:`PoolRegistryError`. The loader never
    returns a partial, empty, or defaulted registry.
    """
    env = os.environ if environ is None else environ
    pool_keys = _parse_pool_keys(env.get(_POOL_KEYS_ENV_VAR))
    entries = [_load_pool_entry(key, env) for key in pool_keys]
    return PoolRegistry(entries)


# --------------------------------------------------------------------------- #
# JWKS fetch + cache (Lambda global/execution-env scope — mirrors Flask plane T4)
# --------------------------------------------------------------------------- #

# Cognito rotates signing keys infrequently; an hour of caching keeps the hot path
# off the network while a `kid` miss still forces an immediate refetch regardless.
_DEFAULT_TTL_SECONDS = 3600
_DEFAULT_FETCH_TIMEOUT_SECONDS = 5

# A JWKS fetcher takes a jwks_uri and returns the parsed document ({"keys": [...]})
# or raises JWKSFetchError. Injectable so unit tests never hit the network.
JwksFetcher = Callable[[str], Mapping]


def _default_fetcher(jwks_uri: str) -> Mapping:
    """Fetch and parse a JWKS document over HTTPS (the production fetcher)."""
    try:
        response = requests.get(jwks_uri, timeout=_DEFAULT_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("JWKS fetch failed for %s: %s", jwks_uri, exc)
        raise JWKSFetchError(jwks_uri, str(exc)) from exc


@dataclass
class _IssuerEntry:
    """One issuer's cached key-set: ``kid -> JWK dict`` plus the fetch timestamp."""

    keys: Dict[str, dict] = field(default_factory=dict)
    fetched_at: float = 0.0

    def is_expired(self, ttl_seconds: int, now: float) -> bool:
        """True if never populated or older than the TTL."""
        if self.fetched_at == 0.0:
            return True
        return (now - self.fetched_at) > ttl_seconds


def _index_keys_by_kid(document: Mapping) -> Dict[str, dict]:
    """Build a ``kid -> JWK`` map from a JWKS document, skipping keyless entries."""
    keys = document.get("keys") if isinstance(document, Mapping) else None
    if not isinstance(keys, list):
        raise JWKSFetchError(
            "<jwks-document>", "response did not contain a 'keys' array"
        )
    indexed: Dict[str, dict] = {}
    for key in keys:
        if isinstance(key, Mapping):
            kid = key.get("kid")
            if kid:
                indexed[kid] = dict(key)
    return indexed


class JWKSCache:
    """Per-``iss`` JWKS cache with TTL and single-refetch rotation handling.

    Held in module/global scope on the module plane so **warm Lambda invocations
    reuse it** and never fetch JWKS per request (design.md "JWKS fetch + cache").
    Lookups return the raw JWK dict for a ``kid``; converting it to a public key is
    the verifier's concern, keeping this layer transport-only and easy to unit test.

    A lock serializes refetches so concurrent invocations don't stampede the JWKS
    endpoint.

    Args:
        registry: The issuer->pool registry. Resolves ``iss`` -> :class:`PoolConfig`.
        fetcher: Callable that fetches a JWKS document from a ``jwks_uri``. Defaults
            to an HTTPS fetch; unit tests inject a fake to avoid real network.
        ttl_seconds: Cache lifetime per issuer before a lookup forces a refetch.
    """

    def __init__(
        self,
        registry: PoolRegistry,
        fetcher: Optional[JwksFetcher] = None,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ):
        self._registry = registry
        self._fetcher = fetcher or _default_fetcher
        self._ttl_seconds = ttl_seconds
        self._entries: Dict[str, _IssuerEntry] = {}
        self._lock = threading.Lock()

    def get_signing_key(self, iss: str, kid: str) -> dict:
        """Return the JWK dict for ``(iss, kid)``, fetching/refreshing as needed.

        Resolution: resolve the pool (unknown issuer -> :class:`UnknownIssuerError`);
        ensure a fresh key-set (fetch if missing/stale); on a ``kid`` hit return it;
        on a miss refetch **exactly once** (rotation) then return if now present, else
        raise :class:`UnknownKidError`.
        """
        # Resolve the pool first — an unrecognized issuer is rejected with no network
        # call (never fetch a guessed endpoint).
        pool = self._registry.require(iss)

        with self._lock:
            entry = self._entries.get(iss)

            # Populate or refresh a stale entry before the first lookup.
            if entry is None or entry.is_expired(self._ttl_seconds, time.time()):
                entry = self._refetch(pool)

            # Warm hit — no network.
            jwk = entry.keys.get(kid)
            if jwk is not None:
                return jwk

            # Rotation: unknown kid within a fresh key-set -> exactly one refetch.
            logger.info(
                "kid '%s' not in cached JWKS for issuer '%s'; refetching once "
                "(possible key rotation)",
                kid,
                iss,
            )
            entry = self._refetch(pool)
            jwk = entry.keys.get(kid)
            if jwk is not None:
                return jwk

            logger.warning(
                "kid '%s' still absent for issuer '%s' after refetch; rejecting",
                kid,
                iss,
            )
            raise UnknownKidError(iss, kid)

    def _refetch(self, pool: PoolConfig) -> _IssuerEntry:
        """Fetch the pool's JWKS and replace the cached entry for its issuer."""
        document = self._fetcher(pool.jwks_uri)
        entry = _IssuerEntry(keys=_index_keys_by_kid(document), fetched_at=time.time())
        self._entries[pool.iss] = entry
        return entry


# --------------------------------------------------------------------------- #
# JWT verifier (RS256 + iss + aud/client_id + exp — mirrors Flask plane T5)
# --------------------------------------------------------------------------- #


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
        jwks_cache: Optional[JWKSCache] = None,
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

_GLOBAL_VERIFIER: Optional[JWTVerifier] = None
_GLOBAL_VERIFIER_LOCK = threading.Lock()


def get_global_verifier(
    registry: Optional[PoolRegistry] = None,
    fetcher: Optional[JwksFetcher] = None,
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


# --------------------------------------------------------------------------- #
# Handler-facing API: prefer the API Gateway Cognito authorizer
# --------------------------------------------------------------------------- #


def _claims_from_authorizer_context(event: Mapping[str, Any]) -> Optional[dict]:
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


def _bearer_token_from_event(event: Mapping[str, Any]) -> Optional[str]:
    """Extract the raw bearer token from the event's Authorization header.

    Handles the case-insensitive header name and both single-value (``headers``) and
    multi-value (``multiValueHeaders``) API Gateway shapes. Returns the token with the
    ``Bearer `` scheme stripped, or ``None`` if no bearer header is present.
    """
    if not isinstance(event, Mapping):
        return None

    def _find(headers: Mapping[str, Any]) -> Optional[str]:
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
    verifier: Optional[JWTVerifier] = None,
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


def get_groups(claims: Mapping[str, Any]) -> List[str]:
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

    sub: Optional[str]
    email: Optional[str]
    groups: List[str]
    claims: Mapping[str, Any]


def get_verified_identity(
    event: Mapping[str, Any],
    verifier: Optional[JWTVerifier] = None,
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
    verifier: Optional[JWTVerifier] = None,
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
) -> Optional[bool]:
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
