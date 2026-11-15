"""
Unit Tests for Domain Verification Background Job

Tests run_domain_verification_check, which periodically checks the
CloudFront-managed certificate of each pending custom domain's distribution
tenant and marks the domain active once the certificate is issued.
"""

import os
import sys
from unittest.mock import Mock

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services.domain_verification_job import (
    _update_status,
    run_domain_verification_check,
)


def _row(domain_id, tenant, domain, status="validating"):
    return {
        "id": domain_id,
        "administration": tenant,
        "slug": domain.split(".")[1],
        "domain": domain,
        "acm_certificate_arn": None,
        "verification_status": status,
    }


class TestRunDomainVerificationCheck:
    """Tests for run_domain_verification_check main function."""

    @pytest.fixture
    def mock_db(self):
        """Create a mocked DatabaseManager."""
        return Mock()

    @pytest.fixture
    def mock_cf_service(self):
        """Create a mocked CloudFrontDomainService."""
        return Mock()

    def test_no_pending_domains(self, mock_db, mock_cf_service):
        """When no pending domains exist, returns zero counts."""
        mock_db.execute_query.return_value = []

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 0, "activated": 0, "failed": 0, "pending": 0}
        mock_db.execute_query.assert_called_once()
        assert "verification_status IN" in mock_db.execute_query.call_args[0][0]

    def test_no_pending_domains_none_result(self, mock_db, mock_cf_service):
        """When query returns None, returns zero counts."""
        mock_db.execute_query.return_value = None

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 0, "activated": 0, "failed": 0, "pending": 0}

    def test_domain_issued_marks_active(self, mock_db, mock_cf_service):
        """Issued managed certificate -> domain marked active, cert ARN stored."""
        mock_db.execute_query.side_effect = [
            [_row(1, "TenantA", "www.tenant-a.nl")],
            None,
        ]
        mock_cf_service.get_domain_status.return_value = {
            "success": True,
            "status": "ISSUED",
            "certificate_arn": "arn:aws:acm:us-east-1:123:certificate/abc",
        }

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 1, "failed": 0, "pending": 0}
        mock_cf_service.get_domain_status.assert_called_once_with("www.tenant-a.nl")

        update_call = mock_db.execute_query.call_args_list[1]
        assert "is_active = TRUE" in update_call[0][0]
        assert "verification_status = 'issued'" in update_call[0][0]
        assert "administration = %s" in update_call[0][0]
        assert update_call[0][1] == (
            "arn:aws:acm:us-east-1:123:certificate/abc",
            1,
            "TenantA",
        )

    def test_domain_failed_updates_status(self, mock_db, mock_cf_service):
        """FAILED (incl. validation timed out) marks the domain failed."""
        mock_db.execute_query.side_effect = [
            [_row(2, "TenantB", "www.tenant-b.nl", "pending_dns")],
            None,
        ]
        mock_cf_service.get_domain_status.return_value = {
            "success": True,
            "status": "FAILED",
        }

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 1, "pending": 0}
        update_call = mock_db.execute_query.call_args_list[1]
        assert "verification_status = %s" in update_call[0][0]
        assert update_call[0][1] == ("failed", 2, "TenantB")

    def test_domain_still_pending(self, mock_db, mock_cf_service):
        """PENDING_VALIDATION is counted as still pending, no DB write."""
        mock_db.execute_query.side_effect = [
            [_row(3, "TenantC", "www.tenant-c.nl", "pending_dns")],
        ]
        mock_cf_service.get_domain_status.return_value = {
            "success": True,
            "status": "PENDING_VALIDATION",
        }

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 0, "pending": 1}
        assert mock_db.execute_query.call_count == 1

    def test_status_lookup_error_counts_failed_keeps_pending(
        self, mock_db, mock_cf_service
    ):
        """A lookup error is transient: counted, but the record is NOT marked failed."""
        mock_db.execute_query.side_effect = [[_row(4, "TenantD", "www.tenant-d.nl")]]
        mock_cf_service.get_domain_status.return_value = {
            "success": False,
            "error": "Failed to check certificate status.",
        }

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 1, "pending": 0}
        assert mock_db.execute_query.call_count == 1  # no status UPDATE
        mock_cf_service.create_domain_tenant.assert_not_called()

    def test_no_tenant_dns_not_ready_stays_pending(self, mock_db, mock_cf_service):
        """No tenant + DNS not pointing yet -> still pending, retried next run."""
        mock_db.execute_query.side_effect = [
            [_row(5, "TenantE", "www.tenant-e.nl", "pending_dns")]
        ]
        mock_cf_service.get_domain_status.return_value = {
            "success": False,
            "not_found": True,
        }
        mock_cf_service.create_domain_tenant.return_value = {
            "success": False,
            "dns_not_ready": True,
        }

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 0, "pending": 1}
        mock_cf_service.create_domain_tenant.assert_called_once_with(
            "www.tenant-e.nl", "tenant-e"
        )
        assert mock_db.execute_query.call_count == 1

    def test_no_tenant_dns_ready_creates_tenant(self, mock_db, mock_cf_service):
        """No tenant + DNS pointing -> tenant created, cert now pending."""
        mock_db.execute_query.side_effect = [
            [_row(6, "TenantF", "www.tenant-f.nl", "pending_dns")]
        ]
        mock_cf_service.get_domain_status.return_value = {
            "success": False,
            "not_found": True,
        }
        mock_cf_service.create_domain_tenant.return_value = {
            "success": True,
            "tenant_id": "dt_6",
            "routing_endpoint": "d1.cloudfront.net",
        }

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 0, "pending": 1}
        mock_cf_service.create_domain_tenant.assert_called_once_with(
            "www.tenant-f.nl", "tenant-f"
        )

    def test_multiple_domains_mixed_statuses(self, mock_db, mock_cf_service):
        """Multiple domains with different statuses are processed correctly."""
        mock_db.execute_query.side_effect = [
            [
                _row(1, "TenantA", "www.tenant-a.nl"),
                _row(2, "TenantB", "www.tenant-b.nl", "pending_dns"),
                _row(3, "TenantC", "www.tenant-c.nl"),
            ],
            None,
            None,
        ]
        mock_cf_service.get_domain_status.side_effect = [
            {"success": True, "status": "ISSUED", "certificate_arn": "arn:a"},
            {"success": True, "status": "PENDING_VALIDATION"},
            {"success": True, "status": "FAILED"},
        ]

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 3, "activated": 1, "failed": 1, "pending": 1}

    def test_unexpected_exception_is_caught(self, mock_db, mock_cf_service):
        """Unexpected exception during processing is caught and counted as failed."""
        mock_db.execute_query.side_effect = [[_row(7, "TenantG", "www.tenant-g.nl")]]
        mock_cf_service.get_domain_status.side_effect = RuntimeError("Boom")

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 1, "pending": 0}


class TestUpdateStatus:
    """Tests for _update_status helper function."""

    @pytest.fixture
    def mock_db(self):
        return Mock()

    def test_update_status_to_failed(self, mock_db):
        """Updates verification_status with correct params."""
        _update_status(mock_db, 42, "ExampleTenant", "failed")

        call_args = mock_db.execute_query.call_args
        assert "verification_status = %s" in call_args[0][0]
        assert "WHERE id = %s AND administration = %s" in call_args[0][0]
        assert call_args[0][1] == ("failed", 42, "ExampleTenant")
        assert call_args[1] == {"fetch": False, "commit": True}
