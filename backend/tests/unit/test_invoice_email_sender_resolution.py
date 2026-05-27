"""Unit tests for InvoiceEmailService sender resolution and error recovery.

Tests the modifications to InvoiceEmailService that integrate with
EmailVerificationService for verified sender resolution and fallback behavior.

Validates: Requirements 4.1–4.4, 6.1–6.3
"""

import pytest
from unittest.mock import Mock, patch, call

from services.invoice_email_service import InvoiceEmailService


# ── Fixtures ────────────────────────────────────────────────


def _make_verification_service(verified=True, email='tenant@example.com',
                               company_name='Acme'):
    """Create a mock EmailVerificationService."""
    svc = Mock()
    svc.get_verified_sender = Mock(return_value={
        'verified': verified,
        'email': email,
        'company_name': company_name,
    })
    svc.mark_expired = Mock()
    return svc


def _make_ses(success=True, message_id='msg-123', error=None):
    """Create a mock SESEmailService."""
    if success:
        result = {'success': True, 'message_id': message_id}
    else:
        result = {'success': False, 'error': error or 'Unknown error'}
    ses = Mock()
    ses.send_email_with_attachments = Mock(return_value=result)
    return ses


def _make_service(ses=None, contact_svc=None, param_svc=None,
                  verification_svc=None):
    """Create an InvoiceEmailService with mocked dependencies."""
    ses = ses or _make_ses()
    contact_svc = contact_svc or Mock(
        get_invoice_email=Mock(return_value='client@example.com')
    )
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return InvoiceEmailService(
        ses_email_service=ses,
        contact_service=contact_svc,
        parameter_service=param_svc,
        email_verification_service=verification_svc,
    )


def _sample_invoice():
    return {
        'invoice_number': 'INV-2026-0001',
        'invoice_date': '2026-04-15',
        'due_date': '2026-05-15',
        'payment_terms_days': 30,
        'grand_total': 1250.00,
        'contact': {
            'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp B.V.',
        },
    }


# ── Test: Verified tenant uses tenant email as sender ───────


@pytest.mark.unit
class TestVerifiedTenantSender:
    """Requirement 4.1: Verified tenant email used as From address.
    Requirement 4.2: Company name used as display name.
    """

    def test_verified_tenant_uses_tenant_email_as_source(self):
        """When tenant is verified, source_email is the tenant's email."""
        ses = _make_ses()
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com', company_name='Acme'
        )
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        svc.send_invoice_email('T1', _sample_invoice(), [])

        call_kwargs = ses.send_email_with_attachments.call_args[1]
        assert call_kwargs['source_email'] == 'tenant@example.com'

    def test_verified_tenant_uses_company_name_as_from_name(self):
        """When tenant is verified, from_name is the company name."""
        ses = _make_ses()
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com', company_name='Acme Corp'
        )
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        svc.send_invoice_email('T1', _sample_invoice(), [])

        call_kwargs = ses.send_email_with_attachments.call_args[1]
        assert call_kwargs['from_name'] == 'Acme Corp'

    def test_verified_tenant_no_explicit_reply_to(self):
        """When tenant is verified, reply_to is None (replies go to sender)."""
        ses = _make_ses()
        verification_svc = _make_verification_service(verified=True)
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        svc.send_invoice_email('T1', _sample_invoice(), [])

        call_kwargs = ses.send_email_with_attachments.call_args[1]
        assert call_kwargs['reply_to'] is None

    def test_verified_tenant_falls_back_to_tenant_id_when_no_company_name(self):
        """When company_name is None, from_name falls back to tenant identifier."""
        ses = _make_ses()
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com', company_name=None
        )
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        svc.send_invoice_email('T1', _sample_invoice(), [])

        call_kwargs = ses.send_email_with_attachments.call_args[1]
        assert call_kwargs['from_name'] == 'T1'


# ── Test: Non-verified tenant uses fallback with Reply-To ───


@pytest.mark.unit
class TestNonVerifiedTenantFallback:
    """Requirement 4.3: Non-verified tenant uses fallback sender with Reply-To."""

    def test_non_verified_tenant_uses_fallback_sender_name(self):
        """When not verified, from_name is the fallback sender name."""
        ses = _make_ses()
        verification_svc = _make_verification_service(verified=False)
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        svc.send_invoice_email('T1', _sample_invoice(), [])

        call_kwargs = ses.send_email_with_attachments.call_args[1]
        assert call_kwargs['from_name'] == 'myAdmin'

    def test_non_verified_tenant_source_email_is_none(self):
        """When not verified, source_email is None (uses SES default)."""
        ses = _make_ses()
        verification_svc = _make_verification_service(verified=False)
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        svc.send_invoice_email('T1', _sample_invoice(), [])

        call_kwargs = ses.send_email_with_attachments.call_args[1]
        assert call_kwargs['source_email'] is None

    def test_non_verified_tenant_reply_to_is_tenant_email(self):
        """When not verified, reply_to is set to the tenant's contact email."""
        ses = _make_ses()
        verification_svc = _make_verification_service(verified=False)
        param_svc = Mock(get_param=Mock(side_effect=lambda ns, key, **kw:
            'admin@tenant.nl' if ns == 'zzp_branding' and key == 'contact_email' else None
        ))
        svc = _make_service(
            ses=ses, verification_svc=verification_svc, param_svc=param_svc
        )

        svc.send_invoice_email('T1', _sample_invoice(), [])

        call_kwargs = ses.send_email_with_attachments.call_args[1]
        assert call_kwargs['reply_to'] == 'admin@tenant.nl'

    def test_no_verification_service_uses_fallback(self):
        """When no verification service is injected, fallback behavior is used."""
        ses = _make_ses()
        param_svc = Mock(get_param=Mock(side_effect=lambda ns, key, **kw:
            'admin@tenant.nl' if ns == 'zzp_branding' and key == 'contact_email'
            else 'Tenant Co' if key == 'company_name' else None
        ))
        svc = _make_service(ses=ses, verification_svc=None, param_svc=param_svc)

        svc.send_invoice_email('T1', _sample_invoice(), [])

        call_kwargs = ses.send_email_with_attachments.call_args[1]
        assert call_kwargs['source_email'] is None
        assert call_kwargs['reply_to'] == 'admin@tenant.nl'


# ── Test: Error recovery retries with fallback ──────────────


@pytest.mark.unit
class TestErrorRecoveryWithFallback:
    """Requirement 6.1: On MessageRejected/MailFromDomainNotVerified,
    retry with fallback sender.
    """

    def test_message_rejected_triggers_retry_with_fallback(self):
        """MessageRejected error triggers retry with fallback sender."""
        ses = Mock()
        # First call fails with MessageRejected, second succeeds
        ses.send_email_with_attachments = Mock(side_effect=[
            {'success': False, 'error': 'MessageRejected: Email address not verified'},
            {'success': True, 'message_id': 'retry-msg-123'},
        ])
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com'
        )
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        result = svc.send_invoice_email('T1', _sample_invoice(), [])

        assert result['success'] is True
        assert result['message_id'] == 'retry-msg-123'
        # Verify retry used fallback sender
        retry_kwargs = ses.send_email_with_attachments.call_args_list[1][1]
        assert retry_kwargs['source_email'] is None
        assert retry_kwargs['from_name'] == 'myAdmin'

    def test_mail_from_domain_not_verified_triggers_retry(self):
        """MailFromDomainNotVerified error triggers retry with fallback."""
        ses = Mock()
        ses.send_email_with_attachments = Mock(side_effect=[
            {'success': False, 'error': 'MailFromDomainNotVerified: not verified'},
            {'success': True, 'message_id': 'retry-456'},
        ])
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com'
        )
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        result = svc.send_invoice_email('T1', _sample_invoice(), [])

        assert result['success'] is True
        assert ses.send_email_with_attachments.call_count == 2

    def test_non_verification_error_does_not_retry(self):
        """Non-verification errors (e.g., throttling) do not trigger retry."""
        ses = _make_ses(success=False, error='Throttling: Rate exceeded')
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com'
        )
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        result = svc.send_invoice_email('T1', _sample_invoice(), [])

        assert result['success'] is False
        assert 'Throttling' in result['error']
        # Only one call — no retry
        assert ses.send_email_with_attachments.call_count == 1

    def test_fallback_not_triggered_when_already_using_fallback(self):
        """When source_email is None (already fallback), no retry occurs."""
        ses = _make_ses(success=False, error='MessageRejected: something')
        verification_svc = _make_verification_service(verified=False)
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        result = svc.send_invoice_email('T1', _sample_invoice(), [])

        # No retry because source_email was None (fallback sender)
        assert result['success'] is False
        assert ses.send_email_with_attachments.call_count == 1

    def test_error_recovery_sets_reply_to_on_retry(self):
        """Retry with fallback sets Reply-To to tenant's contact email."""
        ses = Mock()
        ses.send_email_with_attachments = Mock(side_effect=[
            {'success': False, 'error': 'MessageRejected: not verified'},
            {'success': True, 'message_id': 'retry-789'},
        ])
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com'
        )
        param_svc = Mock(get_param=Mock(side_effect=lambda ns, key, **kw:
            'admin@tenant.nl' if ns == 'zzp_branding' and key == 'contact_email' else None
        ))
        svc = _make_service(
            ses=ses, verification_svc=verification_svc, param_svc=param_svc
        )

        svc.send_invoice_email('T1', _sample_invoice(), [])

        retry_kwargs = ses.send_email_with_attachments.call_args_list[1][1]
        assert retry_kwargs['reply_to'] == 'admin@tenant.nl'


# ── Test: mark_expired called on send failure ───────────────


@pytest.mark.unit
class TestMarkExpiredOnSendFailure:
    """Requirement 6.2: On verification-related send failure,
    mark_expired() is called to update status to expired.
    Requirement 6.3: Warning logged with tenant identifier and email.
    """

    def test_mark_expired_called_on_message_rejected(self):
        """mark_expired is called when MessageRejected error occurs."""
        ses = Mock()
        ses.send_email_with_attachments = Mock(side_effect=[
            {'success': False, 'error': 'MessageRejected: Email not verified'},
            {'success': True, 'message_id': 'retry-123'},
        ])
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com'
        )
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        svc.send_invoice_email('T1', _sample_invoice(), [])

        verification_svc.mark_expired.assert_called_once_with(
            'T1', 'tenant@example.com'
        )

    def test_mark_expired_called_on_mail_from_domain_not_verified(self):
        """mark_expired is called when MailFromDomainNotVerified error occurs."""
        ses = Mock()
        ses.send_email_with_attachments = Mock(side_effect=[
            {'success': False, 'error': 'MailFromDomainNotVerified: domain issue'},
            {'success': True, 'message_id': 'retry-456'},
        ])
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com'
        )
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        svc.send_invoice_email('T1', _sample_invoice(), [])

        verification_svc.mark_expired.assert_called_once_with(
            'T1', 'tenant@example.com'
        )

    def test_mark_expired_not_called_on_non_verification_error(self):
        """mark_expired is NOT called for non-verification errors."""
        ses = _make_ses(success=False, error='Throttling: Rate exceeded')
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com'
        )
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        svc.send_invoice_email('T1', _sample_invoice(), [])

        verification_svc.mark_expired.assert_not_called()

    def test_mark_expired_not_called_when_using_fallback_sender(self):
        """mark_expired is NOT called when already using fallback (not verified)."""
        ses = _make_ses(success=False, error='MessageRejected: something')
        verification_svc = _make_verification_service(verified=False)
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        svc.send_invoice_email('T1', _sample_invoice(), [])

        verification_svc.mark_expired.assert_not_called()

    def test_warning_logged_on_verification_error(self):
        """A warning is logged with tenant identifier and email on error."""
        ses = Mock()
        ses.send_email_with_attachments = Mock(side_effect=[
            {'success': False, 'error': 'MessageRejected: Email not verified'},
            {'success': True, 'message_id': 'retry-123'},
        ])
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com'
        )
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        with patch('services.invoice_email_service.logger') as mock_logger:
            svc.send_invoice_email('T1', _sample_invoice(), [])

            # Verify warning was logged with tenant and email info
            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert 'T1' in warning_msg
            assert 'tenant@example.com' in warning_msg

    def test_reminder_email_also_triggers_error_recovery(self):
        """send_reminder_email also triggers error recovery on verification error."""
        ses = Mock()
        ses.send_email_with_attachments = Mock(side_effect=[
            {'success': False, 'error': 'MessageRejected: not verified'},
            {'success': True, 'message_id': 'reminder-retry-123'},
        ])
        verification_svc = _make_verification_service(
            verified=True, email='tenant@example.com'
        )
        svc = _make_service(ses=ses, verification_svc=verification_svc)

        result = svc.send_reminder_email('T1', _sample_invoice())

        assert result['success'] is True
        verification_svc.mark_expired.assert_called_once_with(
            'T1', 'tenant@example.com'
        )
