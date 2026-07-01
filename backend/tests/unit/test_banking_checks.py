"""Unit tests for banking_checks.py.

Tests cover:
- _get_opening_balance_date helper
- BankingChecks.check_banking_accounts
- BankingChecks.check_sequence_numbers (basic paths)
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from banking_checks import BankingChecks, _get_opening_balance_date


@pytest.fixture
def mock_db():
    """Create a mock DatabaseManager."""
    return MagicMock()


@pytest.fixture
def checks(mock_db):
    """Create a BankingChecks instance with mocked DB."""
    return BankingChecks(db=mock_db)


# ---------------------------------------------------------------------------
# _get_opening_balance_date
# ---------------------------------------------------------------------------

class TestGetOpeningBalanceDate:
    """Tests for the module-level _get_opening_balance_date function."""

    def test_returns_jan_1_of_next_year_after_closure(self, mock_db):
        mock_db.execute_query.return_value = [{'last_closed_year': 2024}]
        result = _get_opening_balance_date(mock_db, 'TenantA')
        assert result == '2025-01-01'

    def test_returns_none_when_no_closure(self, mock_db):
        mock_db.execute_query.return_value = [{'last_closed_year': None}]
        result = _get_opening_balance_date(mock_db, 'TenantA')
        assert result is None

    def test_returns_none_on_empty_result(self, mock_db):
        mock_db.execute_query.return_value = []
        result = _get_opening_balance_date(mock_db, 'TenantA')
        assert result is None

    def test_returns_none_on_exception(self, mock_db):
        mock_db.execute_query.side_effect = RuntimeError("DB error")
        result = _get_opening_balance_date(mock_db, 'TenantA')
        assert result is None


# ---------------------------------------------------------------------------
# check_banking_accounts
# ---------------------------------------------------------------------------

class TestCheckBankingAccounts:
    """Tests for BankingChecks.check_banking_accounts."""

    def test_returns_empty_when_no_accounts(self, checks, mock_db):
        mock_db.execute_query.return_value = [{'last_closed_year': None}]
        mock_db.get_bank_account_lookups.return_value = []
        result = checks.check_banking_accounts(administration='TenantA')
        assert result == []

    def test_returns_balances_with_last_transaction(self, checks, mock_db):
        # Setup: _get_opening_balance_date returns None
        mock_db.execute_query.side_effect = [
            [{'last_closed_year': None}],  # opening balance query
            [{'Reknum': '1100', 'administration': 'TenantA',
              'calculated_balance': 5000.00, 'account_name': 'Bank'}],  # balance query
            [{'TransactionDate': date(2026, 6, 15),
              'TransactionDescription': 'Payment received',
              'TransactionAmount': 100.00,
              'Debet': '1100', 'Credit': '', 'Ref2': '42',
              'Ref3': '5100.00', 'Ref4': ''}],  # last tx query
        ]
        mock_db.get_bank_account_lookups.return_value = [
            {'Account': '1100', 'rekeningNummer': 'NL80RABO0107936917', 'administration': 'TenantA'}
        ]
        result = checks.check_banking_accounts(administration='TenantA')
        assert len(result) == 1
        assert result[0]['Reknum'] == '1100'
        assert result[0]['calculated_balance'] == 5000.00
        assert result[0]['last_transaction_description'] == 'Payment received'

    def test_handles_no_last_transaction(self, checks, mock_db):
        mock_db.execute_query.side_effect = [
            [{'last_closed_year': None}],
            [{'Reknum': '1100', 'administration': 'TenantA',
              'calculated_balance': 0.00, 'account_name': 'Bank'}],
            [],  # No last transaction
        ]
        mock_db.get_bank_account_lookups.return_value = [
            {'Account': '1100', 'rekeningNummer': 'NL80RABO', 'administration': 'TenantA'}
        ]
        result = checks.check_banking_accounts(administration='TenantA')
        assert result[0]['last_transaction_description'] == 'No transactions found'
        assert result[0]['last_transactions'] == []

    def test_with_end_date(self, checks, mock_db):
        mock_db.execute_query.side_effect = [
            [{'last_closed_year': None}],
            [{'Reknum': '1100', 'administration': 'TenantA',
              'calculated_balance': 3000.00, 'account_name': 'Bank'}],
            [{'TransactionDate': date(2026, 3, 31),
              'TransactionDescription': 'EOQ',
              'TransactionAmount': 50.00,
              'Debet': '1100', 'Credit': '', 'Ref2': '10',
              'Ref3': '', 'Ref4': ''}],
        ]
        mock_db.get_bank_account_lookups.return_value = [
            {'Account': '1100', 'rekeningNummer': 'NL80RABO', 'administration': 'TenantA'}
        ]
        result = checks.check_banking_accounts(
            end_date='2026-03-31', administration='TenantA'
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# check_sequence_numbers
# ---------------------------------------------------------------------------

class TestCheckSequenceNumbers:
    """Tests for BankingChecks.check_sequence_numbers."""

    def test_no_iban_found_returns_error(self, checks, mock_db):
        # _get_opening_balance_date
        mock_db.execute_query.return_value = [{'last_closed_year': None}]
        # Setup cursor mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        mock_cursor.fetchone.return_value = None

        result = checks.check_sequence_numbers(
            account_code='1100', administration='TenantA'
        )
        assert result['success'] is False
        assert 'No IBAN found' in result['message']

    def test_consecutive_sequences_report_no_gaps(self, checks, mock_db):
        mock_db.execute_query.return_value = [{'last_closed_year': None}]
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn

        # IBAN lookup succeeds
        mock_cursor.fetchone.return_value = {'rekeningNummer': 'NL80RABO0107936917'}
        # Sequence query returns consecutive numbers
        mock_cursor.fetchall.return_value = [
            {'Ref2': '1', 'TransactionDate': date(2026, 1, 1)},
            {'Ref2': '2', 'TransactionDate': date(2026, 1, 2)},
            {'Ref2': '3', 'TransactionDate': date(2026, 1, 3)},
        ]

        result = checks.check_sequence_numbers(
            account_code='1100', administration='TenantA'
        )
        assert result['success'] is True
        assert result.get('gaps', []) == []
