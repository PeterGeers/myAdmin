"""
Unit tests for OutputService

Tests the output_service module which handles output destination management
for generated reports (download, Google Drive, S3).
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from services.output_service import OutputService


class TestOutputService:
    """Test suite for OutputService"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database manager"""
        return Mock()
    
    @pytest.fixture
    def output_service(self, mock_db):
        """Create an OutputService instance with mock database"""
        return OutputService(mock_db)
    
    def test_initialization(self, mock_db):
        """Test OutputService initialization"""
        service = OutputService(mock_db)
        assert service.db == mock_db
    
    def test_handle_download_destination(self, output_service):
        """Test handling download destination"""
        content = "<html><body>Test Report</body></html>"
        filename = "test_report.html"
        
        result = output_service.handle_output(
            content=content,
            filename=filename,
            destination='download',
            administration='TestAdmin',
            content_type='text/html'
        )
        
        assert result['success'] is True
        assert result['destination'] == 'download'
        assert result['content'] == content
        assert result['filename'] == filename
        assert result['content_type'] == 'text/html'
        assert 'message' in result
    
    def test_handle_invalid_destination(self, output_service):
        """Test handling invalid destination raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            output_service.handle_output(
                content="test",
                filename="test.html",
                destination='invalid',
                administration='TestAdmin'
            )
        
        assert 'Invalid destination' in str(exc_info.value)
    
    @patch('services.storage_resolver.resolve_storage_provider', return_value='google_drive')
    @patch('google_drive_service.GoogleDriveService')
    def test_handle_gdrive_upload_new_file(self, mock_drive_class, mock_resolver, output_service):
        """Test handling Google Drive upload for new file"""
        # Setup mocks
        mock_drive = Mock()
        mock_drive_class.return_value = mock_drive
        
        mock_drive.check_file_exists.return_value = {'exists': False}
        mock_drive.upload_text_file.return_value = {
            'id': 'file123',
            'url': 'https://drive.google.com/file/d/file123'
        }
        
        # Mock _get_or_create_reports_folder
        with patch.object(output_service, '_get_or_create_reports_folder', return_value='folder123'):
            result = output_service.handle_output(
                content="<html>Test</html>",
                filename="test.html",
                destination='gdrive',
                administration='TestAdmin',
                content_type='text/html'
            )
        
        assert result['success'] is True
        assert result['destination'] == 'gdrive'
        assert result['url'] == 'https://drive.google.com/file/d/file123'
        assert result['file_id'] == 'file123'
        assert result['filename'] == 'test.html'
        assert 'message' in result
    
    @patch('services.storage_resolver.resolve_storage_provider', return_value='google_drive')
    @patch('google_drive_service.GoogleDriveService')
    def test_handle_gdrive_upload_existing_file(self, mock_drive_class, mock_resolver, output_service):
        """Test handling Google Drive upload when file already exists (adds timestamp)"""
        # Setup mocks
        mock_drive = Mock()
        mock_drive_class.return_value = mock_drive
        
        mock_drive.check_file_exists.return_value = {
            'exists': True,
            'file': {'id': 'existing123', 'url': 'https://drive.google.com/file/d/existing123'}
        }
        mock_drive.upload_text_file.return_value = {
            'id': 'file456',
            'url': 'https://drive.google.com/file/d/file456'
        }
        
        # Mock _get_or_create_reports_folder
        with patch.object(output_service, '_get_or_create_reports_folder', return_value='folder123'):
            result = output_service.handle_output(
                content="<html>Test</html>",
                filename="test.html",
                destination='gdrive',
                administration='TestAdmin',
                content_type='text/html'
            )
        
        assert result['success'] is True
        assert result['destination'] == 'gdrive'
        # Filename should have timestamp added
        assert result['filename'] != 'test.html'
        assert result['filename'].startswith('test_')
        assert result['filename'].endswith('.html')
    
    @patch('services.storage_resolver.resolve_storage_provider', return_value='google_drive')
    @patch('google_drive_service.GoogleDriveService')
    def test_handle_gdrive_upload_with_folder_id(self, mock_drive_class, mock_resolver, output_service):
        """Test handling Google Drive upload with explicit folder_id"""
        # Setup mocks
        mock_drive = Mock()
        mock_drive_class.return_value = mock_drive
        
        mock_drive.check_file_exists.return_value = {'exists': False}
        mock_drive.upload_text_file.return_value = {
            'id': 'file789',
            'url': 'https://drive.google.com/file/d/file789'
        }
        
        result = output_service.handle_output(
            content="<html>Test</html>",
            filename="test.html",
            destination='gdrive',
            administration='TestAdmin',
            content_type='text/html',
            folder_id='custom_folder_123'
        )
        
        assert result['success'] is True
        assert result['folder_id'] == 'custom_folder_123'
        # Should not call _get_or_create_reports_folder when folder_id is provided
        mock_drive.upload_text_file.assert_called_once()
    
    @patch('services.media_asset_service.MediaAssetService')
    def test_handle_s3_upload_success(self, mock_asset_cls, output_service):
        """Test handling S3 upload via MediaAssetService"""
        mock_asset_svc = Mock()
        mock_asset_cls.return_value = mock_asset_svc
        mock_asset_svc.store_and_register.return_value = {
            'success': True,
            'asset': {
                'id': 'ast_test123',
                's3_key': 'TestAdmin/invoices/ast_test123_test.pdf',
                'bucket': 'myadmin-shared-dev',
                'mime_type': 'application/pdf',
                'file_size': 9,
                'category': 'invoices',
                'media_type': 'document',
                'original_filename': 'test.pdf',
                'content_hash': 'abc123',
                'status': 'ACTIVE',
                'created_at': '2026-01-01 00:00:00',
                'reference_count': 1,
            },
            'duplicate_of': None,
        }

        result = output_service.handle_output(
            content=b'%PDF-fake',
            filename="test.pdf",
            destination='s3',
            administration='TestAdmin',
            content_type='application/pdf'
        )

        assert result['success'] is True
        assert result['destination'] == 's3'
        assert result['url'] == 'TestAdmin/invoices/ast_test123_test.pdf'
        assert result['reference'] == 'TestAdmin/invoices/ast_test123_test.pdf'
        assert result['filename'] == 'test.pdf'

        # Verify store_and_register was called with correct params
        mock_asset_svc.store_and_register.assert_called_once()
        call_kwargs = mock_asset_svc.store_and_register.call_args[1]
        assert call_kwargs['tenant'] == 'TestAdmin'
        assert call_kwargs['file_data'] == b'%PDF-fake'
        assert call_kwargs['filename'] == 'test.pdf'
        assert call_kwargs['category'] == 'invoices'
        assert call_kwargs['entity_type'] == 'report'
        assert ':' in call_kwargs['entity_id']  # report_type:timestamp format
        assert call_kwargs['entity_id'].startswith('test:')

    @patch('services.media_asset_service.MediaAssetService')
    def test_handle_s3_upload_string_content(self, mock_asset_cls, output_service):
        """Test S3 upload with string content is converted to bytes"""
        mock_asset_svc = Mock()
        mock_asset_cls.return_value = mock_asset_svc
        mock_asset_svc.store_and_register.return_value = {
            'success': True,
            'asset': {
                'id': 'ast_test456',
                's3_key': 'TestAdmin/invoices/ast_test456_report.html',
                'bucket': 'myadmin-shared-dev',
                'mime_type': 'text/html',
                'file_size': 26,
                'category': 'invoices',
                'media_type': 'web_content',
                'original_filename': 'report.html',
                'content_hash': 'def456',
                'status': 'ACTIVE',
                'created_at': '2026-01-01 00:00:00',
                'reference_count': 1,
            },
            'duplicate_of': None,
        }

        result = output_service.handle_output(
            content="<html><body>Report</body></html>",
            filename="report.html",
            destination='s3',
            administration='TestAdmin',
            content_type='text/html'
        )

        assert result['success'] is True
        # Verify bytes were passed to store_and_register
        call_kwargs = mock_asset_svc.store_and_register.call_args[1]
        assert call_kwargs['file_data'] == b"<html><body>Report</body></html>"

    @patch('services.media_asset_service.MediaAssetService')
    def test_handle_s3_upload_failure(self, mock_asset_cls, output_service):
        """Test S3 upload failure propagates as exception"""
        mock_asset_svc = Mock()
        mock_asset_cls.return_value = mock_asset_svc
        mock_asset_svc.store_and_register.return_value = {
            'success': False,
            'error': 'S3 upload failed',
        }

        with pytest.raises(Exception) as exc_info:
            output_service.handle_output(
                content=b'%PDF-fake',
                filename="test.pdf",
                destination='s3',
                administration='TestAdmin',
                content_type='application/pdf'
            )

        assert 'S3 upload failed' in str(exc_info.value)

    @patch('services.media_asset_service.MediaAssetService')
    def test_handle_s3_upload_entity_id_format(self, mock_asset_cls, output_service):
        """Test that entity_id uses report_type:timestamp format"""
        mock_asset_svc = Mock()
        mock_asset_cls.return_value = mock_asset_svc
        mock_asset_svc.store_and_register.return_value = {
            'success': True,
            'asset': {
                'id': 'ast_test789',
                's3_key': 'TestAdmin/invoices/ast_test789_quarterly_report.xlsx',
                'bucket': 'myadmin-shared-dev',
                'mime_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'file_size': 100,
                'category': 'invoices',
                'media_type': 'document',
                'original_filename': 'quarterly_report.xlsx',
                'content_hash': 'ghi789',
                'status': 'ACTIVE',
                'created_at': '2026-01-01 00:00:00',
                'reference_count': 1,
            },
            'duplicate_of': None,
        }

        output_service.handle_output(
            content=b'fake-xlsx-content',
            filename="quarterly_report.xlsx",
            destination='s3',
            administration='TestAdmin',
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        call_kwargs = mock_asset_svc.store_and_register.call_args[1]
        entity_id = call_kwargs['entity_id']
        # entity_id should be "quarterly_report:YYYYMMDD_HHMMSS"
        parts = entity_id.split(':')
        assert parts[0] == 'quarterly_report'
        assert len(parts[1]) == 15  # YYYYMMDD_HHMMSS
    
    @patch('google_drive_service.GoogleDriveService')
    @patch('services.output_service.os.getenv')
    def test_get_or_create_reports_folder_existing(self, mock_getenv, mock_drive_class, output_service):
        """Test getting existing Reports folder"""
        # Setup mocks
        mock_drive = Mock()
        mock_getenv.side_effect = lambda key, default=None: {
            'TEST_MODE': 'false',
            'FACTUREN_FOLDER_ID': 'parent123'
        }.get(key, default)
        
        mock_drive.check_file_exists.return_value = {
            'exists': True,
            'file': {'id': 'reports_folder_123'}
        }
        
        folder_id = output_service._get_or_create_reports_folder(mock_drive, 'TestAdmin')
        
        assert folder_id == 'reports_folder_123'
        mock_drive.check_file_exists.assert_called_once_with('Reports_TestAdmin', 'parent123')
        mock_drive.create_folder.assert_not_called()
    
    @patch('google_drive_service.GoogleDriveService')
    @patch('services.output_service.os.getenv')
    def test_get_or_create_reports_folder_new(self, mock_getenv, mock_drive_class, output_service):
        """Test creating new Reports folder"""
        # Setup mocks
        mock_drive = Mock()
        mock_getenv.side_effect = lambda key, default=None: {
            'TEST_MODE': 'false',
            'FACTUREN_FOLDER_ID': 'parent123'
        }.get(key, default)
        
        mock_drive.check_file_exists.return_value = {'exists': False}
        mock_drive.create_folder.return_value = {
            'id': 'new_reports_folder_456',
            'name': 'Reports_TestAdmin'
        }
        
        folder_id = output_service._get_or_create_reports_folder(mock_drive, 'TestAdmin')
        
        assert folder_id == 'new_reports_folder_456'
        mock_drive.check_file_exists.assert_called_once_with('Reports_TestAdmin', 'parent123')
        mock_drive.create_folder.assert_called_once_with('Reports_TestAdmin', 'parent123')
    
    @patch('services.output_service.os.getenv')
    def test_get_or_create_reports_folder_no_parent(self, mock_getenv, output_service):
        """Test error when parent folder ID not configured"""
        mock_drive = Mock()
        mock_getenv.return_value = None
        
        with pytest.raises(Exception) as exc_info:
            output_service._get_or_create_reports_folder(mock_drive, 'TestAdmin')
        
        assert 'not configured' in str(exc_info.value).lower()
    
    def test_handle_download_with_different_content_types(self, output_service):
        """Test download with various content types"""
        content_types = [
            ('text/html', 'report.html'),
            ('text/xml', 'report.xml'),
            ('application/json', 'report.json'),
            ('text/plain', 'report.txt')
        ]
        
        for content_type, filename in content_types:
            result = output_service.handle_output(
                content="test content",
                filename=filename,
                destination='download',
                administration='TestAdmin',
                content_type=content_type
            )
            
            assert result['success'] is True
            assert result['content_type'] == content_type
            assert result['filename'] == filename


    # --- check_health tests ---

    def test_check_health_download_always_healthy(self, output_service):
        """Download destination requires no external service — always healthy."""
        result = output_service.check_health('download', 'TestAdmin')
        assert result['healthy'] is True
        assert 'always available' in result['reason'].lower()

    def test_check_health_unknown_destination(self, output_service):
        """Unknown destination should return unhealthy with descriptive reason."""
        result = output_service.check_health('ftp', 'TestAdmin')
        assert result['healthy'] is False
        assert 'Unknown destination' in result['reason']

    @patch('google_drive_service.GoogleDriveService')
    def test_check_health_gdrive_success(self, mock_drive_class, output_service):
        """Google Drive health check succeeds when API responds."""
        mock_drive = Mock()
        mock_drive_class.return_value = mock_drive
        mock_files = Mock()
        mock_drive.service.files.return_value = mock_files
        mock_files.list.return_value = mock_files
        mock_files.execute.return_value = {'files': []}

        result = output_service.check_health('gdrive', 'TestAdmin')

        assert result['healthy'] is True
        assert 'accessible' in result['reason'].lower()
        mock_files.list.assert_called_once_with(pageSize=1, fields='files(id)')

    @patch('google_drive_service.GoogleDriveService')
    def test_check_health_gdrive_failure(self, mock_drive_class, output_service):
        """Google Drive health check fails when API raises an exception."""
        mock_drive_class.side_effect = Exception('Auth failed')

        result = output_service.check_health('gdrive', 'TestAdmin')

        assert result['healthy'] is False
        assert 'unavailable' in result['reason'].lower()

    @patch('storage.storage_provider.get_storage_provider')
    @patch('services.parameter_service.ParameterService')
    def test_check_health_s3_success(self, mock_param_cls, mock_get_provider, output_service):
        """S3 health check succeeds when HeadBucket responds."""
        mock_provider = Mock()
        mock_provider.bucket = 'test-bucket'
        mock_provider._client = Mock()
        mock_get_provider.return_value = mock_provider

        result = output_service.check_health('s3', 'TestAdmin')

        assert result['healthy'] is True
        assert 'test-bucket' in result['reason']
        mock_provider._client.head_bucket.assert_called_once_with(Bucket='test-bucket')

    @patch('storage.storage_provider.get_storage_provider')
    @patch('services.parameter_service.ParameterService')
    def test_check_health_s3_failure(self, mock_param_cls, mock_get_provider, output_service):
        """S3 health check fails when HeadBucket raises an exception."""
        mock_provider = Mock()
        mock_provider.bucket = 'test-bucket'
        mock_provider._client = Mock()
        mock_provider._client.head_bucket.side_effect = Exception('Access Denied')
        mock_get_provider.return_value = mock_provider

        result = output_service.check_health('s3', 'TestAdmin')

        assert result['healthy'] is False
        assert 'unavailable' in result['reason'].lower()

    @patch('storage.storage_provider.get_storage_provider')
    @patch('services.parameter_service.ParameterService')
    def test_check_health_s3_no_bucket(self, mock_param_cls, mock_get_provider, output_service):
        """S3 health check fails when bucket is not configured."""
        mock_provider = Mock(spec=[])  # no bucket attribute
        mock_get_provider.return_value = mock_provider

        result = output_service.check_health('s3', 'TestAdmin')

        assert result['healthy'] is False
        assert 'not configured' in result['reason'].lower()

    def test_check_health_case_insensitive(self, output_service):
        """Destination parameter should be case-insensitive."""
        result = output_service.check_health('DOWNLOAD', 'TestAdmin')
        assert result['healthy'] is True

        result = output_service.check_health('Download', 'TestAdmin')
        assert result['healthy'] is True
