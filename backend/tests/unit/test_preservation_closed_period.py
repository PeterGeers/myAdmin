"""
Preservation Property Tests — Closed Period Transaction Guard

Property 2: Preservation — Transactions in open fiscal years save identically
to the original function.

These tests are written BEFORE the fix and MUST PASS on UNFIXED code.
They establish the baseline behavior that must be preserved after the fix.

After the fix is implemented, these same tests MUST STILL PASS, confirming
no regressions were introduced.

Spec: .kiro/specs/closed-period-transaction-guard
**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

Preservation scope from design:
    All inputs where NO transaction in the batch has a TransactionDate in a
    closed fiscal year should be completely unaffected by the fix. This includes:
    - All transactions with dates in years not present in year_closure_status
    - All transactions when year_closure_status has no entries for the tenant
    - Zero-amount transactions (skipped before the guard applies)
"""

import sys
import os
import pytest
from datetime import date
from unittest.mock import Mock, MagicMock, patch, call
from contextlib import contextmanager
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Open years: guaranteed NOT in the closed_year_st used by bug condition tests
open_year_st = st.sampled_from([2024, 2025, 2026])

# Administration / tenant names
admin_st = st.sampled_from(['TenantA', 'TenantB', 'GoodwinSolutions'])

# Day-of-year for generating dates
month_st = st.integers(min_value=1, max_value=12)
day_st = st.integers(min_value=1, max_value=28)  # safe for all months

# Transaction amounts — non-zero
nonzero_amount_st = st.floats(
    min_value=0.01, max_value=99999.99,
    allow_nan=False, allow_infinity=False,
)

# Zero amounts (for zero-amount skipping tests)
zero_amount_st = st.just(0.0)

# Account numbers
account_st = st.sampled_from(['4000', '4100', '6000', '6200', '8000', '8003'])
credit_account_st = st.sampled_from(['1300', '1600', '2010', '2020'])

# Batch sizes for multi-transaction tests
batch_size_st = st.integers(min_value=1, max_value=5)

# Closed years that exist in year_closure_status for OTHER tenants (not the
# tenant under test). This lets us verify tenant isolation.
other_closed_year_st = st.sampled_from([2020, 2021, 2022, 2023])


def make_transaction(trans_date, amount, admin, debet='4000', credit='1300'):
    """Helper to build a transaction dict matching the expected schema."""
    return {
        'TransactionNumber': f'Test-{trans_date}',
        'TransactionDate': str(trans_date),
        'TransactionDescription': f'Test transaction {trans_date}',
        'TransactionAmount': amount,
        'Debet': debet,
        'Credit': credit,
        'ReferenceNumber': 'TestRef',
        'Ref1': '',
        'Ref2': '',
        'Ref3': '',
        'Ref4': '',
        'Administration': admin,
    }


# ---------------------------------------------------------------------------
# Helpers for mocking DatabaseManager
# ---------------------------------------------------------------------------

def build_mock_db_for_transaction_logic(closed_years_for_admin=None):
    """Build a mock DatabaseManager for TransactionLogic tests.

    Args:
        closed_years_for_admin: dict mapping administration -> set of closed years.
            Defaults to empty dict (no closed years for any tenant).
    """
    if closed_years_for_admin is None:
        closed_years_for_admin = {}

    mock_db = MagicMock()

    # Track inserts via the transaction context manager
    mock_cursor = MagicMock()
    # Simulate auto-increment IDs
    _id_counter = [0]

    def _lastrowid_side_effect():
        _id_counter[0] += 1
        return _id_counter[0]

    type(mock_cursor).lastrowid = property(lambda self: _lastrowid_side_effect())
    mock_conn = MagicMock()

    @contextmanager
    def mock_transaction(**kwargs):
        yield mock_cursor, mock_conn

    mock_db.transaction = mock_transaction

    # execute_query: simulate year_closure_status lookups
    def mock_execute_query(query, params=None, **kwargs):
        if 'year_closure_status' in query:
            if params:
                admin = params[0]
                closed = closed_years_for_admin.get(admin, set())
                return [{'year': y} for y in closed]
        return []

    mock_db.execute_query = Mock(side_effect=mock_execute_query)

    return mock_db, mock_cursor


def build_mock_db_for_banking_processor(closed_years_for_admin=None,
                                         duplicate_ids=None):
    """Build a mock DatabaseManager for BankingProcessor tests.

    Args:
        closed_years_for_admin: dict mapping administration -> set of closed years.
            Defaults to empty dict (no closed years for any tenant).
        duplicate_ids: list of transaction IDs to return as duplicates.
            Defaults to empty (no duplicates).
    """
    if closed_years_for_admin is None:
        closed_years_for_admin = {}

    mock_db = MagicMock()

    # Connection / cursor for duplicate detection
    mock_conn = MagicMock()
    mock_bp_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_bp_cursor

    if duplicate_ids:
        # Return duplicate rows on first fetchall, then empty for subsequent
        mock_bp_cursor.fetchall.return_value = [{'ID': did} for did in duplicate_ids]
        # fetchone returns matching description for normalization check
        mock_bp_cursor.fetchone.return_value = {'TransactionDescription': 'Test transaction'}
    else:
        # No duplicates found
        mock_bp_cursor.fetchall.return_value = []
        mock_bp_cursor.fetchone.return_value = None

    mock_db.get_connection.return_value = mock_conn

    # insert_transaction: track calls
    mock_db.insert_transaction = MagicMock()

    # execute_query: simulate year_closure_status lookups
    def mock_execute_query(query, params=None, **kwargs):
        if 'year_closure_status' in query:
            if params:
                admin = params[0]
                closed = closed_years_for_admin.get(admin, set())
                return [{'year': y} for y in closed]
        return []

    mock_db.execute_query = Mock(side_effect=mock_execute_query)

    return mock_db, mock_bp_cursor


# ===========================================================================
# Test Suite 1: TransactionLogic — Open-year transactions save successfully
# Validates: Requirements 3.1, 3.2, 3.4, 3.5
# ===========================================================================

class TestTransactionLogicPreservation:
    """
    TransactionLogic.save_approved_transactions() with transactions dated in
    open fiscal years (no matching year_closure_status entry) MUST save all
    non-zero-amount transactions and return the saved list.

    These tests PASS on UNFIXED code and MUST continue to pass after the fix.
    """

    @settings(max_examples=30)
    @given(
        year=open_year_st,
        month=month_st,
        day=day_st,
        amount=nonzero_amount_st,
        admin=admin_st,
        debet=account_st,
        credit=credit_account_st,
    )
    def test_single_open_year_transaction_saves_successfully(
        self, year, month, day, amount, admin, debet, credit
    ):
        """
        **Validates: Requirements 3.1, 3.2**

        A single non-zero-amount transaction dated in an open year saves
        successfully and is returned in the saved list.
        """
        from transaction_logic import TransactionLogic

        trans_date = date(year, month, day)
        transaction = make_transaction(trans_date, amount, admin, debet, credit)

        # No closed years for this admin
        mock_db, mock_cursor = build_mock_db_for_transaction_logic(
            closed_years_for_admin={}
        )

        tl = TransactionLogic(test_mode=True)
        tl.db = mock_db

        result = tl.save_approved_transactions([transaction])

        # Property: exactly 1 transaction saved
        assert len(result) == 1, (
            f"Expected 1 saved transaction, got {len(result)} for "
            f"open-year date {trans_date}"
        )

        # Property: the saved transaction has an ID assigned
        assert result[0].get('ID') is not None, (
            "Saved transaction should have an ID assigned from cursor.lastrowid"
        )

        # Property: INSERT was executed exactly once
        insert_calls = [
            c for c in mock_cursor.execute.call_args_list
            if 'INSERT' in str(c).upper()
        ]
        assert len(insert_calls) == 1, (
            f"Expected 1 INSERT call, got {len(insert_calls)}"
        )

    @settings(max_examples=30)
    @given(
        year=open_year_st,
        month=month_st,
        day=day_st,
        admin=admin_st,
        batch_size=batch_size_st,
        amounts=st.lists(
            nonzero_amount_st, min_size=1, max_size=5
        ),
    )
    def test_batch_open_year_transactions_all_save(
        self, year, month, day, admin, batch_size, amounts
    ):
        """
        **Validates: Requirements 3.1, 3.2**

        A batch of non-zero-amount transactions all dated in open years
        saves all of them. The returned list length equals the batch size.
        """
        from transaction_logic import TransactionLogic

        transactions = []
        for amt in amounts:
            trans_date = date(year, month, day)
            transactions.append(make_transaction(trans_date, amt, admin))

        mock_db, mock_cursor = build_mock_db_for_transaction_logic(
            closed_years_for_admin={}
        )

        tl = TransactionLogic(test_mode=True)
        tl.db = mock_db

        result = tl.save_approved_transactions(transactions)

        # Property: all non-zero transactions saved
        assert len(result) == len(amounts), (
            f"Expected {len(amounts)} saved transactions, got {len(result)}"
        )

        # Property: number of INSERT calls matches batch size
        insert_calls = [
            c for c in mock_cursor.execute.call_args_list
            if 'INSERT' in str(c).upper()
        ]
        assert len(insert_calls) == len(amounts), (
            f"Expected {len(amounts)} INSERT calls, got {len(insert_calls)}"
        )

    @settings(max_examples=30)
    @given(
        year=open_year_st,
        month=month_st,
        day=day_st,
        admin=admin_st,
        debet=account_st,
        credit=credit_account_st,
    )
    def test_zero_amount_transactions_skipped(
        self, year, month, day, admin, debet, credit
    ):
        """
        **Validates: Requirements 3.4**

        Zero-amount transactions are always skipped regardless of date.
        They are never included in the saved results.
        """
        from transaction_logic import TransactionLogic

        trans_date = date(year, month, day)
        zero_transaction = make_transaction(trans_date, 0.0, admin, debet, credit)

        mock_db, mock_cursor = build_mock_db_for_transaction_logic(
            closed_years_for_admin={}
        )

        tl = TransactionLogic(test_mode=True)
        tl.db = mock_db

        result = tl.save_approved_transactions([zero_transaction])

        # Property: zero-amount transaction is skipped
        assert len(result) == 0, (
            f"Expected 0 saved transactions for zero-amount, got {len(result)}"
        )

        # Property: no INSERT calls made
        insert_calls = [
            c for c in mock_cursor.execute.call_args_list
            if 'INSERT' in str(c).upper()
        ]
        assert len(insert_calls) == 0, (
            f"Expected 0 INSERT calls for zero-amount, got {len(insert_calls)}"
        )

    @settings(max_examples=30)
    @given(
        year=open_year_st,
        month=month_st,
        day=day_st,
        nonzero_amount=nonzero_amount_st,
        admin=admin_st,
    )
    def test_mixed_zero_and_nonzero_amounts(
        self, year, month, day, nonzero_amount, admin
    ):
        """
        **Validates: Requirements 3.1, 3.4**

        A batch with both zero and non-zero amounts: only non-zero
        transactions are saved. Zero-amount ones are silently skipped.
        """
        from transaction_logic import TransactionLogic

        trans_date = date(year, month, day)
        transactions = [
            make_transaction(trans_date, nonzero_amount, admin),
            make_transaction(trans_date, 0.0, admin),
            make_transaction(trans_date, nonzero_amount + 1, admin),
        ]

        mock_db, mock_cursor = build_mock_db_for_transaction_logic(
            closed_years_for_admin={}
        )

        tl = TransactionLogic(test_mode=True)
        tl.db = mock_db

        result = tl.save_approved_transactions(transactions)

        # Property: only non-zero transactions saved (2 out of 3)
        assert len(result) == 2, (
            f"Expected 2 saved transactions (skipping zero-amount), "
            f"got {len(result)}"
        )

    @settings(max_examples=30)
    @given(
        year=open_year_st,
        month=month_st,
        day=day_st,
        amount=nonzero_amount_st,
        admin=admin_st,
        other_closed_year=other_closed_year_st,
    )
    def test_no_closed_years_for_tenant_all_save(
        self, year, month, day, amount, admin, other_closed_year
    ):
        """
        **Validates: Requirements 3.5**

        When year_closure_status has no entries for the tenant (but may have
        entries for OTHER tenants), all non-zero transactions save normally.
        """
        from transaction_logic import TransactionLogic

        trans_date = date(year, month, day)
        transaction = make_transaction(trans_date, amount, admin)

        # Closed years exist for a DIFFERENT admin, not the one under test
        other_admin = 'OtherTenant'
        assume(other_admin != admin)

        mock_db, mock_cursor = build_mock_db_for_transaction_logic(
            closed_years_for_admin={other_admin: {other_closed_year}}
        )

        tl = TransactionLogic(test_mode=True)
        tl.db = mock_db

        result = tl.save_approved_transactions([transaction])

        # Property: transaction saves successfully
        assert len(result) == 1, (
            f"Expected 1 saved transaction when no closed years for "
            f"'{admin}', got {len(result)}"
        )


# ===========================================================================
# Test Suite 2: BankingProcessor — Open-year transactions save successfully
# Validates: Requirements 3.3, 3.4, 3.5
# ===========================================================================

class TestBankingProcessorPreservation:
    """
    BankingProcessor.save_approved_transactions() with transactions dated in
    open fiscal years MUST save and return count. Duplicate detection still works.

    These tests PASS on UNFIXED code and MUST continue to pass after the fix.
    """

    @settings(max_examples=30, deadline=None)
    @given(
        year=open_year_st,
        month=month_st,
        day=day_st,
        amount=nonzero_amount_st,
        admin=admin_st,
    )
    def test_single_open_year_banking_transaction_saves(
        self, year, month, day, amount, admin
    ):
        """
        **Validates: Requirements 3.3**

        A single non-zero-amount banking transaction dated in an open year
        saves successfully and returns saved_count = 1.
        """
        from banking_processor import BankingProcessor

        trans_date = date(year, month, day)
        transaction = make_transaction(trans_date, amount, admin)
        # BankingProcessor uses lowercase 'administration' key
        transaction['administration'] = transaction.pop('Administration')

        mock_db, mock_bp_cursor = build_mock_db_for_banking_processor(
            closed_years_for_admin={}
        )

        with patch('banking_processor.DatabaseManager', return_value=mock_db):
            bp = BankingProcessor(test_mode=True)
        bp.db = mock_db

        saved_count = bp.save_approved_transactions([transaction])

        # Property: exactly 1 transaction saved
        assert saved_count == 1, (
            f"Expected saved_count=1 for open-year banking transaction, "
            f"got {saved_count}"
        )

        # Property: insert_transaction was called once
        assert mock_db.insert_transaction.call_count == 1, (
            f"Expected 1 insert_transaction call, got "
            f"{mock_db.insert_transaction.call_count}"
        )

    @settings(max_examples=30, deadline=None)
    @given(
        year=open_year_st,
        month=month_st,
        day=day_st,
        admin=admin_st,
        amounts=st.lists(
            nonzero_amount_st, min_size=1, max_size=5
        ),
    )
    def test_batch_open_year_banking_transactions_all_save(
        self, year, month, day, admin, amounts
    ):
        """
        **Validates: Requirements 3.3**

        A batch of non-zero-amount banking transactions all dated in open
        years saves all of them. saved_count equals the batch size.
        """
        from banking_processor import BankingProcessor

        transactions = []
        for amt in amounts:
            trans_date = date(year, month, day)
            t = make_transaction(trans_date, amt, admin)
            t['administration'] = t.pop('Administration')
            transactions.append(t)

        mock_db, mock_bp_cursor = build_mock_db_for_banking_processor(
            closed_years_for_admin={}
        )

        with patch('banking_processor.DatabaseManager', return_value=mock_db):
            bp = BankingProcessor(test_mode=True)
        bp.db = mock_db

        saved_count = bp.save_approved_transactions(transactions)

        # Property: all transactions saved
        assert saved_count == len(amounts), (
            f"Expected saved_count={len(amounts)}, got {saved_count}"
        )

    @settings(max_examples=30, deadline=None)
    @given(
        year=open_year_st,
        month=month_st,
        day=day_st,
        admin=admin_st,
    )
    def test_zero_amount_banking_transactions_skipped(
        self, year, month, day, admin
    ):
        """
        **Validates: Requirements 3.4**

        Zero-amount banking transactions are always skipped regardless of date.
        """
        from banking_processor import BankingProcessor

        trans_date = date(year, month, day)
        transaction = make_transaction(trans_date, 0.0, admin)
        transaction['administration'] = transaction.pop('Administration')

        mock_db, mock_bp_cursor = build_mock_db_for_banking_processor(
            closed_years_for_admin={}
        )

        with patch('banking_processor.DatabaseManager', return_value=mock_db):
            bp = BankingProcessor(test_mode=True)
        bp.db = mock_db

        saved_count = bp.save_approved_transactions([transaction])

        # Property: zero-amount transaction skipped
        assert saved_count == 0, (
            f"Expected saved_count=0 for zero-amount banking transaction, "
            f"got {saved_count}"
        )

        # Property: no insert_transaction calls
        assert mock_db.insert_transaction.call_count == 0, (
            f"Expected 0 insert_transaction calls, got "
            f"{mock_db.insert_transaction.call_count}"
        )

    @settings(max_examples=30, deadline=None)
    @given(
        year=open_year_st,
        month=month_st,
        day=day_st,
        amount=nonzero_amount_st,
        admin=admin_st,
    )
    def test_duplicate_detection_queries_existing_for_open_year(
        self, year, month, day, amount, admin
    ):
        """
        **Validates: Requirements 3.3**

        BankingProcessor duplicate detection queries for existing transactions
        in open years. The duplicate check SELECT is executed before any insert.
        Note: The current code's `continue` only breaks the inner loop over
        existing rows, so the transaction is still saved — this test preserves
        that actual behavior.
        """
        from banking_processor import BankingProcessor

        trans_date = date(year, month, day)
        transaction = make_transaction(trans_date, amount, admin)
        transaction['administration'] = transaction.pop('Administration')

        # Set up mock with no duplicates — clean save path
        mock_db, mock_bp_cursor = build_mock_db_for_banking_processor(
            closed_years_for_admin={},
            duplicate_ids=None,
        )

        with patch('banking_processor.DatabaseManager', return_value=mock_db):
            bp = BankingProcessor(test_mode=True)
        bp.db = mock_db

        saved_count = bp.save_approved_transactions([transaction])

        # Property: transaction saved when no duplicate found
        assert saved_count == 1, (
            f"Expected saved_count=1 when no duplicate, got {saved_count}"
        )

        # Property: duplicate check SELECT was executed (cursor.execute called)
        select_calls = [
            c for c in mock_bp_cursor.execute.call_args_list
            if 'SELECT' in str(c).upper()
        ]
        assert len(select_calls) >= 1, (
            f"Expected at least 1 SELECT call for duplicate check, got "
            f"{len(select_calls)}"
        )

    @settings(max_examples=30, deadline=None)
    @given(
        year=open_year_st,
        month=month_st,
        day=day_st,
        amount=nonzero_amount_st,
        admin=admin_st,
        other_closed_year=other_closed_year_st,
    )
    def test_no_closed_years_for_tenant_banking_saves(
        self, year, month, day, amount, admin, other_closed_year
    ):
        """
        **Validates: Requirements 3.5**

        When year_closure_status has no entries for the tenant, all non-zero
        banking transactions save normally.
        """
        from banking_processor import BankingProcessor

        trans_date = date(year, month, day)
        transaction = make_transaction(trans_date, amount, admin)
        transaction['administration'] = transaction.pop('Administration')

        # Closed years exist for a DIFFERENT admin
        other_admin = 'OtherTenant'
        assume(other_admin != admin)

        mock_db, mock_bp_cursor = build_mock_db_for_banking_processor(
            closed_years_for_admin={other_admin: {other_closed_year}}
        )

        with patch('banking_processor.DatabaseManager', return_value=mock_db):
            bp = BankingProcessor(test_mode=True)
        bp.db = mock_db

        saved_count = bp.save_approved_transactions([transaction])

        # Property: transaction saves successfully
        assert saved_count == 1, (
            f"Expected saved_count=1 when no closed years for '{admin}', "
            f"got {saved_count}"
        )
