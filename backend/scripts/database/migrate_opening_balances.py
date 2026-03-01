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
            
            # Process each year
            for year in years:
                success = self._migrate_year(tenant, year)
                
                if not success:
                    self.logger.error(f"  Failed to migrate year {year}")
                    return False
                
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
    
    def _migrate_year(self, tenant: str, year: int) -> bool:
        """
        Migrate a single year for a tenant.
        
        Args:
            tenant: Tenant name
            year: Year to migrate
            
        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"    Processing year {year}...")
        
        # Check if already migrated
        if self._is_already_migrated(tenant, year):
            self.logger.info(f"    ✓ Year {year} already migrated")
            return True
        
        # Calculate ending balances from previous year
        balances = self._calculate_ending_balances(tenant, year - 1)
        
        if not balances:
            self.logger.info(f"    No balances to migrate for {year}")
            return True
        
        self.logger.info(f"    Found {len(balances)} accounts with balances")
        
        # Create opening balance transactions
        transaction_ids = self._create_opening_balances(tenant, year, balances)
        
        if not transaction_ids:
            self.logger.error(f"    Failed to create opening balances")
            return False
        
        self.logger.info(f"    Created {len(transaction_ids)} opening balance transactions")
        self.stats['transactions_created'] += len(transaction_ids)
        
        # Validate
        if not self._validate_year(tenant, year):
            self.logger.error(f"    Validation failed for {year}")
            self.stats['validation_errors'] += 1
            return False
        
        self.logger.info(f"    ✓ Year {year} completed and validated")
        return True
    
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
    
    def _calculate_ending_balances(
        self,
        tenant: str,
        year: int
    ) -> List[Dict]:
        """
        Calculate ending balances for balance sheet accounts.
        
        Args:
            tenant: Tenant name
            year: Year to calculate balances for
            
        Returns:
            List of dicts with account and balance
        """
        # TODO: Implement in next task
        self.logger.debug(f"      Calculating ending balances for {year}")
        return []
    
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
        # TODO: Implement in next task
        self.logger.debug(f"      Creating opening balances for {year}")
        return []
    
    def _validate_year(self, tenant: str, year: int) -> bool:
        """
        Validate that migration was successful.
        
        Args:
            tenant: Tenant name
            year: Year to validate
            
        Returns:
            True if validation passed, False otherwise
        """
        # TODO: Implement in next task
        self.logger.debug(f"      Validating {year}")
        return True
    
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
