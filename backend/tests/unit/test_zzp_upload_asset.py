"""
Unit tests for zzp_routes.py upload_supporting_document S3 path migration.

Verifies that the upload_supporting_document endpoint uses
MediaAssetService.store_and_register instead of StorageProvider.upload.

Reference: .kiro/specs/Common/image-asset-management/tasks.md — Task 6.4
"""

import importlib
import json
from functools import wraps
from io import BytesIO
from unittest.mock import MagicMock, Mock, patch

import pytest
from flask import Flask


# ── Auth decorator mocks ───────────────────────────────────


def _passthrough_cognito(required_permissions=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['zzp_crud']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = 'test-tenant'
            kwargs['user_tenants'] = ['test-tenant']
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
    """Mock the ZZP invoice service."""
    svc = Mock()
    svc.get_invoice.return_value = {
        'id': 42,
        'invoice_number': 'ZZP-2025-001',
        'status': 'draft',
    }
    return svc


@pytest.fixture
def mock_asset_service():
    """Mock MediaAssetService instance."""
    svc = Mock()
    svc.store_and_register.return_value = {
        'success': True,
        'asset': {
            'id': 'ast_01TEST123',
            's3_key': 'test-tenant/invoices/ast_01TEST123_doc.pdf',
            'mime_type': 'application/pdf',
            'file_size': 2048,
            'category': 'invoices',
            'media_type': 'document',
            'status': 'ACTIVE',
        },
        'duplicate_of': None,
    }
    return svc


@pytest.fixture
def zzp_client(mock_invoice_service, mock_asset_service):
    """Flask test client with mocked auth, invoice service, and asset service."""
    mock_asset_cls = Mock(return_value=mock_asset_service)

    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module), \
         patch('database.DatabaseManager', return_value=Mock()), \
         patch('services.media_asset_service.MediaAssetService', mock_asset_cls):
        import routes.zzp_routes as zr
        importlib.reload(zr)
        zr._get_invoice_service = lambda: mock_invoice_service

        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(zr.zzp_bp)
        yield app.test_client()


# ── Tests ───────────────────────────────────────────────────


class TestZZPUploadSupportingDocumentMigration:
    """Tests for upload_supporting_document using MediaAssetService."""

    def test_upload_calls_store_and_register(
        self, zzp_client, mock_asset_service, mock_invoice_service
    ):
        """Upload supporting document uses MediaAssetService.store_and_register."""
        data = {
            'file': (BytesIO(b'%PDF-1.4 fake pdf content'), 'supporting_doc.pdf'),
        }

        response = zzp_client.post(
            '/api/zzp/invoices/42/documents',
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 201
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['data']['filename'] == 'supporting_doc.pdf'
        assert result['data']['url'] == 'test-tenant/invoices/ast_01TEST123_doc.pdf'
        assert result['data']['invoice_id'] == 42

        # Verify store_and_register was called with correct params
        mock_asset_service.store_and_register.assert_called_once()
        call_kwargs = mock_asset_service.store_and_register.call_args[1]
        assert call_kwargs['tenant'] == 'test-tenant'
        assert call_kwargs['filename'] == 'supporting_doc.pdf'
        assert call_kwargs['category'] == 'invoices'
        assert call_kwargs['entity_type'] == 'zzp_invoice'
        assert call_kwargs['entity_id'] == '42'
        assert call_kwargs['metadata'] == {'reference_number': 'ZZP-2025-001'}

    def test_upload_passes_entity_type_and_id(
        self, zzp_client, mock_asset_service
    ):
        """entity_type='zzp_invoice' and entity_id=str(invoice_id) are passed."""
        data = {
            'file': (BytesIO(b'%PDF-1.4 content'), 'invoice_attach.pdf'),
        }

        response = zzp_client.post(
            '/api/zzp/invoices/42/documents',
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 201
        call_kwargs = mock_asset_service.store_and_register.call_args[1]
        assert call_kwargs['entity_type'] == 'zzp_invoice'
        assert call_kwargs['entity_id'] == '42'

    def test_upload_returns_500_on_failure(
        self, zzp_client, mock_asset_service
    ):
        """When store_and_register fails, returns 500 with error."""
        mock_asset_service.store_and_register.return_value = {
            'success': False,
            'error': 'File type not allowed',
        }

        data = {
            'file': (BytesIO(b'not a pdf'), 'bad_file.exe'),
        }

        response = zzp_client.post(
            '/api/zzp/invoices/42/documents',
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 500
        result = json.loads(response.data)
        assert result['success'] is False
        assert result['error'] == 'File type not allowed'

    def test_upload_returns_404_when_invoice_not_found(
        self, zzp_client, mock_invoice_service, mock_asset_service
    ):
        """Returns 404 if invoice doesn't exist."""
        mock_invoice_service.get_invoice.return_value = None

        data = {
            'file': (BytesIO(b'%PDF-1.4 content'), 'doc.pdf'),
        }

        response = zzp_client.post(
            '/api/zzp/invoices/999/documents',
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 404
        result = json.loads(response.data)
        assert result['success'] is False
        assert result['error'] == 'Invoice not found'
        # MediaAssetService should not have been called
        mock_asset_service.store_and_register.assert_not_called()

    def test_upload_returns_400_when_no_file(
        self, zzp_client, mock_invoice_service
    ):
        """Returns 400 if no file field in request."""
        response = zzp_client.post(
            '/api/zzp/invoices/42/documents',
            data={},
            content_type='multipart/form-data',
        )

        assert response.status_code == 400
        result = json.loads(response.data)
        assert result['success'] is False
        assert result['error'] == 'No file provided'

    def test_upload_returns_400_for_empty_filename(
        self, zzp_client, mock_invoice_service
    ):
        """Returns 400 if file has empty filename."""
        data = {
            'file': (BytesIO(b'content'), ''),
        }

        response = zzp_client.post(
            '/api/zzp/invoices/42/documents',
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 400
        result = json.loads(response.data)
        assert result['success'] is False
        assert result['error'] == 'Empty filename'

    def test_upload_passes_file_data_correctly(
        self, zzp_client, mock_asset_service
    ):
        """File data read from request is passed to store_and_register."""
        file_content = b'%PDF-1.4 specific test content for zzp'
        data = {
            'file': (BytesIO(file_content), 'receipt.pdf'),
        }

        response = zzp_client.post(
            '/api/zzp/invoices/42/documents',
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 201
        call_kwargs = mock_asset_service.store_and_register.call_args[1]
        assert call_kwargs['file_data'] == file_content

    def test_upload_uses_invoice_number_in_metadata(
        self, zzp_client, mock_invoice_service, mock_asset_service
    ):
        """metadata['reference_number'] is the invoice number from the DB."""
        mock_invoice_service.get_invoice.return_value = {
            'id': 7,
            'invoice_number': 'ZZP-2025-099',
            'status': 'sent',
        }

        data = {
            'file': (BytesIO(b'%PDF-1.4 content'), 'attachment.pdf'),
        }

        response = zzp_client.post(
            '/api/zzp/invoices/7/documents',
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 201
        call_kwargs = mock_asset_service.store_and_register.call_args[1]
        assert call_kwargs['metadata'] == {'reference_number': 'ZZP-2025-099'}
