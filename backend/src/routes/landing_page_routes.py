"""
Landing Page Routes

This module provides API endpoints for managing tenant landing page slugs,
draft editing, publishing/unpublishing landing pages, version history,
rollback, image uploads, resolving slugs for public delivery, and domain
configuration.

Endpoints:
- GET  /api/landing/slug              - Get current tenant's slug
- PUT  /api/landing/slug              - Set/update tenant's slug
- POST /api/landing/slug/validate     - Validate slug format + availability
- GET  /api/landing/domains           - Get Jabaki + custom domain status
- POST /api/landing/domains/jabaki/enable  - Enable Jabaki subdomain
- POST /api/landing/domains/jabaki/disable - Disable Jabaki subdomain
- POST /api/landing/domains/custom         - Register custom domain
- POST /api/landing/domains/custom/verify  - Verify custom domain cert status
- DELETE /api/landing/domains/custom        - Remove custom domain
- GET  /api/landing/draft             - Load current draft from DynamoDB
- PUT  /api/landing/draft             - Save draft to DynamoDB (auto-save)
- POST /api/landing/publish           - Publish current draft to S3
- POST /api/landing/unpublish         - Take landing page offline
- GET  /api/landing/versions          - List published version history
- POST /api/landing/rollback          - Rollback to a previous version
- POST /api/landing/images/upload     - Upload image to public S3 bucket
- GET  /api/public/landing/resolve/<slug> - Public: resolve slug → administration
- POST /api/public/landing/<slug>/contact - Public: submit contact form inquiry

Note: Register this blueprint in app.py:
    from routes.landing_page_routes import landing_page_bp
    app.register_blueprint(landing_page_bp)
"""

import logging
import os
import re

from botocore.exceptions import ClientError
from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.domain_service import DomainService
from services.media_asset_service import MediaAssetService
from services.parameter_service import ParameterService
from services.tenant_slug_service import TenantSlugService

logger = logging.getLogger(__name__)

landing_page_bp = Blueprint("landing_page", __name__)


def _get_slug_service() -> TenantSlugService:
    """Create a TenantSlugService instance with current DB config."""
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    db = DatabaseManager(test_mode=test_mode)
    return TenantSlugService(db)


def _get_domain_service() -> DomainService:
    """Create a DomainService instance with current DB config."""
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    db = DatabaseManager(test_mode=test_mode)
    return DomainService(db)


def _record_audit_event(
    tenant: str,
    action: str,
    version: int | None,
    performed_by: str,
    details: str | None = None,
) -> None:
    """
    Record a landing page audit event in MySQL.

    Inserts into the landing_page_audit table. Failures are logged but
    never raised — audit must not break the main workflow.

    Args:
        tenant: Administration identifier
        action: Action type (publish, unpublish, rollback)
        version: Version number involved (nullable for unpublish)
        performed_by: Email of the user who performed the action
        details: Optional additional detail text
    """
    try:
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)
        query = """
            INSERT INTO landing_page_audit
                (administration, action, version, performed_by, details)
            VALUES (%s, %s, %s, %s, %s)
        """
        db.execute_query(
            query,
            (tenant, action, version, performed_by, details),
            fetch=False,
            commit=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to record audit event for tenant {tenant}: {e}")


# ============================================================================
# Admin Endpoints (Cognito auth + tenant_required)
# ============================================================================


@landing_page_bp.route("/api/landing/slug", methods=["GET"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def get_slug(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Get the current slug for the authenticated tenant.

    Authorization: Tenant_Admin role required

    Returns:
        JSON with success status and slug (or null if not set)
    """
    try:
        service = _get_slug_service()
        slug = service.get_slug(tenant)

        return jsonify({"success": True, "data": {"slug": slug}})

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting slug for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/slug", methods=["PUT"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def set_slug(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Set or update the slug for the authenticated tenant.

    Authorization: Tenant_Admin role required

    Request body:
        { "slug": "my-rental-company" }

    Returns:
        JSON with success status and slug or error message
    """
    try:
        data = request.get_json()

        if not data or "slug" not in data:
            return jsonify(
                {"success": False, "error": "Missing required field: slug"}
            ), 400

        slug = data["slug"].strip()

        if not slug:
            return jsonify({"success": False, "error": "Slug cannot be empty"}), 400

        service = _get_slug_service()
        result = service.set_slug(tenant, slug)

        if result["success"]:
            logger.info(f"Slug set to '{slug}' for tenant {tenant} by {user_email}")
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error setting slug for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/slug/validate", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def validate_slug(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Validate a slug for format correctness and availability.

    Authorization: Tenant_Admin role required

    Request body:
        { "slug": "my-rental-company" }

    Returns:
        JSON with valid (bool) and optionally error message
    """
    try:
        data = request.get_json()

        if not data or "slug" not in data:
            return jsonify(
                {"valid": False, "error": "Missing required field: slug"}
            ), 400

        slug = data["slug"].strip()

        service = _get_slug_service()
        result = service.validate_slug(slug, current_administration=tenant)

        return jsonify(result)

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error validating slug for tenant {tenant}: {e}")
        return jsonify({"valid": False, "error": str(e)}), 500


# ============================================================================
# Domain Endpoints (Cognito auth + tenant_required)
# ============================================================================


@landing_page_bp.route("/api/landing/domains", methods=["GET"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def get_domains(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Get domain configuration for the authenticated tenant.

    Returns the Jabaki subdomain status and custom domain status
    including verification state and DNS instructions if applicable.

    Authorization: Tenant_Admin role required

    Returns:
        JSON with success status and domain data
    """
    try:
        service = _get_domain_service()
        result = service.get_domains(tenant)

        return jsonify({"success": True, "data": result}), 200

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting domains for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/domains/jabaki/enable", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def enable_jabaki(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Enable the Jabaki subdomain for the authenticated tenant.

    Sets jabaki_enabled = true and jabaki_enabled_at = NOW() in
    tenant_slugs. The slug must already exist.

    Authorization: Tenant_Admin role required

    Returns:
        JSON with success status, domain URL, and message
    """
    try:
        service = _get_domain_service()
        result = service.enable_jabaki(tenant)

        if result["success"]:
            logger.info(
                f"Jabaki subdomain enabled for tenant {tenant} by {user_email}"
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error enabling Jabaki for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/domains/jabaki/disable", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def disable_jabaki(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Disable the Jabaki subdomain for the authenticated tenant.

    Sets jabaki_enabled = false in tenant_slugs.

    Authorization: Tenant_Admin role required

    Returns:
        JSON with success status and message
    """
    try:
        service = _get_domain_service()
        result = service.disable_jabaki(tenant)

        if result["success"]:
            logger.info(
                f"Jabaki subdomain disabled for tenant {tenant} by {user_email}"
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error disabling Jabaki for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/domains/custom", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def register_custom_domain(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Register a custom domain for the authenticated tenant.

    Validates domain format, requests an ACM certificate, stores the
    registration, and returns DNS instructions for the tenant to
    configure at their DNS provider.

    Authorization: Tenant_Admin role required

    Request body:
        { "domain": "www.acme-rentals.nl" }

    Returns:
        JSON with domain, status, and dns_instructions on success
    """
    try:
        data = request.get_json()

        if not data or "domain" not in data:
            return jsonify(
                {"success": False, "error": "Missing required field: domain"}
            ), 400

        domain = data["domain"].strip().lower()

        if not domain:
            return jsonify(
                {"success": False, "error": "Domain cannot be empty"}
            ), 400

        service = _get_domain_service()
        result = service.register_custom_domain(tenant, domain)

        if result["success"]:
            logger.info(
                f"Custom domain '{domain}' registered for tenant "
                f"{tenant} by {user_email}"
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:  # noqa: BLE001
        logger.error(
            f"Error registering custom domain for tenant {tenant}: {e}"
        )
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/domains/custom/verify", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def verify_custom_domain(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Verify the custom domain certificate and activate if issued.

    Checks ACM certificate status. If ISSUED, adds domain to CloudFront
    distribution, updates KeyValueStore mapping, and marks domain active.
    If still pending, returns current status with helpful message.

    Authorization: Tenant_Admin role required

    Returns:
        JSON with domain, status, is_active, and message
    """
    try:
        service = _get_domain_service()
        result = service.verify_custom_domain(tenant)

        if result["success"]:
            logger.info(
                f"Custom domain verification checked for tenant "
                f"{tenant} by {user_email}"
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:  # noqa: BLE001
        logger.error(
            f"Error verifying custom domain for tenant {tenant}: {e}"
        )
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/domains/custom", methods=["DELETE"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def delete_custom_domain(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Remove the custom domain for the authenticated tenant.

    Removes domain from CloudFront distribution CNAMEs, deletes
    ACM certificate, removes KeyValueStore mapping, and deletes
    the database record.

    Authorization: Tenant_Admin role required

    Returns:
        JSON with success status and message
    """
    try:
        service = _get_domain_service()
        result = service.remove_custom_domain(tenant)

        if result["success"]:
            logger.info(
                f"Custom domain removed for tenant {tenant} by {user_email}"
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:  # noqa: BLE001
        logger.error(
            f"Error removing custom domain for tenant {tenant}: {e}"
        )
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# Draft Endpoints (Cognito auth + tenant_required)
# ============================================================================


def _get_landing_page_service():
    """Create a LandingPageService instance."""
    from services.landing_page_service import LandingPageService

    return LandingPageService()


@landing_page_bp.route("/api/landing/draft", methods=["GET"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def get_draft(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Get the current draft for the authenticated tenant.

    Authorization: Tenant_Admin role required

    Returns:
        JSON with success status and draft data (or null if no draft exists)
    """
    try:
        slug_service = _get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        service = _get_landing_page_service()
        draft = service.get_draft(slug)

        return jsonify({"success": True, "data": draft})

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting draft for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/draft", methods=["PUT"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def save_draft(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Save/update the draft for the authenticated tenant (auto-save support).

    Authorization: Tenant_Admin role required

    Request body:
        { "sections": [...] }

    Returns:
        JSON with success, version, and last_modified
    """
    try:
        data = request.get_json()

        if not data or "sections" not in data:
            return jsonify(
                {"success": False, "error": "Missing required field: sections"}
            ), 400

        sections = data["sections"]

        if not isinstance(sections, list):
            return jsonify(
                {"success": False, "error": "Field 'sections' must be a list"}
            ), 400

        slug_service = _get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        service = _get_landing_page_service()
        result = service.save_draft(slug, sections, modified_by=user_email)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 500

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error saving draft for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# Publish Endpoints (Cognito auth + tenant_required)
# ============================================================================


def _get_publish_service():
    """Create a LandingPagePublishService instance with dependencies."""
    from services.landing_page_publish_service import LandingPagePublishService
    from services.landing_page_service import LandingPageService
    from services.parameter_service import ParameterService

    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    db = DatabaseManager(test_mode=test_mode)

    landing_page_svc = LandingPageService()
    param_svc = ParameterService(db)
    slug_svc = TenantSlugService(db)

    return LandingPagePublishService(
        landing_page_service=landing_page_svc,
        parameter_service=param_svc,
        slug_service=slug_svc,
        db_manager=db,
    )


# ============================================================================
# Version History & Rollback Endpoints (Task 4.1, 4.2)
# ============================================================================


@landing_page_bp.route("/api/landing/versions", methods=["GET"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def list_versions(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    List all published version snapshots for the tenant's landing page.

    Authorization: Tenant_Admin role required

    Returns:
        JSON with success and list of versions (version, published_at, published_by),
        sorted descending by version number.
    """
    try:
        slug_service = _get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        service = _get_landing_page_service()
        versions = service.list_versions(slug)

        return jsonify({"success": True, "data": versions})

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error listing versions for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/version/<int:version>", methods=["GET"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def get_version_detail(
    version, user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Get a specific version snapshot including sections (for preview).

    Authorization: Tenant_Admin role required

    Response (200):
        { "success": true, "data": { "version": 5, "published_at": "...",
          "published_by": "...", "sections": [...] } }
    """
    try:
        slug_service = _get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        service = _get_landing_page_service()
        version_data = service.get_version(slug, version)

        if not version_data:
            return jsonify(
                {"success": False, "error": f"Version {version} not found"}
            ), 404

        return jsonify({"success": True, "data": version_data})

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting version {version} for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/version/<int:version>", methods=["DELETE"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def delete_version(
    version, user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Delete a specific version snapshot from DynamoDB.

    Authorization: Tenant_Admin role required

    Response (200):
        { "success": true, "message": "Version 5 deleted." }
    """
    try:
        slug_service = _get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        service = _get_landing_page_service()

        # Verify version exists
        version_data = service.get_version(slug, version)
        if not version_data:
            return jsonify(
                {"success": False, "error": f"Version {version} not found"}
            ), 404

        # Delete the version item
        success = service.delete_version(slug, version)
        if not success:
            return jsonify(
                {"success": False, "error": f"Failed to delete version {version}"}
            ), 500

        _record_audit_event(
            tenant=tenant,
            action="delete_version",
            version=version,
            performed_by=user_email,
            details=f"Deleted version {version}",
        )

        return jsonify(
            {"success": True, "message": f"Version {version} deleted."}
        )

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error deleting version {version} for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/rollback", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def rollback_landing_page(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Rollback to a previous version: restores version snapshot as the draft,
    then runs the full publish flow.

    Authorization: Tenant_Admin role required

    Request body:
        { "version": 5 }

    Returns:
        Same response as publish endpoint (success, version, published_at, public_url).
    """
    try:
        data = request.get_json()

        if not data or "version" not in data:
            return jsonify(
                {"success": False, "error": "Missing required field: version"}
            ), 400

        target_version = data["version"]

        if not isinstance(target_version, int) or target_version < 1:
            return jsonify(
                {"success": False, "error": "Version must be a positive integer"}
            ), 400

        slug_service = _get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        # Step 1: Get the version snapshot from DynamoDB
        landing_svc = _get_landing_page_service()
        version_data = landing_svc.get_version(slug, target_version)

        if not version_data:
            return jsonify(
                {"success": False, "error": f"Version {target_version} not found"}
            ), 404

        # Step 2: Overwrite the current draft with the version's sections
        sections = version_data.get("sections", [])
        save_result = landing_svc.save_draft(slug, sections, modified_by=user_email)

        if not save_result.get("success"):
            return jsonify(
                {"success": False, "error": "Failed to restore version as draft"}
            ), 500

        # Step 3: Run the full publish flow
        publish_service = _get_publish_service()
        result = publish_service.publish(tenant, published_by=user_email)

        if result["success"]:
            # Record audit event for rollback
            _record_audit_event(
                tenant=tenant,
                action="rollback",
                version=result.get("version"),
                performed_by=user_email,
                details=f"Rolled back to version {target_version}",
            )
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error rolling back landing page for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# Publish Endpoints (Cognito auth + tenant_required)
# ============================================================================


@landing_page_bp.route("/api/landing/publish", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def publish_landing_page(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Publish the current draft landing page to S3.

    Authorization: Tenant_Admin role required

    Response (200):
        { "success": true, "version": 6, "published_at": "...", "public_url": "/p/slug" }
    """
    try:
        service = _get_publish_service()
        result = service.publish(tenant, published_by=user_email)

        if result["success"]:
            _record_audit_event(
                tenant=tenant,
                action="publish",
                version=result.get("version"),
                performed_by=user_email,
                details=None,
            )
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error publishing landing page for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/unpublish", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def unpublish_landing_page(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Take the landing page offline (delete from S3).

    Authorization: Tenant_Admin role required

    Response (200):
        { "success": true, "message": "Landing page is now offline." }
    """
    try:
        service = _get_publish_service()
        result = service.unpublish(tenant, unpublished_by=user_email)

        if result["success"]:
            _record_audit_event(
                tenant=tenant,
                action="unpublish",
                version=None,
                performed_by=user_email,
                details=None,
            )
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error unpublishing landing page for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# Image Upload Endpoints (Cognito auth + tenant_required)
# ============================================================================


@landing_page_bp.route("/api/landing/images/upload", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def upload_image(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Upload an image to the public S3 bucket via MediaAssetService.

    Authorization: Tenant_Admin role required

    Accepts multipart/form-data with a 'file' field.
    MediaAssetService validates file type (extension + magic bytes) and size.

    Returns:
        JSON with image_key and public URL on success, or error on failure.
    """
    try:
        # Validate file is present
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files["file"]

        if not file.filename:
            return jsonify({"success": False, "error": "No file selected"}), 400

        # Read file data
        file_data = file.read()

        # Get slug for tenant (used as entity_id for reference tracking)
        slug_service = _get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {
                    "success": False,
                    "error": "No slug configured for this tenant. Set a slug first.",
                }
            ), 400

        # Upload via MediaAssetService (handles validation, S3 upload, and registry)
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)
        ps = ParameterService(db)
        asset_svc = MediaAssetService(db, ps)

        result = asset_svc.store_and_register(
            tenant=tenant,
            file_data=file_data,
            filename=file.filename,
            category='landing-pages',
            entity_type='landing_page',
            entity_id=str(slug),
            metadata={'slug': slug},
        )

        if not result['success']:
            return jsonify({"success": False, "error": result.get('error', 'Upload failed')}), 400

        s3_key = result['asset']['s3_key']

        # Build public URL (CloudFront or direct S3)
        cloudfront_domain = os.environ.get("CLOUDFRONT_PUBLIC_PAGES_DOMAIN", "")
        if cloudfront_domain:
            url = f"https://{cloudfront_domain}/{s3_key}"
        else:
            env = os.environ.get("ENVIRONMENT", "production")
            bucket_name = os.environ.get(
                "LANDING_PAGES_BUCKET", f"myadmin-public-pages-{env}"
            )
            region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
            url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"

        logger.info(f"Image uploaded by {user_email} for tenant {tenant}: {s3_key}")

        return jsonify(
            {
                "success": True,
                "data": {
                    "image_key": s3_key,
                    "url": url,
                },
            }
        )

    except ValueError as e:
        # MediaAssetService raises ValueError for validation failures
        logger.warning(f"Image validation error for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 400
    except ClientError as e:
        logger.error(f"S3 upload error for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": "Failed to upload image"}), 500
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error uploading image for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename for safe S3 storage.
    Keeps only alphanumeric characters, hyphens, underscores, and dots.
    """
    import re

    # Get just the filename (not path)
    name = os.path.basename(filename)
    # Replace spaces with hyphens
    name = name.replace(" ", "-")
    # Remove any character that isn't alphanumeric, hyphen, underscore, or dot
    name = re.sub(r"[^a-zA-Z0-9\-_.]", "", name)
    # Collapse multiple hyphens/underscores
    name = re.sub(r"[-_]{2,}", "-", name)
    return name.lower()


def _sanitize_input(value: str) -> str:
    """
    Sanitize user input by stripping HTML tags to prevent stored XSS.

    Task 4.11 — Input sanitization on contact form fields.
    Strips all HTML/XML tags from the input, leaving only plain text content.
    Also normalizes excessive whitespace.

    Args:
        value: Raw user input string

    Returns:
        Sanitized string with HTML tags removed.
    """
    import html as html_module

    # Strip HTML tags
    clean = re.sub(r"<[^>]*>", "", value)
    # Unescape any HTML entities that might have been injected (e.g. &lt;script&gt;)
    clean = html_module.unescape(clean)
    # Strip again after unescape (in case entities decoded into tags)
    clean = re.sub(r"<[^>]*>", "", clean)
    # Normalize excessive whitespace (but preserve newlines for message readability)
    clean = re.sub(r"[ \t]+", " ", clean)
    return clean.strip()


# ============================================================================
# Branding / SEO / Social Settings Endpoints (Tasks 3.15, 3.16, 3.17, 3.22)
# ============================================================================

# All landing page settings keys stored in ParameterService (landing_page namespace)
BRANDING_KEYS = [
    "company_name",
    "tagline",
    "logo_url",
    "color_primary",
    "color_accent",
    "address",
    "postal_city",
    "country",
    "phone",
    "email",
    "coc",
    "vat",
    "font_heading",
    "font_body",
    "base_spacing",
    "border_radius_global",
    "shadow_style",
]
SEO_KEYS = ["seo_title", "seo_description", "og_image_url"]
SETTINGS_KEYS = ["social_links", "show_share_buttons"]


def _get_parameter_service():
    """Create a ParameterService instance."""
    from services.parameter_service import ParameterService

    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    db = DatabaseManager(test_mode=test_mode)
    return ParameterService(db)


@landing_page_bp.route("/api/landing/branding", methods=["GET"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def get_branding_settings(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Get all landing page settings (branding, social links, SEO).

    Returns all ParameterService values from the landing_page namespace
    that are relevant for branding, footer, social, and SEO configuration.

    Authorization: Tenant_Admin role required
    """
    try:
        import json as json_module

        param_svc = _get_parameter_service()
        result = {}

        # Load branding fields
        for key in BRANDING_KEYS:
            result[key] = param_svc.get_param("landing_page", key, tenant=tenant) or ""

        # Load SEO fields
        for key in SEO_KEYS:
            result[key] = param_svc.get_param("landing_page", key, tenant=tenant) or ""

        # Load social_links (stored as JSON string)
        social_raw = param_svc.get_param("landing_page", "social_links", tenant=tenant)
        if social_raw:
            if isinstance(social_raw, str):
                try:
                    result["social_links"] = json_module.loads(social_raw)
                except (json_module.JSONDecodeError, TypeError):
                    result["social_links"] = {}
            elif isinstance(social_raw, dict):
                result["social_links"] = social_raw
            else:
                result["social_links"] = {}
        else:
            result["social_links"] = {}

        # Load show_share_buttons
        show_share = param_svc.get_param(
            "landing_page", "show_share_buttons", tenant=tenant
        )
        result["show_share_buttons"] = show_share in ("true", "True", True)

        # Load theme (preset + overrides)
        theme_raw = param_svc.get_param("landing_page", "theme", tenant=tenant)
        if theme_raw:
            if isinstance(theme_raw, str):
                try:
                    result["theme"] = json_module.loads(theme_raw)
                except (json_module.JSONDecodeError, TypeError):
                    result["theme"] = {"preset": None, "overrides": {}}
            elif isinstance(theme_raw, dict):
                result["theme"] = theme_raw
            else:
                result["theme"] = {"preset": None, "overrides": {}}
        else:
            result["theme"] = {"preset": None, "overrides": {}}

        return jsonify({"success": True, "data": result})

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error loading branding settings for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/branding", methods=["PUT"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def save_branding_settings(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Save all landing page settings (branding, social links, SEO).

    Accepts a flat JSON body with branding, SEO, and social fields.
    Saves each field individually to ParameterService (landing_page namespace, tenant scope).

    Authorization: Tenant_Admin role required

    Request body:
        {
            "company_name": "Acme Rentals",
            "tagline": "Your holiday starts here",
            "logo_url": "https://...",
            "color_primary": "#2D5F8A",
            "color_accent": "#F4A261",
            "address": "...",
            "postal_city": "...",
            "country": "...",
            "phone": "...",
            "email": "...",
            "coc": "...",
            "vat": "...",
            "seo_title": "...",
            "seo_description": "...",
            "og_image_url": "...",
            "social_links": { "instagram": "...", ... },
            "show_share_buttons": true
        }
    """
    try:
        import json as json_module

        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        param_svc = _get_parameter_service()

        # Save branding fields (string values)
        for key in BRANDING_KEYS:
            if key in data:
                value = data[key] if data[key] is not None else ""
                param_svc.set_param(
                    scope="tenant",
                    scope_id=tenant,
                    namespace="landing_page",
                    key=key,
                    value=str(value),
                    value_type="string",
                    created_by=user_email,
                )

        # Save SEO fields (string values)
        for key in SEO_KEYS:
            if key in data:
                value = data[key] if data[key] is not None else ""
                param_svc.set_param(
                    scope="tenant",
                    scope_id=tenant,
                    namespace="landing_page",
                    key=key,
                    value=str(value),
                    value_type="string",
                    created_by=user_email,
                )

        # Save social_links as JSON string
        if "social_links" in data:
            social = data["social_links"]
            if isinstance(social, dict):
                # Filter out empty values
                social_clean = {k: v for k, v in social.items() if v}
                param_svc.set_param(
                    scope="tenant",
                    scope_id=tenant,
                    namespace="landing_page",
                    key="social_links",
                    value=json_module.dumps(social_clean),
                    value_type="string",
                    created_by=user_email,
                )

        # Save show_share_buttons
        if "show_share_buttons" in data:
            param_svc.set_param(
                scope="tenant",
                scope_id=tenant,
                namespace="landing_page",
                key="show_share_buttons",
                value="true" if data["show_share_buttons"] else "false",
                value_type="string",
                created_by=user_email,
            )

        # Save theme selection (preset + overrides)
        if "theme" in data:
            theme = data["theme"]
            if isinstance(theme, dict):
                theme_value = json_module.dumps({
                    "preset": theme.get("preset"),
                    "overrides": theme.get("overrides", {}),
                })
                param_svc.set_param(
                    scope="tenant",
                    scope_id=tenant,
                    namespace="landing_page",
                    key="theme",
                    value=theme_value,
                    value_type="string",
                    created_by=user_email,
                )

        logger.info(f"Branding settings saved for tenant {tenant} by {user_email}")
        return jsonify({"success": True, "message": "Settings saved successfully"})

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error saving branding settings for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# Public Endpoints (no auth)
# ============================================================================


@landing_page_bp.route("/api/public/landing/resolve/<slug>", methods=["GET"])
def resolve_slug(slug: str) -> ResponseReturnValue:
    """
    Resolve a slug to its administration identifier.

    This is a public endpoint used by the landing page rendering system
    to look up which tenant a slug belongs to.

    No authentication required.

    Args:
        slug: The URL slug to resolve

    Returns:
        JSON with success and administration, or 404 if not found
    """
    try:
        service = _get_slug_service()
        administration = service.resolve_slug(slug)

        if administration:
            return jsonify(
                {"success": True, "data": {"administration": administration}}
            )
        else:
            return jsonify({"success": False, "error": "Slug not found"}), 404

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error resolving slug '{slug}': {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


# Basic email regex for server-side validation
_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _get_client_ip() -> str | None:
    """Get the client IP address, respecting X-Forwarded-For header."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr


def _check_rate_limit(
    db: DatabaseManager, email: str, ip_address: str | None
) -> str | None:
    """
    Check rate limits for contact form submissions.

    Limits:
        - 5 submissions per email per hour
        - 10 submissions per IP per hour

    Returns:
        None if within limits, or an error message string if rate-limited.
    """
    # Check email rate limit (5 per hour)
    email_count_query = """
        SELECT COUNT(*) AS cnt
        FROM landing_page_submissions
        WHERE visitor_email = %s
          AND created_at > NOW() - INTERVAL 1 HOUR
    """
    result = db.execute_query(email_count_query, (email,), fetch=True)
    if result and result[0].get("cnt", 0) >= 5:
        return "Too many requests. Please try again later."

    # Check IP rate limit (10 per hour)
    if ip_address:
        ip_count_query = """
            SELECT COUNT(*) AS cnt
            FROM landing_page_submissions
            WHERE ip_address = %s
              AND created_at > NOW() - INTERVAL 1 HOUR
        """
        result = db.execute_query(ip_count_query, (ip_address,), fetch=True)
        if result and result[0].get("cnt", 0) >= 10:
            return "Too many requests. Please try again later."

    return None


def _verify_recaptcha(token: str, client_ip: str | None) -> str | None:
    """
    Verify a reCAPTCHA v3 token with Google's API.

    Task 4.9 — Optional CAPTCHA verification. If RECAPTCHA_SECRET_KEY is not
    configured, verification is skipped (graceful degradation).

    Args:
        token: The reCAPTCHA response token from the frontend
        client_ip: Client IP address for additional verification

    Returns:
        None if verification passes (or is skipped), error message string if failed.
    """
    import urllib.parse
    import urllib.request

    secret_key = os.environ.get("RECAPTCHA_SECRET_KEY")
    if not secret_key:
        # CAPTCHA not configured — skip verification (graceful degradation)
        logger.debug("RECAPTCHA_SECRET_KEY not set, skipping CAPTCHA verification")
        return None

    try:
        verify_url = "https://www.google.com/recaptcha/api/siteverify"
        payload = urllib.parse.urlencode(
            {
                "secret": secret_key,
                "response": token,
                **({"remoteip": client_ip} if client_ip else {}),
            }
        ).encode("utf-8")

        req = urllib.request.Request(verify_url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            import json as json_module

            result = json_module.loads(resp.read().decode("utf-8"))

        if not result.get("success"):
            logger.warning(
                "reCAPTCHA verification failed: %s", result.get("error-codes")
            )
            return "CAPTCHA verification failed. Please try again."

        # Check score threshold (reCAPTCHA v3 returns 0.0–1.0)
        score = result.get("score", 0.0)
        min_score = float(os.environ.get("RECAPTCHA_MIN_SCORE", "0.5"))
        if score < min_score:
            logger.warning(
                "reCAPTCHA score too low: %.2f (min: %.2f)", score, min_score
            )
            return "CAPTCHA verification failed. Please try again."

        return None

    except Exception as e:  # noqa: BLE001
        # On verification error, allow the submission (graceful degradation)
        logger.error("reCAPTCHA verification error: %s", e)
        return None


def _send_contact_notification(
    administration: str, visitor_name: str, visitor_email: str, message: str
) -> None:
    """
    Send an email notification to the tenant about a new contact form submission.

    Uses ParameterService to look up the tenant's contact email from the
    landing_page namespace ('email' key). Falls back silently if no email is
    configured or if SES fails.
    """
    try:
        from datetime import datetime, timezone

        from services.parameter_service import ParameterService
        from services.ses_email_service import SESEmailService

        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)
        param_svc = ParameterService(db)

        # Get tenant contact email from landing_page namespace
        tenant_email = param_svc.get_param(
            "landing_page", "email", tenant=administration
        )

        if not tenant_email:
            logger.info(
                f"No contact email configured for tenant '{administration}', "
                f"skipping notification."
            )
            return

        # Build notification email (HTML-escape values to prevent email XSS)
        import html as html_module

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        subject = f"Nieuw contactformulier bericht van {visitor_name}"

        text_body = (
            f"Nieuw bericht via contactformulier\n"
            f"{'=' * 40}\n\n"
            f"Naam:    {visitor_name}\n"
            f"Email:   {visitor_email}\n"
            f"Datum:   {timestamp}\n\n"
            f"Bericht:\n{message}\n"
        )

        safe_name = html_module.escape(visitor_name)
        safe_email = html_module.escape(visitor_email)
        safe_message = html_module.escape(message)

        html_body = (
            f"<h2>Nieuw bericht via contactformulier</h2>"
            f"<table style='border-collapse:collapse;'>"
            f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold;'>Naam:</td>"
            f"<td>{safe_name}</td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold;'>Email:</td>"
            f"<td><a href='mailto:{safe_email}'>{safe_email}</a></td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold;'>Datum:</td>"
            f"<td>{timestamp}</td></tr>"
            f"</table>"
            f"<h3>Bericht:</h3>"
            f"<p style='white-space:pre-wrap;'>{safe_message}</p>"
        )

        ses = SESEmailService()
        result = ses.send_email(
            to_email=tenant_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            email_type="contact_form",
            administration=administration,
        )

        if result["success"]:
            logger.info(
                f"Contact notification sent to {tenant_email} for tenant '{administration}'"
            )
        else:
            logger.warning(
                f"Failed to send contact notification to {tenant_email}: "
                f"{result.get('error')}"
            )

    except Exception as e:  # noqa: BLE001
        # Never fail the submission because of notification errors
        logger.error(
            f"Error sending contact notification for tenant '{administration}': {e}"
        )


@landing_page_bp.route("/api/public/landing/<slug>/contact", methods=["POST"])
def submit_contact(slug: str) -> ResponseReturnValue:
    """
    Submit a contact form inquiry for a public landing page.

    No authentication required — this is a public endpoint.

    Flow:
        1. Honeypot check (silently reject bots)
        2. Validate required fields + email format
        3. Resolve slug → administration
        4. Rate limiting (5/email/hour, 10/IP/hour)
        5. Store submission in landing_page_submissions
        6. Send SES notification to tenant (async, non-blocking)

    Args:
        slug: The landing page URL slug

    Returns:
        JSON with success message, or error details
    """
    try:
        data = request.get_json(silent=True)

        if not data:
            return jsonify({"success": False, "error": "Invalid request body"}), 400

        # Honeypot check — if filled, silently return success (don't reveal to bots)
        honeypot = data.get("honeypot", "")
        if honeypot:
            return jsonify({"success": True, "message": "Your message has been sent."})

        # Validate and sanitize required fields (Task 4.11 — strip HTML to prevent stored XSS)
        name = _sanitize_input((data.get("name") or "").strip())
        email = (
            data.get("email") or ""
        ).strip()  # Email validated by regex, no HTML expected
        message = _sanitize_input((data.get("message") or "").strip())

        if not name:
            return jsonify({"success": False, "error": "Name is required"}), 400

        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400

        if not message:
            return jsonify({"success": False, "error": "Message is required"}), 400

        # Validate email format
        if not _EMAIL_PATTERN.match(email):
            return jsonify({"success": False, "error": "Invalid email address"}), 400

        # Validate field lengths
        if len(name) > 200:
            return jsonify(
                {"success": False, "error": "Name is too long (max 200 characters)"}
            ), 400

        if len(email) > 200:
            return jsonify(
                {"success": False, "error": "Email is too long (max 200 characters)"}
            ), 400

        # Resolve slug → administration
        service = _get_slug_service()
        administration = service.resolve_slug(slug)

        if not administration:
            return jsonify({"success": False, "error": "Page not found"}), 404

        # Rate limiting
        client_ip = _get_client_ip()
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)

        rate_limit_msg = _check_rate_limit(db, email, client_ip)
        if rate_limit_msg:
            return jsonify({"success": False, "error": rate_limit_msg}), 429

        # CAPTCHA verification (Task 4.9 — optional reCAPTCHA v3)
        captcha_token = data.get("captcha_token")
        if captcha_token:
            captcha_error = _verify_recaptcha(captcha_token, client_ip)
            if captcha_error:
                return jsonify({"success": False, "error": captcha_error}), 400

        # Store submission
        insert_query = """
            INSERT INTO landing_page_submissions
                (administration, visitor_name, visitor_email, message, ip_address)
            VALUES (%s, %s, %s, %s, %s)
        """
        db.execute_query(
            insert_query,
            (administration, name, email, message, client_ip),
            fetch=False,
            commit=True,
        )

        logger.info(
            f"Contact form submission stored for tenant '{administration}' "
            f"from {email} (IP: {client_ip})"
        )

        # Send notification to tenant (non-blocking — errors are logged, not raised)
        _send_contact_notification(administration, name, email, message)

        return jsonify({"success": True, "message": "Your message has been sent."})

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error processing contact form for slug '{slug}': {e}")
        return jsonify(
            {
                "success": False,
                "error": "Failed to send message. Please try again later.",
            }
        ), 500


# ============================================================================
# SysAdmin Endpoints
# ============================================================================


@landing_page_bp.route("/api/sysadmin/domains/verify-pending", methods=["POST"])
@cognito_required(required_roles=["SysAdmin"])
@tenant_required(allow_sysadmin=True)
def run_verification_check(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Manually trigger the domain verification background job.

    Checks all pending custom domains and auto-activates those
    with issued certificates. Designed to be triggered by a
    sysadmin or scheduled daily via an external scheduler.

    Authorization: SysAdmin role required

    Returns:
        JSON with processed, activated, failed, and pending counts
    """
    try:
        from services.domain_verification_job import run_domain_verification_check

        result = run_domain_verification_check()

        logger.info(
            f"Domain verification check triggered by {user_email}: {result}"
        )

        return jsonify({"success": True, "data": result}), 200

    except Exception as e:  # noqa: BLE001
        logger.error(f"Error running domain verification check: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
