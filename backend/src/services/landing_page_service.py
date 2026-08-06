"""
Landing Page Service

Service for managing landing page drafts and versions in DynamoDB.
Uses single-table design with PK/SK pattern for efficient access.

Table: myadmin-landing-pages
- Draft: PK=TENANT#{slug}, SK=LANDING#HOME
- Version: PK=TENANT#{slug}, SK=VERSION#{n}
"""

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class LandingPageService:
    """Service for managing landing page drafts and versions in DynamoDB."""

    TABLE_NAME = "myadmin-landing-pages"

    def __init__(self):
        """Initialize DynamoDB resource. Region from env var."""
        region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
        self._dynamodb = boto3.resource("dynamodb", region_name=region)
        self._table = self._dynamodb.Table(self.TABLE_NAME)

    # ========================================================================
    # Draft Operations
    # ========================================================================

    def get_draft(self, slug: str) -> dict | None:
        """
        Get the current draft for a tenant slug.

        Args:
            slug: Tenant slug (e.g. 'acme-rentals')

        Returns:
            Draft dict with sections, version, status, etc. or None if not found.
        """
        try:
            response = self._table.get_item(
                Key={"PK": f"TENANT#{slug}", "SK": "LANDING#HOME"}
            )
            item = response.get("Item")
            if not item:
                return None

            # Strip internal DynamoDB keys
            item.pop("PK", None)
            item.pop("SK", None)

            # Convert Decimal values to int (DynamoDB stores numbers as Decimal)
            if "version" in item:
                item["version"] = int(item["version"])

            return item

        except ClientError as e:
            logger.error(
                "DynamoDB get_draft failed for slug=%s: %s",
                slug,
                e.response["Error"]["Message"],
            )
            return None

    def save_draft(self, slug: str, sections: list, modified_by: str) -> dict:
        """
        Save/update the draft for a tenant. Auto-increments version.

        Args:
            slug: Tenant slug
            sections: List of section block dicts
            modified_by: Email of the user making the change

        Returns:
            Dict with success, version, and last_modified.
        """
        try:
            # Read current version to auto-increment
            current = self._table.get_item(
                Key={"PK": f"TENANT#{slug}", "SK": "LANDING#HOME"},
                ProjectionExpression="#v",
                ExpressionAttributeNames={"#v": "version"},
            )
            current_version = int(current.get("Item", {}).get("version", 0))
            new_version = current_version + 1

            now = datetime.now(timezone.utc).isoformat()

            self._table.put_item(
                Item={
                    "PK": f"TENANT#{slug}",
                    "SK": "LANDING#HOME",
                    "status": "draft",
                    "version": new_version,
                    "last_modified": now,
                    "modified_by": modified_by,
                    "sections": sections,
                }
            )

            return {"success": True, "version": new_version, "last_modified": now}

        except ClientError as e:
            logger.error(
                "DynamoDB save_draft failed for slug=%s: %s",
                slug,
                e.response["Error"]["Message"],
            )
            return {"success": False, "error": "Failed to save draft"}

    def delete_draft(self, slug: str) -> bool:
        """
        Delete the draft item for a tenant.

        Args:
            slug: Tenant slug

        Returns:
            True if deleted, False if not found.
        """
        try:
            response = self._table.delete_item(
                Key={"PK": f"TENANT#{slug}", "SK": "LANDING#HOME"},
                ReturnValues="ALL_OLD",
            )
            # ALL_OLD returns the deleted item; if empty, item didn't exist
            return "Attributes" in response

        except ClientError as e:
            logger.error(
                "DynamoDB delete_draft failed for slug=%s: %s",
                slug,
                e.response["Error"]["Message"],
            )
            return False

    # ========================================================================
    # Version Operations
    # ========================================================================

    def get_version(self, slug: str, version: int) -> dict | None:
        """
        Get a specific version snapshot.

        Args:
            slug: Tenant slug
            version: Version number

        Returns:
            Version dict with sections, published_at, published_by, or None.
        """
        try:
            response = self._table.get_item(
                Key={"PK": f"TENANT#{slug}", "SK": f"VERSION#{version}"}
            )
            item = response.get("Item")
            if not item:
                return None

            # Strip internal DynamoDB keys
            item.pop("PK", None)
            item.pop("SK", None)

            # Convert Decimal values
            if "version" in item:
                item["version"] = int(item["version"])

            return item

        except ClientError as e:
            logger.error(
                "DynamoDB get_version failed for slug=%s version=%d: %s",
                slug,
                version,
                e.response["Error"]["Message"],
            )
            return None

    def save_version(
        self, slug: str, version: int, sections: list, published_by: str
    ) -> dict:
        """
        Save a version snapshot (called during publish).

        Args:
            slug: Tenant slug
            version: Version number to save
            sections: Frozen copy of sections at publish time
            published_by: Email of the user who published

        Returns:
            Dict with success and version number.
        """
        try:
            now = datetime.now(timezone.utc).isoformat()

            self._table.put_item(
                Item={
                    "PK": f"TENANT#{slug}",
                    "SK": f"VERSION#{version}",
                    "version": version,
                    "published_at": now,
                    "published_by": published_by,
                    "sections": sections,
                }
            )

            return {"success": True, "version": version}

        except ClientError as e:
            logger.error(
                "DynamoDB save_version failed for slug=%s version=%d: %s",
                slug,
                version,
                e.response["Error"]["Message"],
            )
            return {"success": False, "error": "Failed to save version"}

    def list_versions(self, slug: str) -> list[dict]:
        """
        Query all version snapshots for a tenant, sorted descending.

        Args:
            slug: Tenant slug

        Returns:
            List of version summaries (version, published_at, published_by),
            sorted by version descending.
        """
        try:
            response = self._table.query(
                KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                ExpressionAttributeValues={
                    ":pk": f"TENANT#{slug}",
                    ":sk_prefix": "VERSION#",
                },
                ProjectionExpression="#v, published_at, published_by",
                ExpressionAttributeNames={"#v": "version"},
            )

            items = response.get("Items", [])

            # Convert Decimal and build summary list
            versions = [
                {
                    "version": int(item["version"]),
                    "published_at": item.get("published_at", ""),
                    "published_by": item.get("published_by", ""),
                }
                for item in items
            ]

            # Sort by version descending
            versions.sort(key=lambda v: v["version"], reverse=True)

            return versions

        except ClientError as e:
            logger.error(
                "DynamoDB list_versions failed for slug=%s: %s",
                slug,
                e.response["Error"]["Message"],
            )
            return []
