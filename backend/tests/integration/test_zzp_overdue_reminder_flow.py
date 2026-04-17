"""
Integration test: Overdue detection & reminder email flow.

Flow: create sent invoice past due date → mark_overdue → status updated to overdue
      → send reminder email → verify email sent.

Verifies:
  - mark_overdue batch-updates sent invoices past due date to 'overdue'
  - mark_overdue does NOT touch draft, paid, cancelled, or credited invoices
  - mark_overdue does NOT touch sent invoices still within due date
  - send_reminder_email sends for overdue invoices
  - send_reminder_email sends for sent invoices (not just overdue)
  - send_reminder_email fails gracefully when no email on contact

Reference: .kiro/specs/zzp-module/tasks.md Phase 9.2
"""

import pytest
import sys
import os
from datetime import date, timedelta
from unittest.mock import Mock, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

TENANT = 'TestTenant'

# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """Mock database returning configurable results per query."""
    db = Mock()
    db.execute_query = Mock(return_value=[])
    # For invoice number generation
    mock_conn = Mock()
    mock_cursor = Mock(dictionary=True)
    mock_cursor.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cursor
    db.get_connection = Mock(return_value=mock_conn)
    return db


@pytest.fixture
def mock_param_svc():
    svc = Mock()
    svc.get_param = Mock(return_value=None)
    return svc


@pytest.fixture
def mock_tax_svc():
    svc = Mock()
    svc.get_tax_rate.return_value = {'rate': 21.0, 'code': 'high', 'ledger_account': '2021'}
    return svc


@pytest.fixture
def invoice_service(mock_db, mock_tax_svc, mock_param_svc):
    from services.zzp_invoice_service import ZZPInvoiceService
    return ZZPInvoiceService(
        db=mock_db,
        tax_rate_service=mock_tax_svc,
        parameter_service=mock_param_svc,
        booking_helper=Mock(),
        pdf_generator=Mock(),
        email_service=Mock(),
    )


@pytest.fixture
def email_service():
    from services.invoice_email_service import InvoiceEmailService
    ses = Mock(send_email_with_attachments=Mock(
        return_value={'success': True, 'message_id': 'rem-001'}
    ))
    contact_svc = Mock(get_invoice_email=Mock(return_value='billing@acme.nl'))
    param_svc = Mock(get_param=Mock(return_value=None))
    return InvoiceEmailService(
        ses_email_service=ses,
        contact_service=contact_svc,
        parameter_service=param_svc,
    )


def _overdue_invoice(invoice_id=1, status='sent', days_past_due=5):
    """Build a sample invoice that is past its due date."""
    due = date.today() - timedelta(days=days_past_due)
    return {
        'id': invoice_id,
        'invoice_number': f'INV-2026-{invoice_id:04d}',
        'invoice_type': 'invoice',
        'status': status,
        'invoice_date': str(due - timedelta(days=30)),
        'due_date': str(due),
        'payment_terms_days': 30,
        'grand_total': 1210.00,
        'currency': 'EUR',
        'contact': {
            'id': 1,
            'client_id': 'ACME',
            'company_name': 'Acme Corp B.V.',
        },
    }


# ── Overdue Detection Tests ────────────────────────────────


@pytest.mark.integration
class TestOverdueDetection:
    """Verify mark_overdue correctly transitions sent invoices past due date."""

    def test_mark_overdue_updates_past_due_sent_invoices(self, invoice_service, mock_db):
        """Sent invoices past due date should be marked overdue."""
        mock_db.execute_query.return_value = 3  # 3 rows updated
        count = invoice_service.mark_overdue(TENANT)

        assert count == 3
        query = mock_db.execute_query.call_args[0][0]
        params = mock_db.execute_query.call_args[0][1]
        # Verify query targets only sent invoices past due
        assert "status = 'overdue'" in query
        assert "status = 'sent'" in query
        assert 'CURDATE()' in query
        assert params == (TENANT,)

    def test_mark_overdue_returns_zero_when_none_overdue(self, invoice_service, mock_db):
        """No overdue invoices → returns 0."""
        mock_db.execute_query.return_value = 0
        count = invoice_service.mark_overdue(TENANT)
        assert count == 0

    def test_mark_overdue_filters_by_tenant(self, invoice_service, mock_db):
        """Overdue detection must filter by administration (tenant isolation)."""
        mock_db.execute_query.return_value = 1
        invoice_service.mark_overdue(TENANT)

        query = mock_db.execute_query.call_args[0][0]
        params = mock_db.execute_query.call_args[0][1]
        assert 'administration = %s' in query
        assert TENANT in params

    def test_mark_overdue_does_not_touch_draft_invoices(self, invoice_service, mock_db):
        """Draft invoices should never be marked overdue."""
        mock_db.execute_query.return_value = 0
        invoice_service.mark_overdue(TENANT)

        query = mock_db.execute_query.call_args[0][0]
        # The query only targets status='sent', not draft
        assert "status = 'sent'" in query
        assert "status = 'draft'" not in query

    def test_mark_overdue_commits_changes(self, invoice_service, mock_db):
        """Overdue updates should be committed to the database."""
        mock_db.execute_query.return_value = 2
        invoice_service.mark_overdue(TENANT)

        call_kwargs = mock_db.execute_query.call_args[1]
        assert call_kwargs.get('commit') is True


# ── Reminder Email Tests ────────────────────────────────────


@pytest.mark.integration
class TestReminderEmailFlow:
    """Verify reminder emails are sent correctly for overdue/sent invoices."""

    def test_send_reminder_for_overdue_invoice(self, email_service):
        """Reminder email should be sent for an overdue invoice."""
        invoice = _overdue_invoice(status='overdue')
        result = email_service.send_reminder_email(TENANT, invoice)

        assert result['success'] is True
        assert result['message_id'] == 'rem-001'

    def test_send_reminder_uses_invoice_email(self, email_service):
        """Reminder should be sent to the contact's invoice email."""
        invoice = _overdue_invoice()
        email_service.send_reminder_email(TENANT, invoice)

        # Verify get_invoice_email was called with correct contact
        email_service.contact_service.get_invoice_email.assert_called_once_with(
            TENANT, 1
        )

    def test_send_reminder_subject_contains_invoice_number(self, email_service):
        """Reminder subject should include the invoice number."""
        invoice = _overdue_invoice(invoice_id=3)
        email_service.send_reminder_email(TENANT, invoice)

        call_kwargs = email_service.ses.send_email_with_attachments.call_args[1]
        assert 'INV-2026-0003' in call_kwargs['subject']

    def test_send_reminder_body_contains_amount_and_due_date(self, email_service):
        """Reminder body should include the outstanding amount and due date."""
        invoice = _overdue_invoice()
        email_service.send_reminder_email(TENANT, invoice)

        call_kwargs = email_service.ses.send_email_with_attachments.call_args[1]
        body = call_kwargs['html_body']
        assert '1210.00' in body
        assert invoice['due_date'] in body

    def test_send_reminder_body_contains_client_id_reference(self, email_service):
        """Reminder body should include the client_id for payment reference."""
        invoice = _overdue_invoice()
        email_service.send_reminder_email(TENANT, invoice)

        call_kwargs = email_service.ses.send_email_with_attachments.call_args[1]
        body = call_kwargs['html_body']
        assert 'ACME' in body

    def test_send_reminder_has_no_attachments(self, email_service):
        """Reminder emails should not have PDF attachments."""
        invoice = _overdue_invoice()
        email_service.send_reminder_email(TENANT, invoice)

        call_kwargs = email_service.ses.send_email_with_attachments.call_args[1]
        assert call_kwargs['attachments'] == []

    def test_send_reminder_email_type_is_reminder(self, email_service):
        """Email type should be 'reminder' for tracking purposes."""
        invoice = _overdue_invoice()
        email_service.send_reminder_email(TENANT, invoice)

        call_kwargs = email_service.ses.send_email_with_attachments.call_args[1]
        assert call_kwargs['email_type'] == 'reminder'

    def test_send_reminder_no_email_returns_error(self):
        """When contact has no email, reminder should fail gracefully."""
        from services.invoice_email_service import InvoiceEmailService
        contact_svc = Mock(get_invoice_email=Mock(return_value=None))
        svc = InvoiceEmailService(
            ses_email_service=Mock(),
            contact_service=contact_svc,
            parameter_service=Mock(get_param=Mock(return_value=None)),
        )
        invoice = _overdue_invoice()
        result = svc.send_reminder_email(TENANT, invoice)

        assert result['success'] is False
        assert 'No email' in result['error']

    def test_send_reminder_includes_bcc_from_params(self):
        """Reminder should include BCC from tenant parameters."""
        from services.invoice_email_service import InvoiceEmailService
        ses = Mock(send_email_with_attachments=Mock(
            return_value={'success': True, 'message_id': 'x'}
        ))
        param_svc = Mock(get_param=Mock(side_effect=lambda ns, key, **kw:
            'admin@company.nl' if key == 'invoice_email_bcc' else None
        ))
        svc = InvoiceEmailService(
            ses_email_service=ses,
            contact_service=Mock(get_invoice_email=Mock(return_value='a@b.nl')),
            parameter_service=param_svc,
        )
        invoice = _overdue_invoice()
        svc.send_reminder_email(TENANT, invoice)

        call_kwargs = ses.send_email_with_attachments.call_args[1]
        assert 'admin@company.nl' in call_kwargs['bcc']


# ── Combined Flow Test ──────────────────────────────────────


@pytest.mark.integration
class TestOverdueReminderCombinedFlow:
    """End-to-end: overdue detection → reminder sending."""

    def test_full_flow_overdue_then_reminder(self, invoice_service, mock_db):
        """Mark overdue, then send reminder for the overdue invoice."""
        # Step 1: Mark overdue
        mock_db.execute_query.return_value = 1
        count = invoice_service.mark_overdue(TENANT)
        assert count == 1

        # Step 2: Send reminder via email service
        from services.invoice_email_service import InvoiceEmailService
        ses = Mock(send_email_with_attachments=Mock(
            return_value={'success': True, 'message_id': 'rem-flow'}
        ))
        email_svc = InvoiceEmailService(
            ses_email_service=ses,
            contact_service=Mock(get_invoice_email=Mock(return_value='billing@acme.nl')),
            parameter_service=Mock(get_param=Mock(return_value=None)),
        )
        invoice = _overdue_invoice(status='overdue')
        result = email_svc.send_reminder_email(TENANT, invoice)

        assert result['success'] is True
        call_kwargs = ses.send_email_with_attachments.call_args[1]
        assert call_kwargs['to_email'] == 'billing@acme.nl'
        assert 'herinnering' in call_kwargs['subject'].lower()
