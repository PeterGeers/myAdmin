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

# CloudFront-managed certificate status -> the vocabulary DomainService uses.
# Everything else (validation-timed-out, failed, revoked, expired, inactive)
# is terminal and maps to "FAILED".
_CERT_STATUS_MAP = {
    "issued": "ISSUED",
    "pending-validation": "PENDING_VALIDATION",
}


class CloudFrontDomainService:
    """
    Service for AWS infrastructure operations related to custom domains.

    Manages ACM certificates, CloudFront distribution CNAMEs, and
    KeyValueStore domain-to-slug mappings.
    """

    def __init__(self):
        """Initialize AWS clients and load configuration from environment.

        The public-pages hosting (distributions, managed certificates, KVS)
        lives in the nonprofit account, while the Railway backend runs as a
        personal-account IAM user. When ``PUBLIC_PAGES_AWS_ROLE_ARN`` is set,
        every client here uses short-lived credentials from assuming that
        cross-account role (nonprofit-public-pages/hosting.tf).
        """
        region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
        self._client_kwargs = self._assumed_role_credentials()
        self._cloudfront = boto3.client(
            "cloudfront", region_name=region, **self._client_kwargs
        )
        self._acm = boto3.client("acm", region_name="us-east-1", **self._client_kwargs)
        self._kvs = None  # Lazy init — requires awscrt
        self._kvs_init_attempted = False
        # Multi-tenant distribution whose tenants are the custom domains
        # (nonprofit-public-pages/custom-domains.tf).
        self.custom_domains_distribution_id = os.environ.get(
            "CLOUDFRONT_CUSTOM_DOMAINS_DISTRIBUTION_ID", ""
        )
        # Separate KVS mapping the application-form host -> allowed embed origins
        # (CSP frame-ancestors). See infrastructure/application-form.tf.
        self.embed_origins_kvs_arn = os.environ.get(
            "CLOUDFRONT_EMBED_ORIGINS_KVS_ARN", ""
        )

    @staticmethod
    def _assumed_role_credentials() -> dict:
        """boto3 client kwargs for the cross-account role, or {} if unset."""
        role_arn = os.environ.get("PUBLIC_PAGES_AWS_ROLE_ARN", "")
        if not role_arn:
            return {}
        creds = boto3.client("sts").assume_role(
            RoleArn=role_arn, RoleSessionName="myadmin-public-pages"
        )["Credentials"]
        return {
            "aws_access_key_id": creds["AccessKeyId"],
            "aws_secret_access_key": creds["SecretAccessKey"],
            "aws_session_token": creds["SessionToken"],
        }

    def _cli_env(self) -> dict | None:
        """Environment for AWS CLI subprocesses (carries assumed-role creds)."""
        if not self._client_kwargs:
            return None
        env = dict(os.environ)
        env["AWS_ACCESS_KEY_ID"] = self._client_kwargs["aws_access_key_id"]
        env["AWS_SECRET_ACCESS_KEY"] = self._client_kwargs["aws_secret_access_key"]
        env["AWS_SESSION_TOKEN"] = self._client_kwargs["aws_session_token"]
        return env

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
            self._kvs = boto3.client(
                "cloudfront-keyvaluestore", region_name=region, **self._client_kwargs
            )
            return self._kvs
        except Exception as e:
            logger.warning(
                f"cloudfront-keyvaluestore client not available (awscrt missing): {e}. "
                "Falling back to AWS CLI for KVS operations."
            )
            return None

    # ========================================================================
    # Custom domains = CloudFront distribution TENANTS
    # ========================================================================
    # Custom domains are NOT aliases on the `*.jabaki.nl` distribution. Each one
    # is a distribution tenant of a separate MULTI-TENANT distribution
    # (env CLOUDFRONT_CUSTOM_DOMAINS_DISTRIBUTION_ID, Terraform
    # nonprofit-public-pages/custom-domains.tf). The tenant carries:
    #   - the domain (e.g. "www.acme.nl");
    #   - parameter `slug`, used as origin path `/{{slug}}` in the shared bucket;
    #   - a CloudFront-MANAGED certificate, HTTP-validated by CloudFront itself
    #     (ValidationTokenHost=cloudfront) — so the tenant only adds ONE record:
    #     a CNAME from their domain to the connection-group routing endpoint.
    #
    # CloudFront only CREATES a tenant once the domain already points at the
    # routing endpoint ("Could not verify Domain Name ownership" otherwise). So
    # the CNAME target comes from the (default) connection group up front, and
    # tenant creation is retried by verify / the background job until DNS is in.

    @staticmethod
    def _tenant_name(domain: str) -> str:
        """Tenant names must be unique per account; the domain itself is."""
        return domain.lower()

    def get_routing_endpoint(self) -> str | None:
        """CNAME target for custom domains: the default connection group endpoint."""
        try:
            groups = self._cloudfront.list_connection_groups().get(
                "ConnectionGroups", []
            )
        except ClientError as e:
            logger.error(f"Failed to list connection groups: {e}")
            return None
        for group in groups:
            if group.get("IsDefault"):
                return group.get("RoutingEndpoint")
        logger.error("No default CloudFront connection group found")
        return None

    def create_domain_tenant(self, domain: str, slug: str) -> dict:
        """
        Create the distribution tenant for a custom domain.

        Returns:
            {"success": True, "tenant_id", "routing_endpoint"};
            {"success": False, "dns_not_ready": True, "error"} while the domain
            does not yet point at CloudFront; or {"success": False, "error"}.
        """
        if not self.custom_domains_distribution_id:
            logger.error("CLOUDFRONT_CUSTOM_DOMAINS_DISTRIBUTION_ID not set")
            return {"success": False, "error": "Custom domains are not configured."}
        try:
            tenant = self._cloudfront.create_distribution_tenant(
                DistributionId=self.custom_domains_distribution_id,
                Name=self._tenant_name(domain),
                Domains=[{"Domain": domain}],
                Parameters=[{"Name": "slug", "Value": slug}],
                Enabled=True,
                ManagedCertificateRequest={
                    "ValidationTokenHost": "cloudfront",
                    "PrimaryDomainName": domain,
                    "CertificateTransparencyLoggingPreference": "enabled",
                },
                Tags={"Items": [{"Key": "ManagedBy", "Value": "myadmin-backend"}]},
            )["DistributionTenant"]
            endpoint = self._routing_endpoint(tenant["ConnectionGroupId"])
            logger.info(f"Created distribution tenant {tenant['Id']} for {domain}")
            return {
                "success": True,
                "tenant_id": tenant["Id"],
                "routing_endpoint": endpoint,
            }
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code == "InvalidArgument" and "ownership" in str(e).lower():
                logger.info(f"Tenant for {domain} not created yet: DNS not pointing")
            else:
                logger.error(f"Failed to create distribution tenant for {domain}: {e}")
            if code == "CNAMEAlreadyExists":
                return {
                    "success": False,
                    "error": "This domain is already connected to another CloudFront site.",
                }
            if code == "InvalidArgument" and "ownership" in str(e).lower():
                # Expected until the tenant's CNAME points at CloudFront.
                return {
                    "success": False,
                    "dns_not_ready": True,
                    "error": "The DNS record does not point to CloudFront yet.",
                }
            return {"success": False, "error": "Failed to set up the custom domain."}

    def _routing_endpoint(self, connection_group_id: str) -> str:
        """The CloudFront hostname tenants point their CNAME at."""
        group = self._cloudfront.get_connection_group(Identifier=connection_group_id)
        return group["ConnectionGroup"]["RoutingEndpoint"]

    def _get_tenant_by_domain(self, domain: str):
        """Return (tenant, etag), or (None, None) if no tenant has this domain."""
        try:
            response = self._cloudfront.get_distribution_tenant_by_domain(Domain=domain)
            return response["DistributionTenant"], response.get("ETag")
        except ClientError as e:
            if e.response.get("Error", {}).get("Code", "") == "EntityNotFound":
                return None, None
            raise

    def get_domain_status(self, domain: str) -> dict:
        """
        Certificate status of a custom domain's tenant.

        Returns:
            {"success": True, "status": "ISSUED"|"PENDING_VALIDATION"|"FAILED",
             "certificate_arn"}; {"success": False, "not_found": True} when no
            tenant exists yet; or {"success": False, "error"}.
        """
        try:
            tenant, _ = self._get_tenant_by_domain(domain)
            if tenant is None:
                return {
                    "success": False,
                    "not_found": True,
                    "error": "Custom domain not found.",
                }
            details = self._cloudfront.get_managed_certificate_details(
                Identifier=tenant["Id"]
            ).get("ManagedCertificateDetails", {})
        except ClientError as e:
            logger.error(f"Failed to read status for {domain}: {e}")
            return {"success": False, "error": "Failed to check certificate status."}

        raw_status = details.get("CertificateStatus", "")
        return {
            "success": True,
            # validation-timed-out / failed / revoked / expired / inactive
            "status": _CERT_STATUS_MAP.get(raw_status, "FAILED"),
            "certificate_arn": details.get("CertificateArn"),
        }

    def update_domain_tenant_slug(self, domain: str, slug: str) -> bool:
        """Point an existing tenant at a renamed slug (origin path parameter)."""
        try:
            tenant, etag = self._get_tenant_by_domain(domain)
            if tenant is None:
                logger.warning(
                    f"No distribution tenant for {domain}; nothing to update"
                )
                return False
            self._cloudfront.update_distribution_tenant(
                Id=tenant["Id"],
                IfMatch=etag,
                Parameters=[{"Name": "slug", "Value": slug}],
            )
            logger.info(f"Updated slug of tenant {tenant['Id']} ({domain}) to {slug}")
            return True
        except ClientError as e:
            logger.error(f"Failed to update slug for {domain}: {e}")
            return False

    def delete_domain_tenant(self, domain: str) -> bool:
        """
        Disable and delete the tenant for a custom domain.

        A tenant must be disabled before it can be deleted. If the delete itself
        is refused (e.g. still propagating), the tenant stays DISABLED — it no
        longer serves traffic — and False is returned so the caller can log it.
        Returns True if no tenant exists (idempotent).
        """
        try:
            tenant, etag = self._get_tenant_by_domain(domain)
            if tenant is None:
                return True
            if tenant.get("Enabled", True):
                etag = self._cloudfront.update_distribution_tenant(
                    Id=tenant["Id"], IfMatch=etag, Enabled=False
                ).get("ETag", etag)
            self._cloudfront.delete_distribution_tenant(Id=tenant["Id"], IfMatch=etag)
            logger.info(f"Deleted distribution tenant {tenant['Id']} ({domain})")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete distribution tenant for {domain}: {e}")
            return False

    # ========================================================================
    # KeyValueStore Management (Task 4.5)
    # ========================================================================

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
                describe_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=self._cli_env(),
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
                put_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=self._cli_env(),
            )
            if result.returncode != 0:
                logger.error(f"AWS CLI put KVS key failed: {result.stderr}")
                return False

            logger.info(f"Put KVS mapping (CLI): {key} → {value}")
            return True
        except Exception as e:
            logger.error(f"CLI fallback failed for put KVS {key}: {e}")
            return False

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
                describe_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=self._cli_env(),
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
                delete_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=self._cli_env(),
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
