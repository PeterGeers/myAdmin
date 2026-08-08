"""
Unit Tests for CloudFrontDomainService

Tests CloudFront distribution CNAME management (Task 4.4)
and KeyValueStore domain→slug mappings (Task 4.5).
Uses unittest.mock to mock boto3 clients.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


@pytest.fixture
def mock_env(monkeypatch):
    """Set environment variables for CloudFrontDomainService."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.setenv(
        "CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID", "E1234DISTRIBUTION"
    )
    monkeypatch.setenv(
        "CLOUDFRONT_KVS_ARN",
        "arn:aws:cloudfront::123456789:key-value-store/test-kvs",
    )
    monkeypatch.setenv("CLOUDFRONT_PUBLIC_PAGES_DOMAIN", "d1234abcd.cloudfront.net")


@pytest.fixture
def mock_boto3(mock_env):
    """Create CloudFrontDomainService with mocked boto3 clients."""
    with patch("boto3.client") as mock_client_factory:
        mock_cloudfront = MagicMock()
        mock_acm = MagicMock()
        mock_kvs = MagicMock()

        def client_factory(service_name, **kwargs):
            if service_name == "cloudfront":
                return mock_cloudfront
            elif service_name == "acm":
                return mock_acm
            elif service_name == "cloudfront-keyvaluestore":
                return mock_kvs
            return MagicMock()

        mock_client_factory.side_effect = client_factory

        from services.cloudfront_domain_service import CloudFrontDomainService

        service = CloudFrontDomainService()

        yield service, mock_cloudfront, mock_acm, mock_kvs


class TestAddDomainToDistribution:
    """Tests for CloudFrontDomainService.add_domain_to_distribution (Task 4.4)."""

    def test_add_domain_success(self, mock_boto3):
        """Add a new domain to distribution — succeeds."""
        service, mock_cf, _, _ = mock_boto3

        mock_cf.get_distribution_config.return_value = {
            "DistributionConfig": {
                "Aliases": {"Quantity": 1, "Items": ["*.jabaki.nl"]},
                "ViewerCertificate": {},
            },
            "ETag": "ETAG123",
        }
        mock_cf.update_distribution.return_value = {}

        result = service.add_domain_to_distribution(
            "www.acme-rentals.nl",
            "arn:aws:acm:us-east-1:123:certificate/abc",
        )

        assert result is True
        mock_cf.update_distribution.assert_called_once()
        call_kwargs = mock_cf.update_distribution.call_args[1]
        assert call_kwargs["IfMatch"] == "ETAG123"
        config = call_kwargs["DistributionConfig"]
        assert "www.acme-rentals.nl" in config["Aliases"]["Items"]
        assert config["Aliases"]["Quantity"] == 2

    def test_add_domain_already_present(self, mock_boto3):
        """Add a domain that's already in aliases — returns True without update."""
        service, mock_cf, _, _ = mock_boto3

        mock_cf.get_distribution_config.return_value = {
            "DistributionConfig": {
                "Aliases": {
                    "Quantity": 2,
                    "Items": ["*.jabaki.nl", "www.acme-rentals.nl"],
                },
            },
            "ETag": "ETAG456",
        }

        result = service.add_domain_to_distribution(
            "www.acme-rentals.nl",
            "arn:aws:acm:us-east-1:123:certificate/abc",
        )

        assert result is True
        mock_cf.update_distribution.assert_not_called()

    def test_add_domain_client_error(self, mock_boto3):
        """CloudFront API error — returns False."""
        service, mock_cf, _, _ = mock_boto3

        mock_cf.get_distribution_config.side_effect = ClientError(
            {"Error": {"Code": "NoSuchDistribution", "Message": "Not found"}},
            "GetDistributionConfig",
        )

        result = service.add_domain_to_distribution(
            "www.acme-rentals.nl",
            "arn:aws:acm:us-east-1:123:certificate/abc",
        )

        assert result is False


class TestRemoveDomainFromDistribution:
    """Tests for CloudFrontDomainService.remove_domain_from_distribution (Task 4.4)."""

    def test_remove_domain_success(self, mock_boto3):
        """Remove an existing domain from distribution — succeeds."""
        service, mock_cf, _, _ = mock_boto3

        mock_cf.get_distribution_config.return_value = {
            "DistributionConfig": {
                "Aliases": {
                    "Quantity": 2,
                    "Items": ["*.jabaki.nl", "www.acme-rentals.nl"],
                },
            },
            "ETag": "ETAG789",
        }
        mock_cf.update_distribution.return_value = {}

        result = service.remove_domain_from_distribution("www.acme-rentals.nl")

        assert result is True
        call_kwargs = mock_cf.update_distribution.call_args[1]
        assert call_kwargs["IfMatch"] == "ETAG789"
        config = call_kwargs["DistributionConfig"]
        assert "www.acme-rentals.nl" not in config["Aliases"]["Items"]
        assert config["Aliases"]["Quantity"] == 1

    def test_remove_domain_not_present(self, mock_boto3):
        """Remove a domain not in aliases — returns True without update."""
        service, mock_cf, _, _ = mock_boto3

        mock_cf.get_distribution_config.return_value = {
            "DistributionConfig": {
                "Aliases": {"Quantity": 1, "Items": ["*.jabaki.nl"]},
            },
            "ETag": "ETAG000",
        }

        result = service.remove_domain_from_distribution("www.acme-rentals.nl")

        assert result is True
        mock_cf.update_distribution.assert_not_called()

    def test_remove_domain_client_error(self, mock_boto3):
        """CloudFront API error — returns False."""
        service, mock_cf, _, _ = mock_boto3

        mock_cf.get_distribution_config.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "No access"}},
            "GetDistributionConfig",
        )

        result = service.remove_domain_from_distribution("www.acme-rentals.nl")

        assert result is False


class TestPutKvsMapping:
    """Tests for CloudFrontDomainService.put_kvs_mapping (Task 4.5)."""

    def test_put_mapping_success(self, mock_boto3):
        """Put a new domain→slug mapping — succeeds."""
        service, _, _, mock_kvs = mock_boto3

        mock_kvs.describe_key_value_store.return_value = {"ETag": "KVS_ETAG1"}
        mock_kvs.put_key.return_value = {}

        result = service.put_kvs_mapping("www.acme-rentals.nl", "acme-rentals")

        assert result is True
        mock_kvs.put_key.assert_called_once_with(
            KvsARN="arn:aws:cloudfront::123456789:key-value-store/test-kvs",
            Key="www.acme-rentals.nl",
            Value="acme-rentals",
            IfMatch="KVS_ETAG1",
        )

    def test_put_mapping_client_error(self, mock_boto3):
        """KVS API error — returns False."""
        service, _, _, mock_kvs = mock_boto3

        mock_kvs.describe_key_value_store.return_value = {"ETag": "KVS_ETAG1"}
        mock_kvs.put_key.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Invalid"}},
            "PutKey",
        )

        result = service.put_kvs_mapping("www.acme-rentals.nl", "acme-rentals")

        assert result is False


class TestDeleteKvsMapping:
    """Tests for CloudFrontDomainService.delete_kvs_mapping (Task 4.5)."""

    def test_delete_mapping_success(self, mock_boto3):
        """Delete an existing domain mapping — succeeds."""
        service, _, _, mock_kvs = mock_boto3

        mock_kvs.describe_key_value_store.return_value = {"ETag": "KVS_ETAG2"}
        mock_kvs.delete_key.return_value = {}

        result = service.delete_kvs_mapping("www.acme-rentals.nl")

        assert result is True
        mock_kvs.delete_key.assert_called_once_with(
            KvsARN="arn:aws:cloudfront::123456789:key-value-store/test-kvs",
            Key="www.acme-rentals.nl",
            IfMatch="KVS_ETAG2",
        )

    def test_delete_mapping_not_found(self, mock_boto3):
        """Delete a key that doesn't exist — returns True (idempotent)."""
        service, _, _, mock_kvs = mock_boto3

        mock_kvs.describe_key_value_store.return_value = {"ETag": "KVS_ETAG3"}
        mock_kvs.delete_key.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ResourceNotFoundException",
                    "Message": "Key not found",
                }
            },
            "DeleteKey",
        )

        result = service.delete_kvs_mapping("www.nonexistent.nl")

        assert result is True

    def test_delete_mapping_other_error(self, mock_boto3):
        """Delete with non-NotFound error — returns False."""
        service, _, _, mock_kvs = mock_boto3

        mock_kvs.describe_key_value_store.return_value = {"ETag": "KVS_ETAG4"}
        mock_kvs.delete_key.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "No access"}},
            "DeleteKey",
        )

        result = service.delete_kvs_mapping("www.acme-rentals.nl")

        assert result is False
