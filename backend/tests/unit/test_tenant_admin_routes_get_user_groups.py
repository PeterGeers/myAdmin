"""
Unit tests for ``tenant_admin_routes.get_user_groups``.

Covers the ``cognito-admin-pool-resolution`` bugfix (Task 3.3.3) migration of the
``admin_list_groups_for_user`` admin op off the legacy single-pool
``COGNITO_USER_POOL_ID`` var and onto the shared registry-backed resolver.

This op is keyed by the target user's email/username and carries NO caller token,
so it uses **email mode** (:func:`auth.admin_pool_resolver.resolve_pool_id_for_email`).
The tests assert:

  * Under the dev-container split (registry -> TEST, legacy var -> PROD), the op
    targets the registry-resolved TEST pool, NOT the legacy PROD var (Bug_Condition
    / Expected_Behavior — Refs 2.1, 2.3, 2.4).
  * Under prod single-pool config (registry == legacy == PROD_A), the op targets
    PROD_A — behaviour preserved (Preservation — Ref 3.3).
  * The response contract is preserved exactly: list of group names on success,
    ``[]`` on any failure (Cognito error or unresolvable pool) (Ref 3.3).

Test isolation: no real Cognito or MySQL. The registry is driven via
``patch.dict(os.environ, ...)`` and the module's ``cognito_client`` is mocked. A
mocked ``admin_get_user`` (the email-mode probe) reports the user present so the
declared-order probe resolves to the single registered pool.

Requirements: 2.1, 2.3, 2.4, 3.3
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure src is importable (conftest also does this).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


TARGET_USER = "peter@pgeers.nl"

# --- Registry pool ids (trailing segment of the issuer URL) ------------------
TEST_POOL_ID = "eu-west-1_xyrlzfqbl"
TEST_ISSUER = f"https://cognito-idp.eu-west-1.amazonaws.com/{TEST_POOL_ID}"
PROD_A_POOL_ID = "eu-west-1_Hdp40eWmu"
PROD_A_ISSUER = f"https://cognito-idp.eu-west-1.amazonaws.com/{PROD_A_POOL_ID}"


# --- Env: dev-container split (registry -> TEST, legacy var -> PROD) ---------
# poolFrom(legacy)=PROD but registryPoolFor(user)=TEST -> isBugCondition TRUE.
BUGGY_SPLIT_ENV = {
    "COGNITO_POOL_KEYS": "TEST",
    "TEST_COGNITO_ISSUER": TEST_ISSUER,
    "TEST_COGNITO_JWKS_URI": f"{TEST_ISSUER}/.well-known/jwks.json",
    "TEST_COGNITO_CLIENT_ID": "test-client-id",
    "TEST_COGNITO_POOL_LABEL": "myAdmin-test",
    # legacy single-pool var points at PROD (the split) — must NOT be used
    "COGNITO_USER_POOL_ID": PROD_A_POOL_ID,
    "AWS_REGION": "eu-west-1",
    "AWS_ACCESS_KEY_ID": "test-key-id",
    "AWS_SECRET_ACCESS_KEY": "test-secret-key",
    "TEST_MODE": "true",
}

# --- Env: prod single-pool (registry == legacy == PROD_A) — non-buggy --------
PROD_SINGLE_POOL_ENV = {
    "COGNITO_POOL_KEYS": "PROD_A",
    "PROD_A_COGNITO_ISSUER": PROD_A_ISSUER,
    "PROD_A_COGNITO_JWKS_URI": f"{PROD_A_ISSUER}/.well-known/jwks.json",
    "PROD_A_COGNITO_CLIENT_ID": "prod-a-client-id",
    "PROD_A_COGNITO_POOL_LABEL": "myAdmin-prod-a",
    "COGNITO_USER_POOL_ID": PROD_A_POOL_ID,
    "AWS_REGION": "eu-west-1",
    "AWS_ACCESS_KEY_ID": "test-key-id",
    "AWS_SECRET_ACCESS_KEY": "test-secret-key",
    "TEST_MODE": "true",
}


def _make_cognito_client(*, groups=None, user_present=True, list_error=None):
    """Build a mocked cognito-idp client that records the ``UserPoolId`` kwargs.

    ``admin_get_user`` (email-mode probe) succeeds when ``user_present`` is True,
    else raises the UserNotFoundException so the probe records "absent".
    ``admin_list_groups_for_user`` returns ``groups`` (as Cognito group dicts) or
    raises ``list_error`` when provided.

    Returns (client, calls) where ``calls`` maps method name -> UserPoolId.
    """
    client = MagicMock()
    calls: dict[str, str] = {}

    # Real exception class for the resolver's UserNotFoundException handling.
    not_found = type("UserNotFoundException", (Exception,), {})
    client.exceptions.UserNotFoundException = not_found

    def _get_user(*args, **kwargs):
        calls["admin_get_user"] = kwargs.get("UserPoolId")
        if user_present:
            return {"Username": TARGET_USER, "UserStatus": "CONFIRMED"}
        from botocore.exceptions import ClientError

        raise ClientError(
            {"Error": {"Code": "UserNotFoundException", "Message": "no"}},
            "AdminGetUser",
        )

    def _list_groups(*args, **kwargs):
        calls["admin_list_groups_for_user"] = kwargs.get("UserPoolId")
        if list_error is not None:
            raise list_error
        return {"Groups": [{"GroupName": g} for g in (groups or [])]}

    client.admin_get_user.side_effect = _get_user
    client.admin_list_groups_for_user.side_effect = _list_groups
    return client, calls


def _reload_module(env):
    """Reload tenant_admin_routes under ``env`` and return the module."""
    with patch.dict(os.environ, env, clear=True):
        import tenant_admin_routes

        return importlib.reload(tenant_admin_routes)


class TestGetUserGroupsPoolResolution:
    """Email-mode pool resolution for admin_list_groups_for_user."""

    @pytest.mark.unit
    def test_targets_registry_test_pool_under_dev_split(self):
        """Bug_Condition/Expected_Behavior: with registry->TEST and legacy->PROD,
        the op must list groups against the registry-resolved TEST pool, never the
        legacy PROD var. Refs 2.1, 2.3, 2.4."""
        client, calls = _make_cognito_client(groups=["Tenant_Admin", "Finance_CRUD"])
        with patch.dict(os.environ, BUGGY_SPLIT_ENV, clear=True):
            import tenant_admin_routes

            mod = importlib.reload(tenant_admin_routes)
            mod.cognito_client = client

            result = mod.get_user_groups(TARGET_USER)

        assert result == ["Tenant_Admin", "Finance_CRUD"]
        # Resolved (email-mode probe) and listed against the TEST pool, not PROD.
        assert calls.get("admin_get_user") == TEST_POOL_ID
        assert calls.get("admin_list_groups_for_user") == TEST_POOL_ID
        assert calls.get("admin_list_groups_for_user") != PROD_A_POOL_ID

    @pytest.mark.unit
    def test_targets_prod_a_under_prod_single_pool(self):
        """Preservation: under prod single-pool (registry == legacy == PROD_A) the
        op targets PROD_A, exactly as before the fix. Ref 3.3."""
        client, calls = _make_cognito_client(groups=["SysAdmin"])
        with patch.dict(os.environ, PROD_SINGLE_POOL_ENV, clear=True):
            import tenant_admin_routes

            mod = importlib.reload(tenant_admin_routes)
            mod.cognito_client = client

            result = mod.get_user_groups(TARGET_USER)

        assert result == ["SysAdmin"]
        assert calls.get("admin_list_groups_for_user") == PROD_A_POOL_ID


class TestGetUserGroupsContract:
    """Response contract preservation (Ref 3.3)."""

    @pytest.mark.unit
    def test_returns_group_names_on_success(self):
        """Success contract: list of group names."""
        client, _calls = _make_cognito_client(groups=["Tenant_Admin", "STR_Read"])
        with patch.dict(os.environ, BUGGY_SPLIT_ENV, clear=True):
            import tenant_admin_routes

            mod = importlib.reload(tenant_admin_routes)
            mod.cognito_client = client
            result = mod.get_user_groups(TARGET_USER)
        assert result == ["Tenant_Admin", "STR_Read"]

    @pytest.mark.unit
    def test_returns_empty_list_on_cognito_error(self):
        """Failure contract preserved: any Cognito error -> []."""
        client, _calls = _make_cognito_client(
            list_error=Exception("Cognito error")
        )
        with patch.dict(os.environ, BUGGY_SPLIT_ENV, clear=True):
            import tenant_admin_routes

            mod = importlib.reload(tenant_admin_routes)
            mod.cognito_client = client
            result = mod.get_user_groups(TARGET_USER)
        assert result == []

    @pytest.mark.unit
    def test_returns_empty_list_when_pool_unresolvable(self):
        """Failure contract preserved: when the user is absent from every
        registered pool (email mode raises UserPoolNotFoundError), the op still
        returns [] rather than propagating. Ref 3.3."""
        client, _calls = _make_cognito_client(user_present=False)
        with patch.dict(os.environ, BUGGY_SPLIT_ENV, clear=True):
            import tenant_admin_routes

            mod = importlib.reload(tenant_admin_routes)
            mod.cognito_client = client
            result = mod.get_user_groups(TARGET_USER)
        assert result == []
