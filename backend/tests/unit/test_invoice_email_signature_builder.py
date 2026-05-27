"""Unit tests for InvoiceEmailService._build_signature_block().

Tests the branded HTML signature block generation including logo inclusion,
branding parameter fallbacks, and locale-aware greetings.

Validates: Requirements 9.1–9.7
"""

import pytest
from unittest.mock import Mock, patch

from services.invoice_email_service import InvoiceEmailService


# ── Fixtures ────────────────────────────────────────────────


def _make_param_service(company_name='Acme Corp', contact_email='info@acme.nl'):
    """Create a mock ParameterService returning branding params."""
    def get_param(namespace, key, **kwargs):
        if namespace == 'zzp_branding' and key == 'company_name':
            return company_name
        if namespace == 'zzp_branding' and key == 'contact_email':
            return contact_email
        return None

    svc = Mock()
    svc.get_param = Mock(side_effect=get_param)
    return svc


def _make_service(param_svc=None):
    """Create an InvoiceEmailService with mocked dependencies."""
    ses = Mock()
    contact_svc = Mock()
    return InvoiceEmailService(
        ses_email_service=ses,
        contact_service=contact_svc,
        parameter_service=param_svc,
    )


SAMPLE_LOGO_DATA_URI = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=='


# ── Test: Signature with logo and all branding fields ───────


@pytest.mark.unit
class TestSignatureWithAllFields:
    """Requirement 9.1: Signature block appended to email body.
    Requirement 9.2: Includes company_name from zzp_branding.
    Requirement 9.3: Includes contact_email from zzp_branding.
    Requirement 9.4: Includes logo as inline base64 image when configured.
    Requirement 9.6: Visually separated by horizontal rule.
    """

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_signature_contains_company_name(self, mock_logo):
        """Signature block includes the company name."""
        mock_logo.return_value = SAMPLE_LOGO_DATA_URI
        param_svc = _make_param_service(
            company_name='Acme Corp', contact_email='info@acme.nl'
        )
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'nl_NL')

        assert 'Acme Corp' in result

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_signature_contains_contact_email(self, mock_logo):
        """Signature block includes the contact email address."""
        mock_logo.return_value = SAMPLE_LOGO_DATA_URI
        param_svc = _make_param_service(
            company_name='Acme Corp', contact_email='info@acme.nl'
        )
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'nl_NL')

        assert 'info@acme.nl' in result
        assert 'mailto:info@acme.nl' in result

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_signature_contains_logo_img_tag(self, mock_logo):
        """Signature block includes an <img> tag with the logo data URI."""
        mock_logo.return_value = SAMPLE_LOGO_DATA_URI
        param_svc = _make_param_service(
            company_name='Acme Corp', contact_email='info@acme.nl'
        )
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'nl_NL')

        assert '<img' in result
        assert SAMPLE_LOGO_DATA_URI in result

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_signature_has_horizontal_rule_separator(self, mock_logo):
        """Signature block starts with an <hr> separator."""
        mock_logo.return_value = SAMPLE_LOGO_DATA_URI
        param_svc = _make_param_service()
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'nl_NL')

        assert '<hr' in result


# ── Test: Signature without logo ────────────────────────────


@pytest.mark.unit
class TestSignatureWithoutLogo:
    """Requirement 9.5: No logo configured → no broken img tag,
    still shows company name and email.
    """

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_no_logo_omits_img_tag(self, mock_logo):
        """When no logo is configured, no <img> tag is rendered."""
        mock_logo.return_value = None
        param_svc = _make_param_service(
            company_name='Acme Corp', contact_email='info@acme.nl'
        )
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'nl_NL')

        assert '<img' not in result

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_no_logo_still_shows_company_name(self, mock_logo):
        """Without logo, company name is still present."""
        mock_logo.return_value = None
        param_svc = _make_param_service(
            company_name='Acme Corp', contact_email='info@acme.nl'
        )
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'nl_NL')

        assert 'Acme Corp' in result

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_no_logo_still_shows_contact_email(self, mock_logo):
        """Without logo, contact email is still present."""
        mock_logo.return_value = None
        param_svc = _make_param_service(
            company_name='Acme Corp', contact_email='info@acme.nl'
        )
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'nl_NL')

        assert 'info@acme.nl' in result

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_logo_fetch_exception_omits_img_tag(self, mock_logo):
        """When logo resolver raises an exception, no <img> tag is rendered."""
        mock_logo.side_effect = Exception('S3 connection error')
        param_svc = _make_param_service(
            company_name='Acme Corp', contact_email='info@acme.nl'
        )
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'nl_NL')

        assert '<img' not in result
        assert 'Acme Corp' in result


# ── Test: Missing company_name falls back to tenant identifier ──


@pytest.mark.unit
class TestSignatureMissingCompanyName:
    """Requirement 9.2 fallback: When company_name is missing,
    falls back to tenant identifier string.
    """

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_missing_company_name_uses_tenant_id(self, mock_logo):
        """When company_name is None, tenant identifier is used."""
        mock_logo.return_value = None
        param_svc = _make_param_service(
            company_name=None, contact_email='info@acme.nl'
        )
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('my-tenant-123', 'nl_NL')

        assert 'my-tenant-123' in result

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_empty_company_name_uses_tenant_id(self, mock_logo):
        """When company_name is empty string, tenant identifier is used."""
        mock_logo.return_value = None
        param_svc = _make_param_service(
            company_name='', contact_email='info@acme.nl'
        )
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('tenant-xyz', 'nl_NL')

        assert 'tenant-xyz' in result


# ── Test: Missing contact_email omits email line ────────────


@pytest.mark.unit
class TestSignatureMissingContactEmail:
    """Requirement 9.3 fallback: When contact_email is missing,
    the email line is omitted from the signature.
    """

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_missing_contact_email_omits_mailto(self, mock_logo):
        """When contact_email is None, no mailto link is rendered."""
        mock_logo.return_value = None
        param_svc = _make_param_service(
            company_name='Acme Corp', contact_email=None
        )
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'nl_NL')

        assert 'mailto:' not in result
        assert 'Acme Corp' in result

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_empty_contact_email_omits_mailto(self, mock_logo):
        """When contact_email is empty string, no mailto link is rendered."""
        mock_logo.return_value = None
        param_svc = _make_param_service(
            company_name='Acme Corp', contact_email=''
        )
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'nl_NL')

        assert 'mailto:' not in result


# ── Test: Dutch locale greeting ─────────────────────────────


@pytest.mark.unit
class TestSignatureDutchLocaleGreeting:
    """Requirement 9.7: Dutch locale uses 'Met vriendelijke groet,'."""

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_nl_nl_locale_uses_dutch_greeting(self, mock_logo):
        """Locale nl_NL produces Dutch greeting."""
        mock_logo.return_value = None
        param_svc = _make_param_service()
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'nl_NL')

        assert 'Met vriendelijke groet,' in result


# ── Test: English/other locale greeting ─────────────────────


@pytest.mark.unit
class TestSignatureEnglishLocaleGreeting:
    """Requirement 9.7: English and other locales use 'Kind regards,'."""

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_en_us_locale_uses_english_greeting(self, mock_logo):
        """Locale en_US produces English greeting."""
        mock_logo.return_value = None
        param_svc = _make_param_service()
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'en_US')

        assert 'Kind regards,' in result

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_de_de_locale_uses_english_greeting(self, mock_logo):
        """Non-Dutch locale (de_DE) falls back to English greeting."""
        mock_logo.return_value = None
        param_svc = _make_param_service()
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'de_DE')

        assert 'Kind regards,' in result
        assert 'Met vriendelijke groet,' not in result

    @patch('services.invoice_email_service.resolve_tenant_logo')
    def test_fr_fr_locale_uses_english_greeting(self, mock_logo):
        """Non-Dutch locale (fr_FR) falls back to English greeting."""
        mock_logo.return_value = None
        param_svc = _make_param_service()
        svc = _make_service(param_svc=param_svc)

        result = svc._build_signature_block('T1', 'fr_FR')

        assert 'Kind regards,' in result
