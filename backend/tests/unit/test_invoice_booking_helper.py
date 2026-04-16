"""Unit tests for InvoiceBookingHelper."""

import pytest
from unittest.mock import Mock, call
from datetime import date
from services.invoice_booking_helper import InvoiceBookingHelper


# ── Helpers ─────────────────────────────────────────────────

# Default parameter values returned by the mock ParameterService.
# These mirror what a properly configured tenant would have.
_DEFAULT_PARAMS = {
    'debtor_account': '1300',
    'creditor_account': '1600',
    'revenue_account': '8001',
    'expense_account': '4000',
    'btw_debit_account': '2010',
}


def _make_param_svc(overrides: dict = None):
    """Create a mock ParameterService that returns configured account values."""
    params = {**_DEFAULT_PARAMS, **(overrides or {})}

    def _get_param(namespace, key, tenant=None):
        return params.get(key)

    svc = Mock()
    svc.get_param = Mock(side_effect=_get_param)
    return svc


def _make_helper(txn_logic=None, tax_svc=None, param_svc=None):
    db = Mock()
    txn_logic = txn_logic or Mock(save_approved_transactions=Mock(side_effect=lambda t: t))
    tax_svc = tax_svc or Mock(get_tax_rate=Mock(return_value={
        'rate': 21.0, 'ledger_account': '2021',
    }))
    param_svc = param_svc or _make_param_svc()
    return InvoiceBookingHelper(
        db=db, transaction_logic=txn_logic,
        tax_rate_service=tax_svc, parameter_service=param_svc,
    )


def _outgoing_invoice(**overrides):
    base = {
        'invoice_number': 'INV-2026-0001',
        'invoice_type': 'invoice',
        'invoice_date': '2026-04-15',
        'grand_total': 18392.0,
        'vat_total': 3192.0,
        'exchange_rate': 1.0,
        'contact': {'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'},
        'vat_summary': [
            {'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': 15200.0, 'vat_amount': 3192.0},
        ],
    }
    base.update(overrides)
    return base


# ── book_outgoing_invoice ───────────────────────────────────


def test_book_outgoing_invoice_creates_main_and_vat_entries():
    txn_logic = Mock(save_approved_transactions=Mock(side_effect=lambda t: t))
    helper = _make_helper(txn_logic=txn_logic)
    result = helper.book_outgoing_invoice('T1', _outgoing_invoice(),
                                          storage_result={'url': 'https://drive/x', 'filename': 'inv.pdf'})
    assert len(result) == 2  # main + 1 VAT line
    txn_logic.save_approved_transactions.assert_called_once()


def test_book_outgoing_invoice_main_entry_correct_accounts():
    helper = _make_helper()
    result = helper.book_outgoing_invoice('T1', _outgoing_invoice())
    main = result[0]
    assert main['Debet'] == '1300'   # debtor
    assert main['Credit'] == '8001'  # revenue
    assert main['TransactionAmount'] == 18392.0
    assert main['ReferenceNumber'] == 'ACME'
    assert main['Ref2'] == 'INV-2026-0001'


def test_book_outgoing_invoice_vat_entry_uses_tax_rate_ledger():
    tax_svc = Mock(get_tax_rate=Mock(return_value={
        'rate': 21.0, 'ledger_account': '2021',
    }))
    helper = _make_helper(tax_svc=tax_svc)
    result = helper.book_outgoing_invoice('T1', _outgoing_invoice())
    vat = result[1]
    assert vat['Debet'] == '8001'   # revenue account (outgoing VAT debit)
    assert vat['Credit'] == '2021'
    assert vat['TransactionAmount'] == 3192.0


def test_book_outgoing_invoice_stores_pdf_url_in_ref3():
    helper = _make_helper()
    result = helper.book_outgoing_invoice('T1', _outgoing_invoice(),
                                          storage_result={'url': 'https://drive/x', 'filename': 'inv.pdf'})
    assert result[0]['Ref3'] == 'https://drive/x'
    assert result[0]['Ref4'] == 'inv.pdf'


def test_book_outgoing_invoice_skips_zero_vat_entry():
    helper = _make_helper()
    invoice = _outgoing_invoice(vat_summary=[
        {'vat_code': 'zero', 'vat_rate': 0.0, 'base_amount': 500.0, 'vat_amount': 0.0},
    ])
    result = helper.book_outgoing_invoice('T1', invoice)
    assert len(result) == 1  # main only, zero VAT skipped


def test_book_outgoing_invoice_multi_vat_rates_creates_entries_per_rate():
    helper = _make_helper()
    invoice = _outgoing_invoice(
        grand_total=18837.0,
        vat_summary=[
            {'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': 15200.0, 'vat_amount': 3192.0},
            {'vat_code': 'low', 'vat_rate': 9.0, 'base_amount': 500.0, 'vat_amount': 45.0},
        ],
    )
    result = helper.book_outgoing_invoice('T1', invoice)
    assert len(result) == 3  # main + 2 VAT lines


def test_book_outgoing_invoice_multicurrency_converts_amounts():
    helper = _make_helper()
    invoice = _outgoing_invoice(
        grand_total=1000.0,
        exchange_rate=1.1,
        vat_summary=[
            {'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': 826.45, 'vat_amount': 173.55},
        ],
    )
    result = helper.book_outgoing_invoice('T1', invoice)
    assert result[0]['TransactionAmount'] == 1100.0  # 1000 * 1.1
    assert result[1]['TransactionAmount'] == 190.91  # 173.55 * 1.1 rounded


# ── book_incoming_invoice ───────────────────────────────────


def test_book_incoming_invoice_creates_main_and_vat_entries():
    helper = _make_helper()
    invoice = _outgoing_invoice(grand_total=1210.0, vat_total=210.0)
    result = helper.book_incoming_invoice('T1', invoice)
    assert len(result) == 2
    main = result[0]
    assert main['Debet'] == '4000'   # expense
    assert main['Credit'] == '1600'  # creditor


def test_book_incoming_invoice_zero_vat_skips_vat_entry():
    helper = _make_helper()
    invoice = _outgoing_invoice(grand_total=500.0, vat_total=0.0)
    result = helper.book_incoming_invoice('T1', invoice)
    assert len(result) == 1


# ── book_credit_note ────────────────────────────────────────


def test_book_credit_note_reverses_accounts():
    helper = _make_helper()
    cn = _outgoing_invoice(
        invoice_number='CN-2026-0001',
        invoice_type='credit_note',
        grand_total=-18392.0,
        vat_summary=[
            {'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': -15200.0, 'vat_amount': -3192.0},
        ],
    )
    original = _outgoing_invoice()
    result = helper.book_credit_note('T1', cn, original)
    main = result[0]
    # Reversed: debit revenue, credit debtor
    assert main['Debet'] == '8001'
    assert main['Credit'] == '1300'
    assert main['TransactionAmount'] == 18392.0  # absolute value


def test_book_credit_note_vat_reversal_swaps_debit_credit():
    tax_svc = Mock(get_tax_rate=Mock(return_value={
        'rate': 21.0, 'ledger_account': '2021',
    }))
    helper = _make_helper(tax_svc=tax_svc)
    cn = _outgoing_invoice(
        invoice_number='CN-2026-0001',
        grand_total=-18392.0,
        vat_summary=[
            {'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': -15200.0, 'vat_amount': -3192.0},
        ],
    )
    result = helper.book_credit_note('T1', cn, _outgoing_invoice())
    vat = result[1]
    # Reversed: debit vat_ledger, credit btw_debit
    assert vat['Debet'] == '2021'
    assert vat['Credit'] == '2010'


# ── _get_param raises ValueError when not configured ────────


def test_get_param_raises_when_debtor_account_not_configured():
    """_get_param raises ValueError with descriptive message when parameter missing."""
    param_svc = _make_param_svc({'debtor_account': None})
    helper = _make_helper(param_svc=param_svc)
    with pytest.raises(ValueError, match="zzp.debtor_account"):
        helper.book_outgoing_invoice('T1', _outgoing_invoice())


def test_get_param_raises_when_creditor_account_not_configured():
    param_svc = _make_param_svc({'creditor_account': None})
    helper = _make_helper(param_svc=param_svc)
    with pytest.raises(ValueError, match="zzp.creditor_account"):
        helper.book_incoming_invoice('T1', _outgoing_invoice(grand_total=1210.0, vat_total=210.0))


def test_get_param_raises_when_revenue_account_not_configured():
    param_svc = _make_param_svc({'revenue_account': None})
    helper = _make_helper(param_svc=param_svc)
    with pytest.raises(ValueError, match="zzp.revenue_account"):
        helper.book_outgoing_invoice('T1', _outgoing_invoice())


def test_get_param_raises_when_expense_account_not_configured():
    param_svc = _make_param_svc({'expense_account': None})
    helper = _make_helper(param_svc=param_svc)
    with pytest.raises(ValueError, match="zzp.expense_account"):
        helper.book_incoming_invoice('T1', _outgoing_invoice(grand_total=1210.0, vat_total=210.0))


def test_get_param_raises_when_btw_debit_account_not_configured():
    param_svc = _make_param_svc({'btw_debit_account': None})
    helper = _make_helper(param_svc=param_svc)
    with pytest.raises(ValueError, match="zzp.btw_debit_account"):
        helper.book_incoming_invoice('T1', _outgoing_invoice(grand_total=1210.0, vat_total=210.0))


def test_get_param_error_message_includes_tenant_name():
    """Error message includes the tenant identifier for debugging."""
    param_svc = _make_param_svc({'debtor_account': None})
    helper = _make_helper(param_svc=param_svc)
    with pytest.raises(ValueError, match="tenant 'MyTenant'"):
        helper.book_outgoing_invoice('MyTenant', _outgoing_invoice())


def test_get_param_raises_when_parameter_service_is_none():
    """Even without a parameter_service, _get_param raises ValueError (no silent fallback)."""
    helper = _make_helper(param_svc=None)
    helper.parameter_service = None
    with pytest.raises(ValueError, match="zzp.debtor_account"):
        helper.book_outgoing_invoice('T1', _outgoing_invoice())


# ── Custom account values from parameters ───────────────────


def test_book_outgoing_uses_custom_accounts_from_params():
    """When tenant has custom account codes, those are used instead of any default."""
    param_svc = _make_param_svc({
        'debtor_account': '1350',
        'revenue_account': '8100',
    })
    helper = _make_helper(param_svc=param_svc)
    result = helper.book_outgoing_invoice('T1', _outgoing_invoice())
    main = result[0]
    assert main['Debet'] == '1350'
    assert main['Credit'] == '8100'


def test_book_incoming_uses_custom_accounts_from_params():
    param_svc = _make_param_svc({
        'creditor_account': '1650',
        'expense_account': '4100',
        'btw_debit_account': '2015',
    })
    helper = _make_helper(param_svc=param_svc)
    invoice = _outgoing_invoice(grand_total=1210.0, vat_total=210.0)
    result = helper.book_incoming_invoice('T1', invoice)
    main = result[0]
    assert main['Debet'] == '4100'
    assert main['Credit'] == '1650'
    vat = result[1]
    assert vat['Debet'] == '2015'


def test_book_credit_note_uses_custom_accounts_from_params():
    param_svc = _make_param_svc({
        'debtor_account': '1350',
        'revenue_account': '8100',
        'btw_debit_account': '2015',
    })
    helper = _make_helper(param_svc=param_svc)
    cn = _outgoing_invoice(
        invoice_number='CN-2026-0001',
        grand_total=-18392.0,
        vat_summary=[
            {'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': -15200.0, 'vat_amount': -3192.0},
        ],
    )
    result = helper.book_credit_note('T1', cn, _outgoing_invoice())
    main = result[0]
    assert main['Debet'] == '8100'   # revenue (reversed)
    assert main['Credit'] == '1350'  # debtor (reversed)


# ── Invoice-level revenue account override (Req 18) ────────


def test_book_outgoing_uses_invoice_level_revenue_account():
    """When invoice has revenue_account set, use it instead of the tenant parameter."""
    helper = _make_helper()
    invoice = _outgoing_invoice(revenue_account='8010')
    result = helper.book_outgoing_invoice('T1', invoice)
    main = result[0]
    assert main['Credit'] == '8010'  # invoice-level, not default 8001
    vat = result[1]
    assert vat['Debet'] == '8010'    # VAT entry also uses invoice-level revenue


def test_book_outgoing_falls_back_to_param_when_no_invoice_revenue_account():
    """When invoice has no revenue_account, fall back to tenant parameter."""
    helper = _make_helper()
    invoice = _outgoing_invoice()  # no revenue_account key
    result = helper.book_outgoing_invoice('T1', invoice)
    main = result[0]
    assert main['Credit'] == '8001'  # from parameter


def test_book_outgoing_falls_back_when_invoice_revenue_account_is_none():
    """When invoice revenue_account is explicitly None, fall back to parameter."""
    helper = _make_helper()
    invoice = _outgoing_invoice(revenue_account=None)
    result = helper.book_outgoing_invoice('T1', invoice)
    main = result[0]
    assert main['Credit'] == '8001'


def test_book_credit_note_uses_original_invoice_revenue_account():
    """Credit note reversal uses the original invoice's revenue account."""
    helper = _make_helper()
    original = _outgoing_invoice(revenue_account='8010')
    cn = _outgoing_invoice(
        invoice_number='CN-2026-0001',
        invoice_type='credit_note',
        grand_total=-18392.0,
        vat_summary=[
            {'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': -15200.0, 'vat_amount': -3192.0},
        ],
    )
    result = helper.book_credit_note('T1', cn, original)
    main = result[0]
    assert main['Debet'] == '8010'   # original invoice's revenue (reversed)
    assert main['Credit'] == '1300'  # debtor


def test_book_credit_note_falls_back_to_param_when_no_original_revenue_account():
    """When original invoice has no revenue_account, fall back to tenant parameter."""
    helper = _make_helper()
    original = _outgoing_invoice()  # no revenue_account
    cn = _outgoing_invoice(
        invoice_number='CN-2026-0001',
        grand_total=-18392.0,
        vat_summary=[
            {'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': -15200.0, 'vat_amount': -3192.0},
        ],
    )
    result = helper.book_credit_note('T1', cn, original)
    main = result[0]
    assert main['Debet'] == '8001'  # from parameter


def test_book_outgoing_invoice_level_revenue_overrides_custom_param():
    """Invoice-level revenue account takes precedence over custom tenant parameter."""
    param_svc = _make_param_svc({'revenue_account': '8100'})
    helper = _make_helper(param_svc=param_svc)
    invoice = _outgoing_invoice(revenue_account='8200')
    result = helper.book_outgoing_invoice('T1', invoice)
    main = result[0]
    assert main['Credit'] == '8200'  # invoice-level wins over param 8100
    vat = result[1]
    assert vat['Debet'] == '8200'
