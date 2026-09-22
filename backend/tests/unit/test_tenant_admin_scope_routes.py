"""
Tests for the Tenant-Admin member-scope authoring routes (s5d task 5.2).

Covers ``tenant_admin_scope.py``:
- GET returns the user's current scopes (empty when none).
- PUT atomic-overwrites and returns the normalized grant.
- PUT unknown dimension/value -> 400 (service raises ScopeValidationError).
- PUT clearing all -> row deleted (service returns {} -> route echoes {}).
- GET scope-dimensions returns enabled dims + canonical values from the MySQL param.
- Tenant isolation: a caller without access to the tenant -> 403; a body tenant_id
  can never redirect the write (tenant comes from the verified context).
- Module normalization: path 'members' -> stored/canonical 'MEMBERS'.
- Unknown module -> 404.

The routes are a THIN wrapper over UserTenantScopeService (task 5.1); these tests
patch the service + ParameterService at the route module level so they exercise the
route wiring (auth, tenant/user resolution, module normalization, error mapping)
without touching AWS/MySQL (steering 34 isolation).
"""

import base64
import json
from unittest.mock import Mock, patch

import pytest
from flask import Flask

from routes.tenant_admin_scope import tenant_admin_scope_bp
from services.user_tenant_scope_service import ScopeValidationError


def _make_jwt(payload):
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode())
        .decode()
        .rstrip("=")
    )
    body = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    return f"{header}.{body}.mock_signature"


JWT_ADMIN = _make_jwt(
    {
        "email": "admin@example.com",
        "cognito:groups": ["Tenant_Admin"],
        "custom:tenants": '["TenantA", "TenantB"]',
        "exp": 9999999999,
    }
)


@pytest.fixture(autouse=True)
def no_jwt_verifier():
    """Force the base64 JWT fallback so the mock token is accepted.

    In an environment where Cognito env vars are configured, ``cognito_required``
    would cryptographically verify the token and reject our mock JWT (401). Unit
    tests exercise the ROUTE logic, not JWT crypto, so we disable the verifier
    singleton and let ``extract_user_credentials`` decode the unverified payload
    (the same fallback used in local dev / verifier-less CI).
    """
    with patch("auth.cognito_utils._get_jwt_verifier", return_value=None), patch(
        "auth.cognito_utils.get_verified_tenants", return_value=None
    ):
        yield


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(tenant_admin_scope_bp)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def mock_cognito():
    with patch("routes.tenant_admin_scope.cognito_client") as mock:
        mock.admin_get_user.return_value = {
            "UserAttributes": [
                {"Name": "email", "Value": "user@example.com"},
                {"Name": "name", "Value": "Test User"},
                {"Name": "custom:tenants", "Value": '["TenantA"]'},
            ]
        }
        yield mock


@pytest.fixture
def mock_scope_service():
    """Patch the scope-service factory so no real DB/ParameterService is built."""
    svc = Mock()
    with patch(
        "routes.tenant_admin_scope._build_scope_service", return_value=svc
    ):
        yield svc


def _auth_headers(tenant="TenantA", json_body=False):
    headers = {
        "Authorization": f"Bearer {JWT_ADMIN}",
        "X-Tenant": tenant,
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


# The decorator resolves per-tenant roles from the DB; patch it to grant Tenant_Admin.
def _tenant_admin_role_patch():
    return patch("auth.role_cache.get_tenant_roles", return_value=["Tenant_Admin"])


class TestGetUserScope:
    def test_get_returns_current_scopes(self, app, mock_cognito, mock_scope_service):
        mock_scope_service.get_scope.return_value = {"region": ["Oost"]}
        with _tenant_admin_role_patch():
            with app.test_client() as client:
                resp = client.get(
                    "/api/tenant-admin/users/user@example.com/scope/members",
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["scopes"] == {"region": ["Oost"]}
        assert body["module"] == "MEMBERS"
        # tenant + canonical module + resolved email flow to the service
        mock_scope_service.get_scope.assert_called_once_with(
            "user@example.com", "TenantA", "MEMBERS"
        )

    def test_get_empty_when_no_grant(self, app, mock_cognito, mock_scope_service):
        mock_scope_service.get_scope.return_value = {}
        with _tenant_admin_role_patch():
            with app.test_client() as client:
                resp = client.get(
                    "/api/tenant-admin/users/user@example.com/scope/members",
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200
        assert resp.get_json()["scopes"] == {}


class TestSetUserScope:
    def test_put_atomic_overwrite_returns_normalized(
        self, app, mock_cognito, mock_scope_service
    ):
        mock_scope_service.set_scope.return_value = {"region": ["Oost", "Friesland"]}
        with _tenant_admin_role_patch():
            with app.test_client() as client:
                resp = client.put(
                    "/api/tenant-admin/users/user@example.com/scope/members",
                    headers=_auth_headers(json_body=True),
                    json={"scopes": {"region": ["oost", "friesland"]}},
                )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["scopes"] == {"region": ["Oost", "Friesland"]}
        # canonical module stored; created_by is the acting admin
        mock_scope_service.set_scope.assert_called_once_with(
            "user@example.com",
            "TenantA",
            "MEMBERS",
            {"region": ["oost", "friesland"]},
            created_by="admin@example.com",
        )

    def test_put_unknown_dimension_or_value_returns_400(
        self, app, mock_cognito, mock_scope_service
    ):
        mock_scope_service.set_scope.side_effect = ScopeValidationError(
            "Unknown value 'Mars' for scope dimension 'region'"
        )
        with _tenant_admin_role_patch():
            with app.test_client() as client:
                resp = client.put(
                    "/api/tenant-admin/users/user@example.com/scope/members",
                    headers=_auth_headers(json_body=True),
                    json={"scopes": {"region": ["Mars"]}},
                )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert "Mars" in body["error"]

    def test_put_clearing_all_deletes_row_returns_empty(
        self, app, mock_cognito, mock_scope_service
    ):
        # Service returns {} when the grant clears to empty (row deleted -> deny).
        mock_scope_service.set_scope.return_value = {}
        with _tenant_admin_role_patch():
            with app.test_client() as client:
                resp = client.put(
                    "/api/tenant-admin/users/user@example.com/scope/members",
                    headers=_auth_headers(json_body=True),
                    json={"scopes": {"region": []}},
                )
        assert resp.status_code == 200
        assert resp.get_json()["scopes"] == {}

    def test_put_missing_scopes_body_returns_400(
        self, app, mock_cognito, mock_scope_service
    ):
        with _tenant_admin_role_patch():
            with app.test_client() as client:
                resp = client.put(
                    "/api/tenant-admin/users/user@example.com/scope/members",
                    headers=_auth_headers(json_body=True),
                    json={},
                )
        assert resp.status_code == 400
        mock_scope_service.set_scope.assert_not_called()

    def test_put_body_tenant_cannot_redirect_write(
        self, app, mock_cognito, mock_scope_service
    ):
        """A tenant_id in the body is ignored — the verified tenant is used (P1)."""
        mock_scope_service.set_scope.return_value = {"region": ["Oost"]}
        with _tenant_admin_role_patch():
            with app.test_client() as client:
                resp = client.put(
                    "/api/tenant-admin/users/user@example.com/scope/members",
                    headers=_auth_headers(tenant="TenantA", json_body=True),
                    json={
                        "tenant_id": "TenantB",
                        "administration": "TenantB",
                        "scopes": {"region": ["Oost"]},
                    },
                )
        assert resp.status_code == 200
        # Write is keyed by the VERIFIED tenant (TenantA), never the body value.
        called_tenant = mock_scope_service.set_scope.call_args[0][1]
        assert called_tenant == "TenantA"


class TestScopeDimensions:
    @patch("routes.tenant_admin_scope.ParameterService")
    @patch("routes.tenant_admin_scope.DatabaseManager")
    def test_get_dimensions_returns_enabled_with_canonical_values(
        self, mock_db_cls, mock_param_cls, app, mock_cognito
    ):
        param_svc = Mock()
        param_svc.get_param.return_value = [
            {
                "key": "region",
                "label": "Region",
                "field": "overlay.region",
                "enabled": True,
                "values": ["Oost", "Friesland", "Noord-Holland"],
            },
            {
                "key": "age_group",
                "label": "Age group",
                "enabled": False,
                "values": ["U15"],
            },
        ]
        mock_param_cls.return_value = param_svc
        with _tenant_admin_role_patch():
            with app.test_client() as client:
                resp = client.get(
                    "/api/tenant-admin/scope-dimensions/members",
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        # Only the ENABLED dimension is returned, with canonical values + field.
        assert body["dimensions"] == [
            {
                "key": "region",
                "label": "Region",
                "field": "overlay.region",
                "values": ["Oost", "Friesland", "Noord-Holland"],
            }
        ]
        # Read directly from the MySQL param (namespace = module lower-cased).
        param_svc.get_param.assert_called_once_with(
            "members", "scope_dimensions", tenant="TenantA"
        )


class TestTenantIsolationAndModule:
    def test_caller_without_tenant_access_returns_403(
        self, app, mock_cognito, mock_scope_service
    ):
        with _tenant_admin_role_patch():
            with app.test_client() as client:
                resp = client.get(
                    "/api/tenant-admin/users/user@example.com/scope/members",
                    headers=_auth_headers(tenant="TenantZ"),
                )
        assert resp.status_code == 403
        mock_scope_service.get_scope.assert_not_called()

    def test_unknown_module_returns_404(
        self, app, mock_cognito, mock_scope_service
    ):
        with _tenant_admin_role_patch():
            with app.test_client() as client:
                resp = client.get(
                    "/api/tenant-admin/users/user@example.com/scope/widgets",
                    headers=_auth_headers(),
                )
        assert resp.status_code == 404
        mock_scope_service.get_scope.assert_not_called()

    def test_non_tenant_admin_is_rejected(self, app, mock_cognito):
        """A caller without the Tenant_Admin role is denied (403)."""
        with patch("auth.role_cache.get_tenant_roles", return_value=["Members_Read"]):
            with app.test_client() as client:
                resp = client.get(
                    "/api/tenant-admin/users/user@example.com/scope/members",
                    headers=_auth_headers(),
                )
        assert resp.status_code == 403


class TestResyncProjection:
    """POST /api/tenant-admin/projection/resync (s5d task 5.3).

    The route forces a full re-projection of the CURRENT verified tenant via the
    trigger's ProjectionSync.sync_administration path (guaranteed diff-and-replace)
    and returns the written/removed summary. These tests patch the trigger seam so
    no real DynamoDB/MySQL is touched (steering 34).
    """

    def _sync_result(self, written=0, deleted=0):
        result = Mock()
        result.written = written
        result.deleted = deleted
        return result

    def _trigger_patch(self, sync):
        """Patch the module default trigger so _resolve_sync() returns `sync`."""
        trigger = Mock()
        trigger._resolve_sync.return_value = sync
        return patch(
            "routes.tenant_admin_scope.get_default_trigger", return_value=trigger
        )

    def test_resync_runs_sync_for_current_tenant_returns_summary(self, app):
        sync = Mock()
        sync.sync_administration.return_value = self._sync_result(written=3, deleted=1)
        with _tenant_admin_role_patch(), self._trigger_patch(sync):
            with app.test_client() as client:
                resp = client.post(
                    "/api/tenant-admin/projection/resync",
                    headers=_auth_headers(tenant="TenantA"),
                )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["tenant"] == "TenantA"
        assert body["written"] == 3
        assert body["removed"] == 1
        # Forced re-projection runs for the CURRENT verified tenant only (P1).
        sync.sync_administration.assert_called_once_with("TenantA")

    def test_resync_caller_without_tenant_access_returns_403(self, app):
        sync = Mock()
        with _tenant_admin_role_patch(), self._trigger_patch(sync):
            with app.test_client() as client:
                resp = client.post(
                    "/api/tenant-admin/projection/resync",
                    headers=_auth_headers(tenant="TenantZ"),
                )
        assert resp.status_code == 403
        sync.sync_administration.assert_not_called()

    def test_resync_non_tenant_admin_is_rejected(self, app):
        with patch("auth.role_cache.get_tenant_roles", return_value=["Members_Read"]):
            with app.test_client() as client:
                resp = client.post(
                    "/api/tenant-admin/projection/resync",
                    headers=_auth_headers(tenant="TenantA"),
                )
        assert resp.status_code in (401, 403)

    def test_resync_body_tenant_cannot_redirect_reprojection(self, app):
        """A tenant in the body is ignored — the verified tenant is re-projected (P1)."""
        sync = Mock()
        sync.sync_administration.return_value = self._sync_result(written=1, deleted=0)
        with _tenant_admin_role_patch(), self._trigger_patch(sync):
            with app.test_client() as client:
                resp = client.post(
                    "/api/tenant-admin/projection/resync",
                    headers=_auth_headers(tenant="TenantA", json_body=True),
                    json={"tenant_id": "TenantB", "administration": "TenantB"},
                )
        assert resp.status_code == 200
        # Re-projection is keyed by the VERIFIED tenant, never the body value.
        sync.sync_administration.assert_called_once_with("TenantA")

    def test_resync_sync_failure_surfaces_as_500(self, app):
        sync = Mock()
        sync.sync_administration.side_effect = RuntimeError("dynamo unavailable")
        with _tenant_admin_role_patch(), self._trigger_patch(sync):
            with app.test_client() as client:
                resp = client.post(
                    "/api/tenant-admin/projection/resync",
                    headers=_auth_headers(tenant="TenantA"),
                )
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["success"] is False
        assert "dynamo unavailable" in body["error"]
