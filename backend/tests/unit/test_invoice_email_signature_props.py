"""
Property-based tests for InvoiceEmailService signature block builder.

Uses Hypothesis to verify correctness properties from the design document.
Feature: ses-email-verification, Properties 12, 13, 14

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.7
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

# Strategy for company names (non-empty printable strings)
company_name_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Zs'),
                           whitelist_characters='-&.'),
    min_size=1, max_size=50,
).filter(lambda s: s.strip() != '')

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

# Strategy for base64 data URIs (simulating logo data)
logo_data_uri_st = st.builds(
    lambda content: f"data:image/png;base64,{content}",
    content=st.from_regex(r'[A-Za-z0-9+/]{20,60}={0,2}', fullmatch=True),
)

# Strategy for locales — nl_NL vs other locales
nl_locale_st = st.just('nl_NL')
non_nl_locale_st = st.sampled_from([
    'en_US', 'en_GB', 'de_DE', 'fr_FR', 'nl_BE', 'es_ES', 'it_IT',
    'pt_BR', 'ja_JP', 'zh_CN',
])
any_locale_st = st.one_of(nl_locale_st, non_nl_locale_st)


# ---------------------------------------------------------------------------
# Property 12: Signature block contains required branding fields
# Feature: ses-email-verification, Property 12: Signature block contains required branding fields
# Validates: Requirements 9.1, 9.2, 9.3
# ---------------------------------------------------------------------------

class TestSignatureBlockContainsBrandingFields:
    """
    Property 12: Signature block contains required branding fields

    For any tenant with configured zzp_branding.company_name and
    zzp_branding.contact_email parameters, the generated signature block
    HTML SHALL contain both the company name and the contact email address.

    Feature: ses-email-verification, Property 12: Signature block contains required branding fields
    **Validates: Requirements 9.1, 9.2, 9.3**
    """

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Create InvoiceEmailService with mocked dependencies."""
        self.mock_ses = MagicMock()
        self.mock_contact_service = MagicMock()
        self.mock_parameter_service = MagicMock()

        self.service = InvoiceEmailService(
            ses_email_service=self.mock_ses,
            contact_service=self.mock_contact_service,
            parameter_service=self.mock_parameter_service,
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        company_name=company_name_st,
        contact_email=valid_email_st,
        locale=any_locale_st,
    )
    def test_signature_contains_company_name_and_email(
        self, tenant, company_name, contact_email, locale
    ):
        """
        Feature: ses-email-verification, Property 12: Signature block contains required branding fields

        For any tenant with configured company_name and contact_email,
        the signature HTML contains both values.
        """
        # Mock parameter service to return branding values
        def get_param_side_effect(namespace, key, tenant=None):
            if namespace == 'zzp_branding' and key == 'company_name':
                return company_name
            if namespace == 'zzp_branding' and key == 'contact_email':
                return contact_email
            return None

        self.mock_parameter_service.get_param.side_effect = get_param_side_effect

        # Mock logo resolver to return None (no logo)
        with patch('services.invoice_email_service.resolve_tenant_logo', return_value=None):
            result = self.service._build_signature_block(tenant, locale)

        # Signature must be non-empty
        assert result != '', (
            "Expected non-empty signature block when branding params are configured"
        )

        # Company name must appear in the HTML
        assert company_name in result, (
            f"Expected company_name '{company_name}' in signature HTML, "
            f"but it was not found. HTML: {result[:200]}"
        )

        # Contact email must appear in the HTML
        assert contact_email in result, (
            f"Expected contact_email '{contact_email}' in signature HTML, "
            f"but it was not found. HTML: {result[:200]}"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        company_name=company_name_st,
        contact_email=valid_email_st,
        logo_uri=logo_data_uri_st,
        locale=any_locale_st,
    )
    def test_signature_contains_branding_fields_with_logo(
        self, tenant, company_name, contact_email, logo_uri, locale
    ):
        """
        Feature: ses-email-verification, Property 12: Signature block contains required branding fields

        For any tenant with configured company_name, contact_email, and logo,
        the signature HTML still contains both branding text values.
        """
        def get_param_side_effect(namespace, key, tenant=None):
            if namespace == 'zzp_branding' and key == 'company_name':
                return company_name
            if namespace == 'zzp_branding' and key == 'contact_email':
                return contact_email
            return None

        self.mock_parameter_service.get_param.side_effect = get_param_side_effect

        with patch('services.invoice_email_service.resolve_tenant_logo', return_value=logo_uri):
            result = self.service._build_signature_block(tenant, locale)

        assert company_name in result, (
            f"Expected company_name '{company_name}' in signature HTML with logo"
        )
        assert contact_email in result, (
            f"Expected contact_email '{contact_email}' in signature HTML with logo"
        )


# ---------------------------------------------------------------------------
# Property 13: Conditional logo inclusion in signature
# Feature: ses-email-verification, Property 13: Conditional logo inclusion in signature
# Validates: Requirements 9.4, 9.5
# ---------------------------------------------------------------------------

class TestConditionalLogoInclusion:
    """
    Property 13: Conditional logo inclusion in signature

    For any tenant with a configured branding logo, the signature block SHALL
    contain a base64-encoded <img> tag. For any tenant without a configured
    logo, the signature block SHALL NOT contain an <img> tag but SHALL still
    contain the company name and email.

    Feature: ses-email-verification, Property 13: Conditional logo inclusion in signature
    **Validates: Requirements 9.4, 9.5**
    """

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Create InvoiceEmailService with mocked dependencies."""
        self.mock_ses = MagicMock()
        self.mock_contact_service = MagicMock()
        self.mock_parameter_service = MagicMock()

        self.service = InvoiceEmailService(
            ses_email_service=self.mock_ses,
            contact_service=self.mock_contact_service,
            parameter_service=self.mock_parameter_service,
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        company_name=company_name_st,
        contact_email=valid_email_st,
        logo_uri=logo_data_uri_st,
        locale=any_locale_st,
    )
    def test_logo_present_when_resolver_returns_data_uri(
        self, tenant, company_name, contact_email, logo_uri, locale
    ):
        """
        Feature: ses-email-verification, Property 13: Conditional logo inclusion in signature

        When resolve_tenant_logo returns a data URI, the signature contains
        an <img> tag with that data URI.
        """
        def get_param_side_effect(namespace, key, tenant=None):
            if namespace == 'zzp_branding' and key == 'company_name':
                return company_name
            if namespace == 'zzp_branding' and key == 'contact_email':
                return contact_email
            return None

        self.mock_parameter_service.get_param.side_effect = get_param_side_effect

        with patch('services.invoice_email_service.resolve_tenant_logo', return_value=logo_uri):
            result = self.service._build_signature_block(tenant, locale)

        # Must contain an <img tag
        assert '<img' in result, (
            f"Expected <img> tag in signature when logo is available, "
            f"but not found. HTML: {result[:200]}"
        )

        # The img src must contain the logo data URI
        assert logo_uri in result, (
            f"Expected logo data URI in <img> src attribute, "
            f"but not found. HTML: {result[:200]}"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        company_name=company_name_st,
        contact_email=valid_email_st,
        locale=any_locale_st,
    )
    def test_no_img_tag_when_no_logo(
        self, tenant, company_name, contact_email, locale
    ):
        """
        Feature: ses-email-verification, Property 13: Conditional logo inclusion in signature

        When resolve_tenant_logo returns None, the signature does NOT contain
        an <img> tag but still contains company_name and contact_email.
        """
        def get_param_side_effect(namespace, key, tenant=None):
            if namespace == 'zzp_branding' and key == 'company_name':
                return company_name
            if namespace == 'zzp_branding' and key == 'contact_email':
                return contact_email
            return None

        self.mock_parameter_service.get_param.side_effect = get_param_side_effect

        with patch('services.invoice_email_service.resolve_tenant_logo', return_value=None):
            result = self.service._build_signature_block(tenant, locale)

        # Must NOT contain an <img tag
        assert '<img' not in result, (
            f"Expected NO <img> tag in signature when no logo, "
            f"but found one. HTML: {result[:200]}"
        )

        # Must still contain branding fields
        assert company_name in result, (
            f"Expected company_name '{company_name}' in signature without logo"
        )
        assert contact_email in result, (
            f"Expected contact_email '{contact_email}' in signature without logo"
        )


# ---------------------------------------------------------------------------
# Property 14: Locale-aware signature greeting
# Feature: ses-email-verification, Property 14: Locale-aware signature greeting
# Validates: Requirements 9.7
# ---------------------------------------------------------------------------

class TestLocaleAwareSignatureGreeting:
    """
    Property 14: Locale-aware signature greeting

    For any email composed with locale nl_NL, the signature block SHALL
    contain "Met vriendelijke groet,". For any email composed with any other
    locale, the signature block SHALL contain "Kind regards,".

    Feature: ses-email-verification, Property 14: Locale-aware signature greeting
    **Validates: Requirements 9.7**
    """

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Create InvoiceEmailService with mocked dependencies."""
        self.mock_ses = MagicMock()
        self.mock_contact_service = MagicMock()
        self.mock_parameter_service = MagicMock()

        self.service = InvoiceEmailService(
            ses_email_service=self.mock_ses,
            contact_service=self.mock_contact_service,
            parameter_service=self.mock_parameter_service,
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        company_name=company_name_st,
        contact_email=valid_email_st,
    )
    def test_nl_locale_uses_dutch_greeting(
        self, tenant, company_name, contact_email
    ):
        """
        Feature: ses-email-verification, Property 14: Locale-aware signature greeting

        For locale nl_NL, the signature contains "Met vriendelijke groet,".
        """
        def get_param_side_effect(namespace, key, tenant=None):
            if namespace == 'zzp_branding' and key == 'company_name':
                return company_name
            if namespace == 'zzp_branding' and key == 'contact_email':
                return contact_email
            return None

        self.mock_parameter_service.get_param.side_effect = get_param_side_effect

        with patch('services.invoice_email_service.resolve_tenant_logo', return_value=None):
            result = self.service._build_signature_block(tenant, 'nl_NL')

        assert 'Met vriendelijke groet,' in result, (
            f"Expected 'Met vriendelijke groet,' in signature for nl_NL locale, "
            f"but not found. HTML: {result[:200]}"
        )
        # Should NOT contain the English greeting
        assert 'Kind regards,' not in result, (
            f"Expected NO 'Kind regards,' in signature for nl_NL locale, "
            f"but found it. HTML: {result[:200]}"
        )

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        tenant=tenant_id_st,
        company_name=company_name_st,
        contact_email=valid_email_st,
        locale=non_nl_locale_st,
    )
    def test_non_nl_locale_uses_english_greeting(
        self, tenant, company_name, contact_email, locale
    ):
        """
        Feature: ses-email-verification, Property 14: Locale-aware signature greeting

        For any locale other than nl_NL, the signature contains "Kind regards,".
        """
        def get_param_side_effect(namespace, key, tenant=None):
            if namespace == 'zzp_branding' and key == 'company_name':
                return company_name
            if namespace == 'zzp_branding' and key == 'contact_email':
                return contact_email
            return None

        self.mock_parameter_service.get_param.side_effect = get_param_side_effect

        with patch('services.invoice_email_service.resolve_tenant_logo', return_value=None):
            result = self.service._build_signature_block(tenant, locale)

        assert 'Kind regards,' in result, (
            f"Expected 'Kind regards,' in signature for locale '{locale}', "
            f"but not found. HTML: {result[:200]}"
        )
        # Should NOT contain the Dutch greeting
        assert 'Met vriendelijke groet,' not in result, (
            f"Expected NO 'Met vriendelijke groet,' in signature for locale '{locale}', "
            f"but found it. HTML: {result[:200]}"
        )
