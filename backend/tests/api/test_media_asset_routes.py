"""
API tests for media_asset_routes.py

Tests all media asset endpoints: upload, get, search, attach/detach, replace,
dashboard, scan, approve-delete, duplicates, retention settings, force-delete,
and cross-tenant admin stats.

Covers happy path, error cases, and permission checks.

Reference: .kiro/specs/Common/image-asset-management/design.md
"""
import io
import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def asset_auth():
    """Mock authentication with full storage permissions (Administrators has wildcard)."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Administrators']):
        mock_creds.return_value = ('test@example.com', ['Administrators'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


@pytest.fixture
def asset_auth_sysadmin():
    """Mock authentication with sysadmin + wildcard (admin_manage) permissions."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Administrators']):
        mock_creds.return_value = ('admin@myadmin.com', ['Administrators'], None)
        yield {
            'Authorization': 'Bearer sysadmin-token',
            'X-Tenant': 'test-tenant',
        }


# ============================================================================
# Regular User Endpoints (storage_write / storage_read)
# ============================================================================


class TestUploadAsset:
    """Tests for POST /api/media-assets/upload."""

    def test_upload_success(self, client, asset_auth):
        """Successful file upload returns 201 with asset data."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.store_and_register.return_value = {
                'success': True,
                'asset': {
                    'asset_id': 'ast_123',
                    'original_filename': 'test.png',
                    'category': 'branding',
                    'status': 'active',
                },
                'duplicate_of': None,
            }
            mock_svc_factory.return_value = mock_svc

            data = {
                'file': (io.BytesIO(b'fake image data'), 'test.png'),
                'category': 'branding',
            }
            response = client.post(
                '/api/media-assets/upload',
                headers=asset_auth,
                data=data,
                content_type='multipart/form-data',
            )

        assert response.status_code == 201
        result = response.get_json()
        assert result['success'] is True
        assert result['asset']['asset_id'] == 'ast_123'

    def test_upload_missing_file_returns_400(self, client, asset_auth):
        """Upload without file field returns 400."""
        with patch('routes.media_asset_routes._get_service'):
            data = {'category': 'branding'}
            response = client.post(
                '/api/media-assets/upload',
                headers=asset_auth,
                data=data,
                content_type='multipart/form-data',
            )

        assert response.status_code == 400
        result = response.get_json()
        assert result['success'] is False
        assert 'No file' in result['error']

    def test_upload_missing_category_returns_400(self, client, asset_auth):
        """Upload without category returns 400."""
        with patch('routes.media_asset_routes._get_service'):
            data = {
                'file': (io.BytesIO(b'fake image data'), 'test.png'),
            }
            response = client.post(
                '/api/media-assets/upload',
                headers=asset_auth,
                data=data,
                content_type='multipart/form-data',
            )

        assert response.status_code == 400
        result = response.get_json()
        assert result['success'] is False
        assert 'Category' in result['error']


class TestGetAsset:
    """Tests for GET /api/media-assets/<asset_id>."""

    def test_get_asset_success(self, client, asset_auth):
        """Existing asset returns 200 with metadata."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.get_asset.return_value = {
                'success': True,
                'asset': {
                    'asset_id': 'ast_123',
                    'original_filename': 'logo.png',
                    'presigned_url': 'https://s3.example.com/signed',
                },
            }
            mock_svc_factory.return_value = mock_svc

            response = client.get('/api/media-assets/ast_123', headers=asset_auth)

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert result['asset']['asset_id'] == 'ast_123'

    def test_get_asset_not_found_returns_404(self, client, asset_auth):
        """Non-existent asset returns 404."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.get_asset.return_value = {
                'success': False,
                'error': 'Asset not found',
            }
            mock_svc_factory.return_value = mock_svc

            response = client.get('/api/media-assets/ast_nonexistent', headers=asset_auth)

        assert response.status_code == 404
        result = response.get_json()
        assert result['success'] is False


class TestAttachAsset:
    """Tests for POST /api/media-assets/<asset_id>/attach."""

    def test_attach_success(self, client, asset_auth):
        """Attach entity reference returns 200."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.attach.return_value = {
                'success': True,
                'reference_count': 1,
            }
            mock_svc_factory.return_value = mock_svc

            response = client.post(
                '/api/media-assets/ast_123/attach',
                headers=asset_auth,
                json={'entity_type': 'invoice', 'entity_id': 'inv_456'},
            )

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True

    def test_attach_missing_fields_returns_400(self, client, asset_auth):
        """Missing entity_type or entity_id returns 400."""
        with patch('routes.media_asset_routes._get_service'):
            response = client.post(
                '/api/media-assets/ast_123/attach',
                headers=asset_auth,
                json={'entity_type': 'invoice'},
            )

        assert response.status_code == 400
        result = response.get_json()
        assert result['success'] is False
        assert 'entity_type and entity_id are required' in result['error']

    def test_attach_no_body_returns_400(self, client, asset_auth):
        """Request without JSON body returns 400."""
        with patch('routes.media_asset_routes._get_service'):
            response = client.post(
                '/api/media-assets/ast_123/attach',
                headers=asset_auth,
                json={},
            )

        assert response.status_code == 400
        result = response.get_json()
        assert result['success'] is False


class TestDetachAsset:
    """Tests for POST /api/media-assets/<asset_id>/detach."""

    def test_detach_success(self, client, asset_auth):
        """Detach entity reference returns 200."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.detach.return_value = {
                'success': True,
                'asset': {'asset_id': 'ast_123', 'reference_count': 0},
            }
            mock_svc_factory.return_value = mock_svc

            response = client.post(
                '/api/media-assets/ast_123/detach',
                headers=asset_auth,
                json={'entity_type': 'invoice', 'entity_id': 'inv_456'},
            )

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True

    def test_detach_missing_fields_returns_400(self, client, asset_auth):
        """Missing entity_id returns 400."""
        with patch('routes.media_asset_routes._get_service'):
            response = client.post(
                '/api/media-assets/ast_123/detach',
                headers=asset_auth,
                json={'entity_type': 'invoice'},
            )

        assert response.status_code == 400
        result = response.get_json()
        assert result['success'] is False


class TestReplaceAsset:
    """Tests for POST /api/media-assets/replace."""

    def test_replace_success(self, client, asset_auth):
        """Successful replace returns 200."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.replace.return_value = {
                'success': True,
                'old_asset_id': 'ast_old',
                'new_asset_id': 'ast_new',
            }
            mock_svc_factory.return_value = mock_svc

            response = client.post(
                '/api/media-assets/replace',
                headers=asset_auth,
                json={
                    'entity_type': 'invoice',
                    'entity_id': 'inv_1',
                    'old_asset_id': 'ast_old',
                    'new_asset_id': 'ast_new',
                },
            )

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True

    def test_replace_missing_new_asset_id_returns_400(self, client, asset_auth):
        """Missing new_asset_id returns 400."""
        with patch('routes.media_asset_routes._get_service'):
            response = client.post(
                '/api/media-assets/replace',
                headers=asset_auth,
                json={
                    'entity_type': 'invoice',
                    'entity_id': 'inv_1',
                    'old_asset_id': 'ast_old',
                },
            )

        assert response.status_code == 400
        result = response.get_json()
        assert 'new_asset_id is required' in result['error']

    def test_replace_missing_entity_fields_returns_400(self, client, asset_auth):
        """Missing entity_type/entity_id returns 400."""
        with patch('routes.media_asset_routes._get_service'):
            response = client.post(
                '/api/media-assets/replace',
                headers=asset_auth,
                json={'new_asset_id': 'ast_new'},
            )

        assert response.status_code == 400
        result = response.get_json()
        assert 'entity_type and entity_id are required' in result['error']


class TestSearchAssets:
    """Tests for GET /api/media-assets/search."""

    def test_search_default_params(self, client, asset_auth):
        """Search with default params returns 200 with pagination."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.search_assets.return_value = {
                'success': True,
                'data': [],
                'pagination': {
                    'page': 1,
                    'page_size': 20,
                    'total': 0,
                    'total_pages': 0,
                },
            }
            mock_svc_factory.return_value = mock_svc

            response = client.get('/api/media-assets/search', headers=asset_auth)

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert 'pagination' in result

    def test_search_with_filters(self, client, asset_auth):
        """Search with category and query filters passes them to service."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.search_assets.return_value = {
                'success': True,
                'data': [{'asset_id': 'ast_1', 'original_filename': 'logo.png'}],
                'pagination': {'page': 1, 'page_size': 20, 'total': 1, 'total_pages': 1},
            }
            mock_svc_factory.return_value = mock_svc

            response = client.get(
                '/api/media-assets/search?q=logo&category=branding&page=1&page_size=10',
                headers=asset_auth,
            )

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert len(result['data']) == 1

        # Verify filters were passed to service
        call_args = mock_svc.search_assets.call_args
        filters = call_args[1]['filters'] if 'filters' in call_args[1] else call_args[0][1]
        assert filters['q'] == 'logo'
        assert filters['category'] == 'branding'


# ============================================================================
# Tenant Admin Endpoints (storage_manage)
# ============================================================================


class TestDashboard:
    """Tests for GET /api/media-assets/dashboard."""

    def test_dashboard_success(self, client, asset_auth):
        """Dashboard returns summary stats."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.get_dashboard_stats.return_value = {
                'success': True,
                'data': {
                    'total_assets': 150,
                    'active_assets': 120,
                    'orphaned_assets': 5,
                    'total_bytes': 1048576,
                },
            }
            mock_svc_factory.return_value = mock_svc

            response = client.get('/api/media-assets/dashboard', headers=asset_auth)

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert 'data' in result
        assert result['data']['total_assets'] == 150


class TestTriggerScan:
    """Tests for POST /api/media-assets/scan."""

    def test_scan_returns_scan_id(self, client, asset_auth):
        """Trigger scan returns 202 with scan_id."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.run_reconciliation_with_progress.return_value = iter([])
            mock_svc_factory.return_value = mock_svc

            response = client.post(
                '/api/media-assets/scan',
                headers=asset_auth,
                content_type='application/json',
            )

        assert response.status_code == 202
        result = response.get_json()
        assert result['success'] is True
        assert 'scan_id' in result
        # scan_id should be a UUID format
        assert len(result['scan_id']) == 36


class TestApproveDelete:
    """Tests for POST /api/media-assets/approve-delete."""

    def test_approve_delete_success(self, client, asset_auth):
        """Approve deletion with valid asset_ids returns 200."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.delete_asset.return_value = {'success': True}
            mock_svc_factory.return_value = mock_svc

            response = client.post(
                '/api/media-assets/approve-delete',
                headers=asset_auth,
                json={'asset_ids': ['ast_1', 'ast_2']},
            )

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert result['deleted'] == 2
        assert result['skipped'] == 0

    def test_approve_delete_missing_asset_ids_returns_400(self, client, asset_auth):
        """Missing asset_ids returns 400."""
        with patch('routes.media_asset_routes._get_service'):
            response = client.post(
                '/api/media-assets/approve-delete',
                headers=asset_auth,
                json={'asset_ids': 'not-a-list'},
            )

        assert response.status_code == 400
        result = response.get_json()
        assert result['success'] is False
        assert 'asset_ids' in result['error']

    def test_approve_delete_partial_failure(self, client, asset_auth):
        """Some assets fail deletion — shows deleted + skipped counts."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.delete_asset.side_effect = [
                {'success': True},
                {'success': False, 'error': 'Has active references'},
            ]
            mock_svc_factory.return_value = mock_svc

            response = client.post(
                '/api/media-assets/approve-delete',
                headers=asset_auth,
                json={'asset_ids': ['ast_1', 'ast_2']},
            )

        assert response.status_code == 200
        result = response.get_json()
        assert result['deleted'] == 1
        assert result['skipped'] == 1


class TestListDuplicates:
    """Tests for GET /api/media-assets/duplicates."""

    def test_duplicates_success(self, client, asset_auth):
        """List duplicates returns grouped data."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.get_duplicate_groups.return_value = {
                'success': True,
                'data': [
                    {
                        'content_hash': 'abc123',
                        'count': 2,
                        'assets': [
                            {'asset_id': 'ast_1', 'original_filename': 'logo.png'},
                            {'asset_id': 'ast_2', 'original_filename': 'logo_copy.png'},
                        ],
                    }
                ],
            }
            mock_svc_factory.return_value = mock_svc

            response = client.get('/api/media-assets/duplicates', headers=asset_auth)

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert len(result['data']) == 1
        assert result['data'][0]['count'] == 2


class TestRetentionSettings:
    """Tests for GET/PUT /api/media-assets/retention-settings."""

    def test_get_retention_settings_success(self, client, asset_auth):
        """Get retention settings returns config with source indicators."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.get_retention_settings.return_value = {
                'success': True,
                'data': {
                    'branding_days': {'value': 365, 'source': 'default'},
                    'invoices_days': {'value': 2555, 'source': 'tenant_override'},
                },
            }
            mock_svc_factory.return_value = mock_svc

            response = client.get('/api/media-assets/retention-settings', headers=asset_auth)

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert 'data' in result
        assert 'branding_days' in result['data']

    def test_update_retention_settings_success(self, client, asset_auth):
        """Valid update returns 200 with updated keys."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.update_retention_settings.return_value = {
                'success': True,
                'updated': ['branding_days'],
            }
            mock_svc_factory.return_value = mock_svc

            response = client.put(
                '/api/media-assets/retention-settings',
                headers=asset_auth,
                json={'branding_days': 60},
            )

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert 'branding_days' in result['updated']

    def test_update_retention_settings_invalid_key_returns_400(self, client, asset_auth):
        """Invalid retention key raises ValueError → 400."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.update_retention_settings.side_effect = ValueError(
                "Invalid retention key: bogus_key"
            )
            mock_svc_factory.return_value = mock_svc

            response = client.put(
                '/api/media-assets/retention-settings',
                headers=asset_auth,
                json={'bogus_key': 999},
            )

        assert response.status_code == 400
        result = response.get_json()
        assert result['success'] is False
        assert 'Invalid retention key' in result['error']


# ============================================================================
# System Admin Endpoints (admin_manage)
# ============================================================================


class TestForceDelete:
    """Tests for POST /api/media-assets/force-delete."""

    def test_force_delete_success(self, client, asset_auth_sysadmin):
        """Sysadmin force-delete returns 200."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.force_delete.return_value = {
                'success': True,
                'asset_id': 'ast_123',
                'reference_count': 2,
                'operator': 'admin@myadmin.com',
                'reason': 'GDPR compliance',
            }
            mock_svc_factory.return_value = mock_svc

            response = client.post(
                '/api/media-assets/force-delete',
                headers=asset_auth_sysadmin,
                json={
                    'asset_id': 'ast_123',
                    'reason': 'GDPR compliance',
                },
            )

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert result['asset_id'] == 'ast_123'

    def test_force_delete_missing_asset_id_returns_400(self, client, asset_auth_sysadmin):
        """Missing asset_id returns 400."""
        with patch('routes.media_asset_routes._get_service'):
            response = client.post(
                '/api/media-assets/force-delete',
                headers=asset_auth_sysadmin,
                json={'reason': 'GDPR compliance'},
            )

        assert response.status_code == 400
        result = response.get_json()
        assert result['success'] is False
        assert 'asset_id is required' in result['error']

    def test_force_delete_missing_reason_returns_400(self, client, asset_auth_sysadmin):
        """Missing reason returns 400."""
        with patch('routes.media_asset_routes._get_service'):
            response = client.post(
                '/api/media-assets/force-delete',
                headers=asset_auth_sysadmin,
                json={'asset_id': 'ast_123'},
            )

        assert response.status_code == 400
        result = response.get_json()
        assert result['success'] is False
        assert 'reason is required' in result['error']


class TestAdminTenants:
    """Tests for GET /api/media-assets/admin/tenants."""

    def test_admin_tenants_success(self, client, asset_auth_sysadmin):
        """Cross-tenant stats returns aggregated data."""
        with patch('routes.media_asset_routes._get_service') as mock_svc_factory:
            mock_svc = MagicMock()
            mock_db = MagicMock()
            mock_db.execute_query.return_value = [
                {'tenant': 'tenant-a', 'total_assets': 100, 'total_bytes': 5242880},
                {'tenant': 'tenant-b', 'total_assets': 50, 'total_bytes': 2621440},
            ]
            mock_svc.db = mock_db
            mock_svc_factory.return_value = mock_svc

            response = client.get('/api/media-assets/admin/tenants', headers=asset_auth_sysadmin)

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert len(result['data']) == 2
        assert result['data'][0]['tenant'] == 'tenant-a'
        assert result['data'][0]['total_assets'] == 100


# ============================================================================
# Permission / Auth Enforcement
# ============================================================================


class TestAuthEnforcement:
    """Verify unauthenticated requests are rejected."""

    def test_upload_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated upload request should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}',
        }
        with patch(
            'auth.cognito_utils.extract_user_credentials',
            return_value=(None, None, auth_error),
        ):
            data = {
                'file': (io.BytesIO(b'data'), 'test.png'),
                'category': 'branding',
            }
            response = client.post(
                '/api/media-assets/upload',
                data=data,
                content_type='multipart/form-data',
            )

        assert response.status_code in (401, 403)

    def test_get_asset_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated get request should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}',
        }
        with patch(
            'auth.cognito_utils.extract_user_credentials',
            return_value=(None, None, auth_error),
        ):
            response = client.get('/api/media-assets/ast_123')

        assert response.status_code in (401, 403)

    def test_force_delete_non_admin_returns_403(self, client, mock_auth):
        """Non-admin user cannot force-delete (requires admin_manage)."""
        response = client.post(
            '/api/media-assets/force-delete',
            headers=mock_auth,
            json={'asset_id': 'ast_123', 'reason': 'test'},
        )

        assert response.status_code == 403

    def test_admin_tenants_non_admin_returns_403(self, client, mock_auth):
        """Non-admin user cannot access cross-tenant stats."""
        response = client.get(
            '/api/media-assets/admin/tenants',
            headers=mock_auth,
        )

        assert response.status_code == 403
