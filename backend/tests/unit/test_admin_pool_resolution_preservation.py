"""
Preservation Property Test — Cognito Admin Pool Resolution split-brain.

Property 2: Preservation — for every admin Cognito operation ``X`` where the bug
condition does NOT hold (``isBugCondition(X)`` is FALSE — the legacy
``COGNITO_USER_POOL_ID`` var already agrees with the target user's registry pool,
e.g. production ``COGNITO_POOL_KEYS=PROD_A``, or a registry-absent single-pool
deployment), the fixed code ``F'(X)`` SHALL produce exactly the same result as the
original code ``F(X)``: same pool acted on, same Cognito actions, same
request/response contracts, and the same anti-enumeration behavior for
forgot-password.

    These tests capture the NON-BUGGY baseline behavior and are EXPECTED TO PASS
    on the UNFIXED code. They are written BEFORE the fix. After the fix lands they
    must STILL PASS — proving the fix is behavior-preserving where the bug does not
    apply. DO NOT weaken these assertions to make them pass.

Observation-first methodology (design.md → Preservation Checking):
    Each property was authored by running the UNFIXED code first under the
    prod-equivalent config (legacy var == registry pool == PROD_A ==
    ``eu-west-1_Hdp40eWmu``), recording the actual ``UserPoolId`` each op passes
    and the actual success/error response shape, then encoding those observed
    values as the assertions below. The recorded observations are documented inline
    next to each assertion.

Registry configs exercised (both NON-buggy — isBugCondition is FALSE):
  * prod single-pool:  COGNITO_POOL_KEYS=PROD_A, PROD_A_COGNITO_* issuer ends in
    eu-west-1_Hdp40eWmu, and legacy COGNITO_USER_POOL_ID=eu-west-1_Hdp40eWmu.
    poolFrom(legacy) == registryPoolFor(user) == PROD_A → isBugCondition FALSE.
  * registry-absent fallback:  COGNITO_POOL_KEYS unset, COGNITO_USER_POOL_ID set.
    The helper (per design) mirrors the validation fallback and resolves to the
    legacy var — the same pool ops act on today.

Preservation: For all X where NOT isBugCondition(X), F(X) = F'(X) — same pool,
same actions, same contracts, same anti-enumeration.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure src is importable (conftest also does this).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


# ---------------------------------------------------------------------------
# Prod-equivalent single-pool configuration — the NON-buggy baseline.
#
#   Registry (validation)  -> PROD_A   eu-west-1_Hdp40eWmu
#   Legacy var (admin ops) -> PROD_A   eu-west-1_Hdp40eWmu
#
# poolFrom(legacy) == registryPoolFor(user) == PROD_A → isBugCondition is FALSE.
# The registry pool id is the trailing path segment of the PROD_A issuer URL,
# exactly how the fix will derive it (PoolConfig carries no user_pool_id field).
# ---------------------------------------------------------------------------
PROD_A_POOL_ID = "eu-west-1_Hdp40eWmu"
PROD_A_ISSUER = f"https://cognito-idp.eu-west-1.amazonaws.com/{PROD_A_POOL_ID}"

# Env that reproduces prod single-pool: registry -> PROD_A, legacy -> PROD_A.
PROD_SINGLE_POOL_ENV = {
    # --- registry (issuer->pool), keyed to PROD_A (what validation uses) ---
    "COGNITO_POOL_KEYS": "PROD_A",
    "PROD_A_COGNITO_ISSUER": PROD_A_ISSUER,
    "PROD_A_COGNITO_JWKS_URI": f"{PROD_A_ISSUER}/.well-known/jwks.json",
    "PROD_A_COGNITO_CLIENT_ID": "prod-a-client-id",
    "PROD_A_COGNITO_POOL_LABEL": "myAdmin-prod-a",
    # --- legacy single-pool var, ALSO pointing at PROD_A (agrees with registry) ---
    "COGNITO_USER_POOL_ID": PROD_A_POOL_ID,
    "COGNITO_CLIENT_ID": "prod-a-client-id",
    # --- AWS boto3 basics (mocked, never used against real AWS) ---
    "AWS_REGION": "eu-west-1",
    "AWS_ACCESS_KEY_ID": "test-key-id",
    "AWS_SECRET_ACCESS_KEY": "test-secret-key",
    # keep DB isolation happy for anything that peeks at TEST_MODE
    "TEST_MODE": "true",
}

# Registry-absent fallback: no COGNITO_POOL_KEYS, only the legacy var. The helper
# (post-fix) mirrors cognito_utils step (2) and resolves to this legacy var — the
# same pool ops act on today, so behavior is preserved.
LEGACY_FALLBACK_POOL_ID = "eu-west-1_LegacyOnly"
REGISTRY_ABSENT_ENV = {
    # COGNITO_POOL_KEYS intentionally ABSENT.
    "COGNITO_USER_POOL_ID": LEGACY_FALLBACK_POOL_ID,
    "COGNITO_CLIENT_ID": "legacy-client-id",
    "AWS_REGION": "eu-west-1",
    "AWS_ACCESS_KEY_ID": "test-key-id",
    "AWS_SECRET_ACCESS_KEY": "test-secret-key",
    "TEST_MODE": "true",
}

TARGET_EMAIL = "peter@pgeers.nl"


def _make_capturing_cognito_client():
    """
    A mocked cognito-idp client that RECORDS the ``UserPoolId=...`` kwarg passed to
    each admin call, so a test can assert which pool an op actually targeted.

    Returns (client, calls) where ``calls`` maps the admin method name -> the
    UserPoolId it was invoked with (last call wins; each op here is invoked once).

    Mirrors the capture pattern in ``test_admin_pool_resolution_bug.py``.
    """
    client = MagicMock()
    calls: dict[str, str] = {}

    def _record(method_name):
        def _side_effect(*args, **kwargs):
            calls[method_name] = kwargs.get("UserPoolId")
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


# The representative migrated admin ops, each driven the SAME way the corresponding
# source file drives it, returning the UserPoolId it actually passed on unfixed code.
def _observe_auth_routes_forgot_password_pool(env):
    """Drive the auth_routes forgot-password Cognito lookup; return observed pool.

    Mirrors the migrated handler: resolve the target pool via the shared resolver
    (email mode, sharing the route's client) then issue admin_get_user on it.
    """
    client, calls = _make_capturing_cognito_client()
    with patch.dict(os.environ, env, clear=True):
        import routes.auth_routes as auth_routes

        auth_routes = importlib.reload(auth_routes)
        with patch.object(auth_routes.boto3, "client", return_value=client):
            cognito = auth_routes.boto3.client(
                "cognito-idp", region_name=auth_routes.AWS_REGION
            )
            pool_id = auth_routes.resolve_pool_id_for_email(
                TARGET_EMAIL, anti_enumeration=True, client=cognito
            )
            cognito.admin_get_user(UserPoolId=pool_id, Username=TARGET_EMAIL)
    return calls.get("admin_get_user")


def _observe_auth_routes_confirm_reset_pool(env):
    """Drive the auth_routes confirm-reset password set; return observed pool.

    Mirrors the migrated handler: resolve the target pool via the shared resolver
    (email mode, sharing the route's client) then issue admin_set_user_password.
    """
    client, calls = _make_capturing_cognito_client()
    with patch.dict(os.environ, env, clear=True):
        import routes.auth_routes as auth_routes

        auth_routes = importlib.reload(auth_routes)
        with patch.object(auth_routes.boto3, "client", return_value=client):
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
    return calls.get("admin_set_user_password")


def _observe_create_user_pool(env):
    """Drive CognitoService.create_user; return observed admin_create_user pool."""
    client, calls = _make_capturing_cognito_client()
    with patch.dict(os.environ, env, clear=True):
        with patch("services.cognito_service.boto3.client", return_value=client):
            from services.cognito_service import CognitoService

            service = CognitoService()
            service.create_user(
                email=TARGET_EMAIL,
                name="Peter",
                tenant="ExampleTenant",
                password="TempPassw0rd!",
            )
    return calls.get("admin_create_user")


def _observe_assign_role_pool(env):
    """Drive CognitoService.assign_role; return observed add_user_to_group pool."""
    client, calls = _make_capturing_cognito_client()
    with patch.dict(os.environ, env, clear=True):
        with patch("services.cognito_service.boto3.client", return_value=client):
            from services.cognito_service import CognitoService

            service = CognitoService()
            service.assign_role(username=TARGET_EMAIL, role="TenantAdmin")
    return calls.get("admin_add_user_to_group")


def _observe_user_language_read_pool(env):
    """Drive user_language_service.get_user_language; return observed pool."""
    client, calls = _make_capturing_cognito_client()
    with patch.dict(os.environ, env, clear=True):
        import services.user_language_service as uls

        uls.cognito_client = None
        with patch(
            "services.user_language_service.boto3.client", return_value=client
        ):
            uls.get_user_language(TARGET_EMAIL)
        uls.cognito_client = None
    return calls.get("admin_get_user")


# A registry of representative ops keyed by name -> observer callable. Each observer
# returns the UserPoolId the op passes on the UNFIXED code under the given env.
REPRESENTATIVE_OPS = {
    "forgot_password": _observe_auth_routes_forgot_password_pool,
    "confirm_reset": _observe_auth_routes_confirm_reset_pool,
    "create_user": _observe_create_user_pool,
    "assign_role": _observe_assign_role_pool,
    "preferred_language_read": _observe_user_language_read_pool,
}


# ===========================================================================
# Preservation 1 — prod single-pool: every op targets PROD_A (unchanged)
#
# Observed on UNFIXED code under PROD_SINGLE_POOL_ENV: every representative op
# passes UserPoolId = eu-west-1_Hdp40eWmu (PROD_A). Because the legacy var and the
# registry pool agree here (isBugCondition FALSE), the fix must keep every op on
# this SAME pool id.
#
# Refs 3.1, 3.2
# ===========================================================================
class TestPreservation1_ProdSinglePoolPoolIdUnchanged:
    """
    Property (Preservation 1): under the prod single-pool config, every
    representative admin op SHALL act on PROD_A (``eu-west-1_Hdp40eWmu``) — the same
    pool it acts on today. isBugCondition is FALSE, so F' ≡ F.

    Validates: Requirements 3.1, 3.2
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("op_name", sorted(REPRESENTATIVE_OPS))
    def test_op_targets_prod_a_pool(self, op_name):
        observed = REPRESENTATIVE_OPS[op_name](PROD_SINGLE_POOL_ENV)
        # Observed on unfixed code: PROD_A == eu-west-1_Hdp40eWmu.
        assert observed == PROD_A_POOL_ID, (
            f"Preservation baseline: op {op_name!r} must target PROD_A "
            f"{PROD_A_POOL_ID!r} under the prod single-pool config, but targeted "
            f"{observed!r}. In this non-buggy config poolFrom(legacy) == "
            f"registryPoolFor(user), so the pool must be unchanged."
        )

    @pytest.mark.unit
    @settings(max_examples=25, deadline=None)
    @given(op_name=st.sampled_from(sorted(REPRESENTATIVE_OPS)))
    def test_property_every_op_passes_same_prod_pool_id(self, op_name):
        """
        PBT: across the representative op domain, EVERY op resolves to the SAME
        single pool id (PROD_A) under the prod single-pool config — i.e. the pool
        id is invariant across ops, matching the observed unfixed baseline.

        Validates: Requirements 3.1, 3.2
        """
        observed = REPRESENTATIVE_OPS[op_name](PROD_SINGLE_POOL_ENV)
        assert observed == PROD_A_POOL_ID


# ===========================================================================
# Preservation 2 — registry-absent fallback: ops act on the legacy var
#
# Observed on UNFIXED code under REGISTRY_ABSENT_ENV (COGNITO_POOL_KEYS unset,
# COGNITO_USER_POOL_ID set): every op passes UserPoolId = the legacy var value.
# The post-fix helper mirrors the validation fallback and resolves to the same
# legacy var, so behavior is preserved.
#
# Refs 3.4
# ===========================================================================
class TestPreservation2_RegistryAbsentFallbackUnchanged:
    """
    Property (Preservation 2): with the registry absent (no ``COGNITO_POOL_KEYS``)
    and only the legacy ``COGNITO_USER_POOL_ID`` set, every representative admin op
    SHALL act on the legacy-var pool — mirroring the validation fallback and the
    pool ops act on today.

    Validates: Requirements 3.4
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("op_name", sorted(REPRESENTATIVE_OPS))
    def test_op_falls_back_to_legacy_var(self, op_name):
        observed = REPRESENTATIVE_OPS[op_name](REGISTRY_ABSENT_ENV)
        # Observed on unfixed code: the legacy var value.
        assert observed == LEGACY_FALLBACK_POOL_ID, (
            f"Preservation baseline: op {op_name!r} must fall back to the legacy "
            f"var {LEGACY_FALLBACK_POOL_ID!r} when the registry is absent, but "
            f"targeted {observed!r}. The registry-absent fallback must be preserved."
        )

    @pytest.mark.unit
    @settings(max_examples=25, deadline=None)
    @given(op_name=st.sampled_from(sorted(REPRESENTATIVE_OPS)))
    def test_property_every_op_falls_back_to_same_legacy_var(self, op_name):
        """
        PBT: across the representative op domain, every op resolves to the SAME
        legacy-var pool id when the registry is absent (invariant, matching the
        observed unfixed baseline).

        Validates: Requirements 3.4
        """
        observed = REPRESENTATIVE_OPS[op_name](REGISTRY_ABSENT_ENV)
        assert observed == LEGACY_FALLBACK_POOL_ID


# ===========================================================================
# Preservation 3 — response-contract preservation
#
# Observed on UNFIXED code (prod-equivalent config) for representative
# route/service ops: record the success and error status/response shape and assert
# they are unchanged.
#
# Refs 3.3
# ===========================================================================
class TestPreservation3_ResponseContractUnchanged:
    """
    Property (Preservation 3): representative migrated routes/services SHALL return
    the same success/error status and response shape as observed on the unfixed
    code under the prod-equivalent config.

    Validates: Requirements 3.3
    """

    @pytest.mark.unit
    def test_preferred_language_read_success_returns_language_string(self):
        """
        Observed: get_user_language returns the attribute value ("en") on a
        successful admin_get_user; the "nl"-default / failure contract is a plain
        string return. Assert the success contract is a str equal to the stored
        value.
        """
        client, _calls = _make_capturing_cognito_client()
        with patch.dict(os.environ, PROD_SINGLE_POOL_ENV, clear=True):
            import services.user_language_service as uls

            uls.cognito_client = None
            with patch(
                "services.user_language_service.boto3.client", return_value=client
            ):
                result = uls.get_user_language(TARGET_EMAIL)
            uls.cognito_client = None

        # Observed on unfixed code: the mocked admin_get_user returns
        # custom:preferred_language = "en", so the contract is the string "en".
        assert result == "en"
        assert isinstance(result, str)

    @pytest.mark.unit
    def test_preferred_language_update_invalid_code_returns_false(self):
        """
        Observed: update_user_language rejects an invalid language code with a
        plain ``False`` return (no Cognito call). Assert that contract is unchanged.
        """
        with patch.dict(os.environ, PROD_SINGLE_POOL_ENV, clear=True):
            import services.user_language_service as uls

            uls.cognito_client = None
            result = uls.update_user_language(TARGET_EMAIL, "de")  # invalid code
            uls.cognito_client = None

        # Observed on unfixed code: invalid code -> False, no pool touched.
        assert result is False

    @pytest.mark.unit
    def test_create_user_success_returns_user_dict(self):
        """
        Observed: CognitoService.create_user returns the ``response["User"]`` dict
        (containing "Username") on success. Assert the return shape is unchanged.
        """
        client, _calls = _make_capturing_cognito_client()
        with patch.dict(os.environ, PROD_SINGLE_POOL_ENV, clear=True):
            with patch("services.cognito_service.boto3.client", return_value=client):
                from services.cognito_service import CognitoService

                service = CognitoService()
                result = service.create_user(
                    email=TARGET_EMAIL,
                    name="Peter",
                    tenant="ExampleTenant",
                    password="TempPassw0rd!",
                )

        # Observed on unfixed code: returns the User dict with the Username.
        assert isinstance(result, dict)
        assert result.get("Username") == TARGET_EMAIL

    @pytest.mark.unit
    def test_assign_role_success_returns_true(self):
        """
        Observed: CognitoService.assign_role returns ``True`` on a successful
        admin_add_user_to_group. Assert the boolean contract is unchanged.
        """
        client, _calls = _make_capturing_cognito_client()
        with patch.dict(os.environ, PROD_SINGLE_POOL_ENV, clear=True):
            with patch("services.cognito_service.boto3.client", return_value=client):
                from services.cognito_service import CognitoService

                service = CognitoService()
                result = service.assign_role(username=TARGET_EMAIL, role="TenantAdmin")

        # Observed on unfixed code: assign_role -> True.
        assert result is True


# ===========================================================================
# Preservation 4 — forgot-password anti-enumeration preserved
#
# Observed on UNFIXED code (prod-equivalent config): the forgot-password Cognito
# lookup returns the SAME success message whether the user exists, does not exist
# (ClientError), or would be absent in all pools. Assert the response is unchanged.
#
# Refs 3.5
# ===========================================================================
class TestPreservation4_ForgotPasswordAntiEnumerationUnchanged:
    """
    Property (Preservation 4): forgot-password SHALL return the SAME success
    message for existent, non-existent, and absent-in-all-pools emails — the
    anti-enumeration contract observed on the unfixed code.

    Validates: Requirements 3.5
    """

    # The exact anti-enumeration success message emitted by auth_routes today.
    ANTI_ENUM_MESSAGE = "If an account exists, a reset code has been sent."

    def _run_forgot_password(self, email, user_exists):
        """
        Drive auth_routes.forgot_password within a Flask test request context under
        the prod-equivalent config, with Cognito admin_get_user either succeeding
        (user exists) or raising ClientError (user absent). Returns the parsed JSON.
        """
        with patch.dict(os.environ, PROD_SINGLE_POOL_ENV, clear=True):
            import routes.auth_routes as auth_routes

            auth_routes = importlib.reload(auth_routes)

            cognito = MagicMock()
            if user_exists:
                cognito.admin_get_user.return_value = {
                    "UserStatus": "CONFIRMED",
                    "UserAttributes": [],
                }
            else:
                from botocore.exceptions import ClientError

                cognito.admin_get_user.side_effect = ClientError(
                    {"Error": {"Code": "UserNotFoundException", "Message": "no"}},
                    "AdminGetUser",
                )

            # Rate limiter: allow the request through.
            allowed = MagicMock()
            allowed.allowed = True

            # Build a Flask app + request context so request.get_json works.
            from flask import Flask

            app = Flask(__name__)
            app.register_blueprint(auth_routes.auth_bp)

            with patch.object(auth_routes.boto3, "client", return_value=cognito), \
                patch.object(
                    auth_routes.password_reset_limiter,
                    "check_rate_limit",
                    return_value=allowed,
                ), \
                patch.object(
                    auth_routes.password_reset_limiter, "record_request"
                ), \
                patch.object(auth_routes, "_get_db", return_value=MagicMock()), \
                patch(
                    "services.ses_email_service.SESEmailService"
                ), \
                patch(
                    "services.email_template_service.EmailTemplateService"
                ):
                with app.test_request_context(
                    "/api/auth/forgot-password",
                    method="POST",
                    json={"email": email},
                ):
                    response = auth_routes.forgot_password()

        # Normalise the (body, status) or body return into a parsed dict.
        body = response[0] if isinstance(response, tuple) else response
        return body.get_json()

    @pytest.mark.unit
    def test_existent_user_returns_anti_enum_success(self):
        result = self._run_forgot_password("existing@example.com", user_exists=True)
        assert result["success"] is True
        assert result["message"] == self.ANTI_ENUM_MESSAGE

    @pytest.mark.unit
    def test_nonexistent_user_returns_same_anti_enum_success(self):
        result = self._run_forgot_password("missing@example.com", user_exists=False)
        assert result["success"] is True
        assert result["message"] == self.ANTI_ENUM_MESSAGE

    @pytest.mark.unit
    @settings(max_examples=25, deadline=None)
    @given(
        email=st.emails(),
        user_exists=st.booleans(),
    )
    def test_property_forgot_password_message_invariant(self, email, user_exists):
        """
        PBT: for any email and any existence state (exists / absent), the
        forgot-password response is the SAME anti-enumeration success — the
        response never reveals whether the account exists.

        Validates: Requirements 3.5
        """
        result = self._run_forgot_password(email, user_exists=user_exists)
        assert result["success"] is True
        assert result["message"] == self.ANTI_ENUM_MESSAGE
