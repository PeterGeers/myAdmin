"""
S2 T13b — Live auth-path wiring of the issuer->pool registry (R3.2, R1.2/R1.3/R6.1).

`_get_jwt_verifier()` is the single point where `cognito_utils` decides *which*
verifier the live Flask auth path uses. Before T13b it only ever built a legacy
single-pool verifier from `COGNITO_USER_POOL_ID` / `COGNITO_REGION` /
`COGNITO_APP_CLIENT_ID`, so the T3 issuer->pool registry (and the T13a production
Pool A entry) was never activated. These tests pin the corrected selection order:

  1. ``COGNITO_POOL_KEYS`` set  -> multi-pool ``JWTVerifier(registry=...)`` whose
     registry contains the expected issuer(s) (incl. Pool A). (R3.2)
  2. only legacy vars          -> single-pool ``JWTVerifier`` for that pool.
  3. neither                   -> ``None`` (base64 dev/test fallback).
  4. ``COGNITO_POOL_KEYS`` set but a required per-pool var missing (misconfig ->
     PoolRegistryError) -> ``None`` — NEVER a token-accepting verifier
     (no-dangerous-fallbacks, R1.3).

No real network, no DB. Env is controlled with ``patch.dict`` and the module
singleton is reset between tests.

**Validates: Requirements R3.2, R1.2, R1.3, R6.1**
"""

import os
from unittest.mock import patch

import pytest

from auth.jwt_verifier import JWTVerifier


# --- Registry env fixtures (public, non-secret Cognito identifiers only) ---

# The standing test pool (key TEST) — reuses the existing TEST_COGNITO_* wiring.
TEST_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl"
TEST_JWKS = f"{TEST_ISS}/.well-known/jwks.json"
TEST_CLIENT = "test-app-client-id"

# Production Pool A (key PROD_A) — the T13a registry entry (eu-west-1_Hdp40eWmu).
POOL_A_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_Hdp40eWmu"
POOL_A_JWKS = f"{POOL_A_ISS}/.well-known/jwks.json"
POOL_A_CLIENT = "pool-a-app-client-id"

# Legacy single-pool coordinates.
LEGACY_POOL_ID = "eu-west-1_LegacyPool"
LEGACY_REGION = "eu-west-1"
LEGACY_CLIENT = "legacy-app-client-id"
LEGACY_ISS = f"https://cognito-idp.{LEGACY_REGION}.amazonaws.com/{LEGACY_POOL_ID}"


def _registry_env():
    """Env for a two-pool registry: the test pool + production Pool A."""
    return {
        "COGNITO_POOL_KEYS": "TEST,PROD_A",
        "TEST_COGNITO_ISSUER": TEST_ISS,
        "TEST_COGNITO_JWKS_URI": TEST_JWKS,
        "TEST_COGNITO_CLIENT_ID": TEST_CLIENT,
        "TEST_COGNITO_POOL_LABEL": "myAdmin-test",
        "PROD_A_COGNITO_ISSUER": POOL_A_ISS,
        "PROD_A_COGNITO_JWKS_URI": POOL_A_JWKS,
        "PROD_A_COGNITO_CLIENT_ID": POOL_A_CLIENT,
        "PROD_A_COGNITO_POOL_LABEL": "myAdmin",
    }


def _legacy_env():
    return {
        "COGNITO_USER_POOL_ID": LEGACY_POOL_ID,
        "COGNITO_REGION": LEGACY_REGION,
        "COGNITO_APP_CLIENT_ID": LEGACY_CLIENT,
    }


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module singleton so each test exercises fresh selection logic."""
    import auth.cognito_utils as cu

    cu._jwt_verifier_instance = None
    cu._jwt_verifier_init_attempted = False
    yield
    cu._jwt_verifier_instance = None
    cu._jwt_verifier_init_attempted = False


class TestRegistrySelection:
    """R3.2/R6.1: COGNITO_POOL_KEYS activates the multi-pool registry live."""

    def test_pool_keys_set_builds_registry_verifier_with_expected_issuers(self):
        """COGNITO_POOL_KEYS set -> registry verifier containing the test + Pool A iss."""
        from auth.cognito_utils import _get_jwt_verifier

        with patch.dict(os.environ, _registry_env(), clear=True):
            verifier = _get_jwt_verifier()

        assert isinstance(verifier, JWTVerifier)
        # Multi-pool (not the legacy single-pool) path was taken.
        assert verifier._legacy_single_pool is False
        # The registry resolves BOTH configured issuers — incl. production Pool A.
        assert TEST_ISS in verifier._registry
        assert POOL_A_ISS in verifier._registry
        # And Pool A's iss resolves to the Pool A entry (audience proves routing).
        assert verifier._registry.require(POOL_A_ISS).audience == POOL_A_CLIENT
        assert verifier._registry.require(POOL_A_ISS).pool_label == "myAdmin"

    def test_pool_keys_take_precedence_over_legacy_vars(self):
        """When both registry and legacy vars are set, the registry wins (R3.2)."""
        from auth.cognito_utils import _get_jwt_verifier

        env = {**_registry_env(), **_legacy_env()}
        with patch.dict(os.environ, env, clear=True):
            verifier = _get_jwt_verifier()

        assert isinstance(verifier, JWTVerifier)
        assert verifier._legacy_single_pool is False
        assert POOL_A_ISS in verifier._registry

    def test_single_pool_key_registry(self):
        """A registry with only the TEST key still activates the multi-pool path."""
        from auth.cognito_utils import _get_jwt_verifier

        env = {
            "COGNITO_POOL_KEYS": "TEST",
            "TEST_COGNITO_ISSUER": TEST_ISS,
            "TEST_COGNITO_JWKS_URI": TEST_JWKS,
            "TEST_COGNITO_CLIENT_ID": TEST_CLIENT,
            "TEST_COGNITO_POOL_LABEL": "myAdmin-test",
        }
        with patch.dict(os.environ, env, clear=True):
            verifier = _get_jwt_verifier()

        assert isinstance(verifier, JWTVerifier)
        assert verifier._legacy_single_pool is False
        assert TEST_ISS in verifier._registry


class TestLegacySinglePoolSelection:
    """Backward compatibility: legacy vars alone build a single-pool verifier."""

    def test_only_legacy_vars_builds_single_pool_verifier(self):
        from auth.cognito_utils import _get_jwt_verifier

        with patch.dict(os.environ, _legacy_env(), clear=True):
            verifier = _get_jwt_verifier()

        assert isinstance(verifier, JWTVerifier)
        assert verifier._legacy_single_pool is True
        assert verifier.user_pool_id == LEGACY_POOL_ID
        assert verifier.region == LEGACY_REGION
        assert verifier.app_client_id == LEGACY_CLIENT
        # The one-entry registry resolves that pool's issuer.
        assert LEGACY_ISS in verifier._registry

    def test_blank_pool_keys_falls_through_to_legacy(self):
        """A blank COGNITO_POOL_KEYS is treated as unset -> legacy path."""
        from auth.cognito_utils import _get_jwt_verifier

        env = {"COGNITO_POOL_KEYS": "   ", **_legacy_env()}
        with patch.dict(os.environ, env, clear=True):
            verifier = _get_jwt_verifier()

        assert isinstance(verifier, JWTVerifier)
        assert verifier._legacy_single_pool is True


class TestNoConfigReturnsNone:
    """Neither registry nor legacy vars -> None (base64 dev/test fallback)."""

    def test_no_cognito_config_returns_none(self):
        from auth.cognito_utils import _get_jwt_verifier

        with patch.dict(os.environ, {}, clear=True):
            verifier = _get_jwt_verifier()

        assert verifier is None

    def test_partial_legacy_vars_returns_none(self):
        """Only some legacy vars set (no registry) -> None."""
        from auth.cognito_utils import _get_jwt_verifier

        env = {"COGNITO_USER_POOL_ID": LEGACY_POOL_ID}  # missing region + client
        with patch.dict(os.environ, env, clear=True):
            verifier = _get_jwt_verifier()

        assert verifier is None


class TestMisconfiguredRegistryIsNotDangerous:
    """R1.3: a misconfigured registry returns None, never a token-accepting verifier."""

    def test_pool_keys_set_but_required_var_missing_returns_none(self):
        """COGNITO_POOL_KEYS declares PROD_A but its issuer var is missing -> None."""
        from auth.cognito_utils import _get_jwt_verifier

        env = _registry_env()
        # Drop a required per-pool var for the declared PROD_A pool.
        del env["PROD_A_COGNITO_ISSUER"]

        with patch.dict(os.environ, env, clear=True):
            verifier = _get_jwt_verifier()

        # Verification is UNAVAILABLE (None) — NOT a verifier that could be coaxed
        # into accepting unverified tokens.
        assert verifier is None

    def test_misconfig_does_not_fall_back_to_legacy_verifier(self):
        """A declared-but-broken registry must NOT silently build a legacy verifier.

        Even when legacy vars are ALSO present, a misconfigured registry is a hard
        error: return None rather than quietly narrowing to one pool (which would
        mask the misconfiguration and could accept a pool the operator didn't intend).
        """
        from auth.cognito_utils import _get_jwt_verifier

        env = {**_registry_env(), **_legacy_env()}
        del env["TEST_COGNITO_JWKS_URI"]  # break the declared TEST pool

        with patch.dict(os.environ, env, clear=True):
            verifier = _get_jwt_verifier()

        assert verifier is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
