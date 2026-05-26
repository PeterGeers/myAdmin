"""
Preservation Property Tests — Provider-Aware Folder Routes

Property 2: Preservation — Google Drive Tenants Unaffected

These tests capture the BASELINE behavior on UNFIXED code for Google Drive tenants
(cases where isBugCondition returns false). They MUST PASS on unfixed code.

After the fix is implemented, these same tests MUST STILL PASS, confirming no
regressions were introduced for Google Drive tenants.

Spec: .kiro/specs/provider-aware-folder-routes
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11

Preservation from design:
    For all inputs where isBugCondition(X) returns false (provider is 'google_drive'
    or unset), the code SHALL produce exactly the same behavior as the original code.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11**
"""

import sys
import os
import re
import pytest
from unittest.mock import Mock, MagicMock, patch
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Tenant names for Google Drive tenants
tenant_st = st.sampled_from([
    'AcmeBV', 'TenantAlpha', 'GoodwinSolutions', 'PeterPrive',
    'VanDerBergBV', 'SmitConsulting', 'DeJongHolding'
])

# Provider values that indicate Google Drive (NOT S3) — isBugCondition = false
gdrive_provider_st = st.sampled_from(['google_drive', None])

# Folder names returned by Google Drive
folder_name_st = st.lists(
    st.sampled_from([
        'Supplier1', 'KPN', 'Ziggo', 'Albert Heijn', 'Bol.com',
        'Eneco', 'Vattenfall', 'T-Mobile', 'PostNL', 'DHL'
    ]),
    min_size=1,
    max_size=8,
    unique=True
)

# Regex patterns for folder filtering
regex_st = st.sampled_from([
    None, 'KPN', 'Zig.*', '^S', '.*com$', 'Albert|Eneco'
])

# Content types for output service
content_st = st.sampled_from([
    '<html>Report Content</html>',
    'Plain text report',
    '<h1>Monthly Summary</h1><p>Details here</p>'
])

filename_st = st.sampled_from([
    'report.html', 'summary.pdf', 'export_2024.xlsx', 'invoice_batch.html'
])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_flask_app():
    """Create a minimal Flask app for testing route handlers."""
    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


def make_drive_folders(names):
    """Create mock Google Drive folder response from a list of names."""
    return [{'id': f'id_{i}', 'name': name, 'url': f'http://drive/{name}'}
            for i, name in enumerate(names)]


# ---------------------------------------------------------------------------
# Test 1: Google Drive tenants use GoogleDriveService for get_folders()
# Requirement: 3.1
# ---------------------------------------------------------------------------

class TestGetFoldersPreservation:
    """
    For Google Drive tenants, get_folders() MUST call GoogleDriveService.list_subfolders()
    and return the folder names. This behavior must be preserved after the fix.

    **Validates: Requirements 3.1**
    """

    @settings(max_examples=20, deadline=None)
    @given(
        tenant=tenant_st,
        provider=gdrive_provider_st,
        folder_names=folder_name_st
    )
    def test_get_folders_uses_google_drive_for_gdrive_tenant(self, tenant, provider, folder_names):
        """
        PRESERVATION: get_folders() for a Google Drive tenant instantiates
        GoogleDriveService and calls list_subfolders(). MUST PASS on unfixed code.

        **Validates: Requirements 3.1**
        """
        app = create_flask_app()

        from routes import folder_routes
        app.register_blueprint(folder_routes.folder_bp)

        # Set production mode
        mock_config = MagicMock()
        mock_config.vendor_folders = {'test': 'TestFolder'}
        folder_routes.config = mock_config
        folder_routes.flag = False

        mock_gds_class = MagicMock()
        mock_gds_instance = MagicMock()
        mock_gds_instance.list_subfolders.return_value = make_drive_folders(folder_names)
        mock_gds_class.return_value = mock_gds_instance

        with patch.object(folder_routes, 'GoogleDriveService', mock_gds_class), \
             patch('auth.tenant_context.get_current_tenant', return_value=tenant), \
             patch('auth.cognito_utils.extract_user_credentials', return_value=('test@test.com', ['invoices_read'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_read']), \
             patch('database.DatabaseManager'):

            client = app.test_client()
            response = client.get('/api/folders', headers={
                'X-Tenant': tenant,
                'Authorization': 'Bearer fake_token'
            })

            # PRESERVATION: GoogleDriveService MUST be called for Google Drive tenants
            assert mock_gds_class.called, (
                f"REGRESSION: get_folders() for Google Drive tenant '{tenant}' "
                f"did NOT instantiate GoogleDriveService. Provider={provider}"
            )
            # Verify it was instantiated with the correct tenant
            mock_gds_class.assert_called_with(administration=tenant)
            # Verify list_subfolders was called
            assert mock_gds_instance.list_subfolders.called, (
                f"REGRESSION: GoogleDriveService was instantiated but "
                f"list_subfolders() was not called for tenant '{tenant}'"
            )
            # Verify response contains the folder names
            assert response.status_code == 200
            response_data = response.get_json()
            assert set(response_data) == set(folder_names)


# ---------------------------------------------------------------------------
# Test 2: Google Drive tenants use GoogleDriveService for create_folder()
# Requirement: 3.2
# ---------------------------------------------------------------------------

class TestCreateFolderPreservation:
    """
    For Google Drive tenants, create_folder() MUST call GoogleDriveService.create_folder().
    This behavior must be preserved after the fix.

    **Validates: Requirements 3.2**
    """

    @settings(max_examples=15, deadline=None)
    @given(
        tenant=tenant_st,
        provider=gdrive_provider_st,
        folder_name=st.sampled_from(['NewSupplier', 'KPN', 'Ziggo', 'TestVendor'])
    )
    def test_create_folder_uses_google_drive_for_gdrive_tenant(self, tenant, provider, folder_name):
        """
        PRESERVATION: create_folder() for a Google Drive tenant instantiates
        GoogleDriveService and calls create_folder(). MUST PASS on unfixed code.

        **Validates: Requirements 3.2**
        """
        app = create_flask_app()

        from routes import folder_routes
        app.register_blueprint(folder_routes.folder_bp)

        # Set production mode
        mock_config = MagicMock()
        mock_config.get_storage_folder.return_value = f'/tmp/{folder_name}'
        mock_config.ensure_folder_exists = MagicMock()
        folder_routes.config = mock_config
        folder_routes.flag = False

        mock_gds_class = MagicMock()
        mock_gds_instance = MagicMock()
        mock_gds_instance.create_folder.return_value = {
            'id': 'new_folder_id', 'name': folder_name, 'url': f'http://drive/{folder_name}'
        }
        mock_gds_class.return_value = mock_gds_instance

        with patch.object(folder_routes, 'GoogleDriveService', mock_gds_class), \
             patch('auth.tenant_context.get_current_tenant', return_value=tenant), \
             patch('auth.cognito_utils.extract_user_credentials', return_value=('test@test.com', ['invoices_create'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_create']), \
             patch('auth.tenant_context.get_user_tenants', return_value=[tenant]), \
             patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
             patch('database.DatabaseManager'), \
             patch.dict(os.environ, {'FACTUREN_FOLDER_ID': 'fake_parent_id', 'TEST_MODE': 'false'}):

            client = app.test_client()
            response = client.post('/api/create-folder',
                json={'folderName': folder_name},
                headers={
                    'X-Tenant': tenant,
                    'Authorization': 'Bearer fake_token'
                }
            )

            # PRESERVATION: GoogleDriveService MUST be called for Google Drive tenants
            assert mock_gds_class.called, (
                f"REGRESSION: create_folder('{folder_name}') for Google Drive tenant "
                f"'{tenant}' did NOT instantiate GoogleDriveService. Provider={provider}"
            )
            mock_gds_class.assert_called_with(administration=tenant)
            assert mock_gds_instance.create_folder.called, (
                f"REGRESSION: GoogleDriveService was instantiated but "
                f"create_folder() was not called for tenant '{tenant}'"
            )


# ---------------------------------------------------------------------------
# Test 3: Test mode (flag=True) returns local folders regardless of provider
# Requirement: 3.9
# ---------------------------------------------------------------------------

class TestFlagModePreservation:
    """
    When flag=True (test mode), get_folders() MUST return local config folders
    regardless of the tenant's invoice_provider setting.

    **Validates: Requirements 3.9**
    """

    @settings(max_examples=20, deadline=None)
    @given(
        tenant=tenant_st,
        provider=st.sampled_from(['google_drive', None, 's3_shared', 's3_tenant'])
    )
    def test_flag_true_returns_local_folders_regardless_of_provider(self, tenant, provider):
        """
        PRESERVATION: get_folders() with flag=True returns local config folders
        and does NOT call GoogleDriveService. MUST PASS on unfixed code.

        **Validates: Requirements 3.9**
        """
        app = create_flask_app()

        from routes import folder_routes
        app.register_blueprint(folder_routes.folder_bp)

        # Set TEST mode
        local_folders = {'vendor1': 'Supplier1', 'vendor2': 'KPN', 'vendor3': 'Ziggo'}
        mock_config = MagicMock()
        mock_config.vendor_folders = local_folders
        folder_routes.config = mock_config
        folder_routes.flag = True  # TEST MODE

        mock_gds_class = MagicMock()

        with patch.object(folder_routes, 'GoogleDriveService', mock_gds_class), \
             patch('auth.tenant_context.get_current_tenant', return_value=tenant), \
             patch('auth.cognito_utils.extract_user_credentials', return_value=('test@test.com', ['invoices_read'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_read']), \
             patch('database.DatabaseManager'):

            client = app.test_client()
            response = client.get('/api/folders', headers={
                'X-Tenant': tenant,
                'Authorization': 'Bearer fake_token'
            })

            # PRESERVATION: In test mode, GoogleDriveService must NOT be called
            assert not mock_gds_class.called, (
                f"REGRESSION: get_folders() in test mode (flag=True) for tenant "
                f"'{tenant}' with provider='{provider}' called GoogleDriveService. "
                f"Test mode should always return local folders."
            )
            # Verify response contains local folder values
            assert response.status_code == 200
            response_data = response.get_json()
            assert set(response_data) == set(local_folders.values())


# ---------------------------------------------------------------------------
# Test 4: handle_output(destination='download') returns content directly
# Requirement: 3.11
# ---------------------------------------------------------------------------

class TestDownloadDestinationPreservation:
    """
    handle_output(destination='download') MUST return content directly without
    calling any storage backend (Google Drive or S3).

    **Validates: Requirements 3.11**
    """

    @settings(max_examples=20, deadline=None)
    @given(
        tenant=tenant_st,
        content=content_st,
        filename=filename_st
    )
    def test_download_destination_returns_content_without_storage(self, tenant, content, filename):
        """
        PRESERVATION: handle_output(destination='download') returns content directly
        and does NOT call any storage backend. MUST PASS on unfixed code.

        **Validates: Requirements 3.11**
        """
        from services.output_service import OutputService

        mock_db = MagicMock()
        service = OutputService(mock_db)

        with patch.object(service, '_handle_gdrive_upload') as mock_gdrive, \
             patch.object(service, '_handle_s3_upload') as mock_s3:

            result = service.handle_output(
                content=content,
                filename=filename,
                destination='download',
                administration=tenant,
                content_type='text/html'
            )

            # PRESERVATION: Neither storage backend should be called for download
            assert not mock_gdrive.called, (
                f"REGRESSION: handle_output(destination='download') for tenant "
                f"'{tenant}' called _handle_gdrive_upload(). Download should "
                f"return content directly without any storage interaction."
            )
            assert not mock_s3.called, (
                f"REGRESSION: handle_output(destination='download') for tenant "
                f"'{tenant}' called _handle_s3_upload(). Download should "
                f"return content directly without any storage interaction."
            )
            # Verify the response contains the content directly
            assert result['success'] is True
            assert result['destination'] == 'download'
            assert result['content'] == content
            assert result['filename'] == filename


# ---------------------------------------------------------------------------
# Test 5: Regex filtering applies to folder list regardless of provider
# Requirement: 3.10
# ---------------------------------------------------------------------------

class TestRegexFilterPreservation:
    """
    Regex filtering on GET /api/folders applies to the folder list regardless
    of the storage provider. The filter produces the same subset for any provider.

    **Validates: Requirements 3.10**
    """

    @settings(max_examples=25, deadline=None)
    @given(
        tenant=tenant_st,
        folder_names=folder_name_st,
        regex_pattern=regex_st
    )
    def test_regex_filtering_produces_correct_subset(self, tenant, folder_names, regex_pattern):
        """
        PRESERVATION: Regex filtering on GET /api/folders applies correctly
        to the folder list. MUST PASS on unfixed code.

        **Validates: Requirements 3.10**
        """
        app = create_flask_app()

        from routes import folder_routes
        app.register_blueprint(folder_routes.folder_bp)

        # Set production mode
        mock_config = MagicMock()
        mock_config.vendor_folders = {'test': 'TestFolder'}
        folder_routes.config = mock_config
        folder_routes.flag = False

        mock_gds_class = MagicMock()
        mock_gds_instance = MagicMock()
        mock_gds_instance.list_subfolders.return_value = make_drive_folders(folder_names)
        mock_gds_class.return_value = mock_gds_instance

        with patch.object(folder_routes, 'GoogleDriveService', mock_gds_class), \
             patch('auth.tenant_context.get_current_tenant', return_value=tenant), \
             patch('auth.cognito_utils.extract_user_credentials', return_value=('test@test.com', ['invoices_read'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_read']), \
             patch('database.DatabaseManager'):

            client = app.test_client()
            url = '/api/folders'
            if regex_pattern:
                url += f'?regex={regex_pattern}'

            response = client.get(url, headers={
                'X-Tenant': tenant,
                'Authorization': 'Bearer fake_token'
            })

            assert response.status_code == 200
            response_data = response.get_json()

            # Compute expected filtered result
            if regex_pattern:
                compiled = re.compile(regex_pattern, re.IGNORECASE)
                expected = [f for f in folder_names if compiled.search(f)]
            else:
                expected = folder_names

            # PRESERVATION: Regex filtering must produce the same subset
            assert set(response_data) == set(expected), (
                f"REGRESSION: Regex filter '{regex_pattern}' on folders {folder_names} "
                f"returned {response_data} but expected {expected} for tenant '{tenant}'"
            )
