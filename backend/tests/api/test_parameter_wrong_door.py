"""Wrong-door writes to a module-owned namespace must fail closed.

Feature: admin-surface-registry
Requirements: 7.7, 11.2, 11.6
"""

import inspect
import os
import sys
from unittest.mock import MagicMock

import pytest
from flask import Flask

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from routes import parameter_admin_routes

TENANT = "test-tenant"
VERIFIED_TENANTS = [TENANT]


@pytest.fixture
def app_context():
    app = Flask(__name__)
    with app.app_context():
        yield app


def test_authoring_key_is_rejected_by_the_guard(app_context):
    rejected = parameter_admin_routes._module_owned_write_error(
        "members", "field_overlay"
    )
    assert rejected is not None
    payload, status = rejected
    assert status == 400
    assert payload.get_json()["success"] is False
    assert "module plane" in payload.get_json()["error"]


def test_retired_mirror_key_is_now_rejected_too():
    """Option B (Members/02 mirror retirement) removed the last exception.

    The Flask-written ``members.scope_dimensions`` validator mirror is gone, so that
    key now fails closed exactly like every other module-owned key: one logical config,
    exactly one writing door.
    """
    # The guard builds a JSON 400 response, so it needs an app context.
    with Flask(__name__).app_context():
        rejected = parameter_admin_routes._module_owned_write_error(
            "members", "scope_dimensions"
        )
        assert rejected is not None
        response, status = rejected
        assert status == 400
        assert response.get_json()["success"] is False


def test_flask_owned_namespaces_pass_the_guard():
    for namespace in ("storage", "str", "zzp", "fin"):
        assert (
            parameter_admin_routes._module_owned_write_error(namespace, "anything")
            is None
        )


def _app_with_rule(rule, endpoint, view, methods):
    app = Flask(__name__)
    app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=methods)
    app.config["TESTING"] = True
    return app


def test_post_does_not_reach_the_parameter_service(monkeypatch):
    service = MagicMock()
    monkeypatch.setattr(parameter_admin_routes, "_get_service", lambda: service)
    original = inspect.unwrap(parameter_admin_routes.create_parameter)
    app = _app_with_rule(
        "/api/tenant-admin/parameters",
        "create_parameter",
        lambda: original(
            "admin@example.com", ["Tenant_Admin"], TENANT, VERIFIED_TENANTS
        ),
        ["POST"],
    )
    response = app.test_client().post(
        "/api/tenant-admin/parameters",
        json={"namespace": "members", "key": "field_overlay", "value": {}},
    )
    assert response.status_code == 400
    assert "module plane" in response.get_json()["error"]
    service.assert_not_called()


def test_put_does_not_reach_the_parameter_service(monkeypatch):
    row = {
        "scope": "tenant",
        "scope_id": TENANT,
        "namespace": "members",
        "key": "field_overlay",
        "value_type": "json",
        "is_secret": False,
    }
    fake_db = MagicMock()
    fake_db.execute_query.return_value = [row]
    monkeypatch.setattr(parameter_admin_routes, "DatabaseManager", lambda: fake_db)
    service = MagicMock()
    monkeypatch.setattr(parameter_admin_routes, "_get_service", lambda: service)
    original = inspect.unwrap(parameter_admin_routes.update_parameter)
    app = _app_with_rule(
        "/api/tenant-admin/parameters/<int:param_id>",
        "update_parameter",
        lambda param_id: original(
            "admin@example.com", ["Tenant_Admin"], TENANT, VERIFIED_TENANTS, param_id
        ),
        ["PUT"],
    )
    response = app.test_client().put(
        "/api/tenant-admin/parameters/1",
        json={"value": {}, "value_type": "json"},
    )
    assert response.status_code == 400
    assert "module plane" in response.get_json()["error"]
    service.assert_not_called()


def test_advanced_list_excludes_module_owned_namespaces(monkeypatch):
    """The read path omits members.* entirely, even though DB rows exist."""

    class _FakeDb:
        def execute_query(self, sql, params=None, fetch=True):
            if "FROM tenant_modules" in sql:
                return [{"module_name": "FIN"}]
            if "DISTINCT namespace" in sql:
                return [{"namespace": "members"}, {"namespace": "storage"}]
            return []

    monkeypatch.setattr(parameter_admin_routes, "DatabaseManager", _FakeDb)
    service = MagicMock()
    service.get_params_by_namespace.side_effect = lambda ns, tenant: [
        {"namespace": ns, "key": "value", "value": "secret", "is_secret": True}
    ]
    monkeypatch.setattr(parameter_admin_routes, "_get_service", lambda: service)
    original = inspect.unwrap(parameter_admin_routes.list_parameters)
    app = _app_with_rule(
        "/api/tenant-admin/parameters",
        "list_parameters",
        lambda: original(
            "admin@example.com", ["Tenant_Admin"], TENANT, VERIFIED_TENANTS
        ),
        ["GET"],
    )
    response = app.test_client().get("/api/tenant-admin/parameters")
    assert response.status_code == 200
    body = response.get_json()
    assert "members" not in body["parameters"]
    assert "storage" in body["parameters"]
    assert body["parameters"]["storage"][0]["value"] == "********"
    calls = [call.args[0] for call in service.get_params_by_namespace.call_args_list]
    assert "members" not in calls
    assert "storage" in calls


def test_explicit_namespace_read_is_still_served_for_the_typed_editor(monkeypatch):
    """The module's typed editor looks its own row up through this endpoint.

    Only the raw Advanced *listing* hides a module-owned namespace — an explicit
    `?namespace=members` read must still be served, or the editor's in-place UPDATE
    lookup silently degrades to a blind create.
    """

    class _FakeDb:
        def execute_query(self, sql, params=None, fetch=True):
            # MEMBERS enabled, so the (pre-existing) inactive-module gate does not apply
            # and the typed-editor exclusion is the only thing under test here.
            return [{"module_name": "MEMBERS"}]

    monkeypatch.setattr(parameter_admin_routes, "DatabaseManager", _FakeDb)
    service = MagicMock()
    service.get_params_by_namespace.return_value = [
        {
            "namespace": "members",
            "key": "scope_dimensions",
            "value": "[]",
            "is_secret": False,
        }
    ]
    monkeypatch.setattr(parameter_admin_routes, "_get_service", lambda: service)
    original = inspect.unwrap(parameter_admin_routes.list_parameters)
    app = _app_with_rule(
        "/api/tenant-admin/parameters",
        "list_parameters_filtered",
        lambda: original(
            "admin@example.com", ["Tenant_Admin"], TENANT, VERIFIED_TENANTS
        ),
        ["GET"],
    )
    response = app.test_client().get("/api/tenant-admin/parameters?namespace=members")
    assert response.status_code == 200
    assert "members" in response.get_json()["parameters"]
    service.get_params_by_namespace.assert_called_with("members", TENANT)
