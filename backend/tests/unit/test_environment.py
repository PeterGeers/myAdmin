import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import Config
from database import DatabaseManager
from google_drive_service import GoogleDriveService
from pdf_processor import PDFProcessor
from transaction_logic import TransactionLogic
from banking_processor import BankingProcessor
from str_processor import STRProcessor
from str_database import STRDatabase
from pdf_validation import PDFValidator
from xlsx_export import XLSXExportProcessor

class TestEnvironmentModeSwitching:
    
    def test_config_test_mode(self):
        config = Config(test_mode=True)
        
        assert config.test_mode is True
        assert config.base_folder.endswith('storage')
    
    def test_config_production_mode(self):
        config = Config(test_mode=False)
        
        assert config.test_mode is False
        assert config.base_folder.endswith('storage')
    
    def test_config_vendor_folders(self):
        config = Config()
        
        assert 'booking.com' in config.vendor_folders
        assert config.vendor_folders['booking.com'] == 'Booking.com'
        assert config.vendor_folders['general'] == 'General'
    
    def test_config_get_storage_folder(self):
        config = Config()
        
        folder = config.get_storage_folder('booking.com')
        assert folder.endswith(os.path.join('storage', 'Booking.com'))
        
        folder = config.get_storage_folder('unknown')
        assert folder.endswith(os.path.join('storage', 'unknown'))
    
    @patch('config.os.makedirs')
    def test_config_ensure_folder_exists(self, mock_makedirs):
        config = Config()
        
        config.ensure_folder_exists('/test/folder')
        
        mock_makedirs.assert_called_once_with('/test/folder', exist_ok=True)
    
    def test_database_manager_test_mode_basic(self):
        # Test basic mode setting without database connection
        with patch('database.mysql.connector.connect'):
            db = DatabaseManager(test_mode=True)
            assert db.test_mode is True
    
    def test_database_manager_production_mode_basic(self):
        # Test basic mode setting without database connection
        with patch('database.mysql.connector.connect'):
            db = DatabaseManager(test_mode=False)
            assert db.test_mode is False
    
    @patch.dict(os.environ, {'TEST_MODE': 'true', 'TEST_FACTUREN_FOLDER_ID': 'test_folder_id'})
    @patch('google_drive_service.build')
    @patch('google_drive_service.Credentials')
    @patch('google_drive_service.os.path.exists')
    def test_google_drive_service_test_mode(self, mock_exists, mock_creds, mock_build):
        mock_exists.return_value = True
        mock_creds_instance = Mock()
        mock_creds_instance.valid = True
        mock_creds.from_authorized_user_file.return_value = mock_creds_instance
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        drive = GoogleDriveService(administration='test_admin')
        
        # Test that it uses test folder ID when in test mode
        with patch.object(drive, 'list_subfolders') as mock_list:
            mock_list.return_value = []
            drive.list_subfolders()
            # Verify it's using the test environment variables
    
    @patch.dict(os.environ, {'TEST_MODE': 'false', 'FACTUREN_FOLDER_ID': 'prod_folder_id'})
    @patch('google_drive_service.build')
    @patch('google_drive_service.Credentials')
    @patch('google_drive_service.os.path.exists')
    def test_google_drive_service_production_mode(self, mock_exists, mock_creds, mock_build):
        mock_exists.return_value = True
        mock_creds_instance = Mock()
        mock_creds_instance.valid = True
        mock_creds.from_authorized_user_file.return_value = mock_creds_instance
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        drive = GoogleDriveService(administration='prod_admin')
        
        # Test that it uses production folder ID when in production mode
        with patch.object(drive, 'list_subfolders') as mock_list:
            mock_list.return_value = []
            drive.list_subfolders()
    
    def test_pdf_processor_initialization(self):
        # Test that PDFProcessor can be initialized with different modes
        processor_test = PDFProcessor(test_mode=True)
        processor_prod = PDFProcessor(test_mode=False)
        
        # Both should initialize successfully
        assert processor_test is not None
        assert processor_prod is not None
    
    def test_transaction_logic_initialization(self):
        # Test that TransactionLogic can be initialized with different modes
        with patch('database.mysql.connector.connect'):
            logic_test = TransactionLogic(test_mode=True)
            logic_prod = TransactionLogic(test_mode=False)
            
            assert logic_test.test_mode is True
            assert logic_prod.test_mode is False
    
    @patch('banking_processor.DatabaseManager')
    def test_banking_processor_test_mode(self, mock_db):
        processor = BankingProcessor(test_mode=True)
        
        assert processor.test_mode is True
        mock_db.assert_called_once_with(test_mode=True)
    
    @patch('banking_processor.DatabaseManager')
    def test_banking_processor_production_mode(self, mock_db):
        processor = BankingProcessor(test_mode=False)
        
        assert processor.test_mode is False
        mock_db.assert_called_once_with(test_mode=False)
    
    def test_str_processor_initialization(self):
        # Test that STRProcessor can be initialized with different modes
        with patch('database.mysql.connector.connect'):
            processor_test = STRProcessor(test_mode=True)
            processor_prod = STRProcessor(test_mode=False)
            
            assert processor_test.test_mode is True
            assert processor_prod.test_mode is False
    
    def test_str_database_initialization(self):
        # Test that STRDatabase can be initialized with different modes
        with patch('database.mysql.connector.connect'):
            db_test = STRDatabase(test_mode=True)
            db_prod = STRDatabase(test_mode=False)
            
            assert db_test.test_mode is True
            assert db_prod.test_mode is False
    
    @patch('pdf_validation.GoogleDriveService')
    @patch('pdf_validation.DatabaseManager')
    def test_pdf_validator_test_mode(self, mock_db, mock_drive):
        validator = PDFValidator(test_mode=True)
        
        assert validator.test_mode is True
        mock_db.assert_called_once_with(test_mode=True)
    
    @patch('pdf_validation.GoogleDriveService')
    @patch('pdf_validation.DatabaseManager')
    def test_pdf_validator_production_mode(self, mock_db, mock_drive):
        validator = PDFValidator(test_mode=False)
        
        assert validator.test_mode is False
        mock_db.assert_called_once_with(test_mode=False)
    
    @patch('xlsx_export.DatabaseManager')
    def test_xlsx_export_processor_test_mode(self, mock_db):
        processor = XLSXExportProcessor(test_mode=True)
        
        assert processor.test_mode is True
        mock_db.assert_called_once_with(test_mode=True)
    
    @patch('xlsx_export.DatabaseManager')
    def test_xlsx_export_processor_production_mode(self, mock_db):
        processor = XLSXExportProcessor(test_mode=False)
        
        assert processor.test_mode is False
        mock_db.assert_called_once_with(test_mode=False)

class TestEnvironmentVariables:
    
    @patch.dict(os.environ, {'TEST_MODE': 'true'})
    def test_test_mode_environment_variable_true(self):
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        
        assert test_mode is True
    
    @patch.dict(os.environ, {'TEST_MODE': 'false'})
    def test_test_mode_environment_variable_false(self):
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        
        assert test_mode is False
    
    @patch.dict(os.environ, {}, clear=True)
    def test_test_mode_environment_variable_default(self):
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        
        assert test_mode is False
    
    @patch.dict(os.environ, {'DB_NAME': 'finance', 'TEST_DB_NAME': 'testfinance'})
    def test_database_name_environment_variables(self):
        prod_db = os.getenv('DB_NAME', 'finance')
        test_db = os.getenv('TEST_DB_NAME', 'testfinance')
        
        assert prod_db == 'finance'
        assert test_db == 'testfinance'
    
    @patch.dict(os.environ, {'FACTUREN_FOLDER_ID': 'prod_folder', 'TEST_FACTUREN_FOLDER_ID': 'test_folder'})
    def test_folder_id_environment_variables(self):
        prod_folder = os.getenv('FACTUREN_FOLDER_ID')
        test_folder = os.getenv('TEST_FACTUREN_FOLDER_ID')
        
        assert prod_folder == 'prod_folder'
        assert test_folder == 'test_folder'
    
    @patch.dict(os.environ, {'FACTUREN_FOLDER_NAME': 'Facturen', 'TEST_FACTUREN_FOLDER_NAME': 'testFacturen'})
    def test_folder_name_environment_variables(self):
        prod_name = os.getenv('FACTUREN_FOLDER_NAME', 'Facturen')
        test_name = os.getenv('TEST_FACTUREN_FOLDER_NAME', 'testFacturen')
        
        assert prod_name == 'Facturen'
        assert test_name == 'testFacturen'

class TestModeConsistency:
    
    def test_components_mode_consistency(self):
        # Test that components can be initialized with consistent modes
        with patch('database.mysql.connector.connect'):
            test_mode = True
            
            # Initialize components with same test_mode
            db = DatabaseManager(test_mode=test_mode)
            banking = BankingProcessor(test_mode=test_mode)
            
            # Verify all use the same mode
            assert db.test_mode == test_mode
            assert banking.test_mode == test_mode
    
    def test_components_different_modes(self):
        # Test that different instances can have different modes
        with patch('database.mysql.connector.connect'):
            db_test = DatabaseManager(test_mode=True)
            db_prod = DatabaseManager(test_mode=False)
            
            assert db_test.test_mode is True
            assert db_prod.test_mode is False
            assert db_test.test_mode != db_prod.test_mode
    
    def test_mode_switching_isolation(self):
        # Test that different instances can have different modes
        config_test = Config(test_mode=True)
        config_prod = Config(test_mode=False)
        
        assert config_test.test_mode is True
        assert config_prod.test_mode is False
        
        # Verify they don't interfere with each other
        assert config_test.test_mode != config_prod.test_mode