"""
Year-End Journal Entry Helper

Handles the creation and deletion of journal entries for year-end closure:
- Closure transactions (P&L to equity)
- Opening balance transactions for the new year
- VAT netting logic for balance sheet carry-forward

Extracted from year_end_service.py for clarity and maintainability.
"""

from typing import Any, Dict, List, Optional

from services.year_end_config import YearEndConfigService


class YearEndJournalEntryHelper:
    """Helper for creating and managing year-end journal entries."""

    def __init__(self, config_service: YearEndConfigService) -> None:
        """
        Initialize with a config service for account lookups.

        Args:
            config_service: YearEndConfigService instance
        """
        self.config_service = config_service

    def create_closure_transaction(
        self,
        administration: str,
        year: int,
        net_result: float,
        cursor,
    ) -> Optional[str]:
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
            net_result: Pre-calculated net P&L result
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
        reference_number = "Year Closure"

        insert_query = """
            INSERT INTO mutaties (
                TransactionNumber,
                TransactionDate,
                TransactionDescription,
                TransactionAmount,
                Debet,
                Credit,
                ReferenceNumber,
                administration
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(insert_query, [
            transaction_number,
            transaction_date,
            description,
            amount,
            debet,
            credit,
            reference_number,
            administration
        ])

        return transaction_number

    def create_opening_balances(
        self,
        administration: str,
        year: int,
        cursor,
    ) -> Optional[str]:
        """
        Create opening balance transactions for the new year.

        CORRECTED APPROACH:
        - Use equity account as offset for ALL balance sheet accounts
        - Equity is calculated as negative sum of all other balance sheet accounts
        - No separate entry for equity account (it's the balancing account)

        SPECIAL HANDLING FOR VAT ACCOUNTS:
        - Accounts with vat_netting=true parameter are netted together
        - Net balance = (Received VAT accounts) - (Paid VAT accounts)
        - Net balance goes to the vat_primary account only
        - Other VAT accounts are not carried forward individually

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

        # Separate VAT accounts from regular accounts
        vat_accounts = []
        regular_accounts = []

        for balance_info in non_equity_balances:
            account = balance_info['account']

            # Check if account has VAT netting flag
            if self._is_vat_netting_account(administration, account, cursor):
                vat_accounts.append(balance_info)
            else:
                regular_accounts.append(balance_info)

        # Create transaction records
        transaction_number = f"OpeningBalance {year}"
        transaction_date = f"{year}-01-01"
        reference_number = "Opening Balance"

        insert_query = """
            INSERT INTO mutaties (
                TransactionNumber,
                TransactionDate,
                TransactionDescription,
                TransactionAmount,
                Debet,
                Credit,
                ReferenceNumber,
                administration
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        records_created = 0

        # Handle VAT accounts with netting
        if vat_accounts:
            vat_primary_account = self._get_vat_primary_account(administration, cursor)

            if vat_primary_account:
                # Calculate net VAT balance
                net_vat_balance = sum(b['balance'] for b in vat_accounts)

                # Create single entry for netted VAT if non-zero
                if abs(net_vat_balance) > 0.01:
                    description = f"Opening balance {year} for BTW (netted)"

                    if net_vat_balance > 0:
                        # Net debit (more paid than received - VAT receivable)
                        debet = vat_primary_account
                        credit = equity_account
                        amount = net_vat_balance
                    else:
                        # Net credit (more received than paid - VAT payable)
                        debet = equity_account
                        credit = vat_primary_account
                        amount = abs(net_vat_balance)

                    cursor.execute(insert_query, [
                        transaction_number,
                        transaction_date,
                        description,
                        amount,
                        debet,
                        credit,
                        reference_number,
                        administration
                    ])

                    records_created += 1

        # Create opening balance entries for regular (non-VAT) accounts
        # Equity account is used as the offsetting account for all entries
        for balance_info in regular_accounts:
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
                reference_number,
                administration
            ])

            records_created += 1

        return transaction_number if records_created > 0 else None

    def _get_ending_balances(
        self, administration: str, year: int, cursor
    ) -> List[Dict[str, Any]]:
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
            # Use sargable date range instead of YEAR() for index usage
            from utils.query_helpers import year_to_date_range
            start_date, end_date = year_to_date_range(year)
            query = """
                SELECT
                    Reknum as account,
                    AccountName as account_name,
                    SUM(Amount) as balance
                FROM vw_mutaties
                WHERE administration = %s
                AND VW = 'N'
                AND TransactionDate >= %s AND TransactionDate < %s
                GROUP BY Reknum, AccountName
                HAVING ABS(SUM(Amount)) > 0.01
                ORDER BY Reknum
            """
            cursor.execute(query, [administration, start_date, end_date])
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

    def _is_vat_netting_account(
        self, administration: str, account: str, cursor
    ) -> bool:
        """
        Check if account has VAT netting flag in parameters.

        Args:
            administration: Tenant identifier
            account: Account code to check
            cursor: Database cursor

        Returns:
            bool: True if account has vat_netting=true parameter
        """
        query = """
            SELECT JSON_EXTRACT(parameters, '$.vat_netting') as vat_netting
            FROM rekeningschema
            WHERE administration = %s
            AND Account = %s
        """

        cursor.execute(query, [administration, account])
        result = cursor.fetchone()

        if result:
            # Handle both dict and tuple cursor results
            vat_netting = result['vat_netting'] if isinstance(result, dict) else result[0]

            # Handle both boolean true and string "true"
            if vat_netting is not None:
                if isinstance(vat_netting, bool):
                    return vat_netting
                elif isinstance(vat_netting, (int, float)):
                    return bool(vat_netting)
                else:
                    # String value
                    return str(vat_netting).strip('"').lower() == 'true'

        return False

    def _get_vat_primary_account(
        self, administration: str, cursor
    ) -> Optional[str]:
        """
        Get the primary VAT account that receives the net balance.

        Looks for an account with vat_netting=true that has a vat_primary parameter.

        Args:
            administration: Tenant identifier
            cursor: Database cursor

        Returns:
            str: Account code of primary VAT account, or None if not found
        """
        query = """
            SELECT
                Account,
                JSON_EXTRACT(parameters, '$.vat_primary') as vat_primary
            FROM rekeningschema
            WHERE administration = %s
            AND (
                JSON_EXTRACT(parameters, '$.vat_netting') = true
                OR JSON_EXTRACT(parameters, '$.vat_netting') = 'true'
            )
            LIMIT 1
        """

        cursor.execute(query, [administration])
        result = cursor.fetchone()

        if result:
            # Handle both dict and tuple cursor results
            if isinstance(result, dict):
                vat_primary = result.get('vat_primary')
                account = result.get('Account')
            else:
                account = result[0]
                vat_primary = result[1]

            # If vat_primary is specified, use it; otherwise use the account itself
            if vat_primary:
                vat_primary_str = str(vat_primary).strip('"')
                return vat_primary_str if vat_primary_str else account
            else:
                return account

        return None

    def delete_transactions(
        self, administration: str, transaction_number: str, cursor
    ) -> None:
        """
        Delete transactions by TransactionNumber.

        Used during year reopen to remove closure and opening balance entries.

        Args:
            administration: Tenant identifier
            transaction_number: TransactionNumber to delete
            cursor: Database cursor
        """
        delete_query = """
            DELETE FROM mutaties
            WHERE administration = %s
            AND TransactionNumber = %s
        """
        cursor.execute(delete_query, [administration, transaction_number])
