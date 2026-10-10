"""
Integration tests — Members tenant sender-identity routes (R0, design §6.2)

Covers the tenant sender path endpoint added in task 0.2:

    POST /api/members/sender-identities   — verify/activate a tenant sender
                                             (drives SES VerifyEmailIdentity)
    GET  /api/members/sender-identities   — read sender verification status

These routes live on the Flask tenant-admin plane and REUSE
``services.email_verification_service.EmailVerificationService`` (the ZZP
sender-verification pattern driving SES ``VerifyEmailIdentity`` /
``GetIdentityVerificationAttributes``). The tests exercise the full edge:
route → service → SES mock → DB mock → response, asserting:

- the ``members:admin`` gate is enforced (401 unauth, 403 no-permission),
- the active tenant is pinned from the auth context into every service call
  (tenant isolation, steering 22/31),
- POST drives SES verification and returns 202 pending,
- GET returns the current/verified status, with the no-record case null (not error).

Reference: .kiro/specs/Members/pivot-output-actions/design.md §6.2, requirements.md R0
"""

import os
import sys
from datetime import datetime
from functools import wraps
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from flask import Flask, jsonify  # noqa: E402

from routes.members_sender_identity_routes import members_sender_identity_bp  # noqa: E402


# ---------------------------------------------------------------------------
# Auth passthrough decorators (mirror test_email_verification_integration.py)
# ---------------------------------------------------------------------------

def _passthrough_cognito(required_roles=None, required_permissions=None):
    """Inject an authenticated tenant-admin caller."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs["user_email"] = "admin@test-tenant.com"
            kwargs["user_roles"] = ["Members_CRUD"]
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant(allow_sysadmin=False):
    """Inject a validated active tenant context."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs["tenant"] = "MembersTestTenant"
            kwargs["user_tenants"] = ["MembersTestTenant"]
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_cognito_no_permission(required_roles=None, required_permissions=None):
    """Simulate a caller lacking the members:admin capability (403)."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            return jsonify(
                {
                    "error": "Insufficient permissions",
                    "details": "Missing permissions: members:admin",
                }
            ), 403
        return wrapper
    return decorator


def _build_client(cognito=_passthrough_cognito):
    """Reload the route module under the given auth decorators, return a client."""
    with patch("auth.cognito_utils.cognito_required", side_effect=cognito), patch(
        "auth.tenant_context.tenant_required", side_effect=_passthrough_tenant
    ):
        import importlib

        import routes.members_sender_identity_routes as mod

        importlib.reload(mod)

        app = Flask(__name__)
        app.config["TESTING"] = True
        app.register_blueprint(mod.members_sender_identity_bp)
        return app.test_client(), mod


# ---------------------------------------------------------------------------
# GET /api/members/sender-identities
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestGetSenderIdentity:
    def test_get_status_returns_verified(self):
        """GET returns the resolved sender + verified status for the active tenant."""
        client, mod = _build_client()
        mock_service = MagicMock()
        mock_service.check_status.return_value = {
            "email": "sender@tenant.example",
            "status": "verified",
            "last_checked": "2026-01-15T10:30:00Z",
        }

        with patch.object(mod, "DatabaseManager"), patch.object(
            mod, "EmailVerificationService", return_value=mock_service
        ):
            resp = client.get("/api/members/sender-identities")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["email"] == "sender@tenant.example"
        assert data["data"]["status"] == "verified"
        # Tenant is pinned from the auth context, never the request.
        mock_service.check_status.assert_called_once_with("MembersTestTenant")

    def test_get_status_no_sender_returns_null_not_error(self):
        """A tenant without a sender yet returns null email/status at 200 (not 500)."""
        client, mod = _build_client()
        mock_service = MagicMock()
        mock_service.check_status.return_value = {
            "email": None,
            "status": None,
            "last_checked": None,
        }

        with patch.object(mod, "DatabaseManager"), patch.object(
            mod, "EmailVerificationService", return_value=mock_service
        ):
            resp = client.get("/api/members/sender-identities")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["email"] is None
        assert data["data"]["status"] is None

    def test_get_status_service_error_returns_500(self):
        """An unexpected service failure surfaces as a bodied 500 (API standard)."""
        client, mod = _build_client()
        mock_service = MagicMock()
        mock_service.check_status.side_effect = RuntimeError("boom")

        with patch.object(mod, "DatabaseManager"), patch.object(
            mod, "EmailVerificationService", return_value=mock_service
        ):
            resp = client.get("/api/members/sender-identities")

        assert resp.status_code == 500
        data = resp.get_json()
        assert data["success"] is False
        assert "error" in data


# ---------------------------------------------------------------------------
# POST /api/members/sender-identities
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCreateSenderIdentity:
    def test_post_initiates_verification_returns_202_pending(self):
        """POST drives SES verification via the service and returns 202 pending."""
        client, mod = _build_client()
        mock_service = MagicMock()
        mock_service.update_email.return_value = {
            "success": True,
            "status": "pending",
            "error": None,
        }

        with patch.object(mod, "DatabaseManager"), patch.object(
            mod, "EmailVerificationService", return_value=mock_service
        ):
            resp = client.post(
                "/api/members/sender-identities",
                json={"email": "new-sender@tenant.example"},
                content_type="application/json",
            )

        assert resp.status_code == 202
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["email"] == "new-sender@tenant.example"
        assert data["data"]["status"] == "pending"
        # Tenant pinned from auth context; email taken from the body.
        mock_service.update_email.assert_called_once_with(
            "MembersTestTenant", "new-sender@tenant.example"
        )

    def test_post_missing_email_returns_400(self):
        """POST without an email is rejected 400 before any service/SES call."""
        client, mod = _build_client()
        mock_service = MagicMock()

        with patch.object(mod, "DatabaseManager"), patch.object(
            mod, "EmailVerificationService", return_value=mock_service
        ):
            resp = client.post(
                "/api/members/sender-identities",
                json={},
                content_type="application/json",
            )

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        mock_service.update_email.assert_not_called()

    def test_post_invalid_email_surfaces_service_error_400(self):
        """A service-rejected address (bad format / SES reject) returns 400 bodied."""
        client, mod = _build_client()
        mock_service = MagicMock()
        mock_service.update_email.return_value = {
            "success": False,
            "status": "failed",
            "error": "Invalid email format",
        }

        with patch.object(mod, "DatabaseManager"), patch.object(
            mod, "EmailVerificationService", return_value=mock_service
        ):
            resp = client.post(
                "/api/members/sender-identities",
                json={"email": "not-an-email"},
                content_type="application/json",
            )

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert data["error"] == "Invalid email format"

    def test_post_end_to_end_drives_ses_verify(self):
        """Full edge: route → real service → SES mock gets VerifyEmailIdentity."""
        client, mod = _build_client()

        mock_db = MagicMock()
        mock_db.execute_query.return_value = []  # no existing records
        mock_ses = MagicMock()
        mock_ses.verify_email_identity.return_value = {}

        with patch.object(mod, "DatabaseManager", return_value=mock_db), patch(
            "services.email_verification_service.boto3.client", return_value=mock_ses
        ):
            resp = client.post(
                "/api/members/sender-identities",
                json={"email": "e2e-sender@tenant.example"},
                content_type="application/json",
            )

        assert resp.status_code == 202
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "pending"
        mock_ses.verify_email_identity.assert_called_once_with(
            EmailAddress="e2e-sender@tenant.example"
        )
        # Old records marked replaced before initiating the new one.
        replaced_calls = [
            c
            for c in mock_db.execute_query.call_args_list
            if c[0] and "status = 'replaced'" in str(c[0][0])
        ]
        assert replaced_calls, "expected the active sender to be replaced on POST"


# ---------------------------------------------------------------------------
# Authorization gate (members:admin)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSenderIdentityAuthGate:
    def test_unauthenticated_get_returns_401(self):
        """No auth bypass: the real cognito gate rejects an unauthenticated GET."""
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.register_blueprint(members_sender_identity_bp)
        resp = app.test_client().get("/api/members/sender-identities")
        assert resp.status_code == 401

    def test_no_permission_get_returns_403(self):
        """A caller lacking members:admin is rejected 403."""
        client, _mod = _build_client(cognito=_passthrough_cognito_no_permission)
        resp = client.get("/api/members/sender-identities")
        assert resp.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
