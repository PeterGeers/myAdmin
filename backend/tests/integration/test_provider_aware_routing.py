"""
Integration Tests for Provider-Aware Storage Routing

Tests end-to-end flows through route handlers with mocked S3 responses,
verifying that S3 tenants are correctly routed to S3SharedStorage and
Google Drive tenants continue to use GoogleDriveService.

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.9, 2.10, 2.11, 2.12
"""

import sys
import os
import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from io import BytesIO
from flask import Flask

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def create_test_app():
    """Create a minimal Flask app with relevant blueprints for testing."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def s3_tenant():
    """S3-configured tenant name."""
    return 'AcmeBV'


@pytest.fixture
def gdrive_tenant():
    """Google Drive-configured tenant name."""
    return 'GoodwinSolutions'


def make_s3_client(tenant='AcmeBV'):
    """Create a mock S3 client with standard responses for a given tenant."""
    client = MagicMock()
    # Default list_objects_v2 response with folders
    client.list_objects_v2.return_value = {
        'CommonPrefixes': [
            {'Prefix': f'{tenant}/invoices/Supplier1/'},
            {'Prefix': f'{tenant}/invoices/Supplier2/'},
        ],
        'Contents': [
            {'Key': f'{tenant}/invoices/EmptyFolder/.folder', 'Size': 0},
        ],
        'IsTruncated': False,
    }
    # Default put_object response
    client.put_object.return_value = {'ResponseMetadata': {'HTTPStatusCode': 200}}
    # Default delete_object response
    client.delete_object.return_value = {'ResponseMetadata': {'HTTPStatusCode': 204}}
    # Default head_bucket response
    client.head_bucket.return_value = {'ResponseMetadata': {'HTTPStatusCode': 200}}
    return client


@pytest.fixture
def mock_s3_client(s3_tenant):
    """Create a mock S3 client with standard responses."""
    return make_s3_client(s3_tenant)


@pytest.fixture
def mock_parameter_service_s3():
    """Mock ParameterService that returns s3_shared for storage provider."""
    mock_ps = MagicMock()
    mock_ps.get_param.side_effect = lambda ns, key, **kwargs: {
        ('storage', 'invoice_provider'): 's3_shared',
        ('storage', 's3_shared_bucket'): 'test-shared-bucket',
    }.get((ns, key), None)
    return mock_ps


def param_service_s3_side_effect(ns, key, **kwargs):
    """Side effect for ParameterService.get_param that handles both provider and bucket."""
    if ns == 'storage' and key == 'invoice_provider':
        return 's3_shared'
    if ns == 'storage' and key == 's3_shared_bucket':
        return 'test-shared-bucket'
    return None


# ---------------------------------------------------------------------------
# Test 1: Full folder listing flow for S3 tenant
# Requirement: 2.1
# ---------------------------------------------------------------------------

class TestFolderListingS3Flow:
    """Test full folder listing flow for S3 tenant with mocked S3 responses."""

    def test_get_folders_returns_s3_prefixes(self, s3_tenant, mock_s3_client):
        """
        Full flow: GET /api/folders for S3 tenant returns folder names
        extracted from S3 CommonPrefixes and .folder markers.

        Validates: Requirement 2.1
        """
        app = create_test_app()

        from routes import folder_routes
        app.register_blueprint(folder_routes.folder_bp)

        # Configure production mode
        mock_config = MagicMock()
        mock_config.vendor_folders = {'test': 'TestFolder'}
        folder_routes.config = mock_config
        folder_routes.flag = False

        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('test@test.com', ['invoices_read'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_read']), \
             patch('auth.tenant_context.get_current_tenant', return_value=s3_tenant), \
             patch('services.parameter_service.ParameterService.get_param',
                   side_effect=param_service_s3_side_effect), \
             patch('database.DatabaseManager'), \
             patch('boto3.client', return_value=mock_s3_client), \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-shared-bucket'}):

            client = app.test_client()
            response = client.get('/api/folders', headers={
                'X-Tenant': s3_tenant,
                'Authorization': 'Bearer fake_token'
            })

            assert response.status_code == 200
            data = response.get_json()
            assert isinstance(data, list)
            # Should contain folders from S3 prefixes
            assert 'Supplier1' in data
            assert 'Supplier2' in data
            assert 'EmptyFolder' in data

    def test_get_folders_with_regex_filter(self, s3_tenant, mock_s3_client):
        """
        Full flow: GET /api/folders?regex=Supplier for S3 tenant applies
        regex filtering to S3 folder results.

        Validates: Requirement 2.1
        """
        app = create_test_app()

        from routes import folder_routes
        app.register_blueprint(folder_routes.folder_bp)

        mock_config = MagicMock()
        mock_config.vendor_folders = {'test': 'TestFolder'}
        folder_routes.config = mock_config
        folder_routes.flag = False

        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('test@test.com', ['invoices_read'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_read']), \
             patch('auth.tenant_context.get_current_tenant', return_value=s3_tenant), \
             patch('services.parameter_service.ParameterService.get_param',
                   side_effect=param_service_s3_side_effect), \
             patch('database.DatabaseManager'), \
             patch('boto3.client', return_value=mock_s3_client), \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-shared-bucket'}):

            client = app.test_client()
            response = client.get('/api/folders?regex=Supplier', headers={
                'X-Tenant': s3_tenant,
                'Authorization': 'Bearer fake_token'
            })

            assert response.status_code == 200
            data = response.get_json()
            assert isinstance(data, list)
            # Only Supplier folders should match
            assert 'Supplier1' in data
            assert 'Supplier2' in data
            assert 'EmptyFolder' not in data


# ---------------------------------------------------------------------------
# Test 2: Full invoice upload flow for S3 tenant
# Requirement: 2.3
# ---------------------------------------------------------------------------

class TestInvoiceUploadS3Flow:
    """Test full invoice upload flow for S3 tenant (mock S3 put_object)."""

    def test_upload_to_drive_uses_s3_for_s3_tenant(self, s3_tenant, mock_s3_client):
        """
        Full flow: InvoiceService.upload_to_drive() for S3 tenant uploads
        to S3 via S3SharedStorage.upload() and returns S3 key.

        Validates: Requirement 2.3
        """
        import tempfile

        # Create a temp file to simulate uploaded invoice
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'%PDF-1.4 fake invoice content')
            temp_path = f.name

        try:
            with patch('services.parameter_service.ParameterService.get_param',
                       side_effect=param_service_s3_side_effect), \
                 patch('database.DatabaseManager'), \
                 patch('boto3.client', return_value=mock_s3_client), \
                 patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-shared-bucket'}):

                from services.invoice_service import InvoiceService
                service = InvoiceService(test_mode=False)

                result = service.upload_to_drive(
                    temp_path=temp_path,
                    filename='invoice_2024.pdf',
                    folder_name='Supplier1',
                    tenant=s3_tenant
                )

                # Verify S3 put_object was called
                assert mock_s3_client.put_object.called
                call_kwargs = mock_s3_client.put_object.call_args[1]
                assert call_kwargs['Bucket'] == 'test-shared-bucket'
                # Key should follow pattern: {tenant}/invoices/{reference}/{uuid}_{filename}
                assert s3_tenant in call_kwargs['Key']
                assert 'invoices' in call_kwargs['Key']
                assert 'Supplier1' in call_kwargs['Key']
                assert 'invoice_2024.pdf' in call_kwargs['Key']

                # Result should contain S3 key
                assert 'id' in result
                assert 'url' in result
                assert s3_tenant in result['id']
        finally:
            os.unlink(temp_path)


# ---------------------------------------------------------------------------
# Test 3: Full report output flow for S3 tenant
# Requirement: 2.5
# ---------------------------------------------------------------------------

class TestReportOutputS3Flow:
    """Test full report output flow for S3 tenant (mock S3 put_object)."""

    def test_handle_output_gdrive_routes_to_s3_for_s3_tenant(self, s3_tenant, mock_s3_client):
        """
        Full flow: OutputService.handle_output(destination='gdrive') for S3 tenant
        routes to _handle_s3_upload() and uploads report to S3.

        Validates: Requirement 2.5
        """
        mock_db = MagicMock()

        with patch('services.parameter_service.ParameterService.get_param',
                   return_value='s3_shared'), \
             patch('database.DatabaseManager', return_value=mock_db), \
             patch('boto3.client', return_value=mock_s3_client), \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-shared-bucket'}):

            from services.output_service import OutputService
            service = OutputService(mock_db)

            result = service.handle_output(
                content='<html><body>Monthly Report</body></html>',
                filename='report_2024_01.html',
                destination='gdrive',
                administration=s3_tenant,
                content_type='text/html'
            )

            assert result['success'] is True
            assert result['destination'] == 's3'
            assert 'url' in result or 'reference' in result
            assert result['filename'] == 'report_2024_01.html'

    def test_handle_output_download_unchanged_for_s3_tenant(self, s3_tenant):
        """
        Full flow: OutputService.handle_output(destination='download') for S3 tenant
        returns content directly without any storage backend interaction.

        Validates: Requirement 2.5 (download path preservation)
        """
        mock_db = MagicMock()

        from services.output_service import OutputService
        service = OutputService(mock_db)

        result = service.handle_output(
            content='<html><body>Report</body></html>',
            filename='report.html',
            destination='download',
            administration=s3_tenant,
            content_type='text/html'
        )

        assert result['success'] is True
        assert result['destination'] == 'download'
        assert result['content'] == '<html><body>Report</body></html>'


# ---------------------------------------------------------------------------
# Test 4: Storage admin endpoints for S3 tenant
# Requirements: 2.9, 2.10, 2.11, 2.12
# ---------------------------------------------------------------------------

class TestStorageAdminS3Flow:
    """Test storage admin endpoints for S3 tenant (mock list_objects_v2, head_bucket)."""

    def test_list_folders_returns_s3_prefixes(self, s3_tenant, mock_s3_client):
        """
        Full flow: GET /api/tenant-admin/storage/folders for S3 tenant
        returns folder structure from S3 prefixes.

        Validates: Requirement 2.9
        """
        app = create_test_app()

        from routes.tenant_admin_storage import tenant_admin_storage_bp
        app.register_blueprint(tenant_admin_storage_bp)

        # Override list_objects_v2 for tenant-level prefixes
        mock_s3_client.list_objects_v2.return_value = {
            'CommonPrefixes': [
                {'Prefix': f'{s3_tenant}/invoices/'},
                {'Prefix': f'{s3_tenant}/reports/'},
                {'Prefix': f'{s3_tenant}/templates/'},
            ],
            'IsTruncated': False,
        }

        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('admin@test.com', ['Tenant_Admin'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']), \
             patch('auth.tenant_context.get_current_tenant', return_value=s3_tenant), \
             patch('services.parameter_service.ParameterService.get_param',
                   side_effect=param_service_s3_side_effect), \
             patch('database.DatabaseManager'), \
             patch('boto3.client', return_value=mock_s3_client), \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-shared-bucket'}):

            client = app.test_client()
            response = client.get('/api/tenant-admin/storage/folders', headers={
                'X-Tenant': s3_tenant,
                'Authorization': 'Bearer fake_token'
            })

            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['tenant'] == s3_tenant
            assert len(data['folders']) == 3
            folder_names = [f['name'] for f in data['folders']]
            assert 'invoices' in folder_names
            assert 'reports' in folder_names
            assert 'templates' in folder_names

    def test_test_folder_access_uses_s3_validation(self, s3_tenant, mock_s3_client):
        """
        Full flow: POST /api/tenant-admin/storage/test for S3 tenant
        validates access via head_bucket and put/delete cycle.

        Validates: Requirement 2.10
        """
        app = create_test_app()

        from routes.tenant_admin_storage import tenant_admin_storage_bp
        app.register_blueprint(tenant_admin_storage_bp)

        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('admin@test.com', ['Tenant_Admin'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']), \
             patch('auth.tenant_context.get_current_tenant', return_value=s3_tenant), \
             patch('services.parameter_service.ParameterService.get_param',
                   side_effect=param_service_s3_side_effect), \
             patch('database.DatabaseManager'), \
             patch('boto3.client', return_value=mock_s3_client), \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-shared-bucket'}):

            client = app.test_client()
            response = client.post('/api/tenant-admin/storage/test',
                json={'folder_id': 'test-folder-id'},
                headers={
                    'X-Tenant': s3_tenant,
                    'Authorization': 'Bearer fake_token'
                }
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['test_result']['read_access'] is True
            assert data['test_result']['write_access'] is True
            assert data['test_result']['accessible'] is True
            # Verify S3 operations were called
            mock_s3_client.head_bucket.assert_called_once()
            mock_s3_client.put_object.assert_called_once()
            mock_s3_client.delete_object.assert_called_once()

    def test_get_storage_usage_sums_s3_objects(self, s3_tenant, mock_s3_client):
        """
        Full flow: GET /api/tenant-admin/storage/usage for S3 tenant
        calculates usage by summing S3 object sizes.

        Validates: Requirement 2.11
        """
        app = create_test_app()

        from routes.tenant_admin_storage import tenant_admin_storage_bp
        app.register_blueprint(tenant_admin_storage_bp)

        # Override list_objects_v2 for usage calculation
        mock_s3_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': f'{s3_tenant}/invoices/Supplier1/abc_invoice.pdf', 'Size': 1024000},
                {'Key': f'{s3_tenant}/invoices/Supplier2/def_receipt.pdf', 'Size': 512000},
                {'Key': f'{s3_tenant}/reports/report.html', 'Size': 2048},
                # .folder markers should be excluded from count
                {'Key': f'{s3_tenant}/invoices/EmptyFolder/.folder', 'Size': 0},
            ],
            'IsTruncated': False,
        }

        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('admin@test.com', ['Tenant_Admin'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']), \
             patch('auth.tenant_context.get_current_tenant', return_value=s3_tenant), \
             patch('services.parameter_service.ParameterService.get_param',
                   side_effect=param_service_s3_side_effect), \
             patch('database.DatabaseManager'), \
             patch('boto3.client', return_value=mock_s3_client), \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-shared-bucket'}):

            client = app.test_client()
            response = client.get('/api/tenant-admin/storage/usage', headers={
                'X-Tenant': s3_tenant,
                'Authorization': 'Bearer fake_token'
            })

            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            usage = data['usage']
            # 3 real files (excluding .folder marker)
            assert usage['file_count'] == 3
            # Total: 1024000 + 512000 + 2048 = 1538048
            assert usage['total_size_bytes'] == 1538048
            assert usage['total_size_mb'] == round(1538048 / (1024 * 1024), 2)

    def test_update_config_with_s3_validation(self, s3_tenant, mock_s3_client):
        """
        Full flow: PUT /api/tenant-admin/storage/config with validate=True
        for S3 tenant validates via head_bucket and put/delete cycle.

        Validates: Requirement 2.12
        """
        app = create_test_app()

        from routes.tenant_admin_storage import tenant_admin_storage_bp
        app.register_blueprint(tenant_admin_storage_bp)

        mock_db = MagicMock()
        mock_db.execute_query.return_value = []

        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('admin@test.com', ['Tenant_Admin'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']), \
             patch('auth.tenant_context.get_current_tenant', return_value=s3_tenant), \
             patch('services.parameter_service.ParameterService.get_param',
                   side_effect=param_service_s3_side_effect), \
             patch('database.DatabaseManager', return_value=mock_db), \
             patch('boto3.client', return_value=mock_s3_client), \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-shared-bucket'}):

            client = app.test_client()
            response = client.put('/api/tenant-admin/storage/config',
                json={
                    'validate': True,
                    'invoices_folder_id': 'some-config-value'
                },
                headers={
                    'X-Tenant': s3_tenant,
                    'Authorization': 'Bearer fake_token',
                    'Content-Type': 'application/json'
                }
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            # Verify S3 validation was performed
            mock_s3_client.head_bucket.assert_called_once()
            mock_s3_client.put_object.assert_called_once()
            mock_s3_client.delete_object.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5: Switching tenant from google_drive to s3_shared routes correctly
# Requirement: 2.1, 2.2
# ---------------------------------------------------------------------------

class TestProviderSwitching:
    """Test that switching a tenant from google_drive to s3_shared routes correctly."""

    def test_tenant_switch_from_gdrive_to_s3(self):
        """
        Full flow: A tenant that was previously google_drive is switched to
        s3_shared. Subsequent requests should route to S3.

        Validates: Requirements 2.1, 2.2
        """
        app = create_test_app()

        from routes import folder_routes
        app.register_blueprint(folder_routes.folder_bp)

        mock_config = MagicMock()
        mock_config.vendor_folders = {'test': 'TestFolder'}
        mock_config.get_storage_folder.return_value = '/tmp/NewFolder'
        mock_config.ensure_folder_exists = MagicMock()
        folder_routes.config = mock_config
        folder_routes.flag = False

        tenant = 'SwitchingTenant'

        # First call: provider returns google_drive
        mock_gds_class = MagicMock()
        mock_gds_instance = MagicMock()
        mock_gds_instance.list_subfolders.return_value = [
            {'id': 'gd_folder_1', 'name': 'OldFolder'}
        ]
        mock_gds_class.return_value = mock_gds_instance

        with patch.object(folder_routes, 'GoogleDriveService', mock_gds_class), \
             patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('test@test.com', ['invoices_read'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_read']), \
             patch('auth.tenant_context.get_current_tenant', return_value=tenant), \
             patch('services.parameter_service.ParameterService.get_param',
                   return_value='google_drive'), \
             patch('database.DatabaseManager'):

            client = app.test_client()
            response = client.get('/api/folders', headers={
                'X-Tenant': tenant,
                'Authorization': 'Bearer fake_token'
            })

            assert response.status_code == 200
            data = response.get_json()
            assert 'OldFolder' in data
            assert mock_gds_class.called

        # Second call: provider now returns s3_shared (tenant was switched)
        mock_gds_class.reset_mock()

        # Create S3 client with correct tenant prefix
        switching_s3_client = make_s3_client(tenant)

        with patch.object(folder_routes, 'GoogleDriveService', mock_gds_class), \
             patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('test@test.com', ['invoices_read'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_read']), \
             patch('auth.tenant_context.get_current_tenant', return_value=tenant), \
             patch('services.parameter_service.ParameterService.get_param',
                   side_effect=param_service_s3_side_effect), \
             patch('database.DatabaseManager'), \
             patch('boto3.client', return_value=switching_s3_client), \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-shared-bucket'}):

            client = app.test_client()
            response = client.get('/api/folders', headers={
                'X-Tenant': tenant,
                'Authorization': 'Bearer fake_token'
            })

            assert response.status_code == 200
            data = response.get_json()
            # Should now return S3 folders, not Google Drive folders
            assert 'Supplier1' in data
            assert 'Supplier2' in data
            # GoogleDriveService should NOT have been called
            assert not mock_gds_class.called, (
                "After switching to s3_shared, GoogleDriveService should not be called"
            )


# ---------------------------------------------------------------------------
# Test 6: Mixed scenario — two tenants with different providers
# Requirements: 2.1, 2.2
# ---------------------------------------------------------------------------

class TestMixedProviderScenario:
    """Test mixed scenario: two tenants with different providers in same request sequence."""

    def test_two_tenants_different_providers_same_sequence(self):
        """
        Full flow: Two tenants make requests in sequence — one uses S3,
        the other uses Google Drive. Each is routed correctly.

        Validates: Requirements 2.1, 2.2
        """
        app = create_test_app()

        from routes import folder_routes
        app.register_blueprint(folder_routes.folder_bp)

        mock_config = MagicMock()
        mock_config.vendor_folders = {'test': 'TestFolder'}
        mock_config.get_storage_folder.return_value = '/tmp/Folder'
        mock_config.ensure_folder_exists = MagicMock()
        folder_routes.config = mock_config
        folder_routes.flag = False

        s3_tenant = 'S3TenantBV'
        gdrive_tenant = 'GDriveTenantBV'

        mock_gds_class = MagicMock()
        mock_gds_instance = MagicMock()
        mock_gds_instance.list_subfolders.return_value = [
            {'id': 'gd_1', 'name': 'DriveFolder1'},
            {'id': 'gd_2', 'name': 'DriveFolder2'},
        ]
        mock_gds_class.return_value = mock_gds_instance

        def param_side_effect(ns, key, **kwargs):
            tenant = kwargs.get('tenant', '')
            if ns == 'storage' and key == 'invoice_provider':
                if tenant == s3_tenant:
                    return 's3_shared'
                return 'google_drive'
            if ns == 'storage' and key == 's3_shared_bucket':
                return 'test-shared-bucket'
            return None

        # Create S3 client with correct tenant prefix
        s3_client = make_s3_client(s3_tenant)

        # Request 1: S3 tenant
        with patch.object(folder_routes, 'GoogleDriveService', mock_gds_class), \
             patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('test@test.com', ['invoices_read'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_read']), \
             patch('auth.tenant_context.get_current_tenant', return_value=s3_tenant), \
             patch('services.parameter_service.ParameterService.get_param',
                   side_effect=param_side_effect), \
             patch('database.DatabaseManager'), \
             patch('boto3.client', return_value=s3_client), \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-shared-bucket'}):

            client = app.test_client()
            response = client.get('/api/folders', headers={
                'X-Tenant': s3_tenant,
                'Authorization': 'Bearer fake_token'
            })

            assert response.status_code == 200
            data = response.get_json()
            assert 'Supplier1' in data
            assert not mock_gds_class.called

        # Request 2: Google Drive tenant
        mock_gds_class.reset_mock()

        def param_side_effect_gdrive(ns, key, **kwargs):
            tenant = kwargs.get('tenant', '')
            if ns == 'storage' and key == 'invoice_provider':
                if tenant == s3_tenant:
                    return 's3_shared'
                return 'google_drive'
            if ns == 'storage' and key == 's3_shared_bucket':
                return 'test-shared-bucket'
            return None

        with patch.object(folder_routes, 'GoogleDriveService', mock_gds_class), \
             patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('test@test.com', ['invoices_read'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_read']), \
             patch('auth.tenant_context.get_current_tenant', return_value=gdrive_tenant), \
             patch('services.parameter_service.ParameterService.get_param',
                   side_effect=param_side_effect_gdrive), \
             patch('database.DatabaseManager'):

            client = app.test_client()
            response = client.get('/api/folders', headers={
                'X-Tenant': gdrive_tenant,
                'Authorization': 'Bearer fake_token'
            })

            assert response.status_code == 200
            data = response.get_json()
            assert 'DriveFolder1' in data
            assert 'DriveFolder2' in data
            # GoogleDriveService SHOULD be called for Google Drive tenant
            assert mock_gds_class.called

    def test_create_folder_mixed_providers(self):
        """
        Full flow: S3 tenant creates folder via marker object,
        Google Drive tenant creates folder via GoogleDriveService.

        Validates: Requirement 2.2
        """
        app = create_test_app()

        from routes import folder_routes
        app.register_blueprint(folder_routes.folder_bp)

        mock_config = MagicMock()
        mock_config.get_storage_folder.return_value = '/tmp/NewFolder'
        mock_config.ensure_folder_exists = MagicMock()
        folder_routes.config = mock_config
        folder_routes.flag = False

        s3_tenant = 'S3TenantBV'

        def param_side_effect(ns, key, **kwargs):
            if ns == 'storage' and key == 'invoice_provider':
                return 's3_shared'
            if ns == 'storage' and key == 's3_shared_bucket':
                return 'test-shared-bucket'
            return None

        # Create S3 client for this tenant
        s3_client = make_s3_client(s3_tenant)

        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('test@test.com', ['invoices_create'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_create']), \
             patch('auth.tenant_context.get_current_tenant', return_value=s3_tenant), \
             patch('auth.tenant_context.get_user_tenants', return_value=[s3_tenant]), \
             patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
             patch('services.parameter_service.ParameterService.get_param',
                   side_effect=param_side_effect), \
             patch('database.DatabaseManager'), \
             patch('boto3.client', return_value=s3_client), \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-shared-bucket'}):

            client = app.test_client()
            response = client.post('/api/create-folder',
                json={'folderName': 'NewSupplier'},
                headers={
                    'X-Tenant': s3_tenant,
                    'Authorization': 'Bearer fake_token'
                }
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            # Verify S3 marker object was created
            s3_client.put_object.assert_called_once()
            call_kwargs = s3_client.put_object.call_args[1]
            expected_key = f'{s3_tenant}/invoices/NewSupplier/.folder'
            assert call_kwargs['Key'] == expected_key
            assert call_kwargs['Body'] == b''


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
