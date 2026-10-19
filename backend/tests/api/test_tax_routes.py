"""API tests for routes/tax_routes.py

Covers BTW (VAT) and Toeristenbelasting (tourist tax) endpoints: required-field
validation (400), service delegation, tenant isolation on the tenant-scoped
report, and error/abort paths (processor failure → 500, exception → 500). The
report generators / processors are mocked; the tests assert the route's own
observable behavior.

Isolation pattern (mirrors tests/api/test_zzp_phase1_routes.py): auth decorators
are patched to pass through and inject the Flask-plane context, the route module
is reloaded, and the blueprint is mounted on a bare Flask app — exercising the
handler bodies without the full-app security middleware / permission resolution.

Flask plane conventions: response shape {'success': True/False}; the
Toeristenbelasting route is @tenant_required() so `tenant` is injected.
"""

import json
import os
import sys
from functools import wraps
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

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
def tax_module():
    """Reload routes.tax_routes with passthrough auth decorators applied."""
    with (
        patch("auth.cognito_utils.cognito_required", side_effect=_passthrough_cognito),
        patch("auth.tenant_context.tenant_required", side_effect=_passthrough_tenant),
    ):
        import importlib
        import routes.tax_routes as tr

        importlib.reload(tr)
        yield tr
    import importlib
    import routes.tax_routes as tr

    importlib.reload(tr)


@pytest.fixture
def client(tax_module):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(tax_module.tax_bp)
    return app.test_client()


# ============================================================================
# POST /api/btw/generate-report
# ============================================================================


class TestBtwGenerateReport:
    def test_missing_required_fields_returns_400(self, client):
        """administration/year/quarter are all required."""
        response = client.post(
            "/api/btw/generate-report",
            json={"administration": "ExampleTenant"},  # missing year + quarter
        )
        assert response.status_code == 400
        body = json.loads(response.data)
        assert body["success"] is False
        assert "required" in body["error"].lower()

    def test_report_generation_failure_returns_500(self, client, tax_module):
        """If the generator reports failure, the route returns 500 with that payload."""
        with (
            patch.object(tax_module, "get_cache", return_value=MagicMock()),
            patch.object(tax_module, "DatabaseManager", return_value=MagicMock()),
            patch(
                "report_generators.btw_aangifte_generator.generate_btw_report",
                return_value={"success": False, "error": "no data for quarter"},
            ),
        ):
            response = client.post(
                "/api/btw/generate-report",
                json={"administration": "ExampleTenant", "year": 2024, "quarter": 1},
            )

        assert response.status_code == 500
        body = json.loads(response.data)
        assert body["success"] is False


# ============================================================================
# POST /api/btw/save-transaction
# ============================================================================


class TestBtwSaveTransaction:
    def test_missing_transaction_returns_400(self, client):
        response = client.post("/api/btw/save-transaction", json={})
        assert response.status_code == 400
        body = json.loads(response.data)
        assert body["success"] is False
        assert "Transaction data required" in body["error"]

    def test_save_delegates_to_processor(self, client, tax_module):
        """A valid transaction is handed to BTWProcessor.save_btw_transaction."""
        processor = MagicMock()
        processor.save_btw_transaction.return_value = {"success": True, "id": 7}
        with patch.object(tax_module, "BTWProcessor", return_value=processor):
            txn = {"TransactionAmount": 210.0, "administration": "ExampleTenant"}
            response = client.post(
                "/api/btw/save-transaction", json={"transaction": txn}
            )

        assert response.status_code == 200
        body = json.loads(response.data)
        assert body["success"] is True
        processor.save_btw_transaction.assert_called_once_with(txn)

    def test_save_exception_returns_500(self, client, tax_module):
        processor = MagicMock()
        processor.save_btw_transaction.side_effect = RuntimeError("insert failed")
        with patch.object(tax_module, "BTWProcessor", return_value=processor):
            response = client.post(
                "/api/btw/save-transaction",
                json={"transaction": {"TransactionAmount": 1}},
            )

        assert response.status_code == 500
        body = json.loads(response.data)
        assert body["success"] is False
        # Error contract (steering 30 / error_responses): raw exception text must
        # NOT leak; a generic message + correlation error_id is returned instead.
        assert "insert failed" not in body["error"]
        assert body["error_id"]


# ============================================================================
# POST /api/toeristenbelasting/generate-report (tenant-scoped)
# ============================================================================


class TestToeristenbelastingGenerateReport:
    def test_missing_year_returns_400(self, client):
        response = client.post("/api/toeristenbelasting/generate-report", json={})
        assert response.status_code == 400
        body = json.loads(response.data)
        assert body["success"] is False
        assert "Year is required" in body["error"]

    def test_passes_authenticated_tenant_to_processor(self, client, tax_module):
        """Report is generated for the caller's tenant (tenant isolation)."""
        processor = MagicMock()
        processor.generate_toeristenbelasting_report.return_value = {
            "success": True,
            "html_report": "<html></html>",
        }
        with patch.object(
            tax_module, "ToeristenbelastingProcessor", return_value=processor
        ):
            response = client.post(
                "/api/toeristenbelasting/generate-report", json={"year": 2024}
            )

        assert response.status_code == 200
        body = json.loads(response.data)
        assert body["success"] is True
        # The tenant threaded in is the authenticated one from @tenant_required.
        _, kwargs = processor.generate_toeristenbelasting_report.call_args
        assert kwargs.get("tenant") == TENANT

    def test_processor_failure_returns_500(self, client, tax_module):
        processor = MagicMock()
        processor.generate_toeristenbelasting_report.return_value = {
            "success": False,
            "error": "no bookings",
        }
        with patch.object(
            tax_module, "ToeristenbelastingProcessor", return_value=processor
        ):
            response = client.post(
                "/api/toeristenbelasting/generate-report", json={"year": 2024}
            )

        assert response.status_code == 500
        body = json.loads(response.data)
        assert body["success"] is False


# ============================================================================
# GET /api/toeristenbelasting/available-years
# ============================================================================


class TestToeristenbelastingAvailableYears:
    def test_returns_current_and_three_prior_years(self, client):
        from datetime import datetime

        current_year = datetime.now().year

        response = client.get("/api/toeristenbelasting/available-years")

        assert response.status_code == 200
        body = json.loads(response.data)
        assert body["success"] is True
        assert body["years"] == [str(current_year - i) for i in range(4)]
