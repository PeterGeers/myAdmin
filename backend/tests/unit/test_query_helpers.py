"""
Unit tests for query_helpers utility functions.

Tests year_to_date_range() and years_to_date_range_conditions() for:
- Standard years (2020-2030)
- Boundary years
- Type coercion from string input
- Edge cases
"""

import sys
import os
import pytest

# Add backend/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from utils.query_helpers import year_to_date_range, years_to_date_range_conditions


class TestYearToDateRange:
    """Tests for year_to_date_range()"""

    @pytest.mark.parametrize("year,expected_start,expected_end", [
        (2020, "2020-01-01", "2021-01-01"),
        (2021, "2021-01-01", "2022-01-01"),
        (2022, "2022-01-01", "2023-01-01"),
        (2023, "2023-01-01", "2024-01-01"),
        (2024, "2024-01-01", "2025-01-01"),
        (2025, "2025-01-01", "2026-01-01"),
        (2026, "2026-01-01", "2027-01-01"),
        (2027, "2027-01-01", "2028-01-01"),
        (2028, "2028-01-01", "2029-01-01"),
        (2029, "2029-01-01", "2030-01-01"),
        (2030, "2030-01-01", "2031-01-01"),
    ])
    def test_standard_years(self, year, expected_start, expected_end):
        """Test standard years 2020-2030"""
        start, end = year_to_date_range(year)
        assert start == expected_start
        assert end == expected_end

    def test_string_input(self):
        """Test type coercion from string input"""
        start, end = year_to_date_range("2025")
        assert start == "2025-01-01"
        assert end == "2026-01-01"

    def test_string_with_whitespace(self):
        """Test string input with leading/trailing whitespace"""
        start, end = year_to_date_range(" 2025 ")
        assert start == "2025-01-01"
        assert end == "2026-01-01"

    def test_float_input(self):
        """Test type coercion from float input"""
        start, end = year_to_date_range(2025.0)
        assert start == "2025-01-01"
        assert end == "2026-01-01"

    def test_returns_tuple(self):
        """Test that return value is a tuple of two strings"""
        result = year_to_date_range(2025)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)

    def test_boundary_year_2000(self):
        """Test year 2000 boundary"""
        start, end = year_to_date_range(2000)
        assert start == "2000-01-01"
        assert end == "2001-01-01"

    def test_boundary_year_1999(self):
        """Test year 1999 boundary"""
        start, end = year_to_date_range(1999)
        assert start == "1999-01-01"
        assert end == "2000-01-01"

    def test_invalid_string_raises(self):
        """Test that non-numeric string raises ValueError"""
        with pytest.raises(ValueError):
            year_to_date_range("abc")

    def test_none_raises(self):
        """Test that None raises TypeError"""
        with pytest.raises((TypeError, ValueError)):
            year_to_date_range(None)


class TestYearsToDateRangeConditions:
    """Tests for years_to_date_range_conditions()"""

    def test_single_year(self):
        """Test single year produces simple range"""
        sql, params = years_to_date_range_conditions([2025])
        assert sql == "TransactionDate >= %s AND TransactionDate < %s"
        assert params == ["2025-01-01", "2026-01-01"]

    def test_contiguous_years(self):
        """Test contiguous years produce single optimized range"""
        sql, params = years_to_date_range_conditions([2023, 2024, 2025])
        assert sql == "TransactionDate >= %s AND TransactionDate < %s"
        assert params == ["2023-01-01", "2026-01-01"]

    def test_contiguous_years_unordered(self):
        """Test contiguous years work even when unordered"""
        sql, params = years_to_date_range_conditions([2025, 2023, 2024])
        assert sql == "TransactionDate >= %s AND TransactionDate < %s"
        assert params == ["2023-01-01", "2026-01-01"]

    def test_non_contiguous_years(self):
        """Test non-contiguous years produce OR conditions"""
        sql, params = years_to_date_range_conditions([2020, 2025])
        assert "OR" in sql
        assert len(params) == 4
        assert params == ["2020-01-01", "2021-01-01", "2025-01-01", "2026-01-01"]

    def test_string_years(self):
        """Test string year inputs are coerced"""
        sql, params = years_to_date_range_conditions(["2024", "2025"])
        assert sql == "TransactionDate >= %s AND TransactionDate < %s"
        assert params == ["2024-01-01", "2026-01-01"]

    def test_empty_list_raises(self):
        """Test empty list raises ValueError"""
        with pytest.raises(ValueError):
            years_to_date_range_conditions([])

    def test_two_contiguous_years(self):
        """Test two contiguous years produce single range"""
        sql, params = years_to_date_range_conditions([2024, 2025])
        assert sql == "TransactionDate >= %s AND TransactionDate < %s"
        assert params == ["2024-01-01", "2026-01-01"]

    def test_three_non_contiguous_years(self):
        """Test three non-contiguous years"""
        sql, params = years_to_date_range_conditions([2020, 2023, 2025])
        assert "OR" in sql
        assert len(params) == 6
        # Should be sorted
        assert params[0] == "2020-01-01"
        assert params[2] == "2023-01-01"
        assert params[4] == "2025-01-01"

    def test_mixed_contiguous_and_gap(self):
        """Test mix of contiguous and non-contiguous years"""
        # 2023, 2024 are contiguous but 2026 has a gap
        sql, params = years_to_date_range_conditions([2023, 2024, 2026])
        assert "OR" in sql
        assert len(params) == 6
