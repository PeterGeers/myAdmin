"""
CloudFront Domain Service

Manages AWS infrastructure operations for custom domain support:
- ACM certificate lifecycle (request, describe, delete)
- CloudFront distribution CNAME management (add/remove alternate domains)
- CloudFront KeyValueStore domain→slug mappings

This service is focused exclusively on AWS API calls.
Business logic and database operations belong in DomainService.
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class CloudFrontDomainService:
    """
    Service for AWS infrastructure operations related to custom domains.

    Manages ACM certificates, CloudFront distribution CNAMEs, and
    KeyValueStore domain-to-slug mappings.
    """

    def __init__(self):
        """Initialize AWS clients and load configuration from environment."""
        region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
        self._cloudfront = boto3.client("cloudfront", region_name=region)
        self._acm = boto3.client("acm", region_name="us-east-1")
        self._kvs = None  # Lazy init — requires awscrt
        self._kvs_init_attempted = False
        self.distribution_id = os.environ.get(
            "CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID", ""
        )
        self.kvs_arn = os.environ.get("CLOUDFRONT_KVS_ARN", "")
        # Separate KVS mapping the application-form host -> allowed embed origins
        # (CSP frame-ancestors). See infrastructure/application-form.tf.
        self.embed_origins_kvs_arn = os.environ.get(
            "CLOUDFRONT_EMBED_ORIGINS_KVS_ARN", ""
        )
        self.cloudfront_domain = os.environ.get("CLOUDFRONT_PUBLIC_PAGES_DOMAIN", "")

    def _get_kvs_client(self):
        """
        Lazily initialize the KVS client.

        The cloudfront-keyvaluestore client requires awscrt (SigV4A).
        If not available, falls back to AWS CLI subprocess calls.
        """
        if self._kvs is not None:
            return self._kvs

        if self._kvs_init_attempted:
            return None

        self._kvs_init_attempted = True
        try:
            region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
            self._kvs = boto3.client("cloudfront-keyvaluestore", region_name=region)
            return self._kvs
        except Exception as e:
            logger.warning(
                f"cloudfront-keyvaluestore client not available (awscrt missing): {e}. "
                "Falling back to AWS CLI for KVS operations."
            )
            return None

    # ========================================================================
    # CloudFront Distribution CNAME Management (Task 4.4)
    # ========================================================================

    def add_domain_to_distribution(self, domain: str, certificate_arn: str) -> bool:
        """
        Add a custom domain as an alternate domain name on the CloudFront
        distribution and associate its ACM certificate.

        Uses ETag-based optimistic locking to safely update the distribution.

        Args:
            domain: The custom domain to add (e.g., "www.acme-rentals.nl")
            certificate_arn: ARN of the ACM certificate for this domain

        Returns:
            True on success, False on failure
        """
        try:
            # Step 1: Get current distribution config with ETag
            response = self._cloudfront.get_distribution_config(Id=self.distribution_id)
            config = response["DistributionConfig"]
            etag = response["ETag"]

            # Step 2: Add domain to aliases if not already present
            aliases = config.get("Aliases", {"Quantity": 0, "Items": []})
            items = aliases.get("Items", [])

            if domain in items:
                logger.info(f"Domain {domain} already in distribution aliases")
                return True

            items.append(domain)
            aliases["Items"] = items
            aliases["Quantity"] = len(items)
            config["Aliases"] = aliases

            # Step 3: Update the distribution with ETag for optimistic locking
            self._cloudfront.update_distribution(
                DistributionConfig=config,
                Id=self.distribution_id,
                IfMatch=etag,
            )

            logger.info(
                f"Added domain {domain} to CloudFront distribution "
                f"{self.distribution_id}"
            )
            return True

        except ClientError as e:
            logger.error(
                f"Failed to add domain {domain} to CloudFront distribution: {e}"
            )
            return False

    def remove_domain_from_distribution(self, domain: str) -> bool:
        """
        Remove a custom domain from the CloudFront distribution's
        alternate domain names.

        Uses ETag-based optimistic locking to safely update the distribution.

        Args:
            domain: The custom domain to remove (e.g., "www.acme-rentals.nl")

        Returns:
            True on success, False on failure
        """
        try:
            # Step 1: Get current distribution config with ETag
            response = self._cloudfront.get_distribution_config(Id=self.distribution_id)
            config = response["DistributionConfig"]
            etag = response["ETag"]

            # Step 2: Remove domain from aliases
            aliases = config.get("Aliases", {"Quantity": 0, "Items": []})
            items = aliases.get("Items", [])

            if domain not in items:
                logger.info(
                    f"Domain {domain} not in distribution aliases, nothing to remove"
                )
                return True

            items.remove(domain)
            aliases["Items"] = items
            aliases["Quantity"] = len(items)
            config["Aliases"] = aliases

            # Step 3: Update the distribution with ETag for optimistic locking
            self._cloudfront.update_distribution(
                DistributionConfig=config,
                Id=self.distribution_id,
                IfMatch=etag,
            )

            logger.info(
                f"Removed domain {domain} from CloudFront distribution "
                f"{self.distribution_id}"
            )
            return True

        except ClientError as e:
            logger.error(
                f"Failed to remove domain {domain} from CloudFront distribution: {e}"
            )
            return False

    # ========================================================================
    # KeyValueStore Management (Task 4.5)
    # ========================================================================

    def put_kvs_mapping(self, domain: str, slug: str) -> bool:
        """
        Add or update a domain→slug mapping in the CloudFront KeyValueStore.

        This mapping is read by the CloudFront Function at the edge to
        resolve custom domains to tenant slugs.

        Uses boto3 client if awscrt is available, otherwise falls back
        to AWS CLI subprocess.

        Args:
            domain: The custom domain (e.g., "www.acme-rentals.nl")
            slug: The tenant slug (e.g., "acme-rentals")

        Returns:
            True on success, False on failure
        """
        if not self.kvs_arn:
            logger.warning("CLOUDFRONT_KVS_ARN not set — skipping KVS put")
            return True  # Non-fatal: KVS is optional for basic functionality

        kvs_client = self._get_kvs_client()

        if kvs_client:
            return self._put_kvs_boto3(kvs_client, domain, slug, self.kvs_arn)
        else:
            return self._put_kvs_cli(domain, slug, self.kvs_arn)

    def _put_kvs_boto3(self, kvs_client, key: str, value: str, kvs_arn: str) -> bool:
        """Put a key→value mapping in the given KVS using the boto3 client."""
        try:
            describe_response = kvs_client.describe_key_value_store(KvsARN=kvs_arn)
            etag = describe_response["ETag"]

            kvs_client.put_key(
                KvsARN=kvs_arn,
                Key=key,
                Value=value,
                IfMatch=etag,
            )
            logger.info(f"Put KVS mapping: {key} → {value}")
            return True
        except ClientError as e:
            logger.error(f"Failed to put KVS mapping {key} → {value}: {e}")
            return False

    def _put_kvs_cli(self, key: str, value: str, kvs_arn: str) -> bool:
        """Put a key→value mapping via AWS CLI subprocess (fallback when awscrt unavailable)."""
        import json
        import subprocess

        try:
            # Get current ETag
            describe_cmd = [
                "aws",
                "cloudfront-keyvaluestore",
                "describe-key-value-store",
                "--kvs-arn",
                kvs_arn,
                "--output",
                "json",
            ]
            result = subprocess.run(
                describe_cmd, capture_output=True, text=True, timeout=30, check=False
            )
            if result.returncode != 0:
                logger.error(f"AWS CLI describe KVS failed: {result.stderr}")
                return False

            etag = json.loads(result.stdout).get("ETag", "")

            # Put key
            put_cmd = [
                "aws",
                "cloudfront-keyvaluestore",
                "put-key",
                "--kvs-arn",
                kvs_arn,
                "--key",
                key,
                "--value",
                value,
                "--if-match",
                etag,
            ]
            result = subprocess.run(
                put_cmd, capture_output=True, text=True, timeout=30, check=False
            )
            if result.returncode != 0:
                logger.error(f"AWS CLI put KVS key failed: {result.stderr}")
                return False

            logger.info(f"Put KVS mapping (CLI): {key} → {value}")
            return True
        except Exception as e:
            logger.error(f"CLI fallback failed for put KVS {key}: {e}")
            return False

    def delete_kvs_mapping(self, domain: str) -> bool:
        """
        Delete a domain→slug mapping from the CloudFront KeyValueStore.

        Uses boto3 client if awscrt is available, otherwise falls back
        to AWS CLI subprocess.

        Args:
            domain: The custom domain to remove (e.g., "www.acme-rentals.nl")

        Returns:
            True on success, False on failure
        """
        if not self.kvs_arn:
            logger.warning("CLOUDFRONT_KVS_ARN not set — skipping KVS delete")
            return True  # Non-fatal

        kvs_client = self._get_kvs_client()

        if kvs_client:
            return self._delete_kvs_boto3(kvs_client, domain, self.kvs_arn)
        else:
            return self._delete_kvs_cli(domain, self.kvs_arn)

    def _delete_kvs_boto3(self, kvs_client, key: str, kvs_arn: str) -> bool:
        """Delete a key from the given KVS using the boto3 client."""
        try:
            describe_response = kvs_client.describe_key_value_store(KvsARN=kvs_arn)
            etag = describe_response["ETag"]

            kvs_client.delete_key(
                KvsARN=kvs_arn,
                Key=key,
                IfMatch=etag,
            )
            logger.info(f"Deleted KVS mapping for key: {key}")
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                logger.info(f"KVS key {key} not found, nothing to delete")
                return True
            logger.error(f"Failed to delete KVS mapping for {key}: {e}")
            return False

    def _delete_kvs_cli(self, key: str, kvs_arn: str) -> bool:
        """Delete a key via AWS CLI subprocess (fallback)."""
        import json
        import subprocess

        try:
            # Get current ETag
            describe_cmd = [
                "aws",
                "cloudfront-keyvaluestore",
                "describe-key-value-store",
                "--kvs-arn",
                kvs_arn,
                "--output",
                "json",
            ]
            result = subprocess.run(
                describe_cmd, capture_output=True, text=True, timeout=30, check=False
            )
            if result.returncode != 0:
                logger.error(f"AWS CLI describe KVS failed: {result.stderr}")
                return False

            etag = json.loads(result.stdout).get("ETag", "")

            # Delete key
            delete_cmd = [
                "aws",
                "cloudfront-keyvaluestore",
                "delete-key",
                "--kvs-arn",
                kvs_arn,
                "--key",
                key,
                "--if-match",
                etag,
            ]
            result = subprocess.run(
                delete_cmd, capture_output=True, text=True, timeout=30, check=False
            )
            if result.returncode != 0:
                # Key not found is OK
                if "ResourceNotFoundException" in result.stderr:
                    logger.info(f"KVS key {key} not found (CLI), nothing to delete")
                    return True
                logger.error(f"AWS CLI delete KVS key failed: {result.stderr}")
                return False

            logger.info(f"Deleted KVS mapping (CLI) for key: {key}")
            return True
        except Exception as e:
            logger.error(f"CLI fallback failed for delete KVS {key}: {e}")
            return False

    # ========================================================================
    # Application-Form Embed Origins KVS (CSP frame-ancestors) — task 5.2
    # ========================================================================
    # The application form is hosted on the same `*.jabaki.nl` CloudFront
    # distribution as the landing pages. A `viewer-response` CloudFront function
    # (infrastructure/application-form.tf) reads the form host's allowed embed
    # origins from a DEDICATED KVS and emits `Content-Security-Policy:
    # frame-ancestors <origins>`. These methods populate that KVS from the
    # tenant-authored `application_embed_origins` list (one source of truth,
    # also feeding the SAM public-API CORS — task 5.3).
    #
    # Key   = the form's public host (e.g. "tenant-member-application.jabaki.nl")
    # Value = space-separated origins exactly as a CSP frame-ancestors source
    #         list (e.g. "https://www.acme.nl https://portal.acme.nl").
    # An empty / absent list clears the mapping => standalone (no header, not
    # embeddable), matching the function's fail-closed default.

    @staticmethod
    def _format_frame_ancestors_value(origins) -> str:
        """Normalise an embed-origins list into the KVS value (space-separated).

        Collapses to a single space-joined string of non-blank origins. Returns
        "" when there is nothing to allow (caller then deletes the key).
        """
        if not origins:
            return ""
        if isinstance(origins, str):
            parts = origins.split()
        else:
            parts = [str(o).strip() for o in origins]
        return " ".join(p for p in parts if p)

    def put_application_embed_origins(self, form_host: str, origins) -> bool:
        """Set the allowed embed origins for an application-form host.

        `origins` is the tenant's `application_embed_origins` (a list of origin
        strings, or a pre-joined string). An empty/blank list DELETES the key
        so the form becomes standalone (not embeddable).

        Returns True on success (including the non-fatal "KVS ARN not set" case).
        """
        if not self.embed_origins_kvs_arn:
            logger.warning(
                "CLOUDFRONT_EMBED_ORIGINS_KVS_ARN not set — skipping embed-origins KVS put"
            )
            return True  # Non-fatal: KVS is optional for basic functionality

        value = self._format_frame_ancestors_value(origins)
        if not value:
            # No origins -> standalone: clear any existing mapping.
            return self.delete_application_embed_origins(form_host)

        kvs_client = self._get_kvs_client()
        if kvs_client:
            return self._put_kvs_boto3(
                kvs_client, form_host, value, self.embed_origins_kvs_arn
            )
        return self._put_kvs_cli(form_host, value, self.embed_origins_kvs_arn)

    def delete_application_embed_origins(self, form_host: str) -> bool:
        """Clear the embed-origins mapping for a form host (-> standalone).

        Returns True on success (including the non-fatal "KVS ARN not set" case).
        """
        if not self.embed_origins_kvs_arn:
            logger.warning(
                "CLOUDFRONT_EMBED_ORIGINS_KVS_ARN not set — skipping embed-origins KVS delete"
            )
            return True  # Non-fatal

        kvs_client = self._get_kvs_client()
        if kvs_client:
            return self._delete_kvs_boto3(
                kvs_client, form_host, self.embed_origins_kvs_arn
            )
        return self._delete_kvs_cli(form_host, self.embed_origins_kvs_arn)

    # ========================================================================
    # ACM Certificate Management
    # ========================================================================

    def request_certificate(self, domain: str) -> dict:
        """
        Request an ACM certificate for a custom domain using DNS validation.

        The certificate is requested in us-east-1 (required for CloudFront).
        Retries describe_certificate up to 3 times with 2s delay to allow
        AWS to populate the validation records.

        Args:
            domain: The domain to request a certificate for

        Returns:
            Dict with certificate_arn and validation records on success,
            or error information on failure.
        """
        import time

        try:
            response = self._acm.request_certificate(
                DomainName=domain,
                ValidationMethod="DNS",
                Tags=[
                    {"Key": "ManagedBy", "Value": "myadmin-backend"},
                    {"Key": "Domain", "Value": domain},
                ],
            )
            certificate_arn = response["CertificateArn"]

            # Retry describe_certificate — AWS needs a moment to populate
            # the DomainValidationOptions with ResourceRecord values
            validation_name = None
            validation_value = None

            for attempt in range(4):
                if attempt > 0:
                    time.sleep(2)

                cert_details = self._acm.describe_certificate(
                    CertificateArn=certificate_arn
                )
                cert = cert_details["Certificate"]

                validation_options = cert.get("DomainValidationOptions", [])
                for option in validation_options:
                    resource_record = option.get("ResourceRecord", {})
                    if resource_record:
                        validation_name = resource_record.get("Name")
                        validation_value = resource_record.get("Value")
                        break

                if validation_name and validation_value:
                    break

                logger.info(
                    f"ACM validation records not yet available for {domain}, "
                    f"attempt {attempt + 1}/4"
                )

            logger.info(f"Requested ACM certificate for {domain}: {certificate_arn}")

            return {
                "success": True,
                "certificate_arn": certificate_arn,
                "validation_name": validation_name,
                "validation_value": validation_value,
            }

        except ClientError as e:
            logger.error(f"Failed to request ACM certificate for {domain}: {e}")
            return {
                "success": False,
                "error": f"Failed to request certificate: {e!s}",
            }

    def describe_certificate(self, certificate_arn: str) -> dict:
        """
        Describe an ACM certificate to check its current status.

        Args:
            certificate_arn: ARN of the certificate to describe

        Returns:
            Dict with status and validation options:
            {
                "success": True,
                "status": "ISSUED" | "PENDING_VALIDATION" | "FAILED" | ...,
                "validation_options": [...]
            }
        """
        try:
            response = self._acm.describe_certificate(CertificateArn=certificate_arn)
            cert = response["Certificate"]

            return {
                "success": True,
                "status": cert.get("Status"),
                "validation_options": cert.get("DomainValidationOptions", []),
            }

        except ClientError as e:
            logger.error(f"Failed to describe certificate {certificate_arn}: {e}")
            return {
                "success": False,
                "error": f"Failed to describe certificate: {e!s}",
            }

    def delete_certificate(self, certificate_arn: str) -> bool:
        """
        Delete an ACM certificate.

        Args:
            certificate_arn: ARN of the certificate to delete

        Returns:
            True on success, False on failure
        """
        try:
            self._acm.delete_certificate(CertificateArn=certificate_arn)
            logger.info(f"Deleted ACM certificate: {certificate_arn}")
            return True

        except ClientError as e:
            logger.error(f"Failed to delete certificate {certificate_arn}: {e}")
            return False
