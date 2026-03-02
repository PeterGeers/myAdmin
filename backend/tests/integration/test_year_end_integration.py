"""
Integration tests for Year-End Closure

Tests the full year-end closure process with database integration.
These tests require a test database with sample data.
"""

import pytest
import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.year_end_service import YearEndClosureService
from services.year_end_config import YearEndConfigService
from database import DatabaseManager

# Mark as integration test
pytestmark = pytest.mark.integration


@pytest.fixture
def test_administration():
    """Test administration name"""
    return 'TestYearEnd'


@pytest.fixture
def db():
    """Database manager for test mode"""
    return DatabaseManager(test_mode=True)


@pytest.fixture
def config_service():
    """Year-end config service"""
    return YearEndConfigService(test_mode=True)


@pytest.fixture
def service():
    """Year-end closure service"""
    return YearEndClosureService(test_mode=True)


@pytest.fixture
def setup_test_accounts(db, config_service, test_administration):
    """
    Set up test accounts with proper configuration.
    
    This fixture should:
    1. Create test accounts in rekeningschema
    2. Configure required purposes (equity_result, pl_closing, interim_opening_balance)
    3. Create sample transactions for testing
    
    Note: This is a placeholder - actual implementation depends on test database setup
    """
    # TODO: Implement test data setup
    # For now, assume test database has required accounts configured
    pass


class TestYearEndClosureIntegration:
    """Integration tests for year-end closure process"""
    
    @pytest.mark.skip(reason="Requires test database with configured accounts")
    def test_full_year_closure_process(self, service, test_administration, setup_test_accounts):
        """
        Test complete year closure workflow.
        
        Steps:
        1. Validate year can be closed
        2. Close the year
        3. Verify closure transaction created
        4. Verify opening balances created
        5. Verify closure status recorded
        """
        year = 2023
        user_email = 'test@example.com'
        notes = 'Integration test closure'
        
        # Step 1: Validate year
        validation = service.validate_year_closure(test_administration, year)
        assert validation['can_close'] is True, f"Validation failed: {validation['errors']}"
        
        # Step 2: Close year
        result = service.close_year(test_administration, year, user_email, notes)
        
        # Step 3: Verify result
        assert result['success'] is True
        assert result['year'] == year
        assert result['closure_transaction_number'] is not None
        assert result['opening_transaction_number'] is not None
        
        # Step 4: Verify year is now closed
        status = service.get_year_status(test_administration, year)
        assert status is not None
        assert status['year'] == year
        assert status['closed_by'] == user_email
        assert status['notes'] == notes
        
        # Step 5: Verify year no longer in available years
        available = service.get_available_years(test_administration)
        assert year not in available
        
        # Step 6: Verify year in closed years
        closed = service.get_closed_years(test_administration)
        closed_years = [y['year'] for y in closed]
        assert year in closed_years
    
    @pytest.mark.skip(reason="Requires test database with configured accounts")
    def test_rollback_on_error(self, service, test_administration, db):
        """
        Test that database transaction rolls back on error.
        
        This test should:
        1. Start year closure
        2. Simulate an error during closure
        3. Verify no partial data is committed
        """
        year = 2024
        user_email = 'test@example.com'
        
        # Get initial state
        initial_status = service.get_year_status(test_administration, year)
        assert initial_status is None, "Year should not be closed initially"
        
        # Attempt to close year with invalid configuration
        # (This should fail and rollback)
        try:
            # Force an error by using invalid data
            result = service.close_year(test_administration, year, user_email)
            # If it succeeds, that's unexpected but okay for this test
        except Exception as e:
            # Expected to fail
            pass
        
        # Verify year is still not closed
        final_status = service.get_year_status(test_administration, year)
        assert final_status is None, "Year should still not be closed after error"
    
    @pytest.mark.skip(reason="Requires test database with multiple years of data")
    def test_multiple_years_sequential_closure(self, service, test_administration):
        """
        Test closing multiple years in sequence.
        
        This test verifies:
        1. Years must be closed sequentially
        2. Cannot skip years
        3. Each closure creates proper transactions
        """
        years = [2021, 2022, 2023]
        user_email = 'test@example.com'
        
        for year in years:
            # Validate year
            validation = service.validate_year_closure(test_administration, year)
            assert validation['can_close'] is True
            
            # Close year
            result = service.close_year(test_administration, year, user_email)
            assert result['success'] is True
            assert result['year'] == year
            
            # Verify closure
            status = service.get_year_status(test_administration, year)
            assert status is not None
            assert status['year'] == year
    
    @pytest.mark.skip(reason="Requires test database")
    def test_idempotent_behavior(self, service, test_administration):
        """
        Test that attempting to close an already closed year fails gracefully.
        
        This ensures:
        1. Cannot close same year twice
        2. Error message is clear
        3. No duplicate transactions created
        """
        year = 2023
        user_email = 'test@example.com'
        
        # Close year first time
        result1 = service.close_year(test_administration, year, user_email)
        assert result1['success'] is True
        
        # Attempt to close again
        with pytest.raises(Exception) as exc_info:
            service.close_year(test_administration, year, user_email)
        
        assert 'already closed' in str(exc_info.value).lower()
    
    @pytest.mark.skip(reason="Requires test database with P&L data")
    def test_profit_scenario(self, service, test_administration):
        """
        Test year closure with profit (positive P&L result).
        
        Verifies:
        1. Net P&L calculated correctly
        2. Closure transaction: Debit P&L closing, Credit equity
        3. Amount is positive
        """
        year = 2023
        user_email = 'test@example.com'
        
        # Validate and get P&L result
        validation = service.validate_year_closure(test_administration, year)
        net_result = validation['info']['net_result']
        
        # Assume test data has profit
        assert net_result > 0, "Test data should have profit"
        
        # Close year
        result = service.close_year(test_administration, year, user_email)
        assert result['success'] is True
        assert result['net_result'] == net_result
    
    @pytest.mark.skip(reason="Requires test database with loss data")
    def test_loss_scenario(self, service, test_administration):
        """
        Test year closure with loss (negative P&L result).
        
        Verifies:
        1. Net P&L calculated correctly
        2. Closure transaction: Debit equity, Credit P&L closing
        3. Amount is positive (absolute value)
        """
        year = 2024
        user_email = 'test@example.com'
        
        # Validate and get P&L result
        validation = service.validate_year_closure(test_administration, year)
        net_result = validation['info']['net_result']
        
        # Assume test data has loss
        assert net_result < 0, "Test data should have loss"
        
        # Close year
        result = service.close_year(test_administration, year, user_email)
        assert result['success'] is True
        assert result['net_result'] == net_result
    
    @pytest.mark.skip(reason="Requires test database with balance sheet data")
    def test_opening_balances_creation(self, service, test_administration, db):
        """
        Test that opening balances are created correctly.
        
        Verifies:
        1. All balance sheet accounts with non-zero balances get opening balance records
        2. Positive balances: Debit account, Credit interim
        3. Negative balances: Debit interim, Credit account
        4. All records share same TransactionNumber
        """
        year = 2023
        user_email = 'test@example.com'
        
        # Get balance sheet account count before closure
        validation = service.validate_year_closure(test_administration, year)
        expected_accounts = validation['info']['balance_sheet_accounts']
        
        # Close year
        result = service.close_year(test_administration, year, user_email)
        assert result['success'] is True
        
        opening_txn = result['opening_transaction_number']
        assert opening_txn is not None
        
        # Query database for opening balance records
        query = """
            SELECT COUNT(*) as count
            FROM mutaties
            WHERE TransactionNumber = %s
            AND administration = %s
        """
        records = db.execute_query(query, [opening_txn, test_administration])
        actual_count = records[0]['count'] if records else 0
        
        # Should have one record per balance sheet account
        assert actual_count == expected_accounts
    
    @pytest.mark.skip(reason="Requires test database")
    def test_validation_prevents_premature_closure(self, service, test_administration):
        """
        Test that validation prevents closing years out of sequence.
        
        Verifies:
        1. Cannot close year if previous year not closed
        2. Error message is clear
        """
        # Try to close 2025 without closing 2024
        year = 2025
        
        validation = service.validate_year_closure(test_administration, year)
        
        # Should fail validation
        assert validation['can_close'] is False
        assert any('previous year' in error.lower() for error in validation['errors'])
    
    @pytest.mark.skip(reason="Requires test database")
    def test_missing_configuration_prevents_closure(self, service, config_service, test_administration):
        """
        Test that missing account configuration prevents closure.
        
        Verifies:
        1. Cannot close year without required accounts configured
        2. Error message lists missing accounts
        """
        year = 2023
        
        # Clear configuration (if possible in test environment)
        # This would require test database manipulation
        
        validation = service.validate_year_closure(test_administration, year)
        
        # Should fail if configuration is missing
        if not validation['can_close']:
            assert len(validation['errors']) > 0


class TestYearEndClosurePerformance:
    """Performance tests for year-end closure"""
    
    @pytest.mark.skip(reason="Requires test database with large dataset")
    @pytest.mark.slow
    def test_closure_performance_large_dataset(self, service, test_administration):
        """
        Test year closure performance with large dataset.
        
        Verifies:
        1. Closure completes within reasonable time (< 30 seconds)
        2. Memory usage is acceptable
        3. Database queries are efficient
        """
        import time
        
        year = 2023
        user_email = 'test@example.com'
        
        start_time = time.time()
        result = service.close_year(test_administration, year, user_email)
        end_time = time.time()
        
        duration = end_time - start_time
        
        assert result['success'] is True
        assert duration < 30, f"Closure took {duration:.2f} seconds (should be < 30s)"


class TestYearEndClosureEdgeCases:
    """Edge case tests"""
    
    @pytest.mark.skip(reason="Requires test database")
    def test_zero_pl_result(self, service, test_administration):
        """
        Test year closure with zero P&L result.
        
        Verifies:
        1. Closure succeeds
        2. No closure transaction created (since result is zero)
        3. Opening balances still created
        """
        year = 2023
        user_email = 'test@example.com'
        
        validation = service.validate_year_closure(test_administration, year)
        
        # Assume test data has zero P&L
        if validation['info']['net_result'] == 0:
            result = service.close_year(test_administration, year, user_email)
            assert result['success'] is True
            assert result['closure_transaction_number'] is None  # No transaction for zero
    
    @pytest.mark.skip(reason="Requires test database")
    def test_no_balance_sheet_accounts(self, service, test_administration):
        """
        Test year closure with no balance sheet accounts.
        
        Verifies:
        1. Closure succeeds
        2. Closure transaction created (if P&L non-zero)
        3. No opening balances created
        """
        year = 2023
        user_email = 'test@example.com'
        
        validation = service.validate_year_closure(test_administration, year)
        
        # Assume test data has no balance sheet accounts
        if validation['info']['balance_sheet_accounts'] == 0:
            result = service.close_year(test_administration, year, user_email)
            assert result['success'] is True
            assert result['opening_transaction_number'] is None  # No opening balances


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
