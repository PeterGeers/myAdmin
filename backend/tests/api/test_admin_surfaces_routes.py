"""API tests for GET /api/tenant/admin-surfaces.

Feature: admin-surface-registry
Requirements: 4.1-4.8, 8.2
Reference: .kiro/specs/Common/Tenant/admin-surface-registry/design.md

The real view bodies are exercised through a minimal Flask app. Authentication
wrappers are unwrapped in these contract tests; 401 handling is tested separately.
"""

import inspect
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import tenant_module_routes

VERIFIED_TENANTS = ["test-tenant", "other-tenant"]


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, sql, params=None):
        return None

    def fetchall(self):
        return self._rows


class _FakeCursorCtx:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return (self._cursor, MagicMock())

    def __exit__(self, *exc):
        return False


@pytest.fixture
def make_client(monkeypatch):
    def _factory(active_modules=("FIN",)):
        cursor = _FakeCursor([{"module_name": name} for name in active_modules])
        monkeypatch.setattr(
            tenant_module_routes.db_manager,
            "get_cursor",
            lambda: _FakeCursorCtx(cursor),
        )
        monkeypatch.setattr(
            "auth.tenant_context.get_user_tenants",
            lambda token: list(VERIFIED_TENANTS),
        )
        app = Flask(__name__)
        original = inspect.unwrap(tenant_module_routes.get_admin_surfaces)
        app.add_url_rule(
            "/api/tenant/admin-surfaces",
            endpoint="admin_surfaces",
            view_func=lambda: original("admin@example.com", ["Tenant_Admin"]),
            methods=["GET"],
        )
        original_modules = inspect.unwrap(tenant_module_routes.get_tenant_modules)
        app.add_url_rule(
            "/api/tenant/modules",
            endpoint="tenant_modules",
            view_func=lambda: original_modules("admin@example.com", ["Finance_Read"]),
            methods=["GET"],
        )
        app.config["TESTING"] = True
        return app.test_client()

    return _factory


def _get(client, tenant=None):
    headers = {"Authorization": "Bearer test-token"}
    if tenant is not None:
        headers["X-Tenant"] = tenant
    return client.get("/api/tenant/admin-surfaces", headers=headers)


def test_fin_tenant_gets_its_panel_and_capabilities(make_client):
    response = _get(make_client(), "test-tenant")
    assert response.status_code == 200
    body = response.get_json()
    assert body["tenant"] == "test-tenant"
    assert [s["id"] for s in body["admin_surfaces"]] == [
        "users",
        "tenant-info",
        "sender",
        "pivot",
        "landing",
        "financial",
        "storage",
        "templates",
        "advanced",
    ]
    for surface in body["admin_surfaces"]:
        assert set(surface) == {"id", "kind", "order", "label_key"}


def test_members_tenant_gets_the_members_panel(make_client):
    response = _get(make_client(("MEMBERS",)), "test-tenant")
    ids = [s["id"] for s in response.get_json()["admin_surfaces"]]
    assert "members" in ids and "financial" not in ids


def test_missing_x_tenant_is_400(make_client):
    response = _get(make_client())
    assert response.status_code == 400
    assert response.get_json()["error"] == "No tenant specified"


def test_unlisted_tenant_is_403(make_client):
    response = _get(make_client(), "not-my-tenant")
    assert response.status_code == 403
    assert response.get_json()["error"] == "Access denied to tenant"


def test_module_free_tenant_gets_the_baseline_only(make_client):
    response = _get(make_client(active_modules=()), "test-tenant")
    assert response.status_code == 200
    ids = [s["id"] for s in response.get_json()["admin_surfaces"]]
    assert ids == ["users", "tenant-info", "sender", "landing", "advanced"]


def test_response_is_not_cacheable(make_client):
    response = _get(make_client(), "test-tenant")
    assert response.headers["Cache-Control"] == "no-store"


def test_a_tenant_without_members_capability_still_resolves(make_client):
    # ADR 0004/0007: this Flask endpoint validates against custom:tenants, not
    # the module edge's capability-scoped tenant_keys.
    response = _get(make_client(("FIN",)), "other-tenant")
    assert response.status_code == 200
    assert response.get_json()["tenant"] == "other-tenant"


def test_internal_error_is_500_without_a_traceback(make_client, monkeypatch):
    client = make_client()

    def _boom():
        raise RuntimeError("db exploded")

    monkeypatch.setattr(tenant_module_routes.db_manager, "get_cursor", _boom)
    response = _get(client, "test-tenant")
    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error"}
    assert "db exploded" not in response.get_data(as_text=True)


def test_no_token_returns_401_from_the_real_auth_wrapper():
    app = Flask(__name__)
    app.register_blueprint(tenant_module_routes.tenant_module_bp)
    app.config["TESTING"] = True
    auth_error = {
        "statusCode": 401,
        "body": json.dumps({"error": "Unauthorized"}),
    }
    with patch(
        "auth.cognito_utils.extract_user_credentials",
        return_value=(None, [], auth_error),
    ):
        response = app.test_client().get(
            "/api/tenant/admin-surfaces",
            headers={"X-Tenant": "test-tenant"},
        )
    assert response.status_code == 401
    assert response.get_json() == {"error": "Unauthorized"}


class _OnlyCursorCtx:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *exc):
        return False


def test_modules_endpoint_shape_is_unchanged(make_client, monkeypatch):
    client = make_client(("FIN",))
    cursor = _FakeCursor([{"module_name": "FIN"}])
    monkeypatch.setattr(
        tenant_module_routes.db_manager,
        "get_cursor_only",
        lambda: _OnlyCursorCtx(cursor),
    )
    response = client.get(
        "/api/tenant/modules",
        headers={"Authorization": "Bearer test-token", "X-Tenant": "test-tenant"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert "admin_surfaces" not in body
    assert body["tenant"] == "test-tenant"
    assert body["available_modules"] == ["FIN"]
    assert "user_module_permissions" in body


# ---------------------------------------------------------------------------
# Canonical surface contract (checked in)
# ---------------------------------------------------------------------------
#
# (id, kind, order, label_key). Any backend change to a surface — adding one,
# retitling a tab, renaming a label key — must fail here until this literal is
# updated, which is the review gate that keeps the backend registry, the frontend
# component map + label mirror, and the locale files in step with each other.
SURFACE_CONTRACT = [
    ("users", "always", 10, "tenantAdmin.tabs.users"),
    ("functions", "capability", 20, "tenantAdmin.tabs.functions"),
    ("tenant-info", "always", 30, "tenantAdmin.tabs.tenantInfo"),
    ("sender", "always", 40, "tenantAdmin.tabs.senderSettings"),
    ("pivot", "capability", 50, "tenantAdmin.tabs.pivotViews"),
    ("landing", "always", 60, "tenantAdmin.tabs.landingPage"),
    ("financial", "module", 100, "tenantAdmin.tabs.financial"),
    ("members", "module", 110, "tenantAdmin.tabs.membersConfig"),
    ("storage", "capability", 200, "tenantAdmin.tabs.storage"),
    ("media", "capability", 210, "tenantAdmin.tabs.mediaAssets"),
    ("templates", "capability", 220, "tenantAdmin.tabs.templates"),
    ("advanced", "role", 900, "tenantAdmin.tabs.advanced"),
]


def test_endpoint_matches_the_canonical_surface_contract(make_client):
    """The derived response for an all-modules tenant equals the checked-in contract.

    Authoritative on the Flask request path — not just the pure registry — so the
    wire contract itself is pinned.
    """
    client = make_client(("FIN", "MEMBERS", "STR", "ZZP", "TENADMIN"))
    response = _get(client, "test-tenant")
    assert response.status_code == 200

    got = [
        (s["id"], s["kind"], s["order"], s["label_key"])
        for s in response.get_json()["admin_surfaces"]
    ]
    # SURFACE_CONTRACT is written in derived (order, id) order; assert it explicitly.
    assert got == SURFACE_CONTRACT


def test_every_surface_label_key_is_namespaced_under_tenant_admin_tabs(make_client):
    """A label key must stay under `tenantAdmin.tabs.` so the frontend can resolve it."""
    for _sid, _kind, _order, label_key in SURFACE_CONTRACT:
        assert label_key.startswith("tenantAdmin.tabs.")
