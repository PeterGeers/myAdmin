"""Unit tests for the issuer->pool registry (S2 / T3).

Validates: Requirements R3.1 (determine the pool from `iss`), R3.2 (pools are
configuration, not code — env-driven, fail-fast, adding a pool is a registry entry).

The registry generalizes the T2 single-pool loader into a map keyed by `iss`:
- it loads *multiple* pools declared by COGNITO_POOL_KEYS,
- lookup by `iss` hits (known pool) or misses (unknown issuer -> None / raise),
- it fails fast (no defaults) on a missing/blank required var for a declared pool.

No load_dotenv, no real connections — env is injected via patch.dict / a dict.
"""

import os
from unittest.mock import patch

import pytest

from auth.test_pool_config import PoolConfig
from auth.pool_registry import (
    PoolRegistry,
    PoolRegistryError,
    UnknownIssuerError,
    load_pool_registry,
)

# The standing test pool (public, non-secret identifiers), keyed "TEST" — reuses
# the exact TEST_COGNITO_* vars the T2 loader reads.
_TEST_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl"
_TEST_POOL_ENV = {
    "TEST_COGNITO_ISSUER": _TEST_ISS,
    "TEST_COGNITO_JWKS_URI": f"{_TEST_ISS}/.well-known/jwks.json",
    "TEST_COGNITO_CLIENT_ID": "43s15cm8qcgg8an85udt0e087u",
    "TEST_COGNITO_POOL_LABEL": "myAdmin-test",
}

# A second, hypothetical pool keyed "PROD_A" — proves adding a pool is config only
# (this is what Phase 6 / T13 will add; not wired for real here).
_PROD_A_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_Hdp40eWmu"
_PROD_A_POOL_ENV = {
    "PROD_A_COGNITO_ISSUER": _PROD_A_ISS,
    "PROD_A_COGNITO_JWKS_URI": f"{_PROD_A_ISS}/.well-known/jwks.json",
    "PROD_A_COGNITO_CLIENT_ID": "prodaclient000000000000000",
    "PROD_A_COGNITO_POOL_LABEL": "myAdmin",
}


def _single_pool_env():
    return {"COGNITO_POOL_KEYS": "TEST", **_TEST_POOL_ENV}


def _two_pool_env():
    return {"COGNITO_POOL_KEYS": "TEST,PROD_A", **_TEST_POOL_ENV, **_PROD_A_POOL_ENV}


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def test_load_pool_registry_single_pool_loads_test_entry():
    """One declared pool loads into a registry with the expected entry shape."""
    with patch.dict(os.environ, _single_pool_env(), clear=True):
        registry = load_pool_registry()

    assert isinstance(registry, PoolRegistry)
    assert len(registry) == 1
    entry = registry.get(_TEST_ISS)
    assert isinstance(entry, PoolConfig)
    assert entry.jwks_uri == _TEST_POOL_ENV["TEST_COGNITO_JWKS_URI"]
    assert entry.audience == _TEST_POOL_ENV["TEST_COGNITO_CLIENT_ID"]
    assert entry.pool_label == "myAdmin-test"


def test_load_pool_registry_multiple_pools_loads_all_entries():
    """Declaring two pool keys loads both entries — adding a pool is config only."""
    with patch.dict(os.environ, _two_pool_env(), clear=True):
        registry = load_pool_registry()

    assert len(registry) == 2
    assert set(registry.issuers()) == {_TEST_ISS, _PROD_A_ISS}
    assert registry.get(_PROD_A_ISS).pool_label == "myAdmin"


def test_load_pool_registry_pool_keys_whitespace_and_dupes_normalized():
    """COGNITO_POOL_KEYS tolerates spacing/dupes and yields one entry per pool."""
    env = _single_pool_env()
    env["COGNITO_POOL_KEYS"] = " TEST , TEST ,"
    with patch.dict(os.environ, env, clear=True):
        registry = load_pool_registry()

    assert len(registry) == 1
    assert registry.get(_TEST_ISS) is not None


def test_load_pool_registry_accepts_injected_environ_mapping():
    """The loader reads an injected mapping (no dependence on os.environ)."""
    registry = load_pool_registry(environ=_single_pool_env())
    assert len(registry) == 1
    assert _TEST_ISS in registry


# --------------------------------------------------------------------------- #
# Lookup (hit / miss)
# --------------------------------------------------------------------------- #

def test_get_known_issuer_returns_pool_config():
    """Lookup by a registered `iss` returns that pool (hit)."""
    registry = load_pool_registry(environ=_two_pool_env())
    assert registry.get(_TEST_ISS).pool_label == "myAdmin-test"
    assert registry.get(_PROD_A_ISS).pool_label == "myAdmin"


def test_get_unknown_issuer_returns_none():
    """Lookup by an unregistered `iss` returns None (miss) — no guessing."""
    registry = load_pool_registry(environ=_single_pool_env())
    assert registry.get("https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_unknown") is None


def test_require_known_issuer_returns_pool_config():
    """require() returns the pool for a registered issuer."""
    registry = load_pool_registry(environ=_single_pool_env())
    assert registry.require(_TEST_ISS).iss == _TEST_ISS


def test_require_unknown_issuer_raises_unknown_issuer_error():
    """require() makes an unknown issuer explicit (verifier maps this to 401)."""
    registry = load_pool_registry(environ=_single_pool_env())
    bad_iss = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_nope"
    with pytest.raises(UnknownIssuerError) as exc_info:
        registry.require(bad_iss)
    assert exc_info.value.iss == bad_iss
    assert bad_iss in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Fail-fast (no defaults)
# --------------------------------------------------------------------------- #

def test_load_pool_registry_missing_pool_keys_raises():
    """No COGNITO_POOL_KEYS -> fail fast; an empty registry is not a valid state."""
    with patch.dict(os.environ, _TEST_POOL_ENV, clear=True):
        with pytest.raises(PoolRegistryError):
            load_pool_registry()


def test_load_pool_registry_blank_pool_keys_raises():
    """A whitespace-only COGNITO_POOL_KEYS is treated as missing."""
    env = _single_pool_env()
    env["COGNITO_POOL_KEYS"] = "   "
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PoolRegistryError):
            load_pool_registry()


@pytest.mark.parametrize("suffix", sorted(
    ["COGNITO_ISSUER", "COGNITO_JWKS_URI", "COGNITO_CLIENT_ID", "COGNITO_POOL_LABEL"]
))
def test_load_pool_registry_missing_required_var_for_declared_pool_raises(suffix):
    """Removing any required var for a declared pool fails fast — no default."""
    env = _single_pool_env()
    del env[f"TEST_{suffix}"]
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PoolRegistryError) as exc_info:
            load_pool_registry()
    assert f"TEST_{suffix}" in str(exc_info.value)


@pytest.mark.parametrize("suffix", sorted(
    ["COGNITO_ISSUER", "COGNITO_JWKS_URI", "COGNITO_CLIENT_ID", "COGNITO_POOL_LABEL"]
))
def test_load_pool_registry_blank_required_var_for_declared_pool_raises(suffix):
    """A blank required var for a declared pool is treated as missing and raises."""
    env = _single_pool_env()
    env[f"TEST_{suffix}"] = "   "
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PoolRegistryError) as exc_info:
            load_pool_registry()
    assert f"TEST_{suffix}" in str(exc_info.value)


def test_load_pool_registry_declared_pool_with_no_vars_raises():
    """Declaring a pool key with none of its vars set fails fast."""
    env = {**_single_pool_env(), "COGNITO_POOL_KEYS": "TEST,GHOST"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PoolRegistryError) as exc_info:
            load_pool_registry()
    assert "GHOST" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Duplicate-issuer guard
# --------------------------------------------------------------------------- #

def test_pool_registry_duplicate_issuer_raises():
    """Two pools sharing an `iss` is a misconfiguration and fails fast."""
    dup = PoolConfig(iss=_TEST_ISS, jwks_uri="j", audience="a", pool_label="one")
    dup2 = PoolConfig(iss=_TEST_ISS, jwks_uri="j2", audience="a2", pool_label="two")
    with pytest.raises(PoolRegistryError):
        PoolRegistry([dup, dup2])
