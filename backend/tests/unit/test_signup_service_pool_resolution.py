"""
Unit tests for SignupService pool-resolution migration (task 3.3.6).

Bugfix ``cognito-admin-pool-resolution``: signup previously read the legacy
``COGNITO_USER_POOL_ID`` var directly as the fallback for
``SIGNUP_COGNITO_USER_POOL_ID``. After the migration:

* the explicit ``SIGNUP_COGNITO_USER_POOL_ID`` override is preserved unchanged (a
  dedicated signup pool wins, fast-path, no registry consulted);
* when the override is unset, the pool resolves via the shared registry-backed
  resolver in email mode (``resolve_pool_id_for_email``) — no direct legacy read;
* when the registry is absent, the resolver itself falls back to the legacy var, so
  single-pool deployments are observably unchanged.

These tests exercise ``SignupService._resolve_user_pool_id`` directly with the DB and
Cognito clients mocked out, so no real MySQL/Cognito connection is opened.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _no_real_clients():
    """Mock boto3 + mysql so ``SignupService()`` constructs without real connections."""
    with patch("services.signup_service.boto3") as mock_boto3, patch(
        "services.signup_service.DatabaseManager"
    ) as mock_dbm:
        mock_boto3.client.return_value = MagicMock()
        mock_dbm.return_value = MagicMock(config={})
        yield


def _make_service():
    from services.signup_service import SignupService

    return SignupService()


def test_resolve_user_pool_id_prefers_explicit_signup_override(_no_real_clients):
    """When SIGNUP_COGNITO_USER_POOL_ID is set it is returned unchanged (fast-path).

    The shared resolver must NOT be consulted — the dedicated signup pool wins.
    """
    env = {
        "SIGNUP_COGNITO_USER_POOL_ID": "eu-west-1_SignupPool",
        "SIGNUP_COGNITO_APP_CLIENT_ID": "client-id",
    }
    with patch.dict(os.environ, env, clear=False):
        svc = _make_service()

    with patch(
        "services.signup_service.resolve_pool_id_for_email"
    ) as mock_resolve:
        resolved = svc._resolve_user_pool_id("someone@example.com")

    assert resolved == "eu-west-1_SignupPool"
    mock_resolve.assert_not_called()


def test_resolve_user_pool_id_uses_resolver_when_override_unset(_no_real_clients):
    """When the override is unset the pool resolves via the shared resolver (email mode).

    No direct COGNITO_USER_POOL_ID read remains — resolution flows through
    ``resolve_pool_id_for_email`` keyed on the self-service signup email.
    """
    env = {"SIGNUP_COGNITO_APP_CLIENT_ID": "client-id"}
    # Ensure no override leaks in from the ambient environment.
    with patch.dict(os.environ, env, clear=False):
        os.environ.pop("SIGNUP_COGNITO_USER_POOL_ID", None)
        svc = _make_service()

    with patch(
        "services.signup_service.resolve_pool_id_for_email",
        return_value="eu-west-1_xyrlzfqbl",
    ) as mock_resolve:
        resolved = svc._resolve_user_pool_id("dev@example.com")

    assert resolved == "eu-west-1_xyrlzfqbl"
    mock_resolve.assert_called_once_with("dev@example.com")


def test_resolve_user_pool_id_registry_absent_falls_back_to_legacy(_no_real_clients):
    """Override unset + registry absent -> resolver returns the legacy var (preserved).

    This mirrors the old nested ``os.getenv("COGNITO_USER_POOL_ID")`` fallback: with
    COGNITO_POOL_KEYS unset the shared resolver returns COGNITO_USER_POOL_ID, so a
    single-pool deployment is observably unchanged.
    """
    env = {
        "SIGNUP_COGNITO_APP_CLIENT_ID": "client-id",
        "COGNITO_USER_POOL_ID": "eu-west-1_LegacyProd",
    }
    with patch.dict(os.environ, env, clear=False):
        os.environ.pop("SIGNUP_COGNITO_USER_POOL_ID", None)
        os.environ.pop("COGNITO_POOL_KEYS", None)
        svc = _make_service()

        # Real resolver (not patched) — registry absent branch returns legacy var.
        resolved = svc._resolve_user_pool_id("dev@example.com")

    assert resolved == "eu-west-1_LegacyProd"


def test_init_does_not_read_legacy_var_directly(_no_real_clients):
    """__init__ no longer eagerly reads COGNITO_USER_POOL_ID as a fallback.

    With the override unset but the legacy var present, the constructed service must
    NOT have captured the legacy var as its signup override (the legacy read has moved
    into the resolver's registry-absent branch, consulted lazily per email).
    """
    env = {
        "SIGNUP_COGNITO_APP_CLIENT_ID": "client-id",
        "COGNITO_USER_POOL_ID": "eu-west-1_LegacyProd",
    }
    with patch.dict(os.environ, env, clear=False):
        os.environ.pop("SIGNUP_COGNITO_USER_POOL_ID", None)
        svc = _make_service()

    assert svc.signup_pool_id_override is None
