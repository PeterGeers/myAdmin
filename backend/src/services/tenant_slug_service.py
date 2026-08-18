"""
Tenant Slug Service

Manages the mapping between tenant administration identifiers and
public URL slugs for landing pages. Each tenant can have one unique slug
that serves as their public landing page URL: /p/{slug}
"""

import logging
import os
import re

import boto3
from botocore.exceptions import ClientError

from database import DatabaseManager
from db_exceptions import DatabaseError, IntegrityError

logger = logging.getLogger(__name__)

# Slugs reserved for system use — cannot be claimed by tenants
RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "www",
        "app",
        "test",
        "staging",
        "landing",
        "public",
        "static",
        "assets",
    }
)

# Slug format: lowercase alphanumeric with single hyphens, no leading/trailing hyphens
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SLUG_MIN_LENGTH = 3
SLUG_MAX_LENGTH = 100


class TenantSlugService:
    """
    Service for managing tenant URL slugs.

    Handles slug resolution, validation, and CRUD operations
    against the tenant_slugs table.
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize the tenant slug service.

        Args:
            db_manager: DatabaseManager instance for database operations
        """
        self.db = db_manager

    def resolve_slug(self, slug: str) -> str | None:
        """
        Resolve a slug to its administration identifier.

        This is the primary public-facing lookup: given a slug from a URL,
        return the tenant administration value.

        Args:
            slug: The URL slug to resolve

        Returns:
            The administration identifier, or None if slug not found
        """
        try:
            query = """
                SELECT administration
                FROM tenant_slugs
                WHERE slug = %s
            """
            results = self.db.execute_query(query, (slug,))

            if results and len(results) > 0:
                return results[0]["administration"]

            return None

        except DatabaseError as e:
            logger.error(f"Failed to resolve slug '{slug}': {e}")
            raise

    def get_slug(self, administration: str) -> str | None:
        """
        Get the slug for a given administration.

        Args:
            administration: The tenant administration identifier

        Returns:
            The slug string, or None if no slug is set
        """
        try:
            query = """
                SELECT slug
                FROM tenant_slugs
                WHERE administration = %s
            """
            results = self.db.execute_query(query, (administration,))

            if results and len(results) > 0:
                return results[0]["slug"]

            return None

        except DatabaseError as e:
            logger.error(f"Failed to get slug for '{administration}': {e}")
            raise

    def set_slug(self, administration: str, slug: str, user_email: str = "") -> dict:
        """
        Set or update the slug for a tenant.

        Validates the slug format and uniqueness before saving.
        If an existing slug differs, triggers the full rename workflow
        (DynamoDB migration, MySQL cleanup, S3/CloudFront cleanup, republish).

        Args:
            administration: The tenant administration identifier
            slug: The desired slug value
            user_email: Email of the user making the change (for audit)

        Returns:
            Dict with 'success' and either 'slug' or 'error'.
            On rename: includes 'renamed_from' and 'warnings'.
        """
        # Validate first
        validation = self.validate_slug(slug, current_administration=administration)
        if not validation["valid"]:
            return {"success": False, "error": validation["error"]}

        # Check if this is a rename (existing slug differs from new slug)
        old_slug = self.get_slug(administration)

        if old_slug and old_slug == slug:
            # No-op: same slug
            return {"success": True, "slug": slug}

        if old_slug and old_slug != slug:
            # This is a rename — run full migration workflow
            return self.rename_slug(administration, old_slug, slug, user_email)

        # First-time slug setup — simple INSERT
        try:
            query = """
                INSERT INTO tenant_slugs (administration, slug)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE
                    slug = VALUES(slug),
                    updated_at = CURRENT_TIMESTAMP
            """
            self.db.execute_query(
                query, (administration, slug), fetch=False, commit=True
            )

            logger.info(f"Set slug '{slug}' for administration '{administration}'")
            return {"success": True, "slug": slug}

        except IntegrityError as e:
            logger.warning(
                f"Integrity error setting slug '{slug}' for '{administration}': {e}"
            )
            return {"success": False, "error": "Slug is already taken"}

        except DatabaseError as e:
            logger.error(
                f"Database error setting slug '{slug}' for '{administration}': {e}"
            )
            return {"success": False, "error": "Failed to save slug"}

    def validate_slug(
        self, slug: str, current_administration: str | None = None
    ) -> dict:
        """
        Validate a slug for format correctness and uniqueness.

        Checks:
        - Must be lowercase
        - Only alphanumeric characters and hyphens allowed
        - Minimum 3 characters, maximum 100 characters
        - Cannot start or end with a hyphen
        - Cannot have consecutive hyphens
        - Must not be a reserved slug
        - Must be unique in tenant_slugs table (excluding current tenant)

        Args:
            slug: The slug value to validate
            current_administration: If provided, excludes this tenant from
                uniqueness check (for updates)

        Returns:
            Dict with 'valid' (bool) and optionally 'error' (str)
        """
        # Length check
        if len(slug) < SLUG_MIN_LENGTH:
            return {
                "valid": False,
                "error": f"Slug must be at least {SLUG_MIN_LENGTH} characters",
            }

        if len(slug) > SLUG_MAX_LENGTH:
            return {
                "valid": False,
                "error": f"Slug must be at most {SLUG_MAX_LENGTH} characters",
            }

        # Format check (covers lowercase, allowed chars, no leading/trailing
        # hyphens, no consecutive hyphens)
        if not SLUG_PATTERN.match(slug):
            return {
                "valid": False,
                "error": (
                    "Slug must be lowercase, contain only letters, numbers, "
                    "and hyphens, and cannot start/end with a hyphen or "
                    "contain consecutive hyphens"
                ),
            }

        # Reserved slug check
        if slug in RESERVED_SLUGS:
            return {
                "valid": False,
                "error": f"'{slug}' is a reserved name and cannot be used",
            }

        # Uniqueness check
        try:
            if current_administration:
                query = """
                    SELECT administration
                    FROM tenant_slugs
                    WHERE slug = %s AND administration != %s
                """
                results = self.db.execute_query(query, (slug, current_administration))
            else:
                query = """
                    SELECT administration
                    FROM tenant_slugs
                    WHERE slug = %s
                """
                results = self.db.execute_query(query, (slug,))

            if results and len(results) > 0:
                return {"valid": False, "error": "Slug is already taken"}

        except DatabaseError as e:
            logger.error(f"Failed to check slug uniqueness for '{slug}': {e}")
            return {"valid": False, "error": "Failed to validate slug"}

        return {"valid": True}

    # ========================================================================
    # Slug Rename Orchestrator
    # ========================================================================

    def rename_slug(
        self, administration: str, old_slug: str, new_slug: str, user_email: str = ""
    ) -> dict:
        """
        Rename a tenant's slug with full resource migration.

        Steps:
        1. Update MySQL tenant_slugs (source of truth)
        2. Migrate DynamoDB items (draft + versions)
        3. Update MySQL tenant_custom_domains.slug
        4. Update MySQL s3_asset_references.entity_id
        5. Delete old S3 CDN files
        6. Republish under new slug
        7. Update CloudFront KVS if custom domain exists
        8. Invalidate CloudFront cache for old slug

        Non-atomic: partial failures are reported as warnings.
        MySQL update (step 1) must succeed; everything else is best-effort.

        Args:
            administration: Tenant identifier
            old_slug: Current slug value
            new_slug: Desired new slug value
            user_email: Email of user performing the rename

        Returns:
            Dict with success, slug, renamed_from, and warnings list.
        """
        warnings = []

        # Step 1: Update MySQL tenant_slugs — this is the source of truth
        try:
            query = """
                UPDATE tenant_slugs
                SET slug = %s, updated_at = CURRENT_TIMESTAMP
                WHERE administration = %s AND slug = %s
            """
            self.db.execute_query(
                query, (new_slug, administration, old_slug), fetch=False, commit=True
            )
            logger.info(
                "Renamed slug '%s' → '%s' for tenant '%s'",
                old_slug,
                new_slug,
                administration,
            )
        except IntegrityError:
            return {"success": False, "error": "Slug is already taken"}
        except DatabaseError as e:
            logger.error("Failed to update tenant_slugs: %s", e)
            return {"success": False, "error": "Failed to rename slug in database"}

        # Step 2: Migrate DynamoDB items
        try:
            from services.landing_page_service import LandingPageService

            lp_svc = LandingPageService()
            dynamo_result = lp_svc.migrate_slug(old_slug, new_slug)
            if not dynamo_result.get("success"):
                warnings.append(
                    f"DynamoDB migration failed: {dynamo_result.get('error', 'unknown')}"
                )
            elif dynamo_result.get("warnings"):
                warnings.extend(dynamo_result["warnings"])
        except Exception as e:
            warnings.append(f"DynamoDB migration error: {e}")
            logger.error(
                "DynamoDB migration failed for rename %s→%s: %s", old_slug, new_slug, e
            )

        # Step 3: Update tenant_custom_domains.slug
        try:
            self.db.execute_query(
                """
                UPDATE tenant_custom_domains
                SET slug = %s
                WHERE administration = %s AND slug = %s
                """,
                (new_slug, administration, old_slug),
                fetch=False,
                commit=True,
            )
        except DatabaseError as e:
            warnings.append(f"Failed to update tenant_custom_domains: {e}")
            logger.warning("tenant_custom_domains update failed: %s", e)

        # Step 4: Update s3_asset_references.entity_id
        try:
            self.db.execute_query(
                """
                UPDATE s3_asset_references
                SET entity_id = %s
                WHERE entity_type = 'landing_page'
                  AND entity_id = %s
                  AND administration = %s
                """,
                (new_slug, old_slug, administration),
                fetch=False,
                commit=True,
            )
        except DatabaseError as e:
            warnings.append(f"Failed to update s3_asset_references: {e}")
            logger.warning("s3_asset_references update failed: %s", e)

        # Step 5: Delete old S3 CDN files
        try:
            region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
            env = os.environ.get("ENVIRONMENT", "production")
            bucket = os.environ.get(
                "LANDING_PAGES_BUCKET", f"myadmin-public-pages-{env}"
            )
            s3_client = boto3.client("s3", region_name=region)
            for key in (f"{old_slug}/landing.json", f"{old_slug}/index.html"):
                try:
                    s3_client.delete_object(Bucket=bucket, Key=key)
                except ClientError as e:
                    warnings.append(f"Failed to delete S3 key {key}: {e}")
        except Exception as e:
            warnings.append(f"S3 cleanup error: {e}")
            logger.warning("S3 cleanup failed for old slug %s: %s", old_slug, e)

        # Step 6: Republish under new slug
        try:
            from services.landing_page_publish_service import LandingPagePublishService
            from services.landing_page_service import LandingPageService
            from services.parameter_service import ParameterService

            lp_svc = LandingPageService()
            param_svc = ParameterService(self.db)
            publish_svc = LandingPagePublishService(
                landing_page_service=lp_svc,
                parameter_service=param_svc,
                slug_service=self,
                db_manager=self.db,
            )
            publish_result = publish_svc.publish(administration, user_email or "system")
            if not publish_result.get("success"):
                warnings.append(
                    f"Republish failed: {publish_result.get('error', 'unknown')}"
                )
        except Exception as e:
            warnings.append(f"Republish error: {e}")
            logger.warning(
                "Republish failed after rename %s→%s: %s", old_slug, new_slug, e
            )

        # Step 7: Update CloudFront KVS if custom domain exists
        try:
            custom_domain_query = """
                SELECT domain FROM tenant_custom_domains
                WHERE administration = %s AND is_active = TRUE AND domain_type = 'custom'
            """
            domains = self.db.execute_query(custom_domain_query, (administration,))
            if domains:
                from services.cloudfront_domain_service import CloudFrontDomainService

                cf_svc = CloudFrontDomainService()
                for row in domains:
                    domain = row["domain"]
                    if not cf_svc.put_kvs_mapping(domain, new_slug):
                        warnings.append(
                            f"Failed to update KVS mapping for domain {domain}"
                        )
        except Exception as e:
            warnings.append(f"KVS update error: {e}")
            logger.warning(
                "KVS update failed for rename %s→%s: %s", old_slug, new_slug, e
            )

        # Step 8: Invalidate CloudFront cache for old slug
        try:
            distribution_id = os.environ.get(
                "CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID", ""
            )
            if distribution_id:
                cf_client = boto3.client(
                    "cloudfront",
                    region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"),
                )
                cf_client.create_invalidation(
                    DistributionId=distribution_id,
                    InvalidationBatch={
                        "Paths": {
                            "Quantity": 2,
                            "Items": [f"/{old_slug}/*", f"/{old_slug}"],
                        },
                        "CallerReference": f"rename-{old_slug}-{new_slug}-{int(__import__('time').time())}",
                    },
                )
        except Exception as e:
            warnings.append(f"CloudFront invalidation error: {e}")
            logger.warning(
                "CloudFront invalidation failed for old slug %s: %s", old_slug, e
            )

        return {
            "success": True,
            "slug": new_slug,
            "renamed_from": old_slug,
            "warnings": warnings,
        }
