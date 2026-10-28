"""
API tests for audit_routes.py

Tests audit log query endpoint with filters, report generation endpoint,
and authentication enforcement (401/403).

Requirements: 5.2, 5.5, 8.3, 8.4
Reference: .kiro/specs/missing-py-tests/design.md
"""

import pytest
import json
from unittest.mock import patch, MagicMock


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestAuditAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_get_logs_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get audit logs should be rejected."""
        auth_error = {
            "statusCode": 401,
            "body": '{"error": "Unauthorized", "message": "Missing or invalid token"}',
        }
        with patch(
            "auth.cognito_utils.extract_user_credentials",
            return_value=(None, None, auth_error),
        ):
            response = client.get("/api/audit/logs")
        assert response.status_code in (401, 403)

    def test_get_logs_non_sysadmin_returns_403(self, client, mock_auth):
        """Non-SysAdmin user should get 403 on audit endpoints."""
        response = client.get("/api/audit/logs", headers=mock_auth)
        assert response.status_code == 403

    def test_compliance_report_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to compliance report should be rejected."""
        auth_error = {
            "statusCode": 401,
            "body": '{"error": "Unauthorized", "message": "Missing or invalid token"}',
        }
        with patch(
            "auth.cognito_utils.extract_user_credentials",
            return_value=(None, None, auth_error),
        ):
            response = client.get("/api/audit/reports/compliance")
        assert response.status_code in (401, 403)

    def test_cleanup_non_sysadmin_returns_403(self, client, mock_auth):
        """Non-SysAdmin user should get 403 on cleanup endpoint."""
        response = client.post(
            "/api/audit/cleanup", headers=mock_auth, json={"retention_days": 365}
        )
        assert response.status_code == 403


# ============================================================================
# Audit Log Query Tests
# ============================================================================


class TestGetAuditLogs:
    """Tests for GET /api/audit/logs."""

    @patch("audit_routes.get_audit_logger")
    def test_get_logs_success_default_params(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """SysAdmin can query audit logs with default parameters."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.query_logs.return_value = [
            {"id": 1, "action": "login", "user_id": "user1"}
        ]
        mock_logger.get_decision_count.return_value = 1

        response = client.get("/api/audit/logs", headers=mock_auth_sysadmin)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert len(data["logs"]) == 1
        assert data["pagination"]["limit"] == 100
        assert data["pagination"]["offset"] == 0

    @patch("audit_routes.get_audit_logger")
    def test_get_logs_with_filters(self, mock_get_logger, client, mock_auth_sysadmin):
        """Audit logs can be filtered by date range and decision."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.query_logs.return_value = []
        mock_logger.get_decision_count.return_value = 0

        response = client.get(
            "/api/audit/logs?start_date=2024-01-01&end_date=2024-12-31&decision=continue",
            headers=mock_auth_sysadmin,
        )

        assert response.status_code == 200
        mock_logger.query_logs.assert_called_once_with(
            reference_number=None,
            start_date="2024-01-01",
            end_date="2024-12-31",
            decision="continue",
            user_id=None,
            limit=100,
            offset=0,
        )

    @patch("audit_routes.get_audit_logger")
    def test_get_logs_limit_capped_at_1000(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """Limit parameter should be capped at 1000."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.query_logs.return_value = []
        mock_logger.get_decision_count.return_value = 0

        response = client.get("/api/audit/logs?limit=5000", headers=mock_auth_sysadmin)

        assert response.status_code == 200
        # Verify limit was capped
        call_kwargs = mock_logger.query_logs.call_args[1]
        assert call_kwargs["limit"] == 1000

    @patch("audit_routes.get_audit_logger")
    def test_get_logs_internal_error_returns_500(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """Internal error should return 500."""
        mock_get_logger.side_effect = Exception("DB connection failed")

        response = client.get("/api/audit/logs", headers=mock_auth_sysadmin)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data["success"] is False


# ============================================================================
# Log Count Tests
# ============================================================================


class TestGetAuditLogCount:
    """Tests for GET /api/audit/logs/count."""

    @patch("audit_routes.get_audit_logger")
    def test_get_count_success(self, mock_get_logger, client, mock_auth_sysadmin):
        """SysAdmin can get audit log count."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.get_decision_count.return_value = 42

        response = client.get("/api/audit/logs/count", headers=mock_auth_sysadmin)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["count"] == 42


# ============================================================================
# Report Generation Tests
# ============================================================================


class TestComplianceReport:
    """Tests for GET /api/audit/reports/compliance."""

    @patch("audit_routes.get_audit_logger")
    def test_compliance_report_success(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """SysAdmin can generate compliance report."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.generate_compliance_report.return_value = {
            "total_decisions": 100,
            "continue_count": 80,
            "cancel_count": 20,
        }

        response = client.get(
            "/api/audit/reports/compliance?start_date=2024-01-01&end_date=2024-12-31",
            headers=mock_auth_sysadmin,
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "report" in data

    @patch("audit_routes.get_audit_logger")
    def test_compliance_report_missing_dates_returns_400(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """Missing start_date or end_date should return 400."""
        response = client.get(
            "/api/audit/reports/compliance", headers=mock_auth_sysadmin
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert "required" in data["message"].lower()


class TestUserActivityReport:
    """Tests for GET /api/audit/reports/user/<user_id>."""

    @patch("audit_routes.get_audit_logger")
    def test_user_activity_report_success(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """SysAdmin can get user activity report."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.get_user_activity_report.return_value = {
            "user_id": "user1",
            "total_actions": 50,
        }

        response = client.get(
            "/api/audit/reports/user/user1", headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["report"]["user_id"] == "user1"


# ============================================================================
# Transaction Audit Trail Tests
# ============================================================================


class TestTransactionAuditTrail:
    """Tests for GET /api/audit/transaction-trail."""

    @patch("audit_routes.get_audit_logger")
    def test_transaction_trail_success(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """SysAdmin can get transaction audit trail."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.get_audit_trail_for_transaction.return_value = [
            {"action": "created", "timestamp": "2024-01-01T10:00:00"}
        ]

        response = client.get(
            "/api/audit/transaction-trail?reference_number=REF001"
            "&transaction_date=2024-01-01&transaction_amount=100.50",
            headers=mock_auth_sysadmin,
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

    @patch("audit_routes.get_audit_logger")
    def test_transaction_trail_missing_params_returns_400(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """Missing required parameters should return 400."""
        response = client.get(
            "/api/audit/transaction-trail?reference_number=REF001",
            headers=mock_auth_sysadmin,
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False

    @patch("audit_routes.get_audit_logger")
    def test_transaction_trail_invalid_amount_returns_400(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """Invalid transaction_amount should return 400."""
        response = client.get(
            "/api/audit/transaction-trail?reference_number=REF001"
            "&transaction_date=2024-01-01&transaction_amount=not_a_number",
            headers=mock_auth_sysadmin,
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False


# ============================================================================
# Cleanup Tests
# ============================================================================


class TestCleanupOldLogs:
    """Tests for POST /api/audit/cleanup."""

    @patch("audit_routes.get_audit_logger")
    def test_cleanup_success(self, mock_get_logger, client, mock_auth_sysadmin):
        """SysAdmin can clean up old logs."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.cleanup_old_logs.return_value = (True, 50)

        response = client.post(
            "/api/audit/cleanup",
            headers=mock_auth_sysadmin,
            json={"retention_days": 365},
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["deleted_count"] == 50

    @patch("audit_routes.get_audit_logger")
    def test_cleanup_invalid_retention_days_returns_400(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """Invalid retention_days should return 400."""
        response = client.post(
            "/api/audit/cleanup",
            headers=mock_auth_sysadmin,
            json={"retention_days": -1},
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False


# ============================================================================
# Health Check Tests
# ============================================================================


class TestAuditHealthCheck:
    """Tests for GET /api/audit/health."""

    @patch("audit_routes.get_audit_logger")
    def test_health_check_healthy(self, mock_get_logger, client, mock_auth_sysadmin):
        """Health check returns healthy status."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.get_decision_count.return_value = 100

        response = client.get("/api/audit/health", headers=mock_auth_sysadmin)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["status"] == "healthy"

    @patch("audit_routes.get_audit_logger")
    def test_health_check_unhealthy(self, mock_get_logger, client, mock_auth_sysadmin):
        """Health check returns unhealthy when DB fails."""
        mock_get_logger.side_effect = Exception("Connection refused")

        response = client.get("/api/audit/health", headers=mock_auth_sysadmin)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["status"] == "unhealthy"


# ============================================================================
# Error-Envelope Tests (error_payload shape: error + error_id, generic message)
#
# Task 9 (code-quality-fixes-2026-10-28): the audit health check routes its
# caught-exception path through routes.error_responses.error_payload. These tests
# pin the caller-safe envelope — a generic message plus a correlation error_id,
# with the raw exception text NOT leaked (CodeQL py/stack-trace-exposure, steering
# rule 30).
# ============================================================================


class TestAuditErrorEnvelope:
    """The caught-exception path returns the generic error_payload envelope."""

    @patch("audit_routes.get_audit_logger")
    def test_health_check_unhealthy_uses_error_envelope(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """An unhealthy health check returns the error_payload envelope.

        The body carries a generic ``error`` message + a correlation ``error_id``,
        the raw exception text does not leak, and the status stays ``unhealthy``.
        """
        mock_get_logger.side_effect = Exception("secret-internal-table-name")

        response = client.get("/api/audit/health", headers=mock_auth_sysadmin)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["status"] == "unhealthy"
        # Generic, caller-safe message + correlation id; raw exception must not leak.
        assert data["error"] == "Audit system health check failed"
        assert "secret-internal-table-name" not in json.dumps(data)
        assert "error_id" in data
        assert "timestamp" in data

    @patch("audit_routes.get_audit_logger")
    def test_count_internal_error_returns_500(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """An error while counting returns a 500 with the success=False shape."""
        mock_get_logger.side_effect = Exception("DB down")

        response = client.get("/api/audit/logs/count", headers=mock_auth_sysadmin)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["error"] == "Failed to get count"


# ============================================================================
# CSV Export Tests (happy path + export-failure path)
# ============================================================================


class TestExportLogsToCsv:
    """Tests for GET /api/audit/export/csv."""

    def test_export_csv_unauthenticated_returns_401_or_403(self, client):
        """CSV export is SysAdmin-only — unauthenticated is rejected."""
        auth_error = {
            "statusCode": 401,
            "body": '{"error": "Unauthorized", "message": "Missing or invalid token"}',
        }
        with patch(
            "auth.cognito_utils.extract_user_credentials",
            return_value=(None, None, auth_error),
        ):
            response = client.get("/api/audit/export/csv")
        assert response.status_code in (401, 403)

    @patch("audit_routes.get_audit_logger")
    def test_export_csv_success_sends_file(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """A successful export streams a CSV attachment back to the caller."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        def _write_csv(output_file, start_date=None, end_date=None):
            # The route creates the temp file; the logger fills it with content.
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("id,action\n1,login\n")
            return True

        mock_logger.export_logs_to_csv.side_effect = _write_csv

        response = client.get("/api/audit/export/csv", headers=mock_auth_sysadmin)

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert b"login" in response.data

    @patch("audit_routes.get_audit_logger")
    def test_export_csv_failure_returns_500(
        self, mock_get_logger, client, mock_auth_sysadmin
    ):
        """When the export produces nothing, the route returns 500 success=False."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_logger.export_logs_to_csv.return_value = False

        response = client.get("/api/audit/export/csv", headers=mock_auth_sysadmin)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data["success"] is False
