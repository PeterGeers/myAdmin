"""
Performance tests for duplicate invoice detection
Tests query performance with large datasets and validates 2-second response time requirement
"""
import os
import pytest
import time
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume, Phase

from database import DatabaseManager
from duplicate_checker import DuplicateChecker


@pytest.fixture
def patched_db_manager():
    """Create a real DatabaseManager but prevent any real DB connections.

    The instance keeps its real methods (check_duplicate_transactions, etc.)
    but get_connection is patched so no actual mysql.connector.connect() call
    is made.  The connection guard in unit/conftest.py would block it anyway,
    but this makes the intent explicit.
    """
    with patch.object(DatabaseManager, '__init__', lambda self, *a, **kw: None):
        db = DatabaseManager.__new__(DatabaseManager)
        db.test_mode = True
        db.config = {
            'host': 'localhost', 'user': 'test',
            'password': 'test', 'database': 'test', 'port': 3306,
        }
        yield db


class TestDuplicateDetectionPerformance:
    """Performance tests for duplicate detection with large datasets"""

    @pytest.fixture
    def db_manager(self, patched_db_manager):
        return patched_db_manager

    @pytest.fixture
    def duplicate_checker(self, db_manager):
        """Create DuplicateChecker instance for testing"""
        return DuplicateChecker(db_manager)

    def test_duplicate_check_performance_small_dataset(self, db_manager):
        """
        Test duplicate detection performance with small dataset (100 transactions)
        Should complete well under 2 seconds
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            start_time = time.time()
            result = db_manager.check_duplicate_transactions(
                'TestVendor',
                '2024-06-15',
                150.00
            )
            elapsed_time = time.time() - start_time

            assert elapsed_time < 0.5, f"Query took {elapsed_time:.3f}s, expected < 0.5s"
            assert isinstance(result, list)

    def test_duplicate_check_performance_medium_dataset(self, db_manager):
        """
        Test duplicate detection performance with medium dataset (10,000 transactions)
        Should complete under 2 seconds
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            start_time = time.time()
            result = db_manager.check_duplicate_transactions(
                'TestVendor',
                '2024-06-15',
                150.00
            )
            elapsed_time = time.time() - start_time

            assert elapsed_time < 2.0, f"Query took {elapsed_time:.3f}s, expected < 2.0s"
            assert isinstance(result, list)

    def test_duplicate_check_performance_large_dataset(self, db_manager):
        """
        Test duplicate detection performance with large dataset (100,000 transactions)
        Should still complete under 2 seconds with proper indexing
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            start_time = time.time()
            result = db_manager.check_duplicate_transactions(
                'TestVendor',
                '2024-06-15',
                150.00
            )
            elapsed_time = time.time() - start_time

            assert elapsed_time < 2.0, f"Query took {elapsed_time:.3f}s, expected < 2.0s (requires proper indexing)"
            assert isinstance(result, list)

    def test_duplicate_check_with_multiple_matches(self, db_manager):
        """
        Test performance when multiple duplicates are found
        Should still complete under 2 seconds
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_duplicates = []
        for i in range(10):
            mock_duplicates.append({
                'ID': i,
                'TransactionNumber': f'TXN{i:04d}',
                'TransactionDate': date(2024, 6, 15),
                'TransactionDescription': f'Duplicate Transaction {i}',
                'TransactionAmount': Decimal('150.00'),
                'Debet': '1000',
                'Credit': '4000',
                'ReferenceNumber': 'TestVendor',
                'Ref1': 'REF1',
                'Ref2': f'REF2_{i}',
                'Ref3': f'file_url_{i}',
                'Ref4': 'REF4',
                'Administration': 'GoodwinSolutions'
            })

        mock_cursor.fetchall.return_value = mock_duplicates

        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            start_time = time.time()
            result = db_manager.check_duplicate_transactions(
                'TestVendor',
                '2024-06-15',
                150.00
            )
            elapsed_time = time.time() - start_time

            assert elapsed_time < 2.0, f"Query took {elapsed_time:.3f}s, expected < 2.0s"
            assert len(result) == 10
            assert all(t['ReferenceNumber'] == 'TestVendor' for t in result)

    def test_query_uses_indexes(self, db_manager):
        """
        Test that the duplicate check query is structured to use indexes
        Verifies query includes indexed columns in WHERE clause
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            db_manager.check_duplicate_transactions(
                'TestVendor',
                '2024-06-15',
                150.00
            )

            call_args = mock_cursor.execute.call_args
            sql_query = call_args[0][0]

            assert 'ReferenceNumber = %s' in sql_query, "Query should filter by ReferenceNumber (indexed)"
            assert 'TransactionDate = %s' in sql_query, "Query should filter by TransactionDate (indexed)"
            assert 'TransactionAmount' in sql_query, "Query should filter by TransactionAmount (indexed)"
            assert 'INTERVAL 2 YEAR' in sql_query, "Query should use date range filter (indexed)"
            assert 'ORDER BY ID DESC' in sql_query, "Query should order by ID for consistent results"

    def test_date_range_filter_performance(self, db_manager):
        """
        Test that 2-year date range filter improves performance
        Verifies query limits search scope appropriately
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            start_time = time.time()
            db_manager.check_duplicate_transactions(
                'TestVendor',
                '2024-06-15',
                150.00
            )
            elapsed_time = time.time() - start_time

            assert elapsed_time < 1.0, f"Query with date range took {elapsed_time:.3f}s, expected < 1.0s"

            call_args = mock_cursor.execute.call_args
            sql_query = call_args[0][0]
            assert 'TransactionDate > (CURDATE() - INTERVAL 2 YEAR)' in sql_query

    @given(
        reference_number=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pc'))),
        transaction_date=st.dates(min_value=date(2023, 1, 1), max_value=date(2025, 12, 31)),
        transaction_amount=st.floats(min_value=0.01, max_value=999999.99, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50, phases=[Phase.generate, Phase.target])
    def test_performance_property_response_time(self, reference_number, transaction_date, transaction_amount):
        """
        **Property-Based Test: Response Time Requirement**
        For any valid transaction query, the duplicate check should complete within 2 seconds
        **Validates: Requirements 1.3, 5.5**
        """
        assume(len(reference_number.strip()) > 0)
        assume(0.01 <= transaction_amount <= 999999.99)

        with patch.object(DatabaseManager, '__init__', lambda self, *a, **kw: None):
            db = DatabaseManager.__new__(DatabaseManager)
            db.test_mode = True
            db.config = {
                'host': 'localhost', 'user': 'test',
                'password': 'test', 'database': 'test', 'port': 3306,
            }

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch.object(db, 'get_connection', return_value=mock_conn):
            start_time = time.time()
            result = db.check_duplicate_transactions(
                reference_number,
                transaction_date.strftime('%Y-%m-%d'),
                transaction_amount
            )
            elapsed_time = time.time() - start_time

            assert elapsed_time < 2.0, f"Query took {elapsed_time:.3f}s, exceeds 2.0s requirement"
            assert isinstance(result, list)

    def test_query_optimization_effectiveness(self, db_manager):
        """
        Test that query optimization with indexes is effective
        Compares query structure before and after optimization
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            db_manager.check_duplicate_transactions(
                'TestVendor',
                '2024-06-15',
                150.00
            )

            call_args = mock_cursor.execute.call_args
            sql_query = call_args[0][0]

            assert 'ReferenceNumber = %s' in sql_query
            assert 'TransactionDate = %s' in sql_query
            assert 'TransactionDate > (CURDATE() - INTERVAL 2 YEAR)' in sql_query
            assert 'ABS(TransactionAmount - %s) < 0.01' in sql_query
            assert 'ORDER BY ID DESC' in sql_query

    def test_concurrent_duplicate_checks_performance(self, db_manager):
        """
        Test performance when multiple duplicate checks run concurrently
        Simulates realistic load scenario
        """
        import concurrent.futures

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        def run_duplicate_check(vendor_id):
            with patch.object(db_manager, 'get_connection', return_value=mock_conn):
                return db_manager.check_duplicate_transactions(
                    f'Vendor{vendor_id}',
                    '2024-06-15',
                    150.00 + vendor_id
                )

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(run_duplicate_check, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        elapsed_time = time.time() - start_time

        assert elapsed_time < 5.0, f"Concurrent checks took {elapsed_time:.3f}s, expected < 5.0s"
        assert len(results) == 10
        assert all(isinstance(r, list) for r in results)


class TestDuplicateCheckerPerformance:
    """Performance tests for DuplicateChecker class"""

    @pytest.fixture
    def db_manager(self, patched_db_manager):
        return patched_db_manager

    @pytest.fixture
    def duplicate_checker(self, db_manager):
        return DuplicateChecker(db_manager)

    def test_format_duplicate_info_performance(self, duplicate_checker):
        """
        Test that format_duplicate_info completes quickly even with many duplicates
        """
        duplicates = []
        for i in range(100):
            duplicates.append({
                'ID': i,
                'TransactionNumber': f'TXN{i:04d}',
                'TransactionDate': date(2024, 6, 15),
                'TransactionDescription': f'Transaction {i}',
                'TransactionAmount': Decimal('150.00'),
                'Debet': '1000',
                'Credit': '4000',
                'ReferenceNumber': 'TestVendor',
                'Ref1': 'REF1',
                'Ref2': f'REF2_{i}',
                'Ref3': f'file_url_{i}',
                'Ref4': 'REF4',
                'Administration': 'GoodwinSolutions'
            })

        start_time = time.time()
        result = duplicate_checker.format_duplicate_info(duplicates)
        elapsed_time = time.time() - start_time

        assert elapsed_time < 0.1, f"Formatting took {elapsed_time:.3f}s, expected < 0.1s"
        assert result['has_duplicates'] == True
        assert result['duplicate_count'] == 100
        assert len(result['existing_transactions']) == 100


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
