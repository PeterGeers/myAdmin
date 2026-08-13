"""
Unit tests for pattern hygiene fixes in store_verb_patterns_to_database().

Validates Requirements:
- 0.1: Full analysis replaces occurrence counts (not accumulates)
- 0.2: Stale patterns are deleted after full analysis
- 0.3: Incremental analysis does NOT delete patterns
- 0.4: Log output when stale patterns are deleted
"""

import sys
import os
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from pattern_storage import store_verb_patterns_to_database


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """Mock DatabaseManager instance."""
    db = MagicMock()
    # Default: execute_query returns 0 for writes, empty list for reads
    db.execute_query.return_value = [{"count": 1}]
    return db


@pytest.fixture
def sample_patterns():
    """Single pattern for testing."""
    return {
        "pattern_1": {
            "administration": "TestAdmin",
            "bank_account": "1300",
            "verb": "KPN",
            "verb_company": "KPN",
            "verb_reference": None,
            "is_compound": False,
            "reference_number": "KPN",
            "debet_account": "4600",
            "credit_account": "1300",
            "occurrences": 5,
            "confidence": 0.95,
            "last_seen": "2024-06-01",
            "sample_description": "KPN subscription",
        }
    }


@pytest.fixture
def sample_metadata():
    """Analysis metadata with date range."""
    return {
        "total_transactions": 100,
        "date_range": {"from": "2023-06-01", "to": "2024-06-01"},
    }


# ── Requirement 0.1: Full analysis replaces occurrence counts ──────────────


class TestFullAnalysisReplacesOccurrences:
    """Validates Requirement 0.1: full analysis uses 'occurrences = VALUES(occurrences)'."""

    def test_full_analysis_uses_replace_clause(self, mock_db, sample_patterns, sample_metadata):
        """Full analysis SQL contains 'occurrences = VALUES(occurrences)' (replace, not accumulate)."""
        store_verb_patterns_to_database(
            db=mock_db,
            administration="TestAdmin",
            verb_patterns=sample_patterns,
            analysis_metadata=sample_metadata,
            is_incremental=False,
        )

        # The first execute_query call is the INSERT/UPSERT for pattern_1
        insert_call = mock_db.execute_query.call_args_list[0]
        sql = insert_call[0][0]

        # Must use replacement semantics (not accumulation)
        assert "occurrences = VALUES(occurrences)" in sql
        assert "occurrences + VALUES(occurrences)" not in sql

    def test_incremental_analysis_uses_accumulate_clause(self, mock_db, sample_patterns, sample_metadata):
        """Incremental analysis SQL contains 'occurrences = occurrences + VALUES(occurrences)'."""
        store_verb_patterns_to_database(
            db=mock_db,
            administration="TestAdmin",
            verb_patterns=sample_patterns,
            analysis_metadata=sample_metadata,
            is_incremental=True,
        )

        insert_call = mock_db.execute_query.call_args_list[0]
        sql = insert_call[0][0]

        # Must use accumulation semantics
        assert "occurrences = occurrences + VALUES(occurrences)" in sql


# ── Requirement 0.2: Stale patterns deleted after full analysis ────────────


class TestStalePatternDeletion:
    """Validates Requirement 0.2: DELETE patterns where last_seen < analysis_start."""

    def test_delete_called_during_full_analysis(self, mock_db, sample_patterns, sample_metadata):
        """Full analysis issues a DELETE for stale patterns."""
        # Make the DELETE call return a count
        mock_db.execute_query.side_effect = [
            None,        # INSERT/UPSERT for pattern
            3,           # DELETE returns 3 rows removed
            [{"count": 1}],  # SELECT COUNT(*)
            None,        # metadata INSERT
        ]

        store_verb_patterns_to_database(
            db=mock_db,
            administration="TestAdmin",
            verb_patterns=sample_patterns,
            analysis_metadata=sample_metadata,
            is_incremental=False,
        )

        # Find the DELETE call
        delete_calls = [
            c for c in mock_db.execute_query.call_args_list
            if "DELETE" in str(c[0][0])
        ]
        assert len(delete_calls) == 1

        delete_sql = delete_calls[0][0][0]
        delete_params = delete_calls[0][0][1]

        assert "DELETE FROM pattern_verb_patterns" in delete_sql
        assert "last_seen <" in delete_sql
        assert delete_params == ("TestAdmin", "2023-06-01")

    def test_delete_uses_correct_administration_and_date(self, mock_db, sample_patterns):
        """DELETE parameters match the administration and date_range.from."""
        metadata = {
            "total_transactions": 50,
            "date_range": {"from": "2024-01-01", "to": "2024-12-31"},
        }

        mock_db.execute_query.side_effect = [
            None,        # INSERT/UPSERT
            0,           # DELETE returns 0
            [{"count": 1}],  # SELECT COUNT
            None,        # metadata INSERT
        ]

        store_verb_patterns_to_database(
            db=mock_db,
            administration="OtherAdmin",
            verb_patterns=sample_patterns,
            analysis_metadata=metadata,
            is_incremental=False,
        )

        delete_calls = [
            c for c in mock_db.execute_query.call_args_list
            if "DELETE" in str(c[0][0])
        ]
        assert len(delete_calls) == 1
        assert delete_calls[0][0][1] == ("OtherAdmin", "2024-01-01")

    def test_no_delete_when_date_range_missing(self, mock_db, sample_patterns):
        """No DELETE issued if analysis_metadata has no date_range.from."""
        metadata = {"total_transactions": 100}

        mock_db.execute_query.side_effect = [
            None,        # INSERT/UPSERT
            [{"count": 1}],  # SELECT COUNT
            None,        # metadata INSERT
        ]

        store_verb_patterns_to_database(
            db=mock_db,
            administration="TestAdmin",
            verb_patterns=sample_patterns,
            analysis_metadata=metadata,
            is_incremental=False,
        )

        delete_calls = [
            c for c in mock_db.execute_query.call_args_list
            if "DELETE" in str(c[0][0])
        ]
        assert len(delete_calls) == 0


# ── Requirement 0.3: No deletion during incremental analysis ───────────────


class TestIncrementalNoDeletion:
    """Validates Requirement 0.3: incremental analysis never issues DELETE."""

    def test_no_delete_during_incremental(self, mock_db, sample_patterns, sample_metadata):
        """Incremental analysis does not issue any DELETE statement."""
        store_verb_patterns_to_database(
            db=mock_db,
            administration="TestAdmin",
            verb_patterns=sample_patterns,
            analysis_metadata=sample_metadata,
            is_incremental=True,
        )

        # Check that no DELETE call was made
        delete_calls = [
            c for c in mock_db.execute_query.call_args_list
            if "DELETE" in str(c[0][0])
        ]
        assert len(delete_calls) == 0

    def test_incremental_still_accumulates_when_metadata_has_date_range(
        self, mock_db, sample_patterns, sample_metadata
    ):
        """Even with date_range present, incremental skips DELETE and accumulates."""
        store_verb_patterns_to_database(
            db=mock_db,
            administration="TestAdmin",
            verb_patterns=sample_patterns,
            analysis_metadata=sample_metadata,
            is_incremental=True,
        )

        # No DELETE
        delete_calls = [
            c for c in mock_db.execute_query.call_args_list
            if "DELETE" in str(c[0][0])
        ]
        assert len(delete_calls) == 0

        # Verify accumulation in INSERT
        insert_call = mock_db.execute_query.call_args_list[0]
        sql = insert_call[0][0]
        assert "occurrences = occurrences + VALUES(occurrences)" in sql


# ── Requirement 0.4: Log output on stale cleanup ──────────────────────────


class TestStaleCleanupLogging:
    """Validates Requirement 0.4: log count of removed patterns."""

    def test_logs_deleted_count(self, mock_db, sample_patterns, sample_metadata, capsys):
        """Prints removal count when stale patterns are deleted."""
        mock_db.execute_query.side_effect = [
            None,        # INSERT/UPSERT
            7,           # DELETE returns 7 rows removed
            [{"count": 1}],  # SELECT COUNT
            None,        # metadata INSERT
        ]

        store_verb_patterns_to_database(
            db=mock_db,
            administration="TestAdmin",
            verb_patterns=sample_patterns,
            analysis_metadata=sample_metadata,
            is_incremental=False,
        )

        captured = capsys.readouterr()
        assert "Removed 7 stale patterns" in captured.out
        assert "last_seen < 2023-06-01" in captured.out

    def test_no_log_when_zero_deleted(self, mock_db, sample_patterns, sample_metadata, capsys):
        """No removal log when DELETE returns 0."""
        mock_db.execute_query.side_effect = [
            None,        # INSERT/UPSERT
            0,           # DELETE returns 0
            [{"count": 1}],  # SELECT COUNT
            None,        # metadata INSERT
        ]

        store_verb_patterns_to_database(
            db=mock_db,
            administration="TestAdmin",
            verb_patterns=sample_patterns,
            analysis_metadata=sample_metadata,
            is_incremental=False,
        )

        captured = capsys.readouterr()
        assert "Removed" not in captured.out
        assert "stale patterns" not in captured.out

    def test_no_log_when_delete_returns_non_int(self, mock_db, sample_patterns, sample_metadata, capsys):
        """No removal log when DELETE returns a non-integer (e.g., None)."""
        mock_db.execute_query.side_effect = [
            None,        # INSERT/UPSERT
            None,        # DELETE returns None
            [{"count": 1}],  # SELECT COUNT
            None,        # metadata INSERT
        ]

        store_verb_patterns_to_database(
            db=mock_db,
            administration="TestAdmin",
            verb_patterns=sample_patterns,
            analysis_metadata=sample_metadata,
            is_incremental=False,
        )

        captured = capsys.readouterr()
        assert "Removed" not in captured.out
