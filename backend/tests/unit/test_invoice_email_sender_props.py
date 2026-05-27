"""
Property-based tests for InvoiceEmailService sender resolution and error recovery.

Uses Hypothesis to verify correctness properties from the design document.
Feature: ses-email-verification, Properties 6, 7, 10

Requirements: 4.1, 4.2, 4.3, 5.4, 6.1, 6.2
Reference: .kiro/specs/ses-email-verification/design.md
"""

import os
import sys
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.invoice_email_service import InvoiceEmailService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for tenant identifiers (alphanumeric with hyphens/underscores)
tenant_id_st = st.from_regex(r'[a-zA-Z][a-zA-Z0-9_\-]{2,30}', fullmatch=True)

# Strategy for valid email addresses
valid_local_chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
valid_local_part_st = st.text(alphabet=valid_local_chars, min_size=1, max_size=20)
domain_label_st = st.from_regex(r'[a-z][a-z0-9]{1,10}', fullmatch=True)
tld_st = st.from_regex(r'[a-z]{2,4}', fullmatch=True)

valid_email_st = st.builds(
    lambda local, domain, tld: f"{local}@{domain}.{tld}",
    local=valid_local_part_st,
    domain=domain_label_st,
    tld=tld_st,
)

# Strategy for company names (non-empty strings)
company_name_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Zs'),
                           whitelist_characters='-&.'),
    min_size=1, max_size=50,
).filter(lambda s: s.strip() != '')

# Strategy for non-verified statuses
non_verified_status_st = st.sampled_from(['pending', 'failed', 'expired'])

# Strategy for SES verification-related error codes
verification_error_code_st = st.sampled_from([
    'MessageRejected', 'MailFromDomainNotVerified'
])

# Strategy for non-verification error codes (should NOT trigger fallback)
non_verification_error_code_st = st.sampled_from([
    'Throttling', 'ServiceUnavailable', 'InvalidParameterValue',
    'AccountSendingPaused', 'ConfigurationSetDoesNotExist',
])


# ---------------------------------------------------------------------------
# Property 6: Verified sender resolution
# Feature: ses-email-verification, Property 6: Verified sender resolution
# Validates: Requirements 4.1, 4.2
# ---------------------------------------------------------------------------

class TestVerifiedSenderResolution:
    """
    Property 6: Verified sender resolution

    For any tenant whose verification status is `verified`, the
    get_verified_sender method SHALL return verified=True with the tenant's
    email address and company name, and _resolve_sender SHALL use the
    tenant's email as the SES Source with company name as display name.

    Feature: ses-email-verification, Property 6: Verified sender resolution
    **Validates: Requirements 4.1, 4.2**
    """

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Create InvoiceEmailService with mocked dependencies."""
        self.mock_ses = MagicMock()
        self.mock_contact_service = MagicMock()
        self.mock_parameter_service = MagicMock()
        self.mock_verification_service = MagicMock()

        self.service = InvoiceEmailService(
            ses_email_service=self.mock_ses,
            contact_service=self.mock_contact_service,
            parameter_service=self.mock_parameter_service,
            email_verification_service=self.mock_verification_service,
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        email=valid_email_st,
        company_name=company_name_st,
    )
    def test_verified_tenant_uses_tenant_email_as_source(
        self, tenant, email, company_name
    ):
        """
        Feature: ses-email-verification, Property 6: Verified sender resolution

        For any verified tenant, _resolve_sender returns the tenant's email
        as source_email and company name as from_name.
        """
        # Mock verification service to return verified status
        self.mock_verification_service.get_verified_sender.return_value = {
            'verified': True,
            'email': email,
            'company_name': company_name,
        }

        result = self.service._resolve_sender(tenant)

        assert result['source_email'] == email, (
            f"Expected source_email='{email}', got '{result['source_email']}'"
        )
        assert result['from_name'] == company_name, (
            f"Expected from_name='{company_name}', got '{result['from_name']}'"
        )
        assert result['reply_to'] is None, (
            f"Expected reply_to=None for verified sender, got '{result['reply_to']}'"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        email=valid_email_st,
    )
    def test_verified_tenant_without_company_name_uses_tenant_id(
        self, tenant, email
    ):
        """
        Feature: ses-email-verification, Property 6: Verified sender resolution

        For any verified tenant without a company_name, _resolve_sender
        falls back to using the tenant identifier as from_name.
        """
        # Mock verification service to return verified but no company name
        self.mock_verification_service.get_verified_sender.return_value = {
            'verified': True,
            'email': email,
            'company_name': None,
        }

        result = self.service._resolve_sender(tenant)

        assert result['source_email'] == email, (
            f"Expected source_email='{email}', got '{result['source_email']}'"
        )
        assert result['from_name'] == tenant, (
            f"Expected from_name='{tenant}' (fallback to tenant id), "
            f"got '{result['from_name']}'"
        )


# ---------------------------------------------------------------------------
# Property 7: Fallback sender for non-verified tenants
# Feature: ses-email-verification, Property 7: Fallback sender for non-verified tenants
# Validates: Requirements 4.3, 5.4
# ---------------------------------------------------------------------------

class TestFallbackSenderForNonVerifiedTenants:
    """
    Property 7: Fallback sender for non-verified tenants

    For any tenant whose verification status is NOT verified (pending, failed,
    expired, or no record), the get_verified_sender method SHALL return
    verified=False, causing the invoice service to use the fallback sender
    address with Reply-To set to the tenant's email.

    Feature: ses-email-verification, Property 7: Fallback sender for non-verified tenants
    **Validates: Requirements 4.3, 5.4**
    """

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Create InvoiceEmailService with mocked dependencies."""
        self.mock_ses = MagicMock()
        self.mock_contact_service = MagicMock()
        self.mock_parameter_service = MagicMock()
        self.mock_verification_service = MagicMock()

        self.service = InvoiceEmailService(
            ses_email_service=self.mock_ses,
            contact_service=self.mock_contact_service,
            parameter_service=self.mock_parameter_service,
            email_verification_service=self.mock_verification_service,
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        tenant_email=valid_email_st,
        status=non_verified_status_st,
    )
    def test_non_verified_tenant_uses_fallback_sender(
        self, tenant, tenant_email, status
    ):
        """
        Feature: ses-email-verification, Property 7: Fallback sender for non-verified tenants

        For any non-verified status (pending, failed, expired), _resolve_sender
        returns the fallback sender name and sets reply_to to the tenant's email.
        """
        # Mock verification service to return non-verified status
        self.mock_verification_service.get_verified_sender.return_value = {
            'verified': False,
            'email': None,
            'company_name': None,
        }

        # Mock parameter service to return tenant email for reply-to
        self.mock_parameter_service.get_param.return_value = tenant_email

        result = self.service._resolve_sender(tenant)

        assert result['source_email'] is None, (
            f"Expected source_email=None for non-verified tenant (status={status}), "
            f"got '{result['source_email']}'"
        )
        assert result['from_name'] == InvoiceEmailService.FALLBACK_SENDER_NAME, (
            f"Expected from_name='{InvoiceEmailService.FALLBACK_SENDER_NAME}', "
            f"got '{result['from_name']}'"
        )
        assert result['reply_to'] == tenant_email, (
            f"Expected reply_to='{tenant_email}', got '{result['reply_to']}'"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(tenant=tenant_id_st)
    def test_no_verification_record_uses_fallback_sender(self, tenant):
        """
        Feature: ses-email-verification, Property 7: Fallback sender for non-verified tenants

        When no verification record exists (get_verified_sender returns
        verified=False), the fallback sender is used.
        """
        # Mock verification service to return no record
        self.mock_verification_service.get_verified_sender.return_value = {
            'verified': False,
            'email': None,
            'company_name': None,
        }

        # Mock parameter service to return None (no tenant email configured)
        self.mock_parameter_service.get_param.return_value = None

        result = self.service._resolve_sender(tenant)

        assert result['source_email'] is None, (
            f"Expected source_email=None for tenant with no record, "
            f"got '{result['source_email']}'"
        )
        assert result['from_name'] == InvoiceEmailService.FALLBACK_SENDER_NAME, (
            f"Expected from_name='{InvoiceEmailService.FALLBACK_SENDER_NAME}', "
            f"got '{result['from_name']}'"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        tenant_email=valid_email_st,
    )
    def test_no_verification_service_uses_fallback(self, tenant, tenant_email):
        """
        Feature: ses-email-verification, Property 7: Fallback sender for non-verified tenants

        When no EmailVerificationService is configured, the service uses
        fallback behavior (no source_email, reply_to set to tenant email).
        """
        # Create service without verification service
        service = InvoiceEmailService(
            ses_email_service=self.mock_ses,
            contact_service=self.mock_contact_service,
            parameter_service=self.mock_parameter_service,
            email_verification_service=None,
        )

        # Mock parameter service to return tenant email
        self.mock_parameter_service.get_param.return_value = tenant_email

        result = service._resolve_sender(tenant)

        assert result['source_email'] is None, (
            f"Expected source_email=None when no verification service, "
            f"got '{result['source_email']}'"
        )
        assert result['reply_to'] == tenant_email, (
            f"Expected reply_to='{tenant_email}', got '{result['reply_to']}'"
        )


# ---------------------------------------------------------------------------
# Property 10: Error recovery with fallback and expiry
# Feature: ses-email-verification, Property 10: Error recovery with fallback and expiry
# Validates: Requirements 6.1, 6.2
# ---------------------------------------------------------------------------

class TestErrorRecoveryWithFallbackAndExpiry:
    """
    Property 10: Error recovery with fallback and expiry

    For any SES send error of type MessageRejected or MailFromDomainNotVerified
    when sending from a tenant's verified email, the service SHALL (a) retry
    the send using the fallback sender and (b) update the tenant's verification
    status to expired.

    Feature: ses-email-verification, Property 10: Error recovery with fallback and expiry
    **Validates: Requirements 6.1, 6.2**
    """

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Create InvoiceEmailService with mocked dependencies."""
        self.mock_ses = MagicMock()
        self.mock_contact_service = MagicMock()
        self.mock_parameter_service = MagicMock()
        self.mock_verification_service = MagicMock()

        self.service = InvoiceEmailService(
            ses_email_service=self.mock_ses,
            contact_service=self.mock_contact_service,
            parameter_service=self.mock_parameter_service,
            email_verification_service=self.mock_verification_service,
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        verified_email=valid_email_st,
        error_code=verification_error_code_st,
    )
    def test_verification_error_triggers_retry_with_fallback(
        self, tenant, verified_email, error_code
    ):
        """
        Feature: ses-email-verification, Property 10: Error recovery with fallback and expiry

        For any SES error of type MessageRejected or MailFromDomainNotVerified,
        _handle_send_error_with_fallback retries with the fallback sender.
        """
        # Reset mocks between hypothesis iterations
        self.mock_ses.reset_mock()
        self.mock_verification_service.reset_mock()

        # Simulate a failed send result with a verification error
        failed_result = {
            'success': False,
            'error': f"{error_code}: Email address is not verified",
        }

        # Mock the retry to succeed
        retry_result = {'success': True, 'message_id': 'retry-msg-123'}
        self.mock_ses.send_email_with_attachments.return_value = retry_result

        # Mock parameter service for reply-to resolution
        self.mock_parameter_service.get_param.return_value = 'admin@tenant.com'

        result = self.service._handle_send_error_with_fallback(
            result=failed_result,
            tenant=tenant,
            verified_email=verified_email,
            to_email='recipient@example.com',
            subject='Test Subject',
            html_body='<p>Test</p>',
            attachments=[],
            bcc=[],
            email_type='invoice',
            sent_by='test-user',
        )

        # Verify retry was attempted with fallback sender
        assert result['success'] is True, (
            f"Expected retry to succeed for error '{error_code}', "
            f"got: {result}"
        )
        self.mock_ses.send_email_with_attachments.assert_called_once()
        call_kwargs = self.mock_ses.send_email_with_attachments.call_args
        assert call_kwargs.kwargs.get('source_email') is None, (
            "Retry should use fallback sender (source_email=None)"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        verified_email=valid_email_st,
        error_code=verification_error_code_st,
    )
    def test_verification_error_marks_status_as_expired(
        self, tenant, verified_email, error_code
    ):
        """
        Feature: ses-email-verification, Property 10: Error recovery with fallback and expiry

        For any SES verification error, mark_expired is called to update
        the tenant's verification status to expired.
        """
        # Reset mocks between hypothesis iterations
        self.mock_ses.reset_mock()
        self.mock_verification_service.reset_mock()

        # Simulate a failed send result with a verification error
        failed_result = {
            'success': False,
            'error': f"{error_code}: Email address is not verified",
        }

        # Mock the retry to succeed
        self.mock_ses.send_email_with_attachments.return_value = {
            'success': True, 'message_id': 'retry-msg-123'
        }
        self.mock_parameter_service.get_param.return_value = 'admin@tenant.com'

        self.service._handle_send_error_with_fallback(
            result=failed_result,
            tenant=tenant,
            verified_email=verified_email,
            to_email='recipient@example.com',
            subject='Test Subject',
            html_body='<p>Test</p>',
            attachments=[],
            bcc=[],
            email_type='invoice',
            sent_by='test-user',
        )

        # Verify mark_expired was called with correct arguments
        self.mock_verification_service.mark_expired.assert_called_once_with(
            tenant, verified_email
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        verified_email=valid_email_st,
        error_code=non_verification_error_code_st,
    )
    def test_non_verification_error_does_not_trigger_fallback(
        self, tenant, verified_email, error_code
    ):
        """
        Feature: ses-email-verification, Property 10: Error recovery with fallback and expiry

        For any SES error that is NOT MessageRejected or MailFromDomainNotVerified,
        the original error result is returned without retry or expiry marking.
        """
        # Simulate a failed send result with a non-verification error
        failed_result = {
            'success': False,
            'error': f"{error_code}: Some other error",
        }

        result = self.service._handle_send_error_with_fallback(
            result=failed_result,
            tenant=tenant,
            verified_email=verified_email,
            to_email='recipient@example.com',
            subject='Test Subject',
            html_body='<p>Test</p>',
            attachments=[],
            bcc=[],
            email_type='invoice',
            sent_by='test-user',
        )

        # Verify no retry was attempted
        self.mock_ses.send_email_with_attachments.assert_not_called()

        # Verify mark_expired was NOT called
        self.mock_verification_service.mark_expired.assert_not_called()

        # Original result returned unchanged
        assert result == failed_result, (
            f"Expected original result for non-verification error '{error_code}', "
            f"got: {result}"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        verified_email=valid_email_st,
        error_code=verification_error_code_st,
        tenant_reply_email=valid_email_st,
    )
    def test_fallback_retry_uses_correct_reply_to(
        self, tenant, verified_email, error_code, tenant_reply_email
    ):
        """
        Feature: ses-email-verification, Property 10: Error recovery with fallback and expiry

        When retrying with fallback, the reply_to is set to the tenant's
        contact email so recipients can still reply to the tenant.
        """
        failed_result = {
            'success': False,
            'error': f"{error_code}: Email address is not verified",
        }

        # Mock the retry to succeed
        self.mock_ses.send_email_with_attachments.return_value = {
            'success': True, 'message_id': 'retry-msg-123'
        }

        # Mock parameter service to return tenant reply email
        self.mock_parameter_service.get_param.return_value = tenant_reply_email

        self.service._handle_send_error_with_fallback(
            result=failed_result,
            tenant=tenant,
            verified_email=verified_email,
            to_email='recipient@example.com',
            subject='Test Subject',
            html_body='<p>Test</p>',
            attachments=[],
            bcc=[],
            email_type='invoice',
            sent_by='test-user',
        )

        # Verify the retry call used the tenant email as reply_to
        call_kwargs = self.mock_ses.send_email_with_attachments.call_args
        # Check keyword arguments
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs['reply_to'] == tenant_reply_email, (
                f"Expected reply_to='{tenant_reply_email}' in fallback retry, "
                f"got '{call_kwargs.kwargs.get('reply_to')}'"
            )
        else:
            # Positional args - reply_to is the 6th argument (index 5)
            assert call_kwargs[1]['reply_to'] == tenant_reply_email, (
                f"Expected reply_to='{tenant_reply_email}' in fallback retry"
            )
