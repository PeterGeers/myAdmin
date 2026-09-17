"""S3 / T4 — Module-plane validation: Pool A selection + claim interpretation.

**Validates: Requirements R1.2, R4.1**

The companion to the Flask-plane T4 validation
(`backend/tests/unit/test_s3_pool_a_claim_interpretation.py`), for the **module plane**
(`sam/shared/auth_utils.py`). T4 is a *validation* task — no new verification code. It
asserts, reusing the existing S2 module-plane path unchanged:

1. **Selection by `iss` is config-not-code (R1.2).** The module-plane verifier
   (`JWTVerifier` over the env-driven issuer->pool registry) resolves the pool from the
   token's `iss`. Adding a pool is a registry entry (env), never a code change. The
   registry here registers ONLY the test pool (`eu-west-1_xyrlzfqbl`) — never production
   Pool A — so validation can never silently verify against prod (R4.1).

2. **Claim interpretation is correct (R1.1, referenced by R1.2).** Roles are read from
   the *verified* token's `cognito:groups` via `get_groups` (across the raw-list and
   API-Gateway bracketed-string shapes); no client-supplied header contributes. Per the
   S2 module-plane contract, tenant-from-token is deferred (module plane exposes no
   tenant), so this validation checks role interpretation and pool selection only.

Fail-fast (R4.1): a missing/blank required registry var raises `PoolRegistryError` — the
loader never returns a partial/defaulted registry, so verification is unavailable, never
a token-accepting fallback.

RS256 keys are generated in-test and the JWKS fetch is injected — no real network, no
secrets. Nothing here imports backend/src (the module plane is a separate package).
"""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import algorithms

from sam.shared.auth_utils import (
    InvalidTokenError,
    JWKSCache,
    JWTVerifier,
    PoolConfig,
    PoolRegistry,
    PoolRegistryError,
    get_groups,
    get_verified_identity,
    load_pool_registry,
    reset_global_verifier,
)


# --- Test-pool coordinates (public, non-secret identifiers) ----------------- #
#
# ONLY the standing test pool is registered. Production Pool A (eu-west-1_Hdp40eWmu) is
# deliberately NOT registered, so this validation can never verify a token against prod
# (R4.1, no-dangerous-fallbacks).
TEST_POOL_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl"
TEST_POOL_JWKS = f"{TEST_POOL_ISS}/.well-known/jwks.json"
TEST_POOL_CLIENT = "test-app-client-id"
TEST_KID = "test-key-1"

PROD_POOL_A_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_Hdp40eWmu"


def _test_pool_env():
    """A one-pool registry env declaring ONLY the test pool (never prod Pool A)."""
    return {
        "COGNITO_POOL_KEYS": "TEST",
        "TEST_COGNITO_ISSUER": TEST_POOL_ISS,
        "TEST_COGNITO_JWKS_URI": TEST_POOL_JWKS,
        "TEST_COGNITO_CLIENT_ID": TEST_POOL_CLIENT,
        "TEST_COGNITO_POOL_LABEL": "myAdmin-test",
    }


# --- Key + token helpers ---------------------------------------------------- #


def _generate_rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk_from_private_key(private_key, kid: str) -> dict:
    jwk = json.loads(algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return jwk


def _private_pem(private_key) -> bytes:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _make_token(private_key, *, iss=TEST_POOL_ISS, client_id=TEST_POOL_CLIENT,
                groups=None, kid=TEST_KID, exp_delta=3600) -> str:
    now = int(time.time())
    claims = {
        "sub": "user-123",
        "email": "test-goodwin@example.com",
        "iss": iss,
        "client_id": client_id,
        "token_use": "access",
        "cognito:groups": ["Administrators"] if groups is None else groups,
        "iat": now,
        "exp": now + exp_delta,
    }
    return jwt.encode(claims, _private_pem(private_key), algorithm="RS256",
                      headers={"kid": kid})


# --- Fixtures --------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_global():
    reset_global_verifier()
    yield
    reset_global_verifier()


@pytest.fixture
def signing_key():
    return _generate_rsa_key()


@pytest.fixture
def registry():
    """A registry with ONLY the test pool (never production Pool A)."""
    return PoolRegistry([
        PoolConfig(iss=TEST_POOL_ISS, jwks_uri=TEST_POOL_JWKS,
                   audience=TEST_POOL_CLIENT, pool_label="myAdmin-test"),
    ])


@pytest.fixture
def verifier(registry, signing_key):
    """Verifier whose JWKS 'fetch' returns our in-test document (no network)."""
    document = {"keys": [_jwk_from_private_key(signing_key, TEST_KID)]}
    cache = JWKSCache(registry=registry, fetcher=lambda _uri: document)
    return JWTVerifier(registry=registry, jwks_cache=cache)


# --------------------------------------------------------------------------- #
# R1.2 — selection by `iss` is config-not-code (reuses the S2 module-plane registry).
# --------------------------------------------------------------------------- #


def test_module_plane_selects_pool_by_iss_and_verifies_claims(verifier, signing_key):
    """A test-pool token is selected by its `iss` and its claims are read (R1.2/R1.1)."""
    token = _make_token(signing_key, groups=["Administrators", "SysAdmin"])
    payload = verifier.verify_token(token)

    assert payload["iss"] == TEST_POOL_ISS
    assert payload["sub"] == "user-123"
    # cognito:groups read as roles from the VERIFIED token.
    assert get_groups(payload) == ["Administrators", "SysAdmin"]


def test_module_plane_adding_pool_is_config_only():
    """Adding a pool is an env registry entry — proven by loading two pools (R1.2)."""
    placeholder_iss = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_second00"
    env = {
        **_test_pool_env(),
        "COGNITO_POOL_KEYS": "TEST,SECOND",
        "SECOND_COGNITO_ISSUER": placeholder_iss,
        "SECOND_COGNITO_JWKS_URI": f"{placeholder_iss}/.well-known/jwks.json",
        "SECOND_COGNITO_CLIENT_ID": "second-client-id",
        "SECOND_COGNITO_POOL_LABEL": "second-pool",
    }
    registry = load_pool_registry(environ=env)

    assert TEST_POOL_ISS in registry
    assert placeholder_iss in registry


def test_module_plane_test_registry_never_registers_production_pool_a():
    """The test-only registry registers the test pool, NOT production Pool A (R4.1)."""
    registry = load_pool_registry(environ=_test_pool_env())

    assert TEST_POOL_ISS in registry
    assert PROD_POOL_A_ISS not in registry
    assert registry.issuers() == [TEST_POOL_ISS]


def test_module_plane_unknown_issuer_token_rejected(verifier):
    """A token from an unregistered issuer is rejected — the pool is never guessed."""
    other_key = _generate_rsa_key()
    token = _make_token(other_key, iss=PROD_POOL_A_ISS)  # prod iss not in registry
    with pytest.raises(InvalidTokenError):
        verifier.verify_token(token)


# --------------------------------------------------------------------------- #
# R4.1 — fail-fast: a broken registry raises, never a partial/defaulted registry.
# --------------------------------------------------------------------------- #


def test_module_plane_missing_registry_var_fails_fast():
    """A declared pool missing a required var -> PoolRegistryError (R4.1)."""
    env = _test_pool_env()
    del env["TEST_COGNITO_JWKS_URI"]
    with pytest.raises(PoolRegistryError):
        load_pool_registry(environ=env)


def test_module_plane_blank_pool_keys_fails_fast():
    """A blank COGNITO_POOL_KEYS is a misconfiguration — the loader raises (R4.1)."""
    env = _test_pool_env()
    env["COGNITO_POOL_KEYS"] = "   "
    with pytest.raises(PoolRegistryError):
        load_pool_registry(environ=env)


# --------------------------------------------------------------------------- #
# R1.1 — claim interpretation: roles from the verified token only.
# --------------------------------------------------------------------------- #


def test_module_plane_groups_from_verified_token_ignore_headers(verifier, signing_key):
    """Roles come only from the verified `cognito:groups`, never a header (R1.1)."""
    token = _make_token(signing_key, groups=["Administrators"])
    event = {
        "headers": {
            "Authorization": f"Bearer {token}",
            "X-Enhanced-Groups": "SysAdmin,SuperUser",  # must be ignored
        }
    }
    identity = get_verified_identity(event, verifier=verifier)

    assert identity.groups == ["Administrators"]
    assert "SysAdmin" not in identity.groups


def test_module_plane_groups_read_from_bracketed_string_shape():
    """API-Gateway bracketed-string `cognito:groups` is normalized to a list (R1.1)."""
    assert get_groups({"cognito:groups": "[Administrators System_CRUD]"}) == [
        "Administrators",
        "System_CRUD",
    ]
