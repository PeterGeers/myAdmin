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
    
    @patch('google_drive_service.GoogleDriveService')
    def test_handle_gdrive_upload_new_file(self, mock_drive_class, output_service):
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
    
    @patch('google_drive_service.GoogleDriveService')
    def test_handle_gdrive_upload_existing_file(self, mock_drive_class, output_service):
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
    
    @patch('google_drive_service.GoogleDriveService')
    def test_handle_gdrive_upload_with_folder_id(self, mock_drive_class, output_service):
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
    
    def test_handle_s3_upload_not_implemented(self, output_service):
        """Test handling S3 upload raises NotImplementedError"""
        with pytest.raises(NotImplementedError) as exc_info:
            output_service.handle_output(
                content="test",
                filename="test.html",
                destination='s3',
                administration='TestAdmin'
            )
        
        assert 'not yet implemented' in str(exc_info.value).lower()
    
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
