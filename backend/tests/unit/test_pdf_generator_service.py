"""Unit tests for PDFGeneratorService."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO
from datetime import date
from services.pdf_generator_service import (
    PDFGeneratorService, COUNTRY_LOCALE_MAP, DEFAULT_LOCALE,
)


def _make_service(template_svc=None, param_svc=None):
    db = Mock()
    template_svc = template_svc or Mock(get_template_metadata=Mock(return_value=None))
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return PDFGeneratorService(db=db, template_service=template_svc,
                               parameter_service=param_svc)


def _sample_invoice(**overrides):
    base = {
        'invoice_number': 'INV-2026-0001',
        'invoice_type': 'invoice',
        'invoice_date': '2026-04-15',
        'due_date': '2026-05-15',
        'payment_terms_days': 30,
        'currency': 'EUR',
        'subtotal': 15200.0,
        'vat_total': 3192.0,
        'grand_total': 18392.0,
        'notes': 'Werkzaamheden april',
        'contact': {
            'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp B.V.',
            'contact_person': 'Jan de Vries', 'street_address': 'Keizersgracht 100',
            'postal_code': '1015 AA', 'city': 'Amsterdam', 'country': 'NL',
        },
        'lines': [
            {'description': 'Software Development', 'quantity': 160.0,
             'unit_price': 95.0, 'vat_rate': 21.0, 'line_total': 15200.0},
        ],
        'vat_summary': [
            {'vat_code': 'high', 'vat_rate': 21.0, 'base_amount': 15200.0, 'vat_amount': 3192.0},
        ],
    }
    base.update(overrides)
    return base


# ── _render_html ────────────────────────────────────────────


def test_render_html_includes_invoice_number():
    svc = _make_service()
    html = svc._render_html('T1', _sample_invoice())
    assert 'INV-2026-0001' in html


def test_render_html_includes_contact_details():
    svc = _make_service()
    html = svc._render_html('T1', _sample_invoice())
    assert 'Acme Corp B.V.' in html
    assert 'ACME' in html
    assert 'Keizersgracht 100' in html


def test_render_html_includes_line_items():
    svc = _make_service()
    html = svc._render_html('T1', _sample_invoice())
    assert 'Software Development' in html
    # Service formats amounts in Dutch locale (e.g. 15.200,00)
    assert '15.200,00' in html


def test_render_html_includes_vat_summary():
    svc = _make_service()
    html = svc._render_html('T1', _sample_invoice())
    # Service formats amounts in Dutch locale (e.g. 3.192,00)
    assert '3.192,00' in html


def test_render_html_includes_totals():
    svc = _make_service()
    html = svc._render_html('T1', _sample_invoice())
    # Service formats amounts in Dutch locale (e.g. 18.392,00)
    assert '18.392,00' in html


def test_render_html_includes_payment_reference():
    svc = _make_service()
    html = svc._render_html('T1', _sample_invoice())
    assert 'ACME' in html  # client_id in payment info


def test_render_html_copy_includes_watermark():
    svc = _make_service()
    html = svc._render_html('T1', _sample_invoice(), is_copy=True)
    assert 'COPY' in html


def test_render_html_no_copy_no_watermark():
    svc = _make_service()
    html = svc._render_html('T1', _sample_invoice(), is_copy=False)
    assert 'watermark' not in html or 'COPY' not in html


def test_render_html_with_logo_includes_img_tag():
    param_svc = Mock(get_param=Mock(return_value='https://example.com/logo.png'))
    svc = _make_service(param_svc=param_svc)
    html = svc._render_html('T1', _sample_invoice())
    assert '<img' in html
    assert 'logo.png' in html


def test_render_html_no_logo_no_img_tag():
    svc = _make_service()
    html = svc._render_html('T1', _sample_invoice())
    assert '<img' not in html


# ── generate_invoice_pdf ────────────────────────────────────


@patch('services.pdf_generator_service.PDFGeneratorService._html_to_pdf')
def test_generate_invoice_pdf_returns_bytesio(mock_to_pdf):
    mock_to_pdf.return_value = BytesIO(b'%PDF-fake')
    svc = _make_service()
    result = svc.generate_invoice_pdf('T1', _sample_invoice())
    assert isinstance(result, BytesIO)
    mock_to_pdf.assert_called_once()


@patch('services.pdf_generator_service.PDFGeneratorService._html_to_pdf')
def test_generate_copy_invoice_pdf_passes_is_copy(mock_to_pdf):
    mock_to_pdf.return_value = BytesIO(b'%PDF-fake')
    svc = _make_service()
    svc.generate_copy_invoice_pdf('T1', _sample_invoice())
    # Verify the HTML passed to _html_to_pdf contains COPY watermark
    html_arg = mock_to_pdf.call_args[0][0]
    assert 'COPY' in html_arg


# ── _html_to_pdf ────────────────────────────────────────────


@patch.dict('sys.modules', {'weasyprint': None})
def test_html_to_pdf_missing_weasyprint_raises_runtime_error():
    svc = _make_service()
    with pytest.raises(RuntimeError, match="weasyprint"):
        svc._html_to_pdf('<html></html>')


# ── _get_tenant_logo ────────────────────────────────────────


def test_get_tenant_logo_returns_url_from_params():
    """Logo file ID is used to construct a Google Drive thumbnail URL or data URI."""
    param_svc = Mock(get_param=Mock(return_value='abc123fileid'))
    svc = _make_service(param_svc=param_svc)
    result = svc._get_tenant_logo('T1')
    # Should return something (data URI or fallback URL) when a file ID is configured
    assert result is not None
    # The file ID should appear in the result (either in the URL or was used to fetch)
    assert 'abc123fileid' in result or result.startswith('data:')


def test_get_tenant_logo_no_config_returns_none():
    svc = _make_service()
    assert svc._get_tenant_logo('T1') is None


# ── _resolve_locale ─────────────────────────────────────────


class TestResolveLocale:
    """Tests for _resolve_locale: country → Babel locale mapping."""

    def test_nl_country_code(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'NL'}) == 'nl_NL'

    def test_de_country_code(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'DE'}) == 'de_DE'

    def test_us_country_code(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'US'}) == 'en_US'

    def test_gb_country_code(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'GB'}) == 'en_GB'

    def test_fr_country_code(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'FR'}) == 'fr_FR'

    def test_be_country_code(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'BE'}) == 'nl_BE'

    def test_dutch_name(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'Nederland'}) == 'nl_NL'

    def test_english_name_germany(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'Germany'}) == 'de_DE'

    def test_english_name_netherlands(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'Netherlands'}) == 'nl_NL'

    def test_english_name_united_states(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'United States'}) == 'en_US'

    def test_lowercase_code_resolved_via_uppercase(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'nl'}) == 'nl_NL'

    def test_lowercase_name_resolved_via_title_case(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'france'}) == 'fr_FR'

    def test_empty_country_defaults_to_nl(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': ''}) == DEFAULT_LOCALE

    def test_none_country_defaults_to_nl(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': None}) == DEFAULT_LOCALE

    def test_missing_country_key_defaults_to_nl(self):
        svc = _make_service()
        assert svc._resolve_locale({}) == DEFAULT_LOCALE

    def test_unknown_country_defaults_to_nl(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': 'ZZ'}) == DEFAULT_LOCALE

    def test_whitespace_stripped(self):
        svc = _make_service()
        assert svc._resolve_locale({'country': '  NL  '}) == 'nl_NL'


# ── _format_amount ──────────────────────────────────────────


class TestFormatAmount:
    """Tests for _format_amount: locale-aware currency formatting."""

    def test_nl_eur_formatting(self):
        svc = _make_service()
        result = svc._format_amount(1250.00, 'EUR', 'nl_NL')
        # Dutch locale uses comma as decimal separator
        assert '1.250,00' in result
        assert '€' in result

    def test_us_eur_formatting(self):
        svc = _make_service()
        result = svc._format_amount(1250.00, 'EUR', 'en_US')
        # US locale uses period as decimal separator
        assert '1,250.00' in result
        assert '€' in result

    def test_de_eur_formatting(self):
        svc = _make_service()
        result = svc._format_amount(1250.00, 'EUR', 'de_DE')
        # German locale uses comma as decimal separator
        assert '1.250,00' in result
        assert '€' in result

    def test_usd_currency_symbol(self):
        svc = _make_service()
        result = svc._format_amount(1250.00, 'USD', 'en_US')
        assert '$' in result
        assert '1,250.00' in result

    def test_gbp_with_nl_locale_uses_gbp_symbol(self):
        """Currency symbol comes from currency_code, not locale default."""
        svc = _make_service()
        result = svc._format_amount(1250.00, 'GBP', 'nl_NL')
        # Should use GBP symbol, not EUR despite nl_NL locale
        assert '£' in result
        assert '1.250,00' in result

    def test_zero_amount(self):
        svc = _make_service()
        result = svc._format_amount(0, 'EUR', 'nl_NL')
        assert '0,00' in result

    def test_none_amount_treated_as_zero(self):
        svc = _make_service()
        result = svc._format_amount(None, 'EUR', 'nl_NL')
        assert '0,00' in result


# ── _format_qty ─────────────────────────────────────────────


class TestFormatQty:
    """Tests for _format_qty: locale-aware quantity formatting."""

    def test_whole_number_returns_integer_string(self):
        svc = _make_service()
        assert svc._format_qty(160.0, 'nl_NL') == '160'

    def test_whole_number_int_returns_integer_string(self):
        svc = _make_service()
        assert svc._format_qty(10, 'nl_NL') == '10'

    def test_decimal_nl_uses_comma(self):
        svc = _make_service()
        result = svc._format_qty(7.5, 'nl_NL')
        assert '7,5' in result

    def test_decimal_us_uses_period(self):
        svc = _make_service()
        result = svc._format_qty(7.5, 'en_US')
        assert '7.5' in result

    def test_zero_returns_zero_string(self):
        svc = _make_service()
        assert svc._format_qty(0, 'nl_NL') == '0'

    def test_none_treated_as_zero(self):
        svc = _make_service()
        assert svc._format_qty(None, 'nl_NL') == '0'


# ── _format_date ────────────────────────────────────────────


class TestFormatDate:
    """Tests for _format_date: locale-aware date formatting."""

    def test_nl_date_from_string(self):
        svc = _make_service()
        result = svc._format_date('2026-05-15', 'nl_NL')
        # Dutch short format: dd-MM-yyyy or dd-MM-yy
        assert '15' in result
        assert '05' in result

    def test_us_date_from_string(self):
        svc = _make_service()
        result = svc._format_date('2026-05-15', 'en_US')
        # US short format: M/d/yy or similar
        assert '5' in result
        assert '15' in result

    def test_date_object_input(self):
        svc = _make_service()
        result = svc._format_date(date(2026, 5, 15), 'nl_NL')
        assert '15' in result
        assert '05' in result

    def test_empty_string_returns_empty(self):
        svc = _make_service()
        assert svc._format_date('', 'nl_NL') == ''

    def test_none_returns_empty(self):
        svc = _make_service()
        assert svc._format_date(None, 'nl_NL') == ''

    def test_invalid_date_returns_original(self):
        svc = _make_service()
        assert svc._format_date('not-a-date', 'nl_NL') == 'not-a-date'

    def test_de_date_from_string(self):
        svc = _make_service()
        result = svc._format_date('2026-05-15', 'de_DE')
        # German short format uses dots: dd.MM.yy
        assert '15' in result
        assert '05' in result


# ── Module-level constants ──────────────────────────────────


class TestLocaleConstants:
    """Tests for module-level locale constants."""

    def test_default_locale_is_nl(self):
        assert DEFAULT_LOCALE == 'nl_NL'

    def test_country_locale_map_has_expected_entries(self):
        expected_codes = ['NL', 'DE', 'US', 'GB', 'FR', 'BE']
        for code in expected_codes:
            assert code in COUNTRY_LOCALE_MAP

    def test_country_locale_map_has_dutch_names(self):
        assert 'Nederland' in COUNTRY_LOCALE_MAP
        assert 'Duitsland' in COUNTRY_LOCALE_MAP
        assert 'Frankrijk' in COUNTRY_LOCALE_MAP

    def test_country_locale_map_has_english_names(self):
        assert 'Netherlands' in COUNTRY_LOCALE_MAP
        assert 'Germany' in COUNTRY_LOCALE_MAP
        assert 'France' in COUNTRY_LOCALE_MAP
        assert 'United States' in COUNTRY_LOCALE_MAP
        assert 'United Kingdom' in COUNTRY_LOCALE_MAP
