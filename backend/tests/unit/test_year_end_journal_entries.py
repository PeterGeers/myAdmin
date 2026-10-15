"""Unit tests for YearEndJournalEntryHelper.

High-risk money/journal logic (year-end closure + opening-balance carry-forward).
Covers:
- Closure transaction debit/credit direction for profit vs loss (sign handling)
- Zero net result → no transaction
- Missing-account configuration → ValueError (error path)
- Opening-balance direction for asset (positive) vs liability (negative) balances
- VAT netting (received - paid) direction and primary-account routing
- Tenant scoping: `administration` threaded into every INSERT/SELECT/DELETE
- delete_transactions removes by (administration, TransactionNumber)

These assert the service's ACTUAL behavior (verified against the source), using a
mocked DB cursor — no real connection (unit conftest guard enforces this).

Note on sign convention (from the source docstring): in vw_mutaties Amount is
negative for revenue and positive for expenses, so a NEGATIVE net_result is a
profit and a POSITIVE net_result is a loss. TransactionAmount stored is always
positive.
"""

from unittest.mock import MagicMock

import pytest

from services.year_end_journal_entries import YearEndJournalEntryHelper


ADMIN = "ExampleTenant"


def _account(code):
    """Build the minimal account-info dict the config service returns."""
    return {"Account": code}


@pytest.fixture
def config_service():
    """Mocked YearEndConfigService with account-purpose lookups."""
    svc = MagicMock()
    return svc


@pytest.fixture
def helper(config_service):
    return YearEndJournalEntryHelper(config_service)


def _configure_accounts(config_service, equity="0500", pl_closing="0999"):
    """Default: equity_result and pl_closing accounts are configured."""

    def _lookup(administration, purpose):
        if purpose == "equity_result":
            return _account(equity) if equity else None
        if purpose == "pl_closing":
            return _account(pl_closing) if pl_closing else None
        return None

    config_service.get_account_by_purpose.side_effect = _lookup


# ---------------------------------------------------------------------------
# create_closure_transaction — money direction & signs
# ---------------------------------------------------------------------------

class TestCreateClosureTransaction:
    def test_profit_debits_pl_closing_credits_equity(self, helper, config_service):
        """Negative net_result (profit): Debit P&L-closing, Credit equity, amount=abs."""
        _configure_accounts(config_service, equity="0500", pl_closing="0999")
        cursor = MagicMock()

        tx = helper.create_closure_transaction(ADMIN, 2024, net_result=-1500.0, cursor=cursor)

        assert tx == "YearClose 2024"
        cursor.execute.assert_called_once()
        params = cursor.execute.call_args[0][1]
        # INSERT param order: number, date, desc, amount, debet, credit, ref, admin
        amount, debet, credit = params[3], params[4], params[5]
        assert debet == "0999"  # pl_closing
        assert credit == "0500"  # equity
        assert amount == 1500.0  # always positive
        assert params[-1] == ADMIN  # tenant scoping

    def test_loss_debits_equity_credits_pl_closing(self, helper, config_service):
        """Positive net_result (loss): Debit equity, Credit P&L-closing, amount as-is."""
        _configure_accounts(config_service, equity="0500", pl_closing="0999")
        cursor = MagicMock()

        tx = helper.create_closure_transaction(ADMIN, 2024, net_result=820.50, cursor=cursor)

        assert tx == "YearClose 2024"
        params = cursor.execute.call_args[0][1]
        amount, debet, credit = params[3], params[4], params[5]
        assert debet == "0500"  # equity
        assert credit == "0999"  # pl_closing
        assert amount == 820.50

    def test_zero_net_result_creates_no_transaction(self, helper, config_service):
        """A zero result must not post any journal line."""
        _configure_accounts(config_service)
        cursor = MagicMock()

        tx = helper.create_closure_transaction(ADMIN, 2024, net_result=0, cursor=cursor)

        assert tx is None
        cursor.execute.assert_not_called()

    def test_missing_equity_account_raises(self, helper, config_service):
        """Missing required account configuration → ValueError (abort path)."""
        _configure_accounts(config_service, equity=None, pl_closing="0999")
        cursor = MagicMock()

        with pytest.raises(ValueError, match="Required accounts not configured"):
            helper.create_closure_transaction(ADMIN, 2024, net_result=-100.0, cursor=cursor)
        cursor.execute.assert_not_called()

    def test_missing_pl_closing_account_raises(self, helper, config_service):
        """Missing P&L-closing account → ValueError."""
        _configure_accounts(config_service, equity="0500", pl_closing=None)
        cursor = MagicMock()

        with pytest.raises(ValueError, match="Required accounts not configured"):
            helper.create_closure_transaction(ADMIN, 2024, net_result=50.0, cursor=cursor)

    def test_transaction_date_is_year_end(self, helper, config_service):
        """Closure is dated 31 December of the closed year."""
        _configure_accounts(config_service)
        cursor = MagicMock()

        helper.create_closure_transaction(ADMIN, 2024, net_result=-10.0, cursor=cursor)

        params = cursor.execute.call_args[0][1]
        assert params[1] == "2024-12-31"  # TransactionDate


# ---------------------------------------------------------------------------
# create_opening_balances — carry-forward direction & tenant scoping
# ---------------------------------------------------------------------------

class TestCreateOpeningBalances:
    def _wire_balances(self, helper, balances, vat_accounts=None, vat_primary=None):
        """Patch the private balance/VAT lookups so we test the posting logic."""
        vat_accounts = vat_accounts or set()
        helper._get_ending_balances = MagicMock(return_value=balances)
        helper._is_vat_netting_account = MagicMock(
            side_effect=lambda admin, acct, cur: acct in vat_accounts
        )
        helper._get_vat_primary_account = MagicMock(return_value=vat_primary)

    def test_positive_balance_asset_debits_account_credits_equity(self, helper, config_service):
        """Asset (positive balance): Debit account, Credit equity."""
        _configure_accounts(config_service, equity="0500")
        cursor = MagicMock()
        self._wire_balances(
            helper,
            [{"account": "1000", "account_name": "Bank", "balance": 2500.0}],
        )

        tx = helper.create_opening_balances(ADMIN, 2025, cursor)

        assert tx == "OpeningBalance 2025"
        params = cursor.execute.call_args[0][1]
        amount, debet, credit = params[3], params[4], params[5]
        assert debet == "1000"
        assert credit == "0500"
        assert amount == 2500.0
        assert params[1] == "2025-01-01"  # opening dated 1 Jan
        assert params[-1] == ADMIN

    def test_negative_balance_liability_debits_equity_credits_account(self, helper, config_service):
        """Liability (negative balance): Debit equity, Credit account, amount=abs."""
        _configure_accounts(config_service, equity="0500")
        cursor = MagicMock()
        self._wire_balances(
            helper,
            [{"account": "1600", "account_name": "Creditors", "balance": -900.0}],
        )

        helper.create_opening_balances(ADMIN, 2025, cursor)

        params = cursor.execute.call_args[0][1]
        amount, debet, credit = params[3], params[4], params[5]
        assert debet == "0500"  # equity
        assert credit == "1600"
        assert amount == 900.0  # abs of negative

    def test_equity_account_excluded_as_balancing_account(self, helper, config_service):
        """The equity account itself must not get its own opening-balance line."""
        _configure_accounts(config_service, equity="0500")
        cursor = MagicMock()
        self._wire_balances(
            helper,
            [{"account": "0500", "account_name": "Equity", "balance": 1234.0}],
        )

        tx = helper.create_opening_balances(ADMIN, 2025, cursor)

        # Only the equity balance existed; after filtering it out, nothing posts.
        assert tx is None
        cursor.execute.assert_not_called()

    def test_no_balances_returns_none(self, helper, config_service):
        """No ending balances → nothing to carry forward."""
        _configure_accounts(config_service, equity="0500")
        cursor = MagicMock()
        self._wire_balances(helper, [])

        assert helper.create_opening_balances(ADMIN, 2025, cursor) is None
        cursor.execute.assert_not_called()

    def test_missing_equity_account_raises(self, helper, config_service):
        """Missing equity account → ValueError."""
        _configure_accounts(config_service, equity=None)
        cursor = MagicMock()

        with pytest.raises(ValueError, match="Equity result account not configured"):
            helper.create_opening_balances(ADMIN, 2025, cursor)

    def test_vat_netting_net_debit_routes_to_primary(self, helper, config_service):
        """Net positive VAT (more paid than received → receivable): Debit primary, Credit equity."""
        _configure_accounts(config_service, equity="0500")
        cursor = MagicMock()
        # Two VAT accounts netting to +300 (receivable)
        self._wire_balances(
            helper,
            [
                {"account": "1510", "account_name": "VAT paid", "balance": 500.0},
                {"account": "1520", "account_name": "VAT received", "balance": -200.0},
            ],
            vat_accounts={"1510", "1520"},
            vat_primary="1500",
        )

        helper.create_opening_balances(ADMIN, 2025, cursor)

        # Single netted VAT line expected
        assert cursor.execute.call_count == 1
        params = cursor.execute.call_args[0][1]
        amount, debet, credit = params[3], params[4], params[5]
        assert debet == "1500"  # vat primary
        assert credit == "0500"  # equity
        assert amount == pytest.approx(300.0)

    def test_vat_netting_net_credit_routes_to_primary(self, helper, config_service):
        """Net negative VAT (more received than paid → payable): Debit equity, Credit primary."""
        _configure_accounts(config_service, equity="0500")
        cursor = MagicMock()
        self._wire_balances(
            helper,
            [
                {"account": "1510", "account_name": "VAT paid", "balance": 100.0},
                {"account": "1520", "account_name": "VAT received", "balance": -450.0},
            ],
            vat_accounts={"1510", "1520"},
            vat_primary="1500",
        )

        helper.create_opening_balances(ADMIN, 2025, cursor)

        params = cursor.execute.call_args[0][1]
        amount, debet, credit = params[3], params[4], params[5]
        assert debet == "0500"  # equity
        assert credit == "1500"  # vat primary
        assert amount == pytest.approx(350.0)

    def test_vat_netting_below_threshold_skips_line(self, helper, config_service):
        """A net VAT balance within +/-0.01 is treated as zero and not posted."""
        _configure_accounts(config_service, equity="0500")
        cursor = MagicMock()
        self._wire_balances(
            helper,
            [
                {"account": "1510", "account_name": "VAT paid", "balance": 0.005},
                {"account": "1520", "account_name": "VAT received", "balance": -0.004},
            ],
            vat_accounts={"1510", "1520"},
            vat_primary="1500",
        )

        tx = helper.create_opening_balances(ADMIN, 2025, cursor)

        assert tx is None  # nothing material posted
        cursor.execute.assert_not_called()


# ---------------------------------------------------------------------------
# _get_ending_balances — tenant scoping & float coercion
# ---------------------------------------------------------------------------

class TestGetEndingBalances:
    def test_first_closure_scopes_by_tenant_cumulative(self, helper):
        """No prior OpeningBalance → cumulative query scoped to the tenant."""
        cursor = MagicMock()
        # check_query COUNT = 0 → no opening balance exists
        cursor.fetchone.return_value = {"count": 0}
        cursor.fetchall.return_value = [
            {"account": "1000", "account_name": "Bank", "balance": "150.25"}
        ]

        balances = helper._get_ending_balances(ADMIN, 2024, cursor)

        assert balances == [
            {"account": "1000", "account_name": "Bank", "balance": 150.25}
        ]
        # The COUNT check and the balance query must both pass the tenant first.
        count_params = cursor.execute.call_args_list[0][0][1]
        balance_params = cursor.execute.call_args_list[1][0][1]
        assert count_params[0] == ADMIN
        assert balance_params[0] == ADMIN

    def test_tuple_row_format_coerces_balance_to_float(self, helper):
        """Tuple cursor rows are handled and balance coerced to float."""
        cursor = MagicMock()
        cursor.fetchone.return_value = {"count": 0}
        cursor.fetchall.return_value = [("4000", "Sales", "99.99")]

        balances = helper._get_ending_balances(ADMIN, 2024, cursor)

        assert balances[0]["balance"] == 99.99
        assert isinstance(balances[0]["balance"], float)


# ---------------------------------------------------------------------------
# delete_transactions — tenant-scoped delete
# ---------------------------------------------------------------------------

class TestDeleteTransactions:
    def test_delete_is_scoped_to_tenant_and_number(self, helper):
        cursor = MagicMock()

        helper.delete_transactions(ADMIN, "YearClose 2024", cursor)

        cursor.execute.assert_called_once()
        sql, params = cursor.execute.call_args[0]
        assert "DELETE FROM mutaties" in sql
        assert "administration = %s" in sql
        assert params == [ADMIN, "YearClose 2024"]
