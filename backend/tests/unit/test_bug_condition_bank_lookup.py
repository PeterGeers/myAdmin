"""
Bug Condition Exploration Test — Inconsistent Bank Account Resolution

Property 1: Bug Condition — Inconsistent Bank Account Resolution

CRITICAL: These tests MUST FAIL on unfixed code — failure confirms the bug exists.
DO NOT attempt to fix the test or the code when it fails.

Bug condition: Multiple code paths resolved bank accounts from inconsistent data sources
(legacy views like vw_rekeningnummers) instead of using the canonical
`rekeningschema` with `JSON_EXTRACT(parameters, '$.bank_account') = true`
via `get_bank_account_lookups()`.

NOTE: All production code paths have been fixed to use get_bank_account_lookups().
These tests now serve as regression guards ensuring no code path reverts to legacy views.

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

    Regression guard: ensures check_banking_accounts() uses
    self.db.get_bank_account_lookups() (canonical source) and not legacy views.
    When legacy views return empty but get_bank_account_lookups has accounts,
    the method must still return results.
    """

    def test_check_banking_accounts_uses_canonical_source(self):
        """
        Mock get_bank_account_lookups to return accounts, but mock the raw
        cursor to return empty. Ensures the method uses the canonical source
        (get_bank_account_lookups) and not legacy views.
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

            from banking_checks import BankingChecks
            processor._checks = BankingChecks(mock_db)

            result = processor.check_banking_accounts(administration='TestTenant')

            # Result must NOT be empty — it should use get_bank_account_lookups.
            assert result is not None
            assert len(result) != 0, (
                "REGRESSION: check_banking_accounts returned empty list. "
                "It must use get_bank_account_lookups() as the canonical source."
            )


# ---------------------------------------------------------------------------
# Test B: validate_iban_tenant uses canonical source
# ---------------------------------------------------------------------------

class TestValidateIbanTenantWrongDataSource:
    """
    **Validates: Requirements 1.4**

    Regression guard: ensures validate_iban_tenant() uses
    self.db.get_bank_account_lookups() (canonical source) and not legacy views.
    When legacy views return empty but get_bank_account_lookups has the IBAN,
    the method must still resolve the correct tenant.
    """

    def test_validate_iban_tenant_uses_canonical_source(self):
        """
        Mock get_bank_account_lookups to return the IBAN for TestTenant,
        but mock the raw cursor to return None. Ensures the method uses
        the canonical source and not legacy views.
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

            # Mock get_connection → cursor that returns None (simulating legacy view empty)
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.get_connection.return_value = mock_conn

            # The cursor returns None (legacy views would not find this IBAN)
            mock_cursor.fetchone.return_value = None

            from services.banking_service import BankingService
            service = BankingService.__new__(BankingService)
            service.test_mode = False
            service.db = mock_db

            result = service.validate_iban_tenant('NL99TEST1234567890', 'TestTenant')

            # Result must resolve tenant from get_bank_account_lookups.
            assert result['valid'] is True
            assert result['tenant'] == 'TestTenant', (
                f"REGRESSION: validate_iban_tenant returned tenant={result.get('tenant')}. "
                f"It must use get_bank_account_lookups() as the canonical source."
            )


# ---------------------------------------------------------------------------
# Property-based test: for random tenants/IBANs, the canonical source is used
# ---------------------------------------------------------------------------

class TestBankAccountResolutionProperty:
    """
    **Validates: Requirements 1.1, 1.2, 1.4, 1.5**

    Property: For any tenant and IBAN, when get_bank_account_lookups returns
    the account but legacy views would return empty, the functions must still
    find the account via get_bank_account_lookups (canonical source).
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

            from banking_checks import BankingChecks
            processor._checks = BankingChecks(mock_db)

            result = processor.check_banking_accounts(administration=tenant)

            assert len(result) != 0, (
                f"REGRESSION: check_banking_accounts({tenant}) returned empty. "
                f"Must use get_bank_account_lookups() which has [{iban}, {account_code}]."
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
        get_bank_account_lookups (canonical source).
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

            assert result['valid'] is True
            assert result['tenant'] == tenant, (
                f"REGRESSION: validate_iban_tenant({iban}, {tenant}) returned "
                f"tenant={result.get('tenant')}. Must use get_bank_account_lookups()."
            )
