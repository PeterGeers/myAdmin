"""
Unit tests for missing_invoices_routes.py upload_receipt S3 path migration.

Verifies that the upload_receipt endpoint uses MediaAssetService.store_and_register
instead of direct S3SharedStorage.upload for S3 tenants.

Reference: .kiro/specs/Common/image-asset-management/tasks.md — Task 6.3
"""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def finance_auth():
    """Mock authentication with Finance_CRUD role for invoice endpoints."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Finance_CRUD']):
        mock_creds.return_value = ('test@example.com', ['Finance_CRUD'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


@pytest.fixture
def client():
    """Flask test client with missing_invoices blueprint."""
    from flask import Flask
    from routes.missing_invoices_routes import missing_invoices_bp

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(missing_invoices_bp)

    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def bypass_function_guard():
    """Mock function_guard's internal DB calls to allow function access."""
    mock_service = MagicMock()
    mock_service.get_function_state.return_value = True

    with patch('services.module_registry.has_module', return_value=True), \
         patch('services.tenant_function_service.TenantFunctionService', return_value=mock_service):
        yield


class TestUploadReceiptS3Migration:
    """Tests for upload_receipt S3 path using MediaAssetService."""

    @patch('routes.missing_invoices_routes.resolve_storage_provider', return_value='s3_shared')
    @patch('routes.missing_invoices_routes.list_s3_folders', return_value=['ExistingSupplier'])
    @patch('routes.missing_invoices_routes.create_s3_folder')
    @patch('routes.missing_invoices_routes.MediaAssetService')
    @patch('routes.missing_invoices_routes.db')
    def test_s3_upload_calls_store_and_register(
        self, mock_db, mock_asset_cls, mock_create_folder,
        mock_list_folders, mock_resolve, client, finance_auth
    ):
        """Upload receipt for S3 tenant uses MediaAssetService.store_and_register."""
        mock_svc = MagicMock()
        mock_asset_cls.return_value = mock_svc
        mock_svc.store_and_register.return_value = {
            'success': True,
            'asset': {
                'id': 'ast_01TEST123',
                's3_key': 'test-tenant/invoices/ast_01TEST123_receipt.pdf',
                'mime_type': 'application/pdf',
                'file_size': 1024,
                'category': 'invoices',
                'media_type': 'document',
                'status': 'ACTIVE',
            },
            'duplicate_of': None,
        }

        data = {
            'file': (BytesIO(b'%PDF-1.4 fake pdf content'), 'receipt.pdf'),
            'supplierName': 'NewSupplier',
        }

        response = client.post(
            '/api/upload-receipt',
            headers=finance_auth,
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['driveUrl'] == 'test-tenant/invoices/ast_01TEST123_receipt.pdf'

        # Verify store_and_register was called with correct params
        mock_svc.store_and_register.assert_called_once()
        call_kwargs = mock_svc.store_and_register.call_args[1]
        assert call_kwargs['tenant'] == 'test-tenant'
        assert call_kwargs['filename'] == 'receipt.pdf'
        assert call_kwargs['category'] == 'invoices'
        assert call_kwargs['metadata'] == {'reference_number': 'NewSupplier'}
        # No entity_type/entity_id — linked separately via update_transaction_refs
        assert 'entity_type' not in call_kwargs or call_kwargs.get('entity_type') is None
        assert 'entity_id' not in call_kwargs or call_kwargs.get('entity_id') is None

    @patch('routes.missing_invoices_routes.resolve_storage_provider', return_value='s3_shared')
    @patch('routes.missing_invoices_routes.list_s3_folders', return_value=['ExistingSupplier'])
    @patch('routes.missing_invoices_routes.create_s3_folder')
    @patch('routes.missing_invoices_routes.MediaAssetService')
    @patch('routes.missing_invoices_routes.db')
    def test_s3_upload_creates_folder_for_new_supplier(
        self, mock_db, mock_asset_cls, mock_create_folder,
        mock_list_folders, mock_resolve, client, finance_auth
    ):
        """When supplier folder doesn't exist, creates it before upload."""
        mock_svc = MagicMock()
        mock_asset_cls.return_value = mock_svc
        mock_svc.store_and_register.return_value = {
            'success': True,
            'asset': {'id': 'ast_X', 's3_key': 'test-tenant/invoices/ast_X_inv.pdf'},
            'duplicate_of': None,
        }

        data = {
            'file': (BytesIO(b'%PDF-1.4 content'), 'invoice.pdf'),
            'supplierName': 'BrandNewSupplier',
        }

        response = client.post(
            '/api/upload-receipt',
            headers=finance_auth,
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 200
        # Folder should be created since supplier is not in existing folders
        mock_create_folder.assert_called_once_with('test-tenant', 'BrandNewSupplier')

    @patch('routes.missing_invoices_routes.resolve_storage_provider', return_value='s3_shared')
    @patch('routes.missing_invoices_routes.list_s3_folders', return_value=['ExistingSupplier'])
    @patch('routes.missing_invoices_routes.create_s3_folder')
    @patch('routes.missing_invoices_routes.MediaAssetService')
    @patch('routes.missing_invoices_routes.db')
    def test_s3_upload_skips_folder_creation_for_existing_supplier(
        self, mock_db, mock_asset_cls, mock_create_folder,
        mock_list_folders, mock_resolve, client, finance_auth
    ):
        """When supplier folder exists, does not create it."""
        mock_svc = MagicMock()
        mock_asset_cls.return_value = mock_svc
        mock_svc.store_and_register.return_value = {
            'success': True,
            'asset': {'id': 'ast_Y', 's3_key': 'test-tenant/invoices/ast_Y_inv.pdf'},
            'duplicate_of': None,
        }

        data = {
            'file': (BytesIO(b'%PDF-1.4 content'), 'invoice.pdf'),
            'supplierName': 'ExistingSupplier',
        }

        response = client.post(
            '/api/upload-receipt',
            headers=finance_auth,
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 200
        mock_create_folder.assert_not_called()

    @patch('routes.missing_invoices_routes.resolve_storage_provider', return_value='s3_shared')
    @patch('routes.missing_invoices_routes.list_s3_folders', return_value=[])
    @patch('routes.missing_invoices_routes.create_s3_folder')
    @patch('routes.missing_invoices_routes.MediaAssetService')
    @patch('routes.missing_invoices_routes.db')
    def test_s3_upload_returns_500_on_failure(
        self, mock_db, mock_asset_cls, mock_create_folder,
        mock_list_folders, mock_resolve, client, finance_auth
    ):
        """When store_and_register fails, returns 500 with error."""
        mock_svc = MagicMock()
        mock_asset_cls.return_value = mock_svc
        mock_svc.store_and_register.return_value = {
            'success': False,
            'error': 'S3 upload failed',
        }

        data = {
            'file': (BytesIO(b'%PDF-1.4 content'), 'invoice.pdf'),
            'supplierName': 'TestSupplier',
        }

        response = client.post(
            '/api/upload-receipt',
            headers=finance_auth,
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 500
        result = json.loads(response.data)
        assert result['error'] == 'S3 upload failed'

    @patch('routes.missing_invoices_routes.resolve_storage_provider', return_value='s3_shared')
    @patch('routes.missing_invoices_routes.list_s3_folders', return_value=[])
    @patch('routes.missing_invoices_routes.create_s3_folder')
    @patch('routes.missing_invoices_routes.MediaAssetService')
    @patch('routes.missing_invoices_routes.db')
    def test_s3_upload_passes_file_data_correctly(
        self, mock_db, mock_asset_cls, mock_create_folder,
        mock_list_folders, mock_resolve, client, finance_auth
    ):
        """File data read from request is passed to store_and_register."""
        mock_svc = MagicMock()
        mock_asset_cls.return_value = mock_svc
        mock_svc.store_and_register.return_value = {
            'success': True,
            'asset': {'id': 'ast_Z', 's3_key': 'test-tenant/invoices/ast_Z_doc.pdf'},
            'duplicate_of': None,
        }

        file_content = b'%PDF-1.4 specific test content here'
        data = {
            'file': (BytesIO(file_content), 'document.pdf'),
            'supplierName': 'Supplier',
        }

        response = client.post(
            '/api/upload-receipt',
            headers=finance_auth,
            data=data,
            content_type='multipart/form-data',
        )

        assert response.status_code == 200
        call_kwargs = mock_svc.store_and_register.call_args[1]
        assert call_kwargs['file_data'] == file_content

    @patch('routes.missing_invoices_routes.resolve_storage_provider', return_value='s3_shared')
    @patch('routes.missing_invoices_routes.list_s3_folders', return_value=[])
    @patch('routes.missing_invoices_routes.create_s3_folder')
    @patch('routes.missing_invoices_routes.MediaAssetService')
    @patch('routes.missing_invoices_routes.db')
    def test_s3_upload_instantiates_asset_service_with_db(
        self, mock_db, mock_asset_cls, mock_create_folder,
        mock_list_folders, mock_resolve, client, finance_auth
    ):
        """MediaAssetService is instantiated with the module-level db."""
        mock_svc = MagicMock()
        mock_asset_cls.return_value = mock_svc
        mock_svc.store_and_register.return_value = {
            'success': True,
            'asset': {'id': 'ast_W', 's3_key': 'test-tenant/invoices/ast_W_f.pdf'},
            'duplicate_of': None,
        }

        data = {
            'file': (BytesIO(b'%PDF-1.4 content'), 'file.pdf'),
            'supplierName': 'Sup',
        }

        client.post(
            '/api/upload-receipt',
            headers=finance_auth,
            data=data,
            content_type='multipart/form-data',
        )

        mock_asset_cls.assert_called_once_with(mock_db)
