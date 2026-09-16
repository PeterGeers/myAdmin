"""Unit tests for the JWKS fetch + cache (S2 / T4).

Validates: Requirements R3.3 (JWKS is fetched and cached — not per request — with
correct behavior on key rotation: a `kid` cache-miss triggers a single refetch;
still unknown -> reject).

The cache resolves an issuer to its pool via the T3 registry, fetches that pool's
JWKS from `jwks_uri`, and caches the key-set keyed by `iss`. These tests inject a
*fake* fetcher (a counting stub) so there is NO real network, and assert on the
exact number of fetches to prove:

- cold lookup fetches once and populates the cache,
- a warm hit does NOT refetch,
- TTL expiry forces a refetch,
- an unknown `kid` triggers EXACTLY ONE refetch, succeeding if the key is now present,
- an unknown `kid` still missing after that refetch raises,
- an unknown issuer raises without any fetch.

No load_dotenv, no real connections — env/registry are constructed in-process.
"""

import pytest

from auth.test_pool_config import PoolConfig
from auth.pool_registry import PoolRegistry, UnknownIssuerError
from auth.jwks_cache import (
    JWKSCache,
    JWKSFetchError,
    UnknownKidError,
    get_module_cache,
    get_signing_key,
    reset_module_cache,
)

# The standing test pool (public, non-secret identifiers).
_TEST_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl"
_TEST_JWKS_URI = f"{_TEST_ISS}/.well-known/jwks.json"


def _pool(iss=_TEST_ISS, jwks_uri=_TEST_JWKS_URI):
    return PoolConfig(
        iss=iss,
        jwks_uri=jwks_uri,
        audience="43s15cm8qcgg8an85udt0e087u",
        pool_label="myAdmin-test",
    )


def _registry(*pools):
    return PoolRegistry(pools or (_pool(),))


def _jwk(kid):
    """A minimal JWK dict — only `kid` matters for cache indexing/lookup."""
    return {"kid": kid, "kty": "RSA", "alg": "RS256", "use": "sig", "n": "x", "e": "AQAB"}


def _jwks(*kids):
    """A JWKS document ({"keys": [...]}) containing the given key ids."""
    return {"keys": [_jwk(k) for k in kids]}


class CountingFetcher:
    """A fake JWKS fetcher that counts calls and returns scripted documents.

    `documents` is a list returned in order across successive fetches; the last entry
    is reused for any further fetch. This lets a test model key rotation (the second
    fetch returns a document with a new `kid`).
    """

    def __init__(self, documents):
        self._documents = list(documents)
        self.calls = 0
        self.uris = []

    def __call__(self, jwks_uri):
        self.uris.append(jwks_uri)
        index = min(self.calls, len(self._documents) - 1)
        self.calls += 1
        return self._documents[index]


@pytest.fixture(autouse=True)
def _reset_module_cache_between_tests():
    """Ensure the process-wide module cache never leaks across tests."""
    reset_module_cache()
    yield
    reset_module_cache()


# --------------------------------------------------------------------------- #
# Cold fetch / warm hit / TTL
# --------------------------------------------------------------------------- #

def test_get_signing_key_cold_lookup_fetches_once_and_returns_key():
    fetcher = CountingFetcher([_jwks("kid-1")])
    cache = JWKSCache(registry=_registry(), fetcher=fetcher)

    jwk = cache.get_signing_key(_TEST_ISS, "kid-1")

    assert jwk["kid"] == "kid-1"
    assert fetcher.calls == 1
    # The pool's configured jwks_uri (not a guessed endpoint) was used.
    assert fetcher.uris == [_TEST_JWKS_URI]


def test_get_signing_key_warm_hit_does_not_refetch():
    fetcher = CountingFetcher([_jwks("kid-1", "kid-2")])
    cache = JWKSCache(registry=_registry(), fetcher=fetcher)

    cache.get_signing_key(_TEST_ISS, "kid-1")  # cold fetch
    cache.get_signing_key(_TEST_ISS, "kid-2")  # served from cache
    cache.get_signing_key(_TEST_ISS, "kid-1")  # served from cache

    # Only the initial cold fetch hit the network — warm lookups stay off it.
    assert fetcher.calls == 1


def test_get_signing_key_ttl_expiry_forces_refetch():
    fetcher = CountingFetcher([_jwks("kid-1")])
    # ttl=0 makes every entry immediately "expired", so each lookup refetches.
    cache = JWKSCache(registry=_registry(), fetcher=fetcher, ttl_seconds=0)

    cache.get_signing_key(_TEST_ISS, "kid-1")
    cache.get_signing_key(_TEST_ISS, "kid-1")

    assert fetcher.calls == 2


# --------------------------------------------------------------------------- #
# Rotation: single refetch on kid miss
# --------------------------------------------------------------------------- #

def test_get_signing_key_unknown_kid_refetches_once_then_succeeds():
    # First fetch: only kid-old. Second fetch (rotation): the new kid-new appears.
    fetcher = CountingFetcher([_jwks("kid-old"), _jwks("kid-old", "kid-new")])
    cache = JWKSCache(registry=_registry(), fetcher=fetcher)

    cache.get_signing_key(_TEST_ISS, "kid-old")  # cold fetch (1)
    assert fetcher.calls == 1

    jwk = cache.get_signing_key(_TEST_ISS, "kid-new")  # miss -> ONE refetch (2)

    assert jwk["kid"] == "kid-new"
    assert fetcher.calls == 2


def test_get_signing_key_unknown_kid_still_missing_after_refetch_raises():
    # Every fetch returns the same set; kid-ghost is never present.
    fetcher = CountingFetcher([_jwks("kid-1")])
    cache = JWKSCache(registry=_registry(), fetcher=fetcher)

    with pytest.raises(UnknownKidError) as exc_info:
        cache.get_signing_key(_TEST_ISS, "kid-ghost")

    assert exc_info.value.kid == "kid-ghost"
    assert exc_info.value.iss == _TEST_ISS
    # Exactly one cold fetch + exactly one rotation refetch = 2. No hot-path looping.
    assert fetcher.calls == 2


def test_get_signing_key_unknown_kid_does_not_refetch_more_than_once():
    fetcher = CountingFetcher([_jwks("kid-1")])
    cache = JWKSCache(registry=_registry(), fetcher=fetcher)

    with pytest.raises(UnknownKidError):
        cache.get_signing_key(_TEST_ISS, "missing")  # 1 cold + 1 refetch = 2
    with pytest.raises(UnknownKidError):
        cache.get_signing_key(_TEST_ISS, "missing")  # warm entry + 1 refetch = 3

    # The second call reuses the warm cache (no cold fetch) and refetches once more:
    # never more than one refetch per unknown-kid lookup.
    assert fetcher.calls == 3


# --------------------------------------------------------------------------- #
# Unknown issuer / fetch failures
# --------------------------------------------------------------------------- #

def test_get_signing_key_unknown_issuer_raises_without_fetch():
    fetcher = CountingFetcher([_jwks("kid-1")])
    cache = JWKSCache(registry=_registry(), fetcher=fetcher)

    with pytest.raises(UnknownIssuerError):
        cache.get_signing_key("https://evil.example/not-a-pool", "kid-1")

    # An unregistered issuer is rejected before any network call.
    assert fetcher.calls == 0


def test_get_signing_key_fetch_failure_surfaces_as_jwks_fetch_error():
    def boom(_uri):
        raise JWKSFetchError(_uri, "connection refused")

    cache = JWKSCache(registry=_registry(), fetcher=boom)

    with pytest.raises(JWKSFetchError):
        cache.get_signing_key(_TEST_ISS, "kid-1")


def test_get_signing_key_malformed_document_raises_fetch_error():
    # A document without a "keys" array is a fetch failure, not a silent empty cache.
    fetcher = CountingFetcher([{"not_keys": []}])
    cache = JWKSCache(registry=_registry(), fetcher=fetcher)

    with pytest.raises(JWKSFetchError):
        cache.get_signing_key(_TEST_ISS, "kid-1")


# --------------------------------------------------------------------------- #
# Module-level cache (Flask plane) reuse
# --------------------------------------------------------------------------- #

def test_module_level_get_signing_key_reuses_process_wide_cache():
    fetcher = CountingFetcher([_jwks("kid-1", "kid-2")])
    registry = _registry()

    # First module-level call creates + populates the shared cache.
    get_signing_key(_TEST_ISS, "kid-1", registry=registry, fetcher=fetcher)
    # Second call reuses the SAME instance — no second fetch.
    get_signing_key(_TEST_ISS, "kid-2", registry=registry, fetcher=fetcher)

    assert fetcher.calls == 1


def test_get_module_cache_returns_same_instance_until_reset():
    registry = _registry()
    first = get_module_cache(registry, fetcher=CountingFetcher([_jwks("kid-1")]))
    second = get_module_cache(registry, fetcher=CountingFetcher([_jwks("kid-9")]))

    # Same instance returned; the second fetcher argument is ignored (not rebuilt).
    assert first is second

    reset_module_cache()
    third = get_module_cache(registry, fetcher=CountingFetcher([_jwks("kid-1")]))
    assert third is not first
