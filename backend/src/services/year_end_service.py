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
"""

from database import DatabaseManager
from datetime import datetime
from services.year_end_config import YearEndConfigService


class YearEndClosureService:
    """Service for closing fiscal years"""
    
    def __init__(self, test_mode=False):
        """
        Initialize year-end closure service
        
        Args:
            test_mode: Use test database if True
        """
        self.db = DatabaseManager(test_mode=test_mode)
        self.config_service = YearEndConfigService(test_mode=test_mode)
    
    def get_available_years(self, administration):
        """
        Get years that have transactions and are not yet closed.
        
        Args:
            administration: Tenant identifier
            
        Returns:
            list: Years available for closure
        """
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
    
    def get_closed_years(self, administration):
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
    
    def get_year_status(self, administration, year):
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
    
    def validate_year_closure(self, administration, year):
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
    
    def _is_year_closed(self, administration, year):
        """Check if year is already closed"""
        query = """
            SELECT COUNT(*) as count
            FROM year_closure_status
            WHERE administration = %s
            AND year = %s
        """
        
        result = self.db.execute_query(query, [administration, year])
        return result[0]['count'] > 0 if result else False
    
    def _get_first_year(self, administration):
        """Get first year with transactions"""
        query = """
            SELECT MIN(YEAR(TransactionDate)) as first_year
            FROM mutaties
            WHERE administration = %s
            AND TransactionDate IS NOT NULL
        """
        
        result = self.db.execute_query(query, [administration])
        return result[0]['first_year'] if result and result[0]['first_year'] else None
    
    def _calculate_net_pl_result(self, administration, year):
        """
        Calculate net P&L result for the year.
        
        Sums all P&L accounts (VW='Y') for the year.
        Positive = profit, Negative = loss
        
        Uses vw_mutaties view which has Amount column with correct sign.
        
        Args:
            administration: Tenant identifier
            year: Year to calculate
            
        Returns:
            float: Net P&L result
        """
        query = """
            SELECT 
                COALESCE(SUM(Amount), 0) as net_result
            FROM vw_mutaties
            WHERE administration = %s
            AND YEAR(TransactionDate) = %s
            AND VW = 'Y'
        """
        
        result = self.db.execute_query(query, [administration, year])
        return float(result[0]['net_result']) if result else 0.0
    
    def _count_balance_sheet_accounts(self, administration, year):
        """
        Count balance sheet accounts with non-zero balances.
        
        Uses ONLY current year transactions (matches _get_ending_balances logic).
        
        Uses vw_mutaties view for accurate balance calculation.
        
        Args:
            administration: Tenant identifier
            year: Year to check
            
        Returns:
            int: Count of accounts with balances
        """
        query = """
            SELECT COUNT(DISTINCT Reknum) as count
            FROM (
                SELECT 
                    Reknum,
                    SUM(Amount) as balance
                FROM vw_mutaties
                WHERE administration = %s
                AND VW = 'N'
                AND YEAR(TransactionDate) = %s
                GROUP BY Reknum
                HAVING ABS(SUM(Amount)) > 0.01
            ) as accounts_with_balance
        """
        
        result = self.db.execute_query(query, [administration, year])
        return int(result[0]['count']) if result else 0

    def _create_closure_transaction(self, administration, year, cursor):
        """
        Create year-end closure transaction (P&L to equity).
        
        This transaction closes all P&L accounts by recording the net result
        in the equity account. The P&L closing account is used as the
        offsetting account.
        
        NOTE: In vw_mutaties, Amount is negative for revenue and positive for expenses.
        Therefore: negative net_result = profit, positive net_result = loss
        
        For profit (negative net result):
            Debit: P&L Closing Account
            Credit: Equity Result Account
        
        For loss (positive net result):
            Debit: Equity Result Account
            Credit: P&L Closing Account
        
        Args:
            administration: Tenant identifier
            year: Year being closed
            cursor: Database cursor (for transaction control)
            
        Returns:
            str: TransactionNumber of created transaction, or None if net result is zero
        """
        # Get required accounts from configuration
        equity_account_info = self.config_service.get_account_by_purpose(
            administration, 'equity_result'
        )
        pl_closing_account_info = self.config_service.get_account_by_purpose(
            administration, 'pl_closing'
        )
        
        if not equity_account_info or not pl_closing_account_info:
            raise ValueError("Required accounts not configured for year-end closure")
        
        # Extract account codes
        equity_account = equity_account_info['Account']
        pl_closing_account = pl_closing_account_info['Account']
        
        # Calculate net P&L result
        net_result = self._calculate_net_pl_result(administration, year)
        
        # No transaction needed if result is zero
        if net_result == 0:
            return None
        
        # Determine debit and credit based on profit/loss
        # TransactionAmount is always positive
        # NOTE: In vw_mutaties, Amount is negative for revenue (profit) and positive for expenses (loss)
        if net_result < 0:
            # Profit (negative net_result means revenue > expenses): Debit P&L closing, Credit equity
            debet = pl_closing_account
            credit = equity_account
            amount = abs(net_result)
        else:
            # Loss (positive net_result means expenses > revenue): Debit equity, Credit P&L closing
            debet = equity_account
            credit = pl_closing_account
            amount = net_result
        
        # Create transaction
        transaction_number = f"YearClose {year}"
        transaction_date = f"{year}-12-31"
        description = f"Year-end closure {year} - {administration}"
        
        insert_query = """
            INSERT INTO mutaties (
                TransactionNumber,
                TransactionDate,
                TransactionDescription,
                TransactionAmount,
                Debet,
                Credit,
                administration
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        cursor.execute(insert_query, [
            transaction_number,
            transaction_date,
            description,
            amount,
            debet,
            credit,
            administration
        ])
        
        return transaction_number

    def _create_opening_balances(self, administration, year, cursor):
        """
        Create opening balance transactions for the new year.
        
        CORRECTED APPROACH:
        - Use equity account as offset for ALL balance sheet accounts
        - Equity is calculated as negative sum of all other balance sheet accounts
        - No separate entry for equity account (it's the balancing account)
        
        For positive balances (assets):
            Debit: Account
            Credit: Equity Account
        
        For negative balances (liabilities):
            Debit: Equity Account
            Credit: Account
        
        Args:
            administration: Tenant identifier
            year: Year for opening balances (e.g., 2025 for balances from 2024)
            cursor: Database cursor (for transaction control)
            
        Returns:
            str: TransactionNumber of created transactions, or None if no balances
        """
        # Get equity account from configuration
        equity_account_info = self.config_service.get_account_by_purpose(
            administration, 'equity_result'
        )
        
        if not equity_account_info:
            raise ValueError("Equity result account not configured")
        
        equity_account = equity_account_info['Account']
        
        # Get ending balances from previous year
        ending_balances = self._get_ending_balances(administration, year - 1, cursor)
        
        if not ending_balances:
            return None  # No balances to carry forward
        
        # Filter out equity account - it will be calculated as the balancing account
        non_equity_balances = [b for b in ending_balances if b['account'] != equity_account]
        
        if not non_equity_balances:
            return None  # No non-equity balances to carry forward
        
        # Create transaction records
        transaction_number = f"OpeningBalance {year}"
        transaction_date = f"{year}-01-01"
        
        insert_query = """
            INSERT INTO mutaties (
                TransactionNumber,
                TransactionDate,
                TransactionDescription,
                TransactionAmount,
                Debet,
                Credit,
                administration
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        records_created = 0
        
        # Create opening balance entries for all non-equity accounts
        # Equity account is used as the offsetting account for all entries
        for balance_info in non_equity_balances:
            account = balance_info['account']
            account_name = balance_info['account_name']
            balance = balance_info['balance']
            
            # Skip zero balances (shouldn't happen due to query filter)
            if balance == 0:
                continue
            
            # Create description with account name
            description = f"Opening balance {year} for {account_name}"
            
            # Determine debit and credit based on balance sign
            # TransactionAmount is always positive
            if balance > 0:
                # Positive balance (asset): Debit account, Credit equity
                debet = account
                credit = equity_account
                amount = balance
            else:
                # Negative balance (liability): Debit equity, Credit account
                debet = equity_account
                credit = account
                amount = abs(balance)
            
            cursor.execute(insert_query, [
                transaction_number,
                transaction_date,
                description,
                amount,
                debet,
                credit,
                administration
            ])
            
            records_created += 1
        
        return transaction_number if records_created > 0 else None
    
    def _get_ending_balances(self, administration, year, cursor):
        """
        Get ending balances for all balance sheet accounts.
        
        LOGIC:
        - If OpeningBalance {year} exists: Use YEAR(TransactionDate) = year (current year only)
        - If OpeningBalance {year} does NOT exist: Use TransactionDate <= year-12-31 (cumulative)
        
        This handles both first closure (no opening balance) and re-closure scenarios.
        
        Uses vw_mutaties view which has Amount column with correct sign.
        
        Args:
            administration: Tenant identifier
            year: Year to get ending balances for
            cursor: Database cursor
            
        Returns:
            list: List of dicts with 'account', 'account_name', 'balance'
        """
        # Check if OpeningBalance for this year already exists
        check_query = """
            SELECT COUNT(*) as count
            FROM mutaties
            WHERE administration = %s
            AND TransactionNumber = %s
        """
        cursor.execute(check_query, [administration, f"OpeningBalance {year}"])
        result = cursor.fetchone()
        has_opening_balance = (result['count'] if isinstance(result, dict) else result[0]) > 0
        
        # Choose query based on whether opening balance exists
        if has_opening_balance:
            # Re-closure: Use current year only (includes OpeningBalance + year transactions)
            query = """
                SELECT 
                    Reknum as account,
                    AccountName as account_name,
                    SUM(Amount) as balance
                FROM vw_mutaties
                WHERE administration = %s
                AND VW = 'N'
                AND YEAR(TransactionDate) = %s
                GROUP BY Reknum, AccountName
                HAVING ABS(SUM(Amount)) > 0.01
                ORDER BY Reknum
            """
            cursor.execute(query, [administration, year])
        else:
            # First closure: Use cumulative (all history through year-end)
            query = """
                SELECT 
                    Reknum as account,
                    AccountName as account_name,
                    SUM(Amount) as balance
                FROM vw_mutaties
                WHERE administration = %s
                AND VW = 'N'
                AND TransactionDate <= %s
                GROUP BY Reknum, AccountName
                HAVING ABS(SUM(Amount)) > 0.01
                ORDER BY Reknum
            """
            cursor.execute(query, [administration, f"{year}-12-31"])
        
        balances = []
        for row in cursor.fetchall():
            # Handle both dict and tuple cursor results
            if isinstance(row, dict):
                balances.append({
                    'account': row['account'],
                    'account_name': row['account_name'],
                    'balance': float(row['balance'])
                })
            else:
                # Tuple format: (account, account_name, balance)
                balances.append({
                    'account': row[0],
                    'account_name': row[1],
                    'balance': float(row[2])
                })
        
        return balances

    def close_year(self, administration, year, user_email, notes=''):
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
            closure_transaction_number = self._create_closure_transaction(
                administration, year, cursor
            )
            
            # Step 3: Create opening balance transactions for next year
            opening_transaction_number = self._create_opening_balances(
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
    
    def _record_closure_status(self, administration, year, user_email,
                               closure_transaction_number, opening_transaction_number,
                               notes, cursor):
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
    
    def reopen_year(self, administration, year, user_email):
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
                delete_opening = """
                    DELETE FROM mutaties
                    WHERE administration = %s
                    AND TransactionNumber = %s
                """
                cursor.execute(delete_opening, [administration, opening_txn])
            
            # Step 3: Delete year-end closure transaction
            if closure_txn:
                delete_closure = """
                    DELETE FROM mutaties
                    WHERE administration = %s
                    AND TransactionNumber = %s
                """
                cursor.execute(delete_closure, [administration, closure_txn])
            
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

