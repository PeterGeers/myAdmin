"""
Tenant Admin Template AI Assistance Routes

AI-powered fix suggestions, auto-fix application, and template deletion.
Split from tenant_admin_templates.py for file size management.

Endpoints:
- POST   /api/tenant-admin/templates/ai-help         - Get AI fix suggestions
- POST   /api/tenant-admin/templates/apply-ai-fixes  - Apply AI fixes
- DELETE /api/tenant-admin/templates/<template_type>  - Delete (deactivate) template
"""

import os
import logging
from typing import Dict, Any, List

from flask import Blueprint, request, jsonify
from flask.typing import ResponseReturnValue
from auth.cognito_utils import cognito_required
from auth.tenant_context import (
    get_current_tenant,
    get_user_tenants,
    is_tenant_admin,
)
from database import DatabaseManager

logger = logging.getLogger(__name__)

tenant_admin_template_ai_bp = Blueprint("tenant_admin_template_ai", __name__)

# Import valid types from main module
from routes.tenant_admin_templates import VALID_TEMPLATE_TYPES  # noqa: E402


@tenant_admin_template_ai_bp.route(
    "/api/tenant-admin/templates/ai-help", methods=["POST"]
)
@cognito_required(required_permissions=[])
def ai_help_template_endpoint(user_email, user_roles) -> ResponseReturnValue:
    """Get AI-powered fix suggestions for template errors (Tenant_Admin only)."""
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            jwt_token = auth_header.replace("Bearer ", "").strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({"error": "Invalid authorization"}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({"error": "Tenant admin access required"}), 403

        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required"}), 400

        template_type = data.get("template_type")
        template_content = data.get("template_content")
        validation_errors = data.get("validation_errors", [])
        required_placeholders = data.get("required_placeholders", [])

        if not template_type:
            return jsonify({"error": "template_type is required"}), 400

        if not template_content:
            return jsonify({"error": "template_content is required"}), 400

        if not validation_errors:
            return jsonify({"error": "validation_errors is required"}), 400

        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)

        from services.ai_template_assistant import AITemplateAssistant

        ai_assistant = AITemplateAssistant(db)

        result = ai_assistant.get_fix_suggestions(
            template_type=template_type,
            template_content=template_content,
            validation_errors=validation_errors,
            required_placeholders=required_placeholders,
            administration=tenant,
        )

        if result.get("success") and result.get("tokens_used"):
            logger.info(
                f"AUDIT: AI assistance used by {user_email} for {tenant}, "
                f"type={template_type}, tokens={result.get('tokens_used')}, "
                f"cost=${result.get('cost_estimate', 0):.4f}"
            )
        else:
            logger.warning(
                f"AUDIT: AI assistance failed for {user_email} in {tenant}, "
                f"type={template_type}, error={result.get('error', 'unknown')}"
            )

        if result.get("success"):
            return jsonify(result), 200
        else:
            generic_help = _get_generic_help(validation_errors, required_placeholders)
            return jsonify(
                {
                    "success": True,
                    "ai_suggestions": generic_help,
                    "fallback": True,
                    "message": "AI service unavailable, showing generic help",
                }
            ), 200

    except Exception as e:
        logger.error(f"Error getting AI help: {e}")

        try:
            generic_help = _get_generic_help(
                data.get("validation_errors", []), data.get("required_placeholders", [])
            )
            return jsonify(
                {
                    "success": True,
                    "ai_suggestions": generic_help,
                    "fallback": True,
                    "message": "Error occurred, showing generic help",
                }
            ), 200
        except Exception:
            return jsonify({"error": "Internal server error", "details": str(e)}), 500


@tenant_admin_template_ai_bp.route(
    "/api/tenant-admin/templates/apply-ai-fixes", methods=["POST"]
)
@cognito_required(required_permissions=[])
def apply_ai_fixes_endpoint(user_email, user_roles) -> ResponseReturnValue:
    """Apply AI-suggested fixes to template (Tenant_Admin only)."""
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            jwt_token = auth_header.replace("Bearer ", "").strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({"error": "Invalid authorization"}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({"error": "Tenant admin access required"}), 403

        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required"}), 400

        template_content = data.get("template_content")
        fixes = data.get("fixes", [])

        if not template_content:
            return jsonify({"error": "template_content is required"}), 400

        if not fixes:
            return jsonify({"error": "fixes is required"}), 400

        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)

        from services.ai_template_assistant import AITemplateAssistant

        ai_assistant = AITemplateAssistant(db)

        result = ai_assistant.apply_auto_fixes(
            template_content=template_content, fixes=fixes
        )

        fixes_applied = len([f for f in fixes if f.get("auto_fixable", False)])

        response = {
            "success": True,
            "fixed_template": result,
            "fixes_applied": fixes_applied,
            "message": f"Successfully applied {fixes_applied} fixes",
        }

        logger.info(
            f"AUDIT: AI fixes applied by {user_email} for {tenant}, "
            f"fixes_applied={fixes_applied}"
        )

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error applying AI fixes: {e}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@tenant_admin_template_ai_bp.route(
    "/api/tenant-admin/templates/<template_type>", methods=["DELETE"]
)
@cognito_required(required_permissions=[])
def delete_tenant_template_endpoint(
    template_type, user_email, user_roles
) -> ResponseReturnValue:
    """Delete (deactivate) a tenant-specific template (Tenant_Admin only).

    Soft-deletes the active tenant template by setting is_active = FALSE and
    status = 'archived'. The system will then fall back to the built-in default.
    """
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            jwt_token = auth_header.replace("Bearer ", "").strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({"error": "Invalid authorization"}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({"error": "Tenant admin access required"}), 403

        if template_type not in VALID_TEMPLATE_TYPES:
            return jsonify(
                {"error": "Invalid template type", "valid_types": VALID_TEMPLATE_TYPES}
            ), 400

        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)

        select_query = """
            SELECT template_file_id
            FROM tenant_template_config
            WHERE administration = %s AND template_type = %s AND is_active = TRUE
            LIMIT 1
        """
        result = db.execute_query(select_query, (tenant, template_type), fetch=True)

        if not result or len(result) == 0:
            return jsonify(
                {
                    "success": False,
                    "error": f"No active tenant template found for type: {template_type}",
                }
            ), 404

        deactivated_file_id = result[0].get("template_file_id")

        update_query = """
            UPDATE tenant_template_config
            SET is_active = FALSE, status = 'archived', updated_at = NOW()
            WHERE administration = %s AND template_type = %s AND is_active = TRUE
        """
        db.execute_query(
            update_query, (tenant, template_type), fetch=False, commit=True
        )

        logger.info(
            f"AUDIT: Template deactivated by {user_email} for {tenant}, "
            f"type={template_type}, file_id={deactivated_file_id}"
        )

        return jsonify(
            {
                "success": True,
                "message": "Template deactivated successfully. System will use default template.",
                "template_type": template_type,
                "deactivated_file_id": deactivated_file_id,
            }
        ), 200

    except Exception as e:
        logger.error(f"Error deleting tenant template: {e}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# ============================================================================
# Helper Functions
# ============================================================================


def _get_generic_help(
    validation_errors: List[Dict], required_placeholders: List[str]
) -> Dict[str, Any]:
    """Generate generic help when AI service is unavailable."""
    fixes = []

    for error in validation_errors:
        error_type = error.get("type", "unknown")

        if error_type == "missing_placeholder":
            placeholder = error.get("placeholder", "unknown")
            fixes.append(
                {
                    "issue": f"Missing placeholder: {placeholder}",
                    "suggestion": f"Add {{{{ {placeholder} }}}} to your template where you want to display this value",
                    "code_example": f"<p>{{{{ {placeholder} }}}}</p>",
                    "location": "anywhere in template body",
                    "confidence": "high",
                }
            )

        elif error_type == "security_error":
            fixes.append(
                {
                    "issue": error.get("message", "Security issue detected"),
                    "suggestion": "Remove script tags and event handlers from your template. Use CSS for styling instead.",
                    "code_example": '<!-- Remove: <script>...</script> and onclick="..." -->',
                    "location": "throughout template",
                    "confidence": "high",
                }
            )

        elif error_type == "syntax_error":
            fixes.append(
                {
                    "issue": error.get("message", "HTML syntax error"),
                    "suggestion": "Check for unclosed or mismatched HTML tags. Ensure all opening tags have corresponding closing tags.",
                    "code_example": "<!-- Correct: <div>content</div> -->",
                    "location": error.get("line", "unknown line"),
                    "confidence": "medium",
                }
            )

        else:
            fixes.append(
                {
                    "issue": error.get("message", "Validation error"),
                    "suggestion": "Review the error message and fix the issue in your template",
                    "code_example": "",
                    "location": "see error details",
                    "confidence": "low",
                }
            )

    return {
        "analysis": f"Found {len(validation_errors)} validation error(s). Here are generic suggestions to fix them.",
        "fixes": fixes,
        "auto_fixable": False,
        "note": "These are generic suggestions. For more intelligent help, ensure AI service is configured.",
    }
