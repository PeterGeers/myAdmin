"""
Property-based tests for ZZP Invoice PDF Preview service.

Feature: zzp-invoice-pdf-preview
Property 1: Non-draft invoices are rejected for preview
Property 2: Tenant isolation on preview
Property 3: Watermark text is locale-dependent
Property 7: Locale resolution from contact country

Validates: Requirements 1.3, 1.4, 1.5, 2.3, 7.3, 8.2
Reference: .kiro/specs/zzp-invoice-pdf-preview/design.md §Correctness Properties
"""

import sys
import os
import pytest
from unittest.mock import Mock, patch
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.pdf_generator_service import (
    PDFGeneratorService, COUNTRY_LOCALE_MAP, DEFAULT_LOCALE,
)
from services.zzp_invoice_service import ZZPInvoiceService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# All mapped country keys from COUNTRY_LOCALE_MAP
mapped_country_st = st.sampled_from(list(COUNTRY_LOCALE_MAP.keys()))

# Arbitrary text strings for unmapped countries
arbitrary_country_st = st.text(min_size=1).filter(
    lambda s: s.strip() != '' and
    s not in COUNTRY_LOCALE_MAP and
    s.upper() not in COUNTRY_LOCALE_MAP and
    s.title() not in COUNTRY_LOCALE_MAP
)

# Empty/None country values
empty_country_st = st.sampled_from(['', '  ', '\t', None])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service():
    """Create a PDFGeneratorService with mock dependencies."""
    db = Mock()
    template_svc = Mock(get_template_metadata=Mock(return_value=None))
    param_svc = Mock(get_param=Mock(return_value=None))
    return PDFGeneratorService(
        db=db, template_service=template_svc, parameter_service=param_svc,
    )


def _make_contact(country):
    """Create a contact dict with the given country."""
    if country is None:
        return {}
    return {'country': country}


# ---------------------------------------------------------------------------
# Property 7: Locale resolution from contact country
# Feature: zzp-invoice-pdf-preview, Property 7: Locale resolution from contact country
#
# For any contact country string, _resolve_locale SHALL return the
# corresponding locale from COUNTRY_LOCALE_MAP if a match exists
# (case-insensitive), or nl_NL as the default when the country is empty,
# null, or unmapped.
#
# Validates: Requirements 7.3, 8.2
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLocaleResolutionFromContactCountry:
    """Property 7: Locale resolution from contact country."""

    # -- 7a: Mapped countries return correct locale from COUNTRY_LOCALE_MAP --

    @settings(max_examples=20)
    @given(country=mapped_country_st)
    def test_mapped_country_returns_correct_locale(self, country):
        """
        Any country key present in COUNTRY_LOCALE_MAP resolves to its
        mapped locale value.

        **Validates: Requirements 7.3, 8.2**
        """
        svc = _make_service()
        contact = _make_contact(country)
        locale = svc._resolve_locale(contact)
        assert locale == COUNTRY_LOCALE_MAP[country], (
            f"Country '{country}' should resolve to "
            f"'{COUNTRY_LOCALE_MAP[country]}', got '{locale}'"
        )

    # -- 7b: Unmapped countries default to nl_NL ---------------------------

    @settings(max_examples=20)
    @given(country=arbitrary_country_st)
    def test_unmapped_country_defaults_to_nl_nl(self, country):
        """
        Any country string not found in COUNTRY_LOCALE_MAP (after trying
        exact, uppercase, and title case) defaults to nl_NL.

        **Validates: Requirements 7.3, 8.2**
        """
        svc = _make_service()
        contact = _make_contact(country)
        locale = svc._resolve_locale(contact)
        assert locale == DEFAULT_LOCALE, (
            f"Unmapped country '{country}' should default to "
            f"'{DEFAULT_LOCALE}', got '{locale}'"
        )

    # -- 7c: Empty or None country defaults to nl_NL -----------------------

    @settings(max_examples=20)
    @given(country=empty_country_st)
    def test_empty_or_none_country_defaults_to_nl_nl(self, country):
        """
        When the contact country is empty, whitespace-only, or None,
        _resolve_locale returns nl_NL.

        **Validates: Requirements 7.3, 8.2**
        """
        svc = _make_service()
        contact = _make_contact(country)
        locale = svc._resolve_locale(contact)
        assert locale == DEFAULT_LOCALE, (
            f"Empty/None country '{country!r}' should default to "
            f"'{DEFAULT_LOCALE}', got '{locale}'"
        )

    # -- 7d: Case-insensitive resolution works -----------------------------

    @settings(max_examples=20)
    @given(country=mapped_country_st)
    def test_lowercase_country_resolves_correctly(self, country):
        """
        Country strings are resolved case-insensitively: a lowercase version
        of a mapped key should still resolve to the correct locale.

        **Validates: Requirements 7.3, 8.2**
        """
        svc = _make_service()
        lower_country = country.lower()
        contact = _make_contact(lower_country)
        locale = svc._resolve_locale(contact)
        expected = COUNTRY_LOCALE_MAP[country]
        # The implementation tries exact, then .upper(), then .title()
        # So lowercase 'nl' → upper 'NL' → found; 'nederland' → title 'Nederland' → found
        assert locale == expected, (
            f"Lowercase country '{lower_country}' (from '{country}') should "
            f"resolve to '{expected}', got '{locale}'"
        )

    # -- 7e: Result is always a valid locale string ------------------------

    @settings(max_examples=20)
    @given(country=st.text())
    def test_result_is_always_valid_locale(self, country):
        """
        For any arbitrary text input as country, _resolve_locale always
        returns either a value from COUNTRY_LOCALE_MAP or DEFAULT_LOCALE.

        **Validates: Requirements 7.3, 8.2**
        """
        svc = _make_service()
        contact = _make_contact(country)
        locale = svc._resolve_locale(contact)
        valid_locales = set(COUNTRY_LOCALE_MAP.values()) | {DEFAULT_LOCALE}
        assert locale in valid_locales, (
            f"Locale '{locale}' for country '{country!r}' is not a valid "
            f"locale. Expected one of: {valid_locales}"
        )


# ---------------------------------------------------------------------------
# Helpers for Property 3
# ---------------------------------------------------------------------------

def _make_invoice(country):
    """Create a minimal invoice dict with a contact having the given country."""
    return {
        'invoice_number': 'TEST-001',
        'invoice_date': '2024-01-15',
        'due_date': '2024-02-15',
        'currency': 'EUR',
        'payment_terms_days': 30,
        'subtotal': 100.0,
        'vat_total': 21.0,
        'grand_total': 121.0,
        'lines': [],
        'vat_summary': [],
        'contact': {'country': country, 'company_name': 'Test BV'},
    }


# ---------------------------------------------------------------------------
# Property 3: Watermark text is locale-dependent
# Feature: zzp-invoice-pdf-preview, Property 3: Watermark text is locale-dependent
#
# For any contact country string, the preview watermark text SHALL be
# "CONCEPT" when the resolved locale is nl_NL, and "DRAFT" for all other
# resolved locales (including the default when country is empty or unmapped).
#
# **Validates: Requirements 1.5**
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWatermarkLocaleDependent:
    """Property 3: Watermark text is locale-dependent."""

    @settings(max_examples=20)
    @given(country=mapped_country_st)
    def test_mapped_country_watermark_matches_locale(self, country):
        """
        For any mapped country, the watermark is CONCEPT if locale resolves
        to nl_NL, DRAFT otherwise.

        Feature: zzp-invoice-pdf-preview, Property 3: Watermark text is locale-dependent
        **Validates: Requirements 1.5**
        """
        svc = _make_service()
        invoice = _make_invoice(country)

        # Call _render_html with is_preview=True to get the HTML with watermark
        html = svc._render_html('test_tenant', invoice, is_preview=True)

        resolved_locale = COUNTRY_LOCALE_MAP[country]
        if resolved_locale == 'nl_NL':
            assert '<div class="watermark">CONCEPT</div>' in html, (
                f"Country '{country}' resolves to nl_NL, "
                f"watermark should be CONCEPT"
            )
            assert '<div class="watermark">DRAFT</div>' not in html
        else:
            assert '<div class="watermark">DRAFT</div>' in html, (
                f"Country '{country}' resolves to '{resolved_locale}', "
                f"watermark should be DRAFT"
            )
            assert '<div class="watermark">CONCEPT</div>' not in html

    @settings(max_examples=20)
    @given(country=st.one_of(
        st.text(min_size=0, max_size=50),
        st.sampled_from(list(COUNTRY_LOCALE_MAP.keys())),
    ))
    def test_arbitrary_country_watermark_matches_resolved_locale(self, country):
        """
        For any arbitrary country string (including empty, unmapped, or mapped),
        the watermark text is CONCEPT when resolved locale is nl_NL, DRAFT otherwise.

        Feature: zzp-invoice-pdf-preview, Property 3: Watermark text is locale-dependent
        **Validates: Requirements 1.5**
        """
        svc = _make_service()
        invoice = _make_invoice(country)

        html = svc._render_html('test_tenant', invoice, is_preview=True)

        # Determine expected locale using the same resolution logic
        resolved_locale = svc._resolve_locale({'country': country})

        if resolved_locale == 'nl_NL':
            assert '<div class="watermark">CONCEPT</div>' in html, (
                f"Country {country!r} resolves to nl_NL, "
                f"watermark should be CONCEPT but not found in HTML"
            )
            assert '<div class="watermark">DRAFT</div>' not in html
        else:
            assert '<div class="watermark">DRAFT</div>' in html, (
                f"Country {country!r} resolves to '{resolved_locale}', "
                f"watermark should be DRAFT but not found in HTML"
            )
            assert '<div class="watermark">CONCEPT</div>' not in html


# ---------------------------------------------------------------------------
# Property 1: Non-draft invoices are rejected for preview
# Feature: zzp-invoice-pdf-preview, Property 1: Non-draft invoices are rejected for preview
#
# For any invoice with a status other than `draft` (sent, paid, overdue,
# credited, cancelled), calling `preview_invoice` SHALL raise a ValueError
# indicating that only draft invoices can be previewed, and no PDF generation
# SHALL occur.
#
# **Validates: Requirements 1.3**
# ---------------------------------------------------------------------------

# Strategy: all non-draft statuses
non_draft_status_st = st.sampled_from(['sent', 'paid', 'overdue', 'credited', 'cancelled'])


def _make_zzp_invoice_service(mock_get_invoice_return=None):
    """Create a ZZPInvoiceService with mocked dependencies for property testing."""
    db = Mock()
    pdf_generator = Mock()
    service = ZZPInvoiceService(
        db=db,
        pdf_generator=pdf_generator,
    )
    # Mock get_invoice to return the provided invoice dict
    service.get_invoice = Mock(return_value=mock_get_invoice_return)
    return service


@pytest.mark.unit
class TestNonDraftRejection:
    """Property 1: Non-draft invoices are rejected for preview."""

    @settings(max_examples=20)
    @given(status=non_draft_status_st)
    def test_non_draft_status_raises_value_error(self, status):
        """
        For any non-draft status, preview_invoice raises ValueError with
        the message indicating only draft invoices can be previewed.

        Feature: zzp-invoice-pdf-preview, Property 1: Non-draft invoices are rejected for preview
        **Validates: Requirements 1.3**
        """
        invoice = {
            'id': 1,
            'invoice_number': 'INV-2024-0001',
            'status': status,
            'contact_id': 1,
            'contact': {'company_name': 'Test BV', 'country': 'NL'},
        }
        service = _make_zzp_invoice_service(mock_get_invoice_return=invoice)

        with pytest.raises(ValueError, match="Only draft invoices can be previewed"):
            service.preview_invoice('test_tenant', 1)

    @settings(max_examples=20)
    @given(status=non_draft_status_st)
    def test_non_draft_status_does_not_generate_pdf(self, status):
        """
        For any non-draft status, generate_preview_pdf is never called,
        ensuring no PDF generation occurs for non-draft invoices.

        Feature: zzp-invoice-pdf-preview, Property 1: Non-draft invoices are rejected for preview
        **Validates: Requirements 1.3**
        """
        invoice = {
            'id': 1,
            'invoice_number': 'INV-2024-0001',
            'status': status,
            'contact_id': 1,
            'contact': {'company_name': 'Test BV', 'country': 'NL'},
        }
        service = _make_zzp_invoice_service(mock_get_invoice_return=invoice)

        with pytest.raises(ValueError):
            service.preview_invoice('test_tenant', 1)

        # Verify PDF generation was never attempted
        service.pdf_generator.generate_preview_pdf.assert_not_called()


# ---------------------------------------------------------------------------
# Property 2: Tenant isolation on preview
# Feature: zzp-invoice-pdf-preview, Property 2: Tenant isolation on preview
#
# For any invoice_id that does not exist in the database or does not belong
# to the requesting tenant, calling `preview_invoice` SHALL raise a ValueError
# (resulting in HTTP 404), regardless of whether the invoice exists for
# another tenant.
#
# **Validates: Requirements 1.4, 2.3**
# ---------------------------------------------------------------------------

# Strategy: pairs of tenant strings (owner_tenant, requesting_tenant)
tenant_pair_st = st.tuples(st.text(min_size=1), st.text(min_size=1))


@pytest.mark.unit
class TestTenantIsolation:
    """Property 2: Tenant isolation on preview."""

    @settings(max_examples=20)
    @given(tenant_pair=tenant_pair_st)
    def test_invoice_not_found_for_tenant_raises_value_error(self, tenant_pair):
        """
        For any pair of tenant strings, when get_invoice returns None
        (invoice does not exist or does not belong to the requesting tenant),
        preview_invoice raises ValueError with "Invoice not found".

        Feature: zzp-invoice-pdf-preview, Property 2: Tenant isolation on preview
        **Validates: Requirements 1.4, 2.3**
        """
        _owner_tenant, requesting_tenant = tenant_pair

        # Mock get_invoice to return None — simulates invoice not found
        # for the requesting tenant (either doesn't exist or belongs to
        # a different tenant)
        service = _make_zzp_invoice_service(mock_get_invoice_return=None)

        with pytest.raises(ValueError, match="Invoice not found"):
            service.preview_invoice(requesting_tenant, 1)

    @settings(max_examples=20)
    @given(tenant_pair=tenant_pair_st)
    def test_invoice_not_found_does_not_generate_pdf(self, tenant_pair):
        """
        For any pair of tenant strings, when the invoice does not belong to
        the requesting tenant, generate_preview_pdf is never called,
        ensuring no PDF generation occurs for unauthorized access.

        Feature: zzp-invoice-pdf-preview, Property 2: Tenant isolation on preview
        **Validates: Requirements 1.4, 2.3**
        """
        _owner_tenant, requesting_tenant = tenant_pair

        # Mock get_invoice to return None — tenant isolation enforced
        service = _make_zzp_invoice_service(mock_get_invoice_return=None)

        with pytest.raises(ValueError):
            service.preview_invoice(requesting_tenant, 1)

        # Verify PDF generation was never attempted
        service.pdf_generator.generate_preview_pdf.assert_not_called()
