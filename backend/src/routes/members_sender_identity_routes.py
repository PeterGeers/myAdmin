"""
Members — Tenant Sender Identity Routes (R0, design §6.2)

Tenant-admin plane endpoints that let a tenant administrator verify/activate the
tenant's own SES sender email address and read its verification status. This is the
"tenant sender path" prerequisite for the Members mail output actions (R1–R5): the
verified sender resolved here is what the Members mail worker sends ``From`` for the
tenant.

Plane decision (task 0.2):
    SES identity verification already exists on the **Flask tenant-admin plane** as
    ``services.email_verification_service.EmailVerificationService`` (the ZZP
    sender-verification pattern): it drives SES ``VerifyEmailIdentity`` /
    ``GetIdentityVerificationAttributes`` and persists state in the MySQL
    ``email_verifications`` table keyed by ``administration`` (tenant isolation per
    steering 31). SES is a nonprofit-deploy service (steering 23). This endpoint
    therefore lives on the Flask plane and REUSES that service rather than
    reinventing identity verification on the SAM/DynamoDB Members plane — the SAM
    plane owns analytics-set / template DynamoDB data, not SES identity state.

Layering (steering 35 golden rule): thin route → service → DB. The route only
parses, authorizes, delegates to the service, and shapes the response; all SES calls
and persistence live in the service.

Endpoints (design §6.2):
    POST /api/members/sender-identities   — verify/activate a tenant sender address
                                             (drives SES VerifyEmailIdentity)
    GET  /api/members/sender-identities   — read current sender verification status

Authorization (steering 22, design §3 table): ``members:admin`` — the tenant-admin
capability. ``cognito_required`` expands the caller's verified tenant roles through
``ROLE_PERMISSIONS`` (``Members_CRUD`` grants ``members:admin``). The active tenant is
resolved from the verified token context (``tenant_required``), never from the body.
"""

import logging

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.email_verification_service import EmailVerificationService

logger = logging.getLogger(__name__)

# Capability that gates the tenant sender-identity surface (design §6.2 / §3 table).
# A tenant administrator manages their own tenant's sender; `members:admin` is the
# tenant-admin capability (granted by the Members_CRUD role).
CAP_MEMBERS_ADMIN = "members:admin"

members_sender_identity_bp = Blueprint("members_sender_identity", __name__)


@members_sender_identity_bp.route("/api/members/sender-identities", methods=["GET"])
@cognito_required(required_permissions=[CAP_MEMBERS_ADMIN])
@tenant_required()
def get_sender_identity(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Return the current sender-identity verification status for the active tenant.

    Reads SES verification attributes via the service (which syncs the cached DB
    status) and returns the resolved email + status. A tenant with no sender yet
    returns a null email/status (not an error) so the UI can offer "add a sender".

    Returns:
        200 ``{"success": true, "data": {"email", "status", "last_checked"}}``
        500 ``{"success": false, "error"}`` on an unexpected failure.
    """
    try:
        db = DatabaseManager()
        service = EmailVerificationService(db_manager=db)

        result = service.check_status(tenant)

        return jsonify(
            {
                "success": True,
                "data": {
                    "email": result.get("email"),
                    "status": result.get("status"),
                    "last_checked": result.get("last_checked"),
                },
            }
        ), 200

    except Exception as e:
        logger.error(
            f"Error reading sender identity for tenant {tenant}: {e}", exc_info=True
        )
        return jsonify({"success": False, "error": str(e)}), 500


@members_sender_identity_bp.route("/api/members/sender-identities", methods=["POST"])
@cognito_required(required_permissions=[CAP_MEMBERS_ADMIN])
@tenant_required()
def create_sender_identity(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Verify/activate a tenant sender address, driving SES ``VerifyEmailIdentity``.

    Request body::

        { "email": "sender@tenant.example" }

    The address is validated and verification is initiated via the service (SES
    sends its confirmation mail to the address). The tenant is always taken from the
    verified token context, never from the body (steering 22). If the tenant already
    has an active sender, the service replaces it (``update_email``) so a POST is the
    single "set/activate my sender" action.

    Returns:
        202 ``{"success": true, "data": {"email", "status"}}`` once verification is
            initiated (status is ``pending`` until the recipient confirms).
        400 ``{"success": false, "error"}`` on a missing/invalid email or a rejected
            SES call.
        500 ``{"success": false, "error"}`` on an unexpected failure.
    """
    try:
        data = request.get_json(silent=True)
        if not data or not (data.get("email") or "").strip():
            return jsonify({"success": False, "error": "email is required"}), 400

        email = data["email"].strip()

        db = DatabaseManager()
        service = EmailVerificationService(db_manager=db)

        # Reuse the service's "set the tenant's active sender" path: it marks any
        # existing active record replaced and initiates SES verification for the new
        # address. This keeps POST idempotent as "this is now my sender".
        result = service.update_email(tenant, email)

        if result.get("success"):
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "email": email,
                        "status": result.get("status", "pending"),
                    },
                }
            ), 202

        # Service surfaced a domain error (invalid format or a rejected SES call).
        return jsonify(
            {
                "success": False,
                "error": result.get("error", "Failed to verify sender identity"),
            }
        ), 400

    except Exception as e:
        logger.error(
            f"Error verifying sender identity for tenant {tenant}: {e}", exc_info=True
        )
        return jsonify({"success": False, "error": str(e)}), 500
