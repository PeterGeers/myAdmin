"""
Unit tests for Year-End Closure Service

Tests the year-end closure process including validation, transaction creation,
and opening balance generation.
"""

import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.year_end_service import YearEndClosureService


@pytest.fixture
def mock_db():
    """Mock database manager"""
    with patch('services.year_end_service.DatabaseManager') as mock_db_class:
        mock_db_instance = Mock()
        mock_db_class.return_value = mock_db_instance
        yield mock_db_instance


@pytest.fixture
def mock_config_service():
    """Mock year-end config service"""
    with patch('services.year_end_service.YearEndConfigService') as mock_config_class:
        mock_config_instance = Mock()
        mock_config_class.return_value = mock_config_instance
        yield mock_config_instance


@pytest.fixture
def service(mock_db, mock_config_service):
    """Create year-end service with mocked dependencies"""
    return YearEndClosureService(test_mode=True)


@pytest.fixture
def test_administration():
    """Test administration name"""
    return 'TestAdmin'


class TestServiceInitialization:
    """Test service initialization"""
    
    def test_init_creates_database_manager(self, mock_db):
        """Test that initialization creates database manager"""
        service = YearEndClosureService(test_mode=True)
        assert service.db is not None
    
    def test_init_creates_config_service(self, mock_config_service):
        """Test that initialization creates config service"""
        service = YearEndClosureService(test_mode=True)
        assert service.config_service is not None


class TestGetAvailableYears:
    """Test getting available years for closure"""
    
    def test_get_available_years_returns_list(self, service, mock_db, test_administration):
        """Test that available years returns a list"""
        mock_db.execute_query.return_value = [
            {'year': 2023},
            {'year': 2022},
            {'year': 2021}
        ]
        
        years = service.get_available_years(test_administration)
        
        assert isinstance(years, list)
        assert years == [2023, 2022, 2021]
    
    def test_get_available_years_empty(self, service, mock_db, test_administration):
        """Test available years with no results"""
        mock_db.execute_query.return_value = []
        
        years = service.get_available_years(test_administration)
        
        assert years == []
    
    def test_get_available_years_excludes_closed(self, service, mock_db, test_administration):
        """Test that closed years are excluded"""
        # Mock returns only open years (closed years filtered by query)
        mock_db.execute_query.return_value = [
            {'year': 2023},
            {'year': 2022}
        ]
        
        years = service.get_available_years(test_administration)
        
        # Should only have years not in year_closure_status
        assert 2023 in years
        assert 2022 in years


class TestGetClosedYears:
    """Test getting closed years"""
    
    def test_get_closed_years_returns_list(self, service, mock_db, test_administration):
        """Test that closed years returns a list"""
        mock_db.execute_query.return_value = [
            {
                'year': 2022,
                'closed_date': datetime(2023, 1, 15),
                'closed_by': 'user@example.com',
                'closure_transaction_number': 'YearClose 2022',
                'opening_balance_transaction_number': 'OpeningBalance 2023',
                'notes': 'Test closure'
            }
        ]
        
        closed = service.get_closed_years(test_administration)
        
        assert isinstance(closed, list)
        assert len(closed) == 1
        assert closed[0]['year'] == 2022
    
    def test_get_closed_years_empty(self, service, mock_db, test_administration):
        """Test closed years with no results"""
        mock_db.execute_query.return_value = []
        
        closed = service.get_closed_years(test_administration)
        
        assert closed == []


class TestGetYearStatus:
    """Test getting year status"""
    
    def test_get_year_status_found(self, service, mock_db, test_administration):
        """Test getting status for closed year"""
        mock_db.execute_query.return_value = [
            {
                'year': 2022,
                'closed_date': datetime(2023, 1, 15),
                'closed_by': 'user@example.com',
                'closure_transaction_number': 'YearClose 2022',
                'opening_balance_transaction_number': 'OpeningBalance 2023',
                'notes': 'Test closure'
            }
        ]
        
        status = service.get_year_status(test_administration, 2022)
        
        assert status is not None
        assert status['year'] == 2022
    
    def test_get_year_status_not_found(self, service, mock_db, test_administration):
        """Test getting status for non-closed year"""
        mock_db.execute_query.return_value = []
        
        status = service.get_year_status(test_administration, 2023)
        
        assert status is None


class TestCalculateNetPLResult:
    """Test net P&L result calculation"""
    
    def test_calculate_net_pl_profit(self, service, mock_db, test_administration):
        """Test calculating profit"""
        mock_db.execute_query.return_value = [{'net_result': 10000.50}]
        
        result = service._calculate_net_pl_result(test_administration, 2023)
        
        assert result == 10000.50
    
    def test_calculate_net_pl_loss(self, service, mock_db, test_administration):
        """Test calculating loss"""
        mock_db.execute_query.return_value = [{'net_result': -5000.25}]
        
        result = service._calculate_net_pl_result(test_administration, 2023)
        
        assert result == -5000.25
    
    def test_calculate_net_pl_zero(self, service, mock_db, test_administration):
        """Test calculating zero result"""
        mock_db.execute_query.return_value = [{'net_result': 0}]
        
        result = service._calculate_net_pl_result(test_administration, 2023)
        
        assert result == 0.0
    
    def test_calculate_net_pl_no_data(self, service, mock_db, test_administration):
        """Test with no P&L data"""
        mock_db.execute_query.return_value = []
        
        result = service._calculate_net_pl_result(test_administration, 2023)
        
        assert result == 0.0


class TestCountBalanceSheetAccounts:
    """Test counting balance sheet accounts"""
    
    def test_count_balance_sheet_accounts(self, service, mock_db, test_administration):
        """Test counting accounts with balances"""
        # Mock returns count directly
        mock_db.execute_query.return_value = [{'count': 3}]
        
        count = service._count_balance_sheet_accounts(test_administration, 2023)
        
        assert count == 3
    
    def test_count_balance_sheet_accounts_zero(self, service, mock_db, test_administration):
        """Test with no balance sheet accounts"""
        mock_db.execute_query.return_value = [{'count': 0}]
        
        count = service._count_balance_sheet_accounts(test_administration, 2023)
        
        assert count == 0


class TestValidateYearClosure:
    """Test year closure validation"""
    
    def test_validate_year_already_closed(self, service, mock_db, test_administration):
        """Test validation when year is already closed"""
        # Mock year is closed
        mock_db.execute_query.return_value = [{'count': 1}]
        
        validation = service.validate_year_closure(test_administration, 2022)
        
        assert validation['can_close'] is False
        assert any('already closed' in error for error in validation['errors'])
    
    def test_validate_year_previous_not_closed(self, service, mock_db, mock_config_service, test_administration):
        """Test validation when previous year not closed"""
        # Setup mocks
        mock_db.execute_query.side_effect = [
            [{'count': 0}],  # Year not closed
            [{'first_year': 2020}],  # First year
            [{'count': 0}],  # Previous year not closed
            [{'net_result': 10000}],  # Net P&L result (needed even if validation fails)
            [{'count': 1}],  # Balance sheet accounts count
        ]
        mock_config_service.validate_configuration.return_value = {'valid': True, 'errors': []}
        
        validation = service.validate_year_closure(test_administration, 2022)
        
        assert validation['can_close'] is False
        assert any('Previous year' in error for error in validation['errors'])
    
    def test_validate_year_missing_configuration(self, service, mock_db, mock_config_service, test_administration):
        """Test validation with missing configuration"""
        # Setup mocks
        mock_db.execute_query.side_effect = [
            [{'count': 0}],  # Year not closed
            [{'first_year': 2023}],  # First year (no previous check needed)
            [{'net_result': 10000}],  # Net P&L result (calculated even if config invalid)
            [{'count': 1}],  # Balance sheet accounts count
        ]
        mock_config_service.validate_configuration.return_value = {
            'valid': False,
            'errors': ['Missing equity_result account']
        }
        
        validation = service.validate_year_closure(test_administration, 2023)
        
        assert validation['can_close'] is False
        assert 'Missing equity_result account' in validation['errors']
    
    def test_validate_year_success(self, service, mock_db, mock_config_service, test_administration):
        """Test successful validation"""
        # Setup mocks
        mock_db.execute_query.side_effect = [
            [{'count': 0}],  # Year not closed
            [{'first_year': 2023}],  # First year
            [{'net_result': 10000}],  # Net P&L result
            [{'count': 2}],  # Balance sheet accounts count
        ]
        mock_config_service.validate_configuration.return_value = {'valid': True, 'errors': []}
        
        validation = service.validate_year_closure(test_administration, 2023)
        
        assert validation['can_close'] is True
        assert len(validation['errors']) == 0
        assert validation['info']['net_result'] == 10000
        assert validation['info']['balance_sheet_accounts'] == 2
    
    def test_validate_year_zero_result_warning(self, service, mock_db, mock_config_service, test_administration):
        """Test validation with zero P&L result shows warning"""
        # Setup mocks
        mock_db.execute_query.side_effect = [
            [{'count': 0}],  # Year not closed
            [{'first_year': 2023}],  # First year
            [{'net_result': 0}],  # Zero net result
            [{'count': 1}],  # Balance sheet accounts count
        ]
        mock_config_service.validate_configuration.return_value = {'valid': True, 'errors': []}
        
        validation = service.validate_year_closure(test_administration, 2023)
        
        assert validation['can_close'] is True
        assert any('zero' in warning.lower() for warning in validation['warnings'])


class TestIsYearClosed:
    """Test checking if year is closed"""
    
    def test_is_year_closed_true(self, service, mock_db, test_administration):
        """Test year is closed"""
        mock_db.execute_query.return_value = [{'count': 1}]
        
        is_closed = service._is_year_closed(test_administration, 2022)
        
        assert is_closed is True
    
    def test_is_year_closed_false(self, service, mock_db, test_administration):
        """Test year is not closed"""
        mock_db.execute_query.return_value = [{'count': 0}]
        
        is_closed = service._is_year_closed(test_administration, 2023)
        
        assert is_closed is False


class TestGetFirstYear:
    """Test getting first year with transactions"""
    
    def test_get_first_year(self, service, mock_db, test_administration):
        """Test getting first year"""
        mock_db.execute_query.return_value = [{'first_year': 2020}]
        
        first_year = service._get_first_year(test_administration)
        
        assert first_year == 2020
    
    def test_get_first_year_no_data(self, service, mock_db, test_administration):
        """Test with no transaction data"""
        mock_db.execute_query.return_value = [{'first_year': None}]
        
        first_year = service._get_first_year(test_administration)
        
        assert first_year is None


class TestCreateClosureTransaction:
    """Test creating year-end closure transaction"""
    
    def test_create_closure_transaction_profit(self, service, mock_db, mock_config_service, test_administration):
        """Test creating closure transaction for profit"""
        # Setup mocks
        mock_cursor = Mock()
        mock_config_service.get_account_by_purpose.side_effect = [
            {'Account': '3080'},  # equity_result
            {'Account': '8999'}   # pl_closing
        ]
        mock_db.execute_query.return_value = [{'net_result': -10000}]  # Negative = profit in vw_mutaties
        
        transaction_number = service._create_closure_transaction(
            test_administration, 2023, mock_cursor
        )
        
        # Verify transaction created
        assert transaction_number == 'YearClose 2023'
        mock_cursor.execute.assert_called_once()
        
        # Verify correct debit/credit for profit (negative net_result)
        call_args = mock_cursor.execute.call_args[0]
        params = call_args[1]
        assert params[4] == '8999'  # Debit: P&L closing
        assert params[5] == '3080'  # Credit: Equity
        assert params[3] == 10000   # Amount (absolute value)
        assert params[6] == 'Year Closure'  # ReferenceNumber
    
    def test_create_closure_transaction_loss(self, service, mock_db, mock_config_service, test_administration):
        """Test creating closure transaction for loss"""
        # Setup mocks
        mock_cursor = Mock()
        mock_config_service.get_account_by_purpose.side_effect = [
            {'Account': '3080'},  # equity_result
            {'Account': '8999'}   # pl_closing
        ]
        mock_db.execute_query.return_value = [{'net_result': 5000}]  # Positive = loss in vw_mutaties
        
        transaction_number = service._create_closure_transaction(
            test_administration, 2023, mock_cursor
        )
        
        # Verify transaction created
        assert transaction_number == 'YearClose 2023'
        
        # Verify correct debit/credit for loss (positive net_result)
        call_args = mock_cursor.execute.call_args[0]
        params = call_args[1]
        assert params[4] == '3080'  # Debit: Equity
        assert params[5] == '8999'  # Credit: P&L closing
        assert params[3] == 5000    # Amount (already positive)
        assert params[6] == 'Year Closure'  # ReferenceNumber
    
    def test_create_closure_transaction_zero(self, service, mock_db, mock_config_service, test_administration):
        """Test creating closure transaction with zero result"""
        # Setup mocks
        mock_cursor = Mock()
        mock_config_service.get_account_by_purpose.side_effect = [
            {'Account': '3080'},  # equity_result
            {'Account': '8999'}   # pl_closing
        ]
        mock_db.execute_query.return_value = [{'net_result': 0}]
        
        transaction_number = service._create_closure_transaction(
            test_administration, 2023, mock_cursor
        )
        
        # No transaction should be created for zero result
        assert transaction_number is None
        mock_cursor.execute.assert_not_called()
    
    def test_create_closure_transaction_missing_accounts(self, service, mock_config_service, test_administration):
        """Test error when required accounts not configured"""
        # Setup mocks
        mock_cursor = Mock()
        mock_config_service.get_account_by_purpose.return_value = None
        
        with pytest.raises(ValueError, match="Required accounts not configured"):
            service._create_closure_transaction(test_administration, 2023, mock_cursor)


class TestGetEndingBalances:
    """Test getting ending balances"""
    
    def test_get_ending_balances_dict_cursor(self, service, test_administration):
        """Test with dict cursor results"""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = {'count': 0}  # No existing opening balance
        mock_cursor.fetchall.return_value = [
            {'account': '1000', 'account_name': 'Cash', 'balance': 5000.00},
            {'account': '2000', 'account_name': 'Accounts Payable', 'balance': -3000.00}
        ]
        
        balances = service._get_ending_balances(test_administration, 2023, mock_cursor)
        
        assert len(balances) == 2
        assert balances[0]['account'] == '1000'
        assert balances[0]['balance'] == 5000.00
        assert balances[1]['account'] == '2000'
        assert balances[1]['balance'] == -3000.00
    
    def test_get_ending_balances_tuple_cursor(self, service, test_administration):
        """Test with tuple cursor results"""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (0,)  # No existing opening balance (tuple format)
        mock_cursor.fetchall.return_value = [
            ('1000', 'Cash', 5000.00),
            ('2000', 'Accounts Payable', -3000.00)
        ]
        
        balances = service._get_ending_balances(test_administration, 2023, mock_cursor)
        
        assert len(balances) == 2
        assert balances[0]['account'] == '1000'
        assert balances[0]['balance'] == 5000.00
    
    def test_get_ending_balances_empty(self, service, test_administration):
        """Test with no balances"""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = {'count': 0}  # No existing opening balance
        mock_cursor.fetchall.return_value = []
        
        balances = service._get_ending_balances(test_administration, 2023, mock_cursor)
        
        assert balances == []


class TestCreateOpeningBalances:
    """Test creating opening balance transactions"""
    
    def test_create_opening_balances_success(self, service, mock_config_service, test_administration):
        """Test creating opening balances"""
        # Setup mocks
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = {'count': 0}  # No existing opening balance
        mock_cursor.fetchall.return_value = [
            {'account': '1000', 'account_name': 'Cash', 'balance': 5000.00},
            {'account': '2000', 'account_name': 'Accounts Payable', 'balance': -3000.00}
        ]
        mock_config_service.get_account_by_purpose.return_value = {'Account': '3080'}  # equity account
        
        transaction_number = service._create_opening_balances(
            test_administration, 2024, mock_cursor
        )
        
        # Verify transaction created
        assert transaction_number == 'OpeningBalance 2024'
        
        # Verify four calls: 1 check query + 1 balance query + 2 inserts (one for each balance)
        assert mock_cursor.execute.call_count == 4
    
    def test_create_opening_balances_positive_balance(self, service, mock_config_service, test_administration):
        """Test opening balance for positive balance (asset)"""
        # Setup mocks
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = {'count': 0}  # No existing opening balance
        mock_cursor.fetchall.return_value = [
            {'account': '1000', 'account_name': 'Cash', 'balance': 5000.00}
        ]
        mock_config_service.get_account_by_purpose.return_value = {'Account': '3080'}  # equity account
        
        service._create_opening_balances(test_administration, 2024, mock_cursor)
        
        # Verify correct debit/credit for positive balance
        # Get the last call (the INSERT, not the check query)
        call_args = mock_cursor.execute.call_args[0]
        params = call_args[1]
        assert params[4] == '1000'  # Debit: Account
        assert params[5] == '3080'  # Credit: Equity
        assert params[3] == 5000.00  # Amount
        assert params[6] == 'Opening Balance'  # ReferenceNumber
    
    def test_create_opening_balances_negative_balance(self, service, mock_config_service, test_administration):
        """Test opening balance for negative balance (liability)"""
        # Setup mocks
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = {'count': 0}  # No existing opening balance
        mock_cursor.fetchall.return_value = [
            {'account': '2000', 'account_name': 'Accounts Payable', 'balance': -3000.00}
        ]
        mock_config_service.get_account_by_purpose.return_value = {'Account': '3080'}  # equity account
        
        service._create_opening_balances(test_administration, 2024, mock_cursor)
        
        # Verify correct debit/credit for negative balance
        call_args = mock_cursor.execute.call_args[0]
        params = call_args[1]
        assert params[4] == '3080'  # Debit: Equity
        assert params[5] == '2000'  # Credit: Account
        assert params[3] == 3000.00  # Amount (absolute value)
        assert params[6] == 'Opening Balance'  # ReferenceNumber
    
    def test_create_opening_balances_no_balances(self, service, mock_config_service, test_administration):
        """Test with no balances to carry forward"""
        # Setup mocks
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = {'count': 0}  # No existing opening balance
        mock_cursor.fetchall.return_value = []
        mock_config_service.get_account_by_purpose.return_value = {'Account': '3080'}  # equity account
        
        transaction_number = service._create_opening_balances(
            test_administration, 2024, mock_cursor
        )
        
        # No transaction should be created
        assert transaction_number is None
        # Only the check query and balance query should be executed, no inserts
        assert mock_cursor.execute.call_count == 2
    
    def test_create_opening_balances_missing_equity_account(self, service, mock_config_service, test_administration):
        """Test error when equity account not configured"""
        # Setup mocks
        mock_cursor = Mock()
        mock_config_service.get_account_by_purpose.return_value = None
        
        with pytest.raises(ValueError, match="Equity result account not configured"):
            service._create_opening_balances(test_administration, 2024, mock_cursor)


class TestRecordClosureStatus:
    """Test recording closure status"""
    
    def test_record_closure_status(self, service, test_administration):
        """Test recording closure status"""
        mock_cursor = Mock()
        
        service._record_closure_status(
            test_administration,
            2023,
            'user@example.com',
            'YearClose 2023',
            'OpeningBalance 2024',
            'Test notes',
            mock_cursor
        )
        
        # Verify insert executed
        mock_cursor.execute.assert_called_once()
        
        # Verify correct parameters
        call_args = mock_cursor.execute.call_args[0]
        params = call_args[1]
        assert params[0] == test_administration
        assert params[1] == 2023
        assert params[3] == 'user@example.com'
        assert params[4] == 'YearClose 2023'
        assert params[5] == 'OpeningBalance 2024'
        assert params[6] == 'Test notes'


class TestCloseYear:
    """Test full year closure process"""
    
    def test_close_year_validation_fails(self, service, mock_db, mock_config_service, test_administration):
        """Test close year when validation fails"""
        # Setup validation to fail
        mock_db.execute_query.return_value = [{'count': 1}]  # Year already closed
        
        with pytest.raises(Exception, match="Cannot close year"):
            service.close_year(test_administration, 2023, 'user@example.com')
    
    def test_close_year_success(self, service, mock_db, mock_config_service, test_administration):
        """Test successful year closure"""
        # Setup mocks for validation
        mock_db.execute_query.side_effect = [
            [{'count': 0}],  # Year not closed
            [{'first_year': 2023}],  # First year
            [{'net_result': -10000}],  # Net P&L result (negative = profit)
            [{'count': 2}],  # Balance sheet accounts count
            [{'net_result': -10000}],  # Net P&L result (called again in _create_closure_transaction)
        ]
        mock_config_service.validate_configuration.return_value = {'valid': True, 'errors': []}
        
        # Setup mocks for transaction creation
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'count': 0}  # No existing opening balance
        mock_cursor.fetchall.return_value = [
            {'account': '1000', 'account_name': 'Cash', 'balance': 5000.00}
        ]
        mock_db.get_connection.return_value = mock_conn
        
        mock_config_service.get_account_by_purpose.side_effect = [
            {'Account': '3080'},  # equity_result (for closure)
            {'Account': '8999'},  # pl_closing (for closure)
            {'Account': '3080'}   # equity_result (for opening balances)
        ]
        
        # Execute
        result = service.close_year(test_administration, 2023, 'user@example.com', 'Test notes')
        
        # Verify success
        assert result['success'] is True
        assert result['year'] == 2023
        assert result['closure_transaction_number'] == 'YearClose 2023'
        assert result['opening_transaction_number'] == 'OpeningBalance 2024'
        
        # Verify commit called
        mock_conn.commit.assert_called_once()
    
    def test_close_year_rollback_on_error(self, service, mock_db, mock_config_service, test_administration):
        """Test rollback when error occurs during closure"""
        # Setup mocks for validation
        mock_db.execute_query.side_effect = [
            [{'count': 0}],  # Year not closed
            [{'first_year': 2023}],  # First year
            [{'net_result': 10000}],  # Net P&L result
            [{'count': 1}],  # Balance sheet accounts count
        ]
        mock_config_service.validate_configuration.return_value = {'valid': True, 'errors': []}
        
        # Setup mocks to cause error
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("Database error")
        mock_db.get_connection.return_value = mock_conn
        
        mock_config_service.get_account_by_purpose.return_value = {'Account': '3080'}
        
        # Execute and expect error
        with pytest.raises(Exception, match="Failed to close year"):
            service.close_year(test_administration, 2023, 'user@example.com')
        
        # Verify rollback called
        mock_conn.rollback.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
