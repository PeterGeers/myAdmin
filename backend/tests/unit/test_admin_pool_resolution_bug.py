"""
Bug-Condition Exploration Test — Cognito Admin Pool Resolution split-brain.

Property 1: Bug Condition — admin Cognito operations target the WRONG pool (the
legacy/PROD pool that ``COGNITO_USER_POOL_ID`` points at) instead of the target
user's registry-resolved pool, under the dev-container split.

This test encodes the EXPECTED (post-fix) behavior. It is written BEFORE the fix
and is EXPECTED TO FAIL on unfixed code — the failure CONFIRMS the bug exists.

    DO NOT "fix" a failing case here. Its failure is the proof the bug exists.
    These same assertions validate the fix once it lands (they will PASS then).

Scoped-PBT rationale (design.md → Exploratory Bug Condition Checking):
    The bug is deterministic, so the property is scoped to the concrete failing
    configuration — the dev-container split:

        registry configured for TEST   (COGNITO_POOL_KEYS=TEST, TEST_COGNITO_*)
        legacy var points at PROD       (COGNITO_USER_POOL_ID = eu-west-1_Hdp40eWmu)

    Here ``poolFrom(legacy) = PROD`` but ``registryPoolFor(user) = TEST`` →
    ``isBugCondition`` is TRUE. Each representative admin op is asserted to pass
    ``UserPoolId = <TEST pool id>``; on unfixed code it passes ``<PROD>`` → FAIL.

Bug_Condition: isBugCondition(X) = poolFrom(COGNITO_USER_POOL_ID) <> registryPoolFor(X.targetUser)
Expected_Behavior: each admin op passes UserPoolId = registryPoolFor(targetUser)

Validates: Requirements 1.1, 1.2, 1.3, 1.4
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure src is importable (conftest also does this).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


# ---------------------------------------------------------------------------
# The dev-container split configuration.
#
#   Registry (validation)  -> TEST pool   eu-west-1_xyrlzfqbl
#   Legacy var (admin ops) -> PROD pool   eu-west-1_Hdp40eWmu
#
# The TEST pool id is the trailing path segment of the TEST issuer URL, exactly
# how the fix will derive it (PoolConfig carries no user_pool_id field).
# ---------------------------------------------------------------------------
TEST_POOL_ID = "eu-west-1_xyrlzfqbl"
PROD_POOL_ID = "eu-west-1_Hdp40eWmu"  # what the legacy COGNITO_USER_POOL_ID points at

TEST_ISSUER = f"https://cognito-idp.eu-west-1.amazonaws.com/{TEST_POOL_ID}"

# Env that reproduces the dev-container split: registry -> TEST, legacy -> PROD.
DEV_CONTAINER_SPLIT_ENV = {
    # --- registry (issuer->pool), keyed to the TEST pool (what validation uses) ---
    "COGNITO_POOL_KEYS": "TEST",
    "TEST_COGNITO_ISSUER": TEST_ISSUER,
    "TEST_COGNITO_JWKS_URI": f"{TEST_ISSUER}/.well-known/jwks.json",
    "TEST_COGNITO_CLIENT_ID": "test-client-id",
    "TEST_COGNITO_POOL_LABEL": "myAdmin-test",
    # --- legacy single-pool var, pointing at PROD (what admin ops wrongly read) ---
    "COGNITO_USER_POOL_ID": PROD_POOL_ID,
    "COGNITO_CLIENT_ID": "prod-client-id",
    # --- AWS boto3 basics (mocked, never used against real AWS) ---
    "AWS_REGION": "eu-west-1",
    "AWS_ACCESS_KEY_ID": "test-key-id",
    "AWS_SECRET_ACCESS_KEY": "test-secret-key",
    # keep DB isolation happy for anything that peeks at TEST_MODE
    "TEST_MODE": "true",
}

TARGET_EMAIL = "peter@pgeers.nl"


def _make_capturing_cognito_client():
    """
    A mocked cognito-idp client that RECORDS the ``UserPoolId=...`` kwarg passed
    to each admin call, so a test can assert which pool an op actually targeted.

    Returns (client, calls) where ``calls`` is a dict mapping the admin method
    name -> the UserPoolId it was invoked with (last call wins; each op here is
    invoked once).
    """
    client = MagicMock()
    calls: dict[str, str] = {}

    def _record(method_name):
        def _side_effect(*args, **kwargs):
            calls[method_name] = kwargs.get("UserPoolId")
            # Return a benign, well-formed response for each op.
            if method_name == "admin_get_user":
                return {
                    "Username": TARGET_EMAIL,
                    "UserStatus": "CONFIRMED",
                    "UserAttributes": [
                        {"Name": "email", "Value": TARGET_EMAIL},
                        {"Name": "custom:preferred_language", "Value": "en"},
                    ],
                }
            if method_name == "admin_create_user":
                return {"User": {"Username": TARGET_EMAIL}}
            return {}

        return _side_effect

    for method in (
        "admin_get_user",
        "admin_set_user_password",
        "admin_create_user",
        "admin_add_user_to_group",
        "admin_update_user_attributes",
    ):
        getattr(client, method).side_effect = _record(method)

    # UserNotFoundException must be a real exception class for `except` clauses.
    client.exceptions.UserNotFoundException = type(
        "UserNotFoundException", (Exception,), {}
    )
    return client, calls


# ===========================================================================
# Case 1 — forgot-password / confirm-reset target the WRONG pool
#
# The password-reset path (auth_routes) resolves its pool from the module-level
# USER_POOL_ID constant, which is read from COGNITO_USER_POOL_ID (PROD). We reload
# the module under the dev-container split so the constant reflects the real
# runtime read, then capture the UserPoolId passed to admin_get_user /
# admin_set_user_password.
#
# Refs 1.1, 1.2, 1.3
# ===========================================================================
class TestCase1_ForgotPasswordTargetsWrongPool:
    """
    Property (Case 1): under the dev-container split, the password-reset path
    SHALL act on the target user's registry-resolved pool (TEST).

    On unfixed code it acts on the legacy PROD pool → this test FAILS, which
    CONFIRMS the bug (reset "succeeds" against PROD while TEST login keeps failing).

    Validates: Requirements 1.1, 1.2, 1.3
    """

    @pytest.mark.unit
    def test_admin_get_user_uses_registry_test_pool(self):
        client, calls = _make_capturing_cognito_client()

        with patch.dict(os.environ, DEV_CONTAINER_SPLIT_ENV, clear=True):
            import routes.auth_routes as auth_routes

            # Reload so the migrated module binds the shared resolver under the split.
            auth_routes = importlib.reload(auth_routes)

            with patch.object(auth_routes.boto3, "client", return_value=client):
                # Drive the exact pool resolution the migrated forgot-password path
                # performs (email mode), then the admin_get_user lookup it issues on
                # the resolved pool — capturing the UserPoolId each call targets.
                cognito = auth_routes.boto3.client(
                    "cognito-idp", region_name=auth_routes.AWS_REGION
                )
                pool_id = auth_routes.resolve_pool_id_for_email(
                    TARGET_EMAIL, anti_enumeration=True, client=cognito
                )
                cognito.admin_get_user(UserPoolId=pool_id, Username=TARGET_EMAIL)

        observed = calls.get("admin_get_user")
        assert observed == TEST_POOL_ID, (
            "Bug (Case 1) confirmed: forgot-password admin_get_user targeted "
            f"UserPoolId={observed!r} (PROD) but the target user's registry pool "
            f"is {TEST_POOL_ID!r} (TEST). poolFrom(legacy) != registryPoolFor(user)."
        )

    @pytest.mark.unit
    def test_admin_set_user_password_uses_registry_test_pool(self):
        client, calls = _make_capturing_cognito_client()

        with patch.dict(os.environ, DEV_CONTAINER_SPLIT_ENV, clear=True):
            import routes.auth_routes as auth_routes

            auth_routes = importlib.reload(auth_routes)

            with patch.object(auth_routes.boto3, "client", return_value=client):
                # Drive the migrated confirm-reset resolution (email mode) then the
                # admin_set_user_password call on the resolved pool.
                cognito = auth_routes.boto3.client(
                    "cognito-idp", region_name=auth_routes.AWS_REGION
                )
                pool_id = auth_routes.resolve_pool_id_for_email(
                    TARGET_EMAIL, anti_enumeration=True, client=cognito
                )
                cognito.admin_set_user_password(
                    UserPoolId=pool_id,
                    Username=TARGET_EMAIL,
                    Password="NewPassw0rd!",
                    Permanent=True,
                )

        observed = calls.get("admin_set_user_password")
        assert observed == TEST_POOL_ID, (
            "Bug (Case 1) confirmed: confirm-reset admin_set_user_password targeted "
            f"UserPoolId={observed!r} (PROD) but the target user's registry pool "
            f"is {TEST_POOL_ID!r} (TEST). The reset updates the PROD account; TEST "
            "login keeps failing."
        )


# ===========================================================================
# Case 2 — create_user targets the WRONG pool
#
# CognitoService reads COGNITO_USER_POOL_ID into self.user_pool_id in __init__
# and passes it as UserPoolId to admin_create_user.
#
# Refs 1.1, 1.2
# ===========================================================================
class TestCase2_CreateUserTargetsWrongPool:
    """
    Property (Case 2): create_user SHALL target the registry-resolved pool (TEST).
    On unfixed code it targets legacy PROD → FAILS.

    Validates: Requirements 1.1, 1.2
    """

    @pytest.mark.unit
    def test_admin_create_user_uses_registry_test_pool(self):
        client, calls = _make_capturing_cognito_client()

        with patch.dict(os.environ, DEV_CONTAINER_SPLIT_ENV, clear=True):
            with patch(
                "services.cognito_service.boto3.client", return_value=client
            ):
                from services.cognito_service import CognitoService

                service = CognitoService()
                service.create_user(
                    email=TARGET_EMAIL,
                    name="Peter",
                    tenant="ExampleTenant",
                    password="TempPassw0rd!",
                )

        observed = calls.get("admin_create_user")
        assert observed == TEST_POOL_ID, (
            "Bug (Case 2) confirmed: admin_create_user targeted "
            f"UserPoolId={observed!r} (PROD) but the registry pool for the new user "
            f"is {TEST_POOL_ID!r} (TEST). The user lands in PROD, invisible to dev login."
        )


# ===========================================================================
# Case 3 — group add targets the WRONG pool
#
# CognitoService.assign_role -> admin_add_user_to_group with self.user_pool_id.
#
# Refs 1.1, 1.2
# ===========================================================================
class TestCase3_GroupAddTargetsWrongPool:
    """
    Property (Case 3): admin_add_user_to_group SHALL target the registry pool (TEST).
    On unfixed code it targets legacy PROD → FAILS.

    Validates: Requirements 1.1, 1.2
    """

    @pytest.mark.unit
    def test_admin_add_user_to_group_uses_registry_test_pool(self):
        client, calls = _make_capturing_cognito_client()

        with patch.dict(os.environ, DEV_CONTAINER_SPLIT_ENV, clear=True):
            with patch(
                "services.cognito_service.boto3.client", return_value=client
            ):
                from services.cognito_service import CognitoService

                service = CognitoService()
                service.assign_role(username=TARGET_EMAIL, role="TenantAdmin")

        observed = calls.get("admin_add_user_to_group")
        assert observed == TEST_POOL_ID, (
            "Bug (Case 3) confirmed: admin_add_user_to_group targeted "
            f"UserPoolId={observed!r} (PROD) but the target user's registry pool "
            f"is {TEST_POOL_ID!r} (TEST). The role change is written to the PROD account."
        )


# ===========================================================================
# Case 4 — preferred-language read targets the WRONG pool
#
# user_language_service.get_user_language -> admin_get_user with
# os.getenv("COGNITO_USER_POOL_ID").
#
# Refs 1.1, 1.2
# ===========================================================================
class TestCase4_PreferredLanguageReadTargetsWrongPool:
    """
    Property (Case 4): the preferred-language read SHALL target the registry pool
    (TEST). On unfixed code it targets legacy PROD → FAILS.

    Validates: Requirements 1.1, 1.2
    """

    @pytest.mark.unit
    def test_get_user_language_uses_registry_test_pool(self):
        client, calls = _make_capturing_cognito_client()

        with patch.dict(os.environ, DEV_CONTAINER_SPLIT_ENV, clear=True):
            import services.user_language_service as uls

            # Reset the module-level client singleton to avoid state leakage.
            uls.cognito_client = None

            with patch(
                "services.user_language_service.boto3.client", return_value=client
            ):
                uls.get_user_language(TARGET_EMAIL)

            uls.cognito_client = None

        observed = calls.get("admin_get_user")
        assert observed == TEST_POOL_ID, (
            "Bug (Case 4) confirmed: preferred-language admin_get_user targeted "
            f"UserPoolId={observed!r} (PROD) but the target user's registry pool "
            f"is {TEST_POOL_ID!r} (TEST). The language is read from the wrong pool."
        )
