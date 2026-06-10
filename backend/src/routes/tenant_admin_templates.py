"""
Tenant Admin Template Routes

Template preview, validation, approval, rejection, and AI assistance endpoints.

Endpoints:
- GET /api/tenant-admin/templates/<template_type> - Get current active template
- GET /api/tenant-admin/templates/<template_type>/default - Get default template
- POST /api/tenant-admin/templates/preview - Generate template preview
- POST /api/tenant-admin/templates/validate - Validate template
- POST /api/tenant-admin/templates/approve - Approve and activate template
- POST /api/tenant-admin/templates/reject - Reject template with reason
- POST /api/tenant-admin/templates/ai-help - Get AI fix suggestions
- POST /api/tenant-admin/templates/apply-ai-fixes - Apply AI fixes
- DELETE /api/tenant-admin/templates/<template_type> - Delete (deactivate) template
"""

from flask import Blueprint, request, jsonify
import os
import json
import logging
from typing import Dict, Any, List

from auth.cognito_utils import cognito_required
from auth.tenant_context import (
    get_current_tenant,
    get_user_tenants,
    is_tenant_admin,
)
from database import DatabaseManager

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
tenant_admin_templates_bp = Blueprint('tenant_admin_templates', __name__)

# Canonical list of valid template types used across all template endpoints.
VALID_TEMPLATE_TYPES = [
    'str_invoice_nl', 'str_invoice_en',
    'btw_aangifte', 'aangifte_ib',
    'toeristenbelasting', 'financial_report',
    'zzp_invoice',
]

# Mapping from VALID_TEMPLATE_TYPES keys to TemplateService._LOCAL_DEFAULTS keys.
_TEMPLATE_TYPE_TO_LOCAL_KEY = {
    'str_invoice_nl': 'str_invoice_nl',
    'str_invoice_en': 'str_invoice_en',
    'btw_aangifte': 'btw_aangifte_html',
    'aangifte_ib': 'aangifte_ib_html_report',
    'toeristenbelasting': 'toeristenbelasting_html',
    'financial_report': 'financial_report_xlsx',
    'zzp_invoice': 'zzp_invoice',
}


# ============================================================================
# Template Endpoints
# ============================================================================


@tenant_admin_templates_bp.route('/api/tenant-admin/templates/<template_type>', methods=['GET'])
@cognito_required(required_permissions=[])
def get_current_template_endpoint(template_type, user_email, user_roles):
    """
    Get current active template (Tenant_Admin only)

    Returns the currently active template content and metadata for the specified type.

    Path parameters:
        template_type: Type of template (str_invoice_nl, btw_aangifte, etc.)
    """
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        if template_type not in VALID_TEMPLATE_TYPES:
            return jsonify({
                'error': 'Invalid template type',
                'valid_types': VALID_TEMPLATE_TYPES
            }), 400

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        query = """
            SELECT template_file_id, field_mappings, version, approved_by,
                   approved_at, is_active, status
            FROM tenant_template_config
            WHERE administration = %s AND template_type = %s AND is_active = TRUE
            ORDER BY version DESC
            LIMIT 1
        """
        result = db.execute_query(query, [tenant, template_type], fetch=True)

        if not result or len(result) == 0:
            return jsonify({
                'success': False,
                'error': 'No active template found',
                'message': f'No active template found for type: {template_type}',
                'template_type': template_type
            }), 404

        template_metadata = result[0]
        file_id = template_metadata.get('template_file_id')

        # Fetch template content from configured storage backend
        try:
            from services.storage_resolver import resolve_storage_provider, get_s3_storage
            provider = resolve_storage_provider(tenant)

            if provider == 's3_shared' and '/' in file_id:
                s3_storage = get_s3_storage(tenant)
                template_content = s3_storage.download(file_id)
                if isinstance(template_content, bytes):
                    template_content = template_content.decode('utf-8')
            else:
                from google_drive_service import GoogleDriveService
                drive_service = GoogleDriveService(administration=tenant)
                template_content = drive_service.download_file_content(file_id)
        except Exception as e:
            logger.error(f"Error fetching template content: {e}")
            return jsonify({
                'success': False,
                'error': 'Failed to fetch template content',
                'details': str(e)
            }), 500

        # Parse field mappings (stored as JSON)
        field_mappings = template_metadata.get('field_mappings')
        if isinstance(field_mappings, str):
            try:
                field_mappings = json.loads(field_mappings)
            except Exception:
                field_mappings = {}

        logger.info(
            f"AUDIT: Template retrieved by {user_email} for {tenant}, "
            f"type={template_type}, file_id={file_id}"
        )

        return jsonify({
            'success': True,
            'template_type': template_type,
            'template_content': template_content,
            'field_mappings': field_mappings or {},
            'metadata': {
                'file_id': file_id,
                'version': template_metadata.get('version', 1),
                'approved_by': template_metadata.get('approved_by'),
                'approved_at': str(template_metadata.get('approved_at')) if template_metadata.get('approved_at') else None,
                'is_active': template_metadata.get('is_active', True),
                'status': template_metadata.get('status', 'active')
            }
        }), 200

    except Exception as e:
        logger.error(f"Error getting current template: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_templates_bp.route('/api/tenant-admin/templates/<template_type>/default', methods=['GET'])
@cognito_required(required_permissions=[])
def get_default_template_endpoint(template_type, user_email, user_roles):
    """
    Download the built-in default template for a template type (Tenant_Admin only).
    """
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        if template_type not in VALID_TEMPLATE_TYPES:
            return jsonify({
                'error': 'Invalid template type',
                'valid_types': VALID_TEMPLATE_TYPES
            }), 400

        local_key = _TEMPLATE_TYPE_TO_LOCAL_KEY.get(template_type)
        if not local_key:
            return jsonify({
                'success': False,
                'error': f'No default template available for type: {template_type}'
            }), 404

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        from services.template_service import TemplateService
        template_service = TemplateService(db)
        metadata = template_service._get_local_default_metadata(local_key)

        if metadata is None:
            return jsonify({
                'success': False,
                'error': f'No default template available for type: {template_type}'
            }), 404

        local_path = metadata['local_path']
        with open(local_path, 'r', encoding='utf-8') as f:
            template_content = f.read()

        filename = f'{template_type}_default.html'

        logger.info(
            f"AUDIT: Default template downloaded by {user_email} for {tenant}, "
            f"type={template_type}"
        )

        return jsonify({
            'success': True,
            'template_type': template_type,
            'template_content': template_content,
            'filename': filename,
            'field_mappings': metadata.get('field_mappings', {}),
            'message': 'Default template retrieved successfully'
        }), 200

    except Exception as e:
        logger.error(f"Error getting default template: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_templates_bp.route('/api/tenant-admin/templates/preview', methods=['POST'])
@cognito_required(required_permissions=[])
def preview_template_endpoint(user_email, user_roles):
    """
    Generate template preview with sample data (Tenant_Admin only)
    """
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        template_type = data.get('template_type')
        template_content = data.get('template_content')
        field_mappings = data.get('field_mappings', {})

        if not template_type:
            return jsonify({'error': 'template_type is required'}), 400

        if not template_content:
            return jsonify({'error': 'template_content is required'}), 400

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        from services.template_preview_service import TemplatePreviewService
        preview_service = TemplatePreviewService(db, tenant)

        result = preview_service.generate_preview(
            template_type=template_type,
            template_content=template_content,
            field_mappings=field_mappings
        )

        logger.info(
            f"AUDIT: Template preview generated by {user_email} for {tenant}, "
            f"type={template_type}, success={result.get('success')}"
        )

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error generating template preview: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_templates_bp.route('/api/tenant-admin/templates/validate', methods=['POST'])
@cognito_required(required_permissions=[])
def validate_template_endpoint(user_email, user_roles):
    """
    Validate template without generating preview (Tenant_Admin only)
    """
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        template_type = data.get('template_type')
        template_content = data.get('template_content')

        if not template_type:
            return jsonify({'error': 'template_type is required'}), 400

        if not template_content:
            return jsonify({'error': 'template_content is required'}), 400

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        from services.template_preview_service import TemplatePreviewService
        preview_service = TemplatePreviewService(db, tenant)

        result = preview_service.validate_template(
            template_type=template_type,
            template_content=template_content
        )

        logger.info(
            f"AUDIT: Template validation by {user_email} for {tenant}, "
            f"type={template_type}, valid={result.get('is_valid')}"
        )

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error validating template: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_templates_bp.route('/api/tenant-admin/templates/approve', methods=['POST'])
@cognito_required(required_permissions=[])
def approve_template_endpoint(user_email, user_roles):
    """
    Approve and activate template (Tenant_Admin only)
    """
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        template_type = data.get('template_type')
        template_content = data.get('template_content')
        field_mappings = data.get('field_mappings', {})
        notes = data.get('notes', '')

        if not template_type:
            return jsonify({'error': 'template_type is required'}), 400

        if not template_content:
            return jsonify({'error': 'template_content is required'}), 400

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        from services.template_preview_service import TemplatePreviewService
        preview_service = TemplatePreviewService(db, tenant)

        result = preview_service.approve_template(
            template_type=template_type,
            template_content=template_content,
            field_mappings=field_mappings,
            user_email=user_email,
            notes=notes
        )

        if result.get('success'):
            logger.info(
                f"AUDIT: Template approved by {user_email} for {tenant}, "
                f"type={template_type}, file_id={result.get('file_id')}"
            )
        else:
            logger.warning(
                f"AUDIT: Template approval failed by {user_email} for {tenant}, "
                f"type={template_type}, reason={result.get('message')}"
            )

        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error approving template: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_templates_bp.route('/api/tenant-admin/templates/reject', methods=['POST'])
@cognito_required(required_permissions=[])
def reject_template_endpoint(user_email, user_roles):
    """
    Reject template with reason (Tenant_Admin only)
    """
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        template_type = data.get('template_type')
        reason = data.get('reason', 'No reason provided')

        if not template_type:
            return jsonify({'error': 'template_type is required'}), 400

        logger.info(
            f"AUDIT: Template rejected by {user_email} for {tenant}, "
            f"type={template_type}, reason={reason}"
        )

        return jsonify({
            'success': True,
            'message': 'Template rejection logged'
        }), 200

    except Exception as e:
        logger.error(f"Error rejecting template: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_templates_bp.route('/api/tenant-admin/templates/ai-help', methods=['POST'])
@cognito_required(required_permissions=[])
def ai_help_template_endpoint(user_email, user_roles):
    """
    Get AI-powered fix suggestions for template errors (Tenant_Admin only)
    """
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        template_type = data.get('template_type')
        template_content = data.get('template_content')
        validation_errors = data.get('validation_errors', [])
        required_placeholders = data.get('required_placeholders', [])

        if not template_type:
            return jsonify({'error': 'template_type is required'}), 400

        if not template_content:
            return jsonify({'error': 'template_content is required'}), 400

        if not validation_errors:
            return jsonify({'error': 'validation_errors is required'}), 400

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        from services.ai_template_assistant import AITemplateAssistant
        ai_assistant = AITemplateAssistant(db)

        result = ai_assistant.get_fix_suggestions(
            template_type=template_type,
            template_content=template_content,
            validation_errors=validation_errors,
            required_placeholders=required_placeholders,
            administration=tenant
        )

        if result.get('success') and result.get('tokens_used'):
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

        if result.get('success'):
            return jsonify(result), 200
        else:
            generic_help = _get_generic_help(validation_errors, required_placeholders)
            return jsonify({
                'success': True,
                'ai_suggestions': generic_help,
                'fallback': True,
                'message': 'AI service unavailable, showing generic help'
            }), 200

    except Exception as e:
        logger.error(f"Error getting AI help: {e}")

        try:
            generic_help = _get_generic_help(
                data.get('validation_errors', []),
                data.get('required_placeholders', [])
            )
            return jsonify({
                'success': True,
                'ai_suggestions': generic_help,
                'fallback': True,
                'message': 'Error occurred, showing generic help'
            }), 200
        except Exception:
            return jsonify({
                'error': 'Internal server error',
                'details': str(e)
            }), 500


@tenant_admin_templates_bp.route('/api/tenant-admin/templates/apply-ai-fixes', methods=['POST'])
@cognito_required(required_permissions=[])
def apply_ai_fixes_endpoint(user_email, user_roles):
    """
    Apply AI-suggested fixes to template (Tenant_Admin only)
    """
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        template_content = data.get('template_content')
        fixes = data.get('fixes', [])

        if not template_content:
            return jsonify({'error': 'template_content is required'}), 400

        if not fixes:
            return jsonify({'error': 'fixes is required'}), 400

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        from services.ai_template_assistant import AITemplateAssistant
        ai_assistant = AITemplateAssistant(db)

        result = ai_assistant.apply_auto_fixes(
            template_content=template_content,
            fixes=fixes
        )

        fixes_applied = len([f for f in fixes if f.get('auto_fixable', False)])

        response = {
            'success': True,
            'fixed_template': result,
            'fixes_applied': fixes_applied,
            'message': f'Successfully applied {fixes_applied} fixes'
        }

        logger.info(
            f"AUDIT: AI fixes applied by {user_email} for {tenant}, "
            f"fixes_applied={fixes_applied}"
        )

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error applying AI fixes: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_templates_bp.route('/api/tenant-admin/templates/<template_type>', methods=['DELETE'])
@cognito_required(required_permissions=[])
def delete_tenant_template_endpoint(template_type, user_email, user_roles):
    """
    Delete (deactivate) a tenant-specific template (Tenant_Admin only).

    Soft-deletes the active tenant template by setting is_active = FALSE and
    status = 'archived'. The system will then fall back to the built-in default.
    """
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        if template_type not in VALID_TEMPLATE_TYPES:
            return jsonify({
                'error': 'Invalid template type',
                'valid_types': VALID_TEMPLATE_TYPES
            }), 400

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        select_query = """
            SELECT template_file_id
            FROM tenant_template_config
            WHERE administration = %s AND template_type = %s AND is_active = TRUE
            LIMIT 1
        """
        result = db.execute_query(select_query, (tenant, template_type), fetch=True)

        if not result or len(result) == 0:
            return jsonify({
                'success': False,
                'error': f'No active tenant template found for type: {template_type}'
            }), 404

        deactivated_file_id = result[0].get('template_file_id')

        update_query = """
            UPDATE tenant_template_config
            SET is_active = FALSE, status = 'archived', updated_at = NOW()
            WHERE administration = %s AND template_type = %s AND is_active = TRUE
        """
        db.execute_query(update_query, (tenant, template_type), fetch=False, commit=True)

        logger.info(
            f"AUDIT: Template deactivated by {user_email} for {tenant}, "
            f"type={template_type}, file_id={deactivated_file_id}"
        )

        return jsonify({
            'success': True,
            'message': 'Template deactivated successfully. System will use default template.',
            'template_type': template_type,
            'deactivated_file_id': deactivated_file_id
        }), 200

    except Exception as e:
        logger.error(f"Error deleting tenant template: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


# ============================================================================
# Helper Functions
# ============================================================================


def _get_generic_help(validation_errors: List[Dict], required_placeholders: List[str]) -> Dict[str, Any]:
    """
    Generate generic help when AI service is unavailable.
    """
    fixes = []

    for error in validation_errors:
        error_type = error.get('type', 'unknown')

        if error_type == 'missing_placeholder':
            placeholder = error.get('placeholder', 'unknown')
            fixes.append({
                'issue': f"Missing placeholder: {placeholder}",
                'suggestion': f"Add {{{{ {placeholder} }}}} to your template where you want to display this value",
                'code_example': f"<p>{{{{ {placeholder} }}}}</p>",
                'location': 'anywhere in template body',
                'confidence': 'high'
            })

        elif error_type == 'security_error':
            fixes.append({
                'issue': error.get('message', 'Security issue detected'),
                'suggestion': 'Remove script tags and event handlers from your template. Use CSS for styling instead.',
                'code_example': '<!-- Remove: <script>...</script> and onclick="..." -->',
                'location': 'throughout template',
                'confidence': 'high'
            })

        elif error_type == 'syntax_error':
            fixes.append({
                'issue': error.get('message', 'HTML syntax error'),
                'suggestion': 'Check for unclosed or mismatched HTML tags. Ensure all opening tags have corresponding closing tags.',
                'code_example': '<!-- Correct: <div>content</div> -->',
                'location': error.get('line', 'unknown line'),
                'confidence': 'medium'
            })

        else:
            fixes.append({
                'issue': error.get('message', 'Validation error'),
                'suggestion': 'Review the error message and fix the issue in your template',
                'code_example': '',
                'location': 'see error details',
                'confidence': 'low'
            })

    return {
        'analysis': f"Found {len(validation_errors)} validation error(s). Here are generic suggestions to fix them.",
        'fixes': fixes,
        'auto_fixable': False,
        'note': 'These are generic suggestions. For more intelligent help, ensure AI service is configured.'
    }
