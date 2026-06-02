"""
Test SysAdmin Test Tool Routes

Tests for the Invoice Processing Test Tool API endpoints.
Validates authentication, authorization, and input validation.
"""

import pytest
import io
from unittest.mock import patch, MagicMock
from flask import Flask


@pytest.fixture
def app():
    """Create Flask app for testing"""
    app = Flask(__name__)
    app.config['TESTING'] = True

    from routes.sysadmin_routes import sysadmin_bp
    app.register_blueprint(sysadmin_bp)

    return app


@pytest.fixture
def sysadmin_client(app):
    """Create test client with SysAdmin authentication"""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_auth:
        mock_auth.return_value = ('sysadmin@myadmin.com', ['SysAdmin'], None)
        yield app.test_client()


@pytest.fixture
def non_sysadmin_client(app):
    """Create test client with non-SysAdmin authentication"""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_auth:
        mock_auth.return_value = ('user@myadmin.com', ['Finance_CRUD'], None)
        yield app.test_client()


@pytest.fixture
def unauthenticated_client(app):
    """Create test client without authentication"""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_auth:
        mock_auth.return_value = (None, None, {
            'statusCode': 401,
            'body': '{"error": "Authentication required"}'
        })
        yield app.test_client()


# ============================================================================
# Authentication & Authorization Tests
# ============================================================================


class TestAuthAccess:
    """Test authentication and authorization for all endpoints."""

    def test_process_unauthenticated_returns_401(self, unauthenticated_client):
        """Unauthenticated requests to /process return 401."""
        response = unauthenticated_client.post('/api/sysadmin/test-tool/process')
        assert response.status_code == 401

    def test_rerun_prompt_unauthenticated_returns_401(self, unauthenticated_client):
        """Unauthenticated requests to /rerun-prompt return 401."""
        response = unauthenticated_client.post('/api/sysadmin/test-tool/rerun-prompt')
        assert response.status_code == 401

    def test_vendor_history_unauthenticated_returns_401(self, unauthenticated_client):
        """Unauthenticated requests to /vendor-history return 401."""
        response = unauthenticated_client.get('/api/sysadmin/test-tool/vendor-history')
        assert response.status_code == 401

    def test_process_non_sysadmin_returns_403(self, non_sysadmin_client):
        """Non-SysAdmin users get 403 on /process."""
        response = non_sysadmin_client.post('/api/sysadmin/test-tool/process')
        assert response.status_code == 403

    def test_rerun_prompt_non_sysadmin_returns_403(self, non_sysadmin_client):
        """Non-SysAdmin users get 403 on /rerun-prompt."""
        response = non_sysadmin_client.post('/api/sysadmin/test-tool/rerun-prompt')
        assert response.status_code == 403

    def test_vendor_history_non_sysadmin_returns_403(self, non_sysadmin_client):
        """Non-SysAdmin users get 403 on /vendor-history."""
        response = non_sysadmin_client.get('/api/sysadmin/test-tool/vendor-history')
        assert response.status_code == 403


# ============================================================================
# POST /process - File Validation Tests
# ============================================================================


class TestProcessFileValidation:
    """Test file upload validation on POST /process."""

    def test_no_file_returns_400(self, sysadmin_client):
        """Missing file returns 400."""
        response = sysadmin_client.post('/api/sysadmin/test-tool/process')
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'No file provided' in data['error']

    def test_unsupported_extension_returns_400(self, sysadmin_client):
        """Unsupported file extension returns 400."""
        file_data = io.BytesIO(b'fake content')
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/process',
            data={'file': (file_data, 'test.exe')},
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'Unsupported file type' in data['error']

    def test_oversized_file_returns_400(self, sysadmin_client):
        """File exceeding 20 MB returns 400."""
        # Create a file just over 20 MB
        file_data = io.BytesIO(b'x' * (20 * 1024 * 1024 + 1))
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/process',
            data={'file': (file_data, 'test.pdf')},
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert '20 MB' in data['error']

    def test_empty_file_returns_400(self, sysadmin_client):
        """Empty file (0 bytes) returns 400."""
        file_data = io.BytesIO(b'')
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/process',
            data={'file': (file_data, 'test.pdf')},
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'empty' in data['error'].lower()

    def test_valid_pdf_accepted(self, sysadmin_client):
        """Valid PDF file passes validation and processes successfully."""
        file_data = io.BytesIO(b'%PDF-1.4 fake content')
        with patch('routes.sysadmin_test_tool.InvoiceTestService') as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.process_file_dry_run.return_value = {
                'pipeline_result': {'raw_text': 'test', 'folder_name': 'TestVendor'},
                'performance': {'total_duration_ms': 100},
                'ai_usage_preview': None,
                'execution_log': '',
                'errors': [],
            }
            mock_svc_cls.return_value = mock_svc
            response = sysadmin_client.post(
                '/api/sysadmin/test-tool/process',
                data={'file': (file_data, 'invoice.pdf')},
                content_type='multipart/form-data'
            )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_valid_jpg_accepted(self, sysadmin_client):
        """Valid JPG file passes validation."""
        file_data = io.BytesIO(b'\xff\xd8\xff fake jpeg')
        with patch('routes.sysadmin_test_tool.InvoiceTestService') as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.process_file_dry_run.return_value = {
                'pipeline_result': {}, 'performance': {},
                'ai_usage_preview': None, 'execution_log': '', 'errors': [],
            }
            mock_svc_cls.return_value = mock_svc
            response = sysadmin_client.post(
                '/api/sysadmin/test-tool/process',
                data={'file': (file_data, 'scan.JPG')},
                content_type='multipart/form-data'
            )
        assert response.status_code == 200

    def test_valid_csv_accepted(self, sysadmin_client):
        """Valid CSV file passes validation."""
        file_data = io.BytesIO(b'date,amount\n2024-01-01,100')
        with patch('routes.sysadmin_test_tool.InvoiceTestService') as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.process_file_dry_run.return_value = {
                'pipeline_result': {}, 'performance': {},
                'ai_usage_preview': None, 'execution_log': '', 'errors': [],
            }
            mock_svc_cls.return_value = mock_svc
            response = sysadmin_client.post(
                '/api/sysadmin/test-tool/process',
                data={'file': (file_data, 'transactions.csv')},
                content_type='multipart/form-data'
            )
        assert response.status_code == 200

    def test_valid_eml_accepted(self, sysadmin_client):
        """Valid EML file passes validation."""
        file_data = io.BytesIO(b'From: test@example.com\nContent-Type: text/html')
        with patch('routes.sysadmin_test_tool.InvoiceTestService') as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.process_file_dry_run.return_value = {
                'pipeline_result': {}, 'performance': {},
                'ai_usage_preview': None, 'execution_log': '', 'errors': [],
            }
            mock_svc_cls.return_value = mock_svc
            response = sysadmin_client.post(
                '/api/sysadmin/test-tool/process',
                data={'file': (file_data, 'invoice.eml')},
                content_type='multipart/form-data'
            )
        assert response.status_code == 200

    def test_valid_mhtml_accepted(self, sysadmin_client):
        """Valid MHTML file passes validation."""
        file_data = io.BytesIO(b'MIME-Version: 1.0\nContent-Type: multipart/related')
        with patch('routes.sysadmin_test_tool.InvoiceTestService') as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.process_file_dry_run.return_value = {
                'pipeline_result': {}, 'performance': {},
                'ai_usage_preview': None, 'execution_log': '', 'errors': [],
            }
            mock_svc_cls.return_value = mock_svc
            response = sysadmin_client.post(
                '/api/sysadmin/test-tool/process',
                data={'file': (file_data, 'page.mhtml')},
                content_type='multipart/form-data'
            )
        assert response.status_code == 200

    def test_case_insensitive_extension(self, sysadmin_client):
        """File extension check is case-insensitive."""
        file_data = io.BytesIO(b'fake png content')
        with patch('routes.sysadmin_test_tool.InvoiceTestService') as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.process_file_dry_run.return_value = {
                'pipeline_result': {}, 'performance': {},
                'ai_usage_preview': None, 'execution_log': '', 'errors': [],
            }
            mock_svc_cls.return_value = mock_svc
            response = sysadmin_client.post(
                '/api/sysadmin/test-tool/process',
                data={'file': (file_data, 'image.PNG')},
                content_type='multipart/form-data'
            )
        assert response.status_code == 200

    def test_invalid_vendor_name_returns_400(self, sysadmin_client):
        """Invalid vendor name returns 400."""
        file_data = io.BytesIO(b'fake content')
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/process',
            data={
                'file': (file_data, 'test.pdf'),
                'folderName': 'invalid vendor name!'  # spaces and special chars
            },
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'vendor name' in data['error'].lower() or 'Invalid' in data['error']

    def test_valid_vendor_name_accepted(self, sysadmin_client):
        """Valid vendor name passes validation."""
        file_data = io.BytesIO(b'fake content')
        with patch('routes.sysadmin_test_tool.InvoiceTestService') as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.process_file_dry_run.return_value = {
                'pipeline_result': {}, 'performance': {},
                'ai_usage_preview': None, 'execution_log': '', 'errors': [],
            }
            mock_svc_cls.return_value = mock_svc
            response = sysadmin_client.post(
                '/api/sysadmin/test-tool/process',
                data={
                    'file': (file_data, 'test.pdf'),
                    'folderName': 'My-Vendor_123'
                },
                content_type='multipart/form-data'
            )
        assert response.status_code == 200

    def test_default_vendor_name_used(self, sysadmin_client):
        """When no folderName provided, defaults to TestVendor (passes validation)."""
        file_data = io.BytesIO(b'fake content')
        with patch('routes.sysadmin_test_tool.InvoiceTestService') as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.process_file_dry_run.return_value = {
                'pipeline_result': {'folder_name': 'TestVendor'}, 'performance': {},
                'ai_usage_preview': None, 'execution_log': '', 'errors': [],
            }
            mock_svc_cls.return_value = mock_svc
            response = sysadmin_client.post(
                '/api/sysadmin/test-tool/process',
                data={'file': (file_data, 'test.pdf')},
                content_type='multipart/form-data'
            )
        assert response.status_code == 200


# ============================================================================
# POST /rerun-prompt - Prompt Validation Tests
# ============================================================================


class TestRerunPromptValidation:
    """Test prompt validation on POST /rerun-prompt."""

    def test_missing_body_returns_400(self, sysadmin_client):
        """Missing request body returns 400."""
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/rerun-prompt',
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_missing_text_content_returns_400(self, sysadmin_client):
        """Missing text_content returns 400."""
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/rerun-prompt',
            json={'custom_prompt': 'Extract the invoice data'}
        )
        assert response.status_code == 400
        data = response.get_json()
        assert 'text_content' in data['error']

    def test_missing_custom_prompt_returns_400(self, sysadmin_client):
        """Missing custom_prompt returns 400."""
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/rerun-prompt',
            json={'text_content': 'Invoice content here'}
        )
        assert response.status_code == 400
        data = response.get_json()
        assert 'custom_prompt' in data['error']

    def test_empty_prompt_returns_400(self, sysadmin_client):
        """Empty prompt (0 chars) returns 400."""
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/rerun-prompt',
            json={
                'text_content': 'Invoice content',
                'custom_prompt': ''
            }
        )
        assert response.status_code == 400
        data = response.get_json()
        assert 'Prompt must be' in data['error'] or 'characters' in data['error']

    def test_prompt_exceeding_10000_returns_400(self, sysadmin_client):
        """Prompt exceeding 10,000 characters returns 400."""
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/rerun-prompt',
            json={
                'text_content': 'Invoice content',
                'custom_prompt': 'x' * 10_001
            }
        )
        assert response.status_code == 400
        data = response.get_json()
        assert 'Prompt must be' in data['error'] or 'characters' in data['error']

    @patch('routes.sysadmin_test_tool.InvoiceTestService')
    def test_valid_prompt_accepted(self, MockService, sysadmin_client):
        """Valid prompt (1-10,000 chars) passes validation and calls service."""
        mock_instance = MockService.return_value
        mock_instance.rerun_with_custom_prompt.return_value = {
            'success': True,
            'extraction_result': {'date': '2024-01-15', 'total_amount': 100.0, 'vat_amount': 21.0, 'description': 'Test', 'vendor': 'SomeVendor'},
            'performance': {'ai_duration_ms': 500, 'ai_model': 'test-model', 'ai_tokens': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}},
            'ai_usage_preview': None,
            'errors': [],
        }
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/rerun-prompt',
            json={
                'text_content': 'Invoice from SomeVendor dated 2024-01-15',
                'custom_prompt': 'Extract invoice data: date, amount, VAT, description, vendor'
            }
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['extraction_result']['vendor'] == 'SomeVendor'

    @patch('routes.sysadmin_test_tool.InvoiceTestService')
    def test_prompt_at_max_length_accepted(self, MockService, sysadmin_client):
        """Prompt at exactly 10,000 chars passes validation."""
        mock_instance = MockService.return_value
        mock_instance.rerun_with_custom_prompt.return_value = {
            'success': True,
            'extraction_result': {'date': '', 'total_amount': 0.0, 'vat_amount': 0.0, 'description': '', 'vendor': ''},
            'performance': {'ai_duration_ms': 100, 'ai_model': 'test-model', 'ai_tokens': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}},
            'ai_usage_preview': None,
            'errors': [],
        }
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/rerun-prompt',
            json={
                'text_content': 'Invoice content',
                'custom_prompt': 'x' * 10_000
            }
        )
        assert response.status_code == 200

    @patch('routes.sysadmin_test_tool.InvoiceTestService')
    def test_prompt_at_min_length_accepted(self, MockService, sysadmin_client):
        """Prompt at exactly 1 char passes validation."""
        mock_instance = MockService.return_value
        mock_instance.rerun_with_custom_prompt.return_value = {
            'success': True,
            'extraction_result': {'date': '', 'total_amount': 0.0, 'vat_amount': 0.0, 'description': '', 'vendor': ''},
            'performance': {'ai_duration_ms': 100, 'ai_model': 'test-model', 'ai_tokens': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}},
            'ai_usage_preview': None,
            'errors': [],
        }
        response = sysadmin_client.post(
            '/api/sysadmin/test-tool/rerun-prompt',
            json={
                'text_content': 'Invoice content',
                'custom_prompt': 'x'
            }
        )
        assert response.status_code == 200


# ============================================================================
# GET /vendor-history - Vendor Name Validation Tests
# ============================================================================


class TestVendorHistoryValidation:
    """Test vendor name validation on GET /vendor-history."""

    def test_missing_folder_name_returns_400(self, sysadmin_client):
        """Missing folderName returns 400."""
        response = sysadmin_client.get('/api/sysadmin/test-tool/vendor-history')
        assert response.status_code == 400
        data = response.get_json()
        assert 'folderName' in data['error']

    def test_invalid_folder_name_returns_400(self, sysadmin_client):
        """Invalid folderName returns 400."""
        response = sysadmin_client.get(
            '/api/sysadmin/test-tool/vendor-history?folderName=invalid name!'
        )
        assert response.status_code == 400
        data = response.get_json()
        assert 'vendor name' in data['error'].lower() or 'Invalid' in data['error']

    def test_folder_name_too_long_returns_400(self, sysadmin_client):
        """folderName exceeding 100 chars returns 400."""
        long_name = 'a' * 101
        response = sysadmin_client.get(
            f'/api/sysadmin/test-tool/vendor-history?folderName={long_name}'
        )
        assert response.status_code == 400

    @patch('routes.sysadmin_test_tool.InvoiceTestService')
    def test_valid_folder_name_accepted(self, MockService, sysadmin_client):
        """Valid folderName passes validation (returns 200 with vendor history)."""
        mock_instance = MockService.return_value
        mock_instance.get_vendor_history.return_value = [
            {'date': '2024-01-10', 'amount': 125.5, 'description': 'Invoice #12300'}
        ]
        response = sysadmin_client.get(
            '/api/sysadmin/test-tool/vendor-history?folderName=My-Vendor_123'
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['vendor_name'] == 'My-Vendor_123'
        assert 'transactions' in data
        assert 'count' in data

    @patch('routes.sysadmin_test_tool.InvoiceTestService')
    def test_folder_name_with_hyphens_and_underscores(self, MockService, sysadmin_client):
        """folderName with hyphens and underscores is accepted."""
        mock_instance = MockService.return_value
        mock_instance.get_vendor_history.return_value = []
        response = sysadmin_client.get(
            '/api/sysadmin/test-tool/vendor-history?folderName=some-vendor_name'
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['vendor_name'] == 'some-vendor_name'
