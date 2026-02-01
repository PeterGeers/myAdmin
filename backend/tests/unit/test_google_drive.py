import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from google_drive_service import GoogleDriveService

class TestGoogleDriveService:
    
    @patch('google_drive_service.build')
    @patch('google_drive_service.Credentials')
    @patch('google_drive_service.GoogleDriveService._authenticate')
    def test_init_with_existing_token(self, mock_authenticate, mock_creds, mock_build):
        # Mock the _authenticate method to return a mock service
        mock_service = Mock()
        mock_authenticate.return_value = mock_service
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        assert drive.service == mock_service
        assert drive.administration == 'GoodwinSolutions'
        mock_authenticate.assert_called_once()
    
    @patch('database.DatabaseManager')
    @patch('services.credential_service.CredentialService')
    @patch('google_drive_service.build')
    @patch('google_drive_service.Credentials')
    def test_authenticate_with_valid_token(self, mock_creds, mock_build, mock_cred_service_class, mock_db_manager_class):
        # Setup mocks
        mock_db = Mock()
        mock_db_manager_class.return_value = mock_db
        
        mock_cred_svc = Mock()
        mock_cred_service_class.return_value = mock_cred_svc
        
        # Mock OAuth credentials
        oauth_creds = {
            'installed': {
                'client_id': 'test_client_id',
                'client_secret': 'test_secret'
            }
        }
        mock_cred_svc.get_credential.side_effect = [
            oauth_creds,  # google_drive_oauth
            {'token': 'test_token', 'refresh_token': 'refresh'}  # google_drive_token
        ]
        
        # Mock valid credentials
        mock_creds_instance = Mock()
        mock_creds_instance.valid = True
        mock_creds.from_authorized_user_info.return_value = mock_creds_instance
        
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        assert drive.service == mock_service
        assert drive.administration == 'GoodwinSolutions'
        mock_creds.from_authorized_user_info.assert_called_once()
        mock_build.assert_called_once_with('drive', 'v3', credentials=mock_creds_instance)
    
    @patch('database.DatabaseManager')
    @patch('services.credential_service.CredentialService')
    @patch('google_drive_service.build')
    @patch('google_drive_service.Credentials')
    @patch('google_drive_service.Request')
    def test_authenticate_with_expired_token_refresh(self, mock_request, mock_creds, mock_build, mock_cred_service_class, mock_db_manager_class):
        # Setup mocks
        mock_db = Mock()
        mock_db_manager_class.return_value = mock_db
        
        mock_cred_svc = Mock()
        mock_cred_service_class.return_value = mock_cred_svc
        
        # Mock OAuth credentials
        oauth_creds = {
            'installed': {
                'client_id': 'test_client_id',
                'client_secret': 'test_secret'
            }
        }
        mock_cred_svc.get_credential.side_effect = [
            oauth_creds,  # google_drive_oauth
            {'token': 'expired_token', 'refresh_token': 'refresh'}  # google_drive_token
        ]
        
        # Mock expired credentials that can be refreshed
        mock_creds_instance = Mock()
        mock_creds_instance.valid = False
        mock_creds_instance.expired = True
        mock_creds_instance.refresh_token = 'refresh'
        mock_creds_instance.to_json.return_value = '{"token": "new_token"}'
        mock_creds.from_authorized_user_info.return_value = mock_creds_instance
        
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        assert drive.service == mock_service
        mock_creds_instance.refresh.assert_called_once()
        mock_cred_svc.store_credential.assert_called_once()
    
    @patch('database.DatabaseManager')
    @patch('services.credential_service.CredentialService')
    def test_authenticate_without_oauth_credentials(self, mock_cred_service_class, mock_db_manager_class):
        # Setup mocks
        mock_db = Mock()
        mock_db_manager_class.return_value = mock_db
        
        mock_cred_svc = Mock()
        mock_cred_service_class.return_value = mock_cred_svc
        
        # No OAuth credentials found
        mock_cred_svc.get_credential.return_value = None
        
        with pytest.raises(Exception) as exc_info:
            drive = GoogleDriveService('GoodwinSolutions')
        
        assert "OAuth credentials not found" in str(exc_info.value)
    
    @patch('google_drive_service.GoogleDriveService._authenticate')
    @patch.dict(os.environ, {'TEST_MODE': 'false', 'FACTUREN_FOLDER_ID': 'prod_folder_id'})
    def test_list_subfolders_production_mode(self, mock_authenticate):
        # Setup Drive service mocks
        mock_service = Mock()
        mock_files = Mock()
        mock_list = Mock()
        mock_execute = Mock()
        
        mock_execute.return_value = {
            'files': [
                {'id': 'folder1', 'name': 'Folder A', 'webViewLink': 'url1'},
                {'id': 'folder2', 'name': 'Folder B', 'webViewLink': 'url2'}
            ],
            'nextPageToken': None
        }
        mock_list.return_value.execute = mock_execute
        mock_files.return_value.list = mock_list
        mock_service.files = mock_files
        mock_authenticate.return_value = mock_service
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        result = drive.list_subfolders()
        
        assert len(result) == 2
        assert result[0]['name'] == 'Folder A'
        assert result[1]['name'] == 'Folder B'
        mock_list.assert_called_with(
            q="'prod_folder_id' in parents and mimeType='application/vnd.google-apps.folder'",
            fields="nextPageToken, files(id, name, webViewLink)",
            pageSize=1000,
            pageToken=None
        )
    
    @patch('google_drive_service.GoogleDriveService._authenticate')
    @patch.dict(os.environ, {'TEST_MODE': 'true', 'TEST_FACTUREN_FOLDER_ID': 'test_folder_id'})
    def test_list_subfolders_test_mode(self, mock_authenticate):
        # Setup Drive service mocks
        mock_service = Mock()
        mock_files = Mock()
        mock_list = Mock()
        mock_execute = Mock()
        
        mock_execute.return_value = {'files': [], 'nextPageToken': None}
        mock_list.return_value.execute = mock_execute
        mock_files.return_value.list = mock_list
        mock_service.files = mock_files
        mock_authenticate.return_value = mock_service
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        result = drive.list_subfolders()
        
        assert result == []
        mock_list.assert_called_with(
            q="'test_folder_id' in parents and mimeType='application/vnd.google-apps.folder'",
            fields="nextPageToken, files(id, name, webViewLink)",
            pageSize=1000,
            pageToken=None
        )
    
    @patch('google_drive_service.GoogleDriveService._authenticate')
    def test_list_subfolders_with_pagination(self, mock_authenticate):
        # Setup Drive service mocks
        mock_service = Mock()
        mock_files = Mock()
        mock_list = Mock()
        
        # First call returns page with nextPageToken
        first_call = Mock()
        first_call.return_value = {
            'files': [{'id': 'folder1', 'name': 'Folder 1', 'webViewLink': 'url1'}],
            'nextPageToken': 'token123'
        }
        
        # Second call returns final page
        second_call = Mock()
        second_call.return_value = {
            'files': [{'id': 'folder2', 'name': 'Folder 2', 'webViewLink': 'url2'}],
            'nextPageToken': None
        }
        
        mock_list.return_value.execute.side_effect = [first_call.return_value, second_call.return_value]
        mock_files.return_value.list = mock_list
        mock_service.files = mock_files
        mock_authenticate.return_value = mock_service
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        result = drive.list_subfolders()
        
        assert len(result) == 2
        assert mock_list.call_count == 2
    
    @patch('google_drive_service.GoogleDriveService._authenticate')
    def test_list_subfolders_error_handling(self, mock_authenticate):
        # Setup Drive service mocks with error
        mock_service = Mock()
        mock_files = Mock()
        mock_list = Mock()
        mock_list.return_value.execute.side_effect = Exception("API Error")
        mock_files.return_value.list = mock_list
        mock_service.files = mock_files
        mock_authenticate.return_value = mock_service
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        result = drive.list_subfolders()
        
        assert result == []
    
    @patch('google_drive_service.GoogleDriveService._authenticate')
    @patch('google_drive_service.MediaFileUpload')
    def test_upload_file(self, mock_media, mock_authenticate):
        # Setup Drive service mocks
        mock_service = Mock()
        mock_files = Mock()
        mock_create = Mock()
        mock_execute = Mock()
        
        mock_execute.return_value = {'id': 'file123', 'webViewLink': 'file_url'}
        mock_create.return_value.execute = mock_execute
        mock_files.return_value.create = mock_create
        mock_service.files = mock_files
        mock_authenticate.return_value = mock_service
        
        mock_media_instance = Mock()
        mock_media.return_value = mock_media_instance
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        result = drive.upload_file('/path/to/file.pdf', 'test.pdf', 'folder123')
        
        assert result['id'] == 'file123'
        assert result['url'] == 'file_url'
        mock_media.assert_called_once_with('/path/to/file.pdf', resumable=True)
        mock_create.assert_called_once_with(
            body={'name': 'test.pdf', 'parents': ['folder123']},
            media_body=mock_media_instance,
            fields='id,webViewLink'
        )
    
    @patch('google_drive_service.GoogleDriveService._authenticate')
    def test_check_file_exists_found(self, mock_authenticate):
        # Setup Drive service mocks
        mock_service = Mock()
        mock_files = Mock()
        mock_list = Mock()
        mock_execute = Mock()
        
        mock_execute.return_value = {
            'files': [{'id': 'file123', 'name': 'test.pdf', 'webViewLink': 'file_url'}]
        }
        mock_list.return_value.execute = mock_execute
        mock_files.return_value.list = mock_list
        mock_service.files = mock_files
        mock_authenticate.return_value = mock_service
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        result = drive.check_file_exists('test.pdf', 'folder123')
        
        assert result['exists'] is True
        assert result['file']['id'] == 'file123'
        assert result['file']['name'] == 'test.pdf'
        mock_list.assert_called_once_with(
            q="'folder123' in parents and name='test.pdf' and trashed=false",
            fields="files(id, name, webViewLink)"
        )
    
    @patch('google_drive_service.GoogleDriveService._authenticate')
    def test_check_file_exists_not_found(self, mock_authenticate):
        # Setup Drive service mocks
        mock_service = Mock()
        mock_files = Mock()
        mock_list = Mock()
        mock_execute = Mock()
        
        mock_execute.return_value = {'files': []}
        mock_list.return_value.execute = mock_execute
        mock_files.return_value.list = mock_list
        mock_service.files = mock_files
        mock_authenticate.return_value = mock_service
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        result = drive.check_file_exists('nonexistent.pdf', 'folder123')
        
        assert result['exists'] is False
    
    @patch('google_drive_service.GoogleDriveService._authenticate')
    def test_check_file_exists_error(self, mock_authenticate):
        # Setup Drive service mocks with error
        mock_service = Mock()
        mock_files = Mock()
        mock_list = Mock()
        mock_list.return_value.execute.side_effect = Exception("API Error")
        mock_files.return_value.list = mock_list
        mock_service.files = mock_files
        mock_authenticate.return_value = mock_service
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        result = drive.check_file_exists('test.pdf', 'folder123')
        
        assert result['exists'] is False
    
    @patch('google_drive_service.GoogleDriveService._authenticate')
    def test_create_folder(self, mock_authenticate):
        # Setup Drive service mocks
        mock_service = Mock()
        mock_files = Mock()
        mock_create = Mock()
        mock_execute = Mock()
        
        mock_execute.return_value = {
            'id': 'newfolder123',
            'name': 'New Folder',
            'webViewLink': 'folder_url'
        }
        mock_create.return_value.execute = mock_execute
        mock_files.return_value.create = mock_create
        mock_service.files = mock_files
        mock_authenticate.return_value = mock_service
        
        drive = GoogleDriveService('GoodwinSolutions')
        
        result = drive.create_folder('New Folder', 'parent123')
        
        assert result['id'] == 'newfolder123'
        assert result['name'] == 'New Folder'
        assert result['url'] == 'folder_url'
        mock_create.assert_called_once_with(
            body={
                'name': 'New Folder',
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': ['parent123']
            },
            fields='id,name,webViewLink'
        )