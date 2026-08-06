"""
Unit Tests for LandingPageService

Tests DynamoDB CRUD operations for landing page drafts and versions.
Uses unittest.mock to mock boto3 DynamoDB resource.
"""

import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

import pytest
from botocore.exceptions import ClientError

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


class TestLandingPageService:
    """Test suite for LandingPageService DynamoDB operations."""

    @pytest.fixture
    def mock_dynamodb(self):
        """Mock boto3.resource('dynamodb') and table."""
        with patch(
            "services.landing_page_service.boto3.resource"
        ) as mock_resource_factory:
            mock_resource = Mock()
            mock_table = Mock()
            mock_resource.Table.return_value = mock_table
            mock_resource_factory.return_value = mock_resource
            yield mock_table

    @pytest.fixture
    def service(self, mock_dynamodb):
        """Create LandingPageService with mocked DynamoDB."""
        from services.landing_page_service import LandingPageService

        svc = LandingPageService()
        return svc

    # ========================================================================
    # get_draft tests
    # ========================================================================

    def test_get_draft_found(self, service, mock_dynamodb):
        """Test get_draft returns item without PK/SK keys."""
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "PK": "TENANT#acme-rentals",
                "SK": "LANDING#HOME",
                "status": "draft",
                "version": Decimal("3"),
                "last_modified": "2026-08-05T14:30:00+00:00",
                "modified_by": "admin@acme.nl",
                "sections": [{"id": "block-001", "type": "hero"}],
            }
        }

        result = service.get_draft("acme-rentals")

        assert result is not None
        assert "PK" not in result
        assert "SK" not in result
        assert result["status"] == "draft"
        assert result["version"] == 3
        assert isinstance(result["version"], int)
        assert result["modified_by"] == "admin@acme.nl"
        assert len(result["sections"]) == 1

        mock_dynamodb.get_item.assert_called_once_with(
            Key={"PK": "TENANT#acme-rentals", "SK": "LANDING#HOME"}
        )

    def test_get_draft_not_found(self, service, mock_dynamodb):
        """Test get_draft returns None when item doesn't exist."""
        mock_dynamodb.get_item.return_value = {}

        result = service.get_draft("nonexistent")

        assert result is None

    def test_get_draft_client_error(self, service, mock_dynamodb):
        """Test get_draft returns None on ClientError."""
        mock_dynamodb.get_item.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Table not found"}},
            "GetItem",
        )

        result = service.get_draft("acme-rentals")

        assert result is None

    # ========================================================================
    # save_draft tests
    # ========================================================================

    def test_save_draft_first_time(self, service, mock_dynamodb):
        """Test save_draft with no existing draft (version starts at 1)."""
        # No existing item
        mock_dynamodb.get_item.return_value = {}
        mock_dynamodb.put_item.return_value = {}

        result = service.save_draft(
            slug="new-tenant",
            sections=[{"id": "block-001", "type": "hero"}],
            modified_by="user@new-tenant.nl",
        )

        assert result["success"] is True
        assert result["version"] == 1
        assert "last_modified" in result

        # Verify put_item was called with correct structure
        put_call = mock_dynamodb.put_item.call_args
        item = put_call[1]["Item"] if "Item" in put_call[1] else put_call[0][0]
        assert item["PK"] == "TENANT#new-tenant"
        assert item["SK"] == "LANDING#HOME"
        assert item["status"] == "draft"
        assert item["version"] == 1
        assert item["modified_by"] == "user@new-tenant.nl"

    def test_save_draft_increments_version(self, service, mock_dynamodb):
        """Test save_draft increments existing version."""
        mock_dynamodb.get_item.return_value = {
            "Item": {"version": Decimal("5")}
        }
        mock_dynamodb.put_item.return_value = {}

        result = service.save_draft(
            slug="acme-rentals",
            sections=[{"id": "block-002", "type": "about"}],
            modified_by="admin@acme.nl",
        )

        assert result["success"] is True
        assert result["version"] == 6

        put_call = mock_dynamodb.put_item.call_args
        item = put_call[1]["Item"]
        assert item["version"] == 6

    def test_save_draft_client_error(self, service, mock_dynamodb):
        """Test save_draft returns error on ClientError."""
        mock_dynamodb.get_item.return_value = {}
        mock_dynamodb.put_item.side_effect = ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "Throttled"}},
            "PutItem",
        )

        result = service.save_draft(
            slug="acme-rentals",
            sections=[],
            modified_by="admin@acme.nl",
        )

        assert result["success"] is False
        assert "error" in result

    # ========================================================================
    # delete_draft tests
    # ========================================================================

    def test_delete_draft_exists(self, service, mock_dynamodb):
        """Test delete_draft returns True when item existed."""
        mock_dynamodb.delete_item.return_value = {
            "Attributes": {
                "PK": "TENANT#acme-rentals",
                "SK": "LANDING#HOME",
                "version": Decimal("3"),
            }
        }

        result = service.delete_draft("acme-rentals")

        assert result is True
        mock_dynamodb.delete_item.assert_called_once_with(
            Key={"PK": "TENANT#acme-rentals", "SK": "LANDING#HOME"},
            ReturnValues="ALL_OLD",
        )

    def test_delete_draft_not_found(self, service, mock_dynamodb):
        """Test delete_draft returns False when item didn't exist."""
        mock_dynamodb.delete_item.return_value = {}

        result = service.delete_draft("nonexistent")

        assert result is False

    def test_delete_draft_client_error(self, service, mock_dynamodb):
        """Test delete_draft returns False on ClientError."""
        mock_dynamodb.delete_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Internal error"}},
            "DeleteItem",
        )

        result = service.delete_draft("acme-rentals")

        assert result is False

    # ========================================================================
    # get_version tests
    # ========================================================================

    def test_get_version_found(self, service, mock_dynamodb):
        """Test get_version returns version snapshot without PK/SK."""
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "PK": "TENANT#acme-rentals",
                "SK": "VERSION#5",
                "version": Decimal("5"),
                "published_at": "2026-08-05T15:00:00+00:00",
                "published_by": "admin@acme.nl",
                "sections": [{"id": "block-001", "type": "hero"}],
            }
        }

        result = service.get_version("acme-rentals", 5)

        assert result is not None
        assert "PK" not in result
        assert "SK" not in result
        assert result["version"] == 5
        assert isinstance(result["version"], int)
        assert result["published_by"] == "admin@acme.nl"

        mock_dynamodb.get_item.assert_called_once_with(
            Key={"PK": "TENANT#acme-rentals", "SK": "VERSION#5"}
        )

    def test_get_version_not_found(self, service, mock_dynamodb):
        """Test get_version returns None when version doesn't exist."""
        mock_dynamodb.get_item.return_value = {}

        result = service.get_version("acme-rentals", 99)

        assert result is None

    def test_get_version_client_error(self, service, mock_dynamodb):
        """Test get_version returns None on ClientError."""
        mock_dynamodb.get_item.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Table not found"}},
            "GetItem",
        )

        result = service.get_version("acme-rentals", 5)

        assert result is None

    # ========================================================================
    # save_version tests
    # ========================================================================

    def test_save_version_success(self, service, mock_dynamodb):
        """Test save_version creates a version snapshot."""
        mock_dynamodb.put_item.return_value = {}

        result = service.save_version(
            slug="acme-rentals",
            version=6,
            sections=[{"id": "block-001", "type": "hero"}],
            published_by="admin@acme.nl",
        )

        assert result["success"] is True
        assert result["version"] == 6

        put_call = mock_dynamodb.put_item.call_args
        item = put_call[1]["Item"]
        assert item["PK"] == "TENANT#acme-rentals"
        assert item["SK"] == "VERSION#6"
        assert item["version"] == 6
        assert item["published_by"] == "admin@acme.nl"
        assert "published_at" in item

    def test_save_version_client_error(self, service, mock_dynamodb):
        """Test save_version returns error on ClientError."""
        mock_dynamodb.put_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Failed"}},
            "PutItem",
        )

        result = service.save_version(
            slug="acme-rentals",
            version=6,
            sections=[],
            published_by="admin@acme.nl",
        )

        assert result["success"] is False
        assert "error" in result

    # ========================================================================
    # list_versions tests
    # ========================================================================

    def test_list_versions_returns_sorted(self, service, mock_dynamodb):
        """Test list_versions returns versions sorted descending."""
        mock_dynamodb.query.return_value = {
            "Items": [
                {
                    "version": Decimal("3"),
                    "published_at": "2026-08-01T10:00:00+00:00",
                    "published_by": "admin@acme.nl",
                },
                {
                    "version": Decimal("5"),
                    "published_at": "2026-08-05T15:00:00+00:00",
                    "published_by": "admin@acme.nl",
                },
                {
                    "version": Decimal("4"),
                    "published_at": "2026-08-03T12:00:00+00:00",
                    "published_by": "other@acme.nl",
                },
            ]
        }

        result = service.list_versions("acme-rentals")

        assert len(result) == 3
        assert result[0]["version"] == 5
        assert result[1]["version"] == 4
        assert result[2]["version"] == 3
        # Only summary fields returned
        assert set(result[0].keys()) == {"version", "published_at", "published_by"}

    def test_list_versions_empty(self, service, mock_dynamodb):
        """Test list_versions returns empty list for new tenant."""
        mock_dynamodb.query.return_value = {"Items": []}

        result = service.list_versions("new-tenant")

        assert result == []

    def test_list_versions_query_params(self, service, mock_dynamodb):
        """Test list_versions uses correct query parameters."""
        mock_dynamodb.query.return_value = {"Items": []}

        service.list_versions("acme-rentals")

        mock_dynamodb.query.assert_called_once_with(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": "TENANT#acme-rentals",
                ":sk_prefix": "VERSION#",
            },
            ProjectionExpression="#v, published_at, published_by",
            ExpressionAttributeNames={"#v": "version"},
        )

    def test_list_versions_client_error(self, service, mock_dynamodb):
        """Test list_versions returns empty list on ClientError."""
        mock_dynamodb.query.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Failed"}},
            "Query",
        )

        result = service.list_versions("acme-rentals")

        assert result == []

    # ========================================================================
    # Initialization tests
    # ========================================================================

    def test_table_name_constant(self, service):
        """Test TABLE_NAME is set correctly."""
        assert service.TABLE_NAME == "myadmin-landing-pages"

    def test_init_uses_env_region(self, mock_dynamodb):
        """Test constructor reads region from environment variable."""
        with patch.dict(os.environ, {"AWS_DEFAULT_REGION": "us-east-1"}):
            with patch(
                "services.landing_page_service.boto3.resource"
            ) as mock_resource:
                mock_resource.return_value = Mock()
                mock_resource.return_value.Table.return_value = Mock()

                from services.landing_page_service import LandingPageService

                LandingPageService()

                mock_resource.assert_called_with("dynamodb", region_name="us-east-1")

    def test_init_default_region(self, mock_dynamodb):
        """Test constructor defaults to eu-west-1 when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove AWS_DEFAULT_REGION if it exists
            os.environ.pop("AWS_DEFAULT_REGION", None)

            with patch(
                "services.landing_page_service.boto3.resource"
            ) as mock_resource:
                mock_resource.return_value = Mock()
                mock_resource.return_value.Table.return_value = Mock()

                from services.landing_page_service import LandingPageService

                LandingPageService()

                mock_resource.assert_called_with("dynamodb", region_name="eu-west-1")
