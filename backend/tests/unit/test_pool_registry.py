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
    ResolvedIdentity,
    UnknownIssuerError,
    active_pool_from_registry,
    issuer_for_pool_id,
    load_pool_registry,
    resolved_identity,
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
# Declared-order accessor (additive, read-only)
# --------------------------------------------------------------------------- #

def test_entries_in_declared_order_returns_entries_in_pool_keys_order():
    """entries_in_declared_order() returns PoolConfigs in COGNITO_POOL_KEYS order."""
    registry = load_pool_registry(environ=_two_pool_env())

    entries = registry.entries_in_declared_order()
    assert [e.iss for e in entries] == [_TEST_ISS, _PROD_A_ISS]
    assert [e.pool_label for e in entries] == ["myAdmin-test", "myAdmin"]
    assert all(isinstance(e, PoolConfig) for e in entries)


def test_entries_in_declared_order_reflects_reversed_pool_keys_order():
    """Declaration order drives the result — reversing COGNITO_POOL_KEYS reverses it."""
    env = {
        "COGNITO_POOL_KEYS": "PROD_A,TEST",
        **_TEST_POOL_ENV,
        **_PROD_A_POOL_ENV,
    }
    registry = load_pool_registry(environ=env)

    assert [e.iss for e in registry.entries_in_declared_order()] == [
        _PROD_A_ISS,
        _TEST_ISS,
    ]


def test_entries_in_declared_order_single_pool_returns_one_entry():
    """A single declared pool yields a one-element list with that pool."""
    registry = load_pool_registry(environ=_single_pool_env())

    entries = registry.entries_in_declared_order()
    assert len(entries) == 1
    assert entries[0].iss == _TEST_ISS


# --------------------------------------------------------------------------- #
# Duplicate-issuer guard
# --------------------------------------------------------------------------- #

def test_pool_registry_duplicate_issuer_raises():
    """Two pools sharing an `iss` is a misconfiguration and fails fast."""
    dup = PoolConfig(iss=_TEST_ISS, jwks_uri="j", audience="a", pool_label="one")
    dup2 = PoolConfig(iss=_TEST_ISS, jwks_uri="j2", audience="a2", pool_label="two")
    with pytest.raises(PoolRegistryError):
        PoolRegistry([dup, dup2])


# --------------------------------------------------------------------------- #
# Active resolved identity (test-environment spec, T6)
#
# These cover the ADDITIVE active-identity bridge: deriving which pool THIS unit
# *is* from the resolver's ResolvedConfig.cognito (Req 6.1/6.3/8.3), the empty
# test-pool secret (Req 7.3/8.4), and the coherence cross-check that the active
# pool is among the registered verification pools (Req 4.1) — WITHOUT reducing the
# multi-pool registry.
# --------------------------------------------------------------------------- #

class _FakeResolvedCognito:
    """Minimal duck-typed stand-in for `environment.resolver.ResolvedCognito`.

    `resolved_identity` is intentionally duck-typed so `auth.pool_registry` stays
    free of a hard import of the environment package; this mirror keeps the unit
    test self-contained.
    """

    def __init__(self, pool_id, client_id, client_secret_ref, pool_label):
        self.pool_id = pool_id
        self.client_id = client_id
        self.client_secret_ref = client_secret_ref
        self.pool_label = pool_label


_TEST_COGNITO = _FakeResolvedCognito(
    pool_id="eu-west-1_xyrlzfqbl",
    client_id="43s15cm8qcgg8an85udt0e087u",
    client_secret_ref="",  # test pool has no secret
    pool_label="myAdmin-test",
)
_PROD_COGNITO = _FakeResolvedCognito(
    pool_id="eu-west-1_Hdp40eWmu",
    client_id="prodaclient000000000000000",
    client_secret_ref="PROD_CLIENT_SECRET_ENV",  # ref to an env var, not the value
    pool_label="myAdmin",
)


def test_issuer_for_pool_id_builds_cognito_issuer_url():
    """issuer_for_pool_id embeds the pool id as the trailing path segment."""
    iss = issuer_for_pool_id("eu-west-1_xyrlzfqbl", "eu-west-1")
    assert iss == _TEST_ISS


def test_resolved_identity_test_pool_has_empty_client_secret():
    """The active test identity carries no client secret (Req 7.3, 8.4)."""
    identity = resolved_identity(_TEST_COGNITO, environ={"AWS_REGION": "eu-west-1"})
    assert isinstance(identity, ResolvedIdentity)
    assert identity.pool_id == "eu-west-1_xyrlzfqbl"
    assert identity.client_id == "43s15cm8qcgg8an85udt0e087u"
    assert identity.client_secret == ""
    assert identity.has_client_secret is False
    assert identity.iss == _TEST_ISS


def test_resolved_identity_test_pool_ignores_ambient_secret_vars():
    """No ambient env var can give the secret-less test pool a client secret."""
    env = {
        "AWS_REGION": "eu-west-1",
        "COGNITO_CLIENT_SECRET": "should-be-ignored",
        "PROD_CLIENT_SECRET_ENV": "also-ignored",
    }
    identity = resolved_identity(_TEST_COGNITO, environ=env)
    assert identity.client_secret == ""


def test_resolved_identity_production_dereferences_secret_ref():
    """A non-empty client_secret_ref names the env var holding the secret value."""
    env = {"AWS_REGION": "eu-west-1", "PROD_CLIENT_SECRET_ENV": "s3cr3t"}
    identity = resolved_identity(_PROD_COGNITO, environ=env)
    assert identity.pool_id == "eu-west-1_Hdp40eWmu"
    assert identity.client_secret == "s3cr3t"
    assert identity.has_client_secret is True


def test_resolved_identity_production_secret_ref_unset_yields_empty():
    """A referenced-but-unset secret var yields an empty secret (fail-safe)."""
    identity = resolved_identity(_PROD_COGNITO, environ={"AWS_REGION": "eu-west-1"})
    assert identity.client_secret == ""
    assert identity.has_client_secret is False


def test_resolved_identity_region_defaults_to_eu_west_1():
    """With no region env var, the issuer uses the eu-west-1 default."""
    identity = resolved_identity(_TEST_COGNITO, environ={})
    assert identity.iss == _TEST_ISS


def test_resolved_identity_prefers_cognito_region_over_aws_region():
    """COGNITO_REGION wins over AWS_REGION when building the issuer."""
    env = {"COGNITO_REGION": "eu-west-1", "AWS_REGION": "us-east-1"}
    identity = resolved_identity(_TEST_COGNITO, environ=env)
    assert identity.iss == _TEST_ISS


def test_active_pool_from_registry_returns_registered_entry_for_active_pool():
    """The active resolved pool is found in the multi-pool verification registry."""
    registry = load_pool_registry(environ=_two_pool_env())
    entry = active_pool_from_registry(
        _TEST_COGNITO, registry, environ={"AWS_REGION": "eu-west-1"}
    )
    assert isinstance(entry, PoolConfig)
    assert entry.iss == _TEST_ISS
    assert entry.pool_label == "myAdmin-test"


def test_active_pool_from_registry_does_not_reduce_registry():
    """Resolving the active pool leaves the full multi-pool registry intact."""
    registry = load_pool_registry(environ=_two_pool_env())
    active_pool_from_registry(
        _TEST_COGNITO, registry, environ={"AWS_REGION": "eu-west-1"}
    )
    # The verification registry still knows BOTH pools (test + prod) — the active
    # identity is orthogonal to the pools the verifier validates against.
    assert len(registry) == 2
    assert set(registry.issuers()) == {_TEST_ISS, _PROD_A_ISS}


def test_active_pool_from_registry_matches_by_pool_id_across_regions():
    """A region mismatch still matches via the pool id embedded in the issuer."""
    # Registry built with eu-west-1 issuers; resolver asked for a different region.
    registry = load_pool_registry(environ=_two_pool_env())
    entry = active_pool_from_registry(
        _TEST_COGNITO, registry, environ={"AWS_REGION": "us-east-1"}
    )
    assert entry.iss == _TEST_ISS


def test_active_pool_from_registry_unregistered_active_pool_raises():
    """If the active pool is not registered, fail loudly — never a silent fallback."""
    # Registry has only the test pool; the active identity resolves to the prod pool.
    registry = load_pool_registry(environ=_single_pool_env())
    with pytest.raises(UnknownIssuerError) as exc_info:
        active_pool_from_registry(
            _PROD_COGNITO, registry, environ={"AWS_REGION": "eu-west-1"}
        )
    assert "eu-west-1_Hdp40eWmu" in str(exc_info.value)
