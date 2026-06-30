"""
Unit tests for storage_resolver.py helper functions.

Tests resolve_storage_provider(), get_s3_storage(), list_s3_folders(),
and create_s3_folder() with various inputs including edge cases.

Requirements: 2.1, 2.2, 2.9
Reference: .kiro/specs/provider-aware-folder-routes/design.md
"""

import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


def make_param_service(provider_value=None):
    """Create a mock ParameterService that returns the given provider value."""
    svc = Mock()
    svc.get_param = Mock(return_value=provider_value)
    return svc


# ---------------------------------------------------------------------------
# resolve_storage_provider() Tests
# ---------------------------------------------------------------------------

class TestResolveStorageProvider:
    """Tests for resolve_storage_provider()."""

    def test_returns_google_drive_for_none(self):
        """When parameter is None, defaults to 's3_shared' (new default)."""
        from services.storage_resolver import resolve_storage_provider
        ps = make_param_service(provider_value=None)
        result = resolve_storage_provider('tenant1', parameter_service=ps)
        assert result == 's3_shared'

    def test_returns_google_drive_for_empty_string(self):
        """When parameter is empty string, defaults to 's3_shared' (new default)."""
        from services.storage_resolver import resolve_storage_provider
        ps = make_param_service(provider_value='')
        result = resolve_storage_provider('tenant1', parameter_service=ps)
        assert result == 's3_shared'

    def test_returns_google_drive_for_google_drive_value(self):
        """When parameter is 'google_drive', returns 'google_drive'."""
        from services.storage_resolver import resolve_storage_provider
        ps = make_param_service(provider_value='google_drive')
        result = resolve_storage_provider('tenant1', parameter_service=ps)
        assert result == 'google_drive'

    def test_returns_s3_shared_for_s3_shared(self):
        """When parameter is 's3_shared', returns 's3_shared'."""
        from services.storage_resolver import resolve_storage_provider
        ps = make_param_service(provider_value='s3_shared')
        result = resolve_storage_provider('tenant1', parameter_service=ps)
        assert result == 's3_shared'

    def test_returns_s3_shared_for_s3_tenant(self):
        """When parameter is 's3_tenant', returns 's3_shared' (normalized)."""
        from services.storage_resolver import resolve_storage_provider
        ps = make_param_service(provider_value='s3_tenant')
        result = resolve_storage_provider('tenant1', parameter_service=ps)
        assert result == 's3_shared'

    def test_defaults_to_google_drive_on_exception(self):
        """When ParameterService raises, defaults to 's3_shared' (new default)."""
        from services.storage_resolver import resolve_storage_provider
        ps = Mock()
        ps.get_param = Mock(side_effect=RuntimeError("DB connection failed"))
        result = resolve_storage_provider('tenant1', parameter_service=ps)
        assert result == 's3_shared'

    def test_calls_get_param_with_correct_args(self):
        """Verifies get_param is called with correct namespace, key, and tenant."""
        from services.storage_resolver import resolve_storage_provider
        ps = make_param_service(provider_value='google_drive')
        resolve_storage_provider('AcmeBV', parameter_service=ps)
        ps.get_param.assert_called_once_with(
            'storage', 'invoice_provider', tenant='AcmeBV'
        )

    def test_returns_google_drive_for_unknown_provider(self):
        """When parameter is an unknown value (not google_drive), returns 's3_shared' (new default)."""
        from services.storage_resolver import resolve_storage_provider
        ps = make_param_service(provider_value='ftp')
        result = resolve_storage_provider('tenant1', parameter_service=ps)
        assert result == 's3_shared'


# ---------------------------------------------------------------------------
# get_s3_storage() Tests
# ---------------------------------------------------------------------------

class TestGetS3Storage:
    """Tests for get_s3_storage()."""

    def test_returns_s3_shared_storage_instance(self):
        """Returns an S3SharedStorage instance for the given tenant."""
        from services.storage_resolver import get_s3_storage
        ps = make_param_service()
        ps.get_param = Mock(return_value='test-bucket')

        with patch('storage.s3_shared_storage.boto3'):
            storage = get_s3_storage('TenantA', parameter_service=ps)

        from storage.s3_shared_storage import S3SharedStorage
        assert isinstance(storage, S3SharedStorage)
        assert storage.tenant == 'TenantA'


# ---------------------------------------------------------------------------
# list_s3_folders() Tests
# ---------------------------------------------------------------------------

class TestListS3Folders:
    """Tests for list_s3_folders()."""

    def test_parses_common_prefixes(self):
        """Correctly extracts folder names from CommonPrefixes in list_objects_v2 response."""
        from services.storage_resolver import list_s3_folders

        mock_client = Mock()
        mock_client.list_objects_v2.return_value = {
            'CommonPrefixes': [
                {'Prefix': 'TenantA/invoices/Supplier1/'},
                {'Prefix': 'TenantA/invoices/Supplier2/'},
                {'Prefix': 'TenantA/invoices/Acme Corp/'},
            ],
            'Contents': [],
            'IsTruncated': False,
        }

        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = list_s3_folders('TenantA', parameter_service=Mock())

        assert result == ['Acme Corp', 'Supplier1', 'Supplier2']

    def test_includes_folders_from_marker_objects(self):
        """Includes folders that only have .folder marker objects (no other files)."""
        from services.storage_resolver import list_s3_folders

        mock_client = Mock()
        mock_client.list_objects_v2.return_value = {
            'CommonPrefixes': [
                {'Prefix': 'TenantA/invoices/Supplier1/'},
            ],
            'Contents': [
                {'Key': 'TenantA/invoices/EmptyFolder/.folder'},
                {'Key': 'TenantA/invoices/AnotherEmpty/.folder'},
            ],
            'IsTruncated': False,
        }

        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = list_s3_folders('TenantA', parameter_service=Mock())

        assert 'EmptyFolder' in result
        assert 'AnotherEmpty' in result
        assert 'Supplier1' in result
        assert result == ['AnotherEmpty', 'EmptyFolder', 'Supplier1']

    def test_returns_empty_list_on_error(self):
        """Returns empty list when S3 operations fail."""
        from services.storage_resolver import list_s3_folders

        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client.list_objects_v2.side_effect = Exception("S3 error")

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = list_s3_folders('TenantA', parameter_service=Mock())

        assert result == []

    def test_handles_pagination(self):
        """Correctly handles paginated responses from list_objects_v2."""
        from services.storage_resolver import list_s3_folders

        mock_client = Mock()
        # First page - truncated
        mock_client.list_objects_v2.side_effect = [
            {
                'CommonPrefixes': [
                    {'Prefix': 'TenantA/invoices/Folder1/'},
                ],
                'Contents': [],
                'IsTruncated': True,
                'NextContinuationToken': 'token123',
            },
            # Second page - final
            {
                'CommonPrefixes': [
                    {'Prefix': 'TenantA/invoices/Folder2/'},
                ],
                'Contents': [],
                'IsTruncated': False,
            },
        ]

        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = list_s3_folders('TenantA', parameter_service=Mock())

        assert result == ['Folder1', 'Folder2']
        # Verify pagination token was used
        second_call_kwargs = mock_client.list_objects_v2.call_args_list[1][1]
        assert second_call_kwargs['ContinuationToken'] == 'token123'

    def test_deduplicates_folders_from_prefixes_and_markers(self):
        """Folders appearing in both CommonPrefixes and .folder markers are not duplicated."""
        from services.storage_resolver import list_s3_folders

        mock_client = Mock()
        mock_client.list_objects_v2.return_value = {
            'CommonPrefixes': [
                {'Prefix': 'TenantA/invoices/Supplier1/'},
            ],
            'Contents': [
                {'Key': 'TenantA/invoices/Supplier1/.folder'},
            ],
            'IsTruncated': False,
        }

        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = list_s3_folders('TenantA', parameter_service=Mock())

        assert result == ['Supplier1']

    def test_empty_response(self):
        """Returns empty list when no folders exist."""
        from services.storage_resolver import list_s3_folders

        mock_client = Mock()
        mock_client.list_objects_v2.return_value = {
            'IsTruncated': False,
        }

        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = list_s3_folders('TenantA', parameter_service=Mock())

        assert result == []

    def test_uses_correct_prefix_and_delimiter(self):
        """Verifies list_objects_v2 is called with correct Prefix and Delimiter."""
        from services.storage_resolver import list_s3_folders

        mock_client = Mock()
        mock_client.list_objects_v2.return_value = {
            'CommonPrefixes': [],
            'Contents': [],
            'IsTruncated': False,
        }

        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            list_s3_folders('MyTenant', parameter_service=Mock())

        mock_client.list_objects_v2.assert_called_once_with(
            Bucket='test-bucket',
            Prefix='MyTenant/invoices/',
            Delimiter='/',
        )


# ---------------------------------------------------------------------------
# create_s3_folder() Tests
# ---------------------------------------------------------------------------

class TestCreateS3Folder:
    """Tests for create_s3_folder()."""

    def test_creates_correct_marker_object_key(self):
        """Creates marker at {tenant}/invoices/{name}/.folder."""
        from services.storage_resolver import create_s3_folder

        mock_client = Mock()
        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            create_s3_folder('TenantA', 'NewSupplier', parameter_service=Mock())

        mock_client.put_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='TenantA/invoices/NewSupplier/.folder',
            Body=b'',
            ContentType='application/x-directory',
        )

    def test_returns_correct_response_shape(self):
        """Returns dict with 'id', 'name', and 'url' keys."""
        from services.storage_resolver import create_s3_folder

        mock_client = Mock()
        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = create_s3_folder('TenantA', 'MyFolder', parameter_service=Mock())

        assert result == {
            'id': 'TenantA/invoices/MyFolder/.folder',
            'name': 'MyFolder',
            'url': 'TenantA/invoices/MyFolder/.folder',
        }

    def test_returns_error_on_failure(self):
        """Returns error dict when put_object fails."""
        from services.storage_resolver import create_s3_folder

        mock_client = Mock()
        mock_client.put_object.side_effect = Exception("Access denied")
        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = create_s3_folder('TenantA', 'Folder', parameter_service=Mock())

        assert result == {'success': False, 'error': 'Access denied'}


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests for storage resolver functions."""

    def test_empty_tenant_resolve_provider(self):
        """resolve_storage_provider works with empty tenant string."""
        from services.storage_resolver import resolve_storage_provider
        ps = make_param_service(provider_value='s3_shared')
        result = resolve_storage_provider('', parameter_service=ps)
        assert result == 's3_shared'

    def test_special_characters_in_folder_name(self):
        """create_s3_folder handles special characters in folder names."""
        from services.storage_resolver import create_s3_folder

        mock_client = Mock()
        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = create_s3_folder('TenantA', 'Supplier & Co.', parameter_service=Mock())

        expected_key = 'TenantA/invoices/Supplier & Co./.folder'
        mock_client.put_object.assert_called_once_with(
            Bucket='test-bucket',
            Key=expected_key,
            Body=b'',
            ContentType='application/x-directory',
        )
        assert result['name'] == 'Supplier & Co.'
        assert result['id'] == expected_key

    def test_unicode_folder_name(self):
        """create_s3_folder handles unicode characters in folder names."""
        from services.storage_resolver import create_s3_folder

        mock_client = Mock()
        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = create_s3_folder('TenantA', 'Ünternehmen GmbH', parameter_service=Mock())

        expected_key = 'TenantA/invoices/Ünternehmen GmbH/.folder'
        mock_client.put_object.assert_called_once_with(
            Bucket='test-bucket',
            Key=expected_key,
            Body=b'',
            ContentType='application/x-directory',
        )
        assert result['name'] == 'Ünternehmen GmbH'

    def test_list_s3_folders_with_unicode_prefix(self):
        """list_s3_folders correctly handles unicode folder names in response."""
        from services.storage_resolver import list_s3_folders

        mock_client = Mock()
        mock_client.list_objects_v2.return_value = {
            'CommonPrefixes': [
                {'Prefix': 'TenantA/invoices/Café Noir/'},
                {'Prefix': 'TenantA/invoices/日本語フォルダ/'},
            ],
            'Contents': [],
            'IsTruncated': False,
        }

        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = list_s3_folders('TenantA', parameter_service=Mock())

        assert 'Café Noir' in result
        assert '日本語フォルダ' in result

    def test_empty_tenant_list_folders(self):
        """list_s3_folders works with empty tenant string."""
        from services.storage_resolver import list_s3_folders

        mock_client = Mock()
        mock_client.list_objects_v2.return_value = {
            'CommonPrefixes': [
                {'Prefix': '/invoices/Folder1/'},
            ],
            'Contents': [],
            'IsTruncated': False,
        }

        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = list_s3_folders('', parameter_service=Mock())

        assert result == ['Folder1']

    def test_empty_tenant_create_folder(self):
        """create_s3_folder works with empty tenant string."""
        from services.storage_resolver import create_s3_folder

        mock_client = Mock()
        mock_storage = Mock()
        mock_storage.bucket = 'test-bucket'
        mock_storage._client = mock_client

        with patch('services.storage_resolver.get_s3_storage', return_value=mock_storage):
            result = create_s3_folder('', 'TestFolder', parameter_service=Mock())

        assert result['id'] == '/invoices/TestFolder/.folder'
        assert result['name'] == 'TestFolder'
