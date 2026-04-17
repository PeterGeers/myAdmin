"""
Property-based tests for ZZPInvoiceService.send_invoice() strict send flow.

Feature: zzp-module
Property 6: Storage result flows to Ref3/Ref4 on mutaties
Property 7: Storage failure aborts send flow
Property 8: Email failure is soft failure

Validates: Requirements 22.2, 22.3, 22.4, 22.5, 22.6
Reference: .kiro/specs/zzp-module/design-parameter-enhancements.md §14.8
"""

import sys
import os
import pytest
from io import BytesIO
from datetime import date
from unittest.mock import Mock, MagicMock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.zzp_invoice_service import ZZPInvoiceService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

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

# Invoice numbers like INV-2026-0001
invoice_number_st = st.from_regex(r'INV-20[2-3][0-9]-[0-9]{4}', fullmatch=True)

# Credit note numbers like CN-2026-0001
cn_number_st = st.from_regex(r'CN-20[2-3][0-9]-[0-9]{4}', fullmatch=True)

# Storage URLs (non-empty strings representing valid URLs)
storage_url_st = st.from_regex(
    r'https://[a-z]+\.[a-z]+\.[a-z]+/file/[a-z0-9]{6,20}',
    fullmatch=True,
)

# VAT codes and rates
vat_code_st = st.sampled_from(['high', 'low', 'zero'])

# Positive monetary amounts
positive_amount_st = st.floats(
    min_value=0.01, max_value=999999.99,
    allow_nan=False, allow_infinity=False,
)

# Exchange rates
exchange_rate_st = st.floats(
    min_value=0.01, max_value=10.0,
    allow_nan=False, allow_infinity=False,
)

# Invoice dates as valid ISO strings
invoice_date_st = st.dates(
    min_value=date(2020, 1, 1),
    max_value=date(2039, 12, 31),
).map(lambda d: d.isoformat())

# Revenue account codes
account_code_st = st.from_regex(r'[1-9][0-9]{2,4}', fullmatch=True)

# Error messages for storage/email failures
error_message_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
    min_size=1, max_size=100,
)


# ---------------------------------------------------------------------------
# Composite strategies
# ---------------------------------------------------------------------------

@st.composite
def vat_summary_line_st(draw):
    """Generate a single VAT summary line with consistent amounts."""
    code = draw(vat_code_st)
    rate = {'high': 21.0, 'low': 9.0, 'zero': 0.0}[code]
    base = round(draw(st.floats(
        min_value=1.0, max_value=50000.0,
        allow_nan=False, allow_infinity=False,
    )), 2)
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
    assume(any(line['vat_amount'] != 0 for line in lines))
    return lines


@st.composite
def draft_invoice_st(draw, invoice_type='invoice'):
    """Generate a valid draft invoice dict as returned by get_invoice."""
    vat_summary = draw(non_empty_vat_summary_st())
    subtotal = round(sum(l['base_amount'] for l in vat_summary), 2)
    vat_total = round(sum(l['vat_amount'] for l in vat_summary), 2)
    grand_total = round(subtotal + vat_total, 2)
    inv_number = draw(invoice_number_st if invoice_type == 'invoice' else cn_number_st)
    cid = draw(client_id_st)

    invoice = {
        'id': draw(st.integers(min_value=1, max_value=9999)),
        'administration': draw(tenant_st),
        'invoice_number': inv_number,
        'invoice_type': invoice_type,
        'contact_id': draw(st.integers(min_value=1, max_value=9999)),
        'invoice_date': draw(invoice_date_st),
        'due_date': draw(invoice_date_st),
        'payment_terms_days': 30,
        'currency': 'EUR',
        'exchange_rate': draw(exchange_rate_st),
        'status': 'draft',
        'subtotal': subtotal,
        'vat_total': vat_total,
        'grand_total': grand_total,
        'notes': None,
        'original_invoice_id': None,
        'sent_at': None,
        'created_by': 'test',
        'created_at': None,
        'updated_at': None,
        'revenue_account': draw(account_code_st),
        'contact': {
            'id': draw(st.integers(min_value=1, max_value=9999)),
            'client_id': cid,
            'company_name': draw(st.text(min_size=1, max_size=50)),
        },
        'lines': [{
            'id': 1,
            'description': 'Service',
            'product_id': None,
            'quantity': 10,
            'unit_price': 100,
            'vat_code': 'high',
            'vat_rate': 21,
            'vat_amount': 210,
            'line_total': 1000,
            'sort_order': 0,
        }],
        'vat_summary': vat_summary,
    }
    if invoice_type == 'credit_note':
        invoice['original_invoice_id'] = draw(
            st.integers(min_value=10000, max_value=19999)
        )
    return invoice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service_and_mocks(invoice, storage_url='https://drive.google.com/file/abc123',
                             health_ok=True, health_reason=None,
                             email_success=True, storage_exception=None,
                             email_exception=None):
    """Build a ZZPInvoiceService with mocks that return the given invoice.

    The service's get_invoice is patched to return the provided invoice dict
    directly, avoiding complex DB mock setup.
    """
    db = Mock()
    # _update_status calls
    db.execute_query = Mock(return_value=None)

    pdf_gen = Mock(
        generate_invoice_pdf=Mock(return_value=BytesIO(b'%PDF-fake')),
    )

    # Booking helper that captures the transactions it creates
    booking = Mock()
    booking.book_outgoing_invoice = Mock(return_value=[
        {
            'Ref3': storage_url,
            'Ref4': f"{invoice['invoice_number']}.pdf",
            'ReferenceNumber': invoice.get('contact', {}).get('client_id', ''),
            'Ref2': invoice['invoice_number'],
        }
    ])
    booking.book_credit_note = Mock(return_value=[
        {
            'Ref3': storage_url,
            'Ref4': f"{invoice['invoice_number']}.pdf",
            'ReferenceNumber': invoice.get('contact', {}).get('client_id', ''),
            'Ref2': invoice['invoice_number'],
        }
    ])

    email_svc = Mock()
    if email_exception:
        email_svc.send_invoice_email = Mock(side_effect=email_exception)
    else:
        email_svc.send_invoice_email = Mock(return_value={
            'success': email_success,
            'error': 'SES rejected' if not email_success else None,
        })

    output_svc = Mock()
    output_svc.check_health = Mock(return_value={
        'healthy': health_ok,
        'reason': health_reason or ('OK' if health_ok else 'Connection refused'),
    })
    if storage_exception:
        output_svc.handle_output = Mock(side_effect=storage_exception)
    else:
        output_svc.handle_output = Mock(return_value={
            'url': storage_url,
        })

    param_svc = Mock(get_param=Mock(return_value=None))

    svc = ZZPInvoiceService(
        db=db,
        pdf_generator=pdf_gen,
        booking_helper=booking,
        email_service=email_svc,
        parameter_service=param_svc,
    )

    # Patch get_invoice to return our generated invoice directly
    svc.get_invoice = Mock(return_value=invoice)

    return svc, {
        'db': db,
        'pdf_gen': pdf_gen,
        'booking': booking,
        'email_svc': email_svc,
        'output_svc': output_svc,
        'param_svc': param_svc,
    }


# ---------------------------------------------------------------------------
# Property 6: Storage result flows to Ref3/Ref4 on mutaties
# Feature: zzp-module, Property 6: Storage result flows to Ref3/Ref4 on mutaties
# Validates: Requirements 22.2, 22.3, 22.4
# ---------------------------------------------------------------------------

class TestStorageResultFlowsToRef3Ref4:
    """For any invoice or credit note that is successfully sent, all
    corresponding mutaties entries SHALL have Ref3 set to the storage URL
    and Ref4 set to the PDF filename from the storage result."""

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_outgoing_invoice_booking_receives_storage_url(
        self, data, storage_url,
    ):
        """book_outgoing_invoice is called with storage_result containing
        the URL from OutputService (Req 22.2, 22.4)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(invoice, storage_url=storage_url)

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': False},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is True
        call_args = mocks['booking'].book_outgoing_invoice.call_args
        sr = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs.get('storage_result')
        assert sr is not None
        assert sr['url'] == storage_url

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_outgoing_invoice_booking_receives_correct_filename(
        self, data, storage_url,
    ):
        """book_outgoing_invoice is called with storage_result containing
        the PDF filename matching the invoice number (Req 22.2)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(invoice, storage_url=storage_url)

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': False},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is True
        call_args = mocks['booking'].book_outgoing_invoice.call_args
        sr = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs.get('storage_result')
        expected_filename = f"{invoice['invoice_number']}.pdf"
        assert sr['filename'] == expected_filename

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_credit_note_booking_receives_storage_url(
        self, data, storage_url,
    ):
        """book_credit_note is called with storage_result containing
        the URL from OutputService (Req 22.3, 22.4)."""
        cn = data.draw(draft_invoice_st(invoice_type='credit_note'))
        # Create a matching original invoice for the credit note
        original = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(cn, storage_url=storage_url)
        # get_invoice is called twice for credit notes: once for the CN,
        # once for the original invoice
        svc.get_invoice = Mock(side_effect=[cn, original])

        result = svc.send_invoice(
            cn['administration'], cn['id'],
            {'send_email': False},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is True
        call_args = mocks['booking'].book_credit_note.call_args
        sr = call_args.args[3] if len(call_args.args) > 3 else call_args.kwargs.get('storage_result')
        assert sr is not None
        assert sr['url'] == storage_url

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_credit_note_booking_receives_correct_filename(
        self, data, storage_url,
    ):
        """book_credit_note is called with storage_result containing
        the PDF filename matching the credit note number (Req 22.3)."""
        cn = data.draw(draft_invoice_st(invoice_type='credit_note'))
        original = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(cn, storage_url=storage_url)
        svc.get_invoice = Mock(side_effect=[cn, original])

        result = svc.send_invoice(
            cn['administration'], cn['id'],
            {'send_email': False},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is True
        call_args = mocks['booking'].book_credit_note.call_args
        sr = call_args.args[3] if len(call_args.args) > 3 else call_args.kwargs.get('storage_result')
        expected_filename = f"{cn['invoice_number']}.pdf"
        assert sr['filename'] == expected_filename

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_storage_result_url_and_filename_are_consistent(
        self, data, storage_url,
    ):
        """The storage_result passed to booking always has both url and
        filename set — never one without the other (Req 22.4)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(invoice, storage_url=storage_url)

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': False},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is True
        call_args = mocks['booking'].book_outgoing_invoice.call_args
        sr = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs.get('storage_result')
        # Both must be non-empty strings
        assert isinstance(sr['url'], str) and len(sr['url']) > 0
        assert isinstance(sr['filename'], str) and len(sr['filename']) > 0

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_booking_called_exactly_once_per_successful_send(
        self, data, storage_url,
    ):
        """For any successful send, the booking helper is called exactly once
        with the storage result (Req 22.4)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(invoice, storage_url=storage_url)

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': False},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is True
        assert mocks['booking'].book_outgoing_invoice.call_count == 1


# ---------------------------------------------------------------------------
# Property 7: Storage failure aborts send flow
# Feature: zzp-module, Property 7: Storage failure aborts send flow
# Validates: Requirements 22.5
# ---------------------------------------------------------------------------

class TestStorageFailureAbortsSendFlow:
    """For any invoice where the OutputService fails to store the PDF
    (raises exception or returns no URL), the send operation SHALL return
    success: False, the invoice status SHALL remain 'draft', and zero
    mutaties entries SHALL be created for that invoice."""

    @settings(max_examples=25)
    @given(
        data=st.data(),
        error_msg=error_message_st,
    )
    def test_storage_exception_returns_failure(
        self, data, error_msg,
    ):
        """Any storage exception → success: False (Req 22.5)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice,
            storage_exception=RuntimeError(error_msg),
        )

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is False
        assert 'error' in result

    @settings(max_examples=25)
    @given(
        data=st.data(),
        error_msg=error_message_st,
    )
    def test_storage_exception_prevents_booking(
        self, data, error_msg,
    ):
        """Any storage exception → no booking helper calls (Req 22.5)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice,
            storage_exception=RuntimeError(error_msg),
        )

        svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        mocks['booking'].book_outgoing_invoice.assert_not_called()
        mocks['booking'].book_credit_note.assert_not_called()

    @settings(max_examples=25)
    @given(
        data=st.data(),
        error_msg=error_message_st,
    )
    def test_storage_exception_prevents_email(
        self, data, error_msg,
    ):
        """Any storage exception → no email sent (Req 22.5)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice,
            storage_exception=RuntimeError(error_msg),
        )

        svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        mocks['email_svc'].send_invoice_email.assert_not_called()

    @settings(max_examples=25)
    @given(
        data=st.data(),
        error_msg=error_message_st,
    )
    def test_storage_exception_keeps_status_draft(
        self, data, error_msg,
    ):
        """Any storage exception → no status update (invoice stays draft) (Req 22.5)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice,
            storage_exception=RuntimeError(error_msg),
        )

        svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        # _update_status uses db.execute_query with UPDATE invoices SET status
        status_calls = [
            c for c in mocks['db'].execute_query.call_args_list
            if c.args and isinstance(c.args[0], str)
            and 'UPDATE invoices SET status' in c.args[0]
        ]
        assert len(status_calls) == 0

    @settings(max_examples=25)
    @given(data=st.data())
    def test_storage_returns_empty_url_returns_failure(self, data):
        """Storage returning empty URL → success: False (Req 22.5)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(invoice, storage_url='')

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is False
        assert 'error' in result

    @settings(max_examples=25)
    @given(data=st.data())
    def test_storage_returns_empty_url_prevents_booking(self, data):
        """Storage returning empty URL → no booking (Req 22.5)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(invoice, storage_url='')

        svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        mocks['booking'].book_outgoing_invoice.assert_not_called()

    @settings(max_examples=25)
    @given(data=st.data())
    def test_storage_returns_none_url_returns_failure(self, data):
        """Storage returning None URL → success: False (Req 22.5)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(invoice)
        mocks['output_svc'].handle_output.return_value = {'url': None}

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is False
        mocks['booking'].book_outgoing_invoice.assert_not_called()

    @settings(max_examples=25)
    @given(
        data=st.data(),
        health_reason=error_message_st,
    )
    def test_health_check_failure_aborts_before_pdf_generation(
        self, data, health_reason,
    ):
        """Health check failure → no PDF generated, no booking, no email (Req 22.5, 22.7)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice, health_ok=False, health_reason=health_reason,
        )

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is False
        mocks['pdf_gen'].generate_invoice_pdf.assert_not_called()
        mocks['booking'].book_outgoing_invoice.assert_not_called()
        mocks['email_svc'].send_invoice_email.assert_not_called()

    @settings(max_examples=25)
    @given(
        data=st.data(),
        error_msg=error_message_st,
    )
    def test_credit_note_storage_failure_also_aborts(
        self, data, error_msg,
    ):
        """Storage failure for credit notes also aborts (Req 22.5)."""
        cn = data.draw(draft_invoice_st(invoice_type='credit_note'))

        svc, mocks = _make_service_and_mocks(
            cn,
            storage_exception=RuntimeError(error_msg),
        )

        result = svc.send_invoice(
            cn['administration'], cn['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is False
        mocks['booking'].book_outgoing_invoice.assert_not_called()
        mocks['booking'].book_credit_note.assert_not_called()


# ---------------------------------------------------------------------------
# Property 8: Email failure is soft failure
# Feature: zzp-module, Property 8: Email failure is soft failure
# Validates: Requirements 22.6
# ---------------------------------------------------------------------------

class TestEmailFailureIsSoftFailure:
    """For any invoice where storage and booking succeed but email sending
    fails, the invoice status SHALL be 'sent', the mutaties entries SHALL
    exist with correct Ref3/Ref4, and the response SHALL include a warning
    field describing the email failure."""

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_email_failure_returns_success_true(
        self, data, storage_url,
    ):
        """Email failure after booking → success: True (Req 22.6)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice, storage_url=storage_url, email_success=False,
        )

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is True

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_email_failure_includes_warning(
        self, data, storage_url,
    ):
        """Email failure after booking → response has warning field (Req 22.6)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice, storage_url=storage_url, email_success=False,
        )

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        assert 'warning' in result
        assert isinstance(result['warning'], str)
        assert len(result['warning']) > 0

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_email_failure_booking_still_happened(
        self, data, storage_url,
    ):
        """Email failure after booking → booking was called (Req 22.6)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice, storage_url=storage_url, email_success=False,
        )

        svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        mocks['booking'].book_outgoing_invoice.assert_called_once()

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_email_failure_booking_received_storage_result(
        self, data, storage_url,
    ):
        """Even when email fails, booking received the correct storage result
        with url and filename (Req 22.6, 22.4)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice, storage_url=storage_url, email_success=False,
        )

        svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        call_args = mocks['booking'].book_outgoing_invoice.call_args
        sr = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs.get('storage_result')
        assert sr['url'] == storage_url
        assert sr['filename'] == f"{invoice['invoice_number']}.pdf"

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_email_failure_status_updated_to_sent(
        self, data, storage_url,
    ):
        """Email failure after booking → status updated to 'sent' (Req 22.6)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice, storage_url=storage_url, email_success=False,
        )

        svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        # _update_status should have been called (status → sent)
        status_calls = [
            c for c in mocks['db'].execute_query.call_args_list
            if c.args and isinstance(c.args[0], str)
            and 'UPDATE invoices SET status' in c.args[0]
        ]
        assert len(status_calls) >= 1
        # The status should be 'sent'
        last_status_call = status_calls[-1]
        assert 'sent' in last_status_call.args[1]

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
        error_msg=error_message_st,
    )
    def test_email_exception_returns_success_with_warning(
        self, data, storage_url, error_msg,
    ):
        """Email raising an exception → success: True with warning (Req 22.6)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice, storage_url=storage_url,
            email_exception=Exception(error_msg),
        )

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is True
        assert 'warning' in result
        assert isinstance(result['warning'], str)

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
        error_msg=error_message_st,
    )
    def test_email_exception_booking_still_happened(
        self, data, storage_url, error_msg,
    ):
        """Email exception → booking was still called (Req 22.6)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice, storage_url=storage_url,
            email_exception=Exception(error_msg),
        )

        svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        mocks['booking'].book_outgoing_invoice.assert_called_once()

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_successful_email_no_warning(
        self, data, storage_url,
    ):
        """When email succeeds, no warning field in response (Req 22.6 inverse)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice, storage_url=storage_url, email_success=True,
        )

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is True
        assert 'warning' not in result

    @settings(max_examples=25)
    @given(
        data=st.data(),
        storage_url=storage_url_st,
    )
    def test_email_failure_returns_invoice_number(
        self, data, storage_url,
    ):
        """Email failure → response still includes invoice_number (Req 22.6)."""
        invoice = data.draw(draft_invoice_st(invoice_type='invoice'))

        svc, mocks = _make_service_and_mocks(
            invoice, storage_url=storage_url, email_success=False,
        )

        result = svc.send_invoice(
            invoice['administration'], invoice['id'],
            {'send_email': True},
            output_service=mocks['output_svc'],
        )

        assert result['success'] is True
        assert result['invoice_number'] == invoice['invoice_number']
