"""SysAdmin landing page endpoints (manual domain verification trigger).

Handlers resolve shared helpers through the ``routes.landing_page_routes``
package namespace at call time so the test suite's
``patch('routes.landing_page_routes.<name>')`` calls keep working.
"""

import logging

from flask import jsonify
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from routes import landing_page_routes as pkg

logger = logging.getLogger(__name__)

landing_page_bp = pkg.landing_page_bp


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

        logger.info(f"Domain verification check triggered by {user_email}: {result}")

        return jsonify({"success": True, "data": result}), 200

    except Exception as e:
        logger.error(f"Error running domain verification check: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
