"""
Unit tests for OpeningBalanceMigrator class.

Tests the migration script logic without requiring database access.
"""

import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from scripts.database.migrate_opening_balances import OpeningBalanceMigrator


class TestOpeningBalanceMigrator:
    """Test suite for OpeningBalanceMigrator class."""
    
    @pytest.fixture
    def migrator(self):
        """Create a migrator instance for testing."""
        with patch('scripts.database.migrate_opening_balances.DatabaseManager'):
            migrator = OpeningBalanceMigrator(dry_run=True, verbose=False)
            migrator.db_manager = Mock()
            return migrator
    
    @pytest.fixture
    def mock_connection(self):
        """Create a mock database connection."""
        conn = Mock()
        cursor = Mock()
        conn.cursor.return_value = cursor
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        return conn, cursor
    
    def test_init(self):
        """Test migrator initialization."""
        with patch('scripts.database.migrate_opening_balances.DatabaseManager'):
            migrator = OpeningBalanceMigrator(dry_run=True, verbose=True)
            
            assert migrator.dry_run is True
            assert migrator.verbose is True
            assert migrator.stats['tenants_processed'] == 0
            assert migrator.stats['tenants_failed'] == 0
            assert migrator.stats['years_processed'] == 0
            assert migrator.stats['transactions_created'] == 0
            assert migrator.stats['validation_errors'] == 0
    
    def test_get_tenants_specific(self, migrator, mock_connection):
        """Test getting a specific tenant."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock tenant exists
        cursor.fetchone.return_value = {'administration': 'TestTenant'}
        
        result = migrator._get_tenants('TestTenant')
        
        assert result == ['TestTenant']
        cursor.execute.assert_called_once()
        assert 'WHERE administration = %s' in cursor.execute.call_args[0][0]
    
    def test_get_tenants_all(self, migrator, mock_connection):
        """Test getting all tenants."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock multiple tenants
        cursor.fetchall.return_value = [
            {'administration': 'Tenant1'},
            {'administration': 'Tenant2'},
            {'administration': 'Tenant3'}
        ]
        
        result = migrator._get_tenants(None)
        
        assert result == ['Tenant1', 'Tenant2', 'Tenant3']
        cursor.execute.assert_called_once()
        assert 'ORDER BY administration' in cursor.execute.call_args[0][0]
    
    def test_get_tenants_not_found(self, migrator, mock_connection):
        """Test getting tenant that doesn't exist."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock tenant not found
        cursor.fetchone.return_value = None
        
        result = migrator._get_tenants('NonExistent')
        
        assert result == []
    
    def test_get_year_range_auto(self, migrator, mock_connection):
        """Test getting year range with auto detection."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock year range - last_year is 2024
        cursor.fetchone.return_value = {
            'first_year': 2020,
            'last_year': 2024
        }
        
        # Default end year is min(current_year - 1, last_year)
        # Since last_year is 2024, result should be 2020-2024
        result = migrator._get_year_range('TestTenant', None, None)
        
        assert result == [2020, 2021, 2022, 2023, 2024]
    
    def test_get_year_range_specific(self, migrator, mock_connection):
        """Test getting specific year range."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock year range
        cursor.fetchone.return_value = {
            'first_year': 2020,
            'last_year': 2024
        }
        
        result = migrator._get_year_range('TestTenant', 2022, 2023)
        
        assert result == [2022, 2023]
    
    def test_get_year_range_no_data(self, migrator, mock_connection):
        """Test getting year range with no data."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock no data
        cursor.fetchone.return_value = {'first_year': None, 'last_year': None}
        
        result = migrator._get_year_range('TestTenant', None, None)
        
        assert result == []
    
    def test_is_already_migrated_true(self, migrator, mock_connection):
        """Test checking if year is already migrated (true)."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock already migrated
        cursor.fetchone.return_value = {'count': 1}
        
        result = migrator._is_already_migrated('TestTenant', 2024)
        
        assert result is True
        cursor.execute.assert_called_once()
        assert 'OpeningBalance 2024' in cursor.execute.call_args[0][1]
    
    def test_is_already_migrated_false(self, migrator, mock_connection):
        """Test checking if year is already migrated (false)."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock not migrated
        cursor.fetchone.return_value = {'count': 0}
        
        result = migrator._is_already_migrated('TestTenant', 2024)
        
        assert result is False
    
    def test_calculate_ending_balances(self, migrator, mock_connection):
        """Test calculating ending balances."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock balance data
        cursor.fetchall.return_value = [
            {'account': '1000', 'account_name': 'Bank', 'VW': 'N', 'balance': 1000.50},
            {'account': '3080', 'account_name': 'Equity', 'VW': 'N', 'balance': -500.25}
        ]
        
        result = migrator._calculate_ending_balances('TestTenant', 2023)
        
        assert len(result) == 2
        assert result[0]['account'] == '1000'
        assert result[0]['balance'] == 1000.50
        assert result[1]['account'] == '3080'
        assert result[1]['balance'] == -500.25
        
        # Verify query
        cursor.execute.assert_called_once()
        query = cursor.execute.call_args[0][0]
        assert "VW = 'N'" in query
        assert 'TransactionDate <= %s' in query
    
    def test_calculate_ending_balances_no_balances(self, migrator, mock_connection):
        """Test calculating ending balances with no results."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock no balances
        cursor.fetchall.return_value = []
        
        result = migrator._calculate_ending_balances('TestTenant', 2023)
        
        assert result == []
    
    def test_get_account_by_role_found(self, migrator, mock_connection):
        """Test getting account by role (found)."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock account found
        cursor.fetchone.return_value = {'Account': '2001'}
        
        result = migrator._get_account_by_role('TestTenant', 'interim_opening_balance')
        
        assert result == '2001'
        cursor.execute.assert_called_once()
        assert 'JSON_CONTAINS' in cursor.execute.call_args[0][0]
    
    def test_get_account_by_role_not_found(self, migrator, mock_connection):
        """Test getting account by role (not found)."""
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock account not found
        cursor.fetchone.return_value = None
        
        result = migrator._get_account_by_role('TestTenant', 'interim_opening_balance')
        
        assert result is None
    
    def test_create_opening_balances_dry_run(self, migrator, mock_connection):
        """Test creating opening balances in dry-run mode."""
        migrator.dry_run = True
        
        balances = [
            {'account': '1000', 'balance': 1000.50},
            {'account': '3080', 'balance': -500.25}
        ]
        
        result = migrator._create_opening_balances('TestTenant', 2024, balances)
        
        # Should return fake IDs in dry-run
        assert len(result) == 2
        assert result == [1, 2]
    
    def test_create_opening_balances_positive_balance(self, migrator, mock_connection):
        """Test creating opening balance for positive balance."""
        migrator.dry_run = False
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock interim account
        with patch.object(migrator, '_get_account_by_role', return_value='2001'):
            cursor.lastrowid = 123
            
            balances = [{'account': '1000', 'balance': 1000.50}]
            
            result = migrator._create_opening_balances('TestTenant', 2024, balances)
            
            assert result == [123]
            
            # Verify transaction insert
            cursor.execute.assert_called()
            insert_call = cursor.execute.call_args[0]
            assert 'INSERT INTO mutaties' in insert_call[0]
            
            # Verify debit/credit for positive balance
            params = insert_call[1]
            assert params[4] == '1000'  # Debit = account
            assert params[5] == '2001'  # Credit = interim
            assert params[3] == 1000.50  # Amount (positive)
    
    def test_create_opening_balances_negative_balance(self, migrator, mock_connection):
        """Test creating opening balance for negative balance."""
        migrator.dry_run = False
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock interim account
        with patch.object(migrator, '_get_account_by_role', return_value='2001'):
            cursor.lastrowid = 124
            
            balances = [{'account': '3080', 'balance': -500.25}]
            
            result = migrator._create_opening_balances('TestTenant', 2024, balances)
            
            assert result == [124]
            
            # Verify debit/credit for negative balance
            insert_call = cursor.execute.call_args[0]
            params = insert_call[1]
            assert params[4] == '2001'  # Debit = interim
            assert params[5] == '3080'  # Credit = account
            assert params[3] == 500.25  # Amount (absolute value)
    
    def test_create_opening_balances_no_interim_account(self, migrator, mock_connection):
        """Test creating opening balances when interim account not configured."""
        migrator.dry_run = False
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock no interim account
        with patch.object(migrator, '_get_account_by_role', return_value=None):
            balances = [{'account': '1000', 'balance': 1000.50}]
            
            result = migrator._create_opening_balances('TestTenant', 2024, balances)
            
            assert result == []
    
    def test_validate_year_dry_run(self, migrator):
        """Test validation in dry-run mode."""
        migrator.dry_run = True
        
        result = migrator._validate_year('TestTenant', 2024)
        
        # Should skip validation in dry-run
        assert result is True
    
    def test_validate_year_success(self, migrator, mock_connection):
        """Test validation success (balances match)."""
        migrator.dry_run = False
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock matching balances
        cursor.fetchall.side_effect = [
            # Old method
            [
                {'account': '1000', 'balance_old': 1000.50},
                {'account': '3080', 'balance_old': -500.25}
            ],
            # New method
            [
                {'account': '1000', 'balance_new': 1000.50},
                {'account': '3080', 'balance_new': -500.25}
            ]
        ]
        
        result = migrator._validate_year('TestTenant', 2024)
        
        assert result is True
    
    def test_validate_year_failure(self, migrator, mock_connection):
        """Test validation failure (balances don't match)."""
        migrator.dry_run = False
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock mismatched balances
        cursor.fetchall.side_effect = [
            # Old method
            [{'account': '1000', 'balance_old': 1000.50}],
            # New method
            [{'account': '1000', 'balance_new': 900.00}]
        ]
        
        result = migrator._validate_year('TestTenant', 2024)
        
        assert result is False
    
    def test_validate_year_rounding_tolerance(self, migrator, mock_connection):
        """Test validation allows small rounding differences."""
        migrator.dry_run = False
        conn, cursor = mock_connection
        migrator.db_manager.get_connection.return_value = conn
        
        # Mock balances with small difference (within 0.01 tolerance)
        cursor.fetchall.side_effect = [
            # Old method
            [{'account': '1000', 'balance_old': 1000.50}],
            # New method
            [{'account': '1000', 'balance_new': 1000.505}]
        ]
        
        result = migrator._validate_year('TestTenant', 2024)
        
        # Should pass due to rounding tolerance
        assert result is True
    
    def test_migrate_year_already_migrated(self, migrator):
        """Test migrating year that's already migrated."""
        with patch.object(migrator, '_is_already_migrated', return_value=True):
            result = migrator._migrate_year('TestTenant', 2024)
            
            assert result is True
    
    def test_migrate_year_no_balances(self, migrator):
        """Test migrating year with no balances."""
        with patch.object(migrator, '_is_already_migrated', return_value=False):
            with patch.object(migrator, '_calculate_ending_balances', return_value=[]):
                result = migrator._migrate_year('TestTenant', 2024)
                
                assert result is True
    
    def test_migrate_year_success(self, migrator):
        """Test successful year migration."""
        balances = [{'account': '1000', 'balance': 1000.50}]
        
        with patch.object(migrator, '_is_already_migrated', return_value=False):
            with patch.object(migrator, '_calculate_ending_balances', return_value=balances):
                with patch.object(migrator, '_create_opening_balances', return_value=[123]):
                    with patch.object(migrator, '_validate_year', return_value=True):
                        result = migrator._migrate_year('TestTenant', 2024)
                        
                        assert result is True
                        assert migrator.stats['transactions_created'] == 1
    
    def test_migrate_year_validation_failure(self, migrator):
        """Test year migration with validation failure."""
        balances = [{'account': '1000', 'balance': 1000.50}]
        
        with patch.object(migrator, '_is_already_migrated', return_value=False):
            with patch.object(migrator, '_calculate_ending_balances', return_value=balances):
                with patch.object(migrator, '_create_opening_balances', return_value=[123]):
                    with patch.object(migrator, '_validate_year', return_value=False):
                        result = migrator._migrate_year('TestTenant', 2024)
                        
                        assert result is False
                        assert migrator.stats['validation_errors'] == 1
    
    def test_migrate_tenant_success(self, migrator):
        """Test successful tenant migration."""
        with patch.object(migrator, '_get_year_range', return_value=[2023, 2024]):
            with patch.object(migrator, '_migrate_year', return_value=True):
                result = migrator._migrate_tenant('TestTenant', None, None)
                
                assert result is True
                assert migrator.stats['years_processed'] == 2
    
    def test_migrate_tenant_no_years(self, migrator):
        """Test tenant migration with no years."""
        with patch.object(migrator, '_get_year_range', return_value=[]):
            result = migrator._migrate_tenant('TestTenant', None, None)
            
            assert result is True
    
    def test_migrate_tenant_year_failure(self, migrator):
        """Test tenant migration with year failure."""
        with patch.object(migrator, '_get_year_range', return_value=[2024]):
            with patch.object(migrator, '_migrate_year', return_value=False):
                result = migrator._migrate_tenant('TestTenant', None, None)
                
                assert result is False
    
    def test_migrate_success(self, migrator):
        """Test successful full migration."""
        with patch.object(migrator, '_get_tenants', return_value=['Tenant1', 'Tenant2']):
            with patch.object(migrator, '_migrate_tenant', return_value=True):
                with patch.object(migrator, '_print_summary'):
                    result = migrator.migrate()
                    
                    assert result is True
                    assert migrator.stats['tenants_processed'] == 2
                    assert migrator.stats['tenants_failed'] == 0
    
    def test_migrate_partial_failure(self, migrator):
        """Test migration with some tenant failures."""
        with patch.object(migrator, '_get_tenants', return_value=['Tenant1', 'Tenant2']):
            with patch.object(migrator, '_migrate_tenant', side_effect=[True, False]):
                with patch.object(migrator, '_print_summary'):
                    result = migrator.migrate()
                    
                    assert result is False
                    assert migrator.stats['tenants_processed'] == 1
                    assert migrator.stats['tenants_failed'] == 1
    
    def test_migrate_no_tenants(self, migrator):
        """Test migration with no tenants found."""
        with patch.object(migrator, '_get_tenants', return_value=[]):
            result = migrator.migrate()
            
            assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
