import os
import tempfile
import shutil
from unittest.mock import Mock, patch
from contextlib import contextmanager
import json

class TestHelpers:
    """Helper utilities for testing"""
    
    @staticmethod
    def create_temp_pdf(content=None):
        """Create a temporary PDF file for testing"""
        if content is None:
            content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 1\ntrailer\n<<\n/Size 1\n/Root 1 0 R\n>>\nstartxref\n%%EOF'
        
        fd, temp_path = tempfile.mkstemp(suffix='.pdf')
        with os.fdopen(fd, 'wb') as f:
            f.write(content)
        return temp_path
    
    @staticmethod
    def create_temp_csv(content=None):
        """Create a temporary CSV file for testing"""
        if content is None:
            content = "Date,Description,Amount\n2023-01-01,Test,100.00\n"
        
        fd, temp_path = tempfile.mkstemp(suffix='.csv')
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        return temp_path
    
    @staticmethod
    def create_temp_xlsx(content=None):
        """Create a temporary XLSX file for testing"""
        fd, temp_path = tempfile.mkstemp(suffix='.xlsx')
        os.close(fd)
        
        if content:
            with open(temp_path, 'wb') as f:
                f.write(content)
        
        return temp_path
    
    @staticmethod
    def mock_database_response(data):
        """Create a mock database response"""
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = data
        mock_cursor.fetchone.return_value = data[0] if data else None
        mock_cursor.rowcount = len(data) if data else 0
        return mock_cursor
    
    @staticmethod
    def mock_google_drive_file(file_id, name, mime_type='application/pdf'):
        """Create a mock Google Drive file response"""
        return {
            'id': file_id,
            'name': name,
            'mimeType': mime_type,
            'webViewLink': f'https://drive.google.com/file/d/{file_id}/view'
        }
    
    @staticmethod
    def mock_google_drive_folder(folder_id, name):
        """Create a mock Google Drive folder response"""
        return {
            'id': folder_id,
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'webViewLink': f'https://drive.google.com/folders/{folder_id}'
        }
    
    @staticmethod
    @contextmanager
    def temp_environment(**env_vars):
        """Temporarily set environment variables"""
        old_environ = dict(os.environ)
        os.environ.update(env_vars)
        try:
            yield
        finally:
            os.environ.clear()
            os.environ.update(old_environ)
    
    @staticmethod
    @contextmanager
    def temp_directory():
        """Create a temporary directory"""
        temp_dir = tempfile.mkdtemp()
        try:
            yield temp_dir
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @staticmethod
    def cleanup_temp_files(*file_paths):
        """Clean up temporary files"""
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
    
    @staticmethod
    def assert_file_exists(file_path):
        """Assert that a file exists"""
        assert os.path.exists(file_path), f"File does not exist: {file_path}"
    
    @staticmethod
    def assert_file_not_exists(file_path):
        """Assert that a file does not exist"""
        assert not os.path.exists(file_path), f"File should not exist: {file_path}"
    
    @staticmethod
    def read_json_file(file_path):
        """Read and parse a JSON file"""
        with open(file_path, 'r') as f:
            return json.load(f)
    
    @staticmethod
    def write_json_file(file_path, data):
        """Write data to a JSON file"""
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

class MockServices:
    """Mock external services for testing"""
    
    @staticmethod
    def mock_mysql_connection():
        """Mock MySQL connection"""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = None
        mock_cursor.rowcount = 0
        return mock_conn, mock_cursor
    
    @staticmethod
    def mock_google_drive_service():
        """Mock Google Drive service"""
        mock_service = Mock()
        
        # Mock files().list()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            'files': []
        }
        
        # Mock files().get()
        mock_service.files.return_value.get.return_value.execute.return_value = {
            'id': 'test_file_id',
            'name': 'test_file.pdf',
            'mimeType': 'application/pdf'
        }
        
        # Mock files().create()
        mock_service.files.return_value.create.return_value.execute.return_value = {
            'id': 'new_file_id',
            'webViewLink': 'https://drive.google.com/file/d/new_file_id/view'
        }
        
        return mock_service
    
    @staticmethod
    def mock_gmail_service():
        """Mock Gmail service"""
        mock_service = Mock()
        
        # Mock users().messages().get()
        mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            'id': 'message_id',
            'snippet': 'Test message'
        }
        
        return mock_service

class DatabaseTestHelper:
    """Helper for database testing"""
    
    @staticmethod
    def create_mock_database_manager(test_mode=True):
        """Create a mock DatabaseManager for testing"""
        mock_db = Mock()
        mock_db.test_mode = test_mode
        mock_conn, mock_cursor = MockServices.mock_mysql_connection()
        mock_db.get_connection.return_value = mock_conn
        return mock_db, mock_conn, mock_cursor
    
    @staticmethod
    def setup_mock_query_result(mock_cursor, result_data):
        """Setup mock cursor with specific query results"""
        if isinstance(result_data, list):
            mock_cursor.fetchall.return_value = result_data
            mock_cursor.fetchone.return_value = result_data[0] if result_data else None
            mock_cursor.rowcount = len(result_data)
        else:
            mock_cursor.fetchone.return_value = result_data
            mock_cursor.fetchall.return_value = [result_data] if result_data else []
            mock_cursor.rowcount = 1 if result_data else 0

class FileTestHelper:
    """Helper for file testing"""
    
    @staticmethod
    def create_test_files_structure(base_dir):
        """Create a test file structure"""
        structure = {
            'uploads': [],
            'storage': {
                'General': ['test1.pdf', 'test2.pdf'],
                'Booking.com': ['booking1.pdf'],
                'Kuwait': ['kuwait1.pdf']
            },
            'downloads': ['bank_statement.csv', 'airbnb_data.xlsx']
        }
        
        for folder, contents in structure.items():
            folder_path = os.path.join(base_dir, folder)
            os.makedirs(folder_path, exist_ok=True)
            
            if isinstance(contents, list):
                for file_name in contents:
                    file_path = os.path.join(folder_path, file_name)
                    with open(file_path, 'w') as f:
                        f.write(f'Test content for {file_name}')
            elif isinstance(contents, dict):
                for subfolder, files in contents.items():
                    subfolder_path = os.path.join(folder_path, subfolder)
                    os.makedirs(subfolder_path, exist_ok=True)
                    for file_name in files:
                        file_path = os.path.join(subfolder_path, file_name)
                        with open(file_path, 'w') as f:
                            f.write(f'Test content for {file_name}')
        
        return structure