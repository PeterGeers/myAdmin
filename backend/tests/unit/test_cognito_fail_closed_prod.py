"""
H1 (risk F1) — Fail closed on JWT verification in production.

`cognito_utils` supports an UNSIGNED base64 token fallback (`_extract_with_base64`)
for local dev / tests when no Cognito verifier is configured. That fallback trusts
an attacker-forgeable `cognito:groups` claim, so it must be IMPOSSIBLE in production
(or wherever `REQUIRE_JWT_VERIFICATION=true`).

These tests pin the H1 contract:

  * production + NO Cognito env  -> extract_user_credentials must FAIL CLOSED (503),
    never decode/accept the unsigned token (no email/roles leak through).
  * REQUIRE_JWT_VERIFICATION=true + NO Cognito env -> same fail-closed 503.
  * off-production + NO Cognito env -> the base64 dev/test fallback still works
    (backward compatible: a decoded identity is returned).
  * with a configured verifier -> a validly-verified token still passes (the guard
    only fires when the verifier is genuinely absent).

No real network, no DB. Env is controlled with `patch.dict` and the module
singleton is reset between tests.

**Validates: Requirements — Security Assessment 2026-09-26 task H1 (risk F1)**
"""

import base64
import json
import os
from unittest.mock import patch

import pytest

from auth.cognito_utils import extract_user_credentials


def _unsigned_token(payload: dict) -> str:
    """Build a JWT-shaped, UNSIGNED token (header.payload.signature) an attacker
    could trivially forge — the base64 fallback would otherwise trust its payload."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode())
        .decode()
        .rstrip("=")
    )
    body = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    return f"{header}.{body}.forged_signature"


def _event_with(token: str) -> dict:
    return {"headers": {"Authorization": f"Bearer {token}"}}


# A forged admin identity — what an attacker would try to smuggle in.
FORGED_PAYLOAD = {
    "email": "attacker@evil.example",
    "cognito:groups": ["Administrators"],
}


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the verifier singleton so each test re-runs selection logic fresh."""
    import auth.cognito_utils as cu

    cu._jwt_verifier_instance = None
    cu._jwt_verifier_init_attempted = False
    yield
    cu._jwt_verifier_instance = None
    cu._jwt_verifier_init_attempted = False


class TestFailClosedInProduction:
    """RAILWAY_ENVIRONMENT=production + no verifier => 503, never a decoded identity."""

    def test_production_no_cognito_rejects_unsigned_token(self):
        token = _unsigned_token(FORGED_PAYLOAD)
        with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"}, clear=True):
            email, roles, error = extract_user_credentials(_event_with(token))

        # No identity may leak through, and it must be an error response.
        assert email is None
        assert roles is None
        assert error is not None
        assert error["statusCode"] == 503
        # Explicitly: the forged admin identity was NOT accepted.
        assert "Administrators" not in (roles or [])

    def test_production_case_insensitive(self):
        token = _unsigned_token(FORGED_PAYLOAD)
        with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "Production"}, clear=True):
            email, roles, error = extract_user_credentials(_event_with(token))

        assert email is None
        assert error is not None
        assert error["statusCode"] == 503

    def test_require_flag_forces_fail_closed_off_production(self):
        """REQUIRE_JWT_VERIFICATION=true fails closed even when not production."""
        token = _unsigned_token(FORGED_PAYLOAD)
        env = {"REQUIRE_JWT_VERIFICATION": "true"}  # no RAILWAY_ENVIRONMENT
        with patch.dict(os.environ, env, clear=True):
            email, roles, error = extract_user_credentials(_event_with(token))

        assert email is None
        assert roles is None
        assert error is not None
        assert error["statusCode"] == 503


class TestDevFallbackStillWorks:
    """Off-production + no verifier => the base64 dev/test fallback is preserved."""

    def test_non_production_no_cognito_accepts_base64_token(self):
        payload = {
            "email": "dev@example.com",
            "cognito:groups": ["Finance_Read"],
        }
        token = _unsigned_token(payload)
        # No RAILWAY_ENVIRONMENT, no REQUIRE_JWT_VERIFICATION, no Cognito vars.
        with patch.dict(os.environ, {}, clear=True):
            email, roles, error = extract_user_credentials(_event_with(token))

        assert error is None
        assert email == "dev@example.com"
        assert roles == ["Finance_Read"]

    def test_staging_is_not_production(self):
        """A non-'production' RAILWAY_ENVIRONMENT keeps the dev fallback."""
        payload = {"email": "dev@example.com", "cognito:groups": ["Finance_Read"]}
        token = _unsigned_token(payload)
        with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "staging"}, clear=True):
            email, roles, error = extract_user_credentials(_event_with(token))

        assert error is None
        assert email == "dev@example.com"


class TestConfiguredVerifierStillPasses:
    """With a verifier configured, a validly-verified token passes (guard is inert)."""

    def test_production_with_verifier_accepts_verified_token(self):
        verified_payload = {
            "email": "user@example.com",
            "cognito:groups": ["Finance_Read"],
        }

        class _StubVerifier:
            def verify_token(self, _token):
                return verified_payload

        env = {"RAILWAY_ENVIRONMENT": "production"}
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "auth.cognito_utils._get_jwt_verifier",
                return_value=_StubVerifier(),
            ):
                email, roles, error = extract_user_credentials(
                    _event_with("any.jwt.token")
                )

        assert error is None
        assert email == "user@example.com"
        assert roles == ["Finance_Read"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
