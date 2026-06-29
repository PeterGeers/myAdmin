"""
Database Banking Queries Mixin

Domain-specific query methods for the banking processor module:
- Bank account lookups (via rekeningschema parameters)
- Credit card lookups
- Exchange rate accounts
- Transaction sequence tracking
- Pattern discovery
- Duplicate detection

Extracted from database.py to keep the core DatabaseManager focused on
generic database operations (connection, execute, transaction).
"""

from db_exceptions import DatabaseError


class DatabaseBankingQueriesMixin:
    """Mixin providing banking-specific query methods.

    Requires self.execute_query() from DatabaseManager.
    """

    def get_used_transaction_numbers(self, ref1, table_name='mutaties'):
        """Get existing transaction numbers for duplicate prevention"""
        return self.execute_query(f"SELECT Ref2 FROM {table_name} WHERE Ref1 = %s", (ref1,))

    def get_bank_account_lookups(self, administration=None):
        """Get bank account lookup data from rekeningschema using parameters $.bank_account flag.

        The IBAN is read from the parameters JSON ($.iban) as the canonical source,
        falling back to the AccountLookup column for legacy data.
        """
        base_query = """
            SELECT
                COALESCE(
                    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(parameters, '$.iban')), 'null'),
                    NULLIF(AccountLookup, '')
                ) AS rekeningNummer,
                Account,
                administration
            FROM rekeningschema
            WHERE JSON_EXTRACT(parameters, '$.bank_account') = true
        """
        if administration:
            return self.execute_query(
                base_query + " AND administration = %s ORDER BY administration, Account",
                (administration,)
            )
        return self.execute_query(base_query + " ORDER BY administration, Account")

    def get_credit_card_lookups(self, administration=None):
        """Get credit card lookup data from rekeningschema using parameters $.credit_card flag.

        Args:
            administration: Optional tenant filter

        Returns:
            List of dicts with keys: cc_bank_iban, Account, card_number, administration
        """
        base_query = """
            SELECT
                JSON_UNQUOTE(JSON_EXTRACT(parameters, '$.cc_bank_iban')) AS cc_bank_iban,
                Account,
                JSON_UNQUOTE(JSON_EXTRACT(parameters, '$.card_number')) AS card_number,
                administration
            FROM rekeningschema
            WHERE JSON_EXTRACT(parameters, '$.credit_card') = true
        """
        if administration:
            return self.execute_query(
                base_query + " AND administration = %s ORDER BY administration, Account",
                (administration,)
            )
        return self.execute_query(base_query + " ORDER BY administration, Account")

    def get_exchange_rate_account(self, administration=None):
        """Get the exchange rate difference account from rekeningschema.

        Args:
            administration: Optional tenant filter

        Returns:
            List of dicts with keys: Account, administration
        """
        base_query = """
            SELECT Account, administration
            FROM rekeningschema
            WHERE JSON_EXTRACT(parameters, '$.exchange_rate_account') = true
        """
        if administration:
            return self.execute_query(
                base_query + " AND administration = %s",
                (administration,)
            )
        return self.execute_query(base_query)

    def get_existing_sequences(self, iban, table_name='mutaties', administration=None):
        """Get existing Ref2 sequences for a specific IBAN within last 2 years."""
        query = f"""
            SELECT Ref2 as existing FROM {table_name}
            WHERE Ref1 = %s AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
            AND Ref2 IS NOT NULL AND Ref2 != ''
        """
        params = [iban]

        if administration:
            query += " AND administration = %s"
            params.append(administration)

        results = self.execute_query(query, tuple(params))
        return [r['existing'] for r in results]

    def get_patterns(self, administration):
        """Get patterns from vw_readreferences view with date filtering.

        Bank accounts are resolved from rekeningschema.parameters $.bank_account flag.
        """
        return self.execute_query("""
            SELECT debet, credit, administration, referenceNumber, Date
            FROM vw_readreferences
            WHERE administration = %s
            AND (debet IN (
                SELECT Account FROM rekeningschema
                WHERE administration = %s
                  AND JSON_EXTRACT(parameters, '$.bank_account') = true
            ) OR credit IN (
                SELECT Account FROM rekeningschema
                WHERE administration = %s
                  AND JSON_EXTRACT(parameters, '$.bank_account') = true
            ))
            AND Date >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
            ORDER BY Date DESC
        """, (administration, administration, administration))

    def get_recent_transactions(self, limit=100, table_name='mutaties', administration=None):
        """Get recent transactions for lookup data"""
        if administration:
            return self.execute_query(f"""
                SELECT TransactionDescription, Debet, Credit, administration FROM {table_name}
                WHERE administration = %s
                ORDER BY ID DESC LIMIT %s
            """, (administration, limit))
        return self.execute_query(f"""
            SELECT TransactionDescription, Debet, Credit, administration FROM {table_name}
            ORDER BY ID DESC LIMIT %s
        """, (limit,))

    def get_previous_transactions(self, reference_number, limit=3, table_name='mutaties'):
        """Get previous transactions with descriptions for AI pattern learning"""
        query = f"""
            SELECT TransactionDate as Datum, TransactionDescription as Omschrijving,
                   TransactionAmount as Bedrag, Debet, Credit
            FROM {table_name}
            WHERE ReferenceNumber LIKE %s
            ORDER BY TransactionDate DESC, ID DESC
            LIMIT %s
        """

        results = self.execute_query(query, (f"%{reference_number}%", limit))
        return results if results else []

    def check_duplicate_transactions(self, reference_number, transaction_date,
                                     transaction_amount, table_name='mutaties'):
        """
        Check for existing transactions with matching criteria within 2-year window.

        Args:
            reference_number: The reference number to match
            transaction_date: The transaction date to match (YYYY-MM-DD format)
            transaction_amount: The transaction amount to match
            table_name: The table to search in (default: 'mutaties')

        Returns:
            List of matching transactions, empty list if none found
        """
        try:
            query = f"""
                SELECT ID, TransactionNumber, TransactionDate, TransactionDescription,
                       TransactionAmount, Debet, Credit, ReferenceNumber,
                       Ref1, Ref2, Ref3, Ref4, Administration
                FROM {table_name}
                WHERE ReferenceNumber = %s
                AND TransactionDate = %s
                AND ABS(TransactionAmount - %s) < 0.01
                AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
                ORDER BY ID DESC
            """

            results = self.execute_query(query, (reference_number, transaction_date, transaction_amount))
            return results if results else []

        except DatabaseError as e:
            print(f"Database error during duplicate check: {e}")
            raise Exception(f"Database connection failed during duplicate check: {str(e)}")
        except Exception as e:
            print(f"Unexpected error during duplicate check: {e}")
            raise Exception(f"Duplicate check failed: {str(e)}")
