"""
Bug Condition Exploration Tests — Closed Period Transaction Guard

Property 1: Bug Condition — Transactions in closed fiscal years are saved without error

These tests encode the EXPECTED (correct) behavior. They are written BEFORE any fix
and MUST FAIL on unfixed code — failure confirms the bug exists.

DO NOT attempt to fix the test or the code when it fails.

After the fix is implemented, these same tests will PASS, confirming the fix works.

Spec: .kiro/specs/closed-period-transaction-guard
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5

Bug Condition from design:
    isBugCondition(transaction) returns true when
    EXTRACT_YEAR(transaction.TransactionDate) has a matching row in
    year_closure_status for transaction.Administration

Expected behavior (post-fix):
    save_approved_transactions() SHALL raise ClosedPeriodError before any
    database insert occurs, identifying which transactions target closed periods.
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

# Closed year: a year that will exist in year_closure_status
closed_year_st = st.sampled_from([2020, 2021, 2022, 2023])

# Administration / tenant names
admin_st = st.sampled_from(['TenantA', 'TenantB', 'GoodwinSolutions'])

# Day-of-year for generating dates within a closed year
month_st = st.integers(min_value=1, max_value=12)
day_st = st.integers(min_value=1, max_value=28)  # safe for all months

# Transaction amounts (non-zero to avoid the zero-amount skip)
nonzero_amount_st = st.floats(min_value=0.01, max_value=99999.99, allow_nan=False, allow_infinity=False)

# Account numbers
account_st = st.sampled_from(['4000', '4100', '6000', '6200', '8000', '8003'])
credit_account_st = st.sampled_from(['1300', '1600', '2010', '2020'])

# Number of extra open-year transactions in a mixed batch
extra_open_count_st = st.integers(min_value=0, max_value=3)

# Open year (guaranteed not in closed_year_st)
open_year_st = st.sampled_from([2024, 2025, 2026])


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

def build_mock_db_for_transaction_logic(closed_years_for_admin):
    """Build a mock DatabaseManager for TransactionLogic tests.

    Args:
        closed_years_for_admin: dict mapping administration -> set of closed years
            e.g. {'TenantA': {2023}, 'TenantB': {2022, 2023}}

    The mock:
    - execute_query: returns closed year rows when querying year_closure_status
    - transaction(): context manager yielding (cursor, conn) where cursor.execute
      records all INSERT calls (so we can assert no inserts happened)
    """
    mock_db = MagicMock()

    # Track inserts via the transaction context manager
    mock_cursor = MagicMock()
    mock_cursor.lastrowid = 1
    mock_conn = MagicMock()

    @contextmanager
    def mock_transaction(**kwargs):
        yield mock_cursor, mock_conn

    mock_db.transaction = mock_transaction

    # execute_query: simulate year_closure_status lookups
    def mock_execute_query(query, params=None, **kwargs):
        if 'year_closure_status' in query:
            # Extract administration from params
            if params:
                admin = params[0]
                closed = closed_years_for_admin.get(admin, set())
                return [{'year': y} for y in closed]
        return []

    mock_db.execute_query = Mock(side_effect=mock_execute_query)

    return mock_db, mock_cursor


def build_mock_db_for_banking_processor(closed_years_for_admin):
    """Build a mock DatabaseManager for BankingProcessor tests.

    BankingProcessor.save_approved_transactions() uses:
    - db.get_connection() -> conn -> conn.cursor(dictionary=True) for duplicate checks
    - db.insert_transaction() for actual inserts
    - (post-fix) db.execute_query() for year_closure_status lookups
    """
    mock_db = MagicMock()

    # Connection / cursor for duplicate detection
    mock_conn = MagicMock()
    mock_bp_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_bp_cursor
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


# ---------------------------------------------------------------------------
# Test 1: TransactionLogic — closed-year transactions saved without error
# Requirement: 1.1 (approve), 1.2 (outgoing), 1.3 (incoming), 1.4 (credit note)
# ---------------------------------------------------------------------------

class TestTransactionLogicClosedPeriodBugCondition:
    """
    TransactionLogic.save_approved_transactions() SHOULD raise ClosedPeriodError
    when any transaction in the batch has a TransactionDate in a closed fiscal year.

    On UNFIXED code these tests FAIL because transactions are saved without error.
    """

    @settings(max_examples=25)
    @given(
        closed_year=closed_year_st,
        month=month_st,
        day=day_st,
        amount=nonzero_amount_st,
        admin=admin_st,
        debet=account_st,
        credit=credit_account_st,
    )
    def test_single_closed_year_transaction_raises_error(
        self, closed_year, month, day, amount, admin, debet, credit
    ):
        """
        EXPECTED: A single transaction dated in a closed year causes
        ClosedPeriodError. FAILS on unfixed code — transaction is saved.
        """
        from transaction_logic import TransactionLogic

        trans_date = date(closed_year, month, day)
        transaction = make_transaction(trans_date, amount, admin, debet, credit)

        closed_years_for_admin = {admin: {closed_year}}
        mock_db, mock_cursor = build_mock_db_for_transaction_logic(closed_years_for_admin)

        tl = TransactionLogic(test_mode=True)
        tl.db = mock_db

        # Import ClosedPeriodError — it won't exist yet on unfixed code,
        # so we define the expected behavior inline
        try:
            from db_exceptions import ClosedPeriodError
        except ImportError:
            # ClosedPeriodError doesn't exist yet — the test MUST fail
            # because the code can't possibly raise an exception that
            # doesn't exist
            ClosedPeriodError = None

        if ClosedPeriodError is None:
            # ClosedPeriodError not defined yet — call the function and
            # assert it would have raised (it won't, confirming the bug)
            result = tl.save_approved_transactions([transaction])
            # If we get here, the bug is confirmed: transaction was saved
            assert False, (
                f"BUG CONFIRMED: Transaction with date {trans_date} for "
                f"'{admin}' was saved successfully despite year {closed_year} "
                f"being closed. ClosedPeriodError does not exist yet. "
                f"Saved {len(result)} transaction(s)."
            )
        else:
            # ClosedPeriodError exists — verify it's raised
            with pytest.raises(ClosedPeriodError) as exc_info:
                tl.save_approved_transactions([transaction])

            # Verify no inserts occurred
            insert_calls = [
                c for c in mock_cursor.execute.call_args_list
                if 'INSERT' in str(c).upper()
            ]
            assert len(insert_calls) == 0, (
                f"ClosedPeriodError was raised but {len(insert_calls)} INSERT "
                f"statement(s) were executed before the error."
            )

    @settings(max_examples=25)
    @given(
        closed_year=closed_year_st,
        month=month_st,
        day=day_st,
        amount=nonzero_amount_st,
        admin=admin_st,
        extra_count=extra_open_count_st,
        open_year=open_year_st,
    )
    def test_mixed_batch_with_closed_year_rejects_entire_batch(
        self, closed_year, month, day, amount, admin, extra_count, open_year
    ):
        """
        EXPECTED: A batch containing a mix of open-year and closed-year
        transactions is entirely rejected. FAILS on unfixed code — all
        transactions are saved.
        """
        from transaction_logic import TransactionLogic

        # Build batch: one closed-year transaction + N open-year transactions
        closed_date = date(closed_year, month, day)
        transactions = [make_transaction(closed_date, amount, admin)]

        for i in range(extra_count):
            open_date = date(open_year, month, day)
            transactions.append(make_transaction(open_date, amount + i + 1, admin))

        closed_years_for_admin = {admin: {closed_year}}
        mock_db, mock_cursor = build_mock_db_for_transaction_logic(closed_years_for_admin)

        tl = TransactionLogic(test_mode=True)
        tl.db = mock_db

        try:
            from db_exceptions import ClosedPeriodError
        except ImportError:
            ClosedPeriodError = None

        if ClosedPeriodError is None:
            result = tl.save_approved_transactions(transactions)
            assert False, (
                f"BUG CONFIRMED: Mixed batch with {len(transactions)} "
                f"transaction(s) — including one dated {closed_date} in "
                f"closed year {closed_year} for '{admin}' — was saved "
                f"without error. {len(result)} transaction(s) saved. "
                f"ClosedPeriodError does not exist yet."
            )
        else:
            with pytest.raises(ClosedPeriodError):
                tl.save_approved_transactions(transactions)

            # Verify NO inserts at all (entire batch rejected)
            insert_calls = [
                c for c in mock_cursor.execute.call_args_list
                if 'INSERT' in str(c).upper()
            ]
            assert len(insert_calls) == 0, (
                f"Entire batch should be rejected but {len(insert_calls)} "
                f"INSERT(s) were executed."
            )


# ---------------------------------------------------------------------------
# Test 2: BankingProcessor — closed-year transactions saved without error
# Requirement: 1.5
# ---------------------------------------------------------------------------

class TestBankingProcessorClosedPeriodBugCondition:
    """
    BankingProcessor.save_approved_transactions() SHOULD raise ClosedPeriodError
    when any transaction in the batch has a TransactionDate in a closed fiscal year.

    On UNFIXED code these tests FAIL because transactions are saved without error.
    """

    @settings(max_examples=25, deadline=None)
    @given(
        closed_year=closed_year_st,
        month=month_st,
        day=day_st,
        amount=nonzero_amount_st,
        admin=admin_st,
    )
    def test_single_closed_year_banking_transaction_raises_error(
        self, closed_year, month, day, amount, admin
    ):
        """
        EXPECTED: A banking transaction dated in a closed year causes
        ClosedPeriodError. FAILS on unfixed code — transaction is saved.
        """
        from banking_processor import BankingProcessor

        trans_date = date(closed_year, month, day)
        transaction = make_transaction(trans_date, amount, admin)
        # BankingProcessor uses lowercase 'administration' key
        transaction['administration'] = transaction.pop('Administration')

        closed_years_for_admin = {admin: {closed_year}}
        mock_db, mock_bp_cursor = build_mock_db_for_banking_processor(closed_years_for_admin)

        with patch('banking_processor.DatabaseManager', return_value=mock_db):
            bp = BankingProcessor(test_mode=True)
        bp.db = mock_db

        try:
            from db_exceptions import ClosedPeriodError
        except ImportError:
            ClosedPeriodError = None

        if ClosedPeriodError is None:
            saved_count = bp.save_approved_transactions([transaction])
            assert False, (
                f"BUG CONFIRMED: Banking transaction with date {trans_date} "
                f"for '{admin}' was saved successfully despite year "
                f"{closed_year} being closed. ClosedPeriodError does not "
                f"exist yet. saved_count={saved_count}."
            )
        else:
            with pytest.raises(ClosedPeriodError):
                bp.save_approved_transactions([transaction])

            # Verify no inserts occurred
            mock_db.insert_transaction.assert_not_called()

    @settings(max_examples=25, deadline=None)
    @given(
        closed_year=closed_year_st,
        month=month_st,
        day=day_st,
        amount=nonzero_amount_st,
        admin=admin_st,
        extra_count=extra_open_count_st,
        open_year=open_year_st,
    )
    def test_mixed_batch_banking_rejects_entire_batch(
        self, closed_year, month, day, amount, admin, extra_count, open_year
    ):
        """
        EXPECTED: A mixed batch with at least one closed-year transaction
        is entirely rejected. FAILS on unfixed code — all are saved.
        """
        from banking_processor import BankingProcessor

        closed_date = date(closed_year, month, day)
        transactions = [make_transaction(closed_date, amount, admin)]

        for i in range(extra_count):
            open_date = date(open_year, month, day)
            transactions.append(make_transaction(open_date, amount + i + 1, admin))

        # BankingProcessor uses lowercase 'administration' key
        for t in transactions:
            t['administration'] = t.pop('Administration')

        closed_years_for_admin = {admin: {closed_year}}
        mock_db, mock_bp_cursor = build_mock_db_for_banking_processor(closed_years_for_admin)

        with patch('banking_processor.DatabaseManager', return_value=mock_db):
            bp = BankingProcessor(test_mode=True)
        bp.db = mock_db

        try:
            from db_exceptions import ClosedPeriodError
        except ImportError:
            ClosedPeriodError = None

        if ClosedPeriodError is None:
            saved_count = bp.save_approved_transactions(transactions)
            assert False, (
                f"BUG CONFIRMED: Mixed banking batch with "
                f"{len(transactions)} transaction(s) — including one dated "
                f"{closed_date} in closed year {closed_year} for '{admin}' "
                f"— was saved without error. saved_count={saved_count}. "
                f"ClosedPeriodError does not exist yet."
            )
        else:
            with pytest.raises(ClosedPeriodError):
                bp.save_approved_transactions(transactions)

            mock_db.insert_transaction.assert_not_called()
