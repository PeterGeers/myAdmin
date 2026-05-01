"""
Unit tests for the Test Isolation Layer fixtures.

Tests that mock_db, mock_env, mock_cognito, and mock_google_drive
fixtures work correctly with expected defaults and custom values.
"""
import os
import pytest
from unittest.mock import MagicMock


class TestMockDb:
    """Tests for the mock_db fixture."""

    def test_execute_query_returns_empty_list_by_default(self, mock_db):
        """mock_db.execute_query returns [] by default."""
        result = mock_db.execute_query("SELECT * FROM users")
        assert result == []

    def test_execute_query_accepts_custom_return(self, mock_db):
        """mock_db.execute_query can be configured with custom return values."""
        mock_db.execute_query.return_value = [{'id': 1, 'name': 'Alice'}]
        result = mock_db.execute_query("SELECT * FROM users")
        assert result == [{'id': 1, 'name': 'Alice'}]

    def test_execute_batch_queries_returns_none_by_default(self, mock_db):
        """mock_db.execute_batch_queries returns None by default."""
        result = mock_db.execute_batch_queries([("INSERT INTO t VALUES (%s)", (1,))])
        assert result is None

    def test_transaction_context_manager(self, mock_db):
        """mock_db.transaction works as a context manager returning (cursor, conn)."""
        with mock_db.transaction() as (cursor, conn):
            assert cursor is not None
            assert conn is not None

    def test_get_cursor_context_manager(self, mock_db):
        """mock_db.get_cursor works as a context manager returning (cursor, conn)."""
        with mock_db.get_cursor() as (cursor, conn):
            assert cursor is not None
            assert conn is not None

    def test_execute_query_records_calls(self, mock_db):
        """mock_db tracks calls to execute_query."""
        mock_db.execute_query("SELECT 1", (42,))
        mock_db.execute_query.assert_called_once_with("SELECT 1", (42,))


class TestMockEnv:
    """Tests for the mock_env fixture."""

    def test_sets_test_mode(self, mock_env):
        """mock_env sets TEST_MODE to 'true'."""
        assert os.environ['TEST_MODE'] == 'true'

    def test_sets_db_host(self, mock_env):
        """mock_env sets DB_HOST to 'localhost'."""
        assert os.environ['DB_HOST'] == 'localhost'

    def test_sets_db_port(self, mock_env):
        """mock_env sets DB_PORT to '3306'."""
        assert os.environ['DB_PORT'] == '3306'

    def test_sets_db_credentials(self, mock_env):
        """mock_env sets DB_USER and DB_PASSWORD."""
        assert os.environ['DB_USER'] == 'test'
        assert os.environ['DB_PASSWORD'] == 'test'

    def test_sets_db_name(self, mock_env):
        """mock_env sets DB_NAME to 'testfinance'."""
        assert os.environ['DB_NAME'] == 'testfinance'

    def test_sets_cognito_vars(self, mock_env):
        """mock_env sets COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID."""
        assert os.environ['COGNITO_USER_POOL_ID'] == 'us-east-1_test'
        assert os.environ['COGNITO_CLIENT_ID'] == 'test-client-id'

    def test_sets_google_drive_folder(self, mock_env):
        """mock_env sets GOOGLE_DRIVE_FOLDER_ID."""
        assert os.environ['GOOGLE_DRIVE_FOLDER_ID'] == 'test-folder-id'

    def test_sets_aws_region(self, mock_env):
        """mock_env sets AWS_REGION."""
        assert os.environ['AWS_REGION'] == 'us-east-1'

    def test_sets_flask_env(self, mock_env):
        """mock_env sets FLASK_ENV to 'testing'."""
        assert os.environ['FLASK_ENV'] == 'testing'

    def test_all_expected_keys_present(self, mock_env):
        """mock_env yields a dict with all expected keys."""
        expected_keys = {
            'TEST_MODE', 'DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD',
            'DB_NAME', 'COGNITO_USER_POOL_ID', 'COGNITO_CLIENT_ID',
            'GOOGLE_DRIVE_FOLDER_ID', 'AWS_REGION', 'FLASK_ENV',
        }
        assert set(mock_env.keys()) == expected_keys


class TestMockCognito:
    """Tests for the mock_cognito fixture."""

    def test_admin_get_user_returns_default(self, mock_cognito):
        """mock_cognito.admin_get_user returns default test user."""
        response = mock_cognito.admin_get_user(
            UserPoolId='us-east-1_test', Username='test-user'
        )
        assert response['Username'] == 'test-user'

    def test_admin_get_user_has_email(self, mock_cognito):
        """Default user attributes include email."""
        response = mock_cognito.admin_get_user(
            UserPoolId='us-east-1_test', Username='test-user'
        )
        attrs = {a['Name']: a['Value'] for a in response['UserAttributes']}
        assert attrs['email'] == 'test@example.com'

    def test_admin_get_user_has_tenant(self, mock_cognito):
        """Default user attributes include tenant_id."""
        response = mock_cognito.admin_get_user(
            UserPoolId='us-east-1_test', Username='test-user'
        )
        attrs = {a['Name']: a['Value'] for a in response['UserAttributes']}
        assert attrs['custom:tenant_id'] == 'test-tenant'

    def test_custom_return_value(self, mock_cognito):
        """mock_cognito can be configured with custom return values."""
        mock_cognito.admin_get_user.return_value = {
            'Username': 'custom-user',
            'UserAttributes': [],
        }
        response = mock_cognito.admin_get_user(
            UserPoolId='pool', Username='custom-user'
        )
        assert response['Username'] == 'custom-user'


class TestMockGoogleDrive:
    """Tests for the mock_google_drive fixture."""

    def test_files_list_returns_empty(self, mock_google_drive):
        """Default files().list() returns empty file list."""
        result = mock_google_drive.files().list().execute()
        assert result == {'files': []}

    def test_files_get_returns_test_file(self, mock_google_drive):
        """Default files().get() returns test file metadata."""
        result = mock_google_drive.files().get().execute()
        assert result['id'] == 'test_file_id'
        assert result['name'] == 'test.pdf'
        assert result['mimeType'] == 'application/pdf'
