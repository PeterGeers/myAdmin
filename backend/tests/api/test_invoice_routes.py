"""API tests for routes/invoice_routes.py

Covers the invoice upload wrapper (CORS/no-auth OPTIONS, validation, duplicate
409, service error 500) and approve-transactions (tenant enforcement,
closed-period 400, error 500). Routes delegate to the service layer, so the
services are mocked; the tests assert the route's own observable behavior and
tenant handling.

Isolation pattern (mirrors tests/api/test_zzp_phase1_routes.py): the auth
decorators are patched to pass through and inject the Flask-plane context
(user_email, user_roles, tenant='TestTenant', user_tenants), the route module is
reloaded so the passthroughs apply, and the blueprint is mounted on a bare Flask
app. This exercises the handler body directly without the full-app security
middleware / permission resolution.

Flask plane conventions: response shape {'success': True/False, ...}; tenant key
is `administration`.
"""

import io
import json
import os
import sys
from functools import wraps
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from db_exceptions import ClosedPeriodError


TENANT = "TestTenant"


def _passthrough_cognito(required_permissions=None, required_roles=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs["user_email"] = "finance@example.com"
            kwargs["user_roles"] = ["Finance_CRUD"]
            return f(*args, **kwargs)

        return wrapper

    return decorator


def _passthrough_tenant(allow_sysadmin=False):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs["tenant"] = TENANT
            kwargs["user_tenants"] = [TENANT]
            return f(*args, **kwargs)

        return wrapper

    return decorator


@pytest.fixture
def invoice_module():
    """Reload routes.invoice_routes with passthrough auth decorators applied."""
    with (
        patch("auth.cognito_utils.cognito_required", side_effect=_passthrough_cognito),
        patch("auth.tenant_context.tenant_required", side_effect=_passthrough_tenant),
    ):
        import importlib
        import routes.invoice_routes as ir

        importlib.reload(ir)
        yield ir
    # Restore the module to its real (decorated) state for other tests.
    import importlib
    import routes.invoice_routes as ir

    importlib.reload(ir)


@pytest.fixture
def client(invoice_module):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(invoice_module.invoice_bp)
    return app.test_client()


# ============================================================================
# /api/upload — OPTIONS (CORS, no auth) and POST paths
# ============================================================================


class TestUploadWrapper:
    def test_options_preflight_no_auth_returns_ok(self, client):
        """OPTIONS preflight is answered without authentication."""
        response = client.options("/api/upload")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "OK"

    def test_post_missing_file_returns_400(self, client, invoice_module):
        """POST without a file part → 400 'No file provided'."""
        with patch.object(invoice_module, "InvoiceService", return_value=MagicMock()):
            response = client.post("/api/upload", data={})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert "No file" in data["error"]

    def test_post_empty_filename_returns_400(self, client, invoice_module):
        """A file part with an empty filename → 400 'No file selected'."""
        with patch.object(invoice_module, "InvoiceService", return_value=MagicMock()):
            data = {"file": (io.BytesIO(b""), "")}
            response = client.post(
                "/api/upload", data=data, content_type="multipart/form-data"
            )
        assert response.status_code == 400
        body = json.loads(response.data)
        assert body["success"] is False
        assert "No file selected" in body["error"]

    def test_post_invalid_file_type_returns_400(self, client, invoice_module):
        """A file with a disallowed extension → 400 'Invalid file type'."""
        svc = MagicMock()
        svc.allowed_file.return_value = False
        with patch.object(invoice_module, "InvoiceService", return_value=svc):
            data = {"file": (io.BytesIO(b"not a pdf"), "bad.exe")}
            response = client.post(
                "/api/upload", data=data, content_type="multipart/form-data"
            )
        assert response.status_code == 400
        body = json.loads(response.data)
        assert body["success"] is False
        assert "Invalid file type" in body["error"]

    def test_post_duplicate_detected_returns_409(self, client, invoice_module):
        """When the service flags a duplicate, the route stops with 409 and cleans up."""
        svc = MagicMock()
        svc.allowed_file.return_value = True
        svc.upload_to_drive.return_value = {"file_id": "drv1"}
        svc.check_early_duplicates.return_value = {
            "has_duplicates": True,
            "message": "already uploaded",
            "duplicate_info": {"id": 1},
        }
        with (
            patch.object(invoice_module, "InvoiceService", return_value=svc),
            patch.object(invoice_module, "secure_filename", return_value="invoice.pdf"),
            patch("werkzeug.datastructures.FileStorage.save"),
        ):
            data = {"file": (io.BytesIO(b"%PDF-1.4 data"), "invoice.pdf")}
            response = client.post(
                "/api/upload", data=data, content_type="multipart/form-data"
            )

        assert response.status_code == 409
        body = json.loads(response.data)
        assert body["success"] is False
        assert body["error"] == "duplicate_detected"
        svc.cleanup_temp_file.assert_called_once()

    def test_post_tenant_prefixes_saved_filename(self, client, invoice_module):
        """The uploaded file is saved under a tenant-prefixed unique name (isolation)."""
        svc = MagicMock()
        svc.allowed_file.return_value = True
        svc.upload_to_drive.return_value = {"file_id": "drv1"}
        svc.check_early_duplicates.return_value = {"has_duplicates": False}
        svc.process_invoice_file.return_value = {
            "folder": "Vendor",
            "extracted_text": "x",
            "transactions": [],
            "prepared_transactions": [],
            "template_transactions": [],
            "parser_used": "default",
        }
        saved_paths = []
        with (
            patch.object(invoice_module, "InvoiceService", return_value=svc),
            patch.object(invoice_module, "secure_filename", return_value="invoice.pdf"),
            patch(
                "werkzeug.datastructures.FileStorage.save",
                side_effect=lambda p: saved_paths.append(p),
            ),
        ):
            data = {"file": (io.BytesIO(b"%PDF data"), "invoice.pdf")}
            response = client.post(
                "/api/upload", data=data, content_type="multipart/form-data"
            )

        assert response.status_code == 200
        # Saved path must carry the authenticated tenant as a prefix.
        assert saved_paths and os.path.basename(saved_paths[0]).startswith(f"{TENANT}_")

    def test_post_internal_error_returns_500(self, client, invoice_module):
        """An unexpected service error surfaces as 500 with success=False."""
        svc = MagicMock()
        svc.allowed_file.return_value = True
        svc.upload_to_drive.side_effect = RuntimeError("drive exploded")
        with (
            patch.object(invoice_module, "InvoiceService", return_value=svc),
            patch.object(invoice_module, "secure_filename", return_value="invoice.pdf"),
            patch("werkzeug.datastructures.FileStorage.save"),
        ):
            data = {"file": (io.BytesIO(b"%PDF data"), "invoice.pdf")}
            response = client.post(
                "/api/upload", data=data, content_type="multipart/form-data"
            )

        assert response.status_code == 500
        body = json.loads(response.data)
        assert body["success"] is False
        assert "drive exploded" in body["error"]


# ============================================================================
# /api/approve-transactions — tenant enforcement + error paths
# ============================================================================


class TestApproveTransactions:
    def test_forces_tenant_on_every_transaction(self, client):
        """Each incoming transaction gets Administration set to the caller tenant."""
        logic = MagicMock()
        logic.save_approved_transactions.side_effect = lambda txns: txns
        with patch("transaction_logic.TransactionLogic", return_value=logic):
            payload = {
                "transactions": [
                    {"TransactionAmount": 100, "Administration": "AttackerTenant"},
                    {"TransactionAmount": 200},
                ]
            }
            response = client.post("/api/approve-transactions", json=payload)

        assert response.status_code == 200
        body = json.loads(response.data)
        assert body["success"] is True
        # The service received transactions with Administration forced to the
        # authenticated tenant, never the attacker-supplied value.
        saved_arg = logic.save_approved_transactions.call_args[0][0]
        assert all(t["Administration"] == TENANT for t in saved_arg)

    def test_reports_skipped_zero_amount_lines(self, client):
        """When the service saves fewer than submitted, the gap is reported as skipped."""
        logic = MagicMock()
        logic.save_approved_transactions.return_value = [{"id": 1}, {"id": 2}]
        with patch("transaction_logic.TransactionLogic", return_value=logic):
            payload = {
                "transactions": [
                    {"TransactionAmount": 10},
                    {"TransactionAmount": 20},
                    {"TransactionAmount": 0},
                ]
            }
            response = client.post("/api/approve-transactions", json=payload)

        assert response.status_code == 200
        body = json.loads(response.data)
        assert body["skippedCount"] == 1
        assert "skipped" in body["message"]

    def test_closed_period_returns_400(self, client):
        """A ClosedPeriodError from the service maps to a 400 (not a 500)."""
        logic = MagicMock()
        logic.save_approved_transactions.side_effect = ClosedPeriodError(
            [{"year": 2023}]
        )
        with patch("transaction_logic.TransactionLogic", return_value=logic):
            payload = {"transactions": [{"TransactionAmount": 10}]}
            response = client.post("/api/approve-transactions", json=payload)

        assert response.status_code == 400
        body = json.loads(response.data)
        assert body["success"] is False

    def test_internal_error_returns_500(self, client):
        logic = MagicMock()
        logic.save_approved_transactions.side_effect = RuntimeError("db down")
        with patch("transaction_logic.TransactionLogic", return_value=logic):
            payload = {"transactions": [{"TransactionAmount": 10}]}
            response = client.post("/api/approve-transactions", json=payload)

        assert response.status_code == 500
        body = json.loads(response.data)
        assert body["success"] is False
        # Error contract: raw exception text must not leak; generic msg + error_id.
        assert "db down" not in body["error"]
        assert body["error_id"]
