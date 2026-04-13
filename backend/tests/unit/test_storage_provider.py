"""
Unit tests for StorageProvider factory and implementations.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from storage.storage_provider import StorageProvider, get_storage_provider, VALID_PROVIDERS


def make_param_service(provider_type=None, extra=None):
    params = {}
    if provider_type:
        params[('storage', 'invoice_provider')] = provider_type
    if extra:
        params.update(extra)

    def get_param(ns, key, tenant=None, **kw):
        return params.get((ns, key))

    svc = Mock()
    svc.get_param = Mock(side_effect=get_param)
    svc.credential_service = None
    return svc


# ---------------------------------------------------------------------------
# Factory Tests
# ---------------------------------------------------------------------------

class TestStorageProviderFactory:

    def test_defaults_to_google_drive(self):
        ps = make_param_service(provider_type=None)
        provider = get_storage_provider('T1', ps)
        from storage.google_drive_storage import GoogleDriveStorage
        assert isinstance(provider, GoogleDriveStorage)

    def test_explicit_google_drive(self):
        ps = make_param_service(provider_type='google_drive')
        provider = get_storage_provider('T1', ps)
        from storage.google_drive_storage import GoogleDriveStorage
        assert isinstance(provider, GoogleDriveStorage)

    def test_s3_shared(self):
        ps = make_param_service(
            provider_type='s3_shared',
            extra={('storage', 's3_shared_bucket'): 'my-bucket'}
        )
        with patch('storage.s3_shared_storage.boto3'):
            provider = get_storage_provider('T1', ps)
        from storage.s3_shared_storage import S3SharedStorage
        assert isinstance(provider, S3SharedStorage)

    def test_s3_tenant(self):
        ps = make_param_service(
            provider_type='s3_tenant',
            extra={('storage', 's3_tenant_bucket'): 'tenant-bucket'}
        )
        cs = Mock()
        cs.get_credential = Mock(return_value={
            'aws_access_key_id': 'AK', 'aws_secret_access_key': 'SK'
        })
        ps.credential_service = cs
        with patch('storage.s3_tenant_storage.boto3'):
            provider = get_storage_provider('T1', ps)
        from storage.s3_tenant_storage import S3TenantStorage
        assert isinstance(provider, S3TenantStorage)

    def test_unknown_provider_raises(self):
        ps = make_param_service(provider_type='ftp')
        with pytest.raises(ValueError, match="Unknown storage provider: ftp"):
            get_storage_provider('T1', ps)


# ---------------------------------------------------------------------------
# GoogleDriveStorage Tests
# ---------------------------------------------------------------------------

class TestGoogleDriveStorage:

    def test_is_storage_provider(self):
        from storage.google_drive_storage import GoogleDriveStorage
        provider = GoogleDriveStorage('T1')
        assert isinstance(provider, StorageProvider)

    def test_lazy_init_service(self):
        from storage.google_drive_storage import GoogleDriveStorage
        provider = GoogleDriveStorage('T1')
        assert provider._service is None

    def test_upload_text(self):
        from storage.google_drive_storage import GoogleDriveStorage
        provider = GoogleDriveStorage('T1')
        mock_svc = Mock()
        mock_svc.upload_text_file = Mock(return_value={'id': 'file123'})
        provider._service = mock_svc

        ref = provider.upload(b'hello', 'test.html', {'folder_id': 'f1', 'mime_type': 'text/html'})
        assert ref == 'file123'
        mock_svc.upload_text_file.assert_called_once()

    def test_download(self):
        from storage.google_drive_storage import GoogleDriveStorage
        provider = GoogleDriveStorage('T1')
        mock_svc = Mock()
        mock_svc.download_file_content = Mock(return_value=b'content')
        provider._service = mock_svc

        assert provider.download('file123') == b'content'

    def test_delete_success(self):
        from storage.google_drive_storage import GoogleDriveStorage
        provider = GoogleDriveStorage('T1')
        mock_svc = Mock()
        mock_svc.service.files.return_value.delete.return_value.execute.return_value = None
        provider._service = mock_svc

        assert provider.delete('file123') is True

    def test_delete_failure(self):
        from storage.google_drive_storage import GoogleDriveStorage
        provider = GoogleDriveStorage('T1')
        mock_svc = Mock()
        mock_svc.service.files.return_value.delete.return_value.execute.side_effect = Exception("err")
        provider._service = mock_svc

        assert provider.delete('file123') is False


# ---------------------------------------------------------------------------
# S3SharedStorage Tests
# ---------------------------------------------------------------------------

class TestS3SharedStorage:

    def test_missing_bucket_raises(self):
        from storage.s3_shared_storage import S3SharedStorage
        ps = make_param_service()
        with patch.dict(os.environ, {'S3_SHARED_BUCKET': ''}, clear=False):
            with patch('storage.s3_shared_storage.boto3'):
                with pytest.raises(ValueError, match="S3 shared bucket not configured"):
                    S3SharedStorage('T1', ps)

    def test_upload_returns_key(self):
        from storage.s3_shared_storage import S3SharedStorage
        ps = make_param_service(extra={('storage', 's3_shared_bucket'): 'bucket'})
        with patch('storage.s3_shared_storage.boto3') as mock_boto:
            provider = S3SharedStorage('T1', ps)
            ref = provider.upload(b'data', 'invoice.pdf', {'reference_number': 'INV001'})
            assert ref.startswith('T1/INV001/')
            assert 'invoice.pdf' in ref
            mock_boto.client.return_value.put_object.assert_called_once()

    def test_is_storage_provider(self):
        from storage.s3_shared_storage import S3SharedStorage
        ps = make_param_service(extra={('storage', 's3_shared_bucket'): 'bucket'})
        with patch('storage.s3_shared_storage.boto3'):
            provider = S3SharedStorage('T1', ps)
        assert isinstance(provider, StorageProvider)


# ---------------------------------------------------------------------------
# S3TenantStorage Tests
# ---------------------------------------------------------------------------

class TestS3TenantStorage:

    def test_missing_bucket_raises(self):
        from storage.s3_tenant_storage import S3TenantStorage
        ps = make_param_service()
        with pytest.raises(ValueError, match="S3 tenant bucket not configured"):
            S3TenantStorage('T1', ps)

    def test_missing_credential_service_raises(self):
        from storage.s3_tenant_storage import S3TenantStorage
        ps = make_param_service(extra={('storage', 's3_tenant_bucket'): 'bucket'})
        ps.credential_service = None
        with pytest.raises(RuntimeError, match="CredentialService required"):
            S3TenantStorage('T1', ps)

    def test_missing_credentials_raises(self):
        from storage.s3_tenant_storage import S3TenantStorage
        ps = make_param_service(extra={('storage', 's3_tenant_bucket'): 'bucket'})
        cs = Mock()
        cs.get_credential = Mock(return_value=None)
        ps.credential_service = cs
        with pytest.raises(ValueError, match="S3 credentials not found"):
            S3TenantStorage('T1', ps)

    def test_creates_with_valid_credentials(self):
        from storage.s3_tenant_storage import S3TenantStorage
        ps = make_param_service(extra={('storage', 's3_tenant_bucket'): 'bucket'})
        cs = Mock()
        cs.get_credential = Mock(return_value={
            'aws_access_key_id': 'AK', 'aws_secret_access_key': 'SK'
        })
        ps.credential_service = cs
        with patch('storage.s3_tenant_storage.boto3'):
            provider = S3TenantStorage('T1', ps)
        assert isinstance(provider, StorageProvider)
