"""
Unit tests for InvoiceService.upload_to_drive() — S3 path migration.

Validates that the S3 upload path uses MediaAssetService.store_and_register()
instead of the legacy StorageProvider.upload() call, and that:
- The asset is registered without entity_type/entity_id (since mutatie_id
  doesn't exist at upload time)
- The returned s3_key from the asset registry is used
- Fallback to local storage works when store_and_register fails
- Test mode bypasses S3 entirely
"""

import os
import sys
import tempfile

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


@pytest.fixture
def invoice_service():
    """Create InvoiceService instance with mocked dependencies."""
    with patch('services.invoice_service.DatabaseManager') as mock_db_cls, \
         patch('services.invoice_service.PDFProcessor'), \
         patch('services.invoice_service.TransactionLogic'):
        from services.invoice_service import InvoiceService
        service = InvoiceService(test_mode=False)
        # Replace the db with a mock for use in tests
        service.db = MagicMock()
        return service


@pytest.fixture
def temp_pdf_file():
    """Create a temporary PDF file for testing."""
    # Minimal PDF-like content (starts with %PDF magic bytes)
    pdf_content = b'%PDF-1.4 fake pdf content for testing'
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        f.write(pdf_content)
        f.flush()
        yield f.name, pdf_content
    # Cleanup
    if os.path.exists(f.name):
        os.unlink(f.name)


class TestUploadToDriveS3Path:
    """Tests for the S3 upload path using MediaAssetService."""

    @patch('services.media_asset_service.MediaAssetService')
    @patch('services.storage_resolver.resolve_storage_provider', return_value='s3_shared')
    def test_calls_store_and_register_with_correct_params(
        self, mock_resolve, mock_asset_svc_cls, invoice_service, temp_pdf_file
    ):
        """S3 path calls store_and_register with tenant, file_data, filename, category, metadata."""
        temp_path, pdf_content = temp_pdf_file
        mock_asset_svc = MagicMock()
        mock_asset_svc_cls.return_value = mock_asset_svc
        mock_asset_svc.store_and_register.return_value = {
            'success': True,
            'asset': {
                'id': 'ast_01ABCDEF',
                's3_key': 'test_tenant/invoices/ast_01ABCDEF_invoice.pdf',
                'bucket': 'myadmin-shared',
            },
            'duplicate_of': None,
        }

        result = invoice_service.upload_to_drive(
            temp_path, 'invoice.pdf', 'VendorX', 'test_tenant'
        )

        # Verify store_and_register was called correctly
        mock_asset_svc.store_and_register.assert_called_once_with(
            tenant='test_tenant',
            file_data=pdf_content,
            filename='invoice.pdf',
            category='invoices',
            metadata={'reference_number': 'VendorX'},
        )

    @patch('services.media_asset_service.MediaAssetService')
    @patch('services.storage_resolver.resolve_storage_provider', return_value='s3_shared')
    def test_returns_s3_key_from_asset_result(
        self, mock_resolve, mock_asset_svc_cls, invoice_service, temp_pdf_file
    ):
        """Returns the s3_key from asset registration as both id and url."""
        temp_path, _ = temp_pdf_file
        expected_key = 'test_tenant/invoices/ast_01ABCDEF_invoice.pdf'
        mock_asset_svc = MagicMock()
        mock_asset_svc_cls.return_value = mock_asset_svc
        mock_asset_svc.store_and_register.return_value = {
            'success': True,
            'asset': {'id': 'ast_01ABCDEF', 's3_key': expected_key, 'bucket': 'myadmin-shared'},
            'duplicate_of': None,
        }

        result = invoice_service.upload_to_drive(
            temp_path, 'invoice.pdf', 'VendorX', 'test_tenant'
        )

        assert result == {"id": expected_key, "url": expected_key}

    @patch('services.media_asset_service.MediaAssetService')
    @patch('services.storage_resolver.resolve_storage_provider', return_value='s3_shared')
    def test_does_not_pass_entity_type_or_entity_id(
        self, mock_resolve, mock_asset_svc_cls, invoice_service, temp_pdf_file
    ):
        """No entity_type/entity_id since mutatie_id doesn't exist at upload time."""
        temp_path, _ = temp_pdf_file
        mock_asset_svc = MagicMock()
        mock_asset_svc_cls.return_value = mock_asset_svc
        mock_asset_svc.store_and_register.return_value = {
            'success': True,
            'asset': {'id': 'ast_X', 's3_key': 'key', 'bucket': 'b'},
            'duplicate_of': None,
        }

        invoice_service.upload_to_drive(
            temp_path, 'invoice.pdf', 'Folder', 'tenant1'
        )

        call_kwargs = mock_asset_svc.store_and_register.call_args
        # entity_type and entity_id should NOT be in the call
        assert 'entity_type' not in call_kwargs.kwargs
        assert 'entity_id' not in call_kwargs.kwargs

    @patch('services.media_asset_service.MediaAssetService')
    @patch('services.storage_resolver.resolve_storage_provider', return_value='s3_shared')
    def test_fallback_to_local_on_store_and_register_failure(
        self, mock_resolve, mock_asset_svc_cls, invoice_service, temp_pdf_file
    ):
        """Falls back to local storage if store_and_register returns failure."""
        temp_path, _ = temp_pdf_file
        mock_asset_svc = MagicMock()
        mock_asset_svc_cls.return_value = mock_asset_svc
        mock_asset_svc.store_and_register.return_value = {
            'success': False,
            'error': 'S3 upload failed',
        }

        result = invoice_service.upload_to_drive(
            temp_path, 'invoice.pdf', 'VendorX', 'test_tenant'
        )

        assert result == {
            "id": "invoice.pdf",
            "url": "http://localhost:5000/uploads/invoice.pdf",
        }

    @patch('services.media_asset_service.MediaAssetService')
    @patch('services.storage_resolver.resolve_storage_provider', return_value='s3_shared')
    def test_fallback_to_local_on_exception(
        self, mock_resolve, mock_asset_svc_cls, invoice_service, temp_pdf_file
    ):
        """Falls back to local storage if MediaAssetService raises an exception."""
        temp_path, _ = temp_pdf_file
        mock_asset_svc = MagicMock()
        mock_asset_svc_cls.return_value = mock_asset_svc
        mock_asset_svc.store_and_register.side_effect = Exception("Network error")

        result = invoice_service.upload_to_drive(
            temp_path, 'invoice.pdf', 'VendorX', 'test_tenant'
        )

        assert result == {
            "id": "invoice.pdf",
            "url": "http://localhost:5000/uploads/invoice.pdf",
        }

    @patch('services.media_asset_service.MediaAssetService')
    @patch('services.storage_resolver.resolve_storage_provider', return_value='s3_shared')
    def test_asset_service_initialized_with_service_db(
        self, mock_resolve, mock_asset_svc_cls, invoice_service, temp_pdf_file
    ):
        """MediaAssetService is initialized with the InvoiceService's db instance."""
        temp_path, _ = temp_pdf_file
        mock_asset_svc = MagicMock()
        mock_asset_svc_cls.return_value = mock_asset_svc
        mock_asset_svc.store_and_register.return_value = {
            'success': True,
            'asset': {'id': 'ast_X', 's3_key': 'key', 'bucket': 'b'},
            'duplicate_of': None,
        }

        invoice_service.upload_to_drive(
            temp_path, 'invoice.pdf', 'Folder', 'tenant1'
        )

        mock_asset_svc_cls.assert_called_once_with(invoice_service.db)


class TestUploadToDriveTestMode:
    """Tests for test mode bypass."""

    def test_test_mode_returns_local_url(self):
        """Test mode skips all storage providers and returns local URL."""
        with patch('services.invoice_service.DatabaseManager'), \
             patch('services.invoice_service.PDFProcessor'), \
             patch('services.invoice_service.TransactionLogic'):
            from services.invoice_service import InvoiceService
            service = InvoiceService(test_mode=True)

        result = service.upload_to_drive(
            '/tmp/test.pdf', 'test.pdf', 'Vendor', 'tenant1'
        )

        assert result == {
            "id": "test.pdf",
            "url": "http://localhost:5000/uploads/test.pdf",
        }


class TestUploadToDriveGoogleDriveUnchanged:
    """Verify Google Drive path is not affected by migration."""

    @patch('services.invoice_service.GoogleDriveService')
    @patch('services.storage_resolver.resolve_storage_provider', return_value='google_drive')
    def test_google_drive_path_still_works(
        self, mock_resolve, mock_gdrive_cls, invoice_service, temp_pdf_file
    ):
        """Google Drive path is unchanged — not affected by S3 migration."""
        temp_path, _ = temp_pdf_file
        mock_gdrive = MagicMock()
        mock_gdrive_cls.return_value = mock_gdrive
        mock_gdrive.list_subfolders.return_value = [
            {'name': 'VendorX', 'id': 'folder123'}
        ]
        mock_gdrive.check_file_exists.return_value = {'exists': False}
        mock_gdrive.upload_file.return_value = {
            'id': 'gdrive_file_id',
            'url': 'https://drive.google.com/file/d/gdrive_file_id',
        }

        result = invoice_service.upload_to_drive(
            temp_path, 'invoice.pdf', 'VendorX', 'gdrive_tenant'
        )

        assert result['id'] == 'gdrive_file_id'
        assert 'drive.google.com' in result['url']
