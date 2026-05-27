"""
API tests for ZZP Invoice PDF Preview and Email Preview routes.

Tests the GET /api/zzp/invoices/<invoice_id>/preview endpoint
covering success, not-draft (400), not-found (404), and generation failure (500).

Tests the GET /api/zzp/invoices/<invoice_id>/email-preview endpoint
covering success (200 with JSON), not-draft (400), and contact without email (400).

Uses Flask test client with mocked auth decorators and service layer.
Requirements: 2.1, 2.3, 2.4, 2.5, 8.8, 8.9, 8.12
"""

import pytest
import sys
import os
from io import BytesIO
from unittest.mock import Mock, patch
from flask import Flask
from functools import wraps

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ── Auth decorator mocks ───────────────────────────────────


def _passthrough_cognito(required_permissions=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['ZZP_Read']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = 'TestTenant'
            kwargs['user_tenants'] = ['TestTenant']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_module(module_name):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def mock_invoice_service():
    return Mock()


@pytest.fixture
def preview_client(mock_invoice_service):
    """Flask test client with mocked auth and invoice service for preview route."""
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module):
        import importlib
        import routes.zzp_routes as zr
        importlib.reload(zr)
        zr._get_invoice_service = lambda: mock_invoice_service
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(zr.zzp_bp)
        yield app.test_client()


# ── Preview route tests ─────────────────────────────────────


@pytest.mark.api
def test_preview_success_returns_200_with_pdf_content_type(preview_client, mock_invoice_service):
    """Successful preview returns 200 with application/pdf content-type and correct headers."""
    mock_invoice_service.get_invoice.return_value = {
        'id': 1,
        'invoice_number': 'INV-2024-001',
        'status': 'draft',
    }
    pdf_content = b'%PDF-1.4 fake pdf content'
    mock_invoice_service.preview_invoice.return_value = BytesIO(pdf_content)

    resp = preview_client.get('/api/zzp/invoices/1/preview')

    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'
    assert resp.headers['Content-Disposition'] == 'inline; filename="INV-2024-001_PREVIEW.pdf"'
    assert resp.data == pdf_content


@pytest.mark.api
def test_preview_non_draft_invoice_returns_400(preview_client, mock_invoice_service):
    """Non-draft invoice preview returns 400 with appropriate error message."""
    mock_invoice_service.get_invoice.return_value = {
        'id': 1,
        'invoice_number': 'INV-2024-001',
        'status': 'sent',
    }
    mock_invoice_service.preview_invoice.side_effect = ValueError(
        "Only draft invoices can be previewed"
    )

    resp = preview_client.get('/api/zzp/invoices/1/preview')

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'Only draft invoices can be previewed' in data['error']


@pytest.mark.api
def test_preview_nonexistent_invoice_returns_404(preview_client, mock_invoice_service):
    """Non-existent invoice returns 404 with 'Invoice not found' error."""
    mock_invoice_service.get_invoice.return_value = None

    resp = preview_client.get('/api/zzp/invoices/999/preview')

    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False
    assert data['error'] == 'Invoice not found'


@pytest.mark.api
def test_preview_invoice_not_found_via_valueerror_returns_404(preview_client, mock_invoice_service):
    """ValueError with 'not found' in message returns 404."""
    mock_invoice_service.get_invoice.return_value = {
        'id': 1,
        'invoice_number': 'INV-2024-001',
        'status': 'draft',
    }
    mock_invoice_service.preview_invoice.side_effect = ValueError("Invoice not found")

    resp = preview_client.get('/api/zzp/invoices/1/preview')

    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False
    assert 'not found' in data['error'].lower()


@pytest.mark.api
def test_preview_pdf_generation_failure_returns_500(preview_client, mock_invoice_service):
    """RuntimeError during PDF generation returns 500 with generic error."""
    mock_invoice_service.get_invoice.return_value = {
        'id': 1,
        'invoice_number': 'INV-2024-001',
        'status': 'draft',
    }
    mock_invoice_service.preview_invoice.side_effect = RuntimeError(
        "PDF generation failed: weasyprint error"
    )

    resp = preview_client.get('/api/zzp/invoices/1/preview')

    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False
    assert data['error'] == 'PDF generation failed'


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------
from hypothesis import given, strategies as st, settings, HealthCheck


# Strategy for valid invoice_number strings.
# Filter out characters that would break HTTP headers:
# - No newlines (\n, \r) — would split headers
# - No double quotes (") — would break the filename quoting
invoice_number_st = st.text(min_size=1).filter(
    lambda s: '\n' not in s and '\r' not in s and '"' not in s
)


def _make_preview_client_and_service():
    """Create a Flask test client and mock service for property testing.

    Returns (test_client, mock_invoice_service) tuple.
    This avoids function-scoped fixture issues with Hypothesis.
    """
    mock_svc = Mock()
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module):
        import importlib
        import routes.zzp_routes as zr
        importlib.reload(zr)
        zr._get_invoice_service = lambda: mock_svc
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(zr.zzp_bp)
        client = app.test_client()
    return client, mock_svc


# ---------------------------------------------------------------------------
# Property 4: Content-Disposition filename format
# Feature: zzp-invoice-pdf-preview, Property 4: Content-Disposition filename format
#
# For any valid invoice_number string, the preview endpoint response SHALL
# include a Content-Disposition header with value
# `inline; filename="{invoice_number}_PREVIEW.pdf"`.
#
# **Validates: Requirements 2.4**
# ---------------------------------------------------------------------------


@pytest.mark.api
class TestContentDispositionFilenameFormat:
    """Property 4: Content-Disposition filename format."""

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(invoice_number=invoice_number_st)
    def test_content_disposition_contains_invoice_number_preview(self, invoice_number):
        """
        For any valid invoice_number string (no newlines, no quotes),
        the preview endpoint response includes a Content-Disposition header
        with value `inline; filename="{invoice_number}_PREVIEW.pdf"`.

        Feature: zzp-invoice-pdf-preview, Property 4: Content-Disposition filename format
        **Validates: Requirements 2.4**
        """
        client, mock_svc = _make_preview_client_and_service()

        # Setup: mock get_invoice to return an invoice with the given number
        mock_svc.get_invoice.return_value = {
            'id': 1,
            'invoice_number': invoice_number,
            'status': 'draft',
            'contact_id': 1,
            'contact': {'company_name': 'Test BV', 'country': 'NL'},
        }

        # Setup: mock preview_invoice to return a valid PDF BytesIO
        pdf_content = b'%PDF-1.4 fake pdf content'
        mock_svc.preview_invoice.return_value = BytesIO(pdf_content)

        # Act: call the preview endpoint
        resp = client.get('/api/zzp/invoices/1/preview')

        # Assert: response is successful
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.data}"
        )

        # Assert: Content-Disposition header has correct format
        content_disposition = resp.headers.get('Content-Disposition')
        expected = f'inline; filename="{invoice_number}_PREVIEW.pdf"'
        assert content_disposition == expected, (
            f"Expected Content-Disposition '{expected}', "
            f"got '{content_disposition}'"
        )

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(invoice_number=invoice_number_st)
    def test_content_disposition_always_has_inline_disposition(self, invoice_number):
        """
        For any valid invoice_number, the Content-Disposition header always
        starts with 'inline' (not 'attachment'), ensuring the browser displays
        the PDF rather than downloading it.

        Feature: zzp-invoice-pdf-preview, Property 4: Content-Disposition filename format
        **Validates: Requirements 2.4**
        """
        client, mock_svc = _make_preview_client_and_service()

        mock_svc.get_invoice.return_value = {
            'id': 1,
            'invoice_number': invoice_number,
            'status': 'draft',
            'contact_id': 1,
            'contact': {'company_name': 'Test BV', 'country': 'NL'},
        }
        mock_svc.preview_invoice.return_value = BytesIO(b'%PDF-1.4')

        resp = client.get('/api/zzp/invoices/1/preview')

        assert resp.status_code == 200
        content_disposition = resp.headers.get('Content-Disposition')
        assert content_disposition is not None, "Content-Disposition header missing"
        assert content_disposition.startswith('inline'), (
            f"Content-Disposition should start with 'inline', "
            f"got '{content_disposition}'"
        )

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(invoice_number=invoice_number_st)
    def test_content_disposition_filename_ends_with_preview_pdf(self, invoice_number):
        """
        For any valid invoice_number, the filename in Content-Disposition
        always ends with '_PREVIEW.pdf'.

        Feature: zzp-invoice-pdf-preview, Property 4: Content-Disposition filename format
        **Validates: Requirements 2.4**
        """
        client, mock_svc = _make_preview_client_and_service()

        mock_svc.get_invoice.return_value = {
            'id': 1,
            'invoice_number': invoice_number,
            'status': 'draft',
            'contact_id': 1,
            'contact': {'company_name': 'Test BV', 'country': 'NL'},
        }
        mock_svc.preview_invoice.return_value = BytesIO(b'%PDF-1.4')

        resp = client.get('/api/zzp/invoices/1/preview')

        assert resp.status_code == 200
        content_disposition = resp.headers.get('Content-Disposition')
        assert content_disposition is not None
        assert content_disposition.endswith('_PREVIEW.pdf"'), (
            f"Content-Disposition filename should end with '_PREVIEW.pdf\"', "
            f"got '{content_disposition}'"
        )


# ── Email Preview Route Tests ───────────────────────────────


@pytest.mark.api
def test_email_preview_success_returns_200_with_correct_json(preview_client, mock_invoice_service):
    """Successful email preview returns 200 with correct JSON structure.

    Requirements: 8.8
    """
    mock_invoice_service.get_email_preview.return_value = {
        'subject': 'Factuur INV-2024-001 van Company BV',
        'html_body': '<p>Geachte Client BV,</p><p>Bijgevoegd vindt u factuur INV-2024-001.</p>',
        'recipient': 'client@example.com',
        'bcc': 'admin@freelancer.nl',
        'attachment_filename': 'INV-2024-001.pdf',
    }

    resp = preview_client.get('/api/zzp/invoices/1/email-preview')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'data' in data

    email_data = data['data']
    assert email_data['subject'] == 'Factuur INV-2024-001 van Company BV'
    assert email_data['html_body'] == '<p>Geachte Client BV,</p><p>Bijgevoegd vindt u factuur INV-2024-001.</p>'
    assert email_data['recipient'] == 'client@example.com'
    assert email_data['bcc'] == 'admin@freelancer.nl'
    assert email_data['attachment_filename'] == 'INV-2024-001.pdf'


@pytest.mark.api
def test_email_preview_non_draft_invoice_returns_400(preview_client, mock_invoice_service):
    """Non-draft invoice email preview returns 400 with appropriate error.

    Requirements: 8.8
    """
    mock_invoice_service.get_email_preview.side_effect = ValueError(
        "Only draft invoices can be previewed"
    )

    resp = preview_client.get('/api/zzp/invoices/1/email-preview')

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'Only draft invoices can be previewed' in data['error']


@pytest.mark.api
def test_email_preview_contact_without_email_returns_400(preview_client, mock_invoice_service):
    """Contact without email address returns 400 with missing email error.

    Requirements: 8.9
    """
    mock_invoice_service.get_email_preview.side_effect = ValueError(
        "Contact email address is missing"
    )

    resp = preview_client.get('/api/zzp/invoices/1/email-preview')

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'Contact email address is missing' in data['error']


@pytest.mark.api
def test_email_preview_bcc_contains_admin_email(preview_client, mock_invoice_service):
    """Email preview BCC field contains the tenant admin email.

    Requirements: 8.12
    """
    admin_email = 'peter@mycompany.nl'
    mock_invoice_service.get_email_preview.return_value = {
        'subject': 'Invoice INV-2024-005 from My Company BV',
        'html_body': '<p>Dear Client,</p><p>Please find attached invoice INV-2024-005.</p>',
        'recipient': 'client@otherbusiness.com',
        'bcc': admin_email,
        'attachment_filename': 'INV-2024-005.pdf',
    }

    resp = preview_client.get('/api/zzp/invoices/5/email-preview')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['bcc'] == admin_email


@pytest.mark.api
def test_email_preview_not_found_returns_404(preview_client, mock_invoice_service):
    """Non-existent invoice returns 404 for email preview.

    Requirements: 8.8
    """
    mock_invoice_service.get_email_preview.side_effect = ValueError("Invoice not found")

    resp = preview_client.get('/api/zzp/invoices/999/email-preview')

    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False
    assert 'not found' in data['error'].lower()
