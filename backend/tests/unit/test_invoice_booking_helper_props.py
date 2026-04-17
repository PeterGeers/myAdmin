"""
Property-based tests for InvoiceBookingHelper.

Feature: zzp-module
Property 2: Booking entries use invoice-level revenue account
Property 3: Missing required booking parameters raise descriptive errors

Validates: Requirements 18.4, 18.5, 18.6, 19.2, 19.3, 19.5
Reference: .kiro/specs/zzp-module/design-parameter-enhancements.md §14.8
"""

import sys
import os
import pytest
from datetime import date
from unittest.mock import Mock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.invoice_booking_helper import InvoiceBookingHelper


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Account codes: 4-digit numeric strings like real chart-of-accounts entries
account_code_st = st.from_regex(r'[1-9][0-9]{2,4}', fullmatch=True)

# Tenant identifiers
tenant_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='_-'),
    min_size=1, max_size=30,
)

# Client IDs (short alphanumeric codes)
client_id_st = st.text(
    alphabet=st.characters(whitelist_categories=('Lu', 'N')),
    min_size=1, max_size=10,
)

# Invoice numbers like INV-2026-0001 or CN-2026-0001
invoice_number_st = st.from_regex(r'(INV|CN)-20[2-3][0-9]-[0-9]{4}', fullmatch=True)

# Positive monetary amounts (avoid zero for main totals)
positive_amount_st = st.floats(min_value=0.01, max_value=999999.99, allow_nan=False, allow_infinity=False)

# VAT rates commonly used
vat_rate_st = st.sampled_from([0.0, 9.0, 21.0])

# VAT codes
vat_code_st = st.sampled_from(['high', 'low', 'zero'])

# Exchange rates
exchange_rate_st = st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False)

# Invoice dates as valid ISO strings
invoice_date_st = st.dates(
    min_value=date(2020, 1, 1),
    max_value=date(2039, 12, 31),
).map(lambda d: d.isoformat())


# ---------------------------------------------------------------------------
# Composite strategies
# ---------------------------------------------------------------------------

@st.composite
def vat_summary_line_st(draw):
    """Generate a single VAT summary line with consistent amounts."""
    code = draw(vat_code_st)
    rate = {'high': 21.0, 'low': 9.0, 'zero': 0.0}[code]
    base = round(draw(st.floats(min_value=1.0, max_value=50000.0,
                                allow_nan=False, allow_infinity=False)), 2)
    vat_amount = round(base * rate / 100, 2)
    return {
        'vat_code': code,
        'vat_rate': rate,
        'base_amount': base,
        'vat_amount': vat_amount,
    }


@st.composite
def non_empty_vat_summary_st(draw):
    """Generate a VAT summary with at least one non-zero VAT line."""
    lines = draw(st.lists(vat_summary_line_st(), min_size=1, max_size=4))
    # Ensure at least one line has non-zero VAT for meaningful tests
    assume(any(line['vat_amount'] != 0 for line in lines))
    return lines


@st.composite
def outgoing_invoice_st(draw, revenue_account=None):
    """Generate a valid outgoing invoice dict."""
    vat_summary = draw(non_empty_vat_summary_st())
    subtotal = round(sum(l['base_amount'] for l in vat_summary), 2)
    vat_total = round(sum(l['vat_amount'] for l in vat_summary), 2)
    grand_total = round(subtotal + vat_total, 2)

    invoice = {
        'invoice_number': draw(invoice_number_st),
        'invoice_type': 'invoice',
        'invoice_date': draw(invoice_date_st),
        'grand_total': grand_total,
        'vat_total': vat_total,
        'exchange_rate': draw(exchange_rate_st),
        'contact': {
            'id': draw(st.integers(min_value=1, max_value=9999)),
            'client_id': draw(client_id_st),
            'company_name': draw(st.text(min_size=1, max_size=50)),
        },
        'vat_summary': vat_summary,
    }
    if revenue_account is not None:
        invoice['revenue_account'] = revenue_account
    return invoice


@st.composite
def credit_note_st(draw):
    """Generate a valid credit note dict (negated amounts)."""
    vat_summary = draw(non_empty_vat_summary_st())
    subtotal = round(sum(l['base_amount'] for l in vat_summary), 2)
    vat_total = round(sum(l['vat_amount'] for l in vat_summary), 2)
    grand_total = round(subtotal + vat_total, 2)

    return {
        'invoice_number': 'CN-' + draw(st.from_regex(r'20[2-3][0-9]-[0-9]{4}', fullmatch=True)),
        'invoice_type': 'credit_note',
        'invoice_date': draw(invoice_date_st),
        'grand_total': -grand_total,
        'vat_total': -vat_total,
        'exchange_rate': draw(exchange_rate_st),
        'contact': {
            'id': draw(st.integers(min_value=1, max_value=9999)),
            'client_id': draw(client_id_st),
            'company_name': draw(st.text(min_size=1, max_size=50)),
        },
        'vat_summary': [
            {**line, 'base_amount': -line['base_amount'], 'vat_amount': -line['vat_amount']}
            for line in vat_summary
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_param_svc(params: dict):
    """Create a mock ParameterService returning given param values."""
    def _get_param(namespace, key, tenant=None):
        return params.get(key)

    svc = Mock()
    svc.get_param = Mock(side_effect=_get_param)
    return svc


def _make_tax_svc(ledger_account='2021'):
    """Create a mock TaxRateService returning a fixed ledger account."""
    svc = Mock()
    svc.get_tax_rate = Mock(return_value={
        'rate': 21.0,
        'ledger_account': ledger_account,
    })
    return svc


def _make_helper(param_overrides=None, tax_ledger='2021', db_accounts=None):
    """Create an InvoiceBookingHelper with standard mocks.

    Args:
        param_overrides: Override default ParameterService values.
        tax_ledger: Ledger account returned by TaxRateService.
        db_accounts: Dict mapping flag keys to account codes for rekeningschema
                     lookups. E.g. {'zzp_debtor_account': '1300'}.
                     If None, db returns empty (falls through to ParameterService).
    """
    default_params = {
        'debtor_account': '1300',
        'creditor_account': '1600',
        'revenue_account': '8001',
        'expense_account': '4000',
        'btw_debit_account': '2010',
    }
    if param_overrides:
        default_params.update(param_overrides)

    db = Mock()
    # Mock rekeningschema flag lookups: return matching account or empty list
    def _mock_execute_query(query, params=None, **kwargs):
        if db_accounts and 'rekeningschema' in query and 'JSON_EXTRACT' in query:
            # Extract the flag name from the query params (e.g. '$.zzp_debtor_account')
            for p in (params or []):
                if isinstance(p, str) and p.startswith('$.'):
                    flag = p[2:]  # strip '$.'
                    acct = db_accounts.get(flag)
                    if acct:
                        return [{'Account': acct}]
            return []
        return []

    db.execute_query = Mock(side_effect=_mock_execute_query)

    return InvoiceBookingHelper(
        db=db,
        transaction_logic=Mock(save_approved_transactions=Mock(side_effect=lambda t: t)),
        tax_rate_service=_make_tax_svc(tax_ledger),
        parameter_service=_make_param_svc(default_params),
    )


# ---------------------------------------------------------------------------
# Property 2: Booking entries use invoice-level revenue account
# Feature: zzp-module, Property 2: Booking entries use invoice-level revenue account
# Validates: Requirements 18.4, 18.5, 18.6
# ---------------------------------------------------------------------------

class TestBookingUsesInvoiceLevelRevenueAccount:
    """For any outgoing invoice with a revenue_account set, all mutaties entries
    SHALL use that account as credit (main) and debit (VAT), not the global
    zzp.revenue_account parameter. For credit notes, reversal entries SHALL use
    the revenue_account from the original invoice."""

    @settings(max_examples=100)
    @given(
        invoice_revenue=account_code_st,
        param_revenue=account_code_st,
        data=st.data(),
    )
    def test_outgoing_main_entry_uses_invoice_revenue_account(
        self, invoice_revenue, param_revenue, data
    ):
        """Main entry credit account is the invoice-level revenue account (Req 18.4)."""
        assume(invoice_revenue != param_revenue)

        helper = _make_helper(param_overrides={'revenue_account': param_revenue})
        invoice = data.draw(outgoing_invoice_st(revenue_account=invoice_revenue))

        result = helper.book_outgoing_invoice('T1', invoice)

        main_entry = result[0]
        assert main_entry['Credit'] == invoice_revenue, (
            f"Main entry credit should be invoice-level '{invoice_revenue}', "
            f"not param-level '{param_revenue}'"
        )

    @settings(max_examples=100)
    @given(
        invoice_revenue=account_code_st,
        param_revenue=account_code_st,
        data=st.data(),
    )
    def test_outgoing_vat_entries_debit_invoice_revenue_account(
        self, invoice_revenue, param_revenue, data
    ):
        """VAT entry debit account is the invoice-level revenue account (Req 18.5)."""
        assume(invoice_revenue != param_revenue)

        helper = _make_helper(param_overrides={'revenue_account': param_revenue})
        invoice = data.draw(outgoing_invoice_st(revenue_account=invoice_revenue))

        result = helper.book_outgoing_invoice('T1', invoice)

        # Check all VAT entries (entries after the main entry)
        vat_entries = [e for e in result[1:]]
        for vat_entry in vat_entries:
            assert vat_entry['Debet'] == invoice_revenue, (
                f"VAT entry debit should be invoice-level '{invoice_revenue}', "
                f"not param-level '{param_revenue}'"
            )

    @settings(max_examples=100)
    @given(
        invoice_revenue=account_code_st,
        param_revenue=account_code_st,
        data=st.data(),
    )
    def test_outgoing_without_revenue_account_falls_back_to_param(
        self, invoice_revenue, param_revenue, data
    ):
        """When invoice has no revenue_account, fall back to tenant parameter."""
        helper = _make_helper(param_overrides={'revenue_account': param_revenue})
        invoice = data.draw(outgoing_invoice_st(revenue_account=None))
        # Ensure revenue_account key is absent or None
        invoice.pop('revenue_account', None)

        result = helper.book_outgoing_invoice('T1', invoice)

        main_entry = result[0]
        assert main_entry['Credit'] == param_revenue

    @settings(max_examples=100)
    @given(
        original_revenue=account_code_st,
        param_revenue=account_code_st,
        data=st.data(),
    )
    def test_credit_note_uses_original_invoice_revenue_account(
        self, original_revenue, param_revenue, data
    ):
        """Credit note reversal uses the original invoice's revenue account (Req 18.6)."""
        assume(original_revenue != param_revenue)

        helper = _make_helper(param_overrides={'revenue_account': param_revenue})
        cn = data.draw(credit_note_st())
        original = data.draw(outgoing_invoice_st(revenue_account=original_revenue))

        result = helper.book_credit_note('T1', cn, original)

        main_entry = result[0]
        # Credit note reversal: debit = revenue, credit = debtor
        assert main_entry['Debet'] == original_revenue, (
            f"Credit note main debit should be original invoice revenue '{original_revenue}', "
            f"not param-level '{param_revenue}'"
        )

    @settings(max_examples=100)
    @given(
        original_revenue=account_code_st,
        param_revenue=account_code_st,
        data=st.data(),
    )
    def test_credit_note_without_original_revenue_falls_back_to_param(
        self, original_revenue, param_revenue, data
    ):
        """When original invoice has no revenue_account, credit note falls back to param."""
        helper = _make_helper(param_overrides={'revenue_account': param_revenue})
        cn = data.draw(credit_note_st())
        original = data.draw(outgoing_invoice_st(revenue_account=None))
        original.pop('revenue_account', None)

        result = helper.book_credit_note('T1', cn, original)

        main_entry = result[0]
        assert main_entry['Debet'] == param_revenue

    @settings(max_examples=100)
    @given(
        invoice_revenue=account_code_st,
        data=st.data(),
    )
    def test_all_entries_consistently_use_same_revenue_account(
        self, invoice_revenue, data
    ):
        """All entries for an invoice consistently use the same revenue account."""
        helper = _make_helper()
        invoice = data.draw(outgoing_invoice_st(revenue_account=invoice_revenue))

        result = helper.book_outgoing_invoice('T1', invoice)

        main_entry = result[0]
        assert main_entry['Credit'] == invoice_revenue

        for vat_entry in result[1:]:
            assert vat_entry['Debet'] == invoice_revenue, (
                "All VAT entries must use the same revenue account as the main entry"
            )


# ---------------------------------------------------------------------------
# Property 3: Missing required booking parameters raise descriptive errors
# Feature: zzp-module, Property 3: Missing required booking parameters raise descriptive errors
# Validates: Requirements 19.2, 19.3, 19.5
# ---------------------------------------------------------------------------

class TestMissingParamsRaiseDescriptiveErrors:
    """For any tenant where a required booking parameter is not configured,
    calling _get_param() SHALL raise a ValueError naming the missing parameter.
    No hardcoded default SHALL be returned."""

    @settings(max_examples=100)
    @given(tenant=tenant_st)
    def test_missing_debtor_account_raises_with_param_name(self, tenant):
        """Missing zzp.debtor_account raises ValueError naming the parameter (Req 19.2)."""
        helper = _make_helper(param_overrides={'debtor_account': None})

        with pytest.raises(ValueError) as exc_info:
            helper._get_param(tenant, 'debtor_account')

        error_msg = str(exc_info.value)
        assert 'zzp.debtor_account' in error_msg
        assert tenant in error_msg

    @settings(max_examples=100)
    @given(tenant=tenant_st)
    def test_missing_creditor_account_raises_with_param_name(self, tenant):
        """Missing zzp.creditor_account raises ValueError naming the parameter (Req 19.2)."""
        helper = _make_helper(param_overrides={'creditor_account': None})

        with pytest.raises(ValueError) as exc_info:
            helper._get_param(tenant, 'creditor_account')

        error_msg = str(exc_info.value)
        assert 'zzp.creditor_account' in error_msg
        assert tenant in error_msg

    @settings(max_examples=100)
    @given(tenant=tenant_st)
    def test_missing_revenue_account_raises_with_param_name(self, tenant):
        """Missing zzp.revenue_account raises ValueError naming the parameter (Req 19.2)."""
        helper = _make_helper(param_overrides={'revenue_account': None})

        with pytest.raises(ValueError) as exc_info:
            helper._get_param(tenant, 'revenue_account')

        error_msg = str(exc_info.value)
        assert 'zzp.revenue_account' in error_msg
        assert tenant in error_msg

    @settings(max_examples=100)
    @given(
        tenant=tenant_st,
        missing_param=st.sampled_from([
            'debtor_account', 'creditor_account', 'revenue_account',
            'expense_account', 'btw_debit_account',
        ]),
    )
    def test_any_missing_required_param_raises_valueerror(self, tenant, missing_param):
        """Any missing required booking parameter raises ValueError (Req 19.3)."""
        helper = _make_helper(param_overrides={missing_param: None})

        with pytest.raises(ValueError):
            helper._get_param(tenant, missing_param)

    @settings(max_examples=100)
    @given(
        tenant=tenant_st,
        missing_param=st.sampled_from([
            'debtor_account', 'creditor_account', 'revenue_account',
            'expense_account', 'btw_debit_account',
        ]),
    )
    def test_error_message_includes_tenant_identifier(self, tenant, missing_param):
        """Error message includes the tenant name for debugging (Req 19.5)."""
        helper = _make_helper(param_overrides={missing_param: None})

        with pytest.raises(ValueError) as exc_info:
            helper._get_param(tenant, missing_param)

        assert tenant in str(exc_info.value)

    @settings(max_examples=100)
    @given(
        tenant=tenant_st,
        missing_param=st.sampled_from([
            'debtor_account', 'creditor_account', 'revenue_account',
            'expense_account', 'btw_debit_account',
        ]),
    )
    def test_error_message_includes_full_param_path(self, tenant, missing_param):
        """Error message includes the full zzp.* parameter path (Req 19.5)."""
        helper = _make_helper(param_overrides={missing_param: None})

        with pytest.raises(ValueError) as exc_info:
            helper._get_param(tenant, missing_param)

        expected_path = f'zzp.{missing_param}'
        assert expected_path in str(exc_info.value)

    @settings(max_examples=100)
    @given(tenant=tenant_st)
    def test_no_parameter_service_still_raises(self, tenant):
        """Even without a parameter_service, _get_param raises ValueError (Req 19.3)."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        helper = InvoiceBookingHelper(
            db=db,
            transaction_logic=Mock(),
            tax_rate_service=Mock(),
            parameter_service=None,
        )

        with pytest.raises(ValueError):
            helper._get_param(tenant, 'debtor_account')

    @settings(max_examples=100)
    @given(
        tenant=tenant_st,
        missing_param=st.sampled_from([
            'debtor_account', 'creditor_account', 'revenue_account',
            'expense_account', 'btw_debit_account',
        ]),
    )
    def test_empty_string_param_also_raises(self, tenant, missing_param):
        """Empty string parameter value is treated as not configured (Req 19.3)."""
        helper = _make_helper(param_overrides={missing_param: ''})

        with pytest.raises(ValueError):
            helper._get_param(tenant, missing_param)

    @settings(max_examples=100)
    @given(
        tenant=tenant_st,
        account_code=account_code_st,
        param_key=st.sampled_from([
            'debtor_account', 'creditor_account', 'revenue_account',
            'expense_account', 'btw_debit_account',
        ]),
    )
    def test_configured_param_returns_value_no_error(self, tenant, account_code, param_key):
        """When a parameter IS configured, _get_param returns it without error."""
        helper = _make_helper(param_overrides={param_key: account_code})

        result = helper._get_param(tenant, param_key)
        assert result == account_code

    @settings(max_examples=100)
    @given(
        tenant=tenant_st,
        data=st.data(),
    )
    def test_missing_debtor_aborts_outgoing_invoice_booking(self, tenant, data):
        """Outgoing invoice booking fails when debtor_account is missing (Req 19.2)."""
        helper = _make_helper(param_overrides={'debtor_account': None})
        invoice = data.draw(outgoing_invoice_st(revenue_account='8001'))

        with pytest.raises(ValueError, match='zzp.debtor_account'):
            helper.book_outgoing_invoice(tenant, invoice)

    @settings(max_examples=100)
    @given(
        tenant=tenant_st,
        data=st.data(),
    )
    def test_missing_creditor_aborts_incoming_invoice_booking(self, tenant, data):
        """Incoming invoice booking fails when creditor_account is missing (Req 19.2)."""
        helper = _make_helper(param_overrides={'creditor_account': None})
        invoice = data.draw(outgoing_invoice_st(revenue_account='8001'))

        with pytest.raises(ValueError, match='zzp.creditor_account'):
            helper.book_incoming_invoice(tenant, invoice)
