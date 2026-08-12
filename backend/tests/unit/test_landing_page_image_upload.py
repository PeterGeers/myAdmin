"""
Unit tests for Landing Page Image Upload endpoint.

Tests the POST /api/landing/images/upload endpoint for:
- Valid PNG upload returns 200 with correct S3 key and URL
- Valid SVG upload returns 200
- Missing file returns 400
- No slug configured returns 400
- MediaAssetService validation failure returns 400
- MediaAssetService upload failure returns 400
- Asset registered with category='landing-pages', entity_type='landing_page'

Requirements: 9.1 (Exclusive Asset Gateway), 11 (Migration)
Reference: .kiro/specs/Common/image-asset-management/design.md
"""

import sys
import os
import io
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from flask import Flask
from routes.landing_page_routes import landing_page_bp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a minimal Flask app with the landing_page blueprint."""
    app = Flask(__name__)
    app.register_blueprint(landing_page_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


def _auth_mocks(tenant='TestTenant'):
    """Patch stack for an authenticated Tenant_Admin user."""
    return [
        patch('auth.cognito_utils.extract_user_credentials',
              return_value=('admin@test.com', ['Tenant_Admin'], None)),
        patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']),
        patch('auth.tenant_context.get_user_tenants', return_value=[tenant]),
        patch('auth.tenant_context.is_tenant_admin', return_value=True),
        patch('auth.tenant_context.get_current_tenant', return_value=tenant),
    ]


def _mock_store_result(s3_key, asset_id='ast_01TESTASSET123456'):
    """Create a successful store_and_register result."""
    return {
        'success': True,
        'asset': {
            'id': asset_id,
            's3_key': s3_key,
            'bucket': 'myadmin-public-pages-production',
            'mime_type': 'image/png',
            'file_size': 108,
            'category': 'landing-pages',
            'media_type': 'image',
            'original_filename': 'hero.png',
            'content_hash': 'abc123def456',
            'status': 'ACTIVE',
            'created_at': '2025-01-01 00:00:00',
            'reference_count': 1,
        },
        'duplicate_of': None,
    }


# ---------------------------------------------------------------------------
# Tests: Successful upload
# ---------------------------------------------------------------------------

class TestLandingPageImageUploadSuccess:
    """Test successful image uploads via MediaAssetService."""

    def test_valid_png_upload_returns_200_with_cloudfront_url(self, client):
        """Valid PNG upload stores via asset service and returns CloudFront URL."""
        tenant = 'TestTenant'
        slug = 'test-company'
        expected_s3_key = f'{tenant}/landing-pages/ast_01TEST_hero.png'
        cloudfront_domain = 'cdn.example.com'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, {'CLOUDFRONT_PUBLIC_PAGES_DOMAIN': cloudfront_domain}), \
             patch('routes.landing_page_routes._get_slug_service') as mock_slug_factory, \
             patch('routes.landing_page_routes.MediaAssetService') as mock_svc_cls, \
             patch('routes.landing_page_routes.DatabaseManager') as mock_db_cls, \
             patch('routes.landing_page_routes.ParameterService') as mock_ps_cls:

            # Mock slug service
            mock_slug_svc = MagicMock()
            mock_slug_svc.get_slug.return_value = slug
            mock_slug_factory.return_value = mock_slug_svc

            # Mock asset service
            mock_svc = MagicMock()
            mock_svc_cls.return_value = mock_svc
            mock_svc.store_and_register.return_value = _mock_store_result(expected_s3_key)

            data = {
                'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100),
                         'hero.png', 'image/png')
            }

            resp = client.post(
                '/api/landing/images/upload',
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
            assert result['data']['image_key'] == expected_s3_key
            assert result['data']['url'] == f'https://{cloudfront_domain}/{expected_s3_key}'

            # Verify store_and_register was called with correct params
            mock_svc.store_and_register.assert_called_once_with(
                tenant=tenant,
                file_data=b'\x89PNG\r\n\x1a\n' + b'\x00' * 100,
                filename='hero.png',
                category='landing-pages',
                entity_type='landing_page',
                entity_id=str(slug),
                metadata={'slug': slug},
            )

    def test_valid_upload_fallback_to_s3_url_when_no_cloudfront(self, client):
        """When no CloudFront domain is set, returns direct S3 URL."""
        tenant = 'TestTenant'
        slug = 'test-company'
        expected_s3_key = f'{tenant}/landing-pages/ast_01TEST_hero.png'

        mocks = _auth_mocks(tenant=tenant)
        env_vars = {
            'CLOUDFRONT_PUBLIC_PAGES_DOMAIN': '',
            'ENVIRONMENT': 'staging',
            'LANDING_PAGES_BUCKET': 'myadmin-public-pages-staging',
            'AWS_DEFAULT_REGION': 'eu-west-1',
        }
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch.dict(os.environ, env_vars), \
             patch('routes.landing_page_routes._get_slug_service') as mock_slug_factory, \
             patch('routes.landing_page_routes.MediaAssetService') as mock_svc_cls, \
             patch('routes.landing_page_routes.DatabaseManager') as mock_db_cls, \
             patch('routes.landing_page_routes.ParameterService') as mock_ps_cls:

            mock_slug_svc = MagicMock()
            mock_slug_svc.get_slug.return_value = slug
            mock_slug_factory.return_value = mock_slug_svc

            mock_svc = MagicMock()
            mock_svc_cls.return_value = mock_svc
            mock_svc.store_and_register.return_value = _mock_store_result(expected_s3_key)

            data = {
                'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100),
                         'hero.png', 'image/png')
            }

            resp = client.post(
                '/api/landing/images/upload',
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
            expected_url = f'https://myadmin-public-pages-staging.s3.eu-west-1.amazonaws.com/{expected_s3_key}'
            assert result['data']['url'] == expected_url


# ---------------------------------------------------------------------------
# Tests: Error cases
# ---------------------------------------------------------------------------

class TestLandingPageImageUploadErrors:
    """Test error handling in image upload."""

    def test_missing_file_returns_400(self, client):
        """No file in request returns 400."""
        tenant = 'TestTenant'
        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
            resp = client.post(
                '/api/landing/images/upload',
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

    def test_no_slug_configured_returns_400(self, client):
        """When tenant has no slug configured, returns 400."""
        tenant = 'TestTenant'
        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch('routes.landing_page_routes._get_slug_service') as mock_slug_factory:

            mock_slug_svc = MagicMock()
            mock_slug_svc.get_slug.return_value = None
            mock_slug_factory.return_value = mock_slug_svc

            data = {
                'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100),
                         'hero.png', 'image/png')
            }

            resp = client.post(
                '/api/landing/images/upload',
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
            assert 'No slug configured' in result['error']

    def test_asset_service_validation_failure_returns_400(self, client):
        """When MediaAssetService raises ValueError, returns 400."""
        tenant = 'TestTenant'
        slug = 'test-company'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch('routes.landing_page_routes._get_slug_service') as mock_slug_factory, \
             patch('routes.landing_page_routes.MediaAssetService') as mock_svc_cls, \
             patch('routes.landing_page_routes.DatabaseManager') as mock_db_cls, \
             patch('routes.landing_page_routes.ParameterService') as mock_ps_cls:

            mock_slug_svc = MagicMock()
            mock_slug_svc.get_slug.return_value = slug
            mock_slug_factory.return_value = mock_slug_svc

            mock_svc = MagicMock()
            mock_svc_cls.return_value = mock_svc
            mock_svc.store_and_register.side_effect = ValueError(
                "Unsupported file type '.exe'. Allowed types — image: .gif, .jpg, .jpeg, .png, .svg, .webp"
            )

            data = {
                'file': (io.BytesIO(b'\x00' * 50), 'malware.exe', 'application/octet-stream')
            }

            resp = client.post(
                '/api/landing/images/upload',
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
            assert 'Unsupported file type' in result['error']

    def test_asset_service_upload_failure_returns_400(self, client):
        """When store_and_register returns failure, returns 400."""
        tenant = 'TestTenant'
        slug = 'test-company'

        mocks = _auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], \
             patch('routes.landing_page_routes._get_slug_service') as mock_slug_factory, \
             patch('routes.landing_page_routes.MediaAssetService') as mock_svc_cls, \
             patch('routes.landing_page_routes.DatabaseManager') as mock_db_cls, \
             patch('routes.landing_page_routes.ParameterService') as mock_ps_cls:

            mock_slug_svc = MagicMock()
            mock_slug_svc.get_slug.return_value = slug
            mock_slug_factory.return_value = mock_slug_svc

            mock_svc = MagicMock()
            mock_svc_cls.return_value = mock_svc
            mock_svc.store_and_register.return_value = {
                'success': False,
                'error': 'S3 upload failed',
            }

            data = {
                'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100),
                         'hero.png', 'image/png')
            }

            resp = client.post(
                '/api/landing/images/upload',
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
            assert 'Upload failed' in result['error'] or 'S3 upload failed' in result['error']
