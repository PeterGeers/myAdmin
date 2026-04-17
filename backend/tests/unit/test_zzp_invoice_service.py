"""Unit tests for ZZPInvoiceService."""

import pytest
from io import BytesIO
from unittest.mock import Mock, MagicMock, call
from datetime import date
from io import BytesIO
from services.zzp_invoice_service import ZZPInvoiceService


def _make_service(db=None, tax_svc=None, param_svc=None):
    db = db or Mock()
    tax_svc = tax_svc or Mock()
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return ZZPInvoiceService(
        db=db, tax_rate_service=tax_svc, parameter_service=param_svc,
    )


def _mock_db_for_numbering(existing_sequence=None):
    """Create a mock db whose get_connection returns a mock conn/cursor
    that simulates the FOR UPDATE flow."""
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


# ── _generate_invoice_number ────────────────────────────────


def test_generate_invoice_number_first_invoice_returns_0001():
    db, conn, cursor = _mock_db_for_numbering(existing_sequence=None)
    svc = _make_service(db=db)
    result = svc._generate_invoice_number('T1', 'INV', 2026)
    assert result == 'INV-2026-0001'
    conn.commit.assert_called_once()


def test_generate_invoice_number_existing_sequence_increments():
    db, conn, cursor = _mock_db_for_numbering(existing_sequence=5)
    svc = _make_service(db=db)
    result = svc._generate_invoice_number('T1', 'INV', 2026)
    assert result == 'INV-2026-0006'


def test_generate_invoice_number_uses_for_update_locking():
    db, conn, cursor = _mock_db_for_numbering(existing_sequence=1)
    svc = _make_service(db=db)
    svc._generate_invoice_number('T1', 'INV', 2026)
    # Verify FOR UPDATE was in the SELECT query
    select_call = cursor.execute.call_args_list[1]  # [0]=START TRANSACTION, [1]=SELECT
    assert 'FOR UPDATE' in select_call[0][0]


def test_generate_invoice_number_new_year_starts_at_0001():
    db, conn, cursor = _mock_db_for_numbering(existing_sequence=None)
    svc = _make_service(db=db)
    result = svc._generate_invoice_number('T1', 'INV', 2027)
    assert result == 'INV-2027-0001'
    # Verify INSERT was called (not UPDATE)
    insert_call = cursor.execute.call_args_list[2]  # [0]=START, [1]=SELECT, [2]=INSERT
    assert 'INSERT' in insert_call[0][0]


def test_generate_invoice_number_respects_custom_padding():
    db, conn, cursor = _mock_db_for_numbering(existing_sequence=None)
    param_svc = Mock(get_param=Mock(side_effect=lambda ns, key, **kw:
        6 if key == 'invoice_number_padding' else None
    ))
    svc = _make_service(db=db, param_svc=param_svc)
    result = svc._generate_invoice_number('T1', 'INV', 2026)
    assert result == 'INV-2026-000001'


def test_generate_invoice_number_credit_note_prefix():
    db, conn, cursor = _mock_db_for_numbering(existing_sequence=2)
    svc = _make_service(db=db)
    result = svc._generate_invoice_number('T1', 'CN', 2026)
    assert result == 'CN-2026-0003'


def test_generate_invoice_number_rollback_on_error():
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    cursor.execute.side_effect = [None, Exception("DB error")]  # START ok, SELECT fails

    db = Mock()
    db.get_connection.return_value = conn
    svc = _make_service(db=db)

    with pytest.raises(Exception, match="DB error"):
        svc._generate_invoice_number('T1', 'INV', 2026)

    conn.rollback.assert_called_once()
    cursor.close.assert_called_once()
    conn.close.assert_called_once()


def test_generate_invoice_number_concurrent_same_tenant_uses_row_lock():
    """Two calls for the same tenant/year should both use FOR UPDATE,
    ensuring the DB serializes them. We verify the locking query is correct."""
    db1, conn1, cursor1 = _mock_db_for_numbering(existing_sequence=3)
    db2, conn2, cursor2 = _mock_db_for_numbering(existing_sequence=4)

    svc1 = _make_service(db=db1)
    svc2 = _make_service(db=db2)

    r1 = svc1._generate_invoice_number('T1', 'INV', 2026)
    r2 = svc2._generate_invoice_number('T1', 'INV', 2026)

    assert r1 == 'INV-2026-0004'
    assert r2 == 'INV-2026-0005'

    # Both used FOR UPDATE
    for c in [cursor1, cursor2]:
        select_call = c.execute.call_args_list[1]
        assert 'FOR UPDATE' in select_call[0][0]


# ── _get_invoice_prefix / _get_credit_note_prefix ───────────


def test_get_invoice_prefix_default_returns_inv():
    svc = _make_service()
    assert svc._get_invoice_prefix('T1') == 'INV'


def test_get_invoice_prefix_custom_returns_custom():
    param_svc = Mock(get_param=Mock(return_value='FACT'))
    svc = _make_service(param_svc=param_svc)
    assert svc._get_invoice_prefix('T1') == 'FACT'


def test_get_credit_note_prefix_default_returns_cn():
    svc = _make_service()
    assert svc._get_credit_note_prefix('T1') == 'CN'


def test_get_credit_note_prefix_custom_returns_custom():
    param_svc = Mock(get_param=Mock(return_value='CREDIT'))
    svc = _make_service(param_svc=param_svc)
    assert svc._get_credit_note_prefix('T1') == 'CREDIT'


# ── _calculate_line ─────────────────────────────────────────


def test_calculate_line_single_line_correct_totals():
    tax_svc = Mock(get_tax_rate=Mock(return_value={'rate': 21.0}))
    svc = _make_service(tax_svc=tax_svc)
    line = {'quantity': 160, 'unit_price': 95.0, 'vat_code': 'high', 'description': 'Dev'}
    result = svc._calculate_line('T1', line, date(2026, 4, 15))
    assert result['line_total'] == 15200.0
    assert result['vat_amount'] == 3192.0
    assert result['vat_rate'] == 21.0


def test_calculate_line_zero_rate_returns_zero_vat():
    tax_svc = Mock(get_tax_rate=Mock(return_value={'rate': 0.0}))
    svc = _make_service(tax_svc=tax_svc)
    line = {'quantity': 10, 'unit_price': 50.0, 'vat_code': 'zero', 'description': 'Export'}
    result = svc._calculate_line('T1', line, date(2026, 4, 15))
    assert result['line_total'] == 500.0
    assert result['vat_amount'] == 0.0


def test_calculate_line_low_rate_correct_vat():
    tax_svc = Mock(get_tax_rate=Mock(return_value={'rate': 9.0}))
    svc = _make_service(tax_svc=tax_svc)
    line = {'quantity': 1, 'unit_price': 100.0, 'vat_code': 'low', 'description': 'Book'}
    result = svc._calculate_line('T1', line, date(2026, 4, 15))
    assert result['vat_amount'] == 9.0


def test_calculate_line_no_tax_service_returns_zero_vat():
    svc = _make_service(tax_svc=None)
    svc.tax_rate_service = None
    line = {'quantity': 5, 'unit_price': 20.0, 'vat_code': 'high', 'description': 'Item'}
    result = svc._calculate_line('T1', line, date(2026, 4, 15))
    assert result['vat_rate'] == 0.0
    assert result['vat_amount'] == 0.0
    assert result['line_total'] == 100.0


def test_calculate_line_rounding_two_decimals():
    tax_svc = Mock(get_tax_rate=Mock(return_value={'rate': 21.0}))
    svc = _make_service(tax_svc=tax_svc)
    line = {'quantity': 1, 'unit_price': 33.33, 'vat_code': 'high', 'description': 'Item'}
    result = svc._calculate_line('T1', line, date(2026, 4, 15))
    assert result['line_total'] == 33.33
    assert result['vat_amount'] == 7.0  # 33.33 * 0.21 = 6.9993 → 7.0


# ── _update_totals ──────────────────────────────────────────


def test_update_totals_multi_line_correct_sums():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        None,  # UPDATE invoices
        [{'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': 200.0, 'vat_amount': 42.0}],
    ])
    svc = _make_service(db=db)
    lines = [
        {'line_total': 100.0, 'vat_amount': 21.0},
        {'line_total': 100.0, 'vat_amount': 21.0},
    ]
    result = svc._update_totals(1, lines)
    assert result['subtotal'] == 200.0
    assert result['vat_total'] == 42.0
    assert result['grand_total'] == 242.0


def test_update_totals_reads_vat_summary_from_view():
    db = Mock()
    vat_rows = [
        {'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': 15200.0, 'vat_amount': 3192.0},
        {'vat_code': 'low', 'vat_rate': 9.0, 'base_amount': 500.0, 'vat_amount': 45.0},
    ]
    db.execute_query = Mock(side_effect=[None, vat_rows])
    svc = _make_service(db=db)
    result = svc._update_totals(1, [
        {'line_total': 15200.0, 'vat_amount': 3192.0},
        {'line_total': 500.0, 'vat_amount': 45.0},
    ])
    assert len(result['vat_summary']) == 2


# ── create_invoice ──────────────────────────────────────────


def _mock_db_for_create():
    """DB mock that handles the full create_invoice flow."""
    db, conn, cursor = _mock_db_for_numbering(existing_sequence=None)

    call_count = [0]
    def side_effect(query, params=None, fetch=True, commit=False, pool_type='primary'):
        call_count[0] += 1
        q = query.strip().upper()
        if 'SELECT' in q and 'contacts' in query.lower():
            return [{'id': 1}]
        if 'INSERT INTO invoices' in query:
            return 42
        if 'INSERT INTO invoice_lines' in query:
            return 1
        if 'UPDATE invoices SET subtotal' in query:
            return None
        if 'vw_invoice_vat_summary' in query:
            return [{'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': 15200.0, 'vat_amount': 3192.0}]
        if 'SELECT' in q and 'invoices' in query.lower() and 'id = %s' in query:
            return [{'id': 42, 'administration': 'T1', 'invoice_number': 'INV-2026-0001',
                     'invoice_type': 'invoice', 'contact_id': 1, 'invoice_date': '2026-04-15',
                     'due_date': '2026-05-15', 'payment_terms_days': 30, 'currency': 'EUR',
                     'exchange_rate': 1.0, 'status': 'draft', 'subtotal': 15200.0,
                     'vat_total': 3192.0, 'grand_total': 18392.0, 'notes': None,
                     'original_invoice_id': None, 'sent_at': None, 'created_by': 'test',
                     'created_at': None, 'updated_at': None, 'revenue_account': None}]
        if 'SELECT' in q and 'contacts' in query.lower() and 'client_id' in query.lower():
            return [{'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}]
        if 'SELECT' in q and 'invoice_lines' in query.lower():
            return [{'id': 1, 'product_id': 1, 'description': 'Dev', 'quantity': 160.0,
                     'unit_price': 95.0, 'vat_code': 'high', 'vat_rate': 21.0,
                     'vat_amount': 3192.0, 'line_total': 15200.0, 'sort_order': 0}]
        return []

    db.execute_query = Mock(side_effect=side_effect)
    return db, conn, cursor


def test_create_invoice_valid_data_returns_invoice():
    db, conn, cursor = _mock_db_for_create()
    tax_svc = Mock(get_tax_rate=Mock(return_value={'rate': 21.0}))
    svc = ZZPInvoiceService(db=db, tax_rate_service=tax_svc,
                            parameter_service=Mock(get_param=Mock(return_value=None)))
    result = svc.create_invoice('T1', {
        'contact_id': 1,
        'invoice_date': '2026-04-15',
        'lines': [{'product_id': 1, 'description': 'Dev', 'quantity': 160.0,
                    'unit_price': 95.0, 'vat_code': 'high'}],
    }, created_by='test')
    assert result['invoice_number'] == 'INV-2026-0001'
    assert result['status'] == 'draft'


def test_create_invoice_invalid_contact_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[])  # contact not found
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="Contact .* not found"):
        svc.create_invoice('T1', {
            'contact_id': 999, 'invoice_date': '2026-04-15',
        }, created_by='test')


# ── update_invoice ──────────────────────────────────────────


def test_update_invoice_draft_allows_edit():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [{'id': 1, 'status': 'draft', 'invoice_date': date(2026, 4, 15),
          'payment_terms_days': 30}],  # _get_invoice_raw
        None,  # UPDATE header
        # get_invoice chain:
        [{'id': 1, 'administration': 'T1', 'invoice_number': 'INV-2026-0001',
          'invoice_type': 'invoice', 'contact_id': 1, 'invoice_date': '2026-04-15',
          'due_date': '2026-05-15', 'payment_terms_days': 30, 'currency': 'EUR',
          'exchange_rate': 1.0, 'status': 'draft', 'subtotal': 0, 'vat_total': 0,
          'grand_total': 0, 'notes': 'Updated', 'original_invoice_id': None,
          'sent_at': None, 'created_by': 'test', 'created_at': None, 'updated_at': None}],
        [{'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],
        [],  # lines
        [],  # vat_summary
    ])
    svc = _make_service(db=db)
    result = svc.update_invoice('T1', 1, {'notes': 'Updated'})
    assert result['notes'] == 'Updated'


def test_update_invoice_sent_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[
        {'id': 1, 'status': 'sent', 'invoice_date': date(2026, 4, 15),
         'payment_terms_days': 30},
    ])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="Only draft invoices"):
        svc.update_invoice('T1', 1, {'notes': 'Nope'})


def test_update_invoice_not_found_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="not found"):
        svc.update_invoice('T1', 999, {'notes': 'Nope'})


# ── list_invoices ───────────────────────────────────────────


def test_list_invoices_with_status_filter_includes_filter():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    svc.list_invoices('T1', {'status': 'draft'})
    query = db.execute_query.call_args[0][0]
    assert 'status' in query


def test_list_invoices_default_pagination_limit_50():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    svc.list_invoices('T1')
    params = db.execute_query.call_args[0][1]
    assert 50 in params  # default limit


# ── send_invoice ────────────────────────────────────────────


def test_send_invoice_draft_success_returns_invoice_number():
    db = Mock()
    invoice_data = {
        'id': 1, 'administration': 'T1', 'invoice_number': 'INV-2026-0001',
        'invoice_type': 'invoice', 'contact_id': 1, 'invoice_date': '2026-04-15',
        'due_date': '2026-05-15', 'payment_terms_days': 30, 'currency': 'EUR',
        'exchange_rate': 1.0, 'status': 'draft', 'subtotal': 100.0,
        'vat_total': 21.0, 'grand_total': 121.0, 'notes': None,
        'original_invoice_id': None, 'sent_at': None, 'created_by': 'test',
        'created_at': None, 'updated_at': None,
    }
    db.execute_query = Mock(side_effect=[
        [invoice_data],  # _get_invoice_raw via get_invoice
        [{'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],  # contact
        [{'id': 1, 'description': 'Dev', 'product_id': None, 'quantity': 1,
          'unit_price': 100, 'vat_code': 'high', 'vat_rate': 21, 'vat_amount': 21,
          'line_total': 100, 'sort_order': 0}],  # lines
        [{'vat_code': 'high', 'vat_rate': 21, 'base_amount': 100, 'vat_amount': 21}],  # vat_summary
        None,  # _update_status (sent)
    ])

    pdf_gen = Mock(generate_invoice_pdf=Mock(return_value=BytesIO(b'%PDF')))
    booking = Mock(book_outgoing_invoice=Mock(return_value=[]))
    email_svc = Mock(send_invoice_email=Mock(return_value={'success': True, 'message_id': 'x'}))
    output_svc = Mock(
        check_health=Mock(return_value={'healthy': True}),
        handle_output=Mock(return_value={'url': 'https://drive.google.com/file/123'}),
    )

    svc = ZZPInvoiceService(
        db=db, pdf_generator=pdf_gen, booking_helper=booking,
        email_service=email_svc, parameter_service=Mock(get_param=Mock(return_value=None)),
    )
    result = svc.send_invoice('T1', 1, {'send_email': True}, output_service=output_svc)
    assert result['success'] is True
    assert result['invoice_number'] == 'INV-2026-0001'
    assert 'warning' not in result
    output_svc.check_health.assert_called_once_with('gdrive', 'T1')
    pdf_gen.generate_invoice_pdf.assert_called_once()
    booking.book_outgoing_invoice.assert_called_once()
    email_svc.send_invoice_email.assert_called_once()


def test_send_invoice_not_draft_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [{'id': 1, 'status': 'sent', 'invoice_number': 'INV-2026-0001',
          'invoice_type': 'invoice', 'contact_id': 1, 'administration': 'T1',
          'invoice_date': '2026-04-15', 'due_date': '2026-05-15',
          'payment_terms_days': 30, 'currency': 'EUR', 'exchange_rate': 1.0,
          'subtotal': 100, 'vat_total': 21, 'grand_total': 121, 'notes': None,
          'original_invoice_id': None, 'sent_at': None, 'created_by': 'test',
          'created_at': None, 'updated_at': None}],
        [{'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],
        [], [],  # lines, vat_summary
    ])
    svc = ZZPInvoiceService(db=db, parameter_service=Mock(get_param=Mock(return_value=None)))
    with pytest.raises(ValueError, match="Only draft"):
        svc.send_invoice('T1', 1, {})


def test_send_invoice_email_failure_keeps_booked_returns_warning():
    """Email failure is a soft failure: invoice stays sent, warning returned."""
    db = Mock()
    invoice_data = {
        'id': 1, 'administration': 'T1', 'invoice_number': 'INV-2026-0001',
        'invoice_type': 'invoice', 'contact_id': 1, 'invoice_date': '2026-04-15',
        'due_date': '2026-05-15', 'payment_terms_days': 30, 'currency': 'EUR',
        'exchange_rate': 1.0, 'status': 'draft', 'subtotal': 100.0,
        'vat_total': 21.0, 'grand_total': 121.0, 'notes': None,
        'original_invoice_id': None, 'sent_at': None, 'created_by': 'test',
        'created_at': None, 'updated_at': None,
    }
    db.execute_query = Mock(side_effect=[
        [invoice_data],
        [{'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],
        [], [],  # lines, vat_summary
        None,  # _update_status (sent)
    ])

    pdf_gen = Mock(generate_invoice_pdf=Mock(return_value=BytesIO(b'%PDF')))
    booking = Mock(book_outgoing_invoice=Mock(return_value=[]))
    email_svc = Mock(send_invoice_email=Mock(
        return_value={'success': False, 'error': 'SES rejected'}
    ))
    output_svc = Mock(
        check_health=Mock(return_value={'healthy': True}),
        handle_output=Mock(return_value={'url': 'https://drive.google.com/file/123'}),
    )

    svc = ZZPInvoiceService(
        db=db, pdf_generator=pdf_gen, booking_helper=booking,
        email_service=email_svc, parameter_service=Mock(get_param=Mock(return_value=None)),
    )
    result = svc.send_invoice('T1', 1, {'send_email': True}, output_service=output_svc)
    assert result['success'] is True
    assert 'warning' in result
    assert 'email failed' in result['warning']
    assert result['invoice_number'] == 'INV-2026-0001'
    booking.book_outgoing_invoice.assert_called_once()


# ── create_credit_note ──────────────────────────────────────


def _mock_db_for_credit_note():
    """DB mock for credit note creation flow."""
    db, conn, cursor = _mock_db_for_numbering(existing_sequence=None)

    def side_effect(query, params=None, fetch=True, commit=False, pool_type='primary'):
        q = query.strip().upper() if query else ''
        # get_invoice for original
        if 'SELECT' in q and 'invoices' in query.lower() and 'id = %s' in query:
            return [{
                'id': 1, 'administration': 'T1', 'invoice_number': 'INV-2026-0001',
                'invoice_type': 'invoice', 'contact_id': 1, 'invoice_date': '2026-04-15',
                'due_date': '2026-05-15', 'payment_terms_days': 30, 'currency': 'EUR',
                'exchange_rate': 1.0, 'status': 'sent', 'subtotal': 100.0,
                'vat_total': 21.0, 'grand_total': 121.0, 'notes': None,
                'original_invoice_id': None, 'sent_at': '2026-04-15', 'created_by': 'test',
                'created_at': None, 'updated_at': None,
            }]
        if 'SELECT' in q and 'contacts' in query.lower():
            return [{'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}]
        if 'SELECT' in q and 'invoice_lines' in query.lower():
            return [{'id': 1, 'product_id': 1, 'description': 'Dev', 'quantity': 1.0,
                     'unit_price': 100.0, 'vat_code': 'high', 'vat_rate': 21.0,
                     'vat_amount': 21.0, 'line_total': 100.0, 'sort_order': 0}]
        if 'vw_invoice_vat_summary' in query.lower():
            return [{'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': -100.0, 'vat_amount': -21.0}]
        if 'INSERT INTO invoices' in query:
            return 42
        if 'INSERT INTO invoice_lines' in query:
            return 1
        if 'UPDATE invoices SET subtotal' in query:
            return None
        return []

    db.execute_query = Mock(side_effect=side_effect)
    return db, conn, cursor


def test_create_credit_note_sent_invoice_returns_credit_note():
    db, conn, cursor = _mock_db_for_credit_note()
    tax_svc = Mock(get_tax_rate=Mock(return_value={'rate': 21.0}))
    svc = ZZPInvoiceService(
        db=db, tax_rate_service=tax_svc,
        parameter_service=Mock(get_param=Mock(return_value=None)),
    )
    result = svc.create_credit_note('T1', 1, created_by='test')
    assert result is not None
    # Verify CN number was generated (via the numbering mock)
    conn.commit.assert_called()


def test_create_credit_note_draft_invoice_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [{'id': 1, 'status': 'draft', 'invoice_type': 'invoice', 'contact_id': 1,
          'administration': 'T1', 'invoice_number': 'INV-2026-0001',
          'invoice_date': '2026-04-15', 'due_date': '2026-05-15',
          'payment_terms_days': 30, 'currency': 'EUR', 'exchange_rate': 1.0,
          'subtotal': 100, 'vat_total': 21, 'grand_total': 121, 'notes': None,
          'original_invoice_id': None, 'sent_at': None, 'created_by': 'test',
          'created_at': None, 'updated_at': None}],
        [{'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],
        [], [],  # lines, vat_summary
    ])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="Can only credit invoices that have been sent"):
        svc.create_credit_note('T1', 1, created_by='test')


def test_create_credit_note_on_credit_note_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [{'id': 2, 'status': 'sent', 'invoice_type': 'credit_note', 'contact_id': 1,
          'administration': 'T1', 'invoice_number': 'CN-2026-0001',
          'invoice_date': '2026-04-15', 'due_date': '2026-05-15',
          'payment_terms_days': 30, 'currency': 'EUR', 'exchange_rate': 1.0,
          'subtotal': -100, 'vat_total': -21, 'grand_total': -121, 'notes': None,
          'original_invoice_id': 1, 'sent_at': None, 'created_by': 'test',
          'created_at': None, 'updated_at': None}],
        [{'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],
        [], [],
    ])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="Cannot credit a credit note"):
        svc.create_credit_note('T1', 2, created_by='test')


def test_create_credit_note_not_found_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="not found"):
        svc.create_credit_note('T1', 999, created_by='test')


# ── mark_overdue ────────────────────────────────────────────


def test_mark_overdue_updates_past_due_invoices_returns_count():
    db = Mock()
    db.execute_query = Mock(return_value=3)  # 3 rows updated
    svc = _make_service(db=db)
    result = svc.mark_overdue('T1')
    assert result == 3
    query = db.execute_query.call_args[0][0]
    assert 'overdue' in query
    assert 'CURDATE()' in query


def test_mark_overdue_no_overdue_invoices_returns_zero():
    db = Mock()
    db.execute_query = Mock(return_value=0)
    svc = _make_service(db=db)
    result = svc.mark_overdue('T1')
    assert result == 0


# ── create_invoice_from_time_entries ────────────────────────


def test_create_invoice_from_time_entries_creates_invoice_and_marks_billed():
    db, conn, cursor = _mock_db_for_create()
    tax_svc = Mock(get_tax_rate=Mock(return_value={'rate': 21.0}))
    time_svc = Mock()
    time_svc.get_entry = Mock(side_effect=[
        {'id': 10, 'contact_id': 1, 'product_id': 1, 'hours': 8.0,
         'hourly_rate': 95.0, 'entry_date': '2026-04-15',
         'description': 'Dev work', 'is_billed': False},
        {'id': 11, 'contact_id': 1, 'product_id': 1, 'hours': 4.0,
         'hourly_rate': 95.0, 'entry_date': '2026-04-16',
         'description': 'Review', 'is_billed': False},
    ])
    time_svc.mark_as_billed = Mock(return_value=2)

    svc = ZZPInvoiceService(
        db=db, tax_rate_service=tax_svc,
        parameter_service=Mock(get_param=Mock(return_value=None)))

    result = svc.create_invoice_from_time_entries(
        'T1', contact_id=1, entry_ids=[10, 11],
        data={'invoice_date': '2026-04-30'},
        created_by='test', time_tracking_service=time_svc)

    assert result is not None
    time_svc.mark_as_billed.assert_called_once()


def test_create_invoice_from_time_entries_billed_entry_raises_valueerror():
    time_svc = Mock()
    time_svc.get_entry = Mock(return_value={
        'id': 10, 'contact_id': 1, 'is_billed': True, 'hours': 8.0,
    })
    svc = _make_service()
    with pytest.raises(ValueError, match="already billed"):
        svc.create_invoice_from_time_entries(
            'T1', 1, [10], {}, 'test', time_tracking_service=time_svc)


def test_create_invoice_from_time_entries_wrong_contact_raises_valueerror():
    time_svc = Mock()
    time_svc.get_entry = Mock(return_value={
        'id': 10, 'contact_id': 99, 'is_billed': False, 'hours': 8.0,
    })
    svc = _make_service()
    with pytest.raises(ValueError, match="different contact"):
        svc.create_invoice_from_time_entries(
            'T1', 1, [10], {}, 'test', time_tracking_service=time_svc)


# ── copy_last_invoice ───────────────────────────────────────


def test_copy_last_invoice_creates_draft_from_previous():
    db, conn, cursor = _mock_db_for_create()

    # Override to also handle the copy-specific queries
    original_side_effect = db.execute_query.side_effect
    call_idx = [0]

    def side_effect(query, params=None, fetch=True, commit=False, pool_type='primary'):
        call_idx[0] += 1
        q = query.strip() if query else ''
        # Last invoice query
        if 'ORDER BY invoice_date DESC LIMIT 1' in q and 'invoice_type' in q:
            return [{'id': 10, 'administration': 'T1', 'contact_id': 1,
                     'invoice_date': '2026-03-15', 'payment_terms_days': 30,
                     'currency': 'EUR', 'notes': 'March work'}]
        # Last invoice lines
        if 'invoice_lines' in q and 'ORDER BY sort_order' in q:
            return [{'product_id': 1, 'description': 'Dev', 'quantity': 160.0,
                     'unit_price': 95.0, 'vat_code': 'high', 'sort_order': 0}]
        # _advance_date query
        if 'ORDER BY invoice_date DESC LIMIT 2' in q:
            return [{'invoice_date': '2026-03-15'}, {'invoice_date': '2026-02-15'}]
        # Delegate to create_invoice mock
        return original_side_effect(query, params, fetch, commit, pool_type)

    db.execute_query = Mock(side_effect=side_effect)
    tax_svc = Mock(get_tax_rate=Mock(return_value={'rate': 21.0}))
    svc = ZZPInvoiceService(
        db=db, tax_rate_service=tax_svc,
        parameter_service=Mock(get_param=Mock(return_value=None)))

    result = svc.copy_last_invoice('T1', contact_id=1, created_by='test')
    assert result is not None
    assert result.get('copied_from_invoice_id') == 10


def test_copy_last_invoice_no_previous_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="No previous invoice"):
        svc.copy_last_invoice('T1', contact_id=1, created_by='test')


def test_advance_date_two_invoices_uses_gap():
    db = Mock()
    db.execute_query = Mock(return_value=[
        {'invoice_date': '2026-03-15'},
        {'invoice_date': '2026-02-15'},
    ])
    svc = _make_service(db=db)
    result = svc._advance_date('T1', 1, date(2026, 3, 15))
    # Gap is 28 days (Feb 15 → Mar 15), so next = Mar 15 + 28 = Apr 12
    assert result == date(2026, 4, 12)


def test_advance_date_one_invoice_defaults_plus_one_month():
    db = Mock()
    db.execute_query = Mock(return_value=[{'invoice_date': '2026-03-15'}])
    svc = _make_service(db=db)
    result = svc._advance_date('T1', 1, date(2026, 3, 15))
    assert result == date(2026, 4, 15)


# ── revenue_account support (Req 18) ───────────────────────


def test_create_invoice_with_revenue_account_includes_in_insert():
    """When revenue_account is provided, it should be included in the INSERT."""
    db, conn, cursor = _mock_db_for_create()
    tax_svc = Mock(get_tax_rate=Mock(return_value={'rate': 21.0}))
    svc = ZZPInvoiceService(db=db, tax_rate_service=tax_svc,
                            parameter_service=Mock(get_param=Mock(return_value=None)))
    result = svc.create_invoice('T1', {
        'contact_id': 1,
        'invoice_date': '2026-04-15',
        'revenue_account': '8010',
        'lines': [{'product_id': 1, 'description': 'Dev', 'quantity': 160.0,
                    'unit_price': 95.0, 'vat_code': 'high'}],
    }, created_by='test')

    # Find the INSERT INTO invoices call
    insert_calls = [c for c in db.execute_query.call_args_list
                    if 'INSERT INTO invoices' in str(c)]
    assert len(insert_calls) >= 1
    insert_call = insert_calls[0]
    query = insert_call[0][0]
    params = insert_call[0][1]
    assert 'revenue_account' in query
    assert '8010' in params


def test_create_invoice_without_revenue_account_uses_parameter_default():
    """When revenue_account is not provided, it should fall back to zzp.revenue_account param."""
    db, conn, cursor = _mock_db_for_create()
    tax_svc = Mock(get_tax_rate=Mock(return_value={'rate': 21.0}))
    param_svc = Mock()
    param_svc.get_param = Mock(side_effect=lambda ns, key, tenant=None: '8001' if key == 'revenue_account' else None)
    svc = ZZPInvoiceService(db=db, tax_rate_service=tax_svc,
                            parameter_service=param_svc)
    svc.create_invoice('T1', {
        'contact_id': 1,
        'invoice_date': '2026-04-15',
        'lines': [{'product_id': 1, 'description': 'Dev', 'quantity': 160.0,
                    'unit_price': 95.0, 'vat_code': 'high'}],
    }, created_by='test')

    # Verify zzp.revenue_account was looked up
    param_calls = [c for c in param_svc.get_param.call_args_list
                   if c[0] == ('zzp', 'revenue_account')]
    assert len(param_calls) >= 1

    # Verify the default was used in the INSERT
    insert_calls = [c for c in db.execute_query.call_args_list
                    if 'INSERT INTO invoices' in str(c)]
    assert len(insert_calls) >= 1
    params = insert_calls[0][0][1]
    assert '8001' in params


def test_create_invoice_no_revenue_account_and_no_param_inserts_none():
    """When no revenue_account provided and no parameter configured, NULL is stored."""
    db, conn, cursor = _mock_db_for_create()
    tax_svc = Mock(get_tax_rate=Mock(return_value={'rate': 21.0}))
    param_svc = Mock(get_param=Mock(return_value=None))
    svc = ZZPInvoiceService(db=db, tax_rate_service=tax_svc,
                            parameter_service=param_svc)
    svc.create_invoice('T1', {
        'contact_id': 1,
        'invoice_date': '2026-04-15',
        'lines': [{'product_id': 1, 'description': 'Dev', 'quantity': 160.0,
                    'unit_price': 95.0, 'vat_code': 'high'}],
    }, created_by='test')

    insert_calls = [c for c in db.execute_query.call_args_list
                    if 'INSERT INTO invoices' in str(c)]
    assert len(insert_calls) >= 1
    params = insert_calls[0][0][1]
    # revenue_account should be None (NULL in DB)
    assert None in params


def test_update_invoice_revenue_account_on_draft():
    """Updating revenue_account on a draft invoice should be allowed."""
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [{'id': 1, 'status': 'draft', 'invoice_date': date(2026, 4, 15),
          'payment_terms_days': 30}],  # _get_invoice_raw
        None,  # UPDATE header
        # get_invoice chain:
        [{'id': 1, 'administration': 'T1', 'invoice_number': 'INV-2026-0001',
          'invoice_type': 'invoice', 'contact_id': 1, 'invoice_date': '2026-04-15',
          'due_date': '2026-05-15', 'payment_terms_days': 30, 'currency': 'EUR',
          'exchange_rate': 1.0, 'status': 'draft', 'subtotal': 0, 'vat_total': 0,
          'grand_total': 0, 'notes': None, 'original_invoice_id': None,
          'sent_at': None, 'created_by': 'test', 'created_at': None,
          'updated_at': None, 'revenue_account': '8010'}],
        [{'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],
        [],  # lines
        [],  # vat_summary
    ])
    svc = _make_service(db=db)
    result = svc.update_invoice('T1', 1, {'revenue_account': '8010'})

    # Verify the UPDATE query included revenue_account
    update_calls = [c for c in db.execute_query.call_args_list
                    if 'UPDATE invoices SET' in str(c)]
    assert len(update_calls) >= 1
    update_query = update_calls[0][0][0]
    assert 'revenue_account' in update_query
    assert result['revenue_account'] == '8010'


def test_get_invoice_returns_revenue_account():
    """get_invoice should include revenue_account in the response."""
    db = Mock()
    db.execute_query = Mock(side_effect=[
        # _get_invoice_raw (SELECT *)
        [{'id': 1, 'administration': 'T1', 'invoice_number': 'INV-2026-0001',
          'invoice_type': 'invoice', 'contact_id': 1, 'invoice_date': '2026-04-15',
          'due_date': '2026-05-15', 'payment_terms_days': 30, 'currency': 'EUR',
          'exchange_rate': 1.0, 'status': 'draft', 'subtotal': 15200.0,
          'vat_total': 3192.0, 'grand_total': 18392.0, 'notes': None,
          'original_invoice_id': None, 'sent_at': None, 'created_by': 'test',
          'created_at': None, 'updated_at': None, 'revenue_account': '8010'}],
        # contact
        [{'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}],
        # lines
        [{'id': 1, 'product_id': 1, 'description': 'Dev', 'quantity': 160.0,
          'unit_price': 95.0, 'vat_code': 'high', 'vat_rate': 21.0,
          'vat_amount': 3192.0, 'line_total': 15200.0, 'sort_order': 0}],
        # vat_summary
        [{'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': 15200.0, 'vat_amount': 3192.0}],
    ])
    svc = _make_service(db=db)
    result = svc.get_invoice('T1', 1)
    assert result is not None
    assert result['revenue_account'] == '8010'


def test_get_default_revenue_account_returns_param_value():
    """_get_default_revenue_account should return the zzp.revenue_account parameter."""
    param_svc = Mock()
    param_svc.get_param = Mock(return_value='8001')
    svc = _make_service(param_svc=param_svc)
    result = svc._get_default_revenue_account('T1')
    assert result == '8001'
    param_svc.get_param.assert_called_with('zzp', 'revenue_account', tenant='T1')


def test_get_default_revenue_account_returns_none_when_not_configured():
    """_get_default_revenue_account should return None when no parameter is set."""
    param_svc = Mock(get_param=Mock(return_value=None))
    svc = _make_service(param_svc=param_svc)
    result = svc._get_default_revenue_account('T1')
    assert result is None
