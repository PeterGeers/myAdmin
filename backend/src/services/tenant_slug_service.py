"""
Tenant Slug Service

Manages the mapping between tenant administration identifiers and
public URL slugs for landing pages. Each tenant can have one unique slug
that serves as their public landing page URL: /p/{slug}
"""

import logging
import re

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

    def set_slug(self, administration: str, slug: str) -> dict:
        """
        Set or update the slug for a tenant.

        Validates the slug format and uniqueness before saving.
        Uses INSERT ... ON DUPLICATE KEY UPDATE to handle both
        new slugs and updates.

        Args:
            administration: The tenant administration identifier
            slug: The desired slug value

        Returns:
            Dict with 'success' and either 'slug' or 'error'
        """
        # Validate first
        validation = self.validate_slug(slug, current_administration=administration)
        if not validation["valid"]:
            return {"success": False, "error": validation["error"]}

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
