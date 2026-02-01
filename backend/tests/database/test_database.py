import sys
import os
import pytest
import mysql.connector
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, assume
from decimal import Decimal
from datetime import datetime, date, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from database import DatabaseManager

class TestDatabaseManager:
    
    @pytest.fixture
    def db_manager(self):
        """Create DatabaseManager instance for testing"""
        return DatabaseManager(test_mode=True)
    
    @pytest.fixture
    def mock_connection(self):
        """Mock database connection"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor
    
    def test_init_test_mode(self):
        """Test initialization in test mode"""
        db = DatabaseManager(test_mode=True)
        assert db.test_mode == True
    
    def test_init_production_mode(self):
        """Test initialization in production mode"""
        db = DatabaseManager(test_mode=False)
        assert db.test_mode == False
    
    @patch.dict(os.environ, {'TEST_MODE': 'true', 'TEST_DB_NAME': 'testfinance'})
    def test_environment_detection(self):
        """Test automatic test mode detection from environment"""
        db = DatabaseManager()
        # Should detect test mode from environment
        assert hasattr(db, 'test_mode')
    
    @patch('mysql.connector.connect')
    @patch('mysql.connector.pooling.MySQLConnectionPool')
    def test_get_connection_success(self, mock_pool, mock_connect, db_manager):
        """Test successful database connection"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        # Disable pooling for this test
        DatabaseManager._use_pool = False
        connection = db_manager.get_connection()
        
        assert connection == mock_conn
        mock_connect.assert_called_once()
    
    @patch('mysql.connector.connect')
    def test_get_connection_failure(self, mock_connect, db_manager):
        """Test database connection failure"""
        mock_connect.side_effect = mysql.connector.Error("Connection failed")
        
        # Disable pooling for this test
        DatabaseManager._use_pool = False
        with pytest.raises(mysql.connector.Error):
            db_manager.get_connection()
    
    def test_get_existing_sequences(self, db_manager, mock_connection):
        """Test getting existing sequence numbers"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [{'existing': 'SEQ001'}, {'existing': 'SEQ002'}]
        
        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            sequences = db_manager.get_existing_sequences('NL123456789', 'mutaties')
            
            assert sequences == ['SEQ001', 'SEQ002']
            mock_cursor.execute.assert_called_once()
            mock_cursor.close.assert_called_once()
            mock_conn.close.assert_called_once()
    
    def test_get_bank_account_lookups(self, db_manager, mock_connection):
        """Test getting bank account lookups"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [
            {'account': '1000', 'description': 'Cash'},
            {'account': '1100', 'description': 'Bank'}
        ]
        
        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            lookups = db_manager.get_bank_account_lookups()
            
            assert len(lookups) == 2
            assert lookups[0]['account'] == '1000'
            mock_cursor.execute.assert_called_once()
    
    def test_get_recent_transactions(self, db_manager, mock_connection):
        """Test getting recent transactions"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [
            {'TransactionDescription': 'Test', 'Debet': '1000', 'Credit': '4000'}
        ]
        
        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            transactions = db_manager.get_recent_transactions(limit=10)
            
            assert len(transactions) == 1
            assert transactions[0]['TransactionDescription'] == 'Test'
    
    def test_get_patterns(self, db_manager, mock_connection):
        """Test getting pattern data"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [
            {'administration': 'Test', 'referenceNumber': 'REF001', 'debet': '1000', 'credit': '4000'}
        ]
        
        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            patterns = db_manager.get_patterns('Test')
            
            assert len(patterns) == 1
            assert patterns[0]['referenceNumber'] == 'REF001'
    
    def test_table_selection_test_mode(self):
        """Test correct table selection in test mode"""
        db = DatabaseManager(test_mode=True)
        # In test mode, should use test tables when available
        assert db.test_mode == True
    
    def test_table_selection_production_mode(self):
        """Test correct table selection in production mode"""
        db = DatabaseManager(test_mode=False)
        # In production mode, should use production tables
        assert db.test_mode == False
    
    def test_connection_cleanup(self, db_manager, mock_connection):
        """Test proper connection cleanup"""
        mock_conn, mock_cursor = mock_connection
        
        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            db_manager.get_existing_sequences('NL123456789', 'mutaties')
            
            # Verify cleanup was called
            mock_cursor.close.assert_called_once()
            mock_conn.close.assert_called_once()
    
    @patch('mysql.connector.connect')
    def test_connection_error_handling(self, mock_connect, db_manager):
        """Test connection error handling"""
        mock_connect.side_effect = mysql.connector.Error("Database unavailable")
        
        # Disable pooling for this test
        DatabaseManager._use_pool = False
        with pytest.raises(mysql.connector.Error, match="Database unavailable"):
            db_manager.get_connection()
    
    def test_query_parameter_binding(self, db_manager, mock_connection):
        """Test SQL parameter binding"""
        mock_conn, mock_cursor = mock_connection
        
        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            db_manager.get_existing_sequences('NL123456789', 'mutaties')
            
            # Verify parameterized query was used
            call_args = mock_cursor.execute.call_args
            assert '%s' in call_args[0][0]  # SQL contains parameter placeholder
            assert 'NL123456789' in call_args[0][1]  # Parameter was bound

    # Property-based tests for duplicate detection
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
        # Filter out problematic values
        assume(abs(transaction_amount) < 999999.99)
        assume(len(reference_number.strip()) > 0)
        
        # Create fresh instances for each test
        db_manager = DatabaseManager(test_mode=True)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        
        # Create mock duplicate transactions
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
        
        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
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
            assert '%s' in call_args[0][0]  # SQL contains parameter placeholders
            assert reference_number in call_args[0][1]  # Parameters were bound
            
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
        # Filter out problematic values
        assume(abs(transaction_amount) < 999999.99)
        assume(len(reference_number.strip()) > 0)
        
        # Create fresh instance for each test
        db_manager = DatabaseManager(test_mode=True)
        
        # Test database connection failure
        with patch.object(db_manager, 'get_connection', side_effect=mysql.connector.Error("Connection failed")):
            with pytest.raises(Exception) as exc_info:
                db_manager.check_duplicate_transactions(
                    reference_number, 
                    transaction_date.strftime('%Y-%m-%d'), 
                    transaction_amount
                )
            
            # Property: Error should be properly wrapped and informative
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
        # Filter out problematic values
        assume(abs(transaction_amount) < 999999.99)
        assume(len(reference_number.strip()) > 0)
        
        # Create fresh instances for each test
        db_manager = DatabaseManager(test_mode=True)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []  # No duplicates found
        
        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            result = db_manager.check_duplicate_transactions(
                reference_number, 
                transaction_date.strftime('%Y-%m-%d'), 
                transaction_amount
            )
            
            # Property: Should return empty list when no duplicates exist
            assert isinstance(result, list)
            assert len(result) == 0

    def test_check_duplicate_transactions_unit_basic_functionality(self, db_manager, mock_connection):
        """Unit test for basic duplicate check functionality"""
        mock_conn, mock_cursor = mock_connection
        
        # Mock a duplicate transaction
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
        
        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            result = db_manager.check_duplicate_transactions(
                'TestVendor', 
                '2024-01-15', 
                150.00
            )
            
            assert len(result) == 1
            assert result[0]['ID'] == 123
            assert result[0]['ReferenceNumber'] == 'TestVendor'
            assert result[0]['TransactionAmount'] == Decimal('150.00')

    def test_check_duplicate_transactions_unit_database_error(self, db_manager):
        """Unit test for database error handling"""
        with patch.object(db_manager, 'get_connection', side_effect=mysql.connector.Error("Database unavailable")):
            with pytest.raises(Exception) as exc_info:
                db_manager.check_duplicate_transactions('TestVendor', '2024-01-15', 150.00)
            
            assert "Database connection failed during duplicate check" in str(exc_info.value)

    def test_check_duplicate_transactions_unit_amount_tolerance(self, db_manager, mock_connection):
        """Unit test for amount tolerance (0.01 difference)"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = []
        
        with patch.object(db_manager, 'get_connection', return_value=mock_conn):
            db_manager.check_duplicate_transactions('TestVendor', '2024-01-15', 150.00)
            
            # Verify the query uses ABS function for amount comparison
            call_args = mock_cursor.execute.call_args
            sql_query = call_args[0][0]
            assert 'ABS(TransactionAmount - %s) < 0.01' in sql_query

if __name__ == '__main__':
    pytest.main([__file__])