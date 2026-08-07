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
        # validate_slug will check uniqueness
        mock_db.execute_query.return_value = []
        result = service.set_slug("AcmeRentals", "acme-rentals")
        assert result == {"success": True, "slug": "acme-rentals"}

    def test_set_slug_invalid_format(self, service, mock_db):
        result = service.set_slug("AcmeRentals", "INVALID")
        assert result["success"] is False

    def test_set_slug_reserved(self, service, mock_db):
        result = service.set_slug("AcmeRentals", "admin")
        assert result["success"] is False
        assert "reserved" in result["error"]
