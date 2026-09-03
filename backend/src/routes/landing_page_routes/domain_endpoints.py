"""Domain configuration endpoints (Jabaki subdomain + custom domain lifecycle).

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
        service = pkg._get_domain_service()
        result = service.get_domains(tenant)

        return jsonify({"success": True, "data": result}), 200

    except Exception as e:
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
        service = pkg._get_domain_service()
        result = service.enable_jabaki(tenant)

        if result["success"]:
            logger.info(f"Jabaki subdomain enabled for tenant {tenant} by {user_email}")
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error enabling Jabaki for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/domains/jabaki/disable", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def disable_jabaki(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Disable the Jabaki subdomain for the authenticated tenant.

    Sets jabaki_enabled = false in tenant_slugs.

    Authorization: Tenant_Admin role required

    Returns:
        JSON with success status and message
    """
    try:
        service = pkg._get_domain_service()
        result = service.disable_jabaki(tenant)

        if result["success"]:
            logger.info(
                f"Jabaki subdomain disabled for tenant {tenant} by {user_email}"
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
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
            return jsonify({"success": False, "error": "Domain cannot be empty"}), 400

        service = pkg._get_domain_service()
        result = service.register_custom_domain(tenant, domain)

        if result["success"]:
            logger.info(
                f"Custom domain '{domain}' registered for tenant "
                f"{tenant} by {user_email}"
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error registering custom domain for tenant {tenant}: {e}")
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
        service = pkg._get_domain_service()
        result = service.verify_custom_domain(tenant)

        if result["success"]:
            logger.info(
                f"Custom domain verification checked for tenant "
                f"{tenant} by {user_email}"
            )
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error verifying custom domain for tenant {tenant}: {e}")
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
        service = pkg._get_domain_service()
        result = service.remove_custom_domain(tenant)

        if result["success"]:
            logger.info(f"Custom domain removed for tenant {tenant} by {user_email}")
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error removing custom domain for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
