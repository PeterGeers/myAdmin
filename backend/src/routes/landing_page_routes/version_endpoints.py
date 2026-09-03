"""Version history, rollback, and publish/unpublish endpoints.

Handlers resolve shared helpers through the ``routes.landing_page_routes``
package namespace at call time so the test suite's
``patch('routes.landing_page_routes.<name>')`` calls keep working.
"""

import logging

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from routes import landing_page_routes as pkg

logger = logging.getLogger(__name__)

landing_page_bp = pkg.landing_page_bp


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
        slug_service = pkg._get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        service = pkg._get_landing_page_service()
        versions = service.list_versions(slug)

        return jsonify({"success": True, "data": versions})

    except Exception as e:
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
        slug_service = pkg._get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        service = pkg._get_landing_page_service()
        version_data = service.get_version(slug, version)

        if not version_data:
            return jsonify(
                {"success": False, "error": f"Version {version} not found"}
            ), 404

        return jsonify({"success": True, "data": version_data})

    except Exception as e:
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
        slug_service = pkg._get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        service = pkg._get_landing_page_service()

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

        pkg._record_audit_event(
            tenant=tenant,
            action="delete_version",
            version=version,
            performed_by=user_email,
            details=f"Deleted version {version}",
        )

        return jsonify({"success": True, "message": f"Version {version} deleted."})

    except Exception as e:
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

        slug_service = pkg._get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        # Step 1: Get the version snapshot from DynamoDB
        landing_svc = pkg._get_landing_page_service()
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
        publish_service = pkg._get_publish_service()
        result = publish_service.publish(tenant, published_by=user_email)

        if result["success"]:
            # Record audit event for rollback
            pkg._record_audit_event(
                tenant=tenant,
                action="rollback",
                version=result.get("version"),
                performed_by=user_email,
                details=f"Rolled back to version {target_version}",
            )
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error rolling back landing page for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


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
        service = pkg._get_publish_service()
        result = service.publish(tenant, published_by=user_email)

        if result["success"]:
            pkg._record_audit_event(
                tenant=tenant,
                action="publish",
                version=result.get("version"),
                performed_by=user_email,
                details=None,
            )
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:
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
        service = pkg._get_publish_service()
        result = service.unpublish(tenant, unpublished_by=user_email)

        if result["success"]:
            pkg._record_audit_event(
                tenant=tenant,
                action="unpublish",
                version=None,
                performed_by=user_email,
                details=None,
            )
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error unpublishing landing page for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
