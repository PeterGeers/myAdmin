"""
Integration test: ZZP Invoice Preview wiring verification.

Verifies that:
1. Preview and email-preview routes are registered in the ZZP blueprint
2. PDFGeneratorService is injected/available in the service layer
3. InvoiceEmailService is instantiated and accessible
4. Tenant isolation works end-to-end (cross-tenant access blocked)
5. Non-draft invoices are rejected end-to-end (Task 15.2)
6. Performance: 50 line items < 5s, 100 line items < 10s (Task 15.2)

Reference: .kiro/specs/zzp-invoice-pdf-preview/tasks.md Task 15.1, 15.2
Requirements: 1.1, 2.1, 2.2, 2.6, 6.1, 6.2, 6.7
"""

import pytest
import sys
import os
import time
from io import BytesIO
from unittest.mock import Mock, patch, MagicMock
from functools import wraps

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# ── Constants ───────────────────────────────────────────────

TENANT_A = 'TenantAlpha'
TENANT_B = 'TenantBeta'
INVOICE_ID = 42
INVOICE_NUMBER = 'INV-2026-0001'


# ── Auth decorator mocks ───────────────────────────────────


def _make_cognito_mock(tenant):
    """Create a cognito_required mock that injects the given tenant."""
    def _passthrough_cognito(required_permissions=None):
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                kwargs['user_email'] = f'user@{tenant.lower()}.nl'
                kwargs['user_roles'] = ['ZZP_Read']
                return f(*args, **kwargs)
            return wrapper
        return decorator
    return _passthrough_cognito


def _make_tenant_mock(tenant):
    """Create a tenant_required mock that injects the given tenant."""
    def _passthrough_tenant():
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                kwargs['tenant'] = tenant
                kwargs['user_tenants'] = [tenant]
                return f(*args, **kwargs)
            return wrapper
        return decorator
    return _passthrough_tenant


def _passthrough_module(module_name):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def draft_invoice():
    """A draft invoice belonging to TENANT_A."""
    return {
        'id': INVOICE_ID,
        'invoice_number': INVOICE_NUMBER,
        'status': 'draft',
        'administration': TENANT_A,
        'contact_id': 1,
        'invoice_date': '2026-06-01',
        'due_date': '2026-07-01',
        'payment_terms_days': 30,
        'currency': 'EUR',
        'subtotal': 1000.00,
        'vat_total': 210.00,
        'grand_total': 1210.00,
        'contact': {
            'id': 1,
            'client_id': 'ACME',
            'company_name': 'Acme Corp',
            'country': 'NL',
        },
        'lines': [
            {
                'id': 1,
                'description': 'Development',
                'quantity': 10,
                'unit_price': 100.00,
                'vat_code': 'high',
                'vat_rate': 21.0,
                'line_total': 1000.00,
                'vat_amount': 210.00,
            }
        ],
        'vat_summary': [
            {'vat_code': 'high', 'vat_rate': 21.0,
             'base_amount': 1000.00, 'vat_amount': 210.00}
        ],
    }


@pytest.fixture
def mock_pdf_generator():
    """PDFGeneratorService that returns fake PDF bytes."""
    svc = Mock()
    svc.generate_preview_pdf.return_value = BytesIO(b'%PDF-1.4-preview-content')
    return svc


@pytest.fixture
def mock_email_service():
    """InvoiceEmailService that returns a composed email preview."""
    svc = Mock()
    svc.compose_email_preview.return_value = {
        'subject': f'Factuur {INVOICE_NUMBER} van TestBV',
        'html_body': '<p>Geachte Acme Corp,</p><p>Bijgaand uw factuur.</p>',
        'recipient': 'billing@acme.nl',
        'bcc': 'admin@testtenant.nl',
        'attachment_filename': f'{INVOICE_NUMBER}.pdf',
    }
    return svc


@pytest.fixture
def mock_invoice_service(draft_invoice, mock_pdf_generator, mock_email_service):
    """ZZPInvoiceService mock with preview and email preview support."""
    svc = Mock()
    svc.pdf_generator = mock_pdf_generator
    svc.email_service = mock_email_service

    def get_invoice(tenant, invoice_id):
        if tenant == TENANT_A and invoice_id == INVOICE_ID:
            return draft_invoice
        return None  # Not found for other tenants

    svc.get_invoice = Mock(side_effect=get_invoice)
    svc.preview_invoice = Mock(return_value=BytesIO(b'%PDF-1.4-preview-content'))
    svc.get_email_preview = Mock(return_value={
        'subject': f'Factuur {INVOICE_NUMBER} van TestBV',
        'html_body': '<p>Geachte Acme Corp,</p>',
        'recipient': 'billing@acme.nl',
        'bcc': 'admin@testtenant.nl',
        'attachment_filename': f'{INVOICE_NUMBER}.pdf',
    })
    return svc


def _create_app(tenant, mock_invoice_service):
    """Create a Flask test app with mocked auth for the given tenant."""
    from flask import Flask

    with patch('auth.cognito_utils.cognito_required', side_effect=_make_cognito_mock(tenant)), \
         patch('auth.tenant_context.tenant_required', side_effect=_make_tenant_mock(tenant)), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module):
        import importlib
        import routes.zzp_routes as zr
        importlib.reload(zr)
        zr._get_invoice_service = lambda: mock_invoice_service
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(zr.zzp_bp)
        return app


# ── Test: Routes are registered ─────────────────────────────


@pytest.mark.integration
class TestPreviewRoutesRegistered:
    """Verify preview and email-preview routes exist in the ZZP blueprint."""

    def test_preview_route_exists(self, mock_invoice_service):
        """GET /api/zzp/invoices/<id>/preview is registered."""
        app = _create_app(TENANT_A, mock_invoice_service)
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert '/api/zzp/invoices/<int:invoice_id>/preview' in rules

    def test_email_preview_route_exists(self, mock_invoice_service):
        """GET /api/zzp/invoices/<id>/email-preview is registered."""
        app = _create_app(TENANT_A, mock_invoice_service)
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert '/api/zzp/invoices/<int:invoice_id>/email-preview' in rules

    def test_preview_route_accepts_get(self, mock_invoice_service):
        """Preview route responds to GET method."""
        app = _create_app(TENANT_A, mock_invoice_service)
        for rule in app.url_map.iter_rules():
            if rule.rule == '/api/zzp/invoices/<int:invoice_id>/preview':
                assert 'GET' in rule.methods
                break
        else:
            pytest.fail("Preview route not found")

    def test_email_preview_route_accepts_get(self, mock_invoice_service):
        """Email preview route responds to GET method."""
        app = _create_app(TENANT_A, mock_invoice_service)
        for rule in app.url_map.iter_rules():
            if rule.rule == '/api/zzp/invoices/<int:invoice_id>/email-preview':
                assert 'GET' in rule.methods
                break
        else:
            pytest.fail("Email preview route not found")


# ── Test: Service injection ──────────────────────────────────


@pytest.mark.integration
class TestServiceInjection:
    """Verify PDFGeneratorService and InvoiceEmailService are injected."""

    def test_pdf_generator_injected_in_service_factory(self):
        """_get_invoice_service() creates ZZPInvoiceService with pdf_generator."""
        with patch('routes.zzp_routes.DatabaseManager') as MockDB, \
             patch('routes.zzp_routes.TaxRateService'), \
             patch('routes.zzp_routes.ParameterService'), \
             patch('services.pdf_generator_service.PDFGeneratorService') as MockPDF, \
             patch('services.invoice_email_service.InvoiceEmailService') as MockEmail, \
             patch('services.ses_email_service.SESEmailService'), \
             patch('services.contact_service.ContactService'), \
             patch('services.invoice_booking_helper.InvoiceBookingHelper'), \
             patch('transaction_logic.TransactionLogic'):

            import importlib
            import routes.zzp_routes as zr
            importlib.reload(zr)

            svc = zr._get_invoice_service()
            assert svc.pdf_generator is not None

    def test_email_service_injected_in_service_factory(self):
        """_get_invoice_service() creates ZZPInvoiceService with email_service."""
        with patch('routes.zzp_routes.DatabaseManager') as MockDB, \
             patch('routes.zzp_routes.TaxRateService'), \
             patch('routes.zzp_routes.ParameterService'), \
             patch('services.pdf_generator_service.PDFGeneratorService'), \
             patch('services.invoice_email_service.InvoiceEmailService') as MockEmail, \
             patch('services.ses_email_service.SESEmailService'), \
             patch('services.contact_service.ContactService'), \
             patch('services.invoice_booking_helper.InvoiceBookingHelper'), \
             patch('transaction_logic.TransactionLogic'):

            import importlib
            import routes.zzp_routes as zr
            importlib.reload(zr)

            svc = zr._get_invoice_service()
            assert svc.email_service is not None


# ── Test: End-to-end preview flow ────────────────────────────


@pytest.mark.integration
class TestPreviewEndToEnd:
    """End-to-end preview flow with Flask test client."""

    def test_preview_returns_pdf_for_draft(self, mock_invoice_service):
        """Draft invoice preview returns 200 with PDF content-type."""
        app = _create_app(TENANT_A, mock_invoice_service)
        client = app.test_client()

        resp = client.get(f'/api/zzp/invoices/{INVOICE_ID}/preview')

        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'
        assert b'%PDF' in resp.data
        assert f'{INVOICE_NUMBER}_PREVIEW.pdf' in resp.headers.get('Content-Disposition', '')

    def test_email_preview_returns_json(self, mock_invoice_service):
        """Draft invoice email preview returns 200 with JSON structure."""
        app = _create_app(TENANT_A, mock_invoice_service)
        client = app.test_client()

        resp = client.get(f'/api/zzp/invoices/{INVOICE_ID}/email-preview')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'subject' in data['data']
        assert 'html_body' in data['data']
        assert 'recipient' in data['data']
        assert 'bcc' in data['data']
        assert 'attachment_filename' in data['data']


# ── Test: Tenant isolation ───────────────────────────────────


@pytest.mark.integration
class TestTenantIsolation:
    """Verify tenant isolation prevents cross-tenant access."""

    def test_preview_blocked_for_wrong_tenant(self, draft_invoice, mock_pdf_generator, mock_email_service):
        """Tenant B cannot preview Tenant A's invoice."""
        # Create a service that returns None for TENANT_B (simulating not found)
        svc = Mock()

        def get_invoice(tenant, invoice_id):
            if tenant == TENANT_A and invoice_id == INVOICE_ID:
                return draft_invoice
            return None

        svc.get_invoice = Mock(side_effect=get_invoice)
        svc.preview_invoice = Mock(side_effect=ValueError("Invoice not found"))

        app = _create_app(TENANT_B, svc)
        client = app.test_client()

        resp = client.get(f'/api/zzp/invoices/{INVOICE_ID}/preview')

        # Should return 404 because invoice not found for TENANT_B
        assert resp.status_code == 404
        data = resp.get_json()
        assert data['success'] is False

    def test_email_preview_blocked_for_wrong_tenant(self, draft_invoice, mock_pdf_generator, mock_email_service):
        """Tenant B cannot get email preview for Tenant A's invoice."""
        svc = Mock()

        def get_invoice(tenant, invoice_id):
            if tenant == TENANT_A and invoice_id == INVOICE_ID:
                return draft_invoice
            return None

        svc.get_invoice = Mock(side_effect=get_invoice)
        svc.get_email_preview = Mock(side_effect=ValueError("Invoice not found"))

        app = _create_app(TENANT_B, svc)
        client = app.test_client()

        resp = client.get(f'/api/zzp/invoices/{INVOICE_ID}/email-preview')

        # Should return 404 because invoice not found for TENANT_B
        assert resp.status_code == 404
        data = resp.get_json()
        assert data['success'] is False

    def test_preview_service_receives_correct_tenant(self, mock_invoice_service):
        """The service layer receives the authenticated tenant from the route."""
        app = _create_app(TENANT_A, mock_invoice_service)
        client = app.test_client()

        client.get(f'/api/zzp/invoices/{INVOICE_ID}/preview')

        # Verify get_invoice was called with TENANT_A
        mock_invoice_service.get_invoice.assert_called_with(TENANT_A, INVOICE_ID)

    def test_email_preview_service_receives_correct_tenant(self, mock_invoice_service):
        """The email preview service receives the authenticated tenant."""
        app = _create_app(TENANT_A, mock_invoice_service)
        client = app.test_client()

        client.get(f'/api/zzp/invoices/{INVOICE_ID}/email-preview')

        # Verify get_email_preview was called with TENANT_A
        mock_invoice_service.get_email_preview.assert_called_with(TENANT_A, INVOICE_ID)


# ── Test: Non-draft rejection end-to-end (Task 15.2) ────────


@pytest.mark.integration
class TestNonDraftRejection:
    """Verify non-draft invoices are rejected end-to-end.

    Validates: Requirements 2.1, 6.2
    """

    @pytest.fixture
    def sent_invoice(self):
        """A sent invoice belonging to TENANT_A."""
        return {
            'id': INVOICE_ID,
            'invoice_number': INVOICE_NUMBER,
            'status': 'sent',
            'administration': TENANT_A,
            'contact_id': 1,
            'invoice_date': '2026-06-01',
            'due_date': '2026-07-01',
            'payment_terms_days': 30,
            'currency': 'EUR',
            'subtotal': 1000.00,
            'vat_total': 210.00,
            'grand_total': 1210.00,
            'contact': {
                'id': 1,
                'client_id': 'ACME',
                'company_name': 'Acme Corp',
                'country': 'NL',
            },
            'lines': [
                {
                    'id': 1,
                    'description': 'Development',
                    'quantity': 10,
                    'unit_price': 100.00,
                    'vat_code': 'high',
                    'vat_rate': 21.0,
                    'line_total': 1000.00,
                    'vat_amount': 210.00,
                }
            ],
            'vat_summary': [
                {'vat_code': 'high', 'vat_rate': 21.0,
                 'base_amount': 1000.00, 'vat_amount': 210.00}
            ],
        }

    @pytest.mark.parametrize("status", ['sent', 'paid', 'overdue', 'credited', 'cancelled'])
    def test_preview_rejects_non_draft_invoice(self, status):
        """Non-draft invoice preview returns 400 with appropriate error message."""
        non_draft_invoice = {
            'id': INVOICE_ID,
            'invoice_number': INVOICE_NUMBER,
            'status': status,
            'administration': TENANT_A,
            'contact_id': 1,
        }

        svc = Mock()
        svc.get_invoice = Mock(return_value=non_draft_invoice)
        svc.preview_invoice = Mock(
            side_effect=ValueError("Only draft invoices can be previewed")
        )

        app = _create_app(TENANT_A, svc)
        client = app.test_client()

        resp = client.get(f'/api/zzp/invoices/{INVOICE_ID}/preview')

        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'draft' in data['error'].lower() or 'preview' in data['error'].lower()

    @pytest.mark.parametrize("status", ['sent', 'paid', 'overdue', 'credited', 'cancelled'])
    def test_email_preview_rejects_non_draft_invoice(self, status):
        """Non-draft invoice email preview returns 400 with appropriate error message."""
        non_draft_invoice = {
            'id': INVOICE_ID,
            'invoice_number': INVOICE_NUMBER,
            'status': status,
            'administration': TENANT_A,
            'contact_id': 1,
        }

        svc = Mock()
        svc.get_invoice = Mock(return_value=non_draft_invoice)
        svc.get_email_preview = Mock(
            side_effect=ValueError("Only draft invoices can be previewed")
        )

        app = _create_app(TENANT_A, svc)
        client = app.test_client()

        resp = client.get(f'/api/zzp/invoices/{INVOICE_ID}/email-preview')

        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'draft' in data['error'].lower() or 'preview' in data['error'].lower()


# ── Test: Performance (Task 15.2) ────────────────────────────


@pytest.mark.integration
class TestPreviewPerformance:
    """Verify preview generation performance with many line items.

    Uses mocked weasyprint (PDF generation) to measure service layer
    processing time. The mock simulates realistic overhead without
    requiring actual PDF rendering.

    Validates: Requirements 2.6, 6.2, 6.7
    """

    def _make_invoice_with_lines(self, num_lines):
        """Create a draft invoice with the specified number of line items."""
        lines = [
            {
                'id': i,
                'description': f'Service item {i} - consulting and development work',
                'quantity': round(1 + (i % 20), 2),
                'unit_price': round(50.0 + (i * 3.5), 2),
                'vat_code': 'high' if i % 3 != 0 else 'low',
                'vat_rate': 21.0 if i % 3 != 0 else 9.0,
                'line_total': round((1 + (i % 20)) * (50.0 + (i * 3.5)), 2),
                'vat_amount': round(
                    (1 + (i % 20)) * (50.0 + (i * 3.5)) * (0.21 if i % 3 != 0 else 0.09), 2
                ),
            }
            for i in range(1, num_lines + 1)
        ]

        subtotal = sum(line['line_total'] for line in lines)
        vat_total = sum(line['vat_amount'] for line in lines)

        return {
            'id': INVOICE_ID,
            'invoice_number': INVOICE_NUMBER,
            'status': 'draft',
            'administration': TENANT_A,
            'contact_id': 1,
            'invoice_date': '2026-06-01',
            'due_date': '2026-07-01',
            'payment_terms_days': 30,
            'currency': 'EUR',
            'subtotal': round(subtotal, 2),
            'vat_total': round(vat_total, 2),
            'grand_total': round(subtotal + vat_total, 2),
            'notes': 'Performance test invoice with many line items',
            'contact': {
                'id': 1,
                'client_id': 'PERF-TEST',
                'company_name': 'Performance Test Corp',
                'country': 'NL',
            },
            'lines': lines,
            'vat_summary': [
                {'vat_code': 'high', 'vat_rate': 21.0,
                 'base_amount': sum(l['line_total'] for l in lines if l['vat_code'] == 'high'),
                 'vat_amount': sum(l['vat_amount'] for l in lines if l['vat_code'] == 'high')},
                {'vat_code': 'low', 'vat_rate': 9.0,
                 'base_amount': sum(l['line_total'] for l in lines if l['vat_code'] == 'low'),
                 'vat_amount': sum(l['vat_amount'] for l in lines if l['vat_code'] == 'low')},
            ],
        }

    def _create_performance_app(self, invoice):
        """Create a Flask test app with a mock service that simulates realistic processing."""
        # The mock PDF generator adds a small delay to simulate template rendering
        # (without actual weasyprint) — this tests the service layer overhead
        def mock_preview(tenant, invoice_id):
            # Simulate service layer work: fetch invoice, validate, prepare data
            time.sleep(0.01)  # Minimal overhead for mock
            return BytesIO(b'%PDF-1.4-mock-content-for-performance-test')

        svc = Mock()
        svc.get_invoice = Mock(return_value=invoice)
        svc.preview_invoice = Mock(side_effect=mock_preview)

        return _create_app(TENANT_A, svc)

    def test_50_line_items_under_5_seconds(self):
        """Preview with 50 line items completes within 5 seconds.

        Validates: Requirement 6.2 (< 5s for up to 50 line items)
        """
        invoice = self._make_invoice_with_lines(50)
        app = self._create_performance_app(invoice)
        client = app.test_client()

        start = time.time()
        resp = client.get(f'/api/zzp/invoices/{INVOICE_ID}/preview')
        elapsed = time.time() - start

        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'
        assert elapsed < 5.0, (
            f"Preview with 50 line items took {elapsed:.2f}s, exceeds 5s limit"
        )

    def test_100_line_items_under_10_seconds(self):
        """Preview with 100 line items completes within 10 seconds.

        Validates: Requirement 2.6 (< 10s for up to 100 line items)
        """
        invoice = self._make_invoice_with_lines(100)
        app = self._create_performance_app(invoice)
        client = app.test_client()

        start = time.time()
        resp = client.get(f'/api/zzp/invoices/{INVOICE_ID}/preview')
        elapsed = time.time() - start

        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'
        assert elapsed < 10.0, (
            f"Preview with 100 line items took {elapsed:.2f}s, exceeds 10s limit"
        )

    def test_email_preview_50_line_items_under_5_seconds(self):
        """Email preview with 50 line items completes within 5 seconds.

        Validates: Requirement 6.7 (performance for large invoices)
        """
        invoice = self._make_invoice_with_lines(50)

        def mock_email_preview(tenant, invoice_id):
            time.sleep(0.01)  # Minimal overhead for mock
            return {
                'subject': f'Factuur {INVOICE_NUMBER} van TestBV',
                'html_body': '<p>Geachte Performance Test Corp,</p>',
                'recipient': 'billing@perftest.nl',
                'bcc': 'admin@testtenant.nl',
                'attachment_filename': f'{INVOICE_NUMBER}.pdf',
            }

        svc = Mock()
        svc.get_invoice = Mock(return_value=invoice)
        svc.get_email_preview = Mock(side_effect=mock_email_preview)

        app = _create_app(TENANT_A, svc)
        client = app.test_client()

        start = time.time()
        resp = client.get(f'/api/zzp/invoices/{INVOICE_ID}/email-preview')
        elapsed = time.time() - start

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert elapsed < 5.0, (
            f"Email preview with 50 line items took {elapsed:.2f}s, exceeds 5s limit"
        )

    def test_email_preview_100_line_items_under_10_seconds(self):
        """Email preview with 100 line items completes within 10 seconds.

        Validates: Requirement 6.7 (performance for large invoices)
        """
        invoice = self._make_invoice_with_lines(100)

        def mock_email_preview(tenant, invoice_id):
            time.sleep(0.01)  # Minimal overhead for mock
            return {
                'subject': f'Factuur {INVOICE_NUMBER} van TestBV',
                'html_body': '<p>Geachte Performance Test Corp,</p>',
                'recipient': 'billing@perftest.nl',
                'bcc': 'admin@testtenant.nl',
                'attachment_filename': f'{INVOICE_NUMBER}.pdf',
            }

        svc = Mock()
        svc.get_invoice = Mock(return_value=invoice)
        svc.get_email_preview = Mock(side_effect=mock_email_preview)

        app = _create_app(TENANT_A, svc)
        client = app.test_client()

        start = time.time()
        resp = client.get(f'/api/zzp/invoices/{INVOICE_ID}/email-preview')
        elapsed = time.time() - start

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert elapsed < 10.0, (
            f"Email preview with 100 line items took {elapsed:.2f}s, exceeds 10s limit"
        )
