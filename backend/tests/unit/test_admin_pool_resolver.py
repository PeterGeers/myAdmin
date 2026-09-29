"""
Unit tests for the shared registry-backed admin pool resolver.

Bugfix ``cognito-admin-pool-resolution`` Task 3.1. Covers the resolver's public
surface (``auth.admin_pool_resolver``): pool-id derivation, token mode, email mode,
disambiguation, not-found handling, and the registry-absent legacy fallback.

Isolation: no real Cognito or MySQL. The Cognito probe client is patched at
``admin_pool_resolver.boto3.client`` and the token-mode verifier at
``auth.cognito_utils._get_jwt_verifier``; the registry is driven via ``patch.dict``
on the ``COGNITO_POOL_KEYS`` / ``{KEY}_COGNITO_*`` env vars.

Validates: Requirements 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 3.4
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from auth import admin_pool_resolver as apr
from auth.admin_pool_resolver import (
    AmbiguousUserPoolError,
    PoolResolutionError,
    UserPoolNotFoundError,
    pool_id_from_issuer,
    resolve_pool_id_for_email,
    resolve_pool_id_for_token,
)

# --- Fixture pool coordinates (public, non-secret test values) ------------------

REGION = "eu-west-1"
TEST_POOL_ID = "eu-west-1_xyrlzfqbl"
PROD_POOL_ID = "eu-west-1_Hdp40eWmu"
TEST_ISS = f"https://cognito-idp.{REGION}.amazonaws.com/{TEST_POOL_ID}"
PROD_ISS = f"https://cognito-idp.{REGION}.amazonaws.com/{PROD_POOL_ID}"


def _pool_env(*keys: str) -> dict:
    """Build a registry env dict for the given declared pool keys (in order)."""
    coords = {
        "TEST": (TEST_ISS, TEST_POOL_ID),
        "PROD_A": (PROD_ISS, PROD_POOL_ID),
    }
    env = {"COGNITO_POOL_KEYS": ",".join(keys)}
    for key in keys:
        iss, _pid = coords[key]
        env[f"{key}_COGNITO_ISSUER"] = iss
        env[f"{key}_COGNITO_JWKS_URI"] = f"{iss}/.well-known/jwks.json"
        env[f"{key}_COGNITO_CLIENT_ID"] = f"{key.lower()}-client-id"
        env[f"{key}_COGNITO_POOL_LABEL"] = f"myAdmin-{key.lower()}"
    return env


def _clean_env(**overrides) -> dict:
    """A base env with all pool-related vars cleared, then apply overrides."""
    env = {
        "COGNITO_POOL_KEYS": "",
        "COGNITO_USER_POOL_ID": "",
        "TEST_COGNITO_ISSUER": "",
        "TEST_COGNITO_JWKS_URI": "",
        "TEST_COGNITO_CLIENT_ID": "",
        "TEST_COGNITO_POOL_LABEL": "",
        "PROD_A_COGNITO_ISSUER": "",
        "PROD_A_COGNITO_JWKS_URI": "",
        "PROD_A_COGNITO_CLIENT_ID": "",
        "PROD_A_COGNITO_POOL_LABEL": "",
    }
    env.update(overrides)
    return env


def _user_not_found() -> ClientError:
    return ClientError(
        {"Error": {"Code": "UserNotFoundException", "Message": "not found"}},
        "AdminGetUser",
    )


def _fake_cognito(existing: dict) -> MagicMock:
    """A cognito-idp client whose admin_get_user succeeds only for (pool, email)
    pairs listed in ``existing`` = {pool_id: {emails}}."""
    client = MagicMock()

    def _admin_get_user(UserPoolId=None, Username=None):
        if Username in existing.get(UserPoolId, set()):
            return {"Username": Username, "UserStatus": "CONFIRMED"}
        raise _user_not_found()

    client.admin_get_user.side_effect = _admin_get_user
    return client


# --- pool_id_from_issuer --------------------------------------------------------


def test_pool_id_from_issuer_standard_url_returns_trailing_segment():
    assert pool_id_from_issuer(TEST_ISS) == TEST_POOL_ID
    assert pool_id_from_issuer(PROD_ISS) == PROD_POOL_ID


def test_pool_id_from_issuer_trailing_slash_returns_trailing_segment():
    assert pool_id_from_issuer(TEST_ISS + "/") == TEST_POOL_ID


# --- Token mode (2.3) -----------------------------------------------------------


def test_resolve_pool_id_for_token_known_issuer_returns_pool_id():
    env = _clean_env(**_pool_env("TEST", "PROD_A"))
    verifier = MagicMock()
    verifier.verify_token.return_value = {"iss": TEST_ISS, "email": "u@example.com"}
    with patch.dict(os.environ, env, clear=False), patch(
        "auth.cognito_utils._get_jwt_verifier", return_value=verifier
    ):
        assert resolve_pool_id_for_token("tok") == TEST_POOL_ID


def test_resolve_pool_id_for_token_unknown_issuer_rejects():
    from auth.pool_registry import UnknownIssuerError

    env = _clean_env(**_pool_env("TEST"))
    verifier = MagicMock()
    verifier.verify_token.return_value = {"iss": PROD_ISS}
    with patch.dict(os.environ, env, clear=False), patch(
        "auth.cognito_utils._get_jwt_verifier", return_value=verifier
    ):
        with pytest.raises(UnknownIssuerError):
            resolve_pool_id_for_token("tok")


# --- Email mode (2.5 / 2.7) -----------------------------------------------------


def test_resolve_pool_id_for_email_single_hit_returns_that_pool():
    env = _clean_env(**_pool_env("TEST", "PROD_A"))
    client = _fake_cognito({TEST_POOL_ID: {"u@example.com"}})
    with patch.dict(os.environ, env, clear=False), patch.object(
        apr.boto3, "client", return_value=client
    ):
        assert resolve_pool_id_for_email("u@example.com") == TEST_POOL_ID


def test_resolve_pool_id_for_email_none_found_raises_user_pool_not_found():
    env = _clean_env(**_pool_env("TEST", "PROD_A"))
    client = _fake_cognito({})
    with patch.dict(os.environ, env, clear=False), patch.object(
        apr.boto3, "client", return_value=client
    ):
        with pytest.raises(UserPoolNotFoundError):
            resolve_pool_id_for_email("missing@example.com")


def test_resolve_pool_id_for_email_none_found_anti_enumeration_returns_none():
    env = _clean_env(**_pool_env("TEST", "PROD_A"))
    client = _fake_cognito({})
    with patch.dict(os.environ, env, clear=False), patch.object(
        apr.boto3, "client", return_value=client
    ):
        assert (
            resolve_pool_id_for_email("missing@example.com", anti_enumeration=True)
            is None
        )


# --- Disambiguation (2.6) -------------------------------------------------------


def test_resolve_pool_id_for_email_multi_hit_with_token_in_hits_returns_token_pool():
    env = _clean_env(**_pool_env("TEST", "PROD_A"))
    client = _fake_cognito(
        {TEST_POOL_ID: {"shared@example.com"}, PROD_POOL_ID: {"shared@example.com"}}
    )
    verifier = MagicMock()
    verifier.verify_token.return_value = {"iss": PROD_ISS}
    with patch.dict(os.environ, env, clear=False), patch.object(
        apr.boto3, "client", return_value=client
    ), patch("auth.cognito_utils._get_jwt_verifier", return_value=verifier):
        resolved = resolve_pool_id_for_email(
            "shared@example.com", caller_token="tok"
        )
        assert resolved == PROD_POOL_ID


def test_resolve_pool_id_for_email_multi_hit_tokenless_raises_ambiguous():
    env = _clean_env(**_pool_env("TEST", "PROD_A"))
    client = _fake_cognito(
        {TEST_POOL_ID: {"shared@example.com"}, PROD_POOL_ID: {"shared@example.com"}}
    )
    with patch.dict(os.environ, env, clear=False), patch.object(
        apr.boto3, "client", return_value=client
    ):
        with pytest.raises(AmbiguousUserPoolError) as exc:
            resolve_pool_id_for_email("shared@example.com")
    assert exc.value.email == "shared@example.com"
    assert set(exc.value.hits) == {TEST_POOL_ID, PROD_POOL_ID}


# --- Not-found handling (2.7): non-500 op vs forgot-password success ------------


def test_resolve_pool_id_for_email_not_found_surfacing_op_raises_non_500_error():
    """Not-found-surfacing ops get a UserPoolNotFoundError (mapped to a non-500),
    never a silent action on the legacy/prod pool."""
    env = _clean_env(**_pool_env("TEST", "PROD_A"))
    client = _fake_cognito({})
    with patch.dict(os.environ, env, clear=False), patch.object(
        apr.boto3, "client", return_value=client
    ):
        with pytest.raises(UserPoolNotFoundError):
            resolve_pool_id_for_email("ghost@example.com", anti_enumeration=False)


def test_resolve_pool_id_for_email_forgot_password_absent_returns_none_no_signal():
    """Forgot-password (anti_enumeration) returns None for an absent user — no
    existence signal to the caller (preserves anti-enumeration)."""
    env = _clean_env(**_pool_env("TEST", "PROD_A"))
    client = _fake_cognito({})
    with patch.dict(os.environ, env, clear=False), patch.object(
        apr.boto3, "client", return_value=client
    ):
        assert (
            resolve_pool_id_for_email("ghost@example.com", anti_enumeration=True)
            is None
        )


# --- Registry-absent fallback (3.4) ---------------------------------------------


def test_resolve_pool_id_for_token_registry_absent_returns_legacy_var():
    env = _clean_env(COGNITO_USER_POOL_ID=PROD_POOL_ID)
    with patch.dict(os.environ, env, clear=False):
        assert resolve_pool_id_for_token("tok") == PROD_POOL_ID


def test_resolve_pool_id_for_email_registry_absent_returns_legacy_var():
    env = _clean_env(COGNITO_USER_POOL_ID=PROD_POOL_ID)
    with patch.dict(os.environ, env, clear=False):
        assert resolve_pool_id_for_email("u@example.com") == PROD_POOL_ID


def test_resolve_pool_id_registry_absent_legacy_unset_raises_pool_resolution_error():
    env = _clean_env()  # no registry, no legacy var
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(PoolResolutionError):
            resolve_pool_id_for_token("tok")
        with pytest.raises(PoolResolutionError):
            resolve_pool_id_for_email("u@example.com")


def test_resolve_pool_id_registry_present_legacy_var_never_read():
    """With the registry present, the legacy COGNITO_USER_POOL_ID must never be
    consulted — resolution comes from the registry even if the legacy var points
    at a DIFFERENT (wrong) pool (the split-brain the bug is about)."""
    env = _clean_env(**_pool_env("TEST"))
    env["COGNITO_USER_POOL_ID"] = PROD_POOL_ID  # legacy points at the WRONG pool
    client = _fake_cognito({TEST_POOL_ID: {"u@example.com"}})
    verifier = MagicMock()
    verifier.verify_token.return_value = {"iss": TEST_ISS}
    with patch.dict(os.environ, env, clear=False), patch.object(
        apr.boto3, "client", return_value=client
    ), patch("auth.cognito_utils._get_jwt_verifier", return_value=verifier):
        # Token mode resolves to the registry (TEST), not the legacy PROD var.
        assert resolve_pool_id_for_token("tok") == TEST_POOL_ID
        # Email mode probes the registry pool (TEST), not the legacy PROD var.
        assert resolve_pool_id_for_email("u@example.com") == TEST_POOL_ID


def test_registry_misconfigured_raises_pool_resolution_error_not_legacy_read():
    """COGNITO_POOL_KEYS declared but a required pool var missing -> surface a
    PoolResolutionError, never a silent legacy fallback."""
    env = _clean_env(COGNITO_POOL_KEYS="TEST", COGNITO_USER_POOL_ID=PROD_POOL_ID)
    # TEST_* vars are blank -> load_pool_registry raises PoolRegistryError.
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(PoolResolutionError):
            resolve_pool_id_for_token("tok")
