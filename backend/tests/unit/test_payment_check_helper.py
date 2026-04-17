"""Unit tests for PaymentCheckHelper."""

import pytest
from unittest.mock import Mock, call
from services.payment_check_helper import PaymentCheckHelper


def _make_helper(db=None):
    db = db or Mock()
    return PaymentCheckHelper(db=db)


# ── _match_amount ───────────────────────────────────────────


def test_match_amount_exact_within_tolerance_returns_exact():
    assert PaymentCheckHelper._match_amount(121.00, 121.00) == 'exact'


def test_match_amount_exact_at_tolerance_boundary_returns_exact():
    assert PaymentCheckHelper._match_amount(121.005, 121.00) == 'exact'
    assert PaymentCheckHelper._match_amount(120.995, 121.00) == 'exact'


def test_match_amount_over_tolerance_returns_none():
    assert PaymentCheckHelper._match_amount(121.02, 121.00) == 'none'


def test_match_amount_partial_payment_returns_partial():
    assert PaymentCheckHelper._match_amount(60.0, 121.00) == 'partial'


def test_match_amount_zero_payment_returns_none():
    assert PaymentCheckHelper._match_amount(0.0, 121.00) == 'none'


def test_match_amount_overpayment_returns_none():
    assert PaymentCheckHelper._match_amount(200.0, 121.00) == 'none'


# ── run_payment_check ───────────────────────────────────────


def test_run_payment_check_no_open_invoices_returns_zero():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    helper = _make_helper(db=db)
    result = helper.run_payment_check('T1')
    assert result['success'] is True
    assert result['matched'] == 0
    assert result['unmatched'] == 0


def test_run_payment_check_exact_match_marks_paid():
    db = Mock()
    call_count = [0]

    def side_effect(query, params=None, fetch=True, commit=False, pool_type='primary'):
        call_count[0] += 1
        if 'FROM invoices' in query and 'status IN' in query:
            return [{'id': 1, 'invoice_number': 'INV-2026-0001',
                     'grand_total': 121.00, 'status': 'sent',
                     'currency': 'EUR', 'exchange_rate': 1.0,
                     'client_id': 'ACME'}]
        if 'FROM mutaties' in query and 'ReferenceNumber' in query:
            return [{'ID': 99, 'TransactionDate': '2026-05-10',
                     'TransactionAmount': 121.00,
                     'TransactionDescription': 'Betaling ACME'}]
        if 'UPDATE invoices SET status' in query:
            return None
        return []

    db.execute_query = Mock(side_effect=side_effect)
    helper = _make_helper(db=db)
    result = helper.run_payment_check('T1')
    assert result['matched'] == 1
    assert result['details'][0]['match_type'] == 'exact'


def test_run_payment_check_partial_match_keeps_open():
    db = Mock()

    def side_effect(query, params=None, fetch=True, commit=False, pool_type='primary'):
        if 'FROM invoices' in query and 'status IN' in query:
            return [{'id': 1, 'invoice_number': 'INV-2026-0001',
                     'grand_total': 121.00, 'status': 'sent',
                     'currency': 'EUR', 'exchange_rate': 1.0,
                     'client_id': 'ACME'}]
        if 'FROM mutaties' in query and 'ReferenceNumber' in query:
            return [{'ID': 99, 'TransactionDate': '2026-05-10',
                     'TransactionAmount': 60.00,
                     'TransactionDescription': 'Deelbetaling ACME'}]
        return []

    db.execute_query = Mock(side_effect=side_effect)
    helper = _make_helper(db=db)
    result = helper.run_payment_check('T1')
    assert result['partial'] == 1
    assert result['details'][0]['match_type'] == 'partial'


def test_run_payment_check_no_bank_txn_returns_unmatched():
    db = Mock()

    def side_effect(query, params=None, fetch=True, commit=False, pool_type='primary'):
        if 'FROM invoices' in query and 'status IN' in query:
            return [{'id': 1, 'invoice_number': 'INV-2026-0001',
                     'grand_total': 121.00, 'status': 'sent',
                     'currency': 'EUR', 'exchange_rate': 1.0,
                     'client_id': 'ACME'}]
        if 'FROM mutaties' in query:
            return []
        return []

    db.execute_query = Mock(side_effect=side_effect)
    helper = _make_helper(db=db)
    result = helper.run_payment_check('T1')
    assert result['unmatched'] == 1
    assert result['details'][0]['match_type'] == 'none'


def test_run_payment_check_multiple_invoices_mixed_results():
    db = Mock()
    call_idx = [0]

    def side_effect(query, params=None, fetch=True, commit=False, pool_type='primary'):
        if 'FROM invoices' in query and 'status IN' in query:
            return [
                {'id': 1, 'invoice_number': 'INV-0001', 'grand_total': 100.0,
                 'status': 'sent', 'currency': 'EUR', 'exchange_rate': 1.0,
                 'client_id': 'ACME'},
                {'id': 2, 'invoice_number': 'INV-0002', 'grand_total': 200.0,
                 'status': 'overdue', 'currency': 'EUR', 'exchange_rate': 1.0,
                 'client_id': 'KPN'},
            ]
        if 'FROM mutaties' in query and 'ReferenceNumber' in query:
            client = params[1] if params and len(params) > 1 else ''
            if client == 'ACME':
                return [{'ID': 10, 'TransactionDate': '2026-05-01',
                         'TransactionAmount': 100.0,
                         'TransactionDescription': 'Pay ACME'}]
            return []  # KPN has no bank txn
        if 'UPDATE invoices' in query:
            return None
        return []

    db.execute_query = Mock(side_effect=side_effect)
    helper = _make_helper(db=db)
    result = helper.run_payment_check('T1')
    assert result['matched'] == 1
    assert result['unmatched'] == 1
