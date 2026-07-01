"""
Verification Routes

API endpoints for managing SES email verification per tenant.
Allows tenant admins to check verification status, resend verification emails,
and update the sender email address.

Endpoints:
- GET  /api/tenant-admin/sender-verification       — Return current verification status
- POST /api/tenant-admin/sender-verification/resend — Trigger verification resend
- PUT  /api/tenant-admin/sender-verification/email  — Update email and initiate verification
"""

import os
import logging

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.email_verification_service import EmailVerificationService

# Initialize logger
logger = logging.getLogger(__name__)

# Fallback sender constant
FALLBACK_SENDER = "myAdmin <support@jabaki.nl>"

# Create blueprint
verification_bp = Blueprint("verification", __name__)


@verification_bp.route("/api/tenant-admin/sender-verification", methods=["GET"])
@cognito_required(required_permissions=["tenant_admin"])
@tenant_required()
def get_verification_status(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Get the current sender email verification status for the authenticated tenant.

    Returns:
        JSON with verification status data including email, status,
        last_checked timestamp, and fallback sender info.
    """
    try:
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)
        service = EmailVerificationService(db_manager=db)

        result = service.check_status(tenant)

        return jsonify(
            {
                "success": True,
                "data": {
                    "email": result.get("email"),
                    "status": result.get("status"),
                    "last_checked": result.get("last_checked"),
                    "fallback_sender": FALLBACK_SENDER,
                },
            }
        ), 200

    except Exception as e:
        logger.error(f"Error getting verification status for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@verification_bp.route("/api/tenant-admin/sender-verification/resend", methods=["POST"])
@cognito_required(required_permissions=["tenant_admin"])
@tenant_required()
def resend_verification(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Resend the SES verification email for the authenticated tenant.

    Rate limited to one request per 60 seconds per tenant.

    Returns:
        JSON with success message or rate limit error (429).
    """
    try:
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)
        service = EmailVerificationService(db_manager=db)

        result = service.resend_verification(tenant)

        if result["success"]:
            return jsonify(
                {"success": True, "message": "Verification email resent"}
            ), 200
        else:
            # Rate limit error returns 429
            error_msg = result.get("error", "Resend failed")
            if "wait 60 seconds" in error_msg.lower():
                return jsonify({"success": False, "error": error_msg}), 429
            return jsonify({"success": False, "error": error_msg}), 400

    except Exception as e:
        logger.error(f"Error resending verification for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@verification_bp.route("/api/tenant-admin/sender-verification/email", methods=["PUT"])
@cognito_required(required_permissions=["tenant_admin"])
@tenant_required()
def update_sender_email(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Update the sender email address and initiate SES verification.

    Request body:
        { "email": "new-email@example.com" }

    Returns:
        JSON with the new email and its pending verification status.
    """
    try:
        data = request.get_json()

        if not data or not data.get("email"):
            return jsonify({"success": False, "error": "email is required"}), 400

        new_email = data["email"].strip()

        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)
        service = EmailVerificationService(db_manager=db)

        result = service.update_email(tenant, new_email)

        if result["success"]:
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "email": new_email,
                        "status": result.get("status", "pending"),
                    },
                }
            ), 200
        else:
            return jsonify(
                {
                    "success": False,
                    "error": result.get("error", "Failed to update email"),
                }
            ), 400

    except Exception as e:
        logger.error(f"Error updating sender email for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
