"""S3 / T6 — Integration test: Pool A claim contract (acceptance: D1).

**Validates: Requirements R1.1, R1.2, R1.3, R4.1 (acceptance criterion D1)**

This is the **D1 acceptance integration test**. Where T4
(``tests/unit/test_s3_pool_a_claim_interpretation.py``) validates selection and claim
reads at the *unit* level (fake verifier, no crypto), T6 exercises the **whole live
verification stack end to end** against the standing **test pool**
(``eu-west-1_xyrlzfqbl``, registry key ``TEST``):

    PoolRegistry (S2, config-not-code)  ->  JWKSCache (S2, injected fetcher)
                                        ->  JWTVerifier (S2, RS256 verify)
                                        ->  cognito_utils claim readers (Flask plane)

and asserts the four facts the D1 acceptance criterion names:

1. **Selected as Pool A by ``iss``.** A test-pool token whose ``iss`` matches the test
   pool's issuer is resolved to that pool and verified against *its* JWKS — the pool is
   chosen by ``iss`` through the S2 registry (config-not-code), never guessed.
2. **``cognito:groups`` read as global roles.** The verified payload's ``cognito:groups``
   are read by the live Flask reader (``_extract_with_verifier``) and, per the claim
   contract, filtered to exactly the three GLOBAL roles.
3. **``custom:tenants`` read as the tenant list.** The verified payload's
   ``custom:tenants`` are read by the live reader (``_normalize_tenants_claim`` /
   ``get_verified_tenants``) as the user's tenant list, across Cognito delivery shapes.
4. **Per-tenant roles NOT taken from the token.** A per-tenant role that rides
   ``cognito:groups`` (e.g. ``Finance_CRUD``) is never honored as a global role — S3
   keeps per-tenant authority in MySQL (``user_tenant_roles`` via ``role_cache.py``),
   never on the token.

Harness reuse (S2): RS256 keys are generated **in-test** and the JWKS fetch is
**injected** (``JWKSCache(fetcher=...)``), matching the test pool's issuer — the exact
offline pattern used by ``sam/tests/test_auth_utils.py`` and
``tests/unit/test_jwt_verifier_multipool.py``. No real network is reached and no secrets
are used, so the acceptance example is deterministic and CI-safe while still driving the
*real* verifier (real RS256 signature verification, real ``iss``/``aud``/``exp`` checks).

Fail-fast / no-prod-fallback (R4.1): the registry here registers **only** the test pool.
Production Pool A (``eu-west-1_Hdp40eWmu``) is deliberately never registered, so this
acceptance test can never verify a token against production.
"""

import json
import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from auth.jwks_cache import JWKSCache
from auth.jwt_verifier import InvalidTokenError, JWTVerifier
from auth.pool_registry import PoolRegistry
from auth.test_pool_config import PoolConfig


# --- Test-pool coordinates (public, non-secret identifiers) ----------------- #
#
# The standing test pool (registry key TEST in backend/.env). ONLY this pool is
# registered below. Production Pool A (eu-west-1_Hdp40eWmu) is NEVER registered here —
# the acceptance example must never reach production (R4.1, no-dangerous-fallbacks).
TEST_POOL_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl"
TEST_POOL_JWKS = f"{TEST_POOL_ISS}/.well-known/jwks.json"
TEST_POOL_CLIENT = "test-app-client-id"
TEST_POOL_LABEL = "myAdmin-test"
TEST_KID = "test-key-1"

# Production Pool A issuer — used ONLY as a negative assertion (must be absent).
PROD_POOL_A_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_Hdp40eWmu"

# The three GLOBAL roles Pool A carries in cognito:groups (the claim contract, R1.1).
GLOBAL_ROLES = ("SysAdmin", "Administrators", "System_CRUD")


# --- In-test RS256 key + JWKS helpers (reused S2 harness pattern) ----------- #


def _pem(private_key) -> bytes:
    """PEM-encode an RSA private key for PyJWT signing."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _jwk_from_private_key(private_key, kid: str) -> dict:
    """Public JWK (with kid) derived from an RSA private key, for the JWKS document."""
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return jwk


def _make_token(
    private_key,
    *,
    iss=TEST_POOL_ISS,
    client_id=TEST_POOL_CLIENT,
    sub="user-123",
    email="test-goodwin@example.com",
    groups=None,
    tenants=None,
    kid=TEST_KID,
    exp_delta=3600,
) -> str:
    """Sign a realistic Cognito-shaped access token with the in-test RSA key."""
    now = int(time.time())
    claims = {
        "iss": iss,
        "sub": sub,
        "email": email,
        "client_id": client_id,
        "token_use": "access",
        "iat": now,
        "exp": now + exp_delta,
    }
    if groups is not None:
        claims["cognito:groups"] = groups
    if tenants is not None:
        claims["custom:tenants"] = tenants
    return pyjwt.encode(
        claims, _pem(private_key), algorithm="RS256", headers={"kid": kid}
    )


# --- Live-stack fixtures (real registry + cache + verifier, injected JWKS) --- #


@pytest.fixture(scope="module")
def signing_key():
    """A single in-test RSA signing key shared across the module's examples."""
    return rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )


@pytest.fixture
def registry():
    """A registry with ONLY the test pool — never production Pool A (R4.1)."""
    return PoolRegistry(
        [
            PoolConfig(
                iss=TEST_POOL_ISS,
                jwks_uri=TEST_POOL_JWKS,
                audience=TEST_POOL_CLIENT,
                pool_label=TEST_POOL_LABEL,
            )
        ]
    )


@pytest.fixture
def verifier(registry, signing_key):
    """The REAL JWTVerifier whose JWKS 'fetch' returns our in-test document (no network).

    This is the S2 verification path unchanged: real RS256 verification against a
    per-issuer JWKS cache; only the transport (the fetcher) is injected so the example
    is offline and deterministic.
    """
    document = {"keys": [_jwk_from_private_key(signing_key, TEST_KID)]}
    cache = JWKSCache(registry=registry, fetcher=lambda _uri: document)
    return JWTVerifier(registry=registry, jwks_cache=cache)


# --------------------------------------------------------------------------- #
# D1 acceptance — the Pool A claim contract, end to end through the live stack.
# --------------------------------------------------------------------------- #


def test_verify_token_test_pool_token_selected_as_pool_a_by_iss(verifier, signing_key):
    """A test-pool token is selected as Pool A by its `iss` and verifies (D1, R1.2)."""
    token = _make_token(signing_key, groups=["Administrators"], tenants=["GoodwinSolutions"])

    payload = verifier.verify_token(token)

    # Selected & verified against the test pool — resolution is by `iss`.
    assert payload["iss"] == TEST_POOL_ISS
    assert payload["sub"] == "user-123"
    # The pool was chosen by its issuer through the S2 registry (config-not-code).
    assert TEST_POOL_ISS in verifier._registry
    assert verifier._registry.require(TEST_POOL_ISS).pool_label == TEST_POOL_LABEL


def test_verify_token_cognito_groups_read_as_global_roles(verifier, signing_key):
    """`cognito:groups` on the VERIFIED token are read + filtered to global roles (D1, R1.1)."""
    from auth.cognito_utils import _extract_with_verifier

    token = _make_token(
        signing_key,
        groups=["SysAdmin", "Administrators", "System_CRUD"],
        tenants=["GoodwinSolutions"],
    )

    # Live Flask reader over the REAL verifier (verifies, then reads groups as roles).
    email, roles, error = _extract_with_verifier(verifier, token)

    assert error is None
    assert email == "test-goodwin@example.com"
    # Every group is one of the three GLOBAL roles the contract allows.
    assert set(roles) == set(GLOBAL_ROLES)
    global_roles = [r for r in roles if r in GLOBAL_ROLES]
    assert set(global_roles) == set(GLOBAL_ROLES)


def test_verify_token_custom_tenants_read_as_tenant_list(verifier, signing_key):
    """`custom:tenants` on the VERIFIED token is read as the tenant list (D1, R1.1)."""
    from auth.cognito_utils import _normalize_tenants_claim

    # JSON-encoded string is one of Cognito's real delivery shapes for custom:tenants.
    token = _make_token(
        signing_key,
        groups=["Administrators"],
        tenants='["GoodwinSolutions", "PeterPrive"]',
    )

    payload = verifier.verify_token(token)
    tenants = _normalize_tenants_claim(payload.get("custom:tenants", []))

    assert tenants == ["GoodwinSolutions", "PeterPrive"]


def test_verify_token_per_tenant_roles_not_taken_from_token(verifier, signing_key):
    """A per-tenant role riding `cognito:groups` is NOT honored as a global role (D1, R1.3).

    S3 keeps per-tenant authority in MySQL (`user_tenant_roles` via `role_cache.py`);
    the token carries only global roles. Even when `Finance_CRUD` / `STR_Read` appear in
    the verified token's groups, the contract's global-role filter drops them.
    """
    from auth.cognito_utils import _extract_with_verifier

    token = _make_token(
        signing_key,
        groups=["SysAdmin", "Finance_CRUD", "STR_Read"],
        tenants=["GoodwinSolutions"],
    )

    _email, roles, error = _extract_with_verifier(verifier, token)
    assert error is None

    # The contract's global-role filter (mirrors cognito_required §1): only the three
    # GLOBAL roles survive; per-tenant grants on the token are discarded.
    global_roles = [r for r in roles if r in GLOBAL_ROLES]
    assert global_roles == ["SysAdmin"]
    assert "Finance_CRUD" not in global_roles
    assert "STR_Read" not in global_roles


# --------------------------------------------------------------------------- #
# R4.1 guardrail — the acceptance harness can never reach production Pool A.
# --------------------------------------------------------------------------- #


def test_registry_registers_only_test_pool_never_production_pool_a(registry):
    """The acceptance registry registers the test pool and NOT production Pool A (R4.1)."""
    assert TEST_POOL_ISS in registry
    assert PROD_POOL_A_ISS not in registry
    assert registry.issuers() == [TEST_POOL_ISS]


def test_verify_token_from_unregistered_issuer_is_rejected(verifier, signing_key):
    """A token whose `iss` is production Pool A (unregistered) is rejected 401 (R4.1)."""
    token = _make_token(signing_key, iss=PROD_POOL_A_ISS, groups=["Administrators"])

    with pytest.raises(InvalidTokenError) as exc:
        verifier.verify_token(token)
    assert exc.value.http_status == 401
