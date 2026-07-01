"""
SysAdmin Tenant Action Endpoints

API endpoints for tenant provisioning actions:
- Re-provisioning existing tenants
- Resending admin invitations

Split from sysadmin_tenants.py to keep files under 500 lines.
"""

from flask import Blueprint, request, jsonify
from flask.typing import ResponseReturnValue
from auth.cognito_utils import cognito_required
from database import DatabaseManager
import os
import logging

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
sysadmin_tenant_actions_bp = Blueprint("sysadmin_tenant_actions", __name__)


@sysadmin_tenant_actions_bp.route("/<administration>/reprovision", methods=["POST"])
@cognito_required(required_roles=["SysAdmin"])
def reprovision_tenant(user_email, user_roles, administration) -> ResponseReturnValue:
    """
    Re-provision an existing tenant to fill in missing pieces.

    Idempotent — skips steps already completed, fills in gaps:
    - Adds missing modules (skips existing)
    - Loads chart of accounts from template if no rows exist (skips if rows > 0)
    - Does NOT update the tenant record (use PUT endpoint for that)

    Authorization: SysAdmin role required

    Request body (all optional):
    {
        "locale": "nl",                          # Chart template locale (default: nl)
        "modules": ["FIN", "STR", "TENADMIN"]   # Modules to ensure exist (default: current modules)
    }

    Response:
    {
        "success": true,
        "administration": "TenantName",
        "provisioning": {
            "tenant": "skipped",
            "modules": [{"name": "FIN", "status": "skipped"}, ...],
            "chart": "created",
            "chart_rows": 44,
            "warnings": []
        }
    }
    """
    try:
        data = request.get_json() or {}

        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)

        # Verify tenant exists
        existing = db.execute_query(
            "SELECT administration, display_name, contact_email FROM tenants WHERE administration = %s",
            (administration,),
            fetch=True,
        )
        if not existing:
            return jsonify({"error": f"Tenant {administration} not found"}), 404

        tenant = existing[0]

        # Determine modules to ensure: use provided list or fall back to current modules
        if data.get("modules"):
            modules = data["modules"]
        else:
            current = db.execute_query(
                "SELECT module_name FROM tenant_modules WHERE administration = %s AND is_active = TRUE",
                (administration,),
                fetch=True,
            )
            modules = [m["module_name"] for m in current] if current else ["TENADMIN"]

        locale = data.get("locale", "nl")

        from services.tenant_provisioning_service import TenantProvisioningService

        service = TenantProvisioningService(db)

        results = service.create_and_provision_tenant(
            administration=administration,
            display_name=tenant["display_name"],
            contact_email=tenant["contact_email"],
            modules=modules,
            created_by=user_email,
            locale=locale,
        )

        logger.info(
            f"Re-provision '{administration}' by {user_email}: "
            f"tenant={results['tenant']}, chart={results['chart']} ({results['chart_rows']} rows)"
        )

        response = {
            "success": True,
            "administration": administration,
            "provisioning": results,
        }
        if results.get("warnings"):
            response["warnings"] = results["warnings"]

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error re-provisioning tenant {administration}: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@sysadmin_tenant_actions_bp.route(
    "/<administration>/resend-invitation", methods=["POST"]
)
@cognito_required(required_roles=["SysAdmin"])
def resend_invitation(user_email, user_roles, administration) -> ResponseReturnValue:
    """
    Resend the initial admin invitation for a tenant.

    Generates a new temporary password, updates the Cognito user to
    CONFIRMED status, creates or updates the invitation record, ensures
    a Tenant_Admin role row exists, and sends the invitation email.

    Handles pre-fix tenants that were provisioned without an initial
    admin user by creating the missing pieces on the fly.

    Authorization: SysAdmin role required

    Request body:
    {
        "email": "admin@example.com"
    }

    Response:
    {
        "success": true,
        "message": "Invitation resent",
        "email": "admin@example.com"
    }
    """
    try:
        data = request.get_json()

        if not data or not data.get("email"):
            return jsonify({"error": "Missing required field: email"}), 400

        email = data["email"].strip().lower()
        if not email:
            return jsonify({"error": "Email cannot be empty"}), 400

        # ── Verify tenant exists ────────────────────────────────────
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)

        tenant_row = db.execute_query(
            "SELECT administration, status FROM tenants WHERE administration = %s",
            (administration,),
            fetch=True,
        )
        if not tenant_row:
            return jsonify({"error": f"Tenant {administration} not found"}), 404

        if tenant_row[0].get("status") == "deleted":
            return jsonify({"error": f"Tenant {administration} has been deleted"}), 400

        # ── Service instances ───────────────────────────────────────
        from services.cognito_service import CognitoService
        from services.invitation_service import InvitationService
        from services.email_template_service import EmailTemplateService
        from services.ses_email_service import SESEmailService
        from utils.frontend_url import get_frontend_url

        cognito = CognitoService()
        invitation_service = InvitationService(test_mode=test_mode)
        email_template = EmailTemplateService(administration=administration)
        ses = SESEmailService()
        login_url = get_frontend_url()

        # ── Create / update invitation (generates new temp password) ─
        invitation = invitation_service.create_invitation(
            administration=administration,
            email=email,
            username=email,
            created_by=user_email,
            template_type="user_invitation",
        )
        if not invitation.get("success"):
            return jsonify(
                {
                    "error": f"Failed to create invitation: {invitation.get('error')}",
                }
            ), 500

        temp_password = invitation["temporary_password"]

        # ── Ensure Cognito user exists ──────────────────────────────
        cognito_user = cognito.get_user(email)

        if cognito_user is None:
            # Create Cognito user for pre-fix tenants that never had one
            cognito.create_user(
                email=email,
                tenant=administration,
                password=temp_password,
                suppress_email=True,
            )
        else:
            # Ensure tenant is in custom:tenants for existing users
            cognito.add_tenant_to_user(email, administration)

        # ── Set permanent password → keeps/moves status to CONFIRMED ─
        cognito.client.admin_set_user_password(
            UserPoolId=cognito.user_pool_id,
            Username=email,
            Password=temp_password,
            Permanent=True,
        )

        # ── Ensure Tenant_Admin role exists ─────────────────────────
        existing_role = db.execute_query(
            """
            SELECT id FROM user_tenant_roles
            WHERE email = %s AND administration = %s AND role = 'Tenant_Admin'
            """,
            (email, administration),
            fetch=True,
        )
        if not existing_role:
            db.execute_query(
                """
                INSERT INTO user_tenant_roles (email, administration, role, created_by)
                VALUES (%s, %s, 'Tenant_Admin', %s)
                """,
                (email, administration, user_email),
                fetch=False,
                commit=True,
            )
            logger.info(
                f"Created missing Tenant_Admin role for {email} in '{administration}'"
            )

        # ── Send invitation email (auto-detects locale) ─────────────
        html_body = email_template.render_user_invitation(
            email=email,
            temporary_password=temp_password,
            tenant=administration,
            login_url=login_url,
            format="html",
        )
        text_body = email_template.render_user_invitation(
            email=email,
            temporary_password=temp_password,
            tenant=administration,
            login_url=login_url,
            format="txt",
        )
        subject = email_template.get_invitation_subject(administration)

        send_result = ses.send_invitation(
            to_email=email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            administration=administration,
            sent_by=user_email,
        )

        if send_result.get("success"):
            invitation_service.mark_invitation_sent(
                administration=administration,
                email=email,
            )
        else:
            invitation_service.mark_invitation_failed(
                administration=administration,
                email=email,
                error_message=f"SES send failed: {send_result.get('error')}",
            )
            return jsonify(
                {
                    "error": f"Failed to send invitation email: {send_result.get('error')}",
                }
            ), 500

        logger.info(
            f"Invitation resent for {email} in '{administration}' by {user_email}"
        )

        return jsonify(
            {
                "success": True,
                "message": "Invitation resent",
                "email": email,
            }
        )

    except Exception as e:
        logger.error(f"Error resending invitation for {administration}: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
