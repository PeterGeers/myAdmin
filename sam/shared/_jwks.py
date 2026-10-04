"""
Module-plane JWT verification — JWKS fetch + cache (extracted from ``auth_utils``).

Lambda global/execution-env scope — mirrors the Flask plane T4. Re-exported from
:mod:`sam.shared.auth_utils`; the public import surface is unchanged.

Held in module/global scope on the module plane so **warm Lambda invocations reuse it**
and never fetch JWKS per request. Lookups return the raw JWK dict for a ``kid``;
converting it to a public key is the verifier's concern, keeping this layer
transport-only and easy to unit test.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import requests

from sam.shared._auth_errors import JWKSFetchError, UnknownKidError
from sam.shared._pool_registry import PoolConfig, PoolRegistry

logger = logging.getLogger(__name__)

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

    keys: dict[str, dict] = field(default_factory=dict)
    fetched_at: float = 0.0

    def is_expired(self, ttl_seconds: int, now: float) -> bool:
        """True if never populated or older than the TTL."""
        if self.fetched_at == 0.0:
            return True
        return (now - self.fetched_at) > ttl_seconds


def _index_keys_by_kid(document: Mapping) -> dict[str, dict]:
    """Build a ``kid -> JWK`` map from a JWKS document, skipping keyless entries."""
    keys = document.get("keys") if isinstance(document, Mapping) else None
    if not isinstance(keys, list):
        raise JWKSFetchError(
            "<jwks-document>", "response did not contain a 'keys' array"
        )
    indexed: dict[str, dict] = {}
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
        fetcher: JwksFetcher | None = None,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ):
        self._registry = registry
        self._fetcher = fetcher or _default_fetcher
        self._ttl_seconds = ttl_seconds
        self._entries: dict[str, _IssuerEntry] = {}
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


__all__ = [
    "JWKSCache",
    "JwksFetcher",
]
