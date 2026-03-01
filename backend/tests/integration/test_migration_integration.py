"""
Integration tests for OpeningBalanceMigrator.

These tests run against the actual test database and verify
the complete migration workflow end-to-end.
"""

import pytest
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from scripts.database.migrate_opening_balances import OpeningBalanceMigrator
from src.database import DatabaseManager


@pytest.mark.integration
class TestMigrationIntegration:
    """Integration tests for migration script."""
    
    @pytest.fixture
    def db_manager(self):
        """Create database manager for testing."""
        return DatabaseManager()
    
    @pytest.fixture
    def test_tenant(self):
        """Return a test tenant name."""
        return "TestMigration"
    
    @pytest.fixture
    def cleanup_test_data(self, db_manager, test_tenant):
        """Clean up test data before and after tests."""
        # Cleanup before test
        self._cleanup_tenant_data(db_manager, test_tenant)
        
        yield
        
        # Cleanup after test
        self._cleanup_tenant_data(db_manager, test_tenant)
    
    def _cleanup_tenant_data(self, db_manager, tenant):
        """Remove all test data for tenant."""
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        try:
            # Delete all transactions for test tenant
            cursor.execute("""
                DELETE FROM mutaties
                WHERE administration = %s
            """, (tenant,))
            
            # Delete test account configurations
            cursor.execute("""
                DELETE FROM rekeningschema
                WHERE administration = %s
            """, (tenant,))
            
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    
    def _create_test_accounts(self, db_manager, tenant):
        """Create test chart of accounts."""
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        try:
            accounts = [
                ('1000', 'Bank Account', 'N', '{"roles": ["interim_opening_balance"]}'),
                ('3080', 'Equity Result', 'N', None),
                ('8000', 'Revenue', 'Y', None),
                ('4000', 'Expenses', 'Y', None),
            ]
            
            for account, name, vw, params in accounts:
                cursor.execute("""
                    INSERT INTO rekeningschema (Account, AccountName, VW, administration, parameters)
                    VALUES (%s, %s, %s, %s, %s)
                """, (account, name, vw, tenant, params))
            
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    
    def _create_test_transactions(self, db_manager, tenant, year):
        """Create test transactions for a year."""
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        try:
            transactions = [
                # Balance sheet transactions
                (f'Test {year}-01', f'{year}-01-15', 'Initial deposit', 1000.00, '1000', '3080'),
                (f'Test {year}-02', f'{year}-06-15', 'Additional deposit', 500.00, '1000', '3080'),
                # P&L transactions
                (f'Test {year}-03', f'{year}-03-15', 'Revenue', 2000.00, '1000', '8000'),
                (f'Test {year}-04', f'{year}-04-15', 'Expense', 300.00, '4000', '1000'),
            ]
            
            for trans_num, trans_date, desc, amount, debit, credit in transactions:
                cursor.execute("""
                    INSERT INTO mutaties (
                        TransactionNumber, TransactionDate, TransactionDescription,
                        TransactionAmount, Debet, Credit, administration
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (trans_num, trans_date, desc, amount, debit, credit, tenant))
            
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    
    def _get_transaction_count(self, db_manager, tenant, trans_number_pattern):
        """Get count of transactions matching pattern."""
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM mutaties
                WHERE administration = %s
                AND TransactionNumber LIKE %s
            """, (tenant, trans_number_pattern))
            
            result = cursor.fetchone()
            return result['count']
        finally:
            cursor.close()
            conn.close()
    
    def _get_balance_for_account(self, db_manager, tenant, account, end_date):
        """Get balance for account up to end date."""
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("""
                SELECT SUM(Amount) as balance
                FROM vw_mutaties
                WHERE administration = %s
                AND Reknum = %s
                AND TransactionDate <= %s
            """, (tenant, account, end_date))
            
            result = cursor.fetchone()
            return float(result['balance']) if result['balance'] else 0.0
        finally:
            cursor.close()
            conn.close()
    
    def test_full_migration_single_tenant(self, db_manager, test_tenant, cleanup_test_data):
        """Test complete migration for a single tenant."""
        # Setup test data - use current year - 2 for test data
        current_year = datetime.now().year
        test_year = current_year - 2
        migration_year = current_year - 1
        
        self._create_test_accounts(db_manager, test_tenant)
        self._create_test_transactions(db_manager, test_tenant, test_year)
        
        # Run migration for next year
        migrator = OpeningBalanceMigrator(dry_run=False, verbose=False)
        success = migrator.migrate(tenant=test_tenant, start_year=migration_year, end_year=migration_year)
        
        # Verify migration succeeded
        assert success is True
        assert migrator.stats['tenants_processed'] == 1
        assert migrator.stats['tenants_failed'] == 0
        assert migrator.stats['years_processed'] == 1
        
        # Verify opening balance transactions were created
        opening_balance_count = self._get_transaction_count(
            db_manager, test_tenant, f'OpeningBalance {migration_year}%'
        )
        assert opening_balance_count > 0
    
    def test_idempotent_execution(self, db_manager, test_tenant, cleanup_test_data):
        """Test that migration can be run multiple times safely."""
        # Setup test data - use current year - 2 for test data
        current_year = datetime.now().year
        test_year = current_year - 2
        migration_year = current_year - 1
        
        self._create_test_accounts(db_manager, test_tenant)
        self._create_test_transactions(db_manager, test_tenant, test_year)
        
        # Run migration first time
        migrator1 = OpeningBalanceMigrator(dry_run=False, verbose=False)
        success1 = migrator1.migrate(tenant=test_tenant, start_year=migration_year, end_year=migration_year)
        assert success1 is True
        
        # Get transaction count after first run
        count1 = self._get_transaction_count(
            db_manager, test_tenant, f'OpeningBalance {migration_year}%'
        )
        
        # Run migration second time
        migrator2 = OpeningBalanceMigrator(dry_run=False, verbose=False)
        success2 = migrator2.migrate(tenant=test_tenant, start_year=migration_year, end_year=migration_year)
        assert success2 is True
        
        # Get transaction count after second run
        count2 = self._get_transaction_count(
            db_manager, test_tenant, f'OpeningBalance {migration_year}%'
        )
        
        # Should be same count (idempotent)
        assert count1 == count2
    
    def test_multiple_years(self, db_manager, test_tenant, cleanup_test_data):
        """Test migration with multiple years."""
        # Setup test data - use current year - 3 and - 2 for test data
        current_year = datetime.now().year
        test_year1 = current_year - 3
        test_year2 = current_year - 2
        migration_year1 = current_year - 2
        migration_year2 = current_year - 1
        
        self._create_test_accounts(db_manager, test_tenant)
        self._create_test_transactions(db_manager, test_tenant, test_year1)
        self._create_test_transactions(db_manager, test_tenant, test_year2)
        
        # Run migration for both years
        migrator = OpeningBalanceMigrator(dry_run=False, verbose=False)
        success = migrator.migrate(tenant=test_tenant, start_year=migration_year1, end_year=migration_year2)
        
        # Verify migration succeeded
        assert success is True
        assert migrator.stats['years_processed'] == 2
        
        # Verify opening balances for both years
        count_year1 = self._get_transaction_count(
            db_manager, test_tenant, f'OpeningBalance {migration_year1}%'
        )
        count_year2 = self._get_transaction_count(
            db_manager, test_tenant, f'OpeningBalance {migration_year2}%'
        )
        
        assert count_year1 > 0
        assert count_year2 > 0
    
    def test_balance_accuracy(self, db_manager, test_tenant, cleanup_test_data):
        """Test that opening balances are calculated correctly."""
        # Setup test data - use current year - 2 for test data
        current_year = datetime.now().year
        test_year = current_year - 2
        migration_year = current_year - 1
        
        self._create_test_accounts(db_manager, test_tenant)
        self._create_test_transactions(db_manager, test_tenant, test_year)
        
        # Get balance before migration
        balance_before = self._get_balance_for_account(
            db_manager, test_tenant, '1000', f'{test_year}-12-31'
        )
        
        # Run migration
        migrator = OpeningBalanceMigrator(dry_run=False, verbose=False)
        success = migrator.migrate(tenant=test_tenant, start_year=migration_year, end_year=migration_year)
        assert success is True
        
        # Get balance after migration (should include opening balance)
        balance_after = self._get_balance_for_account(
            db_manager, test_tenant, '1000', f'{migration_year}-12-31'
        )
        
        # Balance should be same (opening balance + migration_year transactions = old balance)
        # Since we have no migration_year transactions, balance_after should equal balance_before
        assert abs(balance_after - balance_before) < 0.01
    
    def test_no_interim_account_configured(self, db_manager, test_tenant, cleanup_test_data):
        """Test migration fails gracefully when interim account not configured."""
        # Setup test data WITHOUT interim account - use current year - 2 for test data
        current_year = datetime.now().year
        test_year = current_year - 2
        migration_year = current_year - 1
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        try:
            # Create accounts without interim role
            accounts = [
                ('1000', 'Bank Account', 'N', None),  # No role
                ('3080', 'Equity Result', 'N', None),
            ]
            
            for account, name, vw, params in accounts:
                cursor.execute("""
                    INSERT INTO rekeningschema (Account, AccountName, VW, administration, parameters)
                    VALUES (%s, %s, %s, %s, %s)
                """, (account, name, vw, test_tenant, params))
            
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        
        # Create transactions
        self._create_test_transactions(db_manager, test_tenant, test_year)
        
        # Run migration - should fail
        migrator = OpeningBalanceMigrator(dry_run=False, verbose=False)
        success = migrator.migrate(tenant=test_tenant, start_year=migration_year, end_year=migration_year)
        
        # Should fail due to missing interim account
        assert success is False
        assert migrator.stats['tenants_failed'] == 1
    
    def test_no_balance_sheet_accounts(self, db_manager, test_tenant, cleanup_test_data):
        """Test migration with no balance sheet accounts (only P&L)."""
        # Setup test data - use current year - 2 for test data
        current_year = datetime.now().year
        test_year = current_year - 2
        migration_year = current_year - 1
        
        self._create_test_accounts(db_manager, test_tenant)
        
        # Create only P&L transactions
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO mutaties (
                    TransactionNumber, TransactionDate, TransactionDescription,
                    TransactionAmount, Debet, Credit, administration
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (f'Test {test_year}-01', f'{test_year}-01-15', 'Revenue', 1000.00, '8000', '8000', test_tenant))
            
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        
        # Run migration
        migrator = OpeningBalanceMigrator(dry_run=False, verbose=False)
        success = migrator.migrate(tenant=test_tenant, start_year=migration_year, end_year=migration_year)
        
        # Should succeed but create no opening balances
        assert success is True
        
        # No opening balance transactions should be created
        count = self._get_transaction_count(
            db_manager, test_tenant, f'OpeningBalance {migration_year}%'
        )
        assert count == 0
    
    def test_dry_run_mode(self, db_manager, test_tenant, cleanup_test_data):
        """Test that dry-run mode doesn't create transactions."""
        # Setup test data - use current year - 2 for test data
        current_year = datetime.now().year
        test_year = current_year - 2
        migration_year = current_year - 1
        
        self._create_test_accounts(db_manager, test_tenant)
        self._create_test_transactions(db_manager, test_tenant, test_year)
        
        # Run migration in dry-run mode
        migrator = OpeningBalanceMigrator(dry_run=True, verbose=False)
        success = migrator.migrate(tenant=test_tenant, start_year=migration_year, end_year=migration_year)
        
        # Should succeed
        assert success is True
        
        # But no transactions should be created
        count = self._get_transaction_count(
            db_manager, test_tenant, f'OpeningBalance {migration_year}%'
        )
        assert count == 0
    
    def test_tenant_isolation(self, db_manager, cleanup_test_data):
        """Test that migration only affects specified tenant."""
        tenant1 = "TestMigration1"
        tenant2 = "TestMigration2"
        
        # Use current year - 2 for test data
        current_year = datetime.now().year
        test_year = current_year - 2
        migration_year = current_year - 1
        
        try:
            # Setup data for both tenants
            self._create_test_accounts(db_manager, tenant1)
            self._create_test_accounts(db_manager, tenant2)
            self._create_test_transactions(db_manager, tenant1, test_year)
            self._create_test_transactions(db_manager, tenant2, test_year)
            
            # Migrate only tenant1
            migrator = OpeningBalanceMigrator(dry_run=False, verbose=False)
            success = migrator.migrate(tenant=tenant1, start_year=migration_year, end_year=migration_year)
            assert success is True
            
            # Verify tenant1 has opening balances
            count1 = self._get_transaction_count(
                db_manager, tenant1, f'OpeningBalance {migration_year}%'
            )
            assert count1 > 0
            
            # Verify tenant2 has NO opening balances
            count2 = self._get_transaction_count(
                db_manager, tenant2, f'OpeningBalance {migration_year}%'
            )
            assert count2 == 0
            
        finally:
            # Cleanup both tenants
            self._cleanup_tenant_data(db_manager, tenant1)
            self._cleanup_tenant_data(db_manager, tenant2)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'integration'])
