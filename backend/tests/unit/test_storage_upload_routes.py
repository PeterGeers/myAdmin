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

Requirements: 9.1–9.3
Reference: .kiro/specs/s3-shared-bucket-infrastructure/design.md
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


def _make_file(content=b'\x89PNG\r\n\x1a\n' + b'\x00' * 100,
               filename='logo.png',
               content_type='image/png'):
    """Create a file-like object for upload testing."""
    return (io.BytesIO(content), filename, content_type)


# ---------------------------------------------------------------------------
# Tests: Valid image upload → 200 with correct S3 key
# ---------------------------------------------------------------------------

class TestUploadLogoSuccess:
    """Test successful logo uploads."""

    def test_valid_png_upload_returns_200(self, client):
        """Valid PNG upload stores to correct S3 key and returns 200."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}), \
             patch('routes.storage.boto3') as mock_boto3, \
             patch('routes.storage.DatabaseManager') as mock_db_cls, \
             patch('routes.storage.ParameterService') as mock_ps_cls:

            mock_s3_client = MagicMock()
            mock_boto3.client.return_value = mock_s3_client
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
            assert result['key'] == 'TestTenant/branding/company_logo.png'

            # Verify S3 put_object was called
            mock_s3_client.put_object.assert_called_once()
            call_kwargs = mock_s3_client.put_object.call_args[1]
            assert call_kwargs['Bucket'] == 'myadmin-shared-dev'
            assert call_kwargs['Key'] == 'TestTenant/branding/company_logo.png'
            assert call_kwargs['ContentType'] == 'image/png'

            # Verify ParameterService.set_param was called
            mock_ps.set_param.assert_called_once_with(
                'tenant', tenant, 'branding', 'company_logo_s3_key',
                'TestTenant/branding/company_logo.png',
                value_type='string', created_by='user@test.com'
            )

    def test_valid_jpg_upload_returns_200(self, client):
        """Valid JPG upload stores to correct S3 key and returns 200."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}), \
             patch('routes.storage.boto3') as mock_boto3, \
             patch('routes.storage.DatabaseManager') as mock_db_cls, \
             patch('routes.storage.ParameterService') as mock_ps_cls:

            mock_s3_client = MagicMock()
            mock_boto3.client.return_value = mock_s3_client
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
            assert result['key'] == 'TestTenant/branding/company_logo.jpg'

            # Verify S3 key uses .jpg extension
            call_kwargs = mock_s3_client.put_object.call_args[1]
            assert call_kwargs['Key'] == 'TestTenant/branding/company_logo.jpg'
            assert call_kwargs['ContentType'] == 'image/jpeg'

    def test_valid_svg_upload_returns_200(self, client):
        """Valid SVG upload stores to correct S3 key and returns 200."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}), \
             patch('routes.storage.boto3') as mock_boto3, \
             patch('routes.storage.DatabaseManager') as mock_db_cls, \
             patch('routes.storage.ParameterService') as mock_ps_cls:

            mock_s3_client = MagicMock()
            mock_boto3.client.return_value = mock_s3_client
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
            assert result['key'] == 'TestTenant/branding/company_logo.svg'


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
