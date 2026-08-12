"""
Unit tests for S3SharedStorage list_files with category support.

Requirements: 10.1–10.6
Reference: .kiro/specs/s3-shared-bucket-infrastructure/design.md

Note: The _make_key method was removed from S3SharedStorage during refactoring.
Key building is now handled by MediaAssetService._build_s3_key().
"""

import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


def make_param_service(extra=None):
    params = {}
    if extra:
        params.update(extra)

    def get_param(ns, key, tenant=None, **kw):
        return params.get((ns, key))

    svc = Mock()
    svc.get_param = Mock(side_effect=get_param)
    return svc


def create_storage(tenant='TestTenant'):
    """Create an S3SharedStorage instance with mocked boto3."""
    from storage.s3_shared_storage import S3SharedStorage
    ps = make_param_service(extra={('storage', 's3_shared_bucket'): 'test-bucket'})
    with patch('storage.s3_shared_storage.boto3') as mock_boto:
        provider = S3SharedStorage(tenant, ps)
    return provider


class TestListFilesCategory:
    """Tests for list_files with category parameter."""

    def test_list_files_with_category_invoices(self):
        """list_files with category='invoices' scopes prefix to {tenant}/invoices/."""
        provider = create_storage('KimGeers')
        mock_client = Mock()
        mock_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'KimGeers/invoices/railway/abc_invoice.pdf', 'Size': 1024, 'LastModified': '2024-01-01'}
            ]
        }
        provider._client = mock_client

        result = provider.list_files('', category='invoices')

        mock_client.list_objects_v2.assert_called_once_with(
            Bucket='test-bucket', Prefix='KimGeers/invoices/'
        )
        assert len(result) == 1
        assert result[0]['key'] == 'KimGeers/invoices/railway/abc_invoice.pdf'

    def test_list_files_with_category_branding(self):
        """list_files with category='branding' scopes prefix to {tenant}/branding/."""
        provider = create_storage('KimGeers')
        mock_client = Mock()
        mock_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'KimGeers/branding/company_logo.png', 'Size': 2048, 'LastModified': '2024-01-01'}
            ]
        }
        provider._client = mock_client

        result = provider.list_files('', category='branding')

        mock_client.list_objects_v2.assert_called_once_with(
            Bucket='test-bucket', Prefix='KimGeers/branding/'
        )
        assert len(result) == 1
        assert result[0]['key'] == 'KimGeers/branding/company_logo.png'

    def test_list_files_without_category_uses_path(self):
        """list_files without category uses the provided path as prefix."""
        provider = create_storage('KimGeers')
        mock_client = Mock()
        mock_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'KimGeers/invoices/railway/abc_invoice.pdf', 'Size': 1024, 'LastModified': '2024-01-01'}
            ]
        }
        provider._client = mock_client

        result = provider.list_files('KimGeers/invoices/railway')

        mock_client.list_objects_v2.assert_called_once_with(
            Bucket='test-bucket', Prefix='KimGeers/invoices/railway/'
        )
        assert len(result) == 1

    def test_list_files_without_category_path_with_trailing_slash(self):
        """list_files without category preserves trailing slash in path."""
        provider = create_storage('KimGeers')
        mock_client = Mock()
        mock_client.list_objects_v2.return_value = {'Contents': []}
        provider._client = mock_client

        provider.list_files('KimGeers/templates/')

        mock_client.list_objects_v2.assert_called_once_with(
            Bucket='test-bucket', Prefix='KimGeers/templates/'
        )
