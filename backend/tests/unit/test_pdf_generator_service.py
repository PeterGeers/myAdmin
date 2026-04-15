"""Unit tests for PDFGeneratorService."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO
from services.pdf_generator_service import PDFGeneratorService


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
    assert '15200.00' in html


def test_render_html_includes_vat_summary():
    svc = _make_service()
    html = svc._render_html('T1', _sample_invoice())
    assert '3192.00' in html


def test_render_html_includes_totals():
    svc = _make_service()
    html = svc._render_html('T1', _sample_invoice())
    assert '18392.00' in html


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
    param_svc = Mock(get_param=Mock(return_value='https://example.com/logo.png'))
    svc = _make_service(param_svc=param_svc)
    assert svc._get_tenant_logo('T1') == 'https://example.com/logo.png'


def test_get_tenant_logo_no_config_returns_none():
    svc = _make_service()
    assert svc._get_tenant_logo('T1') is None
