"""
Unit Tests for Pattern Validation Fix (Task 8)

Tests that:
1. get_patterns() uses $.bank_account flag query (not < '1300')
2. validate_pattern/database.py no longer has get_last_transactions() method
3. pdf_processor.py uses transaction_logic.py's get_last_transactions()

Spec: .kiro/specs/ledger-account-hardcode-fix
Requirements: 2.6, 2.7, 3.4
"""

import sys
import os
import inspect
import pytest
from unittest.mock import Mock, patch, MagicMock, call

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# 8.1 — get_patterns() uses $.bank_account flag query
# ---------------------------------------------------------------------------

class TestGetPatternsUsesFlag:
    """Verify get_patterns() queries rekeningschema $.bank_account flag."""

    def test_main_database_get_patterns_no_threshold(self):
        """Main database.py get_patterns() must not contain < '1300' threshold."""
        from database import DatabaseManager
        source = inspect.getsource(DatabaseManager.get_patterns)

        assert "< '1300'" not in source, (
            "database.py get_patterns() still uses hardcoded '< 1300' threshold"
        )
        assert '< 1300' not in source.replace("< '1300'", ''), (
            "database.py get_patterns() still uses hardcoded < 1300 threshold"
        )

    def test_main_database_get_patterns_has_flag_query(self):
        """Main database.py get_patterns() must use $.bank_account flag."""
        from database import DatabaseManager
        source = inspect.getsource(DatabaseManager.get_patterns)

        assert 'bank_account' in source, (
            "database.py get_patterns() does not reference $.bank_account flag"
        )
        assert 'JSON_EXTRACT' in source, (
            "database.py get_patterns() does not use JSON_EXTRACT for flag query"
        )
        assert 'rekeningschema' in source, (
            "database.py get_patterns() does not query rekeningschema table"
        )

    def test_validate_pattern_database_get_patterns_no_threshold(self):
        """validate_pattern/database.py get_patterns() must not contain < '1300'."""
        from validate_pattern.database import DatabaseManager as PatternDB
        source = inspect.getsource(PatternDB.get_patterns)

        assert "< '1300'" not in source, (
            "validate_pattern/database.py get_patterns() still uses '< 1300'"
        )

    def test_validate_pattern_database_get_patterns_has_flag_query(self):
        """validate_pattern/database.py get_patterns() must use $.bank_account flag."""
        from validate_pattern.database import DatabaseManager as PatternDB
        source = inspect.getsource(PatternDB.get_patterns)

        assert 'bank_account' in source, (
            "validate_pattern/database.py get_patterns() does not reference "
            "$.bank_account flag"
        )
        assert 'JSON_EXTRACT' in source, (
            "validate_pattern/database.py get_patterns() does not use "
            "JSON_EXTRACT for flag query"
        )

    def test_main_database_get_patterns_passes_admin_three_times(self):
        """get_patterns() must pass administration to the main query and both subqueries."""
        from database import DatabaseManager

        captured_params = []

        def capture_query(query, params=None, **kwargs):
            if params:
                captured_params.append(params)
            return []

        db = DatabaseManager.__new__(DatabaseManager)
        with patch.object(db, 'execute_query', side_effect=capture_query):
            db.get_patterns('TestTenant')

        assert len(captured_params) == 1, "Expected exactly one execute_query call"
        params = captured_params[0]
        # Administration should appear 3 times: main WHERE, debet subquery, credit subquery
        assert params.count('TestTenant') == 3, (
            f"Expected administration passed 3 times (main + 2 subqueries), "
            f"got {params.count('TestTenant')} in {params}"
        )

    def test_validate_pattern_get_patterns_passes_admin_three_times(self):
        """validate_pattern get_patterns() must pass administration 3 times."""
        from validate_pattern.database import DatabaseManager as PatternDB

        captured_params = []

        def capture_query(query, params=None, **kwargs):
            if params:
                captured_params.append(params)
            return []

        db = PatternDB.__new__(PatternDB)
        with patch.object(db, 'execute_query', side_effect=capture_query):
            db.get_patterns('TestTenant')

        assert len(captured_params) == 1
        params = captured_params[0]
        assert params.count('TestTenant') == 3, (
            f"Expected administration passed 3 times, got {params.count('TestTenant')}"
        )

    def test_get_patterns_query_structure(self):
        """Verify the SQL query uses IN subquery pattern for bank accounts."""
        from database import DatabaseManager

        captured_queries = []

        def capture_query(query, params=None, **kwargs):
            captured_queries.append(query)
            return []

        db = DatabaseManager.__new__(DatabaseManager)
        with patch.object(db, 'execute_query', side_effect=capture_query):
            db.get_patterns('TestTenant')

        assert len(captured_queries) == 1
        query = captured_queries[0]

        # Should use IN (SELECT ...) subquery pattern
        assert 'IN' in query.upper(), "Query should use IN subquery"
        assert 'SELECT Account FROM rekeningschema' in query, (
            "Query should select Account from rekeningschema in subquery"
        )
        # Should still filter by date
        assert 'DATE_SUB' in query, "Query should still filter by date range"
        assert 'vw_readreferences' in query, "Query should still use vw_readreferences view"


# ---------------------------------------------------------------------------
# 8.2 — validate_pattern/database.py no longer has get_last_transactions()
# ---------------------------------------------------------------------------

class TestDuplicateGetLastTransactionsRemoved:
    """Verify duplicate get_last_transactions() is removed from DatabaseManager classes."""

    def test_validate_pattern_database_no_get_last_transactions(self):
        """validate_pattern/database.py DatabaseManager must not have get_last_transactions."""
        from validate_pattern.database import DatabaseManager as PatternDB

        assert not hasattr(PatternDB, 'get_last_transactions'), (
            "validate_pattern/database.py still has get_last_transactions() — "
            "it should be removed; callers should use transaction_logic.py"
        )

    def test_main_database_no_get_last_transactions(self):
        """Main database.py DatabaseManager must not have get_last_transactions."""
        from database import DatabaseManager

        assert not hasattr(DatabaseManager, 'get_last_transactions'), (
            "database.py still has get_last_transactions() — "
            "it should be removed; callers should use transaction_logic.py"
        )

    def test_transaction_logic_has_get_last_transactions(self):
        """transaction_logic.py TransactionLogic must still have get_last_transactions."""
        from transaction_logic import TransactionLogic

        assert hasattr(TransactionLogic, 'get_last_transactions'), (
            "transaction_logic.py TransactionLogic is missing get_last_transactions() — "
            "this is the canonical version that should remain"
        )

    def test_transaction_logic_returns_error_on_zero_results(self):
        """Canonical get_last_transactions returns error dict when no results found."""
        from transaction_logic import TransactionLogic
        source = inspect.getsource(TransactionLogic.get_last_transactions)

        # Should NOT have Gamma fallback in actual code (query for "Gamma%")
        assert 'Gamma%' not in source, (
            "transaction_logic.py get_last_transactions() still has Gamma fallback query"
        )
        # Should return error dict
        assert "'error'" in source or '"error"' in source, (
            "transaction_logic.py get_last_transactions() should return error dict"
        )


# ---------------------------------------------------------------------------
# 8.2 — pdf_processor.py uses transaction_logic.py version
# ---------------------------------------------------------------------------

class TestPdfProcessorUsesTransactionLogic:
    """Verify pdf_processor.py uses TransactionLogic, not DatabaseManager.get_last_transactions."""

    def test_format_vendor_transactions_imports_transaction_logic(self):
        """_format_vendor_transactions should import from transaction_logic, not database."""
        from pdf_processor import PDFProcessor
        source = inspect.getsource(PDFProcessor._format_vendor_transactions)

        assert 'TransactionLogic' in source, (
            "pdf_processor._format_vendor_transactions() should import TransactionLogic"
        )
        assert 'transaction_logic' in source, (
            "pdf_processor._format_vendor_transactions() should import from "
            "transaction_logic module"
        )

    def test_format_vendor_transactions_no_database_get_last_transactions(self):
        """_format_vendor_transactions must not call DatabaseManager.get_last_transactions."""
        from pdf_processor import PDFProcessor
        source = inspect.getsource(PDFProcessor._format_vendor_transactions)

        # Should not import DatabaseManager for get_last_transactions
        # (it may still import DatabaseManager for other purposes elsewhere in the class)
        assert 'db.get_last_transactions' not in source, (
            "pdf_processor._format_vendor_transactions() still calls "
            "db.get_last_transactions() — should use TransactionLogic"
        )

    def test_format_vendor_transactions_handles_error_dict(self):
        """_format_vendor_transactions should handle error dict from TransactionLogic."""
        from pdf_processor import PDFProcessor

        processor = PDFProcessor(test_mode=True)

        vendor_data = {
            'date': '2025-01-15',
            'description': 'Test invoice',
            'total_amount': 121.00,
            'vat_amount': 21.00
        }
        file_data = {
            'folder': 'Facturen/NewVendor',
            'url': 'https://drive.google.com/file/d/test/view',
            'name': 'test_invoice.pdf'
        }

        error_result = {
            'error': True,
            'message': 'No booking history found for vendor "NewVendor". Manual account selection required.',
            'results': []
        }

        with patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_tl = MagicMock()
            mock_tl.get_last_transactions.return_value = error_result
            mock_tl_class.return_value = mock_tl

            # Should handle error gracefully (falls back to defaults via except)
            result = processor._format_vendor_transactions(vendor_data, file_data)

            # Should still return transactions (with fallback accounts from except block)
            assert isinstance(result, list)
            assert len(result) > 0

    def test_format_vendor_transactions_uses_transaction_logic_results(self):
        """_format_vendor_transactions should use accounts from TransactionLogic."""
        from pdf_processor import PDFProcessor

        processor = PDFProcessor(test_mode=True)

        vendor_data = {
            'date': '2025-01-15',
            'description': 'Test invoice',
            'total_amount': 121.00,
            'vat_amount': 21.00
        }
        file_data = {
            'folder': 'Facturen/TestVendor',
            'url': 'https://drive.google.com/file/d/test/view',
            'name': 'test_invoice.pdf'
        }

        mock_transactions = [
            {'Debet': '4100', 'Credit': '1002'},
            {'Debet': '2020', 'Credit': '4100'}
        ]

        with patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_tl = MagicMock()
            mock_tl.get_last_transactions.return_value = mock_transactions
            mock_tl_class.return_value = mock_tl

            result = processor._format_vendor_transactions(vendor_data, file_data)

            assert result[0]['debet'] == '4100', "Main debet should come from TransactionLogic"
            assert result[0]['credit'] == '1002', "Main credit should come from TransactionLogic"
            # VAT transaction
            assert result[1]['debet'] == '2020', "VAT debet should come from TransactionLogic"
            assert result[1]['credit'] == '4100', "VAT credit should come from TransactionLogic"


# ---------------------------------------------------------------------------
# 3.4 — Preservation: same results when flags match old accounts
# ---------------------------------------------------------------------------

class TestPatternValidationPreservation:
    """
    Verify that get_patterns() returns the same results when $.bank_account
    flags identify the same accounts as those below 1300.

    Validates: Requirement 3.4
    """

    def test_query_still_filters_by_administration(self):
        """get_patterns() must still filter by administration."""
        from database import DatabaseManager

        captured_queries = []

        def capture_query(query, params=None, **kwargs):
            captured_queries.append(query)
            return []

        db = DatabaseManager.__new__(DatabaseManager)
        with patch.object(db, 'execute_query', side_effect=capture_query):
            db.get_patterns('TestTenant')

        query = captured_queries[0]
        assert 'administration = %s' in query, (
            "get_patterns() must still filter by administration"
        )

    def test_query_still_filters_by_date(self):
        """get_patterns() must still filter by 2-year date range."""
        from database import DatabaseManager

        captured_queries = []

        def capture_query(query, params=None, **kwargs):
            captured_queries.append(query)
            return []

        db = DatabaseManager.__new__(DatabaseManager)
        with patch.object(db, 'execute_query', side_effect=capture_query):
            db.get_patterns('TestTenant')

        query = captured_queries[0]
        assert 'INTERVAL 2 YEAR' in query, (
            "get_patterns() must still filter by 2-year date range"
        )

    def test_query_still_orders_by_date_desc(self):
        """get_patterns() must still order by Date DESC."""
        from database import DatabaseManager

        captured_queries = []

        def capture_query(query, params=None, **kwargs):
            captured_queries.append(query)
            return []

        db = DatabaseManager.__new__(DatabaseManager)
        with patch.object(db, 'execute_query', side_effect=capture_query):
            db.get_patterns('TestTenant')

        query = captured_queries[0]
        assert 'ORDER BY Date DESC' in query, (
            "get_patterns() must still order by Date DESC"
        )

    def test_query_still_selects_same_columns(self):
        """get_patterns() must still select debet, credit, administration, referenceNumber, Date."""
        from database import DatabaseManager

        captured_queries = []

        def capture_query(query, params=None, **kwargs):
            captured_queries.append(query)
            return []

        db = DatabaseManager.__new__(DatabaseManager)
        with patch.object(db, 'execute_query', side_effect=capture_query):
            db.get_patterns('TestTenant')

        query = captured_queries[0]
        for col in ['debet', 'credit', 'administration', 'referenceNumber', 'Date']:
            assert col in query, f"get_patterns() must still select '{col}'"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
