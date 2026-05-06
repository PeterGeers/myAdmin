"""
Integration tests for migrate_revolut_ref2 module.

Tests data transformation logic and reference format migration
from old to new format (saldo formatted to 2 decimals).

Requirements: 4.8, 8.2, 8.4
"""

import pytest
from unittest.mock import patch, MagicMock


class TestMigrateRevolutRef2:
    """Tests for migrate_revolut_ref2 function."""

    @pytest.fixture
    def mock_cursor(self):
        """Create a mock cursor for database operations."""
        return MagicMock()

    @pytest.fixture
    def mock_conn(self):
        """Create a mock connection for database operations."""
        return MagicMock()

    @pytest.fixture
    def setup_mock_db(self, mock_db, mock_cursor, mock_conn):
        """Configure mock_db with config and get_cursor context manager."""
        mock_db.config = {'database': 'testfinance'}
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        return mock_db

    def test_migrate_revolut_ref2_formats_saldo_to_two_decimals(
        self, setup_mock_db, mock_cursor, mock_conn
    ):
        """Records with unformatted saldo should be updated to 2 decimal places."""
        mock_cursor.fetchall.return_value = [
            {'ID': 1, 'Ref2': 'Hotel_1.5_2025-01-01'},
            {'ID': 2, 'Ref2': 'Restaurant_10_2025-02-15'},
        ]

        with patch('migrate_revolut_ref2.DatabaseManager', return_value=setup_mock_db):
            from migrate_revolut_ref2 import migrate_revolut_ref2
            result = migrate_revolut_ref2(test_mode=True)

        assert result == 2
        # Verify UPDATE calls with formatted saldo
        update_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'UPDATE' in str(call)
        ]
        assert len(update_calls) == 2
        # Check first update: '1.5' -> '1.50'
        assert update_calls[0][0][1] == ('Hotel_1.50_2025-01-01', 1)
        # Check second update: '10' -> '10.00'
        assert update_calls[1][0][1] == ('Restaurant_10.00_2025-02-15', 2)

    def test_migrate_revolut_ref2_already_formatted_no_update(
        self, setup_mock_db, mock_cursor, mock_conn
    ):
        """Records with already formatted saldo (2 decimals) should not be updated."""
        mock_cursor.fetchall.return_value = [
            {'ID': 1, 'Ref2': 'Hotel_1.50_2025-01-01'},
            {'ID': 2, 'Ref2': 'Restaurant_10.00_2025-02-15'},
        ]

        with patch('migrate_revolut_ref2.DatabaseManager', return_value=setup_mock_db):
            from migrate_revolut_ref2 import migrate_revolut_ref2
            result = migrate_revolut_ref2(test_mode=True)

        assert result == 0
        # Only the SELECT should have been called, no UPDATEs
        update_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'UPDATE' in str(call)
        ]
        assert len(update_calls) == 0

    def test_migrate_revolut_ref2_none_ref2_skipped(
        self, setup_mock_db, mock_cursor, mock_conn
    ):
        """Records with None Ref2 should be skipped."""
        mock_cursor.fetchall.return_value = [
            {'ID': 1, 'Ref2': None},
            {'ID': 2, 'Ref2': 'Hotel_1.5_2025-01-01'},
        ]

        with patch('migrate_revolut_ref2.DatabaseManager', return_value=setup_mock_db):
            from migrate_revolut_ref2 import migrate_revolut_ref2
            result = migrate_revolut_ref2(test_mode=True)

        # Only the second record should be updated
        assert result == 1

    def test_migrate_revolut_ref2_non_three_part_ref2_skipped(
        self, setup_mock_db, mock_cursor, mock_conn
    ):
        """Records with Ref2 that doesn't split into exactly 3 parts should be skipped."""
        mock_cursor.fetchall.return_value = [
            {'ID': 1, 'Ref2': 'Hotel_1.5_Extra_2025-01-01'},  # 4 parts
            {'ID': 2, 'Ref2': 'OnlyOnePart'},  # 1 part
            {'ID': 3, 'Ref2': 'Two_Parts'},  # 2 parts
        ]

        with patch('migrate_revolut_ref2.DatabaseManager', return_value=setup_mock_db):
            from migrate_revolut_ref2 import migrate_revolut_ref2
            result = migrate_revolut_ref2(test_mode=True)

        assert result == 0
        update_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'UPDATE' in str(call)
        ]
        assert len(update_calls) == 0

    def test_migrate_revolut_ref2_non_numeric_saldo_skipped(
        self, setup_mock_db, mock_cursor, mock_conn
    ):
        """Records with non-numeric saldo should be skipped (ValueError)."""
        mock_cursor.fetchall.return_value = [
            {'ID': 1, 'Ref2': 'Hotel_abc_2025-01-01'},
            {'ID': 2, 'Ref2': 'Restaurant_not-a-number_2025-02-15'},
        ]

        with patch('migrate_revolut_ref2.DatabaseManager', return_value=setup_mock_db):
            from migrate_revolut_ref2 import migrate_revolut_ref2
            result = migrate_revolut_ref2(test_mode=True)

        assert result == 0
        update_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'UPDATE' in str(call)
        ]
        assert len(update_calls) == 0

    def test_migrate_revolut_ref2_empty_result_set_returns_zero(
        self, setup_mock_db, mock_cursor, mock_conn
    ):
        """Empty result set should return 0 updated records."""
        mock_cursor.fetchall.return_value = []

        with patch('migrate_revolut_ref2.DatabaseManager', return_value=setup_mock_db):
            from migrate_revolut_ref2 import migrate_revolut_ref2
            result = migrate_revolut_ref2(test_mode=True)

        assert result == 0

    def test_migrate_revolut_ref2_commits_at_end(
        self, setup_mock_db, mock_cursor, mock_conn
    ):
        """Migration should commit the connection at the end."""
        mock_cursor.fetchall.return_value = [
            {'ID': 1, 'Ref2': 'Hotel_1.5_2025-01-01'},
        ]

        with patch('migrate_revolut_ref2.DatabaseManager', return_value=setup_mock_db):
            from migrate_revolut_ref2 import migrate_revolut_ref2
            migrate_revolut_ref2(test_mode=True)

        mock_conn.commit.assert_called_once()

    def test_migrate_revolut_ref2_returns_correct_count(
        self, setup_mock_db, mock_cursor, mock_conn
    ):
        """Migration should return the exact count of updated records."""
        mock_cursor.fetchall.return_value = [
            {'ID': 1, 'Ref2': 'Hotel_1.5_2025-01-01'},       # needs update
            {'ID': 2, 'Ref2': 'Bar_2.50_2025-01-02'},        # already formatted
            {'ID': 3, 'Ref2': None},                          # skipped (None)
            {'ID': 4, 'Ref2': 'Cafe_3_2025-01-03'},          # needs update
            {'ID': 5, 'Ref2': 'Shop_abc_2025-01-04'},        # skipped (ValueError)
            {'ID': 6, 'Ref2': 'Too_Many_Parts_Here'},        # 4 parts, skipped
        ]

        with patch('migrate_revolut_ref2.DatabaseManager', return_value=setup_mock_db):
            from migrate_revolut_ref2 import migrate_revolut_ref2
            result = migrate_revolut_ref2(test_mode=True)

        # Only ID 1 and ID 4 need updates
        assert result == 2
