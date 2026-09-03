"""Draft editing endpoints (load/save the current landing page draft).

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
        slug_service = pkg._get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        service = pkg._get_landing_page_service()
        draft = service.get_draft(slug)

        return jsonify({"success": True, "data": draft})

    except Exception as e:
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

        slug_service = pkg._get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {"success": False, "error": "No slug configured for this tenant"}
            ), 400

        service = pkg._get_landing_page_service()
        result = service.save_draft(slug, sections, modified_by=user_email)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 500

    except Exception as e:
        logger.error(f"Error saving draft for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
