"""
Unit tests for Storage API routes (pre-signed URL endpoint).

Tests the GET /api/storage/presigned-url endpoint for:
- Valid tenant-prefixed key returns 200 with pre-signed URL
- Cross-tenant key returns 403
- Missing/invalid authentication returns 401
- S3_SHARED_BUCKET env var unset returns 503

Requirements: 7.1–7.6
Reference: .kiro/specs/s3-shared-bucket-infrastructure/design.md
"""

import sys
import os
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


# ---------------------------------------------------------------------------
# Tests: Valid tenant-prefixed key → 200 with pre-signed URL
# ---------------------------------------------------------------------------

class TestPresignedUrlSuccess:
    """Test successful pre-signed URL generation."""

    def test_valid_tenant_key_returns_200(self, client):
        """Valid tenant-prefixed key returns 200 with pre-signed URL."""
        tenant = 'TestTenant'
        fake_url = 'https://s3.amazonaws.com/bucket/TestTenant/invoices/doc.pdf?signature=abc'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}), \
             patch('routes.storage.boto3') as mock_boto3:

            mock_s3_client = MagicMock()
            mock_s3_client.generate_presigned_url.return_value = fake_url
            mock_boto3.client.return_value = mock_s3_client

            resp = client.get(
                '/api/storage/presigned-url?key=TestTenant/invoices/doc.pdf',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['url'] == fake_url
            assert data['expires_in'] == 300

            # Verify boto3 was called correctly
            mock_s3_client.generate_presigned_url.assert_called_once_with(
                'get_object',
                Params={
                    'Bucket': 'myadmin-shared-dev',
                    'Key': 'TestTenant/invoices/doc.pdf',
                    'ResponseContentDisposition': 'inline',
                    'ResponseContentType': 'application/pdf',
                },
                ExpiresIn=300,
            )


# ---------------------------------------------------------------------------
# Tests: Cross-tenant key → 403
# ---------------------------------------------------------------------------

class TestPresignedUrlCrossTenant:
    """Test cross-tenant access is denied."""

    def test_cross_tenant_key_returns_403(self, client):
        """Key not starting with tenant prefix returns 403."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}):

            resp = client.get(
                '/api/storage/presigned-url?key=OtherTenant/invoices/secret.pdf',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 403
            data = resp.get_json()
            assert 'error' in data
            assert data['error'] == 'Access denied'

    def test_empty_key_returns_403(self, client):
        """Empty key parameter returns 403."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}):

            resp = client.get(
                '/api/storage/presigned-url?key=',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 403

    def test_key_without_tenant_prefix_returns_403(self, client):
        """Key that doesn't start with tenant/ returns 403."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}):

            resp = client.get(
                '/api/storage/presigned-url?key=some-random-key.pdf',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: Missing authentication → 401
# ---------------------------------------------------------------------------

class TestPresignedUrlAuth:
    """Test authentication is required."""

    def test_missing_auth_header_returns_401(self, client):
        """Request without Authorization header returns 401."""
        resp = client.get(
            '/api/storage/presigned-url?key=TestTenant/invoices/doc.pdf',
            headers={'X-Tenant': 'TestTenant'},
        )

        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        """Request with invalid JWT token returns 401."""
        resp = client.get(
            '/api/storage/presigned-url?key=TestTenant/invoices/doc.pdf',
            headers={
                'Authorization': 'Bearer invalid-not-a-jwt',
                'X-Tenant': 'TestTenant',
            },
        )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests: S3_SHARED_BUCKET unset → 503
# ---------------------------------------------------------------------------

class TestPresignedUrlBucketUnset:
    """Test behavior when S3_SHARED_BUCKET is not configured."""

    def test_unset_bucket_returns_503(self, client):
        """Unset S3_SHARED_BUCKET env var returns 503."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'S3_SHARED_BUCKET': ''}, clear=False):

            resp = client.get(
                '/api/storage/presigned-url?key=TestTenant/invoices/doc.pdf',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 503
            data = resp.get_json()
            assert data['error'] == 'S3 storage not configured'

    def test_missing_bucket_env_returns_503(self, client):
        """Missing S3_SHARED_BUCKET env var (not in environ) returns 503."""
        tenant = 'TestTenant'

        mocks = _auth_mocks(tenant=tenant)
        # Remove S3_SHARED_BUCKET from environment entirely
        env_without_bucket = {k: v for k, v in os.environ.items() if k != 'S3_SHARED_BUCKET'}
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, env_without_bucket, clear=True):

            resp = client.get(
                '/api/storage/presigned-url?key=TestTenant/invoices/doc.pdf',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': tenant,
                },
            )

            assert resp.status_code == 503
            data = resp.get_json()
            assert data['error'] == 'S3 storage not configured'
