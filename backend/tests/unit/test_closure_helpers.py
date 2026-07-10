"""
Unit tests for get_closure_aware_start_year() helper.

Tests the shared helper that determines the correct lower-bound year for
balance sheet cumulation based on fiscal year closure state.

Requirements: 2.5, 3.5
"""
import pytest
from unittest.mock import MagicMock

from src.utils.closure_helpers import get_closure_aware_start_year


class TestGetClosureAwareStartYear:
    """Tests for get_closure_aware_start_year()."""

    def test_no_closures_empty_result(self):
        """No closures (empty result set) → returns None."""
        db = MagicMock()
        db.execute_query.return_value = []

        result = get_closure_aware_start_year(db, "admin1")

        assert result is None
        db.execute_query.assert_called_once()

    def test_no_closures_max_year_none(self):
        """No closures (MAX returns None) → returns None."""
        db = MagicMock()
        db.execute_query.return_value = [{"max_year": None}]

        result = get_closure_aware_start_year(db, "admin1")

        assert result is None

    def test_single_closure_year_2023(self):
        """Single closure (year 2023 closed) → returns 2024."""
        db = MagicMock()
        db.execute_query.return_value = [{"max_year": 2023}]

        result = get_closure_aware_start_year(db, "admin1")

        assert result == 2024

    def test_multiple_closures_returns_max_plus_one(self):
        """Multiple closures (2021, 2022, 2023 closed) → returns 2024 (MAX + 1).

        The SQL uses MAX(year), so even with multiple closed years the result
        row contains only the highest closed year.
        """
        db = MagicMock()
        # SQL MAX() already computes the maximum — result is a single row
        db.execute_query.return_value = [{"max_year": 2023}]

        result = get_closure_aware_start_year(db, "admin1")

        assert result == 2024

    def test_database_error_returns_none(self):
        """Database error/unreachable → returns None (safe fallback)."""
        db = MagicMock()
        db.execute_query.side_effect = Exception("Connection timeout")

        result = get_closure_aware_start_year(db, "admin1")

        assert result is None

    def test_only_very_old_year_closed(self):
        """Only very old year closed (e.g., 2018) with large gap to target.

        Helper returns 2019 regardless of the gap — callers decide how to
        use the start_year relative to their target_year.
        """
        db = MagicMock()
        db.execute_query.return_value = [{"max_year": 2018}]

        result = get_closure_aware_start_year(db, "admin1")

        assert result == 2019

    def test_query_uses_correct_administration(self):
        """Verifies the administration parameter is passed to the query."""
        db = MagicMock()
        db.execute_query.return_value = [{"max_year": 2022}]

        get_closure_aware_start_year(db, "tenant_xyz")

        args = db.execute_query.call_args
        assert args[0][1] == ["tenant_xyz"]

    def test_max_year_returned_as_int(self):
        """Ensures the result is always an int even if DB returns a string-like value."""
        db = MagicMock()
        # Some DB drivers may return Decimal or string
        db.execute_query.return_value = [{"max_year": "2022"}]

        result = get_closure_aware_start_year(db, "admin1")

        assert result == 2023
        assert isinstance(result, int)
