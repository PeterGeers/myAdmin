"""Unit tests for InvoiceEmailService."""

import pytest
from unittest.mock import Mock
from services.invoice_email_service import InvoiceEmailService


def _make_service(ses=None, contact_svc=None, param_svc=None):
    ses = ses or Mock(send_email_with_attachments=Mock(
        return_value={'success': True, 'message_id': 'msg-123'}
    ))
    contact_svc = contact_svc or Mock(
        get_invoice_email=Mock(return_value='invoice@acme.nl')
    )
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return InvoiceEmailService(
        ses_email_service=ses, contact_service=contact_svc,
        parameter_service=param_svc,
    )


def _sample_invoice():
    return {
        'invoice_number': 'INV-2026-0001',
        'invoice_date': '2026-04-15',
        'due_date': '2026-05-15',
        'payment_terms_days': 30,
        'grand_total': 18392.0,
        'contact': {
            'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp B.V.',
        },
    }


# ── send_invoice_email ──────────────────────────────────────


def test_send_invoice_email_success_returns_message_id():
    ses = Mock(send_email_with_attachments=Mock(
        return_value={'success': True, 'message_id': 'msg-123'}
    ))
    svc = _make_service(ses=ses)
    result = svc.send_invoice_email('T1', _sample_invoice(), [
        {'filename': 'inv.pdf', 'content': b'pdf', 'content_type': 'application/pdf'},
    ])
    assert result['success'] is True
    assert result['message_id'] == 'msg-123'


def test_send_invoice_email_uses_invoice_email_from_contact(ses=None):
    ses = Mock(send_email_with_attachments=Mock(
        return_value={'success': True, 'message_id': 'x'}
    ))
    contact_svc = Mock(get_invoice_email=Mock(return_value='facturen@acme.nl'))
    svc = _make_service(ses=ses, contact_svc=contact_svc)
    svc.send_invoice_email('T1', _sample_invoice(), [])
    call_kwargs = ses.send_email_with_attachments.call_args[1]
    assert call_kwargs['to_email'] == 'facturen@acme.nl'


def test_send_invoice_email_no_email_returns_error():
    contact_svc = Mock(get_invoice_email=Mock(return_value=None))
    svc = _make_service(contact_svc=contact_svc)
    result = svc.send_invoice_email('T1', _sample_invoice(), [])
    assert result['success'] is False
    assert 'No email' in result['error']


def test_send_invoice_email_uses_custom_subject_template():
    ses = Mock(send_email_with_attachments=Mock(
        return_value={'success': True, 'message_id': 'x'}
    ))
    param_svc = Mock(get_param=Mock(side_effect=lambda ns, key, **kw:
        'Invoice {invoice_number}' if key == 'email_subject_template' else None
    ))
    svc = _make_service(ses=ses, param_svc=param_svc)
    svc.send_invoice_email('T1', _sample_invoice(), [])
    call_kwargs = ses.send_email_with_attachments.call_args[1]
    assert call_kwargs['subject'] == 'Invoice INV-2026-0001'


def test_send_invoice_email_includes_bcc_from_params():
    ses = Mock(send_email_with_attachments=Mock(
        return_value={'success': True, 'message_id': 'x'}
    ))
    param_svc = Mock(get_param=Mock(side_effect=lambda ns, key, **kw:
        'admin@company.nl' if key == 'invoice_email_bcc' else None
    ))
    svc = _make_service(ses=ses, param_svc=param_svc)
    svc.send_invoice_email('T1', _sample_invoice(), [])
    call_kwargs = ses.send_email_with_attachments.call_args[1]
    assert 'admin@company.nl' in call_kwargs['bcc']


def test_send_invoice_email_passes_attachments():
    ses = Mock(send_email_with_attachments=Mock(
        return_value={'success': True, 'message_id': 'x'}
    ))
    svc = _make_service(ses=ses)
    attachments = [
        {'filename': 'inv.pdf', 'content': b'pdf', 'content_type': 'application/pdf'},
        {'filename': 'sheet.xlsx', 'content': b'xlsx', 'content_type': 'application/vnd.ms-excel'},
    ]
    svc.send_invoice_email('T1', _sample_invoice(), attachments)
    call_kwargs = ses.send_email_with_attachments.call_args[1]
    assert len(call_kwargs['attachments']) == 2


# ── send_reminder_email ─────────────────────────────────────


def test_send_reminder_email_success():
    ses = Mock(send_email_with_attachments=Mock(
        return_value={'success': True, 'message_id': 'rem-123'}
    ))
    svc = _make_service(ses=ses)
    result = svc.send_reminder_email('T1', _sample_invoice())
    assert result['success'] is True
    call_kwargs = ses.send_email_with_attachments.call_args[1]
    assert 'herinnering' in call_kwargs['subject'].lower()
    assert call_kwargs['email_type'] == 'reminder'
    assert call_kwargs['attachments'] == []


def test_send_reminder_email_no_email_returns_error():
    contact_svc = Mock(get_invoice_email=Mock(return_value=None))
    svc = _make_service(contact_svc=contact_svc)
    result = svc.send_reminder_email('T1', _sample_invoice())
    assert result['success'] is False


# ── _build_subject ──────────────────────────────────────────


def test_build_subject_default_format():
    svc = _make_service()
    subject = svc._build_subject('T1', _sample_invoice())
    assert 'INV-2026-0001' in subject
    assert 'Acme Corp' in subject


# ── _build_body ─────────────────────────────────────────────


def test_build_body_invoice_includes_client_id_reference():
    svc = _make_service()
    body = svc._build_body('T1', _sample_invoice(), 'invoice')
    assert 'ACME' in body
    assert '18392.00' in body


def test_build_body_reminder_includes_due_date():
    svc = _make_service()
    body = svc._build_body('T1', _sample_invoice(), 'reminder')
    assert '2026-05-15' in body
    assert 'ACME' in body
