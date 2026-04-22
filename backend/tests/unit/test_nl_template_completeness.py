"""
Tests for nl.json chart of accounts template completeness.

Validates that the template has all required rekeningschema.parameters flags
pre-configured so new tenants work correctly from day one.

Requirements: 2.10
"""

import json
import os
import pytest

pytestmark = pytest.mark.unit

TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'src',
    'templates', 'chart_of_accounts', 'nl.json'
)


@pytest.fixture(scope='module')
def template_accounts():
    """Load the nl.json template once for all tests."""
    with open(TEMPLATE_PATH) as f:
        return json.load(f)


@pytest.fixture(scope='module')
def accounts_by_number(template_accounts):
    """Index accounts by account number for quick lookup."""
    return {a['Account']: a for a in template_accounts}


# ---------------------------------------------------------------------------
# Bank accounts: 1002-1004 must have $.bank_account = true
# ---------------------------------------------------------------------------
class TestBankAccountFlags:
    """Bank accounts must have bank_account flag for pattern validation."""

    BANK_ACCOUNTS = ['1002', '1003', '1004']

    @pytest.mark.parametrize('account_number', BANK_ACCOUNTS)
    def test_bank_account_has_flag(self, accounts_by_number, account_number):
        acct = accounts_by_number[account_number]
        params = acct.get('parameters') or {}
        assert params.get('bank_account') is True, (
            f"Account {account_number} ({acct['AccountName']}) "
            f"missing bank_account=true, got parameters={acct['parameters']}"
        )

    def test_bank_accounts_have_pattern_true(self, accounts_by_number):
        """Bank accounts should also have Pattern=true (pre-existing)."""
        for num in self.BANK_ACCOUNTS:
            assert accounts_by_number[num]['Pattern'] is True


# ---------------------------------------------------------------------------
# Expense accounts: all 4xxx must have $.expense_account = true
# ---------------------------------------------------------------------------
class TestExpenseAccountFlags:
    """All 4xxx expense accounts must have expense_account flag."""

    def test_all_4xxx_have_expense_flag(self, template_accounts):
        expense_accounts = [
            a for a in template_accounts if a['Account'].startswith('4')
        ]
        assert len(expense_accounts) > 0, "No 4xxx accounts found in template"

        missing = []
        for acct in expense_accounts:
            params = acct.get('parameters') or {}
            if not params.get('expense_account'):
                missing.append(f"{acct['Account']} ({acct['AccountName']})")

        assert not missing, (
            f"Expense accounts missing expense_account=true: {missing}"
        )

    def test_expense_accounts_are_pl(self, template_accounts):
        """All 4xxx accounts should be P&L accounts (VW='Y')."""
        for acct in template_accounts:
            if acct['Account'].startswith('4'):
                assert acct['VW'] == 'Y', (
                    f"Account {acct['Account']} should be VW='Y'"
                )


# ---------------------------------------------------------------------------
# Revenue accounts: all 8xxx must have $.revenue_account = true
# ---------------------------------------------------------------------------
class TestRevenueAccountFlags:
    """All 8xxx revenue accounts must have revenue_account flag."""

    def test_all_8xxx_have_revenue_flag(self, template_accounts):
        revenue_accounts = [
            a for a in template_accounts if a['Account'].startswith('8')
        ]
        assert len(revenue_accounts) > 0, "No 8xxx accounts found in template"

        missing = []
        for acct in revenue_accounts:
            params = acct.get('parameters') or {}
            if not params.get('revenue_account'):
                missing.append(f"{acct['Account']} ({acct['AccountName']})")

        assert not missing, (
            f"Revenue accounts missing revenue_account=true: {missing}"
        )

    def test_revenue_accounts_are_pl(self, template_accounts):
        """All 8xxx accounts should be P&L accounts (VW='Y')."""
        for acct in template_accounts:
            if acct['Account'].startswith('8'):
                assert acct['VW'] == 'Y', (
                    f"Account {acct['Account']} should be VW='Y'"
                )


# ---------------------------------------------------------------------------
# STR revenue account: 8003 must have $.str_revenue_account = true
# ---------------------------------------------------------------------------
class TestStrRevenueAccountFlag:
    """Account 8003 (Omzet verhuur) must be flagged as STR revenue."""

    def test_8003_has_str_revenue_flag(self, accounts_by_number):
        acct = accounts_by_number['8003']
        params = acct.get('parameters') or {}
        assert params.get('str_revenue_account') is True, (
            f"Account 8003 missing str_revenue_account=true, "
            f"got parameters={acct['parameters']}"
        )

    def test_only_one_str_revenue_account(self, template_accounts):
        """Exactly one account should have str_revenue_account flag."""
        str_accounts = [
            a for a in template_accounts
            if (a.get('parameters') or {}).get('str_revenue_account')
        ]
        assert len(str_accounts) == 1, (
            f"Expected exactly 1 str_revenue_account, found {len(str_accounts)}: "
            f"{[a['Account'] for a in str_accounts]}"
        )


# ---------------------------------------------------------------------------
# BTW rate flags: revenue accounts must have correct $.btw_rate values
# ---------------------------------------------------------------------------
class TestBtwRateFlags:
    """Revenue accounts must have btw_rate indicating VAT treatment."""

    EXPECTED_BTW_RATES = {
        '8000': 'zero',   # Opbrengsten
        '8001': 'high',   # Omzet dienstverlening
        '8002': 'high',   # Omzet ICT
        '8003': 'low',    # Omzet verhuur (STR)
        '8081': 'zero',   # Ontvangen Rente
        '8082': 'zero',   # Ontvangen Dividend
        '8098': 'zero',   # Bijzondere baten en lasten
        '8099': 'zero',   # Bijzondere baten en lasten
    }

    @pytest.mark.parametrize(
        'account_number,expected_rate',
        list(EXPECTED_BTW_RATES.items()),
        ids=[f"{k}-{v}" for k, v in EXPECTED_BTW_RATES.items()]
    )
    def test_btw_rate_value(self, accounts_by_number, account_number, expected_rate):
        acct = accounts_by_number[account_number]
        params = acct.get('parameters') or {}
        assert params.get('btw_rate') == expected_rate, (
            f"Account {account_number} ({acct['AccountName']}) "
            f"btw_rate should be '{expected_rate}', "
            f"got '{params.get('btw_rate')}'"
        )

    def test_all_revenue_accounts_have_btw_rate(self, template_accounts):
        """Every 8xxx account must have a btw_rate value."""
        missing = []
        for acct in template_accounts:
            if acct['Account'].startswith('8'):
                params = acct.get('parameters') or {}
                if 'btw_rate' not in params:
                    missing.append(f"{acct['Account']} ({acct['AccountName']})")
        assert not missing, (
            f"Revenue accounts missing btw_rate: {missing}"
        )

    def test_btw_rate_values_are_valid(self, template_accounts):
        """btw_rate must be one of 'high', 'low', 'zero'."""
        valid_rates = {'high', 'low', 'zero'}
        for acct in template_accounts:
            params = acct.get('parameters') or {}
            rate = params.get('btw_rate')
            if rate is not None:
                assert rate in valid_rates, (
                    f"Account {acct['Account']} has invalid btw_rate "
                    f"'{rate}', expected one of {valid_rates}"
                )


# ---------------------------------------------------------------------------
# Preserved existing parameters: must not lose pre-existing flags
# ---------------------------------------------------------------------------
class TestPreservedParameters:
    """Existing parameters values must be preserved after template update."""

    def test_2001_has_roles_interim_opening_balance(self, accounts_by_number):
        params = accounts_by_number['2001'].get('parameters') or {}
        assert params.get('roles') == ['interim_opening_balance']

    def test_2010_has_vat_netting_and_primary(self, accounts_by_number):
        params = accounts_by_number['2010'].get('parameters') or {}
        assert params.get('vat_netting') is True
        assert params.get('vat_primary') == '2010'

    def test_2020_has_vat_netting_and_primary(self, accounts_by_number):
        params = accounts_by_number['2020'].get('parameters') or {}
        assert params.get('vat_netting') is True
        assert params.get('vat_primary') == '2010'

    def test_2021_has_vat_netting_and_primary(self, accounts_by_number):
        params = accounts_by_number['2021'].get('parameters') or {}
        assert params.get('vat_netting') is True
        assert params.get('vat_primary') == '2010'

    def test_3051_has_asset_account(self, accounts_by_number):
        params = accounts_by_number['3051'].get('parameters') or {}
        assert params.get('asset_account') is True

    def test_3060_has_asset_account(self, accounts_by_number):
        params = accounts_by_number['3060'].get('parameters') or {}
        assert params.get('asset_account') is True

    def test_3080_has_roles_equity_result(self, accounts_by_number):
        params = accounts_by_number['3080'].get('parameters') or {}
        assert params.get('roles') == ['equity_result']

    def test_8099_preserves_roles_pl_closing(self, accounts_by_number):
        """8099 should have both the original roles AND new revenue flags."""
        params = accounts_by_number['8099'].get('parameters') or {}
        assert params.get('roles') == ['pl_closing'], (
            f"8099 lost its roles=['pl_closing'], got {params}"
        )
        assert params.get('revenue_account') is True
        assert params.get('btw_rate') == 'zero'


# ---------------------------------------------------------------------------
# No account that should have flags still has parameters=null
# ---------------------------------------------------------------------------
class TestNoMissingFlags:
    """Accounts that need flags must not have parameters=null."""

    def test_no_bank_account_with_null_params(self, accounts_by_number):
        for num in ['1002', '1003', '1004']:
            assert accounts_by_number[num]['parameters'] is not None, (
                f"Bank account {num} still has parameters=null"
            )

    def test_no_expense_account_with_null_params(self, template_accounts):
        null_expense = [
            a['Account'] for a in template_accounts
            if a['Account'].startswith('4') and a['parameters'] is None
        ]
        assert not null_expense, (
            f"Expense accounts with parameters=null: {null_expense}"
        )

    def test_no_revenue_account_with_null_params(self, template_accounts):
        null_revenue = [
            a['Account'] for a in template_accounts
            if a['Account'].startswith('8') and a['parameters'] is None
        ]
        assert not null_revenue, (
            f"Revenue accounts with parameters=null: {null_revenue}"
        )

    def test_accounts_without_flags_are_expected(self, template_accounts):
        """Accounts with parameters=null should only be non-flagged accounts."""
        flagged_prefixes = {'4', '8'}
        flagged_specific = {'1002', '1003', '1004'}

        for acct in template_accounts:
            needs_flags = (
                acct['Account'] in flagged_specific
                or acct['Account'][0] in flagged_prefixes
            )
            if needs_flags:
                assert acct['parameters'] is not None, (
                    f"Account {acct['Account']} ({acct['AccountName']}) "
                    f"should have parameters but has null"
                )
