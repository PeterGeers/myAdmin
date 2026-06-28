"""
Banking Account Checks

Handles balance verification and sequence gap detection for bank accounts:
- Balance comparison between calculated and last transaction
- Sequence number gap detection for Rabobank (numeric Ref2)
- Running balance verification for Revolut (descriptive Ref2)

Extracted from banking_processor.py for clarity and maintainability.
"""

import logging
from datetime import datetime
from database import DatabaseManager


def _get_opening_balance_date(db, administration):
    """Get the opening balance date based on the last closed year.

    Queries year_closure_status for the most recent closed year and returns
    January 1 of the following year as the opening balance date.

    Args:
        db: DatabaseManager instance
        administration: tenant identifier

    Returns:
        str or None: 'YYYY-01-01' if closure exists, None otherwise
    """
    try:
        query = """
            SELECT MAX(year) as last_closed_year
            FROM year_closure_status
            WHERE administration = %s
        """
        rows = db.execute_query(query, [administration])
        if rows and rows[0]['last_closed_year']:
            return f"{rows[0]['last_closed_year'] + 1}-01-01"
        return None
    except Exception as e:
        logging.warning(f"Could not fetch opening balance date for {administration}: {e}")
        return None


class BankingChecks:
    """Banking account balance and sequence verification."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def check_banking_accounts(self, end_date=None, administration=None):
        """
        Check banking account balances based on internal calculation vs last transaction

        Args:
            end_date: Optional end date for balance calculation
            administration: Tenant to filter accounts by (required for multi-tenant)
        """
        # Get opening balance date from year closure status
        opening_balance_date = _get_opening_balance_date(self.db, administration)

        # Get bank accounts using canonical $.bank_account flag source
        accounts = self.db.get_bank_account_lookups(administration=administration)

        if not accounts:
            return []

        # Get account codes for this tenant
        account_codes = list(set([acc['Account'] for acc in accounts]))

        # Build WHERE clause for account filtering
        account_placeholders = ','.join(['%s'] * len(account_codes))

        # Get calculated balances from vw_mutaties with account names
        if end_date:
            query = f"""
                SELECT Reknum, Administration as administration,
                       ROUND(SUM(Amount), 2) as calculated_balance,
                       MAX(AccountName) as account_name
                FROM vw_mutaties
                WHERE Administration = %s
                AND Reknum IN ({account_placeholders})
                AND TransactionDate <= %s
                {' AND TransactionDate >= %s' if opening_balance_date else ''}
                GROUP BY Reknum, Administration
            """
            params = [administration] + account_codes + [end_date]
            if opening_balance_date:
                params.append(opening_balance_date)
        else:
            query = f"""
                SELECT Reknum, Administration as administration,
                       ROUND(SUM(Amount), 2) as calculated_balance,
                       MAX(AccountName) as account_name
                FROM vw_mutaties
                WHERE Administration = %s
                AND Reknum IN ({account_placeholders})
                {' AND TransactionDate >= %s' if opening_balance_date else ''}
                GROUP BY Reknum, Administration
            """
            params = [administration] + account_codes
            if opening_balance_date:
                params.append(opening_balance_date)

        balances = self.db.execute_query(query, params)

        # For each balance, find the last transaction description from mutaties table
        for balance in balances:
            if end_date:
                last_tx_query = """
                    SELECT TransactionDate, TransactionDescription, TransactionAmount,
                           Debet, Credit, Ref2, Ref3, Ref4
                    FROM mutaties
                    WHERE administration = %s
                    AND (Debet = %s OR Credit = %s)
                    AND TransactionDate <= %s
                    {opening_date_filter}
                    AND TransactionDate = (
                        SELECT MAX(TransactionDate)
                        FROM mutaties
                        WHERE administration = %s
                        AND (Debet = %s OR Credit = %s)
                        AND TransactionDate <= %s
                        {opening_date_filter}
                    )
                    ORDER BY Ref2 DESC
                """.format(opening_date_filter='AND TransactionDate >= %s' if opening_balance_date else '')
                last_tx_params = [
                    balance['administration'], balance['Reknum'], balance['Reknum'], end_date
                ]
                if opening_balance_date:
                    last_tx_params.append(opening_balance_date)
                last_tx_params.extend([
                    balance['administration'], balance['Reknum'], balance['Reknum'], end_date
                ])
                if opening_balance_date:
                    last_tx_params.append(opening_balance_date)
            else:
                last_tx_query = """
                    SELECT TransactionDate, TransactionDescription, TransactionAmount,
                           Debet, Credit, Ref2, Ref3, Ref4
                    FROM mutaties
                    WHERE administration = %s
                    AND (Debet = %s OR Credit = %s)
                    {opening_date_filter}
                    AND TransactionDate = (
                        SELECT MAX(TransactionDate)
                        FROM mutaties
                        WHERE administration = %s
                        AND (Debet = %s OR Credit = %s)
                        {opening_date_filter}
                    )
                    ORDER BY Ref2 DESC
                """.format(opening_date_filter='AND TransactionDate >= %s' if opening_balance_date else '')
                last_tx_params = [
                    balance['administration'], balance['Reknum'], balance['Reknum']
                ]
                if opening_balance_date:
                    last_tx_params.append(opening_balance_date)
                last_tx_params.extend([
                    balance['administration'], balance['Reknum'], balance['Reknum']
                ])
                if opening_balance_date:
                    last_tx_params.append(opening_balance_date)

            last_transactions = self.db.execute_query(last_tx_query, last_tx_params)

            if last_transactions:
                balance['last_transaction_date'] = last_transactions[0]['TransactionDate']
                balance['last_transaction_description'] = last_transactions[0]['TransactionDescription']
                balance['last_transaction_amount'] = last_transactions[0]['TransactionAmount']
                # Ensure Ref3 and Ref4 are included in each transaction
                for tx in last_transactions:
                    if 'Ref3' not in tx:
                        tx['Ref3'] = ''
                    if 'Ref4' not in tx:
                        tx['Ref4'] = ''
                balance['last_transactions'] = last_transactions
            else:
                balance['last_transaction_date'] = None
                balance['last_transaction_description'] = 'No transactions found'
                balance['last_transaction_amount'] = 0
                balance['last_transactions'] = []

        return balances

    def check_sequence_numbers(self, account_code=None, administration=None, start_date='2025-01-01'):
        """Check if Ref2 sequence numbers are consecutive for specific accounts since start_date"""
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Override start_date with closure-derived opening balance date if available
        opening_balance_date = _get_opening_balance_date(self.db, administration)
        if opening_balance_date is not None:
            start_date = opening_balance_date

        # If account_code and administration provided, get IBAN from lookup
        if account_code and administration:
            cursor.execute("""
                SELECT rekeningNummer FROM vw_lookup_accounts
                WHERE Account = %s AND administration = %s
            """, (account_code, administration))
            lookup_result = cursor.fetchone()
            if not lookup_result:
                cursor.close()
                conn.close()
                return {'success': False, 'message': f'No IBAN found for account {account_code} in {administration}'}
            iban = lookup_result['rekeningNummer']
        else:
            iban = 'NL80RABO0107936917'  # Default

        # Get all transactions for the IBAN since start_date, ordered by Ref2
        cursor.execute("""
            SELECT TransactionDate, TransactionDescription, Ref2, TransactionAmount
            FROM mutaties
            WHERE Ref1 = %s
            AND TransactionDate >= %s
            AND Ref2 IS NOT NULL
            AND Ref2 != ''
            ORDER BY CAST(Ref2 AS UNSIGNED)
        """, (iban, start_date))

        transactions = cursor.fetchall()

        if not transactions:
            cursor.close()
            conn.close()
            return {'success': False, 'message': 'No transactions found'}

        # Check if Ref2 values are numeric (sequence check only applies to accounts with numeric Ref2)
        numeric_count = 0
        for tx in transactions[:10]:  # Sample first 10 transactions
            try:
                int(tx['Ref2'])
                numeric_count += 1
            except (ValueError, TypeError):
                pass

        if numeric_count == 0:
            # Non-numeric Ref2 values (e.g., Revolut descriptive references) — do running balance check
            result = self._check_balance_progression(transactions, iban, account_code, administration, start_date)
            cursor.close()
            conn.close()
            return result

        # Check for sequence gaps
        sequence_issues = []
        expected_next = None

        for i, tx in enumerate(transactions):
            try:
                current_seq = int(tx['Ref2'])

                if i == 0:
                    expected_next = current_seq + 1
                else:
                    if current_seq != expected_next:
                        sequence_issues.append({
                            'expected': expected_next,
                            'found': current_seq,
                            'gap': current_seq - expected_next,
                            'date': tx['TransactionDate'],
                            'description': tx['TransactionDescription'],
                            'amount': tx['TransactionAmount']
                        })
                    expected_next = current_seq + 1

            except ValueError:
                sequence_issues.append({
                    'error': f"Invalid sequence number: {tx['Ref2']}",
                    'date': tx['TransactionDate'],
                    'description': tx['TransactionDescription']
                })

        cursor.close()
        conn.close()

        # Handle first and last sequence safely
        first_sequence = None
        last_sequence = None
        if transactions:
            try:
                first_sequence = int(transactions[0]['Ref2'])
            except ValueError:
                pass
            try:
                last_sequence = int(transactions[-1]['Ref2'])
            except ValueError:
                pass

        return {
            'success': True,
            'iban': iban,
            'account_code': account_code,
            'administration': administration,
            'start_date': start_date,
            'total_transactions': len(transactions),
            'first_sequence': first_sequence,
            'last_sequence': last_sequence,
            'sequence_issues': sequence_issues,
            'has_gaps': len(sequence_issues) > 0
        }

    def _check_balance_progression(self, transactions, iban, account_code, administration, start_date):
        """Check running balance for accounts with non-numeric Ref2 (e.g., Revolut)."""
        def get_completion_date(tx):
            if tx.get('Ref2'):
                parts = tx['Ref2'].split('_')
                if len(parts) >= 3:
                    return parts[-1]
            return ''

        sorted_transactions = sorted(transactions, key=get_completion_date)

        balance_issues = []
        prev_saldo = None

        for tx in sorted_transactions:
            if not tx.get('Ref2'):
                continue

            parts = tx['Ref2'].split('_')
            if len(parts) < 3:
                continue

            try:
                current_saldo = float(parts[-2])
            except (ValueError, IndexError):
                continue

            amount = abs(float(tx['TransactionAmount'])) if tx.get('TransactionAmount') else 0.0

            if prev_saldo is not None:
                saldo_diff = round(current_saldo - prev_saldo, 2)

                if amount > 0 and abs(abs(saldo_diff) - amount) > 0.01:
                    balance_issues.append({
                        'expected': round(prev_saldo - amount, 2) if saldo_diff < 0 else round(prev_saldo + amount, 2),
                        'found': current_saldo,
                        'gap': round(current_saldo - (prev_saldo - amount if saldo_diff < 0 else prev_saldo + amount), 2),
                        'date': str(tx['TransactionDate']) if tx.get('TransactionDate') else '',
                        'description': tx.get('TransactionDescription', '')
                    })

            prev_saldo = current_saldo

        return {
            'success': True,
            'iban': iban,
            'account_code': account_code,
            'administration': administration,
            'start_date': start_date,
            'total_transactions': len(sorted_transactions),
            'first_sequence': None,
            'last_sequence': None,
            'has_gaps': len(balance_issues) > 0,
            'sequence_issues': balance_issues,
            'check_type': 'balance_comparison',
            'message': f'Running balance check: {len(balance_issues)} discrepancies found' if balance_issues else 'Running balance is consistent — no gaps found'
        }

    def check_revolut_balance_gaps(self, iban, account_code,
                                   start_date='2025-05-01', expected_final_balance=262.54):
        """
        Check for gaps in Revolut balance by comparing calculated running balance
        against the balance shown in Ref3 field.

        For Revolut transactions:
        - Ref2 format: [description]_[balance]_[datetime]
        - Ref3 contains: the balance from the bank statement

        Args:
            iban: Revolut IBAN
            account_code: Account code
            start_date: Start date for analysis (default: 2025-05-01)
            expected_final_balance: Expected final balance from Revolut (default: 262.54)

        Returns:
            Dictionary with balance analysis including gaps and discrepancies
        """
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT
                    ID,
                    TransactionDate,
                    TransactionDescription,
                    TransactionAmount,
                    Debet,
                    Credit,
                    Ref1,
                    Ref2,
                    Ref3,
                    Administration
                FROM mutaties
                WHERE Ref1 = %s
                AND TransactionDate >= %s
            """, (iban, start_date))

            transactions = cursor.fetchall()

            if not transactions:
                return {
                    'success': False,
                    'message': f'No transactions found for IBAN {iban} since {start_date}'
                }

            # Parse Ref2 to extract datetime and sort by it
            for tx in transactions:
                ref2_parts = (tx['Ref2'] or '').split('_')
                if len(ref2_parts) >= 3:
                    datetime_str = ref2_parts[2]
                    tx['ref2_datetime_str'] = datetime_str
                    try:
                        tx['ref2_datetime_obj'] = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        tx['ref2_datetime_obj'] = datetime.strptime(str(tx['TransactionDate']), '%Y-%m-%d')
                        tx['ref2_datetime_str'] = str(tx['TransactionDate'])
                else:
                    tx['ref2_datetime_str'] = str(tx['TransactionDate'])
                    tx['ref2_datetime_obj'] = datetime.strptime(str(tx['TransactionDate']), '%Y-%m-%d')

            # Sort by ID (database insertion order) - this is the correct sequence
            transactions.sort(key=lambda x: x['ID'])

            print(f"Total transactions after sorting by ID: {len(transactions)}", flush=True)
            if transactions:
                print(f"First transaction ID: {transactions[0]['ID']}", flush=True)
                print(f"First transaction: {transactions[0]['TransactionDescription']}", flush=True)
                print(f"First Ref3: {transactions[0]['Ref3']}", flush=True)
                print(f"Last transaction ID: {transactions[-1]['ID']}", flush=True)

            # Calculate running balance and compare with Ref3
            balance_gaps = []
            transaction_details = []

            calculated_balance = 0.0
            starting_balance_info = {}

            for i, tx in enumerate(transactions):
                amount = float(tx['TransactionAmount'] or 0)

                if tx['Debet'] == account_code:
                    balance_change = amount
                    direction = 'IN'
                elif tx['Credit'] == account_code:
                    balance_change = -amount
                    direction = 'OUT'
                else:
                    balance_change = 0
                    direction = 'SKIP'

                if i == 0 and tx['Ref3']:
                    try:
                        ref3_balance = float(tx['Ref3'])
                        calculated_balance = ref3_balance
                        starting_balance_info = {
                            'first_ref3': ref3_balance,
                            'first_balance_change': balance_change,
                            'calculated_balance': calculated_balance,
                            'note': 'First transaction uses Ref3 directly'
                        }
                        print(f"First transaction: using Ref3 directly as balance: {calculated_balance}", flush=True)
                    except (ValueError, TypeError):
                        calculated_balance = 0.0
                        starting_balance_info = {'error': 'Could not parse first Ref3'}
                else:
                    calculated_balance += balance_change

                # Parse Ref3 balance (if available)
                ref3_balance = None
                if tx['Ref3']:
                    try:
                        ref3_balance = float(tx['Ref3'])
                    except (ValueError, TypeError):
                        ref3_balance = None

                discrepancy = None
                if ref3_balance is not None:
                    discrepancy = round(ref3_balance - calculated_balance, 2)

                tx_detail = {
                    'id': tx['ID'],
                    'transaction_date': str(tx['TransactionDate']),
                    'ref2_datetime': tx['ref2_datetime_str'],
                    'description': tx['TransactionDescription'],
                    'amount': amount,
                    'debet': tx['Debet'],
                    'credit': tx['Credit'],
                    'direction': direction,
                    'balance_change': round(balance_change, 2),
                    'calculated_balance': round(calculated_balance, 2),
                    'ref3_balance': ref3_balance,
                    'discrepancy': discrepancy,
                    'ref2': tx['Ref2']
                }
                transaction_details.append(tx_detail)

                if discrepancy is not None and abs(discrepancy) > 0.01:
                    balance_gaps.append({
                        'transaction_id': tx['ID'],
                        'transaction_date': str(tx['TransactionDate']),
                        'ref2_datetime': tx['ref2_datetime_str'],
                        'description': tx['TransactionDescription'],
                        'calculated_balance': round(calculated_balance, 2),
                        'ref3_balance': ref3_balance,
                        'discrepancy': discrepancy,
                        'ref2': tx['Ref2']
                    })

            final_calculated = round(calculated_balance, 2)
            final_discrepancy = round(expected_final_balance - final_calculated, 2)

            cursor.close()
            conn.close()

            return {
                'success': True,
                'iban': iban,
                'account_code': account_code,
                'start_date': start_date,
                'starting_balance_debug': starting_balance_info,
                'total_transactions': len(transactions),
                'calculated_final_balance': final_calculated,
                'expected_final_balance': expected_final_balance,
                'final_discrepancy': final_discrepancy,
                'balance_gaps_found': len(balance_gaps),
                'balance_gaps': balance_gaps,
                'first_10_transactions': transaction_details[:10],
                'transactions_with_gaps': [tx for tx in transaction_details if tx.get('discrepancy') is not None and abs(tx['discrepancy']) > 0.01],
                'summary': {
                    'has_discrepancy': abs(final_discrepancy) > 0.01,
                    'missing_amount': final_discrepancy if final_discrepancy > 0 else 0,
                    'extra_amount': abs(final_discrepancy) if final_discrepancy < 0 else 0
                }
            }

        except Exception as e:
            cursor.close()
            conn.close()
            return {
                'success': False,
                'error': str(e)
            }
