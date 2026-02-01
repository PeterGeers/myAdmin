import pytest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch
from test_helpers import TestHelpers, MockServices, DatabaseTestHelper, FileTestHelper

class TestInfrastructure:
    """Test the testing infrastructure itself"""
    
    def test_temp_dir_fixture(self, temp_dir):
        """Test temporary directory fixture"""
        assert os.path.exists(temp_dir)
        assert os.path.isdir(temp_dir)
        
        # Create a file in temp dir
        test_file = os.path.join(temp_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test content')
        
        assert os.path.exists(test_file)
    
    def test_temp_file_fixture(self, temp_file):
        """Test temporary file fixture"""
        assert isinstance(temp_file, str)
        # File should exist (created by fixture)
        with open(temp_file, 'w') as f:
            f.write('test')
        assert os.path.exists(temp_file)
    
    def test_mock_database_fixture(self, mock_database):
        """Test mock database fixture"""
        assert 'connection' in mock_database
        assert 'cursor' in mock_database
        assert 'connect' in mock_database
        
        # Test mock functionality
        mock_database['cursor'].fetchall.return_value = [{'id': 1, 'name': 'test'}]
        result = mock_database['cursor'].fetchall()
        assert result == [{'id': 1, 'name': 'test'}]
    
    def test_mock_google_drive_basic(self):
        """Test basic Google Drive mocking"""
        mock_service = MockServices.mock_google_drive_service()
        assert mock_service is not None
        assert hasattr(mock_service, 'files')
    
    def test_test_environment_fixture(self, test_environment):
        """Test environment variables fixture"""
        assert os.getenv('TEST_MODE') == 'true'
        assert os.getenv('TEST_DB_NAME') == 'testfinance'
        assert 'TEST_FACTUREN_FOLDER_ID' in test_environment
    
    def test_production_environment_fixture(self, production_environment):
        """Test production environment fixture"""
        assert os.getenv('TEST_MODE') == 'false'
        assert os.getenv('DB_NAME') == 'finance'
        assert 'FACTUREN_FOLDER_ID' in production_environment
    
    def test_sample_data_fixtures(self, sample_pdf_content, sample_csv_content, 
                                sample_transaction_data, sample_str_data):
        """Test sample data fixtures"""
        assert sample_pdf_content.startswith(b'%PDF')
        assert 'Date,Description,Amount' in sample_csv_content
        assert len(sample_transaction_data) == 2
        assert len(sample_str_data) == 2
        assert sample_transaction_data[0]['TransactionNumber'] == 'T001'
        assert sample_str_data[0]['channel'] == 'Airbnb'

class TestHelperUtilities:
    """Test helper utility functions"""
    
    def test_create_temp_pdf(self):
        """Test PDF creation helper"""
        pdf_path = TestHelpers.create_temp_pdf()
        
        try:
            assert os.path.exists(pdf_path)
            assert pdf_path.endswith('.pdf')
            
            with open(pdf_path, 'rb') as f:
                content = f.read()
                assert content.startswith(b'%PDF')
        finally:
            TestHelpers.cleanup_temp_files(pdf_path)
    
    def test_create_temp_csv(self):
        """Test CSV creation helper"""
        csv_path = TestHelpers.create_temp_csv()
        
        try:
            assert os.path.exists(csv_path)
            assert csv_path.endswith('.csv')
            
            with open(csv_path, 'r') as f:
                content = f.read()
                assert 'Date,Description,Amount' in content
        finally:
            TestHelpers.cleanup_temp_files(csv_path)
    
    def test_mock_database_response(self):
        """Test database response mocking"""
        test_data = [{'id': 1, 'name': 'test1'}, {'id': 2, 'name': 'test2'}]
        mock_cursor = TestHelpers.mock_database_response(test_data)
        
        assert mock_cursor.fetchall() == test_data
        assert mock_cursor.fetchone() == test_data[0]
        assert mock_cursor.rowcount == 2
    
    def test_mock_google_drive_file(self):
        """Test Google Drive file mocking"""
        file_mock = TestHelpers.mock_google_drive_file('file123', 'test.pdf')
        
        assert file_mock['id'] == 'file123'
        assert file_mock['name'] == 'test.pdf'
        assert file_mock['mimeType'] == 'application/pdf'
        assert 'webViewLink' in file_mock
    
    def test_mock_google_drive_folder(self):
        """Test Google Drive folder mocking"""
        folder_mock = TestHelpers.mock_google_drive_folder('folder123', 'TestFolder')
        
        assert folder_mock['id'] == 'folder123'
        assert folder_mock['name'] == 'TestFolder'
        assert folder_mock['mimeType'] == 'application/vnd.google-apps.folder'
    
    def test_temp_environment_context(self):
        """Test temporary environment context manager"""
        original_value = os.getenv('TEST_VAR', 'not_set')
        
        with TestHelpers.temp_environment(TEST_VAR='test_value'):
            assert os.getenv('TEST_VAR') == 'test_value'
        
        # Should be restored after context
        assert os.getenv('TEST_VAR', 'not_set') == original_value
    
    def test_temp_directory_context(self):
        """Test temporary directory context manager"""
        with TestHelpers.temp_directory() as temp_dir:
            assert os.path.exists(temp_dir)
            assert os.path.isdir(temp_dir)
            
            # Create a test file
            test_file = os.path.join(temp_dir, 'test.txt')
            with open(test_file, 'w') as f:
                f.write('test')
            assert os.path.exists(test_file)
        
        # Directory should be cleaned up
        assert not os.path.exists(temp_dir)
    
    def test_file_assertions(self, temp_file):
        """Test file assertion helpers"""
        # Create a test file
        with open(temp_file, 'w') as f:
            f.write('test')
        
        TestHelpers.assert_file_exists(temp_file)
        
        os.remove(temp_file)
        TestHelpers.assert_file_not_exists(temp_file)

class TestMockServices:
    """Test mock service utilities"""
    
    def test_mock_mysql_connection(self):
        """Test MySQL connection mocking"""
        mock_conn, mock_cursor = MockServices.mock_mysql_connection()
        
        assert mock_conn is not None
        assert mock_cursor is not None
        assert mock_conn.cursor() == mock_cursor
        assert mock_cursor.fetchall() == []
        assert mock_cursor.fetchone() is None
        assert mock_cursor.rowcount == 0
    
    def test_mock_google_drive_service(self):
        """Test Google Drive service mocking"""
        mock_service = MockServices.mock_google_drive_service()
        
        # Test files().list()
        result = mock_service.files().list().execute()
        assert 'files' in result
        assert result['files'] == []
        
        # Test files().get()
        result = mock_service.files().get().execute()
        assert result['id'] == 'test_file_id'
        assert result['name'] == 'test_file.pdf'
    
    def test_mock_gmail_service(self):
        """Test Gmail service mocking"""
        mock_service = MockServices.mock_gmail_service()
        
        result = mock_service.users().messages().get().execute()
        assert result['id'] == 'message_id'
        assert result['snippet'] == 'Test message'

class TestDatabaseHelper:
    """Test database testing helper"""
    
    def test_database_helper_mock_setup(self):
        """Test database helper mock setup"""
        mock_db, mock_conn, mock_cursor = DatabaseTestHelper.create_mock_database_manager()
        
        assert mock_db.test_mode is True
        assert mock_conn is not None
        assert mock_cursor is not None
        
        test_data = [{'id': 1, 'name': 'test1'}, {'id': 2, 'name': 'test2'}]
        DatabaseTestHelper.setup_mock_query_result(mock_cursor, test_data)
        
        assert mock_cursor.fetchall() == test_data
        assert mock_cursor.fetchone() == test_data[0]
        assert mock_cursor.rowcount == 2

class TestFileHelper:
    """Test file testing helper"""
    
    def test_create_test_files_structure(self, temp_dir):
        """Test test file structure creation"""
        structure = FileTestHelper.create_test_files_structure(temp_dir)
        
        # Verify structure was created
        assert os.path.exists(os.path.join(temp_dir, 'uploads'))
        assert os.path.exists(os.path.join(temp_dir, 'storage', 'General'))
        assert os.path.exists(os.path.join(temp_dir, 'storage', 'Booking.com'))
        assert os.path.exists(os.path.join(temp_dir, 'downloads'))
        
        # Verify files were created
        assert os.path.exists(os.path.join(temp_dir, 'storage', 'General', 'test1.pdf'))
        assert os.path.exists(os.path.join(temp_dir, 'storage', 'Booking.com', 'booking1.pdf'))
        assert os.path.exists(os.path.join(temp_dir, 'downloads', 'bank_statement.csv'))
        
        # Verify structure matches expected
        assert 'uploads' in structure
        assert 'storage' in structure
        assert 'downloads' in structure

class TestEnvironmentIsolation:
    """Test environment isolation between tests"""
    
    def test_environment_isolation_1(self):
        """First test with specific environment"""
        with TestHelpers.temp_environment(TEST_ISOLATION='test1'):
            assert os.getenv('TEST_ISOLATION') == 'test1'
    
    def test_environment_isolation_2(self):
        """Second test should not see previous environment"""
        assert os.getenv('TEST_ISOLATION') is None
        
        with TestHelpers.temp_environment(TEST_ISOLATION='test2'):
            assert os.getenv('TEST_ISOLATION') == 'test2'
    
    def test_file_isolation(self, temp_dir):
        """Test file isolation between tests"""
        test_file = os.path.join(temp_dir, 'isolation_test.txt')
        
        with open(test_file, 'w') as f:
            f.write('isolated content')
        
        assert os.path.exists(test_file)
        # Each test gets its own temp_dir, so isolation is automatic

@pytest.mark.integration
class TestIntegrationInfrastructure:
    """Test infrastructure for integration tests"""
    
    def test_integration_marker(self):
        """Test that integration marker works"""
        # This test should only run when integration tests are enabled
        assert True
    
    @pytest.mark.slow
    def test_slow_marker(self):
        """Test that slow marker works"""
        # This test should only run when slow tests are enabled
        assert True
    
    @pytest.mark.database
    def test_database_marker(self):
        """Test that database marker works"""
        # This test should only run when database tests are enabled
        assert True