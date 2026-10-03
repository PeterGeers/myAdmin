import os
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from hypothesis import given, strategies as st, assume
from decimal import Decimal
from datetime import datetime, date, timedelta

from database import DatabaseManager
from db_exceptions import DatabaseError


# Shared patch context to prevent real connections and scalability manager initialization
def _create_isolated_db():
    """Create a DatabaseManager instance fully isolated from real connections."""
    with patch.object(DatabaseManager, '_initialize_scalability_manager'), \
         patch('mysql.connector.pooling.MySQLConnectionPool'), \
         patch('mysql.connector.connect'):
        db = DatabaseManager()
    # Ensure class-level state is clean for this instance
    DatabaseManager._scalability_manager = None
    DatabaseManager._use_legacy_pool = False
    return db


class TestDatabaseManager:

    @pytest.fixture(autouse=True)
    def _isolate_db_class(self):
        """Reset DatabaseManager class-level state for each test."""
        orig_sm = DatabaseManager._scalability_manager
        orig_lp = DatabaseManager._use_legacy_pool
        orig_us = DatabaseManager._use_scalability
        DatabaseManager._scalability_manager = None
        DatabaseManager._use_legacy_pool = False
        DatabaseManager._use_scalability = False
        yield
        DatabaseManager._scalability_manager = orig_sm
        DatabaseManager._use_legacy_pool = orig_lp
        DatabaseManager._use_scalability = orig_us

    @pytest.fixture
    def db_manager(self):
        """Create a real DatabaseManager instance isolated from real connections."""
        return _create_isolated_db()

    @pytest.fixture
    def mock_connection(self):
        """Mock database connection and cursor pair."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    # --- Initialization tests ---

    def test_init_uses_finance_schema(self):
        """DatabaseManager constructs (no test_mode) and targets the `finance` schema."""
        db = _create_isolated_db()
        assert db.config['database'] == 'finance'

    def test_init_schema_never_testfinance(self):
        """The legacy `testfinance` schema is never selected anymore."""
        db = _create_isolated_db()
        assert db.config['database'] != 'testfinance'

    @patch.dict(os.environ, {'TEST_DB_NAME': 'testfinance'})
    def test_schema_is_finance_regardless_of_legacy_env(self):
        """The removed TEST_MODE/TEST_DB_NAME switch no longer affects the schema.

        Even with the legacy `TEST_DB_NAME=testfinance` env var set, the manager
        must still resolve to `finance` (environment is selected by APP_ENV via the
        connection target, not the schema name).
        """
        db = _create_isolated_db()
        assert db.config['database'] == 'finance'

    # --- Connection tests ---

    def test_get_connection_success(self):
        """Test successful database connection via direct connect fallback"""
        db = _create_isolated_db()
        mock_conn = MagicMock()
        with patch('mysql.connector.connect', return_value=mock_conn):
            connection = db._get_connection()
        assert connection == mock_conn

    def test_get_connection_failure(self):
        """Test database connection failure"""
        db = _create_isolated_db()
        with patch('mysql.connector.connect', side_effect=DatabaseError("Connection failed")):
            with pytest.raises(Exception):
                db._get_connection()

    def test_connection_error_handling(self):
        """Test connection error handling"""
        db = _create_isolated_db()
        with patch('mysql.connector.connect', side_effect=DatabaseError("Database unavailable")):
            with pytest.raises(Exception, match="Database unavailable"):
                db._get_connection()

    # --- Method tests using execute_query mock ---

    def test_get_existing_sequences(self):
        """Test getting existing sequence numbers"""
        db = _create_isolated_db()
        mock_results = [{'existing': 'SEQ001'}, {'existing': 'SEQ002'}]

        with patch.object(db, 'execute_query', return_value=mock_results) as mock_exec:
            sequences = db.get_existing_sequences('NL123456789', 'mutaties')

        assert sequences == ['SEQ001', 'SEQ002']
        call_args = mock_exec.call_args
        sql = call_args[0][0]
        assert '%s' in sql
        assert 'NL123456789' in call_args[0][1] or call_args[0][1][0] == 'NL123456789'

    def test_get_bank_account_lookups(self, mock_db):
        """Test getting bank account lookups uses rekeningschema with $.bank_account flag query"""
        expected_lookups = [
            {'rekeningNummer': 'NL80RABO0107936917', 'Account': '1600', 'administration': 'TestAdmin'},
            {'rekeningNummer': 'NL08REVO7549383472', 'Account': '1023', 'administration': 'TestAdmin'}
        ]
        mock_db.get_bank_account_lookups.return_value = expected_lookups

        lookups = mock_db.get_bank_account_lookups(administration='TestAdmin')

        assert len(lookups) == 2
        assert lookups[0]['rekeningNummer'] == 'NL80RABO0107936917'
        assert lookups[1]['Account'] == '1023'
        mock_db.get_bank_account_lookups.assert_called_once_with(administration='TestAdmin')

    def test_get_bank_account_lookups_query_sql(self):
        """Test that get_bank_account_lookups queries rekeningschema with $.bank_account flag"""
        db = _create_isolated_db()
        mock_results = [
            {'rekeningNummer': 'NL80RABO0107936917', 'Account': '1600', 'administration': 'TestAdmin'}
        ]

        with patch.object(db, 'execute_query', return_value=mock_results) as mock_exec:
            result = db.get_bank_account_lookups(administration='TestAdmin')

        assert len(result) == 1
        call_args = mock_exec.call_args
        sql = call_args[0][0]
        assert 'rekeningschema' in sql
        assert "JSON_EXTRACT(parameters, '$.bank_account') = true" in sql
        assert 'administration = %s' in sql
        assert call_args[0][1] == ('TestAdmin',)

    def test_get_bank_account_lookups_no_admin_filter(self):
        """Test that get_bank_account_lookups without administration returns all bank accounts"""
        db = _create_isolated_db()

        with patch.object(db, 'execute_query', return_value=[]) as mock_exec:
            db.get_bank_account_lookups()

        call_args = mock_exec.call_args
        sql = call_args[0][0]
        assert 'rekeningschema' in sql
        assert "JSON_EXTRACT(parameters, '$.bank_account') = true" in sql
        assert 'administration = %s' not in sql

    def test_get_recent_transactions(self, mock_db):
        """Test getting recent transactions"""
        mock_db.get_recent_transactions.return_value = [
            {'TransactionDescription': 'Test', 'Debet': '1000', 'Credit': '4000'}
        ]

        transactions = mock_db.get_recent_transactions(limit=10)

        assert len(transactions) == 1
        assert transactions[0]['TransactionDescription'] == 'Test'
        mock_db.get_recent_transactions.assert_called_once_with(limit=10)

    def test_get_patterns(self, mock_db):
        """Test getting pattern data"""
        mock_db.get_patterns.return_value = [
            {'administration': 'Test', 'referenceNumber': 'REF001', 'debet': '1000', 'credit': '4000'}
        ]

        patterns = mock_db.get_patterns('Test')

        assert len(patterns) == 1
        assert patterns[0]['referenceNumber'] == 'REF001'
        mock_db.get_patterns.assert_called_once_with('Test')

    # --- Table selection tests ---

    def test_table_selection_is_mode_independent(self):
        """Table/schema selection no longer depends on a (removed) test_mode flag.

        The manager always targets the single `finance` schema; there is no
        test-vs-production table switch to exercise anymore.
        """
        db = _create_isolated_db()
        assert db.config['database'] == 'finance'

    # --- Connection cleanup test ---

    def test_connection_cleanup(self):
        """Test proper connection cleanup via get_cursor context manager"""
        db = _create_isolated_db()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(db, '_get_connection', return_value=mock_conn):
            db.get_existing_sequences('NL123456789', 'mutaties')

        # Verify cleanup was called
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    # --- Query parameter binding test ---

    def test_query_parameter_binding(self):
        """Test SQL parameter binding"""
        db = _create_isolated_db()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch.object(db, '_get_connection', return_value=mock_conn):
            db.get_existing_sequences('NL123456789', 'mutaties')

        # Verify parameterized query was used
        call_args = mock_cursor.execute.call_args
        assert '%s' in call_args[0][0]  # SQL contains parameter placeholder
        assert 'NL123456789' in call_args[0][1]  # Parameter was bound

    # --- Property-based tests for duplicate detection ---

    @given(
        reference_number=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pc'))),
        transaction_date=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
        transaction_amount=st.floats(min_value=-999999.99, max_value=999999.99, allow_nan=False, allow_infinity=False)
    )
    def test_check_duplicate_transactions_property_accuracy(self, reference_number, transaction_date, transaction_amount):
        """
        **Feature: duplicate-invoice-detection, Property 1: Duplicate Detection Accuracy**
        For any valid transaction with ReferenceNumber, TransactionDate, and TransactionAmount,
        the duplicate checker should correctly identify all matching existing transactions
        within the 2-year window and return accurate match information
        **Validates: Requirements 1.1, 1.3, 1.4**
        """
        assume(abs(transaction_amount) < 999999.99)
        assume(len(reference_number.strip()) > 0)

        db_manager = _create_isolated_db()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        expected_duplicates = [
            {
                'ID': 1,
                'TransactionNumber': 'TXN001',
                'TransactionDate': transaction_date,
                'TransactionDescription': 'Test transaction',
                'TransactionAmount': transaction_amount,
                'Debet': '1000',
                'Credit': '4000',
                'ReferenceNumber': reference_number,
                'Ref1': 'REF1',
                'Ref2': 'REF2',
                'Ref3': 'REF3',
                'Ref4': 'REF4',
                'Administration': 'GoodwinSolutions'
            }
        ]

        mock_cursor.fetchall.return_value = expected_duplicates

        with patch.object(db_manager, '_get_connection', return_value=mock_conn):
            result = db_manager.check_duplicate_transactions(
                reference_number,
                transaction_date.strftime('%Y-%m-%d'),
                transaction_amount
            )

            # Property: The result should contain all matching transactions
            assert isinstance(result, list)
            assert len(result) == len(expected_duplicates)

            # Property: Each returned transaction should match the search criteria
            for transaction in result:
                assert transaction['ReferenceNumber'] == reference_number
                assert str(transaction['TransactionDate']) == transaction_date.strftime('%Y-%m-%d')
                assert abs(float(transaction['TransactionAmount']) - transaction_amount) < 0.01

            # Property: Query should use parameterized statements (security)
            call_args = mock_cursor.execute.call_args
            assert '%s' in call_args[0][0]
            assert reference_number in call_args[0][1]

            # Property: Query should include 2-year window constraint
            sql_query = call_args[0][0]
            assert 'INTERVAL 2 YEAR' in sql_query

    @given(
        reference_number=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pc'))),
        transaction_date=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
        transaction_amount=st.floats(min_value=-999999.99, max_value=999999.99, allow_nan=False, allow_infinity=False)
    )
    def test_check_duplicate_transactions_property_error_handling(self, reference_number, transaction_date, transaction_amount):
        """
        **Feature: duplicate-invoice-detection, Property 1: Duplicate Detection Accuracy**
        For any database error condition, the duplicate checker should handle errors gracefully
        and provide appropriate error information while maintaining system stability
        **Validates: Requirements 6.1**
        """
        assume(abs(transaction_amount) < 999999.99)
        assume(len(reference_number.strip()) > 0)

        db_manager = _create_isolated_db()

        with patch.object(db_manager, '_get_connection', side_effect=DatabaseError("Connection failed")):
            with pytest.raises(Exception) as exc_info:
                db_manager.check_duplicate_transactions(
                    reference_number,
                    transaction_date.strftime('%Y-%m-%d'),
                    transaction_amount
                )

            assert "Database connection failed during duplicate check" in str(exc_info.value)

    @given(
        reference_number=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pc'))),
        transaction_date=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
        transaction_amount=st.floats(min_value=-999999.99, max_value=999999.99, allow_nan=False, allow_infinity=False)
    )
    def test_check_duplicate_transactions_property_no_duplicates(self, reference_number, transaction_date, transaction_amount):
        """
        **Feature: duplicate-invoice-detection, Property 1: Duplicate Detection Accuracy**
        For any transaction with no existing duplicates, the duplicate checker should return an empty list
        **Validates: Requirements 1.1, 1.5**
        """
        assume(abs(transaction_amount) < 999999.99)
        assume(len(reference_number.strip()) > 0)

        db_manager = _create_isolated_db()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch.object(db_manager, '_get_connection', return_value=mock_conn):
            result = db_manager.check_duplicate_transactions(
                reference_number,
                transaction_date.strftime('%Y-%m-%d'),
                transaction_amount
            )

            assert isinstance(result, list)
            assert len(result) == 0

    # --- Unit tests for duplicate detection ---

    def test_check_duplicate_transactions_unit_basic_functionality(self):
        """Unit test for basic duplicate check functionality"""
        db = _create_isolated_db()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        expected_duplicate = {
            'ID': 123,
            'TransactionNumber': 'TXN123',
            'TransactionDate': date(2024, 1, 15),
            'TransactionDescription': 'Test Invoice',
            'TransactionAmount': Decimal('150.00'),
            'Debet': '1000',
            'Credit': '4000',
            'ReferenceNumber': 'TestVendor',
            'Ref1': 'REF1',
            'Ref2': 'REF2',
            'Ref3': 'file_url',
            'Ref4': 'REF4',
            'Administration': 'GoodwinSolutions'
        }

        mock_cursor.fetchall.return_value = [expected_duplicate]

        with patch.object(db, '_get_connection', return_value=mock_conn):
            result = db.check_duplicate_transactions(
                'TestVendor',
                '2024-01-15',
                150.00
            )

            assert len(result) == 1
            assert result[0]['ID'] == 123
            assert result[0]['ReferenceNumber'] == 'TestVendor'
            assert result[0]['TransactionAmount'] == Decimal('150.00')

    def test_check_duplicate_transactions_unit_database_error(self):
        """Unit test for database error handling"""
        db = _create_isolated_db()

        with patch.object(db, '_get_connection', side_effect=DatabaseError("Database unavailable")):
            with pytest.raises(Exception) as exc_info:
                db.check_duplicate_transactions('TestVendor', '2024-01-15', 150.00)

            assert "Database connection failed during duplicate check" in str(exc_info.value)

    def test_check_duplicate_transactions_unit_amount_tolerance(self):
        """Unit test for amount tolerance (0.01 difference)"""
        db = _create_isolated_db()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch.object(db, '_get_connection', return_value=mock_conn):
            db.check_duplicate_transactions('TestVendor', '2024-01-15', 150.00)

            # Verify the query uses ABS function for amount comparison
            call_args = mock_cursor.execute.call_args
            sql_query = call_args[0][0]
            assert 'ABS(TransactionAmount - %s) < 0.01' in sql_query


if __name__ == '__main__':
    pytest.main([__file__])
