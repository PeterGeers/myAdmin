"""
Property-based tests for ZZP Invoice Email Composition.

Feature: zzp-invoice-pdf-preview
Property 9: Email body contains all required fields
Property 10: Missing contact email blocks email composition
Property 12: BCC includes tenant admin email

Validates: Requirements 8.6, 8.7, 8.9, 8.12
Reference: .kiro/specs/zzp-invoice-pdf-preview/design.md §Correctness Properties
"""

import sys
import os
import pytest
from unittest.mock import Mock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.invoice_email_service import InvoiceEmailService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate valid email-like strings for admin emails
admin_email_st = st.from_regex(
    r'[a-z][a-z0-9]{1,10}@[a-z]{2,8}\.[a-z]{2,4}', fullmatch=True
)

# Generate valid invoice dicts with contacts that have emails
invoice_number_st = st.from_regex(r'INV-20[0-9]{2}-[0-9]{4}', fullmatch=True)

company_name_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Zs')),
    min_size=2, max_size=30,
).filter(lambda s: s.strip() != '')

tenant_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N')),
    min_size=1, max_size=20,
).filter(lambda s: s.strip() != '')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(admin_email: str, recipient_email: str = 'client@example.com'):
    """Create an InvoiceEmailService with mocked dependencies.

    The parameter_service is configured to return admin_email for
    the 'zzp_branding' / 'contact_email' lookup.
    """
    ses = Mock()
    contact_svc = Mock(
        get_invoice_email=Mock(return_value=recipient_email)
    )

    def param_side_effect(namespace, key, **kwargs):
        if namespace == 'zzp_branding' and key == 'contact_email':
            return admin_email
        if namespace == 'zzp_branding' and key == 'company_name':
            return 'Test Company BV'
        return None

    param_svc = Mock(get_param=Mock(side_effect=param_side_effect))
    return InvoiceEmailService(
        ses_email_service=ses,
        contact_service=contact_svc,
        parameter_service=param_svc,
    )


def _make_invoice(invoice_number='INV-2024-0001', company_name='Acme BV'):
    """Create a valid invoice dict for email composition."""
    return {
        'invoice_number': invoice_number,
        'invoice_date': '2024-06-01',
        'due_date': '2024-07-01',
        'payment_terms_days': 30,
        'currency': 'EUR',
        'grand_total': 1210.00,
        'contact': {
            'id': 1,
            'company_name': company_name,
            'contact_person': 'Jan de Vries',
            'country': 'NL',
        },
    }


# ---------------------------------------------------------------------------
# Property 12: BCC includes tenant admin email
# Feature: zzp-invoice-pdf-preview, Property 12: BCC includes tenant admin email
#
# For any valid invoice send operation, the composed email SHALL include the
# tenant administrator's email address as a BCC recipient, so that the
# freelancer receives a copy of the sent email in their own inbox.
#
# **Validates: Requirements 8.12**
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBccIncludesTenantAdminEmail:
    """Property 12: BCC includes tenant admin email."""

    @settings(max_examples=20)
    @given(admin_email=admin_email_st)
    def test_bcc_contains_admin_email_from_branding(self, admin_email):
        """
        For any valid admin email configured in zzp_branding.contact_email,
        the composed email's bcc field contains that admin email.

        Feature: zzp-invoice-pdf-preview, Property 12: BCC includes tenant admin email
        **Validates: Requirements 8.12**
        """
        service = _make_service(admin_email=admin_email)
        invoice = _make_invoice()

        result = service.compose_email_preview('test_tenant', invoice)

        assert result['bcc'] == admin_email, (
            f"Expected BCC to be '{admin_email}', got '{result['bcc']}'"
        )

    @settings(max_examples=20)
    @given(admin_email=admin_email_st)
    def test_bcc_fallback_to_invoice_email_bcc_param(self, admin_email):
        """
        When zzp_branding.contact_email is not set, the BCC falls back to
        the zzp.invoice_email_bcc parameter value.

        Feature: zzp-invoice-pdf-preview, Property 12: BCC includes tenant admin email
        **Validates: Requirements 8.12**
        """
        ses = Mock()
        contact_svc = Mock(
            get_invoice_email=Mock(return_value='client@example.com')
        )

        def param_side_effect(namespace, key, **kwargs):
            if namespace == 'zzp_branding' and key == 'contact_email':
                return None  # Primary not set
            if namespace == 'zzp' and key == 'invoice_email_bcc':
                return admin_email  # Fallback returns admin email
            if namespace == 'zzp_branding' and key == 'company_name':
                return 'Test Company BV'
            return None

        param_svc = Mock(get_param=Mock(side_effect=param_side_effect))
        service = InvoiceEmailService(
            ses_email_service=ses,
            contact_service=contact_svc,
            parameter_service=param_svc,
        )
        invoice = _make_invoice()

        result = service.compose_email_preview('test_tenant', invoice)

        assert result['bcc'] == admin_email, (
            f"Expected BCC fallback to be '{admin_email}', "
            f"got '{result['bcc']}'"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 10
# ---------------------------------------------------------------------------

# Generate contact dicts without email fields — various company_name,
# contact_person, country values but never an email address.
contact_without_email_st = st.fixed_dictionaries({
    'id': st.integers(min_value=1, max_value=10000),
    'company_name': st.text(min_size=0, max_size=50),
    'contact_person': st.text(min_size=0, max_size=50),
    'country': st.text(min_size=0, max_size=30),
})


# ---------------------------------------------------------------------------
# Property 10: Missing contact email blocks email composition
# Feature: zzp-invoice-pdf-preview, Property 10: Missing contact email blocks email composition
#
# For any contact that has no email address configured (no email with
# email_type of invoice, no is_primary email, and no other email), calling
# compose_email_preview SHALL raise a ValueError indicating the email
# address is missing.
#
# **Validates: Requirements 8.9**
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMissingContactEmailBlocksComposition:
    """Property 10: Missing contact email blocks email composition."""

    @settings(max_examples=20)
    @given(contact=contact_without_email_st)
    def test_missing_email_raises_value_error(self, contact):
        """
        For any contact without an email address (get_invoice_email returns
        None), compose_email_preview raises ValueError with the message
        "Contact email address is missing".

        Feature: zzp-invoice-pdf-preview, Property 10: Missing contact email blocks email composition
        **Validates: Requirements 8.9**
        """
        # Mock contact_service.get_invoice_email to return None (no email found)
        ses = Mock()
        contact_svc = Mock(
            get_invoice_email=Mock(return_value=None)
        )
        param_svc = Mock(get_param=Mock(return_value='admin@test.nl'))
        service = InvoiceEmailService(
            ses_email_service=ses,
            contact_service=contact_svc,
            parameter_service=param_svc,
        )

        invoice = {
            'invoice_number': 'INV-2024-001',
            'invoice_date': '2024-01-15',
            'due_date': '2024-02-15',
            'currency': 'EUR',
            'payment_terms_days': 30,
            'subtotal': 100.0,
            'vat_total': 21.0,
            'grand_total': 121.0,
            'lines': [],
            'contact': contact,
        }

        with pytest.raises(ValueError, match="Contact email address is missing"):
            service.compose_email_preview('test_tenant', invoice)

    @settings(max_examples=20)
    @given(contact=contact_without_email_st)
    def test_missing_email_does_not_attempt_email_building(self, contact):
        """
        For any contact without an email address, compose_email_preview
        raises ValueError before attempting to build the subject or body,
        ensuring no partial email composition occurs.

        Feature: zzp-invoice-pdf-preview, Property 10: Missing contact email blocks email composition
        **Validates: Requirements 8.9**
        """
        ses = Mock()
        contact_svc = Mock(
            get_invoice_email=Mock(return_value=None)
        )
        param_svc = Mock(get_param=Mock(return_value='admin@test.nl'))
        service = InvoiceEmailService(
            ses_email_service=ses,
            contact_service=contact_svc,
            parameter_service=param_svc,
        )

        invoice = {
            'invoice_number': 'INV-2024-001',
            'invoice_date': '2024-01-15',
            'due_date': '2024-02-15',
            'currency': 'EUR',
            'payment_terms_days': 30,
            'subtotal': 100.0,
            'vat_total': 21.0,
            'grand_total': 121.0,
            'lines': [],
            'contact': contact,
        }

        with pytest.raises(ValueError):
            service.compose_email_preview('test_tenant', invoice)

        # Verify that the contact_service was called with correct args
        contact_svc.get_invoice_email.assert_called_once_with(
            'test_tenant', contact['id']
        )


# ---------------------------------------------------------------------------
# Strategies for Property 9
# ---------------------------------------------------------------------------

# Currency codes commonly used
_currency_st = st.sampled_from(['EUR', 'USD', 'GBP'])

# Invoice numbers: non-empty printable strings
_p9_invoice_number_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Pd')),
    min_size=1, max_size=20,
)

# Company names: non-empty text (letters, digits, spaces)
_p9_company_name_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Zs')),
    min_size=1, max_size=50,
).filter(lambda s: s.strip() != '')

# Contact person names: non-empty text
_p9_contact_person_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Zs')),
    min_size=1, max_size=50,
).filter(lambda s: s.strip() != '')

# Due dates in ISO format
from datetime import date as _date_type
_p9_due_date_st = st.dates(
    min_value=_date_type(2020, 1, 1),
    max_value=_date_type(2030, 12, 31),
).map(lambda d: d.isoformat())

# Grand total: positive amounts
_p9_grand_total_st = st.floats(
    min_value=0.01, max_value=999999.99,
    allow_nan=False, allow_infinity=False,
)

# Country strings (mix of mapped and unmapped for locale variation)
from services.invoice_email_service import COUNTRY_LOCALE_MAP as _P9_LOCALE_MAP
_p9_country_st = st.one_of(
    st.sampled_from(list(_P9_LOCALE_MAP.keys())),
    st.just(''),
    st.just('NL'),
)

# Tenant company name
_p9_tenant_company_st = _p9_company_name_st


@st.composite
def _p9_invoice_with_company_name(draw):
    """Generate a valid invoice dict where contact has company_name."""
    return {
        'invoice_number': draw(_p9_invoice_number_st),
        'grand_total': draw(_p9_grand_total_st),
        'due_date': draw(_p9_due_date_st),
        'currency': draw(_currency_st),
        'contact': {
            'id': 1,
            'company_name': draw(_p9_company_name_st),
            'contact_person': '',
            'country': draw(_p9_country_st),
        },
    }


@st.composite
def _p9_invoice_with_contact_person(draw):
    """Generate a valid invoice dict where contact has only contact_person."""
    return {
        'invoice_number': draw(_p9_invoice_number_st),
        'grand_total': draw(_p9_grand_total_st),
        'due_date': draw(_p9_due_date_st),
        'currency': draw(_currency_st),
        'contact': {
            'id': 1,
            'company_name': '',
            'contact_person': draw(_p9_contact_person_st),
            'country': draw(_p9_country_st),
        },
    }


# Combined strategy: either company_name or contact_person
_p9_invoice_st = st.one_of(
    _p9_invoice_with_company_name(),
    _p9_invoice_with_contact_person(),
)


# ---------------------------------------------------------------------------
# Helpers for Property 9
# ---------------------------------------------------------------------------

def _make_p9_service(tenant_company='Test Company BV'):
    """Create an InvoiceEmailService with mocked dependencies for Property 9."""
    ses = Mock()
    contact_svc = Mock(
        get_invoice_email=Mock(return_value='client@example.com')
    )

    def param_side_effect(namespace, key, **kwargs):
        if namespace == 'zzp_branding' and key == 'company_name':
            return tenant_company
        if namespace == 'zzp_branding' and key == 'contact_email':
            return 'admin@test.nl'
        return None

    param_svc = Mock(get_param=Mock(side_effect=param_side_effect))
    return InvoiceEmailService(
        ses_email_service=ses,
        contact_service=contact_svc,
        parameter_service=param_svc,
    )


# ---------------------------------------------------------------------------
# Property 9: Email body contains all required fields
# Feature: zzp-invoice-pdf-preview, Property 9: Email body contains all required fields
#
# For any valid invoice with a contact, the composed email body SHALL contain:
# a greeting addressing the contact by company_name (or contact_person if
# company_name is empty), the invoice number, the total amount with currency
# symbol, the due date, and the sender's company name.
#
# **Validates: Requirements 8.6, 8.7**
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEmailBodyContainsAllRequiredFields:
    """Property 9: Email body contains all required fields."""

    @settings(max_examples=20)
    @given(invoice=_p9_invoice_with_company_name(), tenant_company=_p9_tenant_company_st)
    def test_body_contains_greeting_with_company_name(self, invoice, tenant_company):
        """
        When contact has a company_name, the email body contains a greeting
        addressing the contact by company_name.

        Feature: zzp-invoice-pdf-preview, Property 9: Email body contains all required fields
        **Validates: Requirements 8.6, 8.7**
        """
        svc = _make_p9_service(tenant_company=tenant_company)
        contact = invoice['contact']
        locale = svc._resolve_locale(contact)

        body = svc._build_locale_body('test_tenant', invoice, locale)

        addressee = contact['company_name'].strip()
        assert addressee in body, (
            f"Email body should contain greeting with company_name "
            f"'{addressee}', but body was: {body[:200]}"
        )

    @settings(max_examples=20)
    @given(invoice=_p9_invoice_with_contact_person(), tenant_company=_p9_tenant_company_st)
    def test_body_contains_greeting_with_contact_person_when_no_company(self, invoice, tenant_company):
        """
        When contact has no company_name, the email body contains a greeting
        addressing the contact by contact_person.

        Feature: zzp-invoice-pdf-preview, Property 9: Email body contains all required fields
        **Validates: Requirements 8.6, 8.7**
        """
        svc = _make_p9_service(tenant_company=tenant_company)
        contact = invoice['contact']
        locale = svc._resolve_locale(contact)

        body = svc._build_locale_body('test_tenant', invoice, locale)

        addressee = contact['contact_person'].strip()
        assert addressee in body, (
            f"Email body should contain greeting with contact_person "
            f"'{addressee}', but body was: {body[:200]}"
        )

    @settings(max_examples=20)
    @given(invoice=_p9_invoice_st, tenant_company=_p9_tenant_company_st)
    def test_body_contains_invoice_number(self, invoice, tenant_company):
        """
        The email body always contains the invoice number.

        Feature: zzp-invoice-pdf-preview, Property 9: Email body contains all required fields
        **Validates: Requirements 8.6, 8.7**
        """
        svc = _make_p9_service(tenant_company=tenant_company)
        contact = invoice['contact']
        locale = svc._resolve_locale(contact)

        body = svc._build_locale_body('test_tenant', invoice, locale)

        invoice_number = invoice['invoice_number']
        assert invoice_number in body, (
            f"Email body should contain invoice_number '{invoice_number}', "
            f"but body was: {body[:200]}"
        )

    @settings(max_examples=20)
    @given(invoice=_p9_invoice_st, tenant_company=_p9_tenant_company_st)
    def test_body_contains_total_with_currency(self, invoice, tenant_company):
        """
        The email body contains the total amount formatted with a currency
        symbol. We verify by calling the same _format_amount method and
        checking its output is present in the body.

        Feature: zzp-invoice-pdf-preview, Property 9: Email body contains all required fields
        **Validates: Requirements 8.6, 8.7**
        """
        svc = _make_p9_service(tenant_company=tenant_company)
        contact = invoice['contact']
        locale = svc._resolve_locale(contact)

        body = svc._build_locale_body('test_tenant', invoice, locale)

        formatted_total = svc._format_amount(
            invoice['grand_total'], invoice['currency'], locale
        )
        assert formatted_total in body, (
            f"Email body should contain formatted total '{formatted_total}', "
            f"but body was: {body[:200]}"
        )

    @settings(max_examples=20)
    @given(invoice=_p9_invoice_st, tenant_company=_p9_tenant_company_st)
    def test_body_contains_due_date(self, invoice, tenant_company):
        """
        The email body contains the due date formatted according to locale.

        Feature: zzp-invoice-pdf-preview, Property 9: Email body contains all required fields
        **Validates: Requirements 8.6, 8.7**
        """
        svc = _make_p9_service(tenant_company=tenant_company)
        contact = invoice['contact']
        locale = svc._resolve_locale(contact)

        body = svc._build_locale_body('test_tenant', invoice, locale)

        formatted_due_date = svc._format_date(invoice['due_date'], locale)
        assert formatted_due_date in body, (
            f"Email body should contain formatted due date "
            f"'{formatted_due_date}', but body was: {body[:200]}"
        )

    @settings(max_examples=20)
    @given(invoice=_p9_invoice_st, tenant_company=_p9_tenant_company_st)
    def test_body_contains_sender_company_name(self, invoice, tenant_company):
        """
        The email body contains the sender's company name (from tenant profile).

        Feature: zzp-invoice-pdf-preview, Property 9: Email body contains all required fields
        **Validates: Requirements 8.6, 8.7**
        """
        svc = _make_p9_service(tenant_company=tenant_company)
        contact = invoice['contact']
        locale = svc._resolve_locale(contact)

        body = svc._build_locale_body('test_tenant', invoice, locale)

        assert tenant_company in body, (
            f"Email body should contain sender company name "
            f"'{tenant_company}', but body was: {body[:200]}"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 8
# ---------------------------------------------------------------------------

# Non-empty, non-whitespace-only text for invoice numbers and company names
printable_text_st = st.text(min_size=1).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Helpers for Property 8
# ---------------------------------------------------------------------------

def _make_service_for_subject(company_name: str):
    """Build an InvoiceEmailService with mocked parameter_service
    that returns the given company_name for _get_tenant_company_name."""
    ses = Mock()
    contact_svc = Mock(get_invoice_email=Mock(return_value='test@example.com'))
    param_svc = Mock(get_param=Mock(side_effect=lambda ns, key, **kw:
        company_name if key == 'company_name' else None
    ))
    return InvoiceEmailService(
        ses_email_service=ses,
        contact_service=contact_svc,
        parameter_service=param_svc,
    )


# ---------------------------------------------------------------------------
# Property 8: Email subject format by locale category
# Feature: zzp-invoice-pdf-preview, Property 8: Email subject format by locale category
#
# For any invoice_number and tenant_company_name, the email subject SHALL be:
# - "Factuur {invoice_number} van {tenant_company_name}" when locale is nl_NL
# - "Invoice {invoice_number} from {tenant_company_name}" for EN/other locales
#
# **Validates: Requirements 8.3, 8.4, 8.5**
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEmailSubjectFormatByLocaleCategory:
    """Property 8: Email subject format by locale category.

    **Validates: Requirements 8.3, 8.4, 8.5**
    """

    @settings(max_examples=20)
    @given(
        invoice_number=printable_text_st,
        company=printable_text_st,
    )
    def test_nl_locale_subject_format(self, invoice_number, company):
        """NL locale (nl_NL) produces Dutch subject format:
        "Factuur {invoice_number} van {tenant_company_name}"

        Feature: zzp-invoice-pdf-preview, Property 8: Email subject format by locale category
        **Validates: Requirements 8.3**
        """
        svc = _make_service_for_subject(company)
        invoice = {'invoice_number': invoice_number}

        subject = svc._build_locale_subject('tenant1', invoice, 'nl_NL')

        expected = f"Factuur {invoice_number} van {company}"
        assert subject == expected

    @settings(max_examples=20)
    @given(
        invoice_number=printable_text_st,
        company=printable_text_st,
        locale=st.sampled_from(['en_US', 'en_GB', 'en_AU']),
    )
    def test_english_locale_subject_format(self, invoice_number, company, locale):
        """English locales (en_US, en_GB, en_AU) produce English subject format:
        "Invoice {invoice_number} from {tenant_company_name}"

        Feature: zzp-invoice-pdf-preview, Property 8: Email subject format by locale category
        **Validates: Requirements 8.4**
        """
        svc = _make_service_for_subject(company)
        invoice = {'invoice_number': invoice_number}

        subject = svc._build_locale_subject('tenant1', invoice, locale)

        expected = f"Invoice {invoice_number} from {company}"
        assert subject == expected

    @settings(max_examples=20)
    @given(
        invoice_number=printable_text_st,
        company=printable_text_st,
        locale=st.sampled_from(['de_DE', 'fr_FR', 'nl_BE', 'es_ES', 'it_IT']),
    )
    def test_non_dutch_non_english_locale_falls_back_to_english(
        self, invoice_number, company, locale
    ):
        """Non-Dutch, non-English locales fall back to English subject format:
        "Invoice {invoice_number} from {tenant_company_name}"

        Feature: zzp-invoice-pdf-preview, Property 8: Email subject format by locale category
        **Validates: Requirements 8.5**
        """
        svc = _make_service_for_subject(company)
        invoice = {'invoice_number': invoice_number}

        subject = svc._build_locale_subject('tenant1', invoice, locale)

        expected = f"Invoice {invoice_number} from {company}"
        assert subject == expected
