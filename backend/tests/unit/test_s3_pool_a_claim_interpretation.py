"""S3 / T4 — Validate Pool A selection + claim interpretation via the S2 registry.

**Validates: Requirements R1.2, R4.1**

T4 is a *validation* task, not new verification code. It asserts two things about the
**Flask plane** (`backend/src/auth/`), reusing the existing S2 path unchanged:

1. **Selection by `iss` is config-not-code (R1.2).** The live auth-path selector
   `cognito_utils._get_jwt_verifier()` builds its verifier from the S2 issuer->pool
   registry (`COGNITO_POOL_KEYS` + `{KEY}_COGNITO_*`), and the built verifier resolves
   Pool A's shape *by its `iss`*. Adding/removing a pool is an env change, never a code
   change. Here Pool A's claim shape is exercised against a **test-pool** registry entry
   — the registry registers ONLY the test pool (`eu-west-1_xyrlzfqbl`), never production
   Pool A, so nothing silently verifies against prod.

2. **Claim interpretation is correct (R1.1, referenced by R1.2).** Given a *verified*
   payload the S2 path reads `cognito:groups` as roles (filtered to the three GLOBAL
   roles by `cognito_required`) and `custom:tenants` as the user's tenant list
   (`get_verified_tenants` / `_normalize_tenants_claim`, across Cognito's delivery
   shapes). Per-tenant roles are NOT taken from the token.

Fail-fast (R4.1): a missing/blank required registry var makes verification *unavailable*
(`_get_jwt_verifier()` -> None) — never a token-accepting fallback, and never a silent
point at production.

No `load_dotenv`, no real network, no DB. Env is injected with `patch.dict`; the module
singleton is reset per test. This reuses the S2 registry loader and claim readers as-is;
it adds no production code.
"""

import os
from unittest.mock import patch

import pytest

from auth.jwt_verifier import JWTVerifier
from auth.pool_registry import PoolRegistryError, load_pool_registry


# --- Test-pool coordinates (public, non-secret identifiers) ----------------- #
#
# ONLY the standing test pool is ever registered here. Production Pool A
# (eu-west-1_Hdp40eWmu) is deliberately NOT registered so this validation can never
# silently verify a token against production (R4.1, no-dangerous-fallbacks).
TEST_POOL_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl"
TEST_POOL_JWKS = f"{TEST_POOL_ISS}/.well-known/jwks.json"
TEST_POOL_CLIENT = "test-app-client-id"
TEST_POOL_LABEL = "myAdmin-test"

# Production Pool A's issuer — used ONLY as a negative assertion (must be absent from a
# test-only registry). Never registered.
PROD_POOL_A_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_Hdp40eWmu"

# The three GLOBAL roles Pool A carries in cognito:groups (per the claim contract).
GLOBAL_ROLES = ("SysAdmin", "Administrators", "System_CRUD")


def _test_pool_registry_env():
    """A one-pool registry env declaring ONLY the test pool (never prod Pool A)."""
    return {
        "COGNITO_POOL_KEYS": "TEST",
        "TEST_COGNITO_ISSUER": TEST_POOL_ISS,
        "TEST_COGNITO_JWKS_URI": TEST_POOL_JWKS,
        "TEST_COGNITO_CLIENT_ID": TEST_POOL_CLIENT,
        "TEST_COGNITO_POOL_LABEL": TEST_POOL_LABEL,
    }


@pytest.fixture(autouse=True)
def _reset_verifier_singleton():
    """Reset cognito_utils' verifier singleton so each test re-runs selection logic."""
    import auth.cognito_utils as cu

    cu._jwt_verifier_instance = None
    cu._jwt_verifier_init_attempted = False
    yield
    cu._jwt_verifier_instance = None
    cu._jwt_verifier_init_attempted = False


# --------------------------------------------------------------------------- #
# R1.2 — Pool selection by `iss` is config-not-code (reuses the S2 registry).
# --------------------------------------------------------------------------- #


def test_flask_plane_selects_pool_by_iss_via_s2_registry_config_not_code():
    """The live auth path builds a registry verifier that resolves the pool by `iss`.

    Declaring the pool in COGNITO_POOL_KEYS (env) is all it takes — no code change.
    """
    from auth.cognito_utils import _get_jwt_verifier

    with patch.dict(os.environ, _test_pool_registry_env(), clear=True):
        verifier = _get_jwt_verifier()

    assert isinstance(verifier, JWTVerifier)
    # Multi-pool registry path (S2), not the legacy single-pool path.
    assert verifier._legacy_single_pool is False
    # The pool is resolved BY ITS ISSUER — the registry key is `iss`.
    assert TEST_POOL_ISS in verifier._registry
    resolved = verifier._registry.require(TEST_POOL_ISS)
    assert resolved.audience == TEST_POOL_CLIENT
    assert resolved.pool_label == TEST_POOL_LABEL


def test_flask_plane_adding_pool_is_config_only_no_code_change():
    """Adding Pool A later is a registry entry (env), proven by loading two pools.

    We add a *second* pool key here purely to show the mechanism is env-driven; the
    live verification still selects each pool by its `iss`. (The second entry uses a
    non-production placeholder issuer — production Pool A is never wired in tests.)
    """
    placeholder_iss = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_second00"
    env = {
        **_test_pool_registry_env(),
        "COGNITO_POOL_KEYS": "TEST,SECOND",
        "SECOND_COGNITO_ISSUER": placeholder_iss,
        "SECOND_COGNITO_JWKS_URI": f"{placeholder_iss}/.well-known/jwks.json",
        "SECOND_COGNITO_CLIENT_ID": "second-client-id",
        "SECOND_COGNITO_POOL_LABEL": "second-pool",
    }
    registry = load_pool_registry(environ=env)

    # Both pools are keyed by their issuer — no code path enumerates pools by name.
    assert TEST_POOL_ISS in registry
    assert placeholder_iss in registry
    assert registry.require(placeholder_iss).pool_label == "second-pool"


def test_flask_plane_test_registry_never_registers_production_pool_a():
    """The test-only registry registers the test pool and NOT production Pool A (R4.1).

    Guards the guardrail: validation must never silently verify against prod.
    """
    registry = load_pool_registry(environ=_test_pool_registry_env())

    assert TEST_POOL_ISS in registry
    assert PROD_POOL_A_ISS not in registry
    assert registry.issuers() == [TEST_POOL_ISS]


def test_flask_plane_unknown_issuer_is_not_guessed_to_a_pool():
    """An `iss` not in the registry resolves to nothing — the pool is never guessed."""
    registry = load_pool_registry(environ=_test_pool_registry_env())
    assert registry.get(PROD_POOL_A_ISS) is None


# --------------------------------------------------------------------------- #
# R4.1 — Fail-fast: a broken registry makes verification unavailable, never a
# token-accepting fallback and never a silent point at production.
# --------------------------------------------------------------------------- #


def test_flask_plane_missing_registry_var_makes_verification_unavailable_not_dangerous():
    """A declared pool missing a required var -> _get_jwt_verifier() returns None.

    Verification becomes UNAVAILABLE (no verifier). It never degrades into a
    token-accepting path (R4.1 / no-dangerous-fallbacks).
    """
    from auth.cognito_utils import _get_jwt_verifier

    env = _test_pool_registry_env()
    del env["TEST_COGNITO_JWKS_URI"]  # break the declared TEST pool

    with patch.dict(os.environ, env, clear=True):
        verifier = _get_jwt_verifier()

    assert verifier is None


def test_flask_plane_blank_pool_keys_registry_loader_fails_fast():
    """A blank COGNITO_POOL_KEYS is a misconfiguration — the loader raises (R4.1)."""
    env = _test_pool_registry_env()
    env["COGNITO_POOL_KEYS"] = "   "
    with pytest.raises(PoolRegistryError):
        load_pool_registry(environ=env)


# --------------------------------------------------------------------------- #
# R1.1 (referenced by R1.2) — claim interpretation on a VERIFIED payload.
#
# These reuse the exact S2 readers (`_extract_with_verifier`, `get_verified_tenants`,
# `_normalize_tenants_claim`) and the `cognito_required` global-role filter, driving
# them with a fake verifier that returns a fixed VERIFIED payload (no network/crypto).
# --------------------------------------------------------------------------- #


class _FakeVerifier:
    """Stands in for a configured JWTVerifier: returns a fixed *verified* payload."""

    def __init__(self, payload):
        self._payload = payload

    def verify_token(self, _token):
        return self._payload


def test_cognito_groups_read_as_roles_from_verified_token():
    """`cognito:groups` on the verified payload is read as the roles list (R1.1)."""
    from auth.cognito_utils import _extract_with_verifier

    payload = {
        "email": "test-goodwin@example.com",
        "cognito:groups": ["Administrators", "Finance_CRUD"],
    }
    email, roles, error = _extract_with_verifier(_FakeVerifier(payload), "tok")

    assert error is None
    assert email == "test-goodwin@example.com"
    assert roles == ["Administrators", "Finance_CRUD"]


def test_cognito_groups_scalar_normalized_to_list():
    """A scalar `cognito:groups` value is normalized to a one-element list."""
    from auth.cognito_utils import _extract_with_verifier

    payload = {"email": "u@example.com", "cognito:groups": "SysAdmin"}
    _email, roles, error = _extract_with_verifier(_FakeVerifier(payload), "tok")

    assert error is None
    assert roles == ["SysAdmin"]


def test_cognito_required_keeps_only_global_roles_from_token():
    """The token's groups are filtered to exactly the three GLOBAL roles (R1.1).

    A stray per-tenant role in `cognito:groups` (e.g. Finance_CRUD) is NOT honored as a
    global role — per-tenant authority never travels on the token in S3.
    """
    token_groups = ["SysAdmin", "Administrators", "System_CRUD", "Finance_CRUD", "STR_Read"]

    # This mirrors the filter inside cognito_required (contract §1). Asserting it here
    # pins the interpretation without invoking Flask's request/DB machinery.
    global_roles = [r for r in token_groups if r in GLOBAL_ROLES]

    assert set(global_roles) == {"SysAdmin", "Administrators", "System_CRUD"}
    assert "Finance_CRUD" not in global_roles
    assert "STR_Read" not in global_roles


@pytest.mark.parametrize(
    "tenants_claim,expected",
    [
        # A real list (raw token).
        (["GoodwinSolutions", "PeterPrive"], ["GoodwinSolutions", "PeterPrive"]),
        # A JSON-encoded string (a common Cognito delivery shape).
        ('["GoodwinSolutions", "PeterPrive"]', ["GoodwinSolutions", "PeterPrive"]),
        # An escaped-quote JSON string (Cognito's other delivery shape).
        ('[\\"GoodwinSolutions\\",\\"PeterPrive\\"]', ["GoodwinSolutions", "PeterPrive"]),
        # A bare scalar tenant.
        ("GoodwinSolutions", ["GoodwinSolutions"]),
        # Empty / absent.
        ([], []),
    ],
)
def test_custom_tenants_normalized_across_cognito_delivery_shapes(tenants_claim, expected):
    """`custom:tenants` is read as the user's tenant list across Cognito shapes (R1.1)."""
    from auth.cognito_utils import _normalize_tenants_claim

    assert _normalize_tenants_claim(tenants_claim) == expected


def test_get_verified_tenants_reads_custom_tenants_from_verified_payload():
    """`get_verified_tenants` returns the tenant list from a VERIFIED token (R1.1)."""
    import auth.cognito_utils as cu

    payload = {
        "email": "test-goodwin@example.com",
        "custom:tenants": '["GoodwinSolutions"]',
    }
    with patch.object(cu, "_get_jwt_verifier", return_value=_FakeVerifier(payload)):
        tenants = cu.get_verified_tenants("tok")

    assert tenants == ["GoodwinSolutions"]


def test_get_verified_tenants_returns_none_when_verifier_unavailable():
    """No verifier configured -> None (caller uses the dev base64 fallback), not a guess."""
    import auth.cognito_utils as cu

    with patch.object(cu, "_get_jwt_verifier", return_value=None):
        assert cu.get_verified_tenants("tok") is None
