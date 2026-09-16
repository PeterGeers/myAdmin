"""
JWKS fetch + cache with rotation handling (S2 / T4, R3.3).

The verifier (T5) must validate RS256 signatures against *several* Cognito pools —
the standing **test pool** now, production **Pool A** in Phase 6, Pool B later —
without fetching JWKS per request and while handling key **rotation** correctly.
This module is the shared JWKS layer that sits between the issuer->pool registry
(T3, :mod:`auth.pool_registry`) and the verifier (T5): given a token's ``iss`` and
``kid`` it returns the matching signing key, fetching + caching JWKS as needed.

Design contract (see ``.kiro/specs/multi-tenant/s2-jwt-verification/design.md``,
"JWKS fetch + cache (R3.3)"):

- **Cache keyed by ``iss``.** Each issuer's JWKS is cached independently, so a
  multi-pool process keeps one key-set per pool.
- **Flask plane = module-level cache + TTL.** A single process-wide
  :class:`JWKSCache` instance (``_MODULE_CACHE``) is reused across requests so warm
  lookups never touch the network. The module plane (Lambda) will mirror this design
  in execution-environment/global scope.
- **Refresh on TTL expiry OR on a ``kid`` cache-miss.** A stale (past-TTL) entry is
  refetched before lookup. Within a fresh entry, an unknown ``kid`` triggers
  **exactly one** refetch (key rotation: the pool published a new key).
- **Rotation = single refetch, then explicit failure.** If the ``kid`` is still
  unknown after that one refetch, raise :class:`UnknownKidError` — the verifier (T5)
  turns it into a **401**. Never fetch repeatedly on the hot path, never "trust
  anyway" (no-dangerous-fallbacks, R1.3).
- **Unknown issuer is explicit.** An ``iss`` not in the registry raises
  :class:`UnknownIssuerError` (from T3) — never fetch a guessed endpoint.

Error handling logs the *reason* server-side only (issuer, kid, endpoint) and never
token contents. Fetch/transport failures surface as :class:`JWKSFetchError`.

This module owns network I/O for JWKS; unit tests inject a fake fetcher (no real
network). Non-secret Cognito identifiers only — nothing here is a credential.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Mapping, Optional

import requests

from auth.pool_registry import (
    PoolRegistry,
    UnknownIssuerError,  # re-exported for callers (verifier T5)
)
from auth.test_pool_config import PoolConfig

logger = logging.getLogger(__name__)

__all__ = [
    "JWKSCacheError",
    "JWKSFetchError",
    "UnknownKidError",
    "UnknownIssuerError",
    "JWKSCache",
    "get_signing_key",
    "get_module_cache",
    "reset_module_cache",
]

# Default cache lifetime. Cognito rotates signing keys infrequently, so an hour of
# caching keeps the hot path off the network while still picking up rotation within a
# bounded window (and a `kid` miss forces an immediate refetch regardless of TTL).
_DEFAULT_TTL_SECONDS = 3600

# HTTP timeout for a JWKS fetch. Kept short so a slow/unreachable endpoint fails fast
# rather than stalling the request path.
_DEFAULT_FETCH_TIMEOUT_SECONDS = 5

# A JWKS fetcher takes a jwks_uri and returns the parsed JWKS document
# ({"keys": [...]}) or raises JWKSFetchError. Injectable so unit tests never hit the
# network.
JwksFetcher = Callable[[str], Mapping]


class JWKSCacheError(RuntimeError):
    """Base class for JWKS cache failures (mapped to 401/5xx by the verifier)."""


class JWKSFetchError(JWKSCacheError):
    """Raised when JWKS cannot be fetched/parsed from a pool's ``jwks_uri``.

    Transport errors, non-2xx responses, and malformed JSON all surface here. The
    verifier (T5) treats an inability to obtain keys as an auth failure — there is no
    "trust anyway" fallback (R1.3).
    """

    def __init__(self, jwks_uri: str, reason: str):
        self.jwks_uri = jwks_uri
        self.reason = reason
        super().__init__(f"Failed to fetch JWKS from '{jwks_uri}': {reason}")


class UnknownKidError(JWKSCacheError):
    """Raised when a ``kid`` is not present even after a single rotation refetch.

    This is the terminal rotation outcome: the cache was refreshed once from the
    pool's live ``jwks_uri`` and the key id is still absent, so the token was not
    signed by any key the pool currently publishes. The verifier (T5) maps this to a
    **401** (R3.3).
    """

    def __init__(self, iss: str, kid: str):
        self.iss = iss
        self.kid = kid
        super().__init__(
            f"Signing key id '{kid}' is not published by issuer '{iss}' even after a "
            f"single refetch; reject the token."
        )


def _default_fetcher(jwks_uri: str) -> Mapping:
    """Fetch and parse a JWKS document over HTTPS (the production fetcher).

    Args:
        jwks_uri: The pool's JWKS endpoint (from its :class:`PoolConfig`).

    Returns:
        The parsed JWKS document (expected shape ``{"keys": [...]}``).

    Raises:
        JWKSFetchError: The endpoint is unreachable, returns non-2xx, or the body is
            not valid JSON.
    """
    try:
        response = requests.get(jwks_uri, timeout=_DEFAULT_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        # Log the endpoint + reason server-side; never log token contents.
        logger.warning("JWKS fetch failed for %s: %s", jwks_uri, exc)
        raise JWKSFetchError(jwks_uri, str(exc)) from exc


@dataclass
class _IssuerEntry:
    """One issuer's cached key-set: ``kid -> JWK dict`` plus the fetch timestamp."""

    keys: Dict[str, dict] = field(default_factory=dict)
    fetched_at: float = 0.0

    def is_expired(self, ttl_seconds: int, now: float) -> bool:
        """True if this entry has never been populated or is older than the TTL."""
        if self.fetched_at == 0.0:
            return True
        return (now - self.fetched_at) > ttl_seconds


class JWKSCache:
    """Per-``iss`` JWKS cache with TTL and single-refetch rotation handling.

    Resolves each issuer to a :class:`PoolConfig` via the injected
    :class:`~auth.pool_registry.PoolRegistry`, fetches that pool's JWKS from its
    ``jwks_uri``, and caches the key-set keyed by ``iss``. Lookups return the raw JWK
    dict for a ``kid``; converting it to a public key is the verifier's concern (T5),
    keeping this layer transport-only and easy to unit test.

    The instance is safe to share process-wide (the Flask plane keeps one module-level
    instance): a lock serializes refetches so concurrent requests don't stampede the
    JWKS endpoint.

    Args:
        registry: The issuer->pool registry (T3). Resolves ``iss`` -> ``PoolConfig``.
        fetcher: Callable that fetches a JWKS document from a ``jwks_uri``. Defaults to
            an HTTPS fetch; unit tests inject a fake to avoid real network.
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

        Resolution order:

        1. Resolve the pool for ``iss`` (unknown issuer -> :class:`UnknownIssuerError`).
        2. Ensure a fresh key-set: fetch if the entry is missing or past its TTL.
        3. Hit: return the JWK for ``kid`` from the cached key-set (no network).
        4. Miss: refetch **exactly once** (rotation), then return the ``kid`` if now
           present, else raise :class:`UnknownKidError`.

        Args:
            iss: The token's issuer claim (registry key).
            kid: The signing key id from the token header.

        Returns:
            The JWK dict for the requested ``kid`` (as published by the pool).

        Raises:
            UnknownIssuerError: ``iss`` has no registered pool.
            UnknownKidError: ``kid`` is absent even after one rotation refetch.
            JWKSFetchError: JWKS could not be fetched when a fetch was required.
        """
        # (1) Resolve the pool first — an unrecognized issuer is rejected without any
        # network call (never fetch a guessed endpoint).
        pool = self._registry.require(iss)

        with self._lock:
            entry = self._entries.get(iss)

            # (2) Populate or refresh a stale entry before the first lookup.
            if entry is None or entry.is_expired(self._ttl_seconds, time.time()):
                entry = self._refetch(pool)

            # (3) Warm hit — no network.
            jwk = entry.keys.get(kid)
            if jwk is not None:
                return jwk

            # (4) Rotation: unknown kid within a fresh key-set -> exactly one refetch.
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

            # Still unknown after the single refetch -> explicit failure (401 at T5).
            logger.warning(
                "kid '%s' still absent for issuer '%s' after refetch; rejecting",
                kid,
                iss,
            )
            raise UnknownKidError(iss, kid)

    def _refetch(self, pool: PoolConfig) -> _IssuerEntry:
        """Fetch the pool's JWKS and replace the cached entry for its issuer.

        Args:
            pool: The resolved pool config (provides ``iss`` + ``jwks_uri``).

        Returns:
            The freshly-populated :class:`_IssuerEntry` (also stored in the cache).

        Raises:
            JWKSFetchError: The fetch failed or the document was malformed.
        """
        document = self._fetcher(pool.jwks_uri)
        entry = _IssuerEntry(keys=_index_keys_by_kid(document), fetched_at=time.time())
        self._entries[pool.iss] = entry
        return entry


def _index_keys_by_kid(document: Mapping) -> Dict[str, dict]:
    """Build a ``kid -> JWK`` map from a JWKS document, skipping keyless entries.

    Args:
        document: A parsed JWKS document, expected shape ``{"keys": [ {..}, ..]}``.

    Returns:
        Mapping of ``kid`` to its JWK dict. Keys without a ``kid`` are ignored (they
        cannot be selected by a token header anyway).

    Raises:
        JWKSFetchError: The document has no usable ``keys`` array — treating this as a
            fetch failure keeps the caller on the fail-fast path rather than caching an
            empty, silently-useless key-set.
    """
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


# --------------------------------------------------------------------------- #
# Flask plane: module-level cache (R3.3)
# --------------------------------------------------------------------------- #
#
# The always-on Flask process keeps ONE cache instance so warm requests reuse cached
# JWKS across the whole process. The module plane (Lambda) mirrors this by holding an
# equivalent instance in execution-environment/global scope.

_MODULE_CACHE: Optional[JWKSCache] = None
_MODULE_CACHE_LOCK = threading.Lock()


def get_module_cache(
    registry: PoolRegistry,
    fetcher: Optional[JwksFetcher] = None,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> JWKSCache:
    """Return the process-wide :class:`JWKSCache`, creating it on first use.

    The Flask plane calls this once per verification and reuses the same instance
    across requests (that reuse is what keeps JWKS off the hot path). The instance is
    created lazily with the given ``registry``/``fetcher``/``ttl`` on first call;
    subsequent calls return the existing instance and **ignore** later arguments (use
    :func:`reset_module_cache` to rebuild, e.g. between tests).

    Args:
        registry: The issuer->pool registry used to resolve issuers.
        fetcher: Optional JWKS fetcher (defaults to the HTTPS fetcher).
        ttl_seconds: Cache TTL for a newly-created instance.

    Returns:
        The shared :class:`JWKSCache` instance.
    """
    global _MODULE_CACHE
    if _MODULE_CACHE is None:
        with _MODULE_CACHE_LOCK:
            if _MODULE_CACHE is None:
                _MODULE_CACHE = JWKSCache(
                    registry=registry, fetcher=fetcher, ttl_seconds=ttl_seconds
                )
    return _MODULE_CACHE


def reset_module_cache() -> None:
    """Drop the process-wide cache instance (test isolation / forced rebuild)."""
    global _MODULE_CACHE
    with _MODULE_CACHE_LOCK:
        _MODULE_CACHE = None


def get_signing_key(
    iss: str,
    kid: str,
    registry: PoolRegistry,
    fetcher: Optional[JwksFetcher] = None,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> dict:
    """Module-level convenience: resolve ``(iss, kid)`` via the shared cache.

    Thin wrapper the verifier (T5) can call directly; it uses the process-wide
    module-level cache so warm lookups never refetch. Equivalent to
    ``get_module_cache(registry, ...).get_signing_key(iss, kid)``.

    Args:
        iss: The token issuer claim.
        kid: The signing key id from the token header.
        registry: The issuer->pool registry (T3).
        fetcher: Optional JWKS fetcher (defaults to the HTTPS fetcher).
        ttl_seconds: TTL used only if the module cache is being created now.

    Returns:
        The JWK dict for the requested ``kid``.

    Raises:
        UnknownIssuerError: ``iss`` has no registered pool.
        UnknownKidError: ``kid`` is absent even after one rotation refetch.
        JWKSFetchError: JWKS could not be fetched when required.
    """
    cache = get_module_cache(registry, fetcher=fetcher, ttl_seconds=ttl_seconds)
    return cache.get_signing_key(iss, kid)
