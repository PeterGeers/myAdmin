"""
Year-End Closure Service

Handles the year-end closure process:
1. Validates year is ready to be closed
2. Creates year-end closure transaction (P&L to equity)
3. Creates opening balance transactions for next year
4. Records closure status

Key Concepts:
- VW='Y' accounts (P&L) are closed to equity at year-end
- VW='N' accounts (Balance Sheet) carry forward to next year
- Net P&L result is recorded in equity_result account
- Opening balances use equity_result account for balancing

Journal entry creation is delegated to YearEndJournalEntryHelper.
"""

from typing import Any, Dict, Optional

from database import DatabaseManager
from datetime import datetime
from services.year_end_config import YearEndConfigService
from services.year_end_journal_entries import YearEndJournalEntryHelper


class YearEndClosureService:
    """Service for closing fiscal years"""

    def __init__(self, test_mode: bool = False) -> None:
        """
        Initialize year-end closure service

        Args:
            test_mode: Use test database if True
        """
        self.db = DatabaseManager(test_mode=test_mode)
        self.config_service = YearEndConfigService(test_mode=test_mode)
        self.journal_helper = YearEndJournalEntryHelper(self.config_service)

    def get_available_years(self, administration: str) -> Dict[str, Any]:
        """
        Get years that have transactions and are not yet closed.

        Args:
            administration: Tenant identifier

        Returns:
            list: Years available for closure
        """
        # Use YEAR() on base mutaties table — acceptable since administration
        # index filters rows first. NOT IN subquery uses year_closure_status
        # which is a small table.
        query = """
            SELECT DISTINCT YEAR(TransactionDate) as year
            FROM mutaties
            WHERE administration = %s
            AND TransactionDate IS NOT NULL
            AND YEAR(TransactionDate) NOT IN (
                SELECT year
                FROM year_closure_status
                WHERE administration = %s
                AND year IS NOT NULL
            )
            ORDER BY year DESC
        """

        results = self.db.execute_query(query, [administration, administration])
        return [row['year'] for row in results] if results else []

    def get_closed_years(self, administration: str) -> Dict[str, Any]:
        """
        Get list of closed years with closure information.

        Args:
            administration: Tenant identifier

        Returns:
            list: Closed years with details
        """
        query = """
            SELECT
                year,
                closed_date,
                closed_by,
                closure_transaction_number,
                opening_balance_transaction_number,
                notes
            FROM year_closure_status
            WHERE administration = %s
            ORDER BY year DESC
        """

        return self.db.execute_query(query, [administration])

    def get_year_status(self, administration: str, year: int) -> Dict[str, Any]:
        """
        Get closure status for a specific year.

        Args:
            administration: Tenant identifier
            year: Year to check

        Returns:
            dict: Status information or None if not closed
        """
        query = """
            SELECT
                year,
                closed_date,
                closed_by,
                closure_transaction_number,
                opening_balance_transaction_number,
                notes
            FROM year_closure_status
            WHERE administration = %s
            AND year = %s
        """

        result = self.db.execute_query(query, [administration, year])
        return result[0] if result else None

    def validate_year_closure(self, administration: str, year: int) -> Dict[str, Any]:
        """
        Validate if year is ready to be closed.

        Checks:
        - Year not already closed
        - Previous year is closed (except first year)
        - Required accounts configured
        - Calculates net P&L result
        - Counts balance sheet accounts

        Args:
            administration: Tenant identifier
            year: Year to validate

        Returns:
            dict: Validation result with can_close, errors, warnings, info
        """
        validation = {
            'can_close': True,
            'errors': [],
            'warnings': [],
            'info': {}
        }

        # Check if already closed
        if self._is_year_closed(administration, year):
            validation['can_close'] = False
            validation['errors'].append(f"Year {year} is already closed")
            return validation

        # Check if previous year is closed (except for first year)
        first_year = self._get_first_year(administration)
        if first_year and year > first_year:
            if not self._is_year_closed(administration, year - 1):
                validation['can_close'] = False
                validation['errors'].append(
                    f"Previous year {year - 1} must be closed first"
                )

        # Check if required accounts are configured
        config_validation = self.config_service.validate_configuration(administration)
        if not config_validation['valid']:
            validation['can_close'] = False
            validation['errors'].extend(config_validation['errors'])

        # Calculate net P&L result
        net_result = self._calculate_net_pl_result(administration, year)
        validation['info']['net_result'] = net_result
        validation['info']['net_result_formatted'] = f"€{net_result:,.2f}"

        # Count balance sheet accounts with non-zero balances
        balance_count = self._count_balance_sheet_accounts(administration, year)
        validation['info']['balance_sheet_accounts'] = balance_count

        # Optional warnings (don't prevent closure)
        if net_result == 0:
            validation['warnings'].append("Net P&L result is zero")

        if balance_count == 0:
            validation['warnings'].append("No balance sheet accounts with balances")

        return validation

    def _is_year_closed(self, administration: str, year: int) -> bool:
        """Check if year is already closed"""
        query = """
            SELECT COUNT(*) as count
            FROM year_closure_status
            WHERE administration = %s
            AND year = %s
        """

        result = self.db.execute_query(query, [administration, year])
        return result[0]['count'] > 0 if result else False

    def _get_first_year(self, administration: str) -> Optional[int]:
        """Get first year with transactions"""
        query = """
            SELECT MIN(TransactionDate) as first_date
            FROM mutaties
            WHERE administration = %s
            AND TransactionDate IS NOT NULL
        """

        result = self.db.execute_query(query, [administration])
        if result and result[0]['first_date']:
            # Extract year from the date in Python
            first_date = result[0]['first_date']
            if hasattr(first_date, 'year'):
                return first_date.year
            # Handle string dates
            return int(str(first_date)[:4])
        return None

    def _calculate_net_pl_result(self, administration: str, year: int) -> float:
        """
        Calculate net P&L result for the year.

        Sums all P&L accounts (VW='Y') for the year.
        Positive = profit, Negative = loss

        Uses vw_mutaties view which has Amount column with correct sign.
        Uses sargable date range instead of YEAR() for index usage.

        Args:
            administration: Tenant identifier
            year: Year to calculate

        Returns:
            float: Net P&L result
        """
        from utils.query_helpers import year_to_date_range
        start_date, end_date = year_to_date_range(year)

        query = """
            SELECT
                COALESCE(SUM(Amount), 0) as net_result
            FROM vw_mutaties
            WHERE administration = %s
            AND TransactionDate >= %s AND TransactionDate < %s
            AND VW = 'Y'
        """

        result = self.db.execute_query(query, [administration, start_date, end_date])
        return float(result[0]['net_result']) if result else 0.0

    def _count_balance_sheet_accounts(self, administration: str, year: int) -> int:
        """
        Count balance sheet accounts with non-zero balances.

        Uses ONLY current year transactions (matches _get_ending_balances logic).

        Uses vw_mutaties view for accurate balance calculation.
        Uses sargable date range instead of YEAR() for index usage.

        Args:
            administration: Tenant identifier
            year: Year to check

        Returns:
            int: Count of accounts with balances
        """
        from utils.query_helpers import year_to_date_range
        start_date, end_date = year_to_date_range(year)

        query = """
            SELECT COUNT(DISTINCT Reknum) as count
            FROM (
                SELECT
                    Reknum,
                    SUM(Amount) as balance
                FROM vw_mutaties
                WHERE administration = %s
                AND VW = 'N'
                AND TransactionDate >= %s AND TransactionDate < %s
                GROUP BY Reknum
                HAVING ABS(SUM(Amount)) > 0.01
            ) as accounts_with_balance
        """

        result = self.db.execute_query(query, [administration, start_date, end_date])
        return int(result[0]['count']) if result else 0

    def close_year(self, administration: str, year: int, user_email: str, notes: str = '') -> Dict[str, Any]:
        """
        Close a fiscal year.

        This is the main orchestration method that:
        1. Validates the year can be closed
        2. Creates year-end closure transaction (P&L to equity)
        3. Creates opening balance transactions for next year
        4. Records closure status in database

        All operations are performed within a database transaction,
        so if any step fails, all changes are rolled back.

        Args:
            administration: Tenant identifier
            year: Year to close
            user_email: Email of user performing closure
            notes: Optional notes about the closure

        Returns:
            dict: Success result with transaction details

        Raises:
            Exception: If validation fails or any step encounters an error
        """
        # Step 1: Validate year can be closed
        validation = self.validate_year_closure(administration, year)
        if not validation['can_close']:
            error_msg = '; '.join(validation['errors'])
            raise Exception(f"Cannot close year {year}: {error_msg}")

        # Get database connection
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Step 2: Create year-end closure transaction
            net_result = self._calculate_net_pl_result(administration, year)
            closure_transaction_number = self.journal_helper.create_closure_transaction(
                administration, year, net_result, cursor
            )

            # Step 3: Create opening balance transactions for next year
            opening_transaction_number = self.journal_helper.create_opening_balances(
                administration, year + 1, cursor
            )

            # Step 4: Record closure status
            self._record_closure_status(
                administration,
                year,
                user_email,
                closure_transaction_number,
                opening_transaction_number,
                notes,
                cursor
            )

            # Commit all changes
            conn.commit()

            # Invalidate cache so reports pick up new transactions
            from mutaties_cache import invalidate_cache
            invalidate_cache()

            # Return success result
            return {
                'success': True,
                'year': year,
                'closure_transaction_number': closure_transaction_number,
                'opening_transaction_number': opening_transaction_number,
                'net_result': validation['info']['net_result'],
                'net_result_formatted': validation['info']['net_result_formatted'],
                'balance_sheet_accounts': validation['info']['balance_sheet_accounts'],
                'message': f'Year {year} closed successfully'
            }

        except Exception as e:
            # Rollback on any error
            conn.rollback()
            raise Exception(f"Failed to close year {year}: {str(e)}")

        finally:
            cursor.close()
            conn.close()

    def _record_closure_status(self, administration: str, year: int, user_email: str,
                               closure_transaction_number: str, opening_transaction_number: str,
                               notes: str, cursor) -> None:
        """
        Record year closure in status table.

        Creates a permanent record of the year closure including:
        - When it was closed
        - Who closed it
        - Transaction numbers for audit trail
        - Optional notes

        Args:
            administration: Tenant identifier
            year: Year that was closed
            user_email: Email of user who performed closure
            closure_transaction_number: TransactionNumber of closure transaction
            opening_transaction_number: TransactionNumber of opening balances
            notes: Optional notes about the closure
            cursor: Database cursor
        """
        insert_query = """
            INSERT INTO year_closure_status (
                administration,
                year,
                closed_date,
                closed_by,
                closure_transaction_number,
                opening_balance_transaction_number,
                notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(insert_query, [
            administration,
            year,
            datetime.now(),
            user_email,
            closure_transaction_number,
            opening_transaction_number,
            notes
        ])

    def reopen_year(self, administration: str, year: int, user_email: str) -> Dict[str, Any]:
        """
        Reopen a closed fiscal year.

        This reverses the year closure by:
        1. Validating the year can be reopened
        2. Deleting opening balance transactions for next year
        3. Deleting year-end closure transaction
        4. Removing closure status record

        All operations are performed within a database transaction,
        so if any step fails, all changes are rolled back.

        Args:
            administration: Tenant identifier
            year: Year to reopen
            user_email: Email of user performing reopen

        Returns:
            dict: Success result

        Raises:
            Exception: If validation fails or any step encounters an error
        """
        # Step 1: Validate year can be reopened
        if not self._is_year_closed(administration, year):
            raise Exception(f"Year {year} is not closed")

        # Check if next year is closed (can't reopen if next year is closed)
        if self._is_year_closed(administration, year + 1):
            raise Exception(f"Cannot reopen year {year} because year {year + 1} is already closed")

        # Get closure information
        closure_info = self.get_year_status(administration, year)
        if not closure_info:
            raise Exception(f"No closure information found for year {year}")

        closure_txn = closure_info.get('closure_transaction_number')
        opening_txn = closure_info.get('opening_balance_transaction_number')

        # Get database connection
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Step 2: Delete opening balance transactions for next year
            if opening_txn:
                self.journal_helper.delete_transactions(administration, opening_txn, cursor)

            # Step 3: Delete year-end closure transaction
            if closure_txn:
                self.journal_helper.delete_transactions(administration, closure_txn, cursor)

            # Step 4: Remove closure status record
            delete_status = """
                DELETE FROM year_closure_status
                WHERE administration = %s
                AND year = %s
            """
            cursor.execute(delete_status, [administration, year])

            # Commit all changes
            conn.commit()

            # Invalidate cache so reports pick up changes
            from mutaties_cache import invalidate_cache
            invalidate_cache()

            # Return success result
            return {
                'success': True,
                'year': year,
                'message': f'Year {year} reopened successfully'
            }

        except Exception as e:
            # Rollback on any error
            conn.rollback()
            raise Exception(f"Failed to reopen year {year}: {str(e)}")

        finally:
            cursor.close()
            conn.close()
