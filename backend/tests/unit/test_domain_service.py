"""
Unit Tests for DomainService

Tests enable_jabaki and disable_jabaki methods.
Uses unittest.mock to mock DatabaseManager.
"""

import os
import sys
from unittest.mock import Mock

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services.domain_service import DomainService


class TestEnableJabaki:
    """Tests for DomainService.enable_jabaki."""

    @pytest.fixture
    def mock_db(self):
        """Create a mocked DatabaseManager."""
        return Mock()

    @pytest.fixture
    def service(self, mock_db):
        """Create DomainService with mocked DB."""
        return DomainService(db_manager=mock_db)

    def test_enable_jabaki_success(self, service, mock_db):
        """Enable Jabaki when slug exists — returns domain URL."""
        mock_db.execute_query.side_effect = [
            # First call: SELECT slug
            [{"slug": "acme-rentals"}],
            # Second call: UPDATE (returns None for write)
            None,
        ]

        result = service.enable_jabaki("TestTenant")

        assert result["success"] is True
        assert result["domain"] == "acme-rentals.jabaki.nl"
        assert result["message"] == "Jabaki subdomain is now active."

        # Verify UPDATE was called with correct params
        update_call = mock_db.execute_query.call_args_list[1]
        assert "jabaki_enabled = TRUE" in update_call[0][0]
        assert "jabaki_enabled_at = NOW()" in update_call[0][0]
        assert update_call[0][1] == ("TestTenant",)
        assert update_call[1] == {"fetch": False, "commit": True}

    def test_enable_jabaki_no_slug_row(self, service, mock_db):
        """Enable Jabaki when no slug record exists — returns error."""
        mock_db.execute_query.return_value = []

        result = service.enable_jabaki("TestTenant")

        assert result["success"] is False
        assert "No slug configured" in result["error"]

    def test_enable_jabaki_slug_is_none(self, service, mock_db):
        """Enable Jabaki when slug column is None — returns error."""
        mock_db.execute_query.return_value = [{"slug": None}]

        result = service.enable_jabaki("TestTenant")

        assert result["success"] is False
        assert "No slug configured" in result["error"]

    def test_enable_jabaki_empty_result(self, service, mock_db):
        """Enable Jabaki when query returns None — returns error."""
        mock_db.execute_query.return_value = None

        result = service.enable_jabaki("TestTenant")

        assert result["success"] is False
        assert "No slug configured" in result["error"]


class TestDisableJabaki:
    """Tests for DomainService.disable_jabaki."""

    @pytest.fixture
    def mock_db(self):
        """Create a mocked DatabaseManager."""
        return Mock()

    @pytest.fixture
    def service(self, mock_db):
        """Create DomainService with mocked DB."""
        return DomainService(db_manager=mock_db)

    def test_disable_jabaki_success(self, service, mock_db):
        """Disable Jabaki — always succeeds with message."""
        mock_db.execute_query.return_value = None

        result = service.disable_jabaki("TestTenant")

        assert result["success"] is True
        assert result["message"] == "Jabaki subdomain is now disabled."

        # Verify UPDATE was called correctly
        call_args = mock_db.execute_query.call_args
        assert "jabaki_enabled = FALSE" in call_args[0][0]
        assert call_args[0][1] == ("TestTenant",)
        assert call_args[1] == {"fetch": False, "commit": True}


class TestRegisterCustomDomain:
    """Tests for DomainService.register_custom_domain (Task 4.1)."""

    @pytest.fixture
    def mock_db(self):
        """Create a mocked DatabaseManager."""
        return Mock()

    @pytest.fixture
    def service(self, mock_db):
        """Create DomainService with mocked DB."""
        return DomainService(db_manager=mock_db)

    def test_register_domain_empty(self, service, mock_db):
        """Empty domain returns validation error."""
        result = service.register_custom_domain("TestTenant", "")
        assert result["success"] is False
        assert "required" in result["error"].lower()

    def test_register_domain_ip_address(self, service, mock_db):
        """IP address is rejected."""
        result = service.register_custom_domain("TestTenant", "192.168.1.1")
        assert result["success"] is False
        assert "IP" in result["error"]

    def test_register_domain_jabaki_subdomain(self, service, mock_db):
        """Jabaki.nl subdomains are rejected."""
        result = service.register_custom_domain("TestTenant", "my-slug.jabaki.nl")
        assert result["success"] is False
        assert "jabaki" in result["error"].lower()

    def test_register_domain_no_tld(self, service, mock_db):
        """Domain without TLD is rejected."""
        result = service.register_custom_domain("TestTenant", "nodomain")
        assert result["success"] is False
        assert "TLD" in result["error"] or "format" in result["error"].lower()

    def test_register_domain_invalid_chars(self, service, mock_db):
        """Domain with invalid characters is rejected."""
        result = service.register_custom_domain("TestTenant", "my domain!.nl")
        assert result["success"] is False
        assert "format" in result["error"].lower()

    def test_register_domain_already_registered_same_tenant(self, service, mock_db):
        """Domain already registered by same tenant returns error."""
        mock_db.execute_query.return_value = [{"id": 1, "administration": "TestTenant"}]

        result = service.register_custom_domain("TestTenant", "www.acme-rentals.nl")

        assert result["success"] is False
        assert "already registered" in result["error"]

    def test_register_domain_already_registered_other_tenant(self, service, mock_db):
        """Domain already registered by another tenant returns error."""
        mock_db.execute_query.return_value = [
            {"id": 1, "administration": "OtherTenant"}
        ]

        result = service.register_custom_domain("TestTenant", "www.acme-rentals.nl")

        assert result["success"] is False
        assert "another tenant" in result["error"]

    def test_register_domain_no_slug(self, service, mock_db):
        """Tenant without slug configured returns error."""
        mock_db.execute_query.side_effect = [
            # First call: check domain uniqueness — not found
            [],
            # Second call: get slug — no slug
            [],
        ]

        result = service.register_custom_domain("TestTenant", "www.acme-rentals.nl")

        assert result["success"] is False
        assert "slug" in result["error"].lower()

    @pytest.fixture
    def mock_cf_service(self):
        """Create a mocked CloudFrontDomainService."""
        with pytest.MonkeyPatch.context() as m:
            mock_cf = Mock()
            mock_cf.get_routing_endpoint.return_value = "d1234abcd.cloudfront.net"
            mock_cf.create_domain_tenant.return_value = {
                "success": True,
                "tenant_id": "dt_123",
                "routing_endpoint": "d1234abcd.cloudfront.net",
            }
            yield mock_cf

    def test_register_domain_success(self, service, mock_db, mock_cf_service):
        """Successful domain registration returns DNS instructions."""
        from unittest.mock import patch

        mock_db.execute_query.side_effect = [
            # First call: check domain uniqueness — not found
            [],
            # Second call: get slug
            [{"slug": "acme-rentals"}],
            # Third call: INSERT (returns None)
            None,
        ]

        with patch(
            "services.cloudfront_domain_service.CloudFrontDomainService",
            return_value=mock_cf_service,
        ):
            result = service.register_custom_domain("TestTenant", "www.acme-rentals.nl")

        assert result["success"] is True
        data = result["data"]
        assert data["domain"] == "www.acme-rentals.nl"
        assert data["status"] == "pending_dns"

        # Check DNS instructions: ONE routing CNAME (CloudFront validates the
        # managed certificate over HTTP itself — no validation record)
        instructions = data["dns_instructions"]
        assert instructions["type"] == "CNAME"
        assert instructions["records"] == [
            {
                "purpose": "routing",
                "name": "www.acme-rentals.nl",
                "value": "d1234abcd.cloudfront.net",
            }
        ]

        # Tenant created for the tenant's slug
        mock_cf_service.create_domain_tenant.assert_called_once_with(
            "www.acme-rentals.nl", "acme-rentals"
        )

        # INSERT stores the routing pair, includes the tenant, no cert yet
        insert_call = mock_db.execute_query.call_args_list[2]
        assert "INSERT INTO tenant_custom_domains" in insert_call[0][0]
        assert insert_call[0][1] == (
            "TestTenant",
            "acme-rentals",
            "www.acme-rentals.nl",
            "www.acme-rentals.nl",
            "d1234abcd.cloudfront.net",
        )

    def test_register_domain_tenant_creation_failure(self, service, mock_db):
        """Distribution tenant creation failure returns error, no INSERT."""
        from unittest.mock import patch

        mock_db.execute_query.side_effect = [
            # First call: check domain uniqueness — not found
            [],
            # Second call: get slug
            [{"slug": "acme-rentals"}],
        ]

        mock_cf = Mock()
        mock_cf.create_domain_tenant.return_value = {
            "success": False,
            "error": "Failed to set up the custom domain.",
        }

        with patch(
            "services.cloudfront_domain_service.CloudFrontDomainService",
            return_value=mock_cf,
        ):
            result = service.register_custom_domain("TestTenant", "www.acme-rentals.nl")

        assert result["success"] is False
        assert "custom domain" in result["error"].lower()
        # Only uniqueness + slug lookups ran; nothing was stored
        assert mock_db.execute_query.call_count == 2

    def test_register_domain_valid_formats(self, service, mock_db):
        """Valid domain formats pass validation (validation-only check)."""
        # These should all pass the format validation step
        # (they will fail at the DB query step)
        valid_domains = [
            "www.example.nl",
            "example.nl",
            "my-site.example.com",
            "sub.domain.example.co.uk",
        ]
        for domain in valid_domains:
            # Access private method for unit testing validation
            error = service._validate_domain_format(domain)
            assert error is None, f"Domain '{domain}' should be valid but got: {error}"

    def test_register_domain_invalid_formats(self, service, mock_db):
        """Invalid domain formats are caught by validation."""
        invalid_domains = [
            "",
            "nodot",
            "192.168.1.1",
            "10.0.0.1",
            "test.jabaki.nl",
            "my slug.nl",
            "-startwithhyphen.nl",
        ]
        for domain in invalid_domains:
            error = service._validate_domain_format(domain)
            assert error is not None, f"Domain '{domain}' should be invalid but passed"


class TestVerifyCustomDomain:
    """Tests for DomainService.verify_custom_domain (Task 4.2)."""

    @pytest.fixture
    def mock_db(self):
        """Create a mocked DatabaseManager."""
        return Mock()

    @pytest.fixture
    def service(self, mock_db):
        """Create DomainService with mocked DB."""
        return DomainService(db_manager=mock_db)

    def test_verify_no_custom_domain_registered(self, service, mock_db):
        """Verify when no custom domain exists returns error."""
        mock_db.execute_query.return_value = []

        result = service.verify_custom_domain("TestTenant")

        assert result["success"] is False
        assert "No custom domain" in result["error"]

    def test_verify_cert_issued_activates_domain(self, service, mock_db):
        """Verify when cert is ISSUED activates the domain."""
        from unittest.mock import patch

        mock_db.execute_query.side_effect = [
            # First call: SELECT custom domain record
            [
                {
                    "id": 42,
                    "domain": "www.acme-rentals.nl",
                    "slug": "acme-rentals",
                    "acm_certificate_arn": "arn:aws:acm:us-east-1:123:certificate/abc",
                    "verification_status": "validating",
                    "is_active": False,
                }
            ],
            # Second call: UPDATE (returns None)
            None,
        ]

        mock_cf = Mock()
        mock_cf.get_domain_status.return_value = {
            "success": True,
            "status": "ISSUED",
            "certificate_arn": "arn:aws:acm:us-east-1:123:certificate/managed",
        }

        with patch(
            "services.cloudfront_domain_service.CloudFrontDomainService",
            return_value=mock_cf,
        ):
            result = service.verify_custom_domain("TestTenant")

        assert result["success"] is True
        data = result["data"]
        assert data["domain"] == "www.acme-rentals.nl"
        assert data["status"] == "issued"
        assert data["is_active"] is True
        assert "active" in data["message"].lower()

        # Status is read from the domain's distribution tenant
        mock_cf.get_domain_status.assert_called_once_with("www.acme-rentals.nl")

        # Verify DB update (stores the managed cert ARN, tenant-scoped)
        update_call = mock_db.execute_query.call_args_list[1]
        assert "is_active = TRUE" in update_call[0][0]
        assert "verification_status = 'issued'" in update_call[0][0]
        assert "administration = %s" in update_call[0][0]
        assert update_call[0][1] == (
            "arn:aws:acm:us-east-1:123:certificate/managed",
            42,
            "TestTenant",
        )

    def test_verify_cert_pending_returns_validating(self, service, mock_db):
        """Verify when cert is PENDING_VALIDATION returns validating status."""
        from unittest.mock import patch

        mock_db.execute_query.side_effect = [
            # First call: SELECT custom domain record
            [
                {
                    "id": 42,
                    "domain": "www.acme-rentals.nl",
                    "slug": "acme-rentals",
                    "acm_certificate_arn": "arn:aws:acm:us-east-1:123:certificate/abc",
                    "verification_status": "pending_dns",
                    "is_active": False,
                }
            ],
            # Second call: UPDATE (returns None)
            None,
        ]

        mock_cf = Mock()
        mock_cf.get_domain_status.return_value = {
            "success": True,
            "status": "PENDING_VALIDATION",
        }

        with patch(
            "services.cloudfront_domain_service.CloudFrontDomainService",
            return_value=mock_cf,
        ):
            result = service.verify_custom_domain("TestTenant")

        assert result["success"] is True
        data = result["data"]
        assert data["domain"] == "www.acme-rentals.nl"
        assert data["status"] == "validating"
        assert data["is_active"] is False
        assert "30 minutes" in data["message"]

        # Verify DB update to validating
        update_call = mock_db.execute_query.call_args_list[1]
        assert "verification_status = 'validating'" in update_call[0][0]

    def test_verify_already_active_returns_immediately(self, service, mock_db):
        """Verify when domain is already active returns without calling AWS."""
        mock_db.execute_query.return_value = [
            {
                "id": 42,
                "domain": "www.acme-rentals.nl",
                "slug": "acme-rentals",
                "acm_certificate_arn": "arn:aws:acm:us-east-1:123:certificate/abc",
                "verification_status": "issued",
                "is_active": True,
            }
        ]

        result = service.verify_custom_domain("TestTenant")

        assert result["success"] is True
        data = result["data"]
        assert data["status"] == "issued"
        assert data["is_active"] is True
        # Only one DB call (SELECT), no UPDATE
        assert mock_db.execute_query.call_count == 1

    def test_verify_cert_failed_returns_failure(self, service, mock_db):
        """Verify when cert status is FAILED returns failure message."""
        from unittest.mock import patch

        mock_db.execute_query.side_effect = [
            [
                {
                    "id": 42,
                    "domain": "www.acme-rentals.nl",
                    "slug": "acme-rentals",
                    "acm_certificate_arn": "arn:aws:acm:us-east-1:123:certificate/abc",
                    "verification_status": "validating",
                    "is_active": False,
                }
            ],
            None,
        ]

        mock_cf = Mock()
        mock_cf.get_domain_status.return_value = {
            "success": True,
            "status": "FAILED",
        }

        with patch(
            "services.cloudfront_domain_service.CloudFrontDomainService",
            return_value=mock_cf,
        ):
            result = service.verify_custom_domain("TestTenant")

        assert result["success"] is True
        data = result["data"]
        assert data["status"] == "failed"
        assert data["is_active"] is False
        assert "failed" in data["message"].lower()


class TestRemoveCustomDomain:
    """Tests for DomainService.remove_custom_domain (Task 4.3)."""

    @pytest.fixture
    def mock_db(self):
        """Create a mocked DatabaseManager."""
        return Mock()

    @pytest.fixture
    def service(self, mock_db):
        """Create DomainService with mocked DB."""
        return DomainService(db_manager=mock_db)

    def test_remove_no_custom_domain_registered(self, service, mock_db):
        """Remove when no custom domain exists returns error."""
        mock_db.execute_query.return_value = []

        result = service.remove_custom_domain("TestTenant")

        assert result["success"] is False
        assert "No custom domain" in result["error"]

    def test_remove_success_full_cleanup(self, service, mock_db):
        """Remove performs all cleanup steps and deletes record."""
        from unittest.mock import patch

        mock_db.execute_query.side_effect = [
            # First call: SELECT custom domain record
            [
                {
                    "id": 42,
                    "domain": "www.acme-rentals.nl",
                    "acm_certificate_arn": "arn:aws:acm:us-east-1:123:certificate/abc",
                }
            ],
            # Second call: DELETE (returns None)
            None,
        ]

        mock_cf = Mock()
        mock_cf.delete_domain_tenant.return_value = True
        mock_cf.delete_certificate.return_value = True

        with patch(
            "services.cloudfront_domain_service.CloudFrontDomainService",
            return_value=mock_cf,
        ):
            result = service.remove_custom_domain("TestTenant")

        assert result["success"] is True
        assert result["message"] == "Custom domain removed."

        # Verify all cleanup steps were called
        mock_cf.delete_domain_tenant.assert_called_once_with("www.acme-rentals.nl")
        mock_cf.delete_certificate.assert_called_once_with(
            "arn:aws:acm:us-east-1:123:certificate/abc"
        )

        # Verify DELETE query includes tenant isolation
        delete_call = mock_db.execute_query.call_args_list[1]
        assert "DELETE FROM tenant_custom_domains" in delete_call[0][0]
        assert "administration = %s" in delete_call[0][0]
        assert delete_call[0][1] == (42, "TestTenant")

    def test_remove_without_certificate_arn(self, service, mock_db):
        """Remove works even when certificate_arn is None."""
        from unittest.mock import patch

        mock_db.execute_query.side_effect = [
            [
                {
                    "id": 42,
                    "domain": "www.acme-rentals.nl",
                    "acm_certificate_arn": None,
                }
            ],
            None,
        ]

        mock_cf = Mock()
        mock_cf.delete_domain_tenant.return_value = True

        with patch(
            "services.cloudfront_domain_service.CloudFrontDomainService",
            return_value=mock_cf,
        ):
            result = service.remove_custom_domain("TestTenant")

        assert result["success"] is True
        # Should NOT call delete_certificate when cert_arn is None
        mock_cf.delete_certificate.assert_not_called()


class TestCustomDomainStatus:
    """Status view repeats the single routing CNAME while pending."""

    def test_status_pending_shows_routing_record(self):
        mock_db = Mock()
        mock_db.execute_query.return_value = [
            {
                "domain": "www.acme-rentals.nl",
                "verification_status": "pending_dns",
                "is_active": False,
                "dns_validation_name": "www.acme-rentals.nl",
                "dns_validation_value": "d1234abcd.cloudfront.net",
            }
        ]
        service = DomainService(db_manager=mock_db)

        status = service._get_custom_domain_status("TestTenant")

        assert status["dns_instructions"]["records"] == [
            {
                "purpose": "routing",
                "name": "www.acme-rentals.nl",
                "value": "d1234abcd.cloudfront.net",
            }
        ]
        assert mock_db.execute_query.call_args[0][1] == ("TestTenant",)

    def test_remove_tenant_delete_refused_still_removes_record(self):
        """A refused tenant delete (left disabled) does not block removal."""
        from unittest.mock import patch

        mock_db = Mock()
        mock_db.execute_query.side_effect = [
            [{"id": 7, "domain": "www.acme-rentals.nl", "acm_certificate_arn": None}],
            None,
        ]
        mock_cf = Mock()
        mock_cf.delete_domain_tenant.return_value = False
        service = DomainService(db_manager=mock_db)

        with patch(
            "services.cloudfront_domain_service.CloudFrontDomainService",
            return_value=mock_cf,
        ):
            result = service.remove_custom_domain("TestTenant")

        assert result["success"] is True
        delete_call = mock_db.execute_query.call_args_list[1]
        assert "DELETE FROM tenant_custom_domains" in delete_call[0][0]
        assert delete_call[0][1] == (7, "TestTenant")


class TestTenantCreatedOnceDnsPoints:
    """CloudFront only creates a tenant after the CNAME points at it."""

    def _cf(self, created):
        mock_cf = Mock()
        mock_cf.get_routing_endpoint.return_value = "d1234abcd.cloudfront.net"
        mock_cf.create_domain_tenant.return_value = created
        return mock_cf

    def test_register_dns_not_ready_still_registers_with_cname(self):
        from unittest.mock import patch

        mock_db = Mock()
        mock_db.execute_query.side_effect = [[], [{"slug": "acme-rentals"}], None]
        mock_cf = self._cf({"success": False, "dns_not_ready": True})
        service = DomainService(db_manager=mock_db)

        with patch(
            "services.cloudfront_domain_service.CloudFrontDomainService",
            return_value=mock_cf,
        ):
            result = service.register_custom_domain("TestTenant", "www.acme-rentals.nl")

        assert result["success"] is True
        assert result["data"]["status"] == "pending_dns"
        assert result["data"]["dns_instructions"]["records"][0]["value"] == (
            "d1234abcd.cloudfront.net"
        )
        insert_call = mock_db.execute_query.call_args_list[2]
        assert "INSERT INTO tenant_custom_domains" in insert_call[0][0]

    def test_register_no_routing_endpoint_returns_error(self):
        from unittest.mock import patch

        mock_db = Mock()
        mock_db.execute_query.side_effect = [[], [{"slug": "acme-rentals"}]]
        mock_cf = self._cf({"success": True})
        mock_cf.get_routing_endpoint.return_value = None
        service = DomainService(db_manager=mock_db)

        with patch(
            "services.cloudfront_domain_service.CloudFrontDomainService",
            return_value=mock_cf,
        ):
            result = service.register_custom_domain("TestTenant", "www.acme-rentals.nl")

        assert result["success"] is False
        mock_cf.create_domain_tenant.assert_not_called()
        assert mock_db.execute_query.call_count == 2

    def test_verify_no_tenant_dns_not_ready_returns_pending_dns(self):
        from unittest.mock import patch

        mock_db = Mock()
        mock_db.execute_query.return_value = [
            {
                "id": 42,
                "domain": "www.acme-rentals.nl",
                "slug": "acme-rentals",
                "acm_certificate_arn": None,
                "verification_status": "pending_dns",
                "is_active": False,
            }
        ]
        mock_cf = self._cf({"success": False, "dns_not_ready": True})
        mock_cf.get_domain_status.return_value = {"success": False, "not_found": True}
        service = DomainService(db_manager=mock_db)

        with patch(
            "services.cloudfront_domain_service.CloudFrontDomainService",
            return_value=mock_cf,
        ):
            result = service.verify_custom_domain("TestTenant")

        assert result["success"] is True
        assert result["data"]["status"] == "pending_dns"
        assert result["data"]["is_active"] is False
        mock_cf.create_domain_tenant.assert_called_once_with(
            "www.acme-rentals.nl", "acme-rentals"
        )
        assert mock_db.execute_query.call_count == 1  # no status change
