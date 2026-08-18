"""
Unit tests for TenantSlugService.

Tests slug validation logic (format, length, reserved words)
and service methods with mocked database.
"""

import pytest
from unittest.mock import MagicMock, patch

from services.tenant_slug_service import (
    TenantSlugService,
    RESERVED_SLUGS,
    SLUG_MIN_LENGTH,
    SLUG_MAX_LENGTH,
    SLUG_PATTERN,
)


@pytest.fixture
def mock_db():
    """Create a mock DatabaseManager."""
    return MagicMock()


@pytest.fixture
def service(mock_db):
    """Create a TenantSlugService with mocked DB."""
    return TenantSlugService(mock_db)


# ============================================================================
# Slug validation — format rules
# ============================================================================


class TestValidateSlugFormat:
    """Test slug format validation rules."""

    def test_valid_simple_slug(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.validate_slug("acme-rentals")
        assert result == {"valid": True}

    def test_valid_numeric_slug(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.validate_slug("property123")
        assert result == {"valid": True}

    def test_valid_all_lowercase(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.validate_slug("abc")
        assert result == {"valid": True}

    def test_invalid_uppercase(self, service, mock_db):
        result = service.validate_slug("Acme-Rentals")
        assert result["valid"] is False
        assert "lowercase" in result["error"]

    def test_invalid_starts_with_hyphen(self, service, mock_db):
        result = service.validate_slug("-acme-rentals")
        assert result["valid"] is False

    def test_invalid_ends_with_hyphen(self, service, mock_db):
        result = service.validate_slug("acme-rentals-")
        assert result["valid"] is False

    def test_invalid_consecutive_hyphens(self, service, mock_db):
        result = service.validate_slug("acme--rentals")
        assert result["valid"] is False

    def test_invalid_special_characters(self, service, mock_db):
        result = service.validate_slug("acme_rentals")
        assert result["valid"] is False

    def test_invalid_spaces(self, service, mock_db):
        result = service.validate_slug("acme rentals")
        assert result["valid"] is False

    def test_invalid_dots(self, service, mock_db):
        result = service.validate_slug("acme.rentals")
        assert result["valid"] is False


class TestValidateSlugLength:
    """Test slug length validation."""

    def test_too_short(self, service, mock_db):
        result = service.validate_slug("ab")
        assert result["valid"] is False
        assert "at least" in result["error"]

    def test_minimum_length(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.validate_slug("abc")
        assert result == {"valid": True}

    def test_too_long(self, service, mock_db):
        slug = "a" * (SLUG_MAX_LENGTH + 1)
        result = service.validate_slug(slug)
        assert result["valid"] is False
        assert "at most" in result["error"]

    def test_maximum_length(self, service, mock_db):
        mock_db.execute_query.return_value = []
        slug = "a" * SLUG_MAX_LENGTH
        result = service.validate_slug(slug)
        assert result == {"valid": True}


class TestValidateSlugReserved:
    """Test reserved slug blocking."""

    @pytest.mark.parametrize("slug", list(RESERVED_SLUGS))
    def test_reserved_slugs_rejected(self, service, mock_db, slug):
        result = service.validate_slug(slug)
        assert result["valid"] is False
        assert "reserved" in result["error"]


class TestValidateSlugUniqueness:
    """Test slug uniqueness checking."""

    def test_slug_taken(self, service, mock_db):
        mock_db.execute_query.return_value = [{"administration": "OtherTenant"}]
        result = service.validate_slug("taken-slug")
        assert result["valid"] is False
        assert "already taken" in result["error"]

    def test_slug_available(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.validate_slug("available-slug")
        assert result == {"valid": True}

    def test_slug_owned_by_current_tenant_is_valid(self, service, mock_db):
        # When updating, the current tenant's own slug should not block
        mock_db.execute_query.return_value = []
        result = service.validate_slug(
            "my-slug", current_administration="MyTenant"
        )
        assert result == {"valid": True}


# ============================================================================
# resolve_slug
# ============================================================================


class TestResolveSlug:
    """Test slug → administration resolution."""

    def test_resolves_existing_slug(self, service, mock_db):
        mock_db.execute_query.return_value = [{"administration": "AcmeRentals"}]
        result = service.resolve_slug("acme-rentals")
        assert result == "AcmeRentals"

    def test_returns_none_for_unknown_slug(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.resolve_slug("nonexistent")
        assert result is None


# ============================================================================
# get_slug
# ============================================================================


class TestGetSlug:
    """Test administration → slug lookup."""

    def test_returns_slug(self, service, mock_db):
        mock_db.execute_query.return_value = [{"slug": "acme-rentals"}]
        result = service.get_slug("AcmeRentals")
        assert result == "acme-rentals"

    def test_returns_none_when_no_slug(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.get_slug("NewTenant")
        assert result is None


# ============================================================================
# set_slug
# ============================================================================


class TestSetSlug:
    """Test setting/updating a tenant slug."""

    def test_set_slug_success(self, service, mock_db):
        """First-time slug setup (no existing slug)."""
        def side_effect(query, params, **kwargs):
            # validate_slug uniqueness check
            if "SELECT administration" in query:
                return []
            # get_slug check
            if "SELECT slug" in query:
                return []
            # INSERT
            return []

        mock_db.execute_query.side_effect = side_effect
        result = service.set_slug("AcmeRentals", "acme-rentals")
        assert result == {"success": True, "slug": "acme-rentals"}

    def test_set_slug_invalid_format(self, service, mock_db):
        result = service.set_slug("AcmeRentals", "INVALID")
        assert result["success"] is False

    def test_set_slug_reserved(self, service, mock_db):
        result = service.set_slug("AcmeRentals", "admin")
        assert result["success"] is False
        assert "reserved" in result["error"]


# ============================================================================
# rename_slug
# ============================================================================


class TestRenameSlug:
    """Test the full slug rename orchestration."""

    @patch("services.tenant_slug_service.boto3")
    @patch("services.landing_page_publish_service.LandingPagePublishService")
    @patch("services.parameter_service.ParameterService")
    @patch("services.landing_page_service.LandingPageService")
    def test_rename_happy_path(
        self, mock_lp_svc_cls, mock_param_cls, mock_pub_cls, mock_boto3, service, mock_db
    ):
        """All steps succeed — DynamoDB migrated, MySQL updated, S3 cleaned, republished."""
        # Step 1: MySQL update succeeds (no exception)
        mock_db.execute_query.return_value = []

        # Step 2: DynamoDB migration — patch the instance created inside rename_slug
        mock_lp_instance = MagicMock()
        mock_lp_instance.migrate_slug.return_value = {
            "success": True,
            "migrated": 3,
            "warnings": [],
        }

        # Step 6: Republish
        mock_pub_instance = MagicMock()
        mock_pub_instance.publish.return_value = {"success": True, "version": 5}

        # Step 5: S3 client
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        with patch("services.tenant_slug_service.LandingPageService", return_value=mock_lp_instance, create=True):
            with patch("services.tenant_slug_service.LandingPagePublishService", return_value=mock_pub_instance, create=True):
                with patch("services.tenant_slug_service.ParameterService", return_value=MagicMock(), create=True):
                    result = service.rename_slug("kimgeers", "old-slug", "new-slug", "user@test.com")

        assert result["success"] is True
        assert result["slug"] == "new-slug"
        assert result["renamed_from"] == "old-slug"
        assert result["warnings"] == []

    @patch("services.tenant_slug_service.boto3")
    def test_rename_partial_failure_returns_warnings(
        self, mock_boto3, service, mock_db
    ):
        """DynamoDB succeeds but republish fails — result is success with warnings."""
        mock_db.execute_query.return_value = []

        mock_lp_instance = MagicMock()
        mock_lp_instance.migrate_slug.return_value = {
            "success": True,
            "migrated": 2,
            "warnings": [],
        }

        mock_pub_instance = MagicMock()
        mock_pub_instance.publish.return_value = {
            "success": False,
            "error": "No draft found",
        }

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        with patch("services.tenant_slug_service.LandingPageService", return_value=mock_lp_instance, create=True):
            with patch("services.tenant_slug_service.LandingPagePublishService", return_value=mock_pub_instance, create=True):
                with patch("services.tenant_slug_service.ParameterService", return_value=MagicMock(), create=True):
                    result = service.rename_slug("tenant1", "old-name", "new-name", "u@t.com")

        assert result["success"] is True
        assert result["slug"] == "new-name"
        assert any("Republish failed" in w for w in result["warnings"])

    def test_rename_to_taken_slug_fails(self, service, mock_db):
        """Renaming to a slug that's taken by another tenant returns error."""
        from db_exceptions import IntegrityError

        # get_slug returns old slug (triggering rename path in set_slug)
        # But we call rename_slug directly here — MySQL UPDATE raises IntegrityError
        mock_db.execute_query.side_effect = IntegrityError("Duplicate entry")

        result = service.rename_slug("tenant1", "old-slug", "taken-slug", "u@t.com")

        assert result["success"] is False
        assert "already taken" in result["error"]

    def test_set_slug_same_slug_is_noop(self, service, mock_db):
        """Setting the same slug that already exists is a no-op."""

        def side_effect(query, params, **kwargs):
            # validate_slug uniqueness check — same tenant owns it, so empty result
            if "SELECT administration" in query:
                return []
            # get_slug returns current slug
            if "SELECT slug" in query:
                return [{"slug": "my-slug"}]
            return []

        mock_db.execute_query.side_effect = side_effect

        result = service.set_slug("MyTenant", "my-slug", user_email="u@t.com")

        assert result == {"success": True, "slug": "my-slug"}

    @patch("services.tenant_slug_service.boto3")
    def test_set_slug_detects_rename(
        self, mock_boto3, service, mock_db
    ):
        """set_slug detects an existing different slug and triggers rename."""
        old_slug = "old-slug"

        def side_effect(query, params, **kwargs):
            # validate_slug uniqueness check
            if "SELECT administration" in query and "slug = %s" in query:
                return []
            # get_slug
            if "SELECT slug" in query:
                return [{"slug": old_slug}]
            # Everything else (UPDATE, custom domain query, etc.)
            return []

        mock_db.execute_query.side_effect = side_effect

        mock_lp_instance = MagicMock()
        mock_lp_instance.migrate_slug.return_value = {
            "success": True,
            "migrated": 1,
            "warnings": [],
        }

        mock_pub_instance = MagicMock()
        mock_pub_instance.publish.return_value = {"success": True, "version": 2}

        mock_boto3.client.return_value = MagicMock()

        with patch("services.tenant_slug_service.LandingPageService", return_value=mock_lp_instance, create=True):
            with patch("services.tenant_slug_service.LandingPagePublishService", return_value=mock_pub_instance, create=True):
                with patch("services.tenant_slug_service.ParameterService", return_value=MagicMock(), create=True):
                    result = service.set_slug("MyTenant", "new-slug", user_email="u@t.com")

        assert result["success"] is True
        assert result["slug"] == "new-slug"
        assert result["renamed_from"] == "old-slug"
