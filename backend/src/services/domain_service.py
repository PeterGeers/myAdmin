"""
Domain Service

Manages domain configuration for tenant landing pages.
Provides read access to Jabaki subdomain status and custom domain
registration status for a given tenant. Supports enabling/disabling
the Jabaki subdomain (slug.jabaki.nl) for a tenant, and registering
custom domains with ACM certificate provisioning.
"""

import logging
import re

from database import DatabaseManager

logger = logging.getLogger(__name__)

# Domain validation regex: valid hostname characters (letters, digits, hyphens, dots)
# Must have at least one dot, cannot start/end with hyphen or dot per label
DOMAIN_REGEX = re.compile(
    r"^(?!-)"  # Cannot start with hyphen
    r"[a-z0-9]"  # Must start with letter or digit
    r"(?:[a-z0-9-]*[a-z0-9])?"  # Middle can have hyphens
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*"  # Additional labels
    r"\.[a-z]{2,}$"  # TLD at least 2 chars
)

# IPv4 pattern to reject IP addresses
IP_REGEX = re.compile(
    r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
)


class DomainService:
    """
    Service for managing tenant domain configurations.

    Handles querying Jabaki subdomain status and custom domain
    registration/verification status from the database.
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize the domain service.

        Args:
            db_manager: DatabaseManager instance for database operations
        """
        self.db = db_manager

    def get_domains(self, tenant: str) -> dict:
        """
        Get the domain configuration for a tenant.

        Returns Jabaki subdomain status and custom domain status,
        following the API contract defined in design.md.

        Args:
            tenant: Administration identifier (from @tenant_required)

        Returns:
            Dict with 'jabaki' and 'custom' domain status:
            {
                "jabaki": {
                    "enabled": bool,
                    "domain": str | None,
                    "status": str
                },
                "custom": {
                    "domain": str | None,
                    "status": str | None,
                    "is_active": bool,
                    "dns_instructions": dict | None
                }
            }
        """
        jabaki = self._get_jabaki_status(tenant)
        custom = self._get_custom_domain_status(tenant)

        return {
            "jabaki": jabaki,
            "custom": custom,
        }

    def enable_jabaki(self, tenant: str) -> dict:
        """
        Enable the Jabaki subdomain for a tenant.

        Validates that a slug exists for the tenant, then sets
        jabaki_enabled = TRUE and jabaki_enabled_at = NOW().

        Args:
            tenant: Administration identifier

        Returns:
            Dict with success, domain, and message on success.
            Dict with success=False and error on validation failure.
        """
        # Check that a slug exists for this tenant
        slug_query = """
            SELECT slug
            FROM tenant_slugs
            WHERE administration = %s
        """
        results = self.db.execute_query(slug_query, (tenant,))

        if not results or len(results) == 0 or not results[0].get("slug"):
            return {
                "success": False,
                "error": "No slug configured. Set a slug first.",
            }

        slug = results[0]["slug"]

        # Enable the Jabaki subdomain
        update_query = """
            UPDATE tenant_slugs
            SET jabaki_enabled = TRUE, jabaki_enabled_at = NOW()
            WHERE administration = %s
        """
        self.db.execute_query(update_query, (tenant,), fetch=False, commit=True)

        domain = f"{slug}.jabaki.nl"
        logger.info(f"Jabaki subdomain enabled for tenant {tenant}: {domain}")

        return {
            "success": True,
            "domain": domain,
            "message": "Jabaki subdomain is now active.",
        }

    def disable_jabaki(self, tenant: str) -> dict:
        """
        Disable the Jabaki subdomain for a tenant.

        Sets jabaki_enabled = FALSE. Does not remove the slug.

        Args:
            tenant: Administration identifier

        Returns:
            Dict with success and message.
        """
        update_query = """
            UPDATE tenant_slugs
            SET jabaki_enabled = FALSE
            WHERE administration = %s
        """
        self.db.execute_query(update_query, (tenant,), fetch=False, commit=True)

        logger.info(f"Jabaki subdomain disabled for tenant {tenant}")

        return {
            "success": True,
            "message": "Jabaki subdomain is now disabled.",
        }

    def register_custom_domain(self, tenant: str, domain: str) -> dict:
        """
        Register a custom domain for a tenant.

        Validates domain format, checks uniqueness, requests an ACM
        certificate, stores the record, and returns DNS instructions.

        Args:
            tenant: Administration identifier
            domain: The custom domain to register (e.g., "www.acme-rentals.nl")

        Returns:
            Dict with success, data (domain, status, dns_instructions) on success,
            or success=False with error message on failure.
        """
        # Step 1: Validate domain format
        validation_error = self._validate_domain_format(domain)
        if validation_error:
            return {"success": False, "error": validation_error}

        # Step 2: Check domain is not already registered
        existing_query = """
            SELECT id, administration
            FROM tenant_custom_domains
            WHERE domain = %s
        """
        existing = self.db.execute_query(existing_query, (domain,))
        if existing and len(existing) > 0:
            if existing[0]["administration"] == tenant:
                return {
                    "success": False,
                    "error": "This domain is already registered for your account.",
                }
            return {
                "success": False,
                "error": "This domain is already registered by another tenant.",
            }

        # Step 3: Get slug for tenant
        slug_query = """
            SELECT slug
            FROM tenant_slugs
            WHERE administration = %s
        """
        slug_results = self.db.execute_query(slug_query, (tenant,))
        if not slug_results or not slug_results[0].get("slug"):
            return {
                "success": False,
                "error": "No slug configured. Set a slug first.",
            }
        slug = slug_results[0]["slug"]

        # Step 4: Request ACM certificate
        from services.cloudfront_domain_service import CloudFrontDomainService

        cf_service = CloudFrontDomainService()
        cert_result = cf_service.request_certificate(domain)

        if not cert_result.get("success"):
            return {
                "success": False,
                "error": cert_result.get(
                    "error", "Failed to request SSL certificate."
                ),
            }

        certificate_arn = cert_result["certificate_arn"]
        validation_name = cert_result.get("validation_name")
        validation_value = cert_result.get("validation_value")

        # Step 5: Store in tenant_custom_domains
        insert_query = """
            INSERT INTO tenant_custom_domains
                (administration, slug, domain_type, domain,
                 acm_certificate_arn, dns_validation_name,
                 dns_validation_value, verification_status)
            VALUES (%s, %s, 'custom', %s, %s, %s, %s, 'pending_dns')
        """
        self.db.execute_query(
            insert_query,
            (
                tenant,
                slug,
                domain,
                certificate_arn,
                validation_name,
                validation_value,
            ),
            fetch=False,
            commit=True,
        )

        logger.info(
            f"Custom domain {domain} registered for tenant {tenant} "
            f"(cert: {certificate_arn})"
        )

        # Step 6: Build DNS instructions response
        cloudfront_domain = cf_service.cloudfront_domain
        dns_instructions = {
            "type": "CNAME",
            "records": [
                {
                    "purpose": "domain_verification",
                    "name": validation_name,
                    "value": validation_value,
                },
                {
                    "purpose": "routing",
                    "name": domain,
                    "value": cloudfront_domain,
                },
            ],
        }

        return {
            "success": True,
            "data": {
                "domain": domain,
                "status": "pending_dns",
                "dns_instructions": dns_instructions,
            },
        }

    def verify_custom_domain(self, tenant: str) -> dict:
        """
        Verify the custom domain certificate status and activate if issued.

        Checks ACM certificate status. If ISSUED, activates the domain by
        adding it to CloudFront and the KeyValueStore. If still pending,
        returns the current status with a helpful message.

        Args:
            tenant: Administration identifier

        Returns:
            Dict with success, data (domain, status, is_active, message)
        """
        # Query the custom domain record for this tenant
        query = """
            SELECT id, domain, slug, acm_certificate_arn, verification_status, is_active
            FROM tenant_custom_domains
            WHERE administration = %s AND domain_type = 'custom'
            ORDER BY created_at DESC
            LIMIT 1
        """
        results = self.db.execute_query(query, (tenant,))

        if not results or len(results) == 0:
            return {
                "success": False,
                "error": "No custom domain registered for this tenant.",
            }

        row = results[0]
        domain = row["domain"]
        slug = row["slug"]
        cert_arn = row["acm_certificate_arn"]
        record_id = row["id"]

        # If already active, return immediately
        if row.get("is_active"):
            return {
                "success": True,
                "data": {
                    "domain": domain,
                    "status": "issued",
                    "is_active": True,
                    "message": "Domain is verified and active.",
                },
            }

        # Check ACM certificate status
        from services.cloudfront_domain_service import CloudFrontDomainService

        cf_service = CloudFrontDomainService()
        cert_result = cf_service.describe_certificate(cert_arn)

        if not cert_result.get("success"):
            return {
                "success": False,
                "error": cert_result.get(
                    "error", "Failed to check certificate status."
                ),
            }

        status = cert_result["status"]

        if status == "ISSUED":
            # Activate the domain: add to CloudFront + KVS
            add_success = cf_service.add_domain_to_distribution(
                domain, cert_arn
            )
            if not add_success:
                return {
                    "success": False,
                    "error": "Failed to add domain to CloudFront distribution.",
                }

            kvs_success = cf_service.put_kvs_mapping(domain, slug)
            if not kvs_success:
                return {
                    "success": False,
                    "error": "Failed to update domain routing.",
                }

            # Update database: mark as active
            update_query = """
                UPDATE tenant_custom_domains
                SET verification_status = 'issued',
                    is_active = TRUE,
                    activated_at = NOW()
                WHERE id = %s AND administration = %s
            """
            self.db.execute_query(
                update_query, (record_id, tenant), fetch=False, commit=True
            )

            logger.info(
                f"Custom domain {domain} activated for tenant {tenant}"
            )

            return {
                "success": True,
                "data": {
                    "domain": domain,
                    "status": "issued",
                    "is_active": True,
                    "message": "Domain is verified and active.",
                },
            }

        elif status == "PENDING_VALIDATION":
            # Update status to validating
            update_query = """
                UPDATE tenant_custom_domains
                SET verification_status = 'validating'
                WHERE id = %s AND administration = %s
            """
            self.db.execute_query(
                update_query, (record_id, tenant), fetch=False, commit=True
            )

            return {
                "success": True,
                "data": {
                    "domain": domain,
                    "status": "validating",
                    "is_active": False,
                    "message": "DNS records detected. Certificate validation in progress (may take up to 30 minutes).",
                },
            }

        else:
            # FAILED or other status
            update_query = """
                UPDATE tenant_custom_domains
                SET verification_status = 'failed'
                WHERE id = %s AND administration = %s
            """
            self.db.execute_query(
                update_query, (record_id, tenant), fetch=False, commit=True
            )

            return {
                "success": True,
                "data": {
                    "domain": domain,
                    "status": "failed",
                    "is_active": False,
                    "message": f"Certificate validation failed (status: {status}). Please check your DNS records and try again.",
                },
            }

    def remove_custom_domain(self, tenant: str) -> dict:
        """
        Remove the custom domain for a tenant.

        Performs full cleanup: removes from CloudFront distribution,
        deletes ACM certificate, removes KVS mapping, and deletes
        the database record.

        Args:
            tenant: Administration identifier

        Returns:
            Dict with success and message.
        """
        # Query the custom domain record for this tenant
        query = """
            SELECT id, domain, acm_certificate_arn
            FROM tenant_custom_domains
            WHERE administration = %s AND domain_type = 'custom'
            ORDER BY created_at DESC
            LIMIT 1
        """
        results = self.db.execute_query(query, (tenant,))

        if not results or len(results) == 0:
            return {
                "success": False,
                "error": "No custom domain registered for this tenant.",
            }

        row = results[0]
        record_id = row["id"]
        domain = row["domain"]
        cert_arn = row.get("acm_certificate_arn")

        from services.cloudfront_domain_service import CloudFrontDomainService

        cf_service = CloudFrontDomainService()

        # Step 1: Remove domain from CloudFront distribution
        cf_service.remove_domain_from_distribution(domain)

        # Step 2: Delete KVS mapping
        cf_service.delete_kvs_mapping(domain)

        # Step 3: Delete ACM certificate (if exists)
        if cert_arn:
            cf_service.delete_certificate(cert_arn)

        # Step 4: Delete database record
        delete_query = """
            DELETE FROM tenant_custom_domains
            WHERE id = %s AND administration = %s
        """
        self.db.execute_query(
            delete_query, (record_id, tenant), fetch=False, commit=True
        )

        logger.info(
            f"Custom domain {domain} removed for tenant {tenant}"
        )

        return {
            "success": True,
            "message": "Custom domain removed.",
        }

    def _validate_domain_format(self, domain: str) -> str | None:
        """
        Validate custom domain format.

        Rules:
        - Must be a valid hostname (letters, digits, hyphens, dots)
        - Cannot be an IP address
        - Cannot end with .jabaki.nl
        - Must have at least one dot

        Args:
            domain: The domain to validate

        Returns:
            Error message string if invalid, None if valid.
        """
        if not domain:
            return "Domain is required."

        # Must have at least one dot
        if "." not in domain:
            return "Invalid domain format. Must include a TLD (e.g., example.nl)."

        # Cannot be an IP address
        if IP_REGEX.match(domain):
            return "IP addresses are not allowed. Please enter a domain name."

        # Cannot be a jabaki.nl subdomain
        if domain.endswith(".jabaki.nl") or domain == "jabaki.nl":
            return "Jabaki.nl subdomains cannot be registered as custom domains."

        # Must match valid hostname pattern
        if not DOMAIN_REGEX.match(domain):
            return (
                "Invalid domain format. Use only letters, digits, "
                "hyphens, and dots (e.g., www.example.nl)."
            )

        return None

    def _get_jabaki_status(self, tenant: str) -> dict:
        """
        Get Jabaki subdomain status for a tenant.

        Queries tenant_slugs for the slug and jabaki_enabled flag.

        Args:
            tenant: Administration identifier

        Returns:
            Dict with enabled, domain, and status fields
        """
        query = """
            SELECT slug, jabaki_enabled
            FROM tenant_slugs
            WHERE administration = %s
        """
        results = self.db.execute_query(query, (tenant,))

        if not results or len(results) == 0:
            return {
                "enabled": False,
                "domain": None,
                "status": "no_slug",
            }

        row = results[0]
        slug = row["slug"]
        enabled = bool(row.get("jabaki_enabled", False))

        if enabled and slug:
            domain = f"{slug}.jabaki.nl"
            status = "active"
        else:
            domain = f"{slug}.jabaki.nl" if slug else None
            status = "inactive"

        return {
            "enabled": enabled,
            "domain": domain,
            "status": status,
        }

    def _get_custom_domain_status(self, tenant: str) -> dict:
        """
        Get custom domain status for a tenant.

        Queries tenant_custom_domains for the custom domain record.
        Only returns domains with domain_type = 'custom'.

        Args:
            tenant: Administration identifier

        Returns:
            Dict with domain, status, is_active, and dns_instructions fields
        """
        query = """
            SELECT domain, verification_status, is_active,
                   dns_validation_name, dns_validation_value
            FROM tenant_custom_domains
            WHERE administration = %s AND domain_type = 'custom'
            ORDER BY created_at DESC
            LIMIT 1
        """
        results = self.db.execute_query(query, (tenant,))

        if not results or len(results) == 0:
            return {
                "domain": None,
                "status": None,
                "is_active": False,
                "dns_instructions": None,
            }

        row = results[0]
        domain = row["domain"]
        status = row["verification_status"]
        is_active = bool(row.get("is_active", False))

        # Include DNS instructions if domain is still pending verification
        dns_instructions = None
        if status in ("pending_dns", "validating") and row.get("dns_validation_name"):
            dns_instructions = {
                "type": "CNAME",
                "records": [
                    {
                        "purpose": "domain_verification",
                        "name": row["dns_validation_name"],
                        "value": row["dns_validation_value"],
                    },
                ],
            }

        return {
            "domain": domain,
            "status": status,
            "is_active": is_active,
            "dns_instructions": dns_instructions,
        }
