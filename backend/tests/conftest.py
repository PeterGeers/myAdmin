import pytest
import os
import sys
import tempfile
import shutil
from unittest.mock import Mock, patch
import mysql.connector
from contextlib import contextmanager
from pathlib import Path

# Add src directory to Python path for imports
backend_dir = Path(__file__).parent.parent
src_dir = backend_dir / 'src'
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Test fixtures for pytest framework

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)

@pytest.fixture
def temp_file():
    """Create a temporary file for testing"""
    fd, temp_path = tempfile.mkstemp()
    os.close(fd)
    yield temp_path
    if os.path.exists(temp_path):
        os.remove(temp_path)

@pytest.fixture
def mock_database():
    """Mock database connection for testing"""
    with patch('mysql.connector.connect') as mock_connect:
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        yield {
            'connection': mock_conn,
            'cursor': mock_cursor,
            'connect': mock_connect
        }

@pytest.fixture
def mock_google_drive():
    """Mock Google Drive service for testing"""
    mock_service = Mock()
    mock_service.files.return_value.list.return_value.execute.return_value = {'files': []}
    mock_service.files.return_value.get.return_value.execute.return_value = {
        'id': 'test_file', 'name': 'test.pdf', 'mimeType': 'application/pdf'
    }
    yield mock_service

@pytest.fixture
def test_environment():
    """Set up test environment variables"""
    test_env = {
        'TEST_MODE': 'true',
        'DB_NAME': 'finance',
        'TEST_DB_NAME': 'testfinance',
        'FACTUREN_FOLDER_ID': 'prod_folder_id',
        'TEST_FACTUREN_FOLDER_ID': 'test_folder_id',
        'FACTUREN_FOLDER_NAME': 'Facturen',
        'TEST_FACTUREN_FOLDER_NAME': 'testFacturen'
    }
    
    with patch.dict(os.environ, test_env):
        yield test_env

@pytest.fixture
def production_environment():
    """Set up production environment variables"""
    prod_env = {
        'TEST_MODE': 'false',
        'DB_NAME': 'finance',
        'FACTUREN_FOLDER_ID': 'prod_folder_id',
        'FACTUREN_FOLDER_NAME': 'Facturen'
    }
    
    with patch.dict(os.environ, prod_env, clear=True):
        yield prod_env

@pytest.fixture
def sample_pdf_content():
    """Sample PDF content for testing"""
    return b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000074 00000 n \n0000000120 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n179\n%%EOF'

@pytest.fixture
def sample_csv_content():
    """Sample CSV content for banking tests"""
    return """Date,Description,Amount,Balance,Account
2023-01-01,Opening Balance,1000.00,1000.00,NL123456789
2023-01-02,Payment to Vendor,-250.00,750.00,NL123456789
2023-01-03,Income from Client,500.00,1250.00,NL123456789"""

@pytest.fixture
def sample_transaction_data():
    """Sample transaction data for testing"""
    return [
        {
            'TransactionNumber': 'T001',
            'TransactionDate': '2023-01-01',
            'TransactionDescription': 'Test transaction 1',
            'TransactionAmount': 100.00,
            'Debet': '1000',
            'Credit': '4000',
            'Administration': 'Test',
            'ReferenceNumber': 'REF001'
        },
        {
            'TransactionNumber': 'T002',
            'TransactionDate': '2023-01-02',
            'TransactionDescription': 'Test transaction 2',
            'TransactionAmount': 200.00,
            'Debet': '6000',
            'Credit': '1000',
            'Administration': 'Test',
            'ReferenceNumber': 'REF002'
        }
    ]

@pytest.fixture
def sample_str_data():
    """Sample STR booking data for testing"""
    return [
        {
            'checkinDate': '2023-06-01',
            'checkoutDate': '2023-06-05',
            'channel': 'Airbnb',
            'listing': 'Property1',
            'nights': 4,
            'guests': 2,
            'amountGross': 400.00,
            'amountNett': 360.00,
            'status': 'realised'
        },
        {
            'checkinDate': '2023-07-01',
            'checkoutDate': '2023-07-03',
            'channel': 'Booking.com',
            'listing': 'Property1',
            'nights': 2,
            'guests': 1,
            'amountGross': 200.00,
            'amountNett': 180.00,
            'status': 'planned'
        }
    ]

@contextmanager
def isolated_filesystem():
    """Create an isolated filesystem for testing"""
    cwd = os.getcwd()
    temp_dir = tempfile.mkdtemp()
    try:
        os.chdir(temp_dir)
        yield temp_dir
    finally:
        os.chdir(cwd)
        shutil.rmtree(temp_dir, ignore_errors=True)

# Test configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    # Register all markers (these are also in pytest.ini but we register them here too)
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, isolated, no external dependencies)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (database, file system, external services)"
    )
    config.addinivalue_line(
        "markers", "api: API tests (requires running Flask app with authentication)"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests (full stack testing)"
    )
    config.addinivalue_line(
        "markers", "performance: Performance tests (manual/nightly only, not for CI)"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take > 10 seconds"
    )
    config.addinivalue_line(
        "markers", "skip_ci: Skip in CI pipeline"
    )
    # Legacy markers for backward compatibility
    config.addinivalue_line(
        "markers", "database: Tests that require database connection (legacy, use integration)"
    )
    config.addinivalue_line(
        "markers", "external: Tests that require external services (legacy, use integration)"
    )


def pytest_collection_modifyitems(config, items):
    """
    Automatically mark tests based on their location in the directory structure.
    This ensures tests are properly categorized even without explicit markers.
    """
    for item in items:
        # Get test file path (works with both Unix and Windows paths)
        test_path = str(item.fspath).replace('\\', '/')
        
        # Auto-mark based on directory structure
        if '/tests/unit/' in test_path:
            item.add_marker(pytest.mark.unit)
        elif '/tests/integration/' in test_path:
            item.add_marker(pytest.mark.integration)
        elif '/tests/api/' in test_path:
            item.add_marker(pytest.mark.api)
        elif '/tests/e2e/' in test_path:
            item.add_marker(pytest.mark.e2e)
        elif '/tests/performance/' in test_path:
            item.add_marker(pytest.mark.performance)
        elif '/tests/database/' in test_path:
            # Database tests are integration tests
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.database)
        elif '/tests/patterns/' in test_path:
            # Pattern tests are typically integration tests
            item.add_marker(pytest.mark.integration)
        elif '/tests/manual/' in test_path:
            # Manual tests should be skipped in CI
            item.add_marker(pytest.mark.skip_ci)
        else:
            # Default: mark as unit test if not in a specific directory
            item.add_marker(pytest.mark.unit)