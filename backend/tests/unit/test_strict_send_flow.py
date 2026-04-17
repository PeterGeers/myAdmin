"""Unit tests for strict send flow ordering in ZZPInvoiceService.send_invoice().

Validates Requirements 22.1–22.7:
- 22.1: Strict order: generate PDF → store → book mutaties → email
- 22.2: Storage URL written to Ref3, filename to Ref4
- 22.3: Credit note storage URL/filename in Ref3/Ref4
- 22.4: Storage result passed to booking helper before entries created
- 22.5: Storage failure aborts send (draft, no mutaties)
- 22.6: Email failure is soft (sent, warning returned, mutaties exist)
- 22.7: Pre-flight health check before any PDF generation
"""

import pytest
from io import BytesIO
from unittest.mock import Mock, MagicMock, call, patch
from services.zzp_invoice_service import ZZPInvoiceService


# ── Helpers ─────────────────────────────────────────────────


def _draft_invoice_data(invoice_id=1, invoice_type='invoice',
                        original_invoice_id=None):
    """Return a minimal draft invoice dict as returned by get_invoice."""
    return {
        'id': invoice_id,
        'administration': 'T1',
        'invoice_number': 'INV-2026-0003',
        'invoice_type': invoice_type,
        'contact_id': 10,
        'invoice_date': '2026-04-15',
        'due_date': '2026-05-15',
        'payment_terms_days': 30,
        'currency': 'EUR',
        'exchange_rate': 1.0,
        'status': 'draft',
        'subtotal': 1000.0,
        'vat_total': 210.0,
        'grand_total': 1210.0,
        'notes': None,
        'original_invoice_id': original_invoice_id,
        'sent_at': None,
        'created_by': 'test',
        'created_at': None,
        'updated_at': None,
        'revenue_account': '8001',
    }


def _make_db_for_send(invoice_data=None):
    """Create a mock db that returns invoice data for get_invoice queries."""
    inv = invoice_data or _draft_invoice_data()
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [inv],  # _get_invoice_raw
        [{'id': 10, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],  # contact
        [{'id': 1, 'description': 'Dev', 'product_id': None, 'quantity': 10,
          'unit_price': 100, 'vat_code': 'high', 'vat_rate': 21,
          'vat_amount': 210, 'line_total': 1000, 'sort_order': 0}],  # lines
        [{'vat_code': 'high', 'vat_rate': 21,
          'base_amount': 1000, 'vat_amount': 210}],  # vat_summary
        None,  # _update_status (sent)
    ])
    return db


def _make_service_with_mocks(db=None, pdf_bytes=None, storage_url=None,
                              email_success=True, health_ok=True,
                              health_reason=None):
    """Build a ZZPInvoiceService with fully mocked dependencies."""
    db = db or _make_db_for_send()
    pdf_gen = Mock(
        generate_invoice_pdf=Mock(
            return_value=BytesIO(pdf_bytes or b'%PDF-fake')
        ),
    )
    booking = Mock(book_outgoing_invoice=Mock(return_value=[]))
    email_svc = Mock(send_invoice_email=Mock(
        return_value={'success': email_success, 'error': 'SES rejected' if not email_success else None}
    ))
    output_svc = Mock(
        check_health=Mock(return_value={
            'healthy': health_ok,
            'reason': health_reason or ('OK' if health_ok else 'Connection refused'),
        }),
        handle_output=Mock(return_value={
            'url': storage_url if storage_url is not None else 'https://drive.google.com/file/abc123',
        }),
    )
    param_svc = Mock(get_param=Mock(return_value=None))

    svc = ZZPInvoiceService(
        db=db,
        pdf_generator=pdf_gen,
        booking_helper=booking,
        email_service=email_svc,
        parameter_service=param_svc,
    )
    return svc, {
        'db': db,
        'pdf_gen': pdf_gen,
        'booking': booking,
        'email_svc': email_svc,
        'output_svc': output_svc,
        'param_svc': param_svc,
    }


# ── Test: Strict ordering (Req 22.1) ───────────────────────


def test_send_flow_executes_in_order_health_generate_store_book_email():
    """Verify the send flow calls services in strict order:
    health check → generate PDF → store PDF → book → email.
    Req 22.1
    """
    call_order = []

    svc, mocks = _make_service_with_mocks()

    # Instrument each mock to record call order
    mocks['output_svc'].check_health.side_effect = lambda dest, admin: (
        call_order.append('health_check'),
        {'healthy': True},
    )[-1]

    mocks['pdf_gen'].generate_invoice_pdf.side_effect = lambda t, inv: (
        call_order.append('generate_pdf'),
        BytesIO(b'%PDF-fake'),
    )[-1]

    mocks['output_svc'].handle_output.side_effect = lambda **kw: (
        call_order.append('store_pdf'),
        {'url': 'https://drive.google.com/file/abc123'},
    )[-1]

    mocks['booking'].book_outgoing_invoice.side_effect = lambda t, inv, sr: (
        call_order.append('book'),
        [],
    )[-1]

    mocks['email_svc'].send_invoice_email.side_effect = lambda t, inv, att: (
        call_order.append('email'),
        {'success': True},
    )[-1]

    result = svc.send_invoice('T1', 1, {'send_email': True},
                              output_service=mocks['output_svc'])

    assert result['success'] is True
    assert call_order == [
        'health_check', 'generate_pdf', 'store_pdf', 'book', 'email',
    ]


# ── Test: Health check failure aborts send (Req 22.7) ──────


def test_health_check_failure_aborts_send_invoice_stays_draft():
    """Storage health check failure → invoice stays draft, no mutaties.
    Req 22.7, 22.5
    """
    svc, mocks = _make_service_with_mocks(health_ok=False,
                                           health_reason='Connection refused')

    result = svc.send_invoice('T1', 1, {'send_email': True},
                              output_service=mocks['output_svc'])

    assert result['success'] is False
    assert 'Storage unavailable' in result['error']
    # PDF should NOT have been generated
    mocks['pdf_gen'].generate_invoice_pdf.assert_not_called()
    # No booking should have happened
    mocks['booking'].book_outgoing_invoice.assert_not_called()
    # No email should have been sent
    mocks['email_svc'].send_invoice_email.assert_not_called()
    # No status update (invoice stays draft)
    # The db.execute_query calls should only be the get_invoice ones (4 calls)
    # and NOT include the _update_status call
    status_update_calls = [
        c for c in mocks['db'].execute_query.call_args_list
        if c.args and isinstance(c.args[0], str) and 'UPDATE invoices SET status' in c.args[0]
    ]
    assert len(status_update_calls) == 0


def test_health_check_exception_aborts_send():
    """Health check raising an exception → invoice stays draft, no mutaties.
    Req 22.7
    """
    svc, mocks = _make_service_with_mocks()
    mocks['output_svc'].check_health.side_effect = ConnectionError('Network down')

    result = svc.send_invoice('T1', 1, {'send_email': True},
                              output_service=mocks['output_svc'])

    assert result['success'] is False
    assert 'health check failed' in result['error']
    mocks['pdf_gen'].generate_invoice_pdf.assert_not_called()
    mocks['booking'].book_outgoing_invoice.assert_not_called()


def test_check_health_called_before_any_pdf_generation():
    """check_health() must be called before generate_invoice_pdf().
    Req 22.7
    """
    call_order = []

    svc, mocks = _make_service_with_mocks()

    mocks['output_svc'].check_health.side_effect = lambda dest, admin: (
        call_order.append('health'),
        {'healthy': True},
    )[-1]

    mocks['pdf_gen'].generate_invoice_pdf.side_effect = lambda t, inv: (
        call_order.append('pdf'),
        BytesIO(b'%PDF'),
    )[-1]

    svc.send_invoice('T1', 1, {'send_email': False},
                     output_service=mocks['output_svc'])

    assert 'health' in call_order
    assert 'pdf' in call_order
    assert call_order.index('health') < call_order.index('pdf')


# ── Test: Storage failure aborts send (Req 22.5) ───────────


def test_storage_exception_aborts_send_invoice_stays_draft():
    """Storage raising an exception → invoice stays draft, no mutaties.
    Req 22.5
    """
    svc, mocks = _make_service_with_mocks()
    mocks['output_svc'].handle_output.side_effect = RuntimeError('Drive API error')

    result = svc.send_invoice('T1', 1, {'send_email': True},
                              output_service=mocks['output_svc'])

    assert result['success'] is False
    assert 'Storage unavailable' in result['error']
    mocks['booking'].book_outgoing_invoice.assert_not_called()
    mocks['email_svc'].send_invoice_email.assert_not_called()
    # No status update
    status_update_calls = [
        c for c in mocks['db'].execute_query.call_args_list
        if c.args and isinstance(c.args[0], str) and 'UPDATE invoices SET status' in c.args[0]
    ]
    assert len(status_update_calls) == 0


def test_storage_returns_no_url_aborts_send():
    """Storage returns empty/no URL → invoice stays draft, no mutaties.
    Req 22.5
    """
    svc, mocks = _make_service_with_mocks(storage_url='')

    result = svc.send_invoice('T1', 1, {'send_email': True},
                              output_service=mocks['output_svc'])

    assert result['success'] is False
    assert 'no URL returned' in result['error']
    mocks['booking'].book_outgoing_invoice.assert_not_called()
    mocks['email_svc'].send_invoice_email.assert_not_called()


def test_storage_returns_none_url_aborts_send():
    """Storage returns None URL → invoice stays draft, no mutaties.
    Req 22.5
    """
    svc, mocks = _make_service_with_mocks()
    mocks['output_svc'].handle_output.return_value = {'url': None}

    result = svc.send_invoice('T1', 1, {'send_email': True},
                              output_service=mocks['output_svc'])

    assert result['success'] is False
    assert 'no URL returned' in result['error']
    mocks['booking'].book_outgoing_invoice.assert_not_called()


# ── Test: Email failure is soft (Req 22.6) ──────────────────


def test_email_failure_after_booking_returns_success_with_warning():
    """Email failure after successful booking: status = sent, warning returned.
    Req 22.6
    """
    svc, mocks = _make_service_with_mocks(email_success=False)

    result = svc.send_invoice('T1', 1, {'send_email': True},
                              output_service=mocks['output_svc'])

    assert result['success'] is True
    assert 'warning' in result
    assert 'email failed' in result['warning']
    assert result['invoice_number'] == 'INV-2026-0003'
    # Booking DID happen
    mocks['booking'].book_outgoing_invoice.assert_called_once()
    # Status was updated to sent
    status_update_calls = [
        c for c in mocks['db'].execute_query.call_args_list
        if c.args and isinstance(c.args[0], str) and 'UPDATE invoices SET status' in c.args[0]
    ]
    assert len(status_update_calls) == 1


def test_email_exception_after_booking_returns_success_with_warning():
    """Email raising an exception after successful booking: status = sent, warning.
    Req 22.6
    """
    svc, mocks = _make_service_with_mocks()
    mocks['email_svc'].send_invoice_email.side_effect = Exception('SMTP timeout')

    result = svc.send_invoice('T1', 1, {'send_email': True},
                              output_service=mocks['output_svc'])

    assert result['success'] is True
    assert 'warning' in result
    assert 'email failed' in result['warning']
    # Booking happened
    mocks['booking'].book_outgoing_invoice.assert_called_once()


# ── Test: Storage result flows to booking (Req 22.2, 22.4) ─


def test_successful_send_passes_storage_result_to_booking():
    """Storage URL and filename are passed to book_outgoing_invoice.
    Req 22.2, 22.4
    """
    svc, mocks = _make_service_with_mocks()

    result = svc.send_invoice('T1', 1, {'send_email': False},
                              output_service=mocks['output_svc'])

    assert result['success'] is True
    # Verify booking was called with storage_result containing url + filename
    booking_call = mocks['booking'].book_outgoing_invoice.call_args
    storage_result = booking_call.args[2] if len(booking_call.args) > 2 else booking_call.kwargs.get('storage_result')
    assert storage_result is not None
    assert storage_result['url'] == 'https://drive.google.com/file/abc123'
    assert storage_result['filename'] == 'INV-2026-0003.pdf'


def test_successful_send_storage_result_has_correct_filename():
    """The filename in storage_result matches the invoice number.
    Req 22.2
    """
    svc, mocks = _make_service_with_mocks()

    svc.send_invoice('T1', 1, {'send_email': False},
                     output_service=mocks['output_svc'])

    booking_call = mocks['booking'].book_outgoing_invoice.call_args
    storage_result = booking_call.args[2] if len(booking_call.args) > 2 else booking_call.kwargs.get('storage_result')
    assert storage_result['filename'] == 'INV-2026-0003.pdf'


# ── Test: No email when send_email=False ────────────────────


def test_send_with_send_email_false_skips_email():
    """When send_email=False, email service is not called.
    Req 22.1 (email is optional step)
    """
    svc, mocks = _make_service_with_mocks()

    result = svc.send_invoice('T1', 1, {'send_email': False},
                              output_service=mocks['output_svc'])

    assert result['success'] is True
    assert 'warning' not in result
    mocks['email_svc'].send_invoice_email.assert_not_called()
    # But booking still happened
    mocks['booking'].book_outgoing_invoice.assert_called_once()


# ── Test: Status update happens before email (Req 22.6) ────


def test_status_updated_to_sent_before_email_attempt():
    """Status is set to 'sent' before email is attempted, so email failure
    doesn't leave invoice in draft.
    Req 22.6
    """
    call_order = []

    svc, mocks = _make_service_with_mocks()

    original_execute = mocks['db'].execute_query

    def tracking_execute(*args, **kwargs):
        if args and isinstance(args[0], str) and 'UPDATE invoices SET status' in args[0]:
            call_order.append('status_update')
        return original_execute(*args, **kwargs)

    mocks['db'].execute_query = Mock(side_effect=tracking_execute)
    # Re-setup the side effects for get_invoice queries
    inv = _draft_invoice_data()
    mocks['db'].execute_query.side_effect = [
        [inv],  # _get_invoice_raw
        [{'id': 10, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],
        [{'id': 1, 'description': 'Dev', 'product_id': None, 'quantity': 10,
          'unit_price': 100, 'vat_code': 'high', 'vat_rate': 21,
          'vat_amount': 210, 'line_total': 1000, 'sort_order': 0}],
        [{'vat_code': 'high', 'vat_rate': 21,
          'base_amount': 1000, 'vat_amount': 210}],
        None,  # _update_status
    ]

    mocks['email_svc'].send_invoice_email.side_effect = lambda t, inv, att: (
        call_order.append('email'),
        {'success': True},
    )[-1]

    # We need to track the status update call
    original_side_effects = list(mocks['db'].execute_query.side_effect)

    def ordered_execute(*args, **kwargs):
        if args and isinstance(args[0], str) and 'UPDATE invoices SET status' in args[0]:
            call_order.append('status_update')
            return None
        return original_side_effects.pop(0)

    mocks['db'].execute_query.side_effect = ordered_execute

    result = svc.send_invoice('T1', 1, {'send_email': True},
                              output_service=mocks['output_svc'])

    assert result['success'] is True
    assert 'status_update' in call_order
    assert 'email' in call_order
    assert call_order.index('status_update') < call_order.index('email')
