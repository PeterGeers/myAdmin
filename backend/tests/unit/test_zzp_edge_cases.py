"""Unit tests for ZZP edge cases and error handling (Phase 9.3).

Covers five categories:
1. Soft-delete protection (contacts & products referenced by invoices)
2. Sent invoice immutability (financial fields locked after send)
3. Concurrent invoice numbering (FOR UPDATE locking, no duplicates)
4. Missing logo handling (PDF generates without logo placeholder)
5. Email failure handling (soft failure with warning, storage failure = hard stop)
"""

import pytest
from io import BytesIO
from unittest.mock import Mock, MagicMock, patch
from datetime import date

from services.contact_service import ContactService
from services.product_service import ProductService
from services.zzp_invoice_service import ZZPInvoiceService
from services.pdf_generator_service import PDFGeneratorService


# ── Helpers ─────────────────────────────────────────────────


def _make_contact_service(db=None, param_svc=None):
    db = db or Mock()
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return ContactService(db=db, parameter_service=param_svc)


def _make_product_service(db=None, tax_svc=None, param_svc=None):
    db = db or Mock()
    tax_svc = tax_svc or Mock(get_tax_rate=Mock(return_value={'rate': 21.0}))
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return ProductService(db=db, tax_rate_service=tax_svc, parameter_service=param_svc)


def _make_invoice_service(db=None, tax_svc=None, param_svc=None,
                          booking=None, pdf_gen=None, email_svc=None):
    db = db or Mock()
    tax_svc = tax_svc or Mock()
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return ZZPInvoiceService(
        db=db, tax_rate_service=tax_svc, parameter_service=param_svc,
        booking_helper=booking, pdf_generator=pdf_gen, email_service=email_svc,
    )


def _make_pdf_service(db=None, template_svc=None, param_svc=None):
    db = db or Mock()
    template_svc = template_svc or Mock(get_template_metadata=Mock(return_value=None))
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return PDFGeneratorService(db=db, template_service=template_svc,
                               parameter_service=param_svc)


def _contact_row(**overrides):
    base = {
        'id': 1, 'administration': 'T1', 'client_id': 'ACME',
        'contact_type': 'client', 'company_name': 'Acme Corp',
        'contact_person': None, 'street_address': None,
        'postal_code': None, 'city': None, 'country': 'NL',
        'vat_number': None, 'kvk_number': None, 'phone': None,
        'iban': None, 'is_active': True, 'created_by': 'test',
        'created_at': None, 'updated_at': None,
    }
    base.update(overrides)
    return base


def _product_row(**overrides):
    base = {
        'id': 1, 'administration': 'T1', 'product_code': 'DEV-HR',
        'external_reference': None, 'name': 'Software Development',
        'description': None, 'product_type': 'service',
        'unit_price': 95.00, 'vat_code': 'high',
        'unit_of_measure': 'uur', 'is_active': True,
        'created_by': 'test', 'created_at': None, 'updated_at': None,
    }
    base.update(overrides)
    return base


def _draft_invoice(**overrides):
    base = {
        'id': 1, 'administration': 'T1', 'invoice_number': 'INV-2026-0001',
        'invoice_type': 'invoice', 'contact_id': 10,
        'invoice_date': '2026-04-15', 'due_date': '2026-05-15',
        'payment_terms_days': 30, 'currency': 'EUR', 'exchange_rate': 1.0,
        'status': 'draft', 'subtotal': 1000.0, 'vat_total': 210.0,
        'grand_total': 1210.0, 'notes': None, 'original_invoice_id': None,
        'sent_at': None, 'created_by': 'test', 'created_at': None,
        'updated_at': None, 'revenue_account': '8001',
    }
    base.update(overrides)
    return base


def _sample_invoice_dict(**overrides):
    """Full invoice dict as returned by get_invoice (with contact, lines, vat_summary)."""
    base = _draft_invoice(**overrides)
    base.setdefault('contact', {
        'id': 10, 'client_id': 'ACME', 'company_name': 'Acme Corp',
    })
    base.setdefault('lines', [{
        'id': 1, 'description': 'Dev', 'product_id': None, 'quantity': 10,
        'unit_price': 100, 'vat_code': 'high', 'vat_rate': 21,
        'vat_amount': 210, 'line_total': 1000, 'sort_order': 0,
    }])
    base.setdefault('vat_summary', [{
        'vat_code': 'high', 'vat_rate': 21,
        'base_amount': 1000, 'vat_amount': 210,
    }])
    return base


# ═══════════════════════════════════════════════════════════
# 1. Soft-Delete Protection
# ═══════════════════════════════════════════════════════════


def test_soft_delete_contact_referenced_by_invoice_raises_valueerror():
    """Contact with invoices cannot be deleted."""
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_contact_row()],  # get_contact
        [],                # _get_emails
        [{'1': 1}],       # _check_contact_in_use → invoice exists
    ])
    svc = _make_contact_service(db=db)
    with pytest.raises(ValueError, match="referenced by existing invoices"):
        svc.soft_delete_contact('T1', 1)


def test_soft_delete_contact_unused_returns_true():
    """Unused contact can be soft-deleted."""
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_contact_row()],  # get_contact
        [],                # _get_emails
        [],                # _check_contact_in_use → no invoices
        None,              # UPDATE is_active = FALSE
    ])
    svc = _make_contact_service(db=db)
    assert svc.soft_delete_contact('T1', 1) is True


def test_soft_delete_contact_sets_is_active_false():
    """Soft-delete issues UPDATE is_active = FALSE, not a hard DELETE."""
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_contact_row()],  # get_contact
        [],                # _get_emails
        [],                # _check_contact_in_use
        None,              # UPDATE
    ])
    svc = _make_contact_service(db=db)
    svc.soft_delete_contact('T1', 1)
    update_call = db.execute_query.call_args_list[3]
    assert 'is_active = FALSE' in update_call[0][0]
    assert 'DELETE' not in update_call[0][0].upper()


def test_soft_delete_product_referenced_by_invoice_lines_raises_valueerror():
    """Product with invoice lines cannot be deleted."""
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_product_row()],  # get_product
        [{'1': 1}],       # _check_product_in_use → line exists
    ])
    svc = _make_product_service(db=db)
    with pytest.raises(ValueError, match="referenced by existing invoice lines"):
        svc.soft_delete_product('T1', 1)


def test_soft_delete_product_unused_returns_true():
    """Unused product can be soft-deleted."""
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_product_row()],  # get_product
        [],                # _check_product_in_use → no lines
        None,              # UPDATE is_active = FALSE
    ])
    svc = _make_product_service(db=db)
    assert svc.soft_delete_product('T1', 1) is True


def test_soft_delete_product_sets_is_active_false():
    """Soft-delete issues UPDATE is_active = FALSE, not a hard DELETE."""
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_product_row()],  # get_product
        [],                # _check_product_in_use
        None,              # UPDATE
    ])
    svc = _make_product_service(db=db)
    svc.soft_delete_product('T1', 1)
    update_call = db.execute_query.call_args_list[2]
    assert 'is_active = FALSE' in update_call[0][0]
    assert 'DELETE' not in update_call[0][0].upper()


# ═══════════════════════════════════════════════════════════
# 2. Sent Invoice Immutability
# ═══════════════════════════════════════════════════════════


def test_update_sent_invoice_raises_valueerror():
    """Sent invoices cannot be edited."""
    db = Mock()
    db.execute_query = Mock(return_value=[
        _draft_invoice(status='sent'),
    ])
    svc = _make_invoice_service(db=db)
    with pytest.raises(ValueError, match="Only draft invoices can be edited"):
        svc.update_invoice('T1', 1, {'notes': 'Nope'})


def test_update_draft_invoice_succeeds():
    """Draft invoices can be edited."""
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_draft_invoice(status='draft', invoice_date=date(2026, 4, 15))],  # _get_invoice_raw
        None,  # UPDATE header
        # get_invoice chain:
        [_draft_invoice(notes='Updated')],  # _get_invoice_raw
        [{'id': 10, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],  # contact
        [],  # lines
        [],  # vat_summary
    ])
    svc = _make_invoice_service(db=db)
    result = svc.update_invoice('T1', 1, {'notes': 'Updated'})
    assert result['notes'] == 'Updated'


def test_send_non_draft_invoice_raises_valueerror():
    """Only draft invoices can be sent."""
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_draft_invoice(status='sent')],  # _get_invoice_raw
        [{'id': 10, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],
        [], [],  # lines, vat_summary
    ])
    svc = _make_invoice_service(db=db)
    with pytest.raises(ValueError, match="Only draft invoices can be sent"):
        svc.send_invoice('T1', 1, {})


def test_credit_note_from_draft_invoice_raises_valueerror():
    """Credit notes cannot be created from draft invoices."""
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_draft_invoice(status='draft')],  # _get_invoice_raw
        [{'id': 10, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],
        [], [],  # lines, vat_summary
    ])
    svc = _make_invoice_service(db=db)
    with pytest.raises(ValueError, match="Can only credit invoices that have been sent"):
        svc.create_credit_note('T1', 1, created_by='test')


# ═══════════════════════════════════════════════════════════
# 3. Concurrent Invoice Numbering
# ═══════════════════════════════════════════════════════════


def _mock_db_for_numbering(existing_sequence=None):
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    if existing_sequence is not None:
        cursor.fetchone.return_value = {'last_sequence': existing_sequence}
    else:
        cursor.fetchone.return_value = None
    db = Mock()
    db.get_connection.return_value = conn
    return db, conn, cursor


def test_generate_invoice_number_uses_for_update():
    """The SELECT query must include FOR UPDATE for row-level locking."""
    db, conn, cursor = _mock_db_for_numbering(existing_sequence=1)
    svc = _make_invoice_service(db=db)
    svc._generate_invoice_number('T1', 'INV', 2026)
    select_call = cursor.execute.call_args_list[1]  # [0]=START TRANSACTION, [1]=SELECT
    assert 'FOR UPDATE' in select_call[0][0]


def test_generate_invoice_number_wraps_in_transaction():
    """The method must use START TRANSACTION and COMMIT."""
    db, conn, cursor = _mock_db_for_numbering(existing_sequence=1)
    svc = _make_invoice_service(db=db)
    svc._generate_invoice_number('T1', 'INV', 2026)
    start_call = cursor.execute.call_args_list[0]
    assert 'START TRANSACTION' in start_call[0][0]
    conn.commit.assert_called_once()


def test_generate_invoice_number_rollback_on_error():
    """Errors during numbering must trigger ROLLBACK."""
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    cursor.execute.side_effect = [None, Exception("DB error")]  # START ok, SELECT fails
    db = Mock()
    db.get_connection.return_value = conn
    svc = _make_invoice_service(db=db)
    with pytest.raises(Exception, match="DB error"):
        svc._generate_invoice_number('T1', 'INV', 2026)
    conn.rollback.assert_called_once()


def test_generate_invoice_number_sequential_calls_produce_different_numbers():
    """Two sequential calls (simulated concurrency) produce different numbers."""
    db1, conn1, cursor1 = _mock_db_for_numbering(existing_sequence=3)
    db2, conn2, cursor2 = _mock_db_for_numbering(existing_sequence=4)
    svc1 = _make_invoice_service(db=db1)
    svc2 = _make_invoice_service(db=db2)
    r1 = svc1._generate_invoice_number('T1', 'INV', 2026)
    r2 = svc2._generate_invoice_number('T1', 'INV', 2026)
    assert r1 == 'INV-2026-0004'
    assert r2 == 'INV-2026-0005'
    assert r1 != r2


# ═══════════════════════════════════════════════════════════
# 4. Missing Logo Handling
# ═══════════════════════════════════════════════════════════


def test_get_tenant_logo_no_config_returns_none():
    """When no logo parameter is configured, _get_tenant_logo returns None."""
    svc = _make_pdf_service()
    assert svc._get_tenant_logo('T1') is None


def test_render_html_no_logo_has_no_img_tag():
    """When logo is None, rendered HTML must not contain an <img tag."""
    svc = _make_pdf_service()
    inv = _sample_invoice_dict()
    html = svc._render_html('T1', inv)
    assert '<img' not in html


@patch('services.pdf_generator_service.PDFGeneratorService._html_to_pdf')
def test_pdf_generation_succeeds_without_logo(mock_to_pdf):
    """PDF generation returns a BytesIO with content even without a logo."""
    mock_to_pdf.return_value = BytesIO(b'%PDF-fake-content')
    svc = _make_pdf_service()
    inv = _sample_invoice_dict()
    result = svc.generate_invoice_pdf('T1', inv)
    assert isinstance(result, BytesIO)
    assert len(result.getvalue()) > 0


# ═══════════════════════════════════════════════════════════
# 5. Email Failure Handling
# ═══════════════════════════════════════════════════════════


def _make_send_flow_service(email_result=None, email_exception=None,
                            storage_exception=None):
    """Build a ZZPInvoiceService wired for send_invoice testing."""
    inv = _draft_invoice()
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [inv],  # _get_invoice_raw
        [{'id': 10, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],
        [{'id': 1, 'description': 'Dev', 'product_id': None, 'quantity': 10,
          'unit_price': 100, 'vat_code': 'high', 'vat_rate': 21,
          'vat_amount': 210, 'line_total': 1000, 'sort_order': 0}],
        [{'vat_code': 'high', 'vat_rate': 21,
          'base_amount': 1000, 'vat_amount': 210}],
        None,  # _update_status
    ])

    pdf_gen = Mock(generate_invoice_pdf=Mock(return_value=BytesIO(b'%PDF-fake')))
    booking = Mock(book_outgoing_invoice=Mock(return_value=[]))

    email_svc = Mock()
    if email_exception:
        email_svc.send_invoice_email = Mock(side_effect=email_exception)
    elif email_result is not None:
        email_svc.send_invoice_email = Mock(return_value=email_result)
    else:
        email_svc.send_invoice_email = Mock(return_value={'success': True})

    output_svc = Mock(
        check_health=Mock(return_value={'healthy': True}),
        handle_output=Mock(
            side_effect=storage_exception if storage_exception else None,
            return_value=None if storage_exception else {'url': 'https://drive.google.com/file/abc'},
        ),
    )
    if storage_exception:
        output_svc.handle_output = Mock(side_effect=storage_exception)

    param_svc = Mock(get_param=Mock(return_value=None))

    svc = ZZPInvoiceService(
        db=db, pdf_generator=pdf_gen, booking_helper=booking,
        email_service=email_svc, parameter_service=param_svc,
    )
    return svc, output_svc, booking, db


def test_email_failure_returns_success_with_warning():
    """When email service returns success=False, send_invoice still succeeds with a warning."""
    svc, output_svc, booking, db = _make_send_flow_service(
        email_result={'success': False, 'error': 'SES rejected'},
    )
    result = svc.send_invoice('T1', 1, {'send_email': True}, output_service=output_svc)
    assert result['success'] is True
    assert 'warning' in result
    assert 'email failed' in result['warning']


def test_email_exception_returns_success_with_warning():
    """When email service raises an exception, send_invoice still succeeds with a warning."""
    svc, output_svc, booking, db = _make_send_flow_service(
        email_exception=Exception('SMTP timeout'),
    )
    result = svc.send_invoice('T1', 1, {'send_email': True}, output_service=output_svc)
    assert result['success'] is True
    assert 'warning' in result
    assert 'email failed' in result['warning']


def test_booking_happens_even_when_email_fails():
    """Booking must happen even when email fails (email is soft failure)."""
    svc, output_svc, booking, db = _make_send_flow_service(
        email_result={'success': False, 'error': 'SES rejected'},
    )
    svc.send_invoice('T1', 1, {'send_email': True}, output_service=output_svc)
    booking.book_outgoing_invoice.assert_called_once()


def test_storage_failure_returns_failure_invoice_stays_draft():
    """Storage failure = hard stop: success=False, no booking, invoice stays draft."""
    svc, output_svc, booking, db = _make_send_flow_service(
        storage_exception=RuntimeError('Drive API error'),
    )
    result = svc.send_invoice('T1', 1, {'send_email': True}, output_service=output_svc)
    assert result['success'] is False
    assert 'Storage unavailable' in result['error']
    booking.book_outgoing_invoice.assert_not_called()
    # No status update should have happened
    status_update_calls = [
        c for c in db.execute_query.call_args_list
        if c.args and isinstance(c.args[0], str) and 'UPDATE invoices SET status' in c.args[0]
    ]
    assert len(status_update_calls) == 0
