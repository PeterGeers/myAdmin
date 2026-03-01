#!/usr/bin/env python3
"""
Migration Script: Generate Opening Balance Transactions

This script generates opening balance transactions for all historical years,
allowing reports to query only current year data instead of all history.

Usage:
    python migrate_opening_balances.py [options]

Options:
    --dry-run              Preview changes without committing
    --tenant TENANT        Process specific tenant only
    --start-year YEAR      Start from specific year (default: first year with data)
    --end-year YEAR        End at specific year (default: current year - 1)
    --verbose              Enable verbose logging
    --log-file FILE        Log to file (default: logs/migration_YYYYMMDD_HHMMSS.log)

Examples:
    # Dry run for all tenants
    python migrate_opening_balances.py --dry-run

    # Process specific tenant
    python migrate_opening_balances.py --tenant "MyTenant"

    # Process specific year range
    python migrate_opening_balances.py --start-year 2020 --end-year 2023

    # Verbose output with custom log file
    python migrate_opening_balances.py --verbose --log-file migration.log
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.database import DatabaseManager


class OpeningBalanceMigrator:
    """
    Migrates historical data to use opening balance transactions.
    
    This allows reports to query only current year data instead of
    all history, significantly improving performance.
    """
    
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        """
        Initialize the migrator.
        
        Args:
            dry_run: If True, preview changes without committing
            verbose: If True, enable verbose logging
        """
        self.dry_run = dry_run
        self.verbose = verbose
        self.db_manager = DatabaseManager()
        self.logger = logging.getLogger(__name__)
        
        # Statistics
        self.stats = {
            'tenants_processed': 0,
            'tenants_failed': 0,
            'years_processed': 0,
            'transactions_created': 0,
            'validation_errors': 0
        }
    
    def migrate(
        self,
        tenant: Optional[str] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None
    ) -> bool:
        """
        Main migration entry point.
        
        Args:
            tenant: Specific tenant to process (None = all tenants)
            start_year: Start year (None = first year with data)
            end_year: End year (None = current year - 1)
            
        Returns:
            True if migration successful, False otherwise
        """
        self.logger.info("=" * 60)
        self.logger.info("Opening Balance Migration")
        self.logger.info("=" * 60)
        self.logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        self.logger.info(f"Tenant: {tenant or 'ALL'}")
        self.logger.info(f"Start Year: {start_year or 'AUTO'}")
        self.logger.info(f"End Year: {end_year or 'AUTO'}")
        self.logger.info("")
        
        try:
            # Get tenants to process
            tenants = self._get_tenants(tenant)
            
            if not tenants:
                self.logger.error("No tenants found to process")
                return False
            
            self.logger.info(f"Processing {len(tenants)} tenant(s)")
            self.logger.info("")
            
            # Process each tenant
            for tenant_name in tenants:
                success = self._migrate_tenant(
                    tenant_name,
                    start_year,
                    end_year
                )
                
                if success:
                    self.stats['tenants_processed'] += 1
                else:
                    self.stats['tenants_failed'] += 1
            
            # Print summary
            self._print_summary()
            
            return self.stats['tenants_failed'] == 0
            
        except Exception as e:
            self.logger.error(f"Migration failed: {e}", exc_info=True)
            return False
    
    def _get_tenants(self, tenant: Optional[str] = None) -> List[str]:
        """
        Get list of tenants to process.
        
        Args:
            tenant: Specific tenant name or None for all
            
        Returns:
            List of tenant names
        """
        conn = self.db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            if tenant:
                # Verify tenant exists
                cursor.execute("""
                    SELECT DISTINCT administration
                    FROM mutaties
                    WHERE administration = %s
                    LIMIT 1
                """, (tenant,))
                
                result = cursor.fetchone()
                return [tenant] if result else []
            else:
                # Get all tenants
                cursor.execute("""
                    SELECT DISTINCT administration
                    FROM mutaties
                    WHERE administration IS NOT NULL
                    ORDER BY administration
                """)
                
                results = cursor.fetchall()
                return [r['administration'] for r in results]
                
        finally:
            cursor.close()
            conn.close()
    
    def _migrate_tenant(
        self,
        tenant: str,
        start_year: Optional[int],
        end_year: Optional[int]
    ) -> bool:
        """
        Migrate a single tenant.
        
        Args:
            tenant: Tenant name
            start_year: Start year (None = auto)
            end_year: End year (None = auto)
            
        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Processing tenant: {tenant}")
        
        try:
            # Get year range
            years = self._get_year_range(tenant, start_year, end_year)
            
            if not years:
                self.logger.warning(f"  No years to process for {tenant}")
                return True
            
            self.logger.info(f"  Years to process: {years[0]} to {years[-1]}")
            
            # STEP 1: Pre-calculate ALL ending balances using OLD method (before any opening balances exist)
            self.logger.info(f"  Step 1: Pre-calculating ending balances for all years using OLD method")
            ending_balances_by_year = {}
            for year in years:
                balances = self._calculate_ending_balances_old_method(tenant, year)
                if balances:
                    ending_balances_by_year[year] = balances
                    self.logger.debug(f"    Year {year}: {len(balances)} accounts with balances")
            
            # STEP 2: Create opening balance transactions for each year
            self.logger.info(f"  Step 2: Creating opening balance transactions")
            for year in years:
                # Skip first year (no opening balance needed)
                if year == years[0]:
                    self.logger.info(f"    Year {year}: First year, no opening balance needed")
                    continue
                
                # Check if already migrated
                if self._is_already_migrated(tenant, year):
                    self.logger.info(f"    Year {year}: Already migrated")
                    continue
                
                # Get ending balances from previous year
                prev_year = year - 1
                if prev_year not in ending_balances_by_year:
                    self.logger.info(f"    Year {year}: No balances from previous year")
                    continue
                
                balances = ending_balances_by_year[prev_year]
                self.logger.info(f"    Year {year}: Creating {len(balances)} opening balance transactions")
                
                # Create opening balance transactions
                transaction_ids = self._create_opening_balances(tenant, year, balances)
                
                if not transaction_ids:
                    self.logger.error(f"    Failed to create opening balances for {year}")
                    return False
                
                self.stats['transactions_created'] += len(transaction_ids)
            
            # STEP 3: Validate each year
            self.logger.info(f"  Step 3: Validating all years")
            for year in years:
                if year == years[0]:
                    continue  # Skip first year
                
                if not self._validate_year(tenant, year, ending_balances_by_year.get(year, [])):
                    self.logger.error(f"    Validation failed for year {year}")
                    self.stats['validation_errors'] += 1
                    return False
                
                self.logger.info(f"    ✓ Year {year} validated")
                self.stats['years_processed'] += 1
            
            self.logger.info(f"  ✓ Completed {tenant}")
            return True
            
        except Exception as e:
            self.logger.error(f"  Error processing {tenant}: {e}", exc_info=True)
            return False
    
    def _get_year_range(
        self,
        tenant: str,
        start_year: Optional[int],
        end_year: Optional[int]
    ) -> List[int]:
        """
        Get list of years to process for tenant.
        
        Args:
            tenant: Tenant name
            start_year: Start year (None = first year with data)
            end_year: End year (None = current year - 1)
            
        Returns:
            List of years to process
        """
        conn = self.db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Get first and last year with data
            cursor.execute("""
                SELECT 
                    MIN(YEAR(TransactionDate)) as first_year,
                    MAX(YEAR(TransactionDate)) as last_year
                FROM mutaties
                WHERE administration = %s
            """, (tenant,))
            
            result = cursor.fetchone()
            
            if not result or not result['first_year']:
                return []
            
            # Determine range
            first_year = start_year or result['first_year']
            last_year = end_year or (datetime.now().year - 1)
            
            # Don't process beyond data range
            first_year = max(first_year, result['first_year'])
            last_year = min(last_year, result['last_year'])
            
            if first_year > last_year:
                return []
            
            return list(range(first_year, last_year + 1))
            
        finally:
            cursor.close()
            conn.close()
    
    def _is_already_migrated(self, tenant: str, year: int) -> bool:
        """
        Check if year is already migrated.
        
        Args:
            tenant: Tenant name
            year: Year to check
            
        Returns:
            True if already migrated, False otherwise
        """
        conn = self.db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM mutaties
                WHERE administration = %s
                AND TransactionNumber = %s
                AND YEAR(TransactionDate) = %s
            """, (tenant, f"OpeningBalance {year}", year))
            
            result = cursor.fetchone()
            return result['count'] > 0
            
        finally:
            cursor.close()
            conn.close()
    
    def _calculate_ending_balances_old_method(
        self,
        tenant: str,
        year: int
    ) -> List[Dict]:
        """
        Calculate ending balances for balance sheet accounts using OLD method.
        This calculates from beginning of time, EXCLUDING any opening balance transactions.
        
        Args:
            tenant: Tenant name
            year: Year to calculate balances for
            
        Returns:
            List of dicts with account and balance
        """
        self.logger.debug(f"      Calculating ending balances for {year} (OLD method)")
        
        conn = self.db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Query vw_mutaties for balance sheet accounts (VW='N')
            # Sum amounts from beginning of time up to end of year
            # EXCLUDE opening balance transactions
            cursor.execute("""
                SELECT 
                    Reknum as account,
                    AccountName as account_name,
                    VW,
                    SUM(Amount) as balance
                FROM vw_mutaties
                WHERE administration = %s
                AND VW = 'N'
                AND TransactionDate <= %s
                AND TransactionNumber NOT LIKE 'OpeningBalance%'
                GROUP BY Reknum, AccountName, VW
                HAVING ABS(SUM(Amount)) > 0.01
                ORDER BY Reknum
            """, (tenant, f"{year}-12-31"))
            
            results = cursor.fetchall()
            
            self.logger.debug(f"      Found {len(results)} accounts with non-zero balances")
            
            return results
            
        finally:
            cursor.close()
            conn.close()
    
    def _calculate_ending_balances(
        self,
        tenant: str,
        year: int
    ) -> List[Dict]:
        """
        Calculate ending balances for balance sheet accounts.
        
        DEPRECATED: Use _calculate_ending_balances_old_method instead.
        This method is kept for backwards compatibility.
        
        Args:
            tenant: Tenant name
            year: Year to calculate balances for
            
        Returns:
            List of dicts with account and balance
        """
        return self._calculate_ending_balances_old_method(tenant, year)
    
    def _create_opening_balances(
        self,
        tenant: str,
        year: int,
        balances: List[Dict]
    ) -> List[int]:
        """
        Create opening balance transactions.
        
        Args:
            tenant: Tenant name
            year: Year to create opening balances for
            balances: List of account balances
            
        Returns:
            List of transaction IDs created
        """
        self.logger.debug(f"      Creating opening balances for {year}")
        
        if self.dry_run:
            self.logger.debug(f"      DRY RUN: Would create {len(balances)} opening balance transactions")
            return list(range(1, len(balances) + 1))  # Fake IDs for dry run
        
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get interim account from configuration
            interim_account = self._get_account_by_role(tenant, 'interim_opening_balance')
            
            if not interim_account:
                self.logger.error(f"      Interim account not configured for {tenant}")
                return []
            
            transaction_ids = []
            transaction_number = f"OpeningBalance {year}"
            transaction_date = f"{year}-01-01"
            description = f"Opening balance for year {year} of Administration {tenant}"
            
            # Create transaction for each account
            for balance_row in balances:
                account = balance_row['account']
                balance = float(balance_row['balance'])
                
                # Determine debit and credit based on balance sign
                if balance > 0:
                    # Positive balance: account is debit, interim is credit
                    debit = account
                    credit = interim_account
                else:
                    # Negative balance: interim is debit, account is credit
                    debit = interim_account
                    credit = account
                
                amount = abs(balance)
                
                # Insert transaction
                cursor.execute("""
                    INSERT INTO mutaties (
                        TransactionNumber,
                        TransactionDate,
                        TransactionDescription,
                        TransactionAmount,
                        Debet,
                        Credit,
                        administration
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    transaction_number,
                    transaction_date,
                    description,
                    amount,
                    debit,
                    credit,
                    tenant
                ))
                
                transaction_ids.append(cursor.lastrowid)
            
            conn.commit()
            
            self.logger.debug(f"      Created {len(transaction_ids)} transactions")
            return transaction_ids
            
        except Exception as e:
            self.logger.error(f"      Error creating opening balances: {e}")
            conn.rollback()
            return []
            
        finally:
            cursor.close()
            conn.close()
    
    def _get_account_by_role(self, tenant: str, role: str) -> Optional[str]:
        """
        Get account code by role name.
        
        Args:
            tenant: Tenant name
            role: Role name (e.g., 'interim_opening_balance')
            
        Returns:
            Account code or None if not found
        """
        import json
        
        conn = self.db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("""
                SELECT Account
                FROM rekeningschema
                WHERE administration = %s
                AND JSON_CONTAINS(parameters->'$.roles', %s)
                LIMIT 1
            """, (tenant, json.dumps(role)))
            
            result = cursor.fetchone()
            return result['Account'] if result else None
            
        finally:
            cursor.close()
            conn.close()
    
    def _validate_year(self, tenant: str, year: int, expected_ending_balances: List[Dict]) -> bool:
        """
        Validate that migration was successful.
        
        Compares expected ending balances (calculated using OLD method before migration)
        vs actual ending balances (calculated using NEW method with opening balances).
        
        Args:
            tenant: Tenant name
            year: Year to validate
            expected_ending_balances: Pre-calculated ending balances from OLD method
            
        Returns:
            True if validation passed, False otherwise
        """
        self.logger.debug(f"      Validating {year}")
        
        # Skip validation in dry-run mode
        if self.dry_run:
            self.logger.debug(f"      DRY RUN: Skipping validation")
            return True
        
        conn = self.db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Convert expected balances to dict for easy lookup
            expected_balances = {row['account']: float(row['balance']) for row in expected_ending_balances}
            
            # Calculate balances using NEW method (opening balance + current year transactions)
            cursor.execute("""
                SELECT 
                    Reknum as account,
                    SUM(Amount) as balance_new
                FROM vw_mutaties
                WHERE administration = %s
                AND VW = 'N'
                AND TransactionDate >= %s
                AND TransactionDate <= %s
                GROUP BY Reknum
                HAVING ABS(SUM(Amount)) > 0.01
            """, (tenant, f"{year}-01-01", f"{year}-12-31"))
            
            new_balances = {row['account']: float(row['balance_new']) for row in cursor.fetchall()}
            
            # Compare balances
            all_accounts = set(expected_balances.keys()) | set(new_balances.keys())
            errors = []
            
            for account in all_accounts:
                expected_bal = expected_balances.get(account, 0.0)
                new_bal = new_balances.get(account, 0.0)
                diff = abs(expected_bal - new_bal)
                
                # Allow small rounding differences (0.01)
                if diff > 0.01:
                    errors.append({
                        'account': account,
                        'expected_balance': expected_bal,
                        'new_balance': new_bal,
                        'difference': diff
                    })
            
            if errors:
                self.logger.error(f"      Validation failed: {len(errors)} account(s) with differences")
                for error in errors[:5]:  # Show first 5 errors
                    self.logger.error(
                        f"        Account {error['account']}: "
                        f"expected={error['expected_balance']:.2f}, "
                        f"new={error['new_balance']:.2f}, "
                        f"diff={error['difference']:.2f}"
                    )
                if len(errors) > 5:
                    self.logger.error(f"        ... and {len(errors) - 5} more")
                return False
            
            self.logger.debug(f"      Validation passed: {len(all_accounts)} accounts checked")
            return True
            
        except Exception as e:
            self.logger.error(f"      Validation error: {e}")
            return False
            
        finally:
            cursor.close()
            conn.close()
    
    def _print_summary(self):
        """Print migration summary."""
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info("Migration Summary")
        self.logger.info("=" * 60)
        self.logger.info(f"Tenants processed: {self.stats['tenants_processed']}")
        self.logger.info(f"Tenants failed: {self.stats['tenants_failed']}")
        self.logger.info(f"Years processed: {self.stats['years_processed']}")
        self.logger.info(f"Transactions created: {self.stats['transactions_created']}")
        self.logger.info(f"Validation errors: {self.stats['validation_errors']}")
        self.logger.info("=" * 60)


def setup_logging(verbose: bool = False, log_file: Optional[str] = None):
    """
    Setup logging configuration.
    
    Args:
        verbose: Enable verbose logging
        log_file: Log file path (None = auto-generate)
    """
    # Create logs directory if needed
    log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Generate log file name if not provided
    if log_file is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(log_dir, f'migration_{timestamp}.log')
    
    # Configure logging
    level = logging.DEBUG if verbose else logging.INFO
    
    # Create formatters
    console_formatter = logging.Formatter('%(message)s')
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Log file location
    logging.info(f"Logging to: {log_file}")
    logging.info("")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Migrate historical data to use opening balance transactions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without committing to database'
    )
    
    parser.add_argument(
        '--tenant',
        type=str,
        help='Process specific tenant only'
    )
    
    parser.add_argument(
        '--start-year',
        type=int,
        help='Start from specific year (default: first year with data)'
    )
    
    parser.add_argument(
        '--end-year',
        type=int,
        help='End at specific year (default: current year - 1)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--log-file',
        type=str,
        help='Log file path (default: logs/migration_YYYYMMDD_HHMMSS.log)'
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    # Parse arguments
    args = parse_arguments()
    
    # Setup logging
    setup_logging(args.verbose, args.log_file)
    
    # Create migrator
    migrator = OpeningBalanceMigrator(
        dry_run=args.dry_run,
        verbose=args.verbose
    )
    
    # Run migration
    success = migrator.migrate(
        tenant=args.tenant,
        start_year=args.start_year,
        end_year=args.end_year
    )
    
    # Exit with appropriate code
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
