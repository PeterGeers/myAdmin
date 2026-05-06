"""
API tests for tenant_admin_storage.py

Tests storage configuration, folder listing, and usage endpoints,
including authentication enforcement and input validation.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def tenant_admin_auth():
    """
    Mock authentication with Tenant_Admin role for tenant admin endpoints.
    """
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']):
        mock_creds.return_value = ('admin@example.com', ['Tenant_Admin'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestTenantAdminStorageAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_list_folders_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to list folders should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant-admin/storage/folders')
        assert response.status_code in (401, 403)

    def test_get_storage_config_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get storage config should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant-admin/storage/config')
        assert response.status_code in (401, 403)


# ============================================================================
# List Folders Tests
# ============================================================================


class TestTenantAdminStorageFolders:
    """Tests for GET /api/tenant-admin/storage/folders."""

    @patch('routes.tenant_admin_storage.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_storage.GoogleDriveService')
    def test_list_folders_returns_data(
        self, mock_drive_class, mock_tenant, client, tenant_admin_auth
    ):
        """Authenticated request should return folder list."""
        mock_drive = MagicMock()
        mock_drive_class.return_value = mock_drive
        mock_drive.list_subfolders.return_value = [
            {'id': 'folder-1', 'name': 'Invoices'},
            {'id': 'folder-2', 'name': 'Reports'}
        ]

        response = client.get(
            '/api/tenant-admin/storage/folders',
            headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 2
        assert data['folders'][0]['name'] == 'Invoices'

    @patch('routes.tenant_admin_storage.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_storage.GoogleDriveService')
    def test_list_folders_drive_error_returns_500(
        self, mock_drive_class, mock_tenant, client, tenant_admin_auth
    ):
        """Google Drive error should return 500."""
        mock_drive_class.side_effect = Exception('Drive service unavailable')

        response = client.get(
            '/api/tenant-admin/storage/folders',
            headers=tenant_admin_auth
        )
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data


# ============================================================================
# Get Storage Config Tests
# ============================================================================


class TestTenantAdminStorageConfig:
    """Tests for GET /api/tenant-admin/storage/config."""

    @patch('routes.tenant_admin_storage.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_storage.DatabaseManager')
    def test_get_config_returns_data(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Authenticated request should return storage config."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = [
            {'config_key': 'google_drive_invoices_folder_id', 'config_value': 'folder-abc', 'is_secret': False},
            {'config_key': 'google_drive_reports_folder_id', 'config_value': 'folder-def', 'is_secret': False}
        ]

        response = client.get(
            '/api/tenant-admin/storage/config',
            headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'google_drive_invoices_folder_id' in data['config']
        assert data['config']['google_drive_invoices_folder_id'] == 'folder-abc'


# ============================================================================
# Update Storage Config Tests
# ============================================================================


class TestTenantAdminStorageConfigUpdate:
    """Tests for PUT /api/tenant-admin/storage/config."""

    @patch('routes.tenant_admin_storage.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_storage.DatabaseManager')
    def test_update_config_no_data_returns_400(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Update with empty data should return 400."""
        response = client.put(
            '/api/tenant-admin/storage/config',
            headers=tenant_admin_auth,
            json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'no configuration' in data['error'].lower() or 'no data' in data['error'].lower()

    @patch('routes.tenant_admin_storage.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_storage.DatabaseManager')
    def test_update_config_success(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Valid config update should return 200."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = [
            {'config_key': 'storage_invoices_folder_id', 'config_value': 'new-folder-id'}
        ]

        response = client.put(
            '/api/tenant-admin/storage/config',
            headers=tenant_admin_auth,
            json={'invoices_folder_id': 'new-folder-id'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'updated successfully' in data['message'].lower()


# ============================================================================
# Test Folder Access Tests
# ============================================================================


class TestTenantAdminStorageTestFolder:
    """Tests for POST /api/tenant-admin/storage/test."""

    @patch('routes.tenant_admin_storage.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_storage.GoogleDriveService')
    def test_test_folder_missing_folder_id_returns_400(
        self, mock_drive_class, mock_tenant, client, tenant_admin_auth
    ):
        """Test folder without folder_id should return 400."""
        response = client.post(
            '/api/tenant-admin/storage/test',
            headers=tenant_admin_auth,
            json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'folder_id' in data['error'].lower()

    @patch('routes.tenant_admin_storage.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_storage.GoogleDriveService')
    def test_test_folder_success(
        self, mock_drive_class, mock_tenant, client, tenant_admin_auth
    ):
        """Valid folder test should return test results."""
        mock_drive = MagicMock()
        mock_drive_class.return_value = mock_drive

        # Mock files().list().execute()
        mock_files_list = MagicMock()
        mock_files_list.execute.return_value = {'files': [{'id': 'f1', 'name': 'test.pdf'}]}
        mock_drive.service.files.return_value.list.return_value = mock_files_list

        # Mock upload_text_file
        mock_drive.upload_text_file.return_value = {'id': 'test-file-id'}

        # Mock files().delete().execute()
        mock_drive.service.files.return_value.delete.return_value.execute.return_value = None

        response = client.post(
            '/api/tenant-admin/storage/test',
            headers=tenant_admin_auth,
            json={'folder_id': 'test-folder-123'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['test_result']['read_access'] is True


# ============================================================================
# Storage Usage Tests
# ============================================================================


class TestTenantAdminStorageUsage:
    """Tests for GET /api/tenant-admin/storage/usage."""

    @patch('routes.tenant_admin_storage.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_storage.DatabaseManager')
    @patch('routes.tenant_admin_storage.GoogleDriveService')
    def test_get_usage_no_folders_configured(
        self, mock_drive_class, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """No configured folders should return empty usage."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = []

        response = client.get(
            '/api/tenant-admin/storage/usage',
            headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['usage'] == {}
        assert 'no storage folders' in data['message'].lower()
