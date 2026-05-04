"""
Bug Condition Exploration Test — Inconsistent Bank Account Resolution

Property 1: Bug Condition — Inconsistent Bank Account Resolution

CRITICAL: These tests MUST FAIL on unfixed code — failure confirms the bug exists.
DO NOT attempt to fix the test or the code when it fails.

Bug condition: Multiple code paths resolve bank accounts from inconsistent data sources
(vw_rekeningnummers, vw_lookup_accounts) instead of using the canonical
`rekeningschema` with `JSON_EXTRACT(parameters, '$.bank_account') = true`.

Validates: Requirements 1.1, 1.2, 1.4, 1.5, 1.6, 1.7, 1.8
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# Strategies for hypothesis
# ---------------------------------------------------------------------------

# Tenant names: non-empty alphanumeric strings
tenant_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N')),
    min_size=3, max_size=20
).filter(lambda s: s.strip() != '')

# IBAN-like strings: NL + 2 digits + TEST + 10 digits
iban_strategy = st.builds(
    lambda digits, suffix: f'NL{digits:02d}TEST{suffix:010d}',
    st.integers(min_value=10, max_value=99),
    st.integers(min_value=1000000000, max_value=9999999999),
)

# Account codes: 4-digit strings
account_code_strategy = st.integers(min_value=1000, max_value=9999).map(str)


# ---------------------------------------------------------------------------
# Test A: check_banking_accounts uses wrong data source (vw_rekeningnummers)
# ---------------------------------------------------------------------------

class TestCheckBankingAccountsWrongDataSource:
    """
    **Validates: Requirements 1.1, 1.2, 1.5**

    check_banking_accounts() queries vw_rekeningnummers directly instead of
    using self.db.get_bank_account_lookups(). When vw_rekeningnummers returns
    empty but get_bank_account_lookups has accounts, the method returns [].

    On UNFIXED code: the method queries vw_rekeningnummers (empty) → returns []
    → test FAILS (confirms bug).
    """

    def test_check_banking_accounts_uses_canonical_source(self):
        """
        Mock get_bank_account_lookups to return accounts, but mock the raw
        cursor (vw_rekeningnummers) to return empty. On unfixed code, the
        method uses the cursor → returns [] → assertion fails.
        """
        with patch('banking_processor.DatabaseManager') as MockDBClass:
            mock_db = MagicMock()
            MockDBClass.return_value = mock_db

            # The canonical source has accounts
            mock_db.get_bank_account_lookups.return_value = [
                {
                    'rekeningNummer': 'NL99TEST1234567890',
                    'Account': '1099',
                    'administration': 'TestTenant'
                }
            ]

            # Mock execute_query for sequential calls:
            # 1. opening balance date
            # 2. vw_mutaties balance query
            # 3. mutaties last transaction query
            mock_db.execute_query.side_effect = [
                [{'last_closed_year': None}],
                [{'Reknum': '1099', 'administration': 'TestTenant',
                  'calculated_balance': 100.0, 'account_name': 'Test Account'}],
                [{'TransactionDate': '2026-04-15', 'TransactionDescription': 'Test',
                  'TransactionAmount': 10.0, 'Debet': '', 'Credit': '1099',
                  'Ref2': '1', 'Ref3': '100.0', 'Ref4': 'test.csv'}],
            ]

            # Mock get_connection → cursor that returns EMPTY for vw_rekeningnummers
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.get_connection.return_value = mock_conn

            # The cursor returns empty results for vw_rekeningnummers queries
            mock_cursor.fetchall.return_value = []

            from banking_processor import BankingProcessor
            processor = BankingProcessor.__new__(BankingProcessor)
            processor.test_mode = False
            processor.db = mock_db
            processor.download_folder = '/tmp'

            result = processor.check_banking_accounts(administration='TestTenant')

            # Expected: result should NOT be empty — it should contain the
            # accounts from get_bank_account_lookups.
            # On UNFIXED code: result IS empty because it queries
            # vw_rekeningnummers (which returns []) → FAILS
            assert result is not None
            assert len(result) != 0, (
                "BUG CONFIRMED: check_banking_accounts returned empty list. "
                "It queries vw_rekeningnummers (empty) instead of using "
                "get_bank_account_lookups() which has accounts."
            )


# ---------------------------------------------------------------------------
# Test B: validate_iban_tenant uses wrong data source (vw_lookup_accounts)
# ---------------------------------------------------------------------------

class TestValidateIbanTenantWrongDataSource:
    """
    **Validates: Requirements 1.4**

    validate_iban_tenant() queries vw_lookup_accounts directly instead of
    using self.db.get_bank_account_lookups(). When the IBAN is not in
    vw_lookup_accounts but IS in get_bank_account_lookups, the method
    returns tenant=None.

    On UNFIXED code: the method queries vw_lookup_accounts (returns None)
    → returns {'valid': True, 'tenant': None, 'warning': ...}
    → test FAILS because tenant is None, not 'TestTenant'.
    """

    def test_validate_iban_tenant_uses_canonical_source(self):
        """
        Mock get_bank_account_lookups to return the IBAN for TestTenant,
        but mock the raw cursor (vw_lookup_accounts) to return None.
        On unfixed code, the method queries vw_lookup_accounts → returns
        tenant=None → assertion fails.
        """
        with patch('services.banking_service.DatabaseManager') as MockDBClass:
            mock_db = MagicMock()
            MockDBClass.return_value = mock_db

            # The canonical source has the IBAN
            mock_db.get_bank_account_lookups.return_value = [
                {
                    'rekeningNummer': 'NL99TEST1234567890',
                    'Account': '1099',
                    'administration': 'TestTenant'
                }
            ]

            # Mock get_connection → cursor that returns None for vw_lookup_accounts
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.get_connection.return_value = mock_conn

            # The cursor returns None (IBAN not found in vw_lookup_accounts)
            mock_cursor.fetchone.return_value = None

            from services.banking_service import BankingService
            service = BankingService.__new__(BankingService)
            service.test_mode = False
            service.db = mock_db

            result = service.validate_iban_tenant('NL99TEST1234567890', 'TestTenant')

            # Expected: result should show valid=True with tenant='TestTenant'
            # because the IBAN exists in get_bank_account_lookups for TestTenant.
            # On UNFIXED code: result is {'valid': True, 'tenant': None, 'warning': ...}
            # because it queries vw_lookup_accounts (returns None) → FAILS
            assert result['valid'] is True
            assert result['tenant'] == 'TestTenant', (
                f"BUG CONFIRMED: validate_iban_tenant returned tenant={result.get('tenant')}. "
                f"It queries vw_lookup_accounts (returns None) instead of using "
                f"get_bank_account_lookups() which has the IBAN for 'TestTenant'."
            )


# ---------------------------------------------------------------------------
# Property-based test: for random tenants/IBANs, the canonical source is used
# ---------------------------------------------------------------------------

class TestBankAccountResolutionProperty:
    """
    **Validates: Requirements 1.1, 1.2, 1.4, 1.5**

    Property: For any tenant and IBAN, when get_bank_account_lookups returns
    the account but the legacy views return empty, the functions should still
    find the account (because they should use get_bank_account_lookups).

    On UNFIXED code: functions use legacy views → return empty/None → FAILS.
    """

    @given(
        tenant=tenant_strategy,
        iban=iban_strategy,
        account_code=account_code_strategy,
    )
    @settings(max_examples=30, deadline=5000)
    def test_check_banking_accounts_resolves_from_canonical_source(
        self, tenant, iban, account_code
    ):
        """
        Property: check_banking_accounts should return accounts from
        get_bank_account_lookups, not from vw_rekeningnummers.
        """
        with patch('banking_processor.DatabaseManager') as MockDBClass:
            mock_db = MagicMock()
            MockDBClass.return_value = mock_db

            mock_db.get_bank_account_lookups.return_value = [
                {
                    'rekeningNummer': iban,
                    'Account': account_code,
                    'administration': tenant
                }
            ]

            # Sequential execute_query calls:
            # 1. opening balance date
            # 2. vw_mutaties balance query
            # 3. mutaties last transaction query
            mock_db.execute_query.side_effect = [
                [{'last_closed_year': None}],
                [{'Reknum': account_code, 'administration': tenant,
                  'calculated_balance': 100.0, 'account_name': f'Account {account_code}'}],
                [{'TransactionDate': '2026-04-15', 'TransactionDescription': 'Test',
                  'TransactionAmount': 10.0, 'Debet': '', 'Credit': account_code,
                  'Ref2': '1', 'Ref3': '100.0', 'Ref4': 'test.csv'}],
            ]

            # Legacy view returns empty
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.get_connection.return_value = mock_conn
            mock_cursor.fetchall.return_value = []

            from banking_processor import BankingProcessor
            processor = BankingProcessor.__new__(BankingProcessor)
            processor.test_mode = False
            processor.db = mock_db
            processor.download_folder = '/tmp'

            result = processor.check_banking_accounts(administration=tenant)

            # On UNFIXED code: returns [] because vw_rekeningnummers is empty
            assert len(result) != 0, (
                f"BUG: check_banking_accounts({tenant}) returned empty. "
                f"Legacy vw_rekeningnummers is empty but "
                f"get_bank_account_lookups has [{iban}, {account_code}]."
            )

    @given(
        tenant=tenant_strategy,
        iban=iban_strategy,
        account_code=account_code_strategy,
    )
    @settings(max_examples=30, deadline=5000)
    def test_validate_iban_tenant_resolves_from_canonical_source(
        self, tenant, iban, account_code
    ):
        """
        Property: validate_iban_tenant should find the IBAN via
        get_bank_account_lookups, not via vw_lookup_accounts.
        """
        with patch('services.banking_service.DatabaseManager') as MockDBClass:
            mock_db = MagicMock()
            MockDBClass.return_value = mock_db

            mock_db.get_bank_account_lookups.return_value = [
                {
                    'rekeningNummer': iban,
                    'Account': account_code,
                    'administration': tenant
                }
            ]

            # Legacy view returns None
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.get_connection.return_value = mock_conn
            mock_cursor.fetchone.return_value = None

            from services.banking_service import BankingService
            service = BankingService.__new__(BankingService)
            service.test_mode = False
            service.db = mock_db

            result = service.validate_iban_tenant(iban, tenant)

            # On UNFIXED code: returns tenant=None because vw_lookup_accounts
            # returns None
            assert result['valid'] is True
            assert result['tenant'] == tenant, (
                f"BUG: validate_iban_tenant({iban}, {tenant}) returned "
                f"tenant={result.get('tenant')}. Legacy vw_lookup_accounts "
                f"returns None but get_bank_account_lookups has the IBAN."
            )
