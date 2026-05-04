"""
Preservation Property Tests — Valid File Processing and Cross-Tenant Rejection Unchanged

Property 2: Preservation — Valid File Processing and Cross-Tenant Rejection Unchanged

These tests capture the CURRENT (unfixed) behavior of check_banking_accounts and
validate_iban_tenant for valid inputs. They must PASS on unfixed code to establish
a baseline. After the fix is applied, these tests ensure no regressions.

Observation-first methodology:
  Step 1 — Observe concrete behavior on unfixed code
  Step 2 — Write property-based tests capturing that behavior

Validates: Requirements 3.1, 3.2, 3.3, 3.6
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings

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

# Balance amounts: reasonable monetary values
balance_strategy = st.floats(min_value=-99999.99, max_value=99999.99, allow_nan=False, allow_infinity=False).map(
    lambda x: round(x, 2)
)


# ===========================================================================
# Step 1 — Observe behavior on UNFIXED code (concrete deterministic tests)
# ===========================================================================

class TestCheckBankingAccountsPreservation:
    """
    **Validates: Requirements 3.1, 3.3**

    Observe: check_banking_accounts(administration='TestTenant') with valid
    accounts in vw_rekeningnummers returns correct balance data from vw_mutaties.
    This captures the CURRENT working behavior for valid accounts.
    """

    def test_check_banking_accounts_returns_balance_data(self):
        """
        When get_bank_account_lookups returns accounts AND execute_query returns
        balance data, check_banking_accounts returns correct balance structure.

        Mock sequence:
        1st execute_query call: opening balance date (returns None)
        2nd execute_query call (get_bank_account_lookups): accounts from $.bank_account flag
        3rd execute_query call: balances from vw_mutaties
        4th execute_query call: last transactions from mutaties
        """
        mock_db = MagicMock()

        # get_bank_account_lookups returns accounts from $.bank_account flag
        mock_db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': 'NL99TEST1234567890', 'Account': '1099', 'administration': 'TestTenant'},
        ]

        # execute_query is called for:
        # 1. _get_opening_balance_date
        # 2. vw_mutaties balance query
        # 3. mutaties last transaction query
        mock_db.execute_query.side_effect = [
            # Opening balance date
            [{'last_closed_year': None}],
            # vw_mutaties balances
            [{
                'Reknum': '1099',
                'administration': 'TestTenant',
                'calculated_balance': 1500.50,
                'account_name': 'Test Bank Account',
            }],
            # mutaties last transactions for account 1099
            [{
                'TransactionDate': '2026-04-15',
                'TransactionDescription': 'Last payment',
                'TransactionAmount': -100.00,
                'Debet': '',
                'Credit': '1099',
                'Ref2': '42',
                'Ref3': '1500.50',
                'Ref4': 'test.csv',
            }],
        ]

        from banking_processor import BankingProcessor
        processor = BankingProcessor.__new__(BankingProcessor)
        processor.test_mode = False
        processor.db = mock_db
        processor.download_folder = '/tmp'

        result = processor.check_banking_accounts(administration='TestTenant')

        # Should return balance data
        assert len(result) == 1
        assert result[0]['Reknum'] == '1099'
        assert result[0]['administration'] == 'TestTenant'
        assert result[0]['calculated_balance'] == 1500.50
        assert result[0]['account_name'] == 'Test Bank Account'
        assert result[0]['last_transaction_date'] == '2026-04-15'
        assert result[0]['last_transaction_description'] == 'Last payment'
        assert result[0]['last_transaction_amount'] == -100.00
        assert len(result[0]['last_transactions']) == 1


class TestValidateIbanTenantPreservation:
    """
    **Validates: Requirements 3.2**

    Observe: validate_iban_tenant returns correct results when vw_lookup_accounts
    finds the IBAN. Tests both correct-tenant and wrong-tenant scenarios.
    """

    def test_validate_iban_correct_tenant_returns_valid(self):
        """
        When get_bank_account_lookups finds the IBAN for the correct tenant,
        validate_iban_tenant returns {'valid': True, 'tenant': correctTenant}.
        """
        mock_db = MagicMock()

        # get_bank_account_lookups returns the IBAN belonging to TestTenant
        mock_db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': 'NL99TEST1234567890', 'Account': '1099', 'administration': 'TestTenant'}
        ]

        from services.banking_service import BankingService
        service = BankingService.__new__(BankingService)
        service.test_mode = False
        service.db = mock_db

        result = service.validate_iban_tenant('NL99TEST1234567890', 'TestTenant')

        assert result['valid'] is True
        assert result['tenant'] == 'TestTenant'
        assert 'error' not in result

    def test_validate_iban_wrong_tenant_returns_access_denied(self):
        """
        When get_bank_account_lookups finds the IBAN belonging to a different tenant,
        validate_iban_tenant returns {'valid': False, 'tenant': actualTenant,
        'error': 'Access denied: ...'}.
        """
        mock_db = MagicMock()

        # get_bank_account_lookups returns the IBAN belonging to TenantA
        mock_db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': 'NL99TEST1234567890', 'Account': '1099', 'administration': 'TenantA'}
        ]

        from services.banking_service import BankingService
        service = BankingService.__new__(BankingService)
        service.test_mode = False
        service.db = mock_db

        result = service.validate_iban_tenant('NL99TEST1234567890', 'TenantB')

        assert result['valid'] is False
        assert result['tenant'] == 'TenantA'
        assert 'Access denied' in result['error']
        assert 'TenantA' in result['error']
        assert 'TenantB' in result['error']


# ===========================================================================
# Step 2 — Property-based tests capturing observed behavior
# ===========================================================================

class TestCheckBankingAccountsBalanceProperty:
    """
    **Validates: Requirements 3.1, 3.3**

    Property: for all valid IBANs, check_banking_accounts returns identical
    balance data structure. Uses hypothesis to generate random tenant names,
    IBANs, account codes, and balance amounts.
    """

    @given(
        tenant=tenant_strategy,
        iban=iban_strategy,
        account_code=account_code_strategy,
        calc_balance=balance_strategy,
        tx_amount=st.floats(min_value=-9999.99, max_value=9999.99, allow_nan=False, allow_infinity=False).map(
            lambda x: round(x, 2)
        ),
    )
    @settings(max_examples=50, deadline=5000)
    def test_check_banking_accounts_returns_correct_balance_structure(
        self, tenant, iban, account_code, calc_balance, tx_amount
    ):
        """
        Property: for any valid tenant/IBAN/account combination where
        get_bank_account_lookups returns accounts and execute_query returns balances,
        check_banking_accounts returns the correct balance data structure.
        """
        mock_db = MagicMock()

        # get_bank_account_lookups returns accounts from $.bank_account flag
        mock_db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': iban, 'Account': account_code, 'administration': tenant}
        ]

        # execute_query is called for:
        # 1. _get_opening_balance_date
        # 2. vw_mutaties balance query
        # 3. mutaties last transaction query
        mock_db.execute_query.side_effect = [
            # Opening balance date
            [{'last_closed_year': None}],
            # vw_mutaties balances
            [{
                'Reknum': account_code,
                'administration': tenant,
                'calculated_balance': calc_balance,
                'account_name': f'Account {account_code}',
            }],
            # mutaties last transactions
            [{
                'TransactionDate': '2026-04-15',
                'TransactionDescription': 'Test transaction',
                'TransactionAmount': tx_amount,
                'Debet': '' if tx_amount < 0 else account_code,
                'Credit': account_code if tx_amount < 0 else '',
                'Ref2': '1',
                'Ref3': str(calc_balance),
                'Ref4': 'test.csv',
            }],
        ]

        from banking_processor import BankingProcessor
        processor = BankingProcessor.__new__(BankingProcessor)
        processor.test_mode = False
        processor.db = mock_db
        processor.download_folder = '/tmp'

        result = processor.check_banking_accounts(administration=tenant)

        # Verify correct balance data structure
        assert len(result) == 1
        assert result[0]['Reknum'] == account_code
        assert result[0]['administration'] == tenant
        assert result[0]['calculated_balance'] == calc_balance
        assert result[0]['account_name'] == f'Account {account_code}'
        assert result[0]['last_transaction_date'] == '2026-04-15'
        assert result[0]['last_transaction_description'] == 'Test transaction'
        assert result[0]['last_transaction_amount'] == tx_amount
        assert len(result[0]['last_transactions']) == 1


class TestCrossTenantRejectionProperty:
    """
    **Validates: Requirements 3.2**

    Property: for all cross-tenant IBAN/tenant pairs, rejection behavior
    is preserved. When vw_lookup_accounts returns the IBAN belonging to
    tenantA, calling validate_iban_tenant(iban, tenantB) returns valid=False
    with access denied message containing both tenant names.
    """

    @given(
        iban=iban_strategy,
        tenant_a=tenant_strategy,
        tenant_b=tenant_strategy,
    )
    @settings(max_examples=50, deadline=5000)
    def test_cross_tenant_rejection_preserved(self, iban, tenant_a, tenant_b):
        """
        Property: for any IBAN belonging to tenantA, calling
        validate_iban_tenant(iban, tenantB) returns valid=False with
        access denied message.
        """
        # Ensure tenants are different
        if tenant_a == tenant_b:
            return  # skip — same tenant is not a cross-tenant scenario

        mock_db = MagicMock()

        # get_bank_account_lookups returns the IBAN belonging to tenant_a
        mock_db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': iban, 'Account': '1099', 'administration': tenant_a}
        ]

        from services.banking_service import BankingService
        service = BankingService.__new__(BankingService)
        service.test_mode = False
        service.db = mock_db

        result = service.validate_iban_tenant(iban, tenant_b)

        # Cross-tenant rejection must be preserved
        assert result['valid'] is False
        assert result['tenant'] == tenant_a
        assert 'Access denied' in result['error']
        assert tenant_a in result['error']
        assert tenant_b in result['error']
        assert iban in result['error']
