"""
Unit Tests for Domain Verification Background Job

Tests run_domain_verification_check function which periodically
checks pending custom domains and auto-activates issued certificates.
"""

import os
import sys
from unittest.mock import Mock, patch, call

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services.domain_verification_job import (
    run_domain_verification_check,
    _activate_domain,
    _update_status,
)


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
        # Should only call the SELECT query
        mock_db.execute_query.assert_called_once()
        assert "verification_status IN" in mock_db.execute_query.call_args[0][0]

    def test_no_pending_domains_none_result(self, mock_db, mock_cf_service):
        """When query returns None, returns zero counts."""
        mock_db.execute_query.return_value = None

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 0, "activated": 0, "failed": 0, "pending": 0}

    def test_domain_issued_activates_successfully(self, mock_db, mock_cf_service):
        """Domain with ISSUED certificate is activated."""
        mock_db.execute_query.side_effect = [
            # First call: SELECT pending domains
            [
                {
                    "id": 1,
                    "administration": "TenantA",
                    "slug": "tenant-a",
                    "domain": "www.tenant-a.nl",
                    "acm_certificate_arn": "arn:aws:acm:us-east-1:123:certificate/abc",
                    "verification_status": "validating",
                }
            ],
            # Second call: UPDATE (activation)
            None,
        ]

        mock_cf_service.describe_certificate.return_value = {
            "success": True,
            "status": "ISSUED",
            "validation_options": [],
        }
        mock_cf_service.add_domain_to_distribution.return_value = True
        mock_cf_service.put_kvs_mapping.return_value = True

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 1, "failed": 0, "pending": 0}

        # Verify CloudFront service calls
        mock_cf_service.describe_certificate.assert_called_once_with(
            "arn:aws:acm:us-east-1:123:certificate/abc"
        )
        mock_cf_service.add_domain_to_distribution.assert_called_once_with(
            "www.tenant-a.nl", "arn:aws:acm:us-east-1:123:certificate/abc"
        )
        mock_cf_service.put_kvs_mapping.assert_called_once_with(
            "www.tenant-a.nl", "tenant-a"
        )

        # Verify DB update sets is_active = TRUE
        update_call = mock_db.execute_query.call_args_list[1]
        assert "is_active = TRUE" in update_call[0][0]
        assert "verification_status = 'issued'" in update_call[0][0]
        assert update_call[0][1] == (1, "TenantA")

    def test_domain_failed_updates_status(self, mock_db, mock_cf_service):
        """Domain with FAILED certificate status is marked as failed."""
        mock_db.execute_query.side_effect = [
            # First call: SELECT pending domains
            [
                {
                    "id": 2,
                    "administration": "TenantB",
                    "slug": "tenant-b",
                    "domain": "www.tenant-b.nl",
                    "acm_certificate_arn": "arn:aws:acm:us-east-1:123:certificate/def",
                    "verification_status": "pending_dns",
                }
            ],
            # Second call: UPDATE status to failed
            None,
        ]

        mock_cf_service.describe_certificate.return_value = {
            "success": True,
            "status": "FAILED",
            "validation_options": [],
        }

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 1, "pending": 0}

        # Verify DB update sets status to 'failed'
        update_call = mock_db.execute_query.call_args_list[1]
        assert "verification_status = %s" in update_call[0][0]
        assert update_call[0][1] == ("failed", 2, "TenantB")

    def test_domain_still_pending(self, mock_db, mock_cf_service):
        """Domain with PENDING_VALIDATION certificate is counted as still pending."""
        mock_db.execute_query.side_effect = [
            # First call: SELECT pending domains
            [
                {
                    "id": 3,
                    "administration": "TenantC",
                    "slug": "tenant-c",
                    "domain": "www.tenant-c.nl",
                    "acm_certificate_arn": "arn:aws:acm:us-east-1:123:certificate/ghi",
                    "verification_status": "pending_dns",
                }
            ],
        ]

        mock_cf_service.describe_certificate.return_value = {
            "success": True,
            "status": "PENDING_VALIDATION",
            "validation_options": [],
        }

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 0, "pending": 1}

        # Should NOT update the DB for pending domains
        assert mock_db.execute_query.call_count == 1  # Only the initial SELECT

    def test_describe_certificate_failure(self, mock_db, mock_cf_service):
        """When describe_certificate returns failure, domain is marked as failed."""
        mock_db.execute_query.side_effect = [
            # First call: SELECT pending domains
            [
                {
                    "id": 4,
                    "administration": "TenantD",
                    "slug": "tenant-d",
                    "domain": "www.tenant-d.nl",
                    "acm_certificate_arn": "arn:aws:acm:us-east-1:123:certificate/jkl",
                    "verification_status": "validating",
                }
            ],
            # Second call: UPDATE status to failed
            None,
        ]

        mock_cf_service.describe_certificate.return_value = {
            "success": False,
            "error": "Certificate not found",
        }

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 1, "pending": 0}

        # Verify status was updated to failed
        update_call = mock_db.execute_query.call_args_list[1]
        assert "verification_status = %s" in update_call[0][0]
        assert update_call[0][1] == ("failed", 4, "TenantD")

    def test_multiple_domains_mixed_statuses(self, mock_db, mock_cf_service):
        """Multiple domains with different statuses are processed correctly."""
        mock_db.execute_query.side_effect = [
            # First call: SELECT pending domains — 3 domains
            [
                {
                    "id": 1,
                    "administration": "TenantA",
                    "slug": "tenant-a",
                    "domain": "www.tenant-a.nl",
                    "acm_certificate_arn": "arn:cert-a",
                    "verification_status": "validating",
                },
                {
                    "id": 2,
                    "administration": "TenantB",
                    "slug": "tenant-b",
                    "domain": "www.tenant-b.nl",
                    "acm_certificate_arn": "arn:cert-b",
                    "verification_status": "pending_dns",
                },
                {
                    "id": 3,
                    "administration": "TenantC",
                    "slug": "tenant-c",
                    "domain": "www.tenant-c.nl",
                    "acm_certificate_arn": "arn:cert-c",
                    "verification_status": "validating",
                },
            ],
            # Second call: UPDATE for domain 1 (activation)
            None,
            # Third call: UPDATE for domain 3 (failed status)
            None,
        ]

        # domain 1: ISSUED, domain 2: PENDING, domain 3: FAILED
        mock_cf_service.describe_certificate.side_effect = [
            {"success": True, "status": "ISSUED", "validation_options": []},
            {"success": True, "status": "PENDING_VALIDATION", "validation_options": []},
            {"success": True, "status": "FAILED", "validation_options": []},
        ]
        mock_cf_service.add_domain_to_distribution.return_value = True
        mock_cf_service.put_kvs_mapping.return_value = True

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 3, "activated": 1, "failed": 1, "pending": 1}

    def test_activation_cloudfront_failure(self, mock_db, mock_cf_service):
        """When add_domain_to_distribution fails, domain counts as failed."""
        mock_db.execute_query.side_effect = [
            [
                {
                    "id": 5,
                    "administration": "TenantE",
                    "slug": "tenant-e",
                    "domain": "www.tenant-e.nl",
                    "acm_certificate_arn": "arn:cert-e",
                    "verification_status": "validating",
                }
            ],
        ]

        mock_cf_service.describe_certificate.return_value = {
            "success": True,
            "status": "ISSUED",
            "validation_options": [],
        }
        mock_cf_service.add_domain_to_distribution.return_value = False

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 1, "pending": 0}

    def test_activation_kvs_failure(self, mock_db, mock_cf_service):
        """When put_kvs_mapping fails, domain counts as failed."""
        mock_db.execute_query.side_effect = [
            [
                {
                    "id": 6,
                    "administration": "TenantF",
                    "slug": "tenant-f",
                    "domain": "www.tenant-f.nl",
                    "acm_certificate_arn": "arn:cert-f",
                    "verification_status": "validating",
                }
            ],
        ]

        mock_cf_service.describe_certificate.return_value = {
            "success": True,
            "status": "ISSUED",
            "validation_options": [],
        }
        mock_cf_service.add_domain_to_distribution.return_value = True
        mock_cf_service.put_kvs_mapping.return_value = False

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 1, "pending": 0}

    def test_unexpected_exception_is_caught(self, mock_db, mock_cf_service):
        """Unexpected exception during processing is caught and counted as failed."""
        mock_db.execute_query.side_effect = [
            [
                {
                    "id": 7,
                    "administration": "TenantG",
                    "slug": "tenant-g",
                    "domain": "www.tenant-g.nl",
                    "acm_certificate_arn": "arn:cert-g",
                    "verification_status": "validating",
                }
            ],
        ]

        mock_cf_service.describe_certificate.side_effect = RuntimeError("Boom")

        result = run_domain_verification_check(db=mock_db, cf_service=mock_cf_service)

        assert result == {"processed": 1, "activated": 0, "failed": 1, "pending": 0}


class TestActivateDomain:
    """Tests for _activate_domain helper function."""

    @pytest.fixture
    def mock_db(self):
        return Mock()

    @pytest.fixture
    def mock_cf_service(self):
        return Mock()

    def test_activate_success(self, mock_db, mock_cf_service):
        """Successful activation calls all services and updates DB."""
        mock_cf_service.add_domain_to_distribution.return_value = True
        mock_cf_service.put_kvs_mapping.return_value = True

        result = _activate_domain(
            mock_db, mock_cf_service, 42, "www.example.nl",
            "example", "arn:cert-123", "ExampleTenant"
        )

        assert result is True
        mock_cf_service.add_domain_to_distribution.assert_called_once_with(
            "www.example.nl", "arn:cert-123"
        )
        mock_cf_service.put_kvs_mapping.assert_called_once_with(
            "www.example.nl", "example"
        )

        # Verify DB update
        update_call = mock_db.execute_query.call_args
        assert "is_active = TRUE" in update_call[0][0]
        assert update_call[0][1] == (42, "ExampleTenant")
        assert update_call[1] == {"fetch": False, "commit": True}

    def test_activate_cloudfront_failure(self, mock_db, mock_cf_service):
        """CloudFront failure returns False without calling KVS or DB."""
        mock_cf_service.add_domain_to_distribution.return_value = False

        result = _activate_domain(
            mock_db, mock_cf_service, 42, "www.example.nl",
            "example", "arn:cert-123", "ExampleTenant"
        )

        assert result is False
        mock_cf_service.put_kvs_mapping.assert_not_called()
        mock_db.execute_query.assert_not_called()

    def test_activate_kvs_failure(self, mock_db, mock_cf_service):
        """KVS failure returns False without updating DB."""
        mock_cf_service.add_domain_to_distribution.return_value = True
        mock_cf_service.put_kvs_mapping.return_value = False

        result = _activate_domain(
            mock_db, mock_cf_service, 42, "www.example.nl",
            "example", "arn:cert-123", "ExampleTenant"
        )

        assert result is False
        mock_db.execute_query.assert_not_called()


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
