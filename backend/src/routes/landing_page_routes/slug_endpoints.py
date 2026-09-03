"""Slug management endpoints (get/set/validate the tenant slug).

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
        service = pkg._get_slug_service()
        slug = service.get_slug(tenant)

        return jsonify({"success": True, "data": {"slug": slug}})

    except Exception as e:
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

        service = pkg._get_slug_service()
        result = service.set_slug(tenant, slug, user_email=user_email)

        if result["success"]:
            logger.info(f"Slug set to '{slug}' for tenant {tenant} by {user_email}")
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:
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

        service = pkg._get_slug_service()
        result = service.validate_slug(slug, current_administration=tenant)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error validating slug for tenant {tenant}: {e}")
        return jsonify({"valid": False, "error": str(e)}), 500
