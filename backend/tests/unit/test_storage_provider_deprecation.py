"""
Unit tests for StorageProvider: internal methods and ABC contract.

Verifies:
- _upload_raw() works correctly
- _delete_raw() works correctly
- ABC enforces abstract method implementation
- Deprecated upload()/delete() methods no longer exist

Requirements: Task 7.3
Reference: .kiro/specs/Common/image-asset-management/design.md
"""

import os
import sys
import warnings

import pytest
from unittest.mock import Mock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


def make_param_service(extra=None):
    """Create a mock ParameterService."""
    params = {}
    if extra:
        params.update(extra)

    def get_param(ns, key, tenant=None, **kw):
        return params.get((ns, key))

    svc = Mock()
    svc.get_param = Mock(side_effect=get_param)
    svc.credential_service = None
    return svc


# ---------------------------------------------------------------------------
# S3SharedStorage: Internal Method Tests
# ---------------------------------------------------------------------------

class TestS3SharedStorageInternalMethods:
    """Tests that _upload_raw() and _delete_raw() work correctly."""

    def _make_provider(self):
        from storage.s3_shared_storage import S3SharedStorage
        ps = make_param_service(extra={('storage', 's3_shared_bucket'): 'bucket'})
        with patch('storage.s3_shared_storage.boto3') as mock_boto:
            provider = S3SharedStorage('T1', ps)
        return provider

    def test_upload_raw_no_deprecation_warning(self):
        """_upload_raw() does NOT emit a deprecation warning."""
        provider = self._make_provider()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = provider._upload_raw(b'data', 'T1/invoices/key.pdf', 'application/pdf')

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) == 0
        assert result is True

    def test_upload_raw_calls_put_object(self):
        """_upload_raw() calls S3 put_object with correct params."""
        from storage.s3_shared_storage import S3SharedStorage
        ps = make_param_service(extra={('storage', 's3_shared_bucket'): 'my-bucket'})
        with patch('storage.s3_shared_storage.boto3') as mock_boto:
            provider = S3SharedStorage('T1', ps)
            provider._upload_raw(b'content', 'path/to/file.txt', 'text/plain')

            mock_boto.client.return_value.put_object.assert_called_once_with(
                Bucket='my-bucket',
                Key='path/to/file.txt',
                Body=b'content',
                ContentType='text/plain',
            )

    def test_delete_raw_no_deprecation_warning(self):
        """_delete_raw() does NOT emit a deprecation warning."""
        provider = self._make_provider()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = provider._delete_raw('some/key.pdf')

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) == 0
        assert result is True

    def test_delete_raw_calls_delete_object(self):
        """_delete_raw() calls S3 delete_object with correct params."""
        from storage.s3_shared_storage import S3SharedStorage
        ps = make_param_service(extra={('storage', 's3_shared_bucket'): 'my-bucket'})
        with patch('storage.s3_shared_storage.boto3') as mock_boto:
            provider = S3SharedStorage('T1', ps)
            provider._delete_raw('path/to/file.txt')

            mock_boto.client.return_value.delete_object.assert_called_once_with(
                Bucket='my-bucket',
                Key='path/to/file.txt',
            )

    def test_delete_raw_returns_false_on_client_error(self):
        """_delete_raw() returns False when ClientError occurs."""
        from storage.s3_shared_storage import S3SharedStorage
        from botocore.exceptions import ClientError
        ps = make_param_service(extra={('storage', 's3_shared_bucket'): 'my-bucket'})
        with patch('storage.s3_shared_storage.boto3') as mock_boto:
            provider = S3SharedStorage('T1', ps)
            mock_boto.client.return_value.delete_object.side_effect = ClientError(
                {'Error': {'Code': '404', 'Message': 'Not Found'}}, 'DeleteObject'
            )
            result = provider._delete_raw('missing/key.pdf')

        assert result is False

    def test_no_upload_method(self):
        """S3SharedStorage no longer has a public upload() method."""
        provider = self._make_provider()
        # upload should not be defined on the instance (only inherited from ABC if it existed)
        assert not hasattr(provider, 'upload') or 'upload' not in type(provider).__dict__

    def test_no_delete_method(self):
        """S3SharedStorage no longer has a public delete() method."""
        provider = self._make_provider()
        assert not hasattr(provider, 'delete') or 'delete' not in type(provider).__dict__


# ---------------------------------------------------------------------------
# S3TenantStorage: Internal Method Tests
# ---------------------------------------------------------------------------

class TestS3TenantStorageInternalMethods:
    """Tests that _upload_raw() and _delete_raw() work correctly."""

    def _make_provider(self):
        from storage.s3_tenant_storage import S3TenantStorage
        ps = make_param_service(extra={('storage', 's3_tenant_bucket'): 'tenant-bucket'})
        cs = Mock()
        cs.get_credential = Mock(return_value={
            'aws_access_key_id': 'AK', 'aws_secret_access_key': 'SK'
        })
        ps.credential_service = cs
        with patch('storage.s3_tenant_storage.boto3'):
            provider = S3TenantStorage('T1', ps)
        return provider

    def test_upload_raw_no_deprecation_warning(self):
        """_upload_raw() does NOT emit a deprecation warning."""
        provider = self._make_provider()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = provider._upload_raw(b'data', 'T1/key.pdf', 'application/pdf')

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) == 0
        assert result is True

    def test_delete_raw_no_deprecation_warning(self):
        """_delete_raw() does NOT emit a deprecation warning."""
        provider = self._make_provider()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = provider._delete_raw('some/key.pdf')

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) == 0
        assert result is True

    def test_no_upload_method(self):
        """S3TenantStorage no longer has a public upload() method."""
        provider = self._make_provider()
        assert not hasattr(provider, 'upload') or 'upload' not in type(provider).__dict__

    def test_no_delete_method(self):
        """S3TenantStorage no longer has a public delete() method."""
        provider = self._make_provider()
        assert not hasattr(provider, 'delete') or 'delete' not in type(provider).__dict__


# ---------------------------------------------------------------------------
# StorageProvider ABC Contract Tests
# ---------------------------------------------------------------------------

class TestStorageProviderABC:
    """Tests that the ABC enforces the expected interface."""

    def test_cannot_instantiate_without_abstract_methods(self):
        """StorageProvider requires all abstract methods to be implemented."""
        from storage.storage_provider import StorageProvider

        with pytest.raises(TypeError):
            StorageProvider()

    def test_concrete_implementation_needs_all_abstracts(self):
        """A subclass missing abstract methods cannot be instantiated."""
        from storage.storage_provider import StorageProvider

        class IncompleteProvider(StorageProvider):
            def download(self, reference):
                return b''

            def list_files(self, path):
                return []

            # Missing _upload_raw and _delete_raw

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_complete_implementation_instantiates(self):
        """A subclass implementing all abstract methods can be instantiated."""
        from storage.storage_provider import StorageProvider

        class CompleteProvider(StorageProvider):
            def download(self, reference):
                return b''

            def list_files(self, path):
                return []

            def _upload_raw(self, file_data, key, content_type):
                return True

            def _delete_raw(self, key):
                return True

        provider = CompleteProvider()
        assert isinstance(provider, StorageProvider)

    def test_no_upload_on_abc(self):
        """StorageProvider ABC does not have upload() method."""
        from storage.storage_provider import StorageProvider
        assert not hasattr(StorageProvider, 'upload')

    def test_no_delete_on_abc(self):
        """StorageProvider ABC does not have delete() method."""
        from storage.storage_provider import StorageProvider
        assert not hasattr(StorageProvider, 'delete')
