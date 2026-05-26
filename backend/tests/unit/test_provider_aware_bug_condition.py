"""
Bug Condition Exploration Tests — Provider-Aware Folder Routes

Property 1: Bug Condition — S3 Tenants Unconditionally Hit GoogleDriveService

These tests encode the EXPECTED (correct) behavior. They are written BEFORE any fix
and MUST FAIL on unfixed code — failure confirms the bug exists.

DO NOT attempt to fix the test or the code when it fails.

After the fix is implemented, these same tests will PASS, confirming the fix works.

Spec: .kiro/specs/provider-aware-folder-routes
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 1.9

Bug Condition from design:
    isBugCondition(X) returns true when
    ParameterService.get_param('storage', 'invoice_provider', tenant=X.tenant)
    returns 's3_shared' or 's3_tenant'

Expected behavior (post-fix):
    All storage endpoints SHALL route to S3SharedStorage operations and
    SHALL NOT instantiate GoogleDriveService when the tenant's provider is s3_shared.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 1.9**
"""

import sys
import os
import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Tenant names — realistic Dutch company names that would use S3
tenant_st = st.sampled_from([
    'AcmeBV', 'TenantAlpha', 'GoodwinSolutions', 'PeterPrive',
    'VanDerBergBV', 'SmitConsulting', 'DeJongHolding'
])

# Folder/supplier names for create and upload operations
folder_name_st = st.sampled_from([
    'Supplier1', 'KPN', 'Ziggo', 'Albert Heijn', 'Bol.com',
    'NewVendor', 'TestSupplier', 'Eneco'
])

# Template names for email template tests
template_name_st = st.sampled_from([
    'user_invitation', 'invoice_reminder', 'payment_confirmation'
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


# ---------------------------------------------------------------------------
# Test 1: folder_routes.get_folders() — should use S3, not GoogleDriveService
# Requirement: 1.1
# ---------------------------------------------------------------------------

class TestGetFoldersBugCondition:
    """
    folder_routes.get_folders() SHOULD call list_s3_folders() for S3 tenants
    and SHOULD NOT instantiate GoogleDriveService.

    On UNFIXED code these tests FAIL because GoogleDriveService is always used.
    """

    @settings(max_examples=15, deadline=None)
    @given(tenant=tenant_st)
    def test_get_folders_does_not_use_google_drive_for_s3_tenant(self, tenant):
        """
        EXPECTED: get_folders() for an S3 tenant does NOT instantiate
        GoogleDriveService. FAILS on unfixed code — GoogleDriveService is called.

        **Validates: Requirements 1.1**
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
        mock_gds_instance.list_subfolders.return_value = [
            {'id': 'fake_id', 'name': 'FakeFolder', 'url': ''}
        ]
        mock_gds_class.return_value = mock_gds_instance

        with patch.object(folder_routes, 'GoogleDriveService', mock_gds_class), \
             patch('auth.tenant_context.get_current_tenant', return_value=tenant), \
             patch('auth.cognito_utils.extract_user_credentials', return_value=('test@test.com', ['invoices_read'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_read']), \
             patch('services.parameter_service.ParameterService.get_param', return_value='s3_shared'), \
             patch('database.DatabaseManager'):

            client = app.test_client()
            response = client.get('/api/folders', headers={
                'X-Tenant': tenant,
                'Authorization': 'Bearer fake_token'
            })

            # BUG ASSERTION: GoogleDriveService should NOT be called for S3 tenants
            assert not mock_gds_class.called, (
                f"BUG CONFIRMED: get_folders() for S3 tenant '{tenant}' "
                f"instantiated GoogleDriveService instead of using S3 prefix listing. "
                f"GoogleDriveService was called with args: {mock_gds_class.call_args}"
            )


# ---------------------------------------------------------------------------
# Test 2: folder_routes.create_folder() — should use S3, not GoogleDriveService
# Requirement: 1.2
# ---------------------------------------------------------------------------

class TestCreateFolderBugCondition:
    """
    folder_routes.create_folder() SHOULD call create_s3_folder() for S3 tenants
    and SHOULD NOT instantiate GoogleDriveService.

    On UNFIXED code these tests FAIL because GoogleDriveService is always used.
    """

    @settings(max_examples=15, deadline=None)
    @given(tenant=tenant_st, folder_name=folder_name_st)
    def test_create_folder_does_not_use_google_drive_for_s3_tenant(self, tenant, folder_name):
        """
        EXPECTED: create_folder() for an S3 tenant does NOT instantiate
        GoogleDriveService. FAILS on unfixed code — GoogleDriveService is called.

        **Validates: Requirements 1.2**
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
        mock_gds_instance.create_folder.return_value = {'id': 'fake_id', 'name': folder_name, 'url': ''}
        mock_gds_class.return_value = mock_gds_instance

        with patch.object(folder_routes, 'GoogleDriveService', mock_gds_class), \
             patch('auth.tenant_context.get_current_tenant', return_value=tenant), \
             patch('auth.cognito_utils.extract_user_credentials', return_value=('test@test.com', ['invoices_create'], None)), \
             patch('auth.cognito_utils.validate_permissions', return_value=(True, None)), \
             patch('auth.role_cache.get_tenant_roles', return_value=['invoices_create']), \
             patch('auth.tenant_context.get_user_tenants', return_value=[tenant]), \
             patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
             patch('services.parameter_service.ParameterService.get_param', return_value='s3_shared'), \
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

            # BUG ASSERTION: GoogleDriveService should NOT be called for S3 tenants
            assert not mock_gds_class.called, (
                f"BUG CONFIRMED: create_folder('{folder_name}') for S3 tenant '{tenant}' "
                f"instantiated GoogleDriveService instead of creating an S3 marker object. "
                f"GoogleDriveService was called with args: {mock_gds_class.call_args}"
            )


# ---------------------------------------------------------------------------
# Test 3: missing_invoices_routes.upload_receipt() — should use S3
# Requirement: 1.4
# ---------------------------------------------------------------------------

class TestUploadReceiptBugCondition:
    """
    missing_invoices_routes.upload_receipt() SHOULD use S3 for folder listing
    and file upload for S3 tenants.

    On UNFIXED code these tests FAIL because GoogleDriveService is always used.
    """

    @settings(max_examples=15, deadline=None)
    @given(tenant=tenant_st, supplier=folder_name_st)
    def test_upload_receipt_does_not_use_google_drive_for_s3_tenant(self, tenant, supplier):
        """
        EXPECTED: upload_receipt() for an S3 tenant does NOT instantiate
        GoogleDriveService. FAILS on unfixed code — GoogleDriveService is called.

        **Validates: Requirements 1.4**
        """
        app = create_flask_app()

        from io import BytesIO

        with app.test_request_context(
            '/api/upload-receipt',
            method='POST',
            data={
                'file': (BytesIO(b'fake pdf content'), 'receipt.pdf'),
                'supplierName': supplier
            },
            content_type='multipart/form-data',
            headers={'X-Tenant': tenant}
        ):
            from routes import missing_invoices_routes

            mock_gds_class = MagicMock()
            mock_gds_instance = MagicMock()
            mock_gds_instance.list_subfolders.return_value = [
                {'id': 'folder_1', 'name': supplier}
            ]
            mock_gds_instance.upload_file.return_value = {'id': 'file_1', 'url': 'http://fake'}
            mock_gds_class.return_value = mock_gds_instance

            with patch.object(missing_invoices_routes, 'GoogleDriveService', mock_gds_class), \
                 patch('auth.tenant_context.get_current_tenant', return_value=tenant), \
                 patch('services.parameter_service.ParameterService.get_param', return_value='s3_shared'), \
                 patch.dict(os.environ, {'FACTUREN_FOLDER_ID': 'fake_parent_id', 'TEST_MODE': 'false'}):

                try:
                    response = missing_invoices_routes.upload_receipt.__wrapped__(
                        user_email='test@test.com',
                        user_roles=['invoices_create']
                    )
                except Exception:
                    pass  # We only care about whether GDS was called

                # BUG ASSERTION: GoogleDriveService should NOT be called for S3 tenants
                assert not mock_gds_class.called, (
                    f"BUG CONFIRMED: upload_receipt() for S3 tenant '{tenant}' with supplier "
                    f"'{supplier}' instantiated GoogleDriveService instead of using S3. "
                    f"GoogleDriveService was called with args: {mock_gds_class.call_args}"
                )


# ---------------------------------------------------------------------------
# Test 4: output_service.handle_output(destination='gdrive') — should route to S3
# Requirement: 1.5
# ---------------------------------------------------------------------------

class TestOutputServiceBugCondition:
    """
    OutputService.handle_output(destination='gdrive') SHOULD route to
    _handle_s3_upload() for S3 tenants.

    On UNFIXED code these tests FAIL because _handle_gdrive_upload() is always called.
    """

    @settings(max_examples=15, deadline=None)
    @given(tenant=tenant_st)
    def test_handle_output_gdrive_does_not_use_google_drive_for_s3_tenant(self, tenant):
        """
        EXPECTED: handle_output(destination='gdrive') for an S3 tenant routes to
        _handle_s3_upload(). FAILS on unfixed code — _handle_gdrive_upload() is called.

        **Validates: Requirements 1.5**
        """
        from services.output_service import OutputService

        mock_db = MagicMock()
        service = OutputService(mock_db)

        # Track which internal method is called
        with patch.object(service, '_handle_gdrive_upload') as mock_gdrive, \
             patch.object(service, '_handle_s3_upload') as mock_s3, \
             patch('services.parameter_service.ParameterService.get_param', return_value='s3_shared'):

            mock_gdrive.return_value = {'success': True, 'destination': 'gdrive', 'url': 'http://fake'}
            mock_s3.return_value = {'success': True, 'destination': 's3', 'url': 's3://fake'}

            result = service.handle_output(
                content='<html>Report</html>',
                filename='report.html',
                destination='gdrive',
                administration=tenant,
                content_type='text/html'
            )

            # BUG ASSERTION: For S3 tenants, 'gdrive' destination should route to S3
            assert not mock_gdrive.called, (
                f"BUG CONFIRMED: handle_output(destination='gdrive') for S3 tenant '{tenant}' "
                f"called _handle_gdrive_upload() instead of routing to _handle_s3_upload(). "
                f"The code does not check the tenant's storage provider before routing."
            )
            assert mock_s3.called, (
                f"BUG CONFIRMED: handle_output(destination='gdrive') for S3 tenant '{tenant}' "
                f"did not call _handle_s3_upload(). Expected S3 routing for S3 tenants."
            )


# ---------------------------------------------------------------------------
# Test 5: tenant_admin_storage.list_folders() — should use S3
# Requirement: 1.9
# ---------------------------------------------------------------------------

class TestTenantAdminStorageBugCondition:
    """
    tenant_admin_storage.list_folders() SHOULD use list_objects_v2 for S3 tenants
    and SHOULD NOT instantiate GoogleDriveService.

    On UNFIXED code these tests FAIL because GoogleDriveService is always used.
    """

    @settings(max_examples=15, deadline=None)
    @given(tenant=tenant_st)
    def test_list_folders_does_not_use_google_drive_for_s3_tenant(self, tenant):
        """
        EXPECTED: list_folders() for an S3 tenant does NOT instantiate
        GoogleDriveService. FAILS on unfixed code — GoogleDriveService is called.

        **Validates: Requirements 1.9**
        """
        app = create_flask_app()

        with app.test_request_context(
            '/api/tenant-admin/storage/folders',
            headers={'X-Tenant': tenant}
        ):
            from routes import tenant_admin_storage

            mock_gds_class = MagicMock()
            mock_gds_instance = MagicMock()
            mock_gds_instance.list_subfolders.return_value = [
                {'id': 'folder_1', 'name': 'invoices'}
            ]
            mock_gds_class.return_value = mock_gds_instance

            with patch.object(tenant_admin_storage, 'GoogleDriveService', mock_gds_class), \
                 patch('auth.tenant_context.get_current_tenant', return_value=tenant), \
                 patch('services.parameter_service.ParameterService.get_param', return_value='s3_shared'):

                try:
                    response = tenant_admin_storage.list_folders.__wrapped__(
                        user_email='test@test.com',
                        user_roles=['Tenant_Admin']
                    )
                except Exception:
                    pass  # We only care about whether GDS was called

                # BUG ASSERTION: GoogleDriveService should NOT be called for S3 tenants
                assert not mock_gds_class.called, (
                    f"BUG CONFIRMED: tenant_admin_storage.list_folders() for S3 tenant "
                    f"'{tenant}' instantiated GoogleDriveService instead of using "
                    f"list_objects_v2 for S3 prefix listing. "
                    f"GoogleDriveService was called with args: {mock_gds_class.call_args}"
                )


# ---------------------------------------------------------------------------
# Test 6: email_template_service._load_from_google_drive() — should use S3
# Requirement: 1.8
# ---------------------------------------------------------------------------

class TestEmailTemplateServiceBugCondition:
    """
    EmailTemplateService._load_from_google_drive() SHOULD download from S3
    when the template_file_id contains '/' (indicating an S3 key).

    On UNFIXED code these tests FAIL because GoogleDriveService is always used.
    """

    @settings(max_examples=15, deadline=None)
    @given(tenant=tenant_st, template_name=template_name_st)
    def test_load_template_does_not_use_google_drive_for_s3_tenant(self, tenant, template_name):
        """
        EXPECTED: _load_from_google_drive() for an S3 tenant with an S3 key
        does NOT instantiate GoogleDriveService. FAILS on unfixed code.

        **Validates: Requirements 1.8**
        """
        from services.email_template_service import EmailTemplateService

        # S3 key format: contains '/' indicating it's an S3 path
        s3_key = f"{tenant}/templates/uuid_{template_name}.html"

        mock_db = MagicMock()
        # Return a template record with an S3 key as file_id
        mock_db.execute_query.return_value = [{
            'template_file_id': s3_key,
            'template_content': None  # Force it to try downloading
        }]

        mock_gds_class = MagicMock()
        mock_gds_instance = MagicMock()
        mock_gds_instance.download_file_content.return_value = '<html>Template</html>'
        mock_gds_class.return_value = mock_gds_instance

        # DatabaseManager and GoogleDriveService are imported inside the method
        with patch('database.DatabaseManager', return_value=mock_db), \
             patch('google_drive_service.GoogleDriveService', mock_gds_class), \
             patch('services.parameter_service.ParameterService.get_param', return_value='s3_shared'):

            service = EmailTemplateService(administration=tenant)
            result = service._load_from_google_drive(template_name)

            # BUG ASSERTION: GoogleDriveService should NOT be called for S3 tenants
            # when the file_id is an S3 key (contains '/')
            assert not mock_gds_class.called, (
                f"BUG CONFIRMED: _load_from_google_drive() for S3 tenant '{tenant}' "
                f"with S3 key '{s3_key}' instantiated GoogleDriveService instead of "
                f"downloading from S3. GoogleDriveService was called with args: "
                f"{mock_gds_class.call_args}"
            )
