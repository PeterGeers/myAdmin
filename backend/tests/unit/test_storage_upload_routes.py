"""
Unit tests for Storage API routes (logo upload endpoint).

Tests the POST /api/storage/upload-logo endpoint for:
- Valid PNG upload returns 200 with correct S3 key
- Valid JPG upload returns 200 with correct S3 key
- Valid SVG upload returns 200 with correct S3 key
- Invalid file type returns 400
- File exceeding 2MB returns 400
- Missing file in request returns 400
- Missing authentication returns 401
- Asset registered with correct entity_type and entity_id
- Parameter updated with s3_key from asset service result

Requirements: 9.1–9.3
Reference: .kiro/specs/Common/image-asset-management/design.md
"""

import sys
import os
import io
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from flask import Flask
from routes.storage import storage_bp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a minimal Flask app with the storage blueprint."""
    app = Flask(__name__)
    app.register_blueprint(storage_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


def _auth_mocks(tenant='TestTenant'):
    """Patch stack for an authenticated user with tenant context."""
    return [
        patch('auth.cognito_utils.extract_user_credentials',
              return_value=('user@test.com', ['Finance_CRUD'], None)),
        patch('auth.role_cache.get_tenant_roles', return_value=['Finance_CRUD']),
        patch('auth.tenant_context.get_user_tenants', return_value=[tenant]),
        patch('auth.tenant_context.is_tenant_admin', return_value=False),
        patch('auth.tenant_context.get_current_tenant', return_value=tenant),
    ]


def _mock_store_result(s3_key, asset_id='ast_01TESTASSET123456'):
    """Create a successful store_and_register result."""
    return {
        'success': True,
        'asset': {
            'id': asset_id,
            's3_key': s3_key,
            'bucket': 'myadmin-shared-dev',
            'mime_type': 'image/png',
            'file_size': 108,
            'category': 'branding',
            'media_type': 'image',
            'original_filename': 'company_logo.png',
            'content_hash': 'abc123',
            'status': 'ACTIVE',
            'created_at': '2025-01-01 00:00:00',
            'reference_count': 1,
        },
        'duplicate_of': None,
    }


# ---------------------------------------------------------------------------
# Tests: Valid image upload → 200 with correct S3 key
# ---------------------------------------------------------------------------

class TestUploadLogoSuccess:
    """Test successful logo uploads."""

    def test_valid_png_upload_returns_200(self, client):
        """Valid PNG upload stores via asset service and returns 200."""
        tenant = 'TestTenant'
        expected_s3_key = 'TestTenant/branding/ast_01TEST_company_logo.png'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}), \
             patch('routes.storage.MediaAssetService') as mock_svc_cls, \
             patch('routes.storage.DatabaseManager') as mock_db_cls, \
             patch('routes.storage.ParameterService') as mock_ps_cls:

            mock_svc = MagicMock()
            mock_svc_cls.return_value = mock_svc
            mock_svc.store_and_register.return_value = _mock_store_result(expected_s3_key)
            mock_ps = MagicMock()
            mock_ps_cls.return_value = mock_ps

            data = {
                'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100),
                         'logo.png', 'image/png')
            }

            resp = client.post(
                '/api/storage/upload-logo',
                data=data,
                content_type='multipart/form-data',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 200
            result = resp.get_json()
            assert result['success'] is True
            assert result['key'] == expected_s3_key

            # Verify store_and_register was called with correct params
            mock_svc.store_and_register.assert_called_once_with(
                tenant=tenant,
                file_data=b'\x89PNG\r\n\x1a\n' + b'\x00' * 100,
                filename='company_logo.png',
                category='branding',
                entity_type='branding',
                entity_id=f'{tenant}:company_logo',
            )

            # Verify ParameterService.set_param was called with asset s3_key
            mock_ps.set_param.assert_called_once_with(
                'tenant', tenant, 'branding', 'company_logo_s3_key',
                expected_s3_key,
                value_type='string', created_by='user@test.com'
            )

    def test_valid_jpg_upload_returns_200(self, client):
        """Valid JPG upload stores via asset service and returns 200."""
        tenant = 'TestTenant'
        expected_s3_key = 'TestTenant/branding/ast_01TEST_company_logo.jpg'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}), \
             patch('routes.storage.MediaAssetService') as mock_svc_cls, \
             patch('routes.storage.DatabaseManager') as mock_db_cls, \
             patch('routes.storage.ParameterService') as mock_ps_cls:

            mock_svc = MagicMock()
            mock_svc_cls.return_value = mock_svc
            result_data = _mock_store_result(expected_s3_key)
            result_data['asset']['mime_type'] = 'image/jpeg'
            result_data['asset']['original_filename'] = 'company_logo.jpg'
            mock_svc.store_and_register.return_value = result_data
            mock_ps = MagicMock()
            mock_ps_cls.return_value = mock_ps

            data = {
                'file': (io.BytesIO(b'\xff\xd8\xff\xe0' + b'\x00' * 100),
                         'photo.jpg', 'image/jpeg')
            }

            resp = client.post(
                '/api/storage/upload-logo',
                data=data,
                content_type='multipart/form-data',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 200
            result = resp.get_json()
            assert result['success'] is True
            assert result['key'] == expected_s3_key

            # Verify store_and_register called with .jpg filename
            mock_svc.store_and_register.assert_called_once_with(
                tenant=tenant,
                file_data=b'\xff\xd8\xff\xe0' + b'\x00' * 100,
                filename='company_logo.jpg',
                category='branding',
                entity_type='branding',
                entity_id=f'{tenant}:company_logo',
            )

    def test_valid_svg_upload_returns_200(self, client):
        """Valid SVG upload stores via asset service and returns 200."""
        tenant = 'TestTenant'
        expected_s3_key = 'TestTenant/branding/ast_01TEST_company_logo.svg'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}), \
             patch('routes.storage.MediaAssetService') as mock_svc_cls, \
             patch('routes.storage.DatabaseManager') as mock_db_cls, \
             patch('routes.storage.ParameterService') as mock_ps_cls:

            mock_svc = MagicMock()
            mock_svc_cls.return_value = mock_svc
            result_data = _mock_store_result(expected_s3_key)
            result_data['asset']['mime_type'] = 'image/svg+xml'
            result_data['asset']['original_filename'] = 'company_logo.svg'
            mock_svc.store_and_register.return_value = result_data
            mock_ps = MagicMock()
            mock_ps_cls.return_value = mock_ps

            svg_content = b'<svg xmlns="http://www.w3.org/2000/svg"><circle/></svg>'
            data = {
                'file': (io.BytesIO(svg_content), 'logo.svg', 'image/svg+xml')
            }

            resp = client.post(
                '/api/storage/upload-logo',
                data=data,
                content_type='multipart/form-data',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 200
            result = resp.get_json()
            assert result['success'] is True
            assert result['key'] == expected_s3_key

            # Verify store_and_register called with .svg filename
            mock_svc.store_and_register.assert_called_once_with(
                tenant=tenant,
                file_data=svg_content,
                filename='company_logo.svg',
                category='branding',
                entity_type='branding',
                entity_id=f'{tenant}:company_logo',
            )


# ---------------------------------------------------------------------------
# Tests: Asset registration with correct entity_type and entity_id
# ---------------------------------------------------------------------------

class TestUploadLogoAssetRegistration:
    """Test that asset service is called with correct branding entity params."""

    def test_entity_type_is_branding(self, client):
        """store_and_register called with entity_type='branding'."""
        tenant = 'MyCompany'
        expected_s3_key = 'MyCompany/branding/ast_01TEST_company_logo.png'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}), \
             patch('routes.storage.MediaAssetService') as mock_svc_cls, \
             patch('routes.storage.DatabaseManager'), \
             patch('routes.storage.ParameterService') as mock_ps_cls:

            mock_svc = MagicMock()
            mock_svc_cls.return_value = mock_svc
            mock_svc.store_and_register.return_value = _mock_store_result(expected_s3_key)
            mock_ps_cls.return_value = MagicMock()

            data = {
                'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100),
                         'logo.png', 'image/png')
            }

            resp = client.post(
                '/api/storage/upload-logo',
                data=data,
                content_type='multipart/form-data',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 200
            call_kwargs = mock_svc.store_and_register.call_args[1]
            assert call_kwargs['entity_type'] == 'branding'
            assert call_kwargs['entity_id'] == f'{tenant}:company_logo'
            assert call_kwargs['category'] == 'branding'

    def test_asset_service_failure_returns_400(self, client):
        """When store_and_register fails, route returns 400."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}), \
             patch('routes.storage.MediaAssetService') as mock_svc_cls, \
             patch('routes.storage.DatabaseManager'), \
             patch('routes.storage.ParameterService') as mock_ps_cls:

            mock_svc = MagicMock()
            mock_svc_cls.return_value = mock_svc
            mock_svc.store_and_register.return_value = {
                'success': False,
                'error': 'S3 upload failed',
            }
            mock_ps_cls.return_value = MagicMock()

            data = {
                'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100),
                         'logo.png', 'image/png')
            }

            resp = client.post(
                '/api/storage/upload-logo',
                data=data,
                content_type='multipart/form-data',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 400
            result = resp.get_json()
            assert result['success'] is False
            assert 'S3 upload failed' in result['error']


# ---------------------------------------------------------------------------
# Tests: Invalid file type → 400
# ---------------------------------------------------------------------------

class TestUploadLogoInvalidType:
    """Test invalid file type rejection."""

    def test_text_file_returns_400(self, client):
        """Text/plain file type returns 400."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}):

            data = {
                'file': (io.BytesIO(b'hello world'), 'file.txt', 'text/plain')
            }

            resp = client.post(
                '/api/storage/upload-logo',
                data=data,
                content_type='multipart/form-data',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 400
            result = resp.get_json()
            assert result['success'] is False
            assert 'Invalid file type' in result['error']

    def test_pdf_file_returns_400(self, client):
        """PDF file type returns 400."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}):

            data = {
                'file': (io.BytesIO(b'%PDF-1.4'), 'doc.pdf', 'application/pdf')
            }

            resp = client.post(
                '/api/storage/upload-logo',
                data=data,
                content_type='multipart/form-data',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 400
            result = resp.get_json()
            assert result['success'] is False
            assert 'Invalid file type' in result['error']


# ---------------------------------------------------------------------------
# Tests: File exceeding 2MB → 400
# ---------------------------------------------------------------------------

class TestUploadLogoTooLarge:
    """Test file size limit enforcement."""

    def test_file_over_2mb_returns_400(self, client):
        """File exceeding 2MB returns 400."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}):

            # Create a file just over 2MB
            large_content = b'\x89PNG\r\n\x1a\n' + b'\x00' * (2 * 1024 * 1024 + 1)
            data = {
                'file': (io.BytesIO(large_content), 'big_logo.png', 'image/png')
            }

            resp = client.post(
                '/api/storage/upload-logo',
                data=data,
                content_type='multipart/form-data',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 400
            result = resp.get_json()
            assert result['success'] is False
            assert '2MB' in result['error']


# ---------------------------------------------------------------------------
# Tests: Missing file in request → 400
# ---------------------------------------------------------------------------

class TestUploadLogoMissingFile:
    """Test missing file handling."""

    def test_no_file_field_returns_400(self, client):
        """Request without 'file' field returns 400."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}):

            resp = client.post(
                '/api/storage/upload-logo',
                data={},
                content_type='multipart/form-data',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 400
            result = resp.get_json()
            assert result['success'] is False
            assert 'No file provided' in result['error']

    def test_empty_filename_returns_400(self, client):
        """File with empty filename returns 400."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}):

            data = {
                'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n'), '', 'image/png')
            }

            resp = client.post(
                '/api/storage/upload-logo',
                data=data,
                content_type='multipart/form-data',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 400
            result = resp.get_json()
            assert result['success'] is False
            assert 'No file selected' in result['error']


# ---------------------------------------------------------------------------
# Tests: Missing authentication → 401
# ---------------------------------------------------------------------------

class TestUploadLogoAuth:
    """Test authentication is required."""

    def test_missing_auth_header_returns_401(self, client):
        """Request without Authorization header returns 401."""
        data = {
            'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100),
                     'logo.png', 'image/png')
        }

        resp = client.post(
            '/api/storage/upload-logo',
            data=data,
            content_type='multipart/form-data',
            headers={'X-Tenant': 'TestTenant'},
        )

        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        """Request with invalid JWT token returns 401."""
        data = {
            'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100),
                     'logo.png', 'image/png')
        }

        resp = client.post(
            '/api/storage/upload-logo',
            data=data,
            content_type='multipart/form-data',
            headers={
                'Authorization': 'Bearer invalid-not-a-jwt',
                'X-Tenant': 'TestTenant',
            },
        )

        assert resp.status_code == 401
