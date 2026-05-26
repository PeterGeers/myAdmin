"""
Unit tests for logo_resolver.py — provider-aware logo resolution.

Requirements: 8.1–8.7
Reference: .kiro/specs/s3-shared-bucket-infrastructure/design.md §Provider-Aware Logo Resolution
"""

import sys
import os
import base64
import pytest
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.logo_resolver import resolve_tenant_logo


def make_param_service(provider=None, logo_file_id=None, s3_key=None):
    """Create a mock parameter service with configurable return values."""
    params = {}
    if provider is not None:
        params[('storage', 'invoice_provider')] = provider
    if logo_file_id is not None:
        params[('str_branding', 'company_logo_file_id')] = logo_file_id
    if s3_key is not None:
        params[('str_branding', 'company_logo_s3_key')] = s3_key

    def get_param(ns, key, tenant=None, **kw):
        return params.get((ns, key))

    svc = Mock()
    svc.get_param = Mock(side_effect=get_param)
    return svc


class TestGoogleDriveProvider:
    """Tests for Google Drive logo resolution (provider='google_drive' or None)."""

    @patch('services.logo_resolver.requests.get')
    def test_google_drive_returns_base64_data_uri(self, mock_get):
        """Google Drive provider fetches logo and returns base64 data URI."""
        image_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = image_bytes
        mock_response.headers = {'Content-Type': 'image/png'}
        mock_get.return_value = mock_response

        ps = make_param_service(provider='google_drive', logo_file_id='abc123')
        result = resolve_tenant_logo('TestTenant', 'str_branding', ps)

        expected_b64 = base64.b64encode(image_bytes).decode('utf-8')
        assert result == f'data:image/png;base64,{expected_b64}'
        mock_get.assert_called_once_with(
            'https://lh3.googleusercontent.com/d/abc123=w600', timeout=10
        )

    @patch('services.logo_resolver.requests.get')
    def test_default_provider_uses_google_drive(self, mock_get):
        """When provider is None (default), falls back to Google Drive behavior."""
        image_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = image_bytes
        mock_response.headers = {'Content-Type': 'image/jpeg'}
        mock_get.return_value = mock_response

        ps = make_param_service(provider=None, logo_file_id='drive_id_456')
        result = resolve_tenant_logo('TestTenant', 'str_branding', ps)

        expected_b64 = base64.b64encode(image_bytes).decode('utf-8')
        assert result == f'data:image/jpeg;base64,{expected_b64}'

    @patch('services.logo_resolver.requests.get')
    def test_google_drive_non_200_returns_none(self, mock_get):
        """Google Drive fetch failure (non-200 response) returns None."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        ps = make_param_service(provider='google_drive', logo_file_id='bad_id')
        result = resolve_tenant_logo('TestTenant', 'str_branding', ps)

        assert result is None

    def test_google_drive_missing_file_id_returns_none(self):
        """Missing company_logo_file_id returns None."""
        ps = make_param_service(provider='google_drive', logo_file_id=None)
        result = resolve_tenant_logo('TestTenant', 'str_branding', ps)

        assert result is None


class TestS3Provider:
    """Tests for S3 logo resolution (provider='s3_shared' or 's3_tenant')."""

    @patch('services.logo_resolver.boto3')
    @patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'})
    def test_s3_shared_returns_base64_data_uri(self, mock_boto3):
        """S3 provider fetches logo from bucket and returns base64 data URI."""
        image_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 80
        mock_body = Mock()
        mock_body.read.return_value = image_bytes
        mock_s3_client = Mock()
        mock_s3_client.get_object.return_value = {
            'ContentType': 'image/png',
            'Body': mock_body
        }
        mock_boto3.client.return_value = mock_s3_client

        ps = make_param_service(provider='s3_shared', s3_key='TestTenant/branding/company_logo.png')
        result = resolve_tenant_logo('TestTenant', 'str_branding', ps)

        expected_b64 = base64.b64encode(image_bytes).decode('utf-8')
        assert result == f'data:image/png;base64,{expected_b64}'
        mock_s3_client.get_object.assert_called_once_with(
            Bucket='myadmin-shared-dev',
            Key='TestTenant/branding/company_logo.png'
        )

    @patch('services.logo_resolver.boto3')
    @patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'})
    def test_s3_tenant_returns_base64_data_uri(self, mock_boto3):
        """S3 tenant provider also works correctly."""
        image_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 60
        mock_body = Mock()
        mock_body.read.return_value = image_bytes
        mock_s3_client = Mock()
        mock_s3_client.get_object.return_value = {
            'ContentType': 'image/jpeg',
            'Body': mock_body
        }
        mock_boto3.client.return_value = mock_s3_client

        ps = make_param_service(provider='s3_tenant', s3_key='TestTenant/branding/logo.jpg')
        result = resolve_tenant_logo('TestTenant', 'str_branding', ps)

        expected_b64 = base64.b64encode(image_bytes).decode('utf-8')
        assert result == f'data:image/jpeg;base64,{expected_b64}'

    def test_s3_missing_logo_key_returns_none(self):
        """Missing company_logo_s3_key returns None."""
        ps = make_param_service(provider='s3_shared', s3_key=None)
        result = resolve_tenant_logo('TestTenant', 'str_branding', ps)

        assert result is None

    @patch.dict(os.environ, {'S3_SHARED_BUCKET': ''})
    def test_s3_missing_bucket_env_var_returns_none(self):
        """S3 provider with missing S3_SHARED_BUCKET env var returns None."""
        ps = make_param_service(provider='s3_shared', s3_key='TestTenant/branding/logo.png')
        result = resolve_tenant_logo('TestTenant', 'str_branding', ps)

        assert result is None

    @patch.dict(os.environ, {}, clear=False)
    def test_s3_unset_bucket_env_var_returns_none(self):
        """S3 provider with unset S3_SHARED_BUCKET env var returns None."""
        # Ensure the env var is not set
        os.environ.pop('S3_SHARED_BUCKET', None)
        ps = make_param_service(provider='s3_shared', s3_key='TestTenant/branding/logo.png')
        result = resolve_tenant_logo('TestTenant', 'str_branding', ps)

        assert result is None


class TestUnknownProvider:
    """Tests for unknown/unsupported provider values."""

    def test_unknown_provider_returns_none(self):
        """Unknown provider (e.g., 'dropbox') returns None."""
        ps = make_param_service(provider='dropbox')
        result = resolve_tenant_logo('TestTenant', 'str_branding', ps)

        assert result is None

    def test_another_unknown_provider_returns_none(self):
        """Another unknown provider (e.g., 'ftp') returns None."""
        ps = make_param_service(provider='ftp')
        result = resolve_tenant_logo('TestTenant', 'str_branding', ps)

        assert result is None
