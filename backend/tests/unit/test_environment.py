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

    def test_config_initializes(self):
        # `test_mode` was removed from Config; it now constructs with no args and
        # the storage base folder is environment-independent.
        config = Config()

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
    
    def test_database_manager_constructs(self):
        # `test_mode` parameter + attribute were removed. DatabaseManager now
        # constructs with no args and always targets the `finance` schema.
        with patch('database.mysql.connector.connect'):
            db = DatabaseManager()
            assert db.config['database'] == 'finance'

    def test_database_manager_schema_always_finance(self):
        # Req 9.2, 9.3: the TEST_DB_NAME/testfinance switch is GONE. The schema is
        # ALWAYS `finance` regardless of the legacy TEST_MODE / TEST_DB_NAME env
        # vars — TEST vs PROD is distinguished by the resolved connection target,
        # not by the schema name.
        with patch('database.mysql.connector.connect'):
            with patch.dict(os.environ,
                            {'TEST_MODE': 'true', 'TEST_DB_NAME': 'testfinance'},
                            clear=False):
                db_env = DatabaseManager()
            db_default = DatabaseManager()

        assert db_env.config['database'] == 'finance'
        assert db_default.config['database'] == 'finance'
        # `testfinance` must never be selected anymore.
        assert db_env.config['database'] != 'testfinance'
    
    @patch('database.DatabaseManager')
    @patch('services.credential_service.CredentialService')
    @patch.dict(os.environ, {'TEST_FACTUREN_FOLDER_ID': 'test_folder_id'})
    @patch('google_drive_service.build')
    @patch('google_drive_service.Credentials')
    @patch('google_drive_service.os.path.exists')
    def test_google_drive_service_initializes(self, mock_exists, mock_creds, mock_build, mock_cred_service, mock_db):
        # Mock database and credential service
        mock_db_instance = Mock()
        mock_db.return_value = mock_db_instance
        
        mock_cred_service_instance = Mock()
        mock_cred_service.return_value = mock_cred_service_instance
        mock_cred_service_instance.get_credential.return_value = '{"client_id": "test"}'
        
        # Mock Google credentials
        mock_exists.return_value = True
        mock_creds_instance = Mock()
        mock_creds_instance.valid = True
        mock_creds.from_authorized_user_info.return_value = mock_creds_instance
        
        # Mock Google Drive service
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        drive = GoogleDriveService(administration='test_admin')
        
        # Verify the service was created
        assert drive is not None
        assert drive.administration == 'test_admin'
    
    def test_pdf_processor_initialization(self):
        # PDFProcessor no longer takes test_mode; it just constructs.
        processor = PDFProcessor()

        assert processor is not None
    
    def test_transaction_logic_initialization(self):
        # TransactionLogic no longer takes test_mode; it just constructs.
        with patch('database.mysql.connector.connect'):
            logic = TransactionLogic()

            assert logic is not None
    
    @patch('banking_processor.DatabaseManager')
    def test_banking_processor_initializes(self, mock_db):
        # test_mode is gone from both BankingProcessor and the internal
        # DatabaseManager it constructs.
        processor = BankingProcessor()

        assert processor is not None
        mock_db.assert_called_once_with()
    
    def test_str_processor_initialization(self):
        # STRProcessor no longer takes test_mode; it just constructs.
        with patch('database.mysql.connector.connect'):
            processor = STRProcessor()

            assert processor is not None
    
    def test_str_database_initialization(self):
        # STRDatabase no longer takes test_mode; it just constructs.
        with patch('database.mysql.connector.connect'):
            db = STRDatabase()

            assert db is not None
    
    @patch('pdf_validation.DatabaseManager')
    def test_pdf_validator_initializes(self, mock_db):
        validator = PDFValidator()

        assert validator is not None
        mock_db.assert_called_once_with()
    
    @patch('xlsx_export.DatabaseManager')
    def test_xlsx_export_processor_initializes(self, mock_db):
        processor = XLSXExportProcessor()

        assert processor is not None
        mock_db.assert_called_once_with()

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
    
    def test_database_schema_is_always_finance(self):
        # Req 9.2: the old DB_NAME/TEST_DB_NAME -> finance/testfinance switch is
        # removed. The DatabaseManager schema is now ALWAYS `finance`; TEST and
        # PROD are told apart by the resolved connection target, not by the schema
        # name. Even with the legacy TEST_DB_NAME var set, the manager must not
        # select `testfinance`.
        with patch('database.mysql.connector.connect'):
            with patch.dict(os.environ, {'TEST_DB_NAME': 'testfinance'}, clear=False):
                db = DatabaseManager()
        assert db.config['database'] == 'finance'
        assert db.config['database'] != 'testfinance'
    
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
    
    def test_components_initialize_together(self):
        # With test_mode removed, components simply construct against the single
        # (finance) schema; there is no per-instance mode to keep consistent.
        with patch('database.mysql.connector.connect'):
            db = DatabaseManager()
            banking = BankingProcessor()

            assert db.config['database'] == 'finance'
            assert banking is not None


class TestDotenvLoaderHygiene:
    """Guard the .env configuration-hygiene fix.

    Every import-time ``load_dotenv()`` under ``backend/src`` must PIN
    ``backend/.env`` via ``Path(__file__).parent.parent / ".env"`` rather than
    call the BARE ``load_dotenv()``. A bare call searches the CWD upward, so
    which .env loads becomes context-dependent: a script run from the repo root
    makes the backend import the ROOT .env, whose static personal-account AWS
    keys then clobber boto3's AWS_PROFILE (documented in
    scripts/onboarding/members/_generic/project-config-to-prod.py). Pinning makes
    the load deterministic and CWD-independent regardless of where Python starts.

    These tests parse module SOURCE (they do NOT call load_dotenv — forbidden in
    test files per steering 34 — and never open a DB connection), so they assert
    the property directly without mutating process env.
    """

    # Files whose loaders were pinned (app.py is the reference and already pinned).
    SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src")
    PINNED_MODULES = [
        "database.py",
        "transaction_logic.py",
        "actuals_routes.py",
        "google_drive_service.py",
        "ai_extractor.py",
        "hybrid_pricing_optimizer.py",
        "image_ai_processor.py",
        "app.py",  # the pattern these mirror
    ]

    def _read_src(self, filename):
        with open(os.path.join(self.SRC_DIR, filename), "r", encoding="utf-8") as fh:
            return fh.read()

    @pytest.mark.parametrize("filename", PINNED_MODULES)
    def test_loader_has_no_bare_load_dotenv(self, filename):
        source = self._read_src(filename)
        # A bare call is load_dotenv with an empty arg list. The pinned form
        # always passes dotenv_path=..., so no "load_dotenv()" literal may remain.
        assert "load_dotenv()" not in source, (
            f"{filename} still calls bare load_dotenv() — it must pin backend/.env "
            "so the import-time load is CWD-independent."
        )

    @pytest.mark.parametrize("filename", PINNED_MODULES)
    def test_loader_pins_backend_env(self, filename):
        source = self._read_src(filename)
        # Accept either literal path layout used across the modules/app.py.
        pins_inline = 'dotenv_path=Path(__file__).parent.parent / ".env"' in source
        pins_via_var = (
            'Path(__file__).parent.parent / ".env"' in source
            and "load_dotenv(dotenv_path=" in source
        )
        assert pins_inline or pins_via_var, (
            f"{filename} must load backend/.env via "
            'load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env").'
        )

    def test_backend_env_resolves_to_backend_dir(self):
        # Sanity-check the relative depth the modules rely on: for a file directly
        # in backend/src, parent.parent is the backend/ dir, so the pinned path is
        # backend/.env — the single file the backend app is meant to read.
        from pathlib import Path

        fake_src_file = Path(self.SRC_DIR).resolve() / "database.py"
        resolved = (fake_src_file.parent.parent / ".env").resolve()
        assert resolved.name == ".env"
        assert resolved.parent.name == "backend"
