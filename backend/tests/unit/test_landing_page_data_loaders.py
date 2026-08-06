"""
Unit Tests for Landing Page Data Loaders

Tests load_zzp_public_services function
that provides live data for landing page publishing (Task 3.11).
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services.landing_page_data_loaders import (
    load_zzp_public_services,
    _format_price,
)


class TestLoadZzpPublicServices:
    """Tests for load_zzp_public_services (Task 3.11)."""

    @pytest.fixture
    def mock_db(self):
        """Mock DatabaseManager."""
        return Mock()

    def test_returns_services_when_found(self, mock_db):
        """Test returns formatted service dicts from query results."""
        mock_db.execute_query.return_value = [
            {
                "id": 1,
                "name": "Web Development",
                "description": "Full-stack web dev",
                "unit_price": "95.00",
                "unit_of_measure": "uur",
                "product_type": "development",
            },
            {
                "id": 2,
                "name": "Consulting",
                "description": "Strategy consulting",
                "unit_price": "125.00",
                "unit_of_measure": "uur",
                "product_type": "consulting",
            },
        ]

        result = load_zzp_public_services(mock_db, "TestTenant")

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Web Development"
        assert result[0]["price"] == "€95/uur"
        assert result[0]["category"] == "development"
        assert result[1]["price"] == "€125/uur"

    def test_returns_empty_list_when_no_results(self, mock_db):
        """Test returns empty list when no public services found."""
        mock_db.execute_query.return_value = []

        result = load_zzp_public_services(mock_db, "TestTenant")

        assert result == []

    def test_returns_empty_list_on_exception(self, mock_db):
        """Test returns empty list gracefully on database error."""
        mock_db.execute_query.side_effect = Exception("DB error")

        result = load_zzp_public_services(mock_db, "TestTenant")

        assert result == []

    def test_passes_tenant_as_parameter(self, mock_db):
        """Test tenant is passed as parameterized query value."""
        mock_db.execute_query.return_value = []

        load_zzp_public_services(mock_db, "MyAdmin")

        call_args = mock_db.execute_query.call_args
        assert call_args[0][1] == ("MyAdmin",)


class TestFormatPrice:
    """Tests for _format_price helper."""

    def test_formats_price_with_unit(self):
        """Test price formatting with unit of measure."""
        assert _format_price("95.00", "uur") == "€95/uur"

    def test_formats_price_without_unit(self):
        """Test price formatting without unit of measure."""
        assert _format_price("50.00", None) == "€50"

    def test_formats_price_with_decimals(self):
        """Test price keeps meaningful decimals."""
        assert _format_price("99.50", "stuk") == "€99.5/stuk"

    def test_returns_empty_for_none_price(self):
        """Test returns empty string for None price."""
        assert _format_price(None, "uur") == ""

    def test_returns_empty_for_invalid_price(self):
        """Test returns empty string for non-numeric price."""
        assert _format_price("invalid", "uur") == ""
