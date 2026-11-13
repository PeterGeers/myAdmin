"""API tests for routes/chart_of_accounts_io_routes.py.

Exercises the two view functions directly inside a request context: the FIN
module guard, export download headers, import validation, the service-failure
400 payload, and the bare ``error_payload`` envelope on unexpected failures.

Reference: .kiro/specs/missing-py-tests/design.md
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

import routes.chart_of_accounts_io_routes as mod


def _unwrap(func):
    """Strip the auth decorators to reach the handler body.

    The views are wrapped by ``@cognito_required`` + ``@tenant_admin_required``
    (task 1 collapsed the inline guards onto the shared decorators), so calling
    ``mod.export_accounts(**...)`` would run the auth layer rather than the
    handler. Unwrapping is the established convention in this test suite
    (cf. ``tests/unit/test_tenant_function_routes_props.py``).
    """
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    return func


# Decorator-free handler references; the guards themselves are asserted by
# ``TestRouteGuards`` below.
export_view = _unwrap(mod.export_accounts)
import_view = _unwrap(mod.import_accounts)

TENANT = "test_admin"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORT_URL = "/api/tenant-admin/chart-of-accounts/export"
IMPORT_URL = "/api/tenant-admin/chart-of-accounts/import"


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    return flask_app


def _fin(value):
    """Patch the FIN-module guard on the route module."""
    return patch.object(mod, "_has_fin_module", return_value=value)


def _service(svc):
    """Patch the lazily-imported service class so the route builds our mock."""
    return patch(
        "services.chart_of_accounts_io_service.ChartOfAccountsIOService",
        return_value=svc,
    )


def _db():
    return patch.object(mod, "DatabaseManager", return_value=MagicMock())


def _auth():
    """The kwargs @cognito_required + @tenant_admin_required would inject."""
    return {
        "user_email": "test@example.com",
        "user_roles": ["Tenant_Admin"],
        "tenant": TENANT,
    }


def _import_request(app, file_tuple=None):
    data = {} if file_tuple is None else {"file": file_tuple}
    return app.test_request_context(
        IMPORT_URL, method="POST", data=data, content_type="multipart/form-data"
    )


class TestExportAccounts:
    def test_happy_path_returns_xlsx_attachment(self, app):
        svc = MagicMock()
        svc.export_to_excel.return_value = (
            BytesIO(b"xlsx-bytes"),
            "chart_of_accounts_test_admin_20260101.xlsx",
            3,
        )

        with app.test_request_context(EXPORT_URL), _fin(True), _service(svc), _db():
            resp = export_view(**_auth())

        assert resp.status_code == 200
        assert resp.mimetype == XLSX_MIME
        disposition = resp.headers["Content-Disposition"]
        assert disposition.startswith("attachment")
        assert "chart_of_accounts_test_admin_20260101.xlsx" in disposition
        assert b"".join(resp.iter_encoded()) == b"xlsx-bytes"
        svc.export_to_excel.assert_called_once_with(TENANT)

    def test_fin_module_disabled_returns_403(self, app):
        svc = MagicMock()

        with app.test_request_context(EXPORT_URL), _fin(False), _service(svc), _db():
            resp, status = export_view(**_auth())

        assert status == 403
        assert resp.get_json() == {"error": "FIN module not enabled"}
        svc.export_to_excel.assert_not_called()

    def test_unexpected_failure_returns_bare_error_envelope(self, app):
        svc = MagicMock()
        svc.export_to_excel.side_effect = RuntimeError("boom: rekeningschema")

        with app.test_request_context(EXPORT_URL), _fin(True), _service(svc), _db():
            resp, status = export_view(**_auth())

        assert status == 500
        body = resp.get_json()
        assert body["error"] == "Failed to export accounts"
        assert body.get("error_id")
        assert "success" not in body  # include_success=False -> legacy bare shape
        assert "boom" not in resp.get_data(as_text=True)


class TestImportAccounts:
    def test_happy_path_returns_import_summary(self, app):
        svc = MagicMock()
        svc.import_from_excel.return_value = {
            "success": True,
            "imported": 10,
            "updated": 5,
            "total": 15,
        }

        with (
            _import_request(app, (BytesIO(b"excel-bytes"), "accounts.xlsx")),
            _fin(True),
            _service(svc),
            _db(),
        ):
            resp = import_view(**_auth())

        assert resp.status_code == 200
        assert resp.get_json() == {
            "success": True,
            "imported": 10,
            "updated": 5,
            "total": 15,
        }
        tenant, uploaded = svc.import_from_excel.call_args[0]
        assert tenant == TENANT
        assert uploaded.filename == "accounts.xlsx"

    def test_fin_module_disabled_returns_403(self, app):
        svc = MagicMock()

        with (
            _import_request(app, (BytesIO(b"excel-bytes"), "accounts.xlsx")),
            _fin(False),
            _service(svc),
            _db(),
        ):
            resp, status = import_view(**_auth())

        assert status == 403
        assert resp.get_json() == {"error": "FIN module not enabled"}
        svc.import_from_excel.assert_not_called()

    def test_missing_file_returns_400(self, app):
        svc = MagicMock()

        with _import_request(app), _fin(True), _service(svc), _db():
            resp, status = import_view(**_auth())

        assert status == 400
        assert resp.get_json() == {"error": "No file uploaded"}
        svc.import_from_excel.assert_not_called()

    def test_empty_filename_returns_400(self, app):
        svc = MagicMock()

        with _import_request(app, (BytesIO(b""), "")), _fin(True), _service(svc), _db():
            resp, status = import_view(**_auth())

        assert status == 400
        assert resp.get_json() == {"error": "No file selected"}
        svc.import_from_excel.assert_not_called()

    def test_non_excel_extension_returns_400(self, app):
        svc = MagicMock()

        with (
            _import_request(app, (BytesIO(b"a,b"), "accounts.csv")),
            _fin(True),
            _service(svc),
            _db(),
        ):
            resp, status = import_view(**_auth())

        assert status == 400
        assert resp.get_json() == {
            "error": "Invalid file type. Must be Excel file (.xlsx or .xls)"
        }
        svc.import_from_excel.assert_not_called()

    def test_service_validation_failure_returns_400_payload(self, app):
        svc = MagicMock()
        svc.import_from_excel.return_value = {
            "success": False,
            "errors": ["Row 2: Account name required"],
            "parsed": 0,
        }

        with (
            _import_request(app, (BytesIO(b"excel-bytes"), "accounts.xlsx")),
            _fin(True),
            _service(svc),
            _db(),
        ):
            resp, status = import_view(**_auth())

        assert status == 400
        assert resp.get_json() == svc.import_from_excel.return_value

    def test_unexpected_failure_returns_bare_error_envelope(self, app):
        svc = MagicMock()
        svc.import_from_excel.side_effect = RuntimeError("boom: rekeningschema")

        with (
            _import_request(app, (BytesIO(b"excel-bytes"), "accounts.xlsx")),
            _fin(True),
            _service(svc),
            _db(),
        ):
            resp, status = import_view(**_auth())

        assert status == 500
        body = resp.get_json()
        assert body["error"] == "Failed to import accounts"
        assert body.get("error_id")
        assert "success" not in body
        assert "boom" not in resp.get_data(as_text=True)


class TestRouteGuards:
    def test_io_routes_carry_cognito_and_tenant_admin_guards(self):
        """Both views must keep @cognito_required + @tenant_admin_required.

        Relies on the sentinels those decorators set after ``functools.wraps``
        (same convention as tests/api/test_pattern_storage_tenant_scope.py).
        """
        flask_app = Flask(__name__)
        flask_app.register_blueprint(mod.chart_of_accounts_io_bp)

        checked = 0
        for endpoint, view in flask_app.view_functions.items():
            if not endpoint.startswith("chart_of_accounts_io."):
                continue
            assert getattr(view, "_cognito_required", False), (
                f"{endpoint} missing @cognito_required"
            )
            assert getattr(view, "_tenant_required", False), (
                f"{endpoint} missing @tenant_admin_required"
            )
            checked += 1

        assert checked == 2, f"expected 2 chart_of_accounts_io routes, found {checked}"


class TestAuthGuardEnforcement:
    """The real decorators must reject an unauthenticated request."""

    def test_anonymous_export_is_rejected(self):
        auth_error = {
            "statusCode": 401,
            "body": '{"error": "Unauthorized", "message": "Missing or invalid token"}',
        }
        flask_app = Flask(__name__)
        flask_app.config["TESTING"] = True
        flask_app.register_blueprint(mod.chart_of_accounts_io_bp)
        with (
            patch(
                "auth.cognito_utils.extract_user_credentials",
                return_value=(None, None, auth_error),
            ),
            flask_app.test_client() as client,
        ):
            resp = client.get(EXPORT_URL)
        assert resp.status_code in (401, 403)
        assert resp.get_json()["error"]
