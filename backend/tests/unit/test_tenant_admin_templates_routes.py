"""
Unit tests for tenant_admin_templates.py

Tests template management endpoints:
- GET /api/tenant-admin/templates/<template_type> - Get current active template
- GET /api/tenant-admin/templates/<template_type>/default - Get default template
- POST /api/tenant-admin/templates/preview - Generate preview
- POST /api/tenant-admin/templates/validate - Validate template
- POST /api/tenant-admin/templates/approve - Approve and activate
- POST /api/tenant-admin/templates/reject - Reject with reason
- POST /api/tenant-admin/templates/ai-help - Get AI fix suggestions
- POST /api/tenant-admin/templates/apply-ai-fixes - Apply AI fixes
- DELETE /api/tenant-admin/templates/<template_type> - Delete (deactivate)

Task 51 of Phase 7: Missing Test Coverage
"""

import sys
import os
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from functools import wraps

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ── Auth decorator mocks ───────────────────────────────────────────────────


def _passthrough_cognito(required_permissions=None, required_roles=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'admin@example.com'
            kwargs['user_roles'] = ['Tenant_Admin']
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """Create Flask test client with patched auth and tenant context."""
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.get_current_tenant', return_value='TestTenant'), \
         patch('auth.tenant_context.get_user_tenants', return_value=['TestTenant']), \
         patch('auth.tenant_context.is_tenant_admin', return_value=True):
        import importlib
        import routes.tenant_admin_templates as tat
        importlib.reload(tat)
        import routes.tenant_admin_template_ai_routes as tat_ai
        importlib.reload(tat_ai)

        from flask import Flask
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(tat.tenant_admin_templates_bp)
        app.register_blueprint(tat_ai.tenant_admin_template_ai_bp)

        with app.test_client() as c:
            with app.app_context():
                yield c


@pytest.fixture
def client_not_admin():
    """Create Flask test client where user is NOT tenant admin."""
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.get_current_tenant', return_value='TestTenant'), \
         patch('auth.tenant_context.get_user_tenants', return_value=['TestTenant']), \
         patch('auth.tenant_context.is_tenant_admin', return_value=False):
        import importlib
        import routes.tenant_admin_templates as tat
        importlib.reload(tat)
        import routes.tenant_admin_template_ai_routes as tat_ai
        importlib.reload(tat_ai)

        from flask import Flask
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(tat.tenant_admin_templates_bp)
        app.register_blueprint(tat_ai.tenant_admin_template_ai_bp)

        with app.test_client() as c:
            with app.app_context():
                yield c


# ── GET /api/tenant-admin/templates/<template_type> ────────────────────────


class TestGetCurrentTemplate:

    @patch('routes.tenant_admin_templates.DatabaseManager')
    def test_success(self, mock_db_cls, client):
        """GET /<template_type> returns active template."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.execute_query.return_value = [{
            'template_file_id': 'templates/file-123.html',
            'field_mappings': '{"fields": {}}',
            'version': 2,
            'approved_by': 'admin@test.com',
            'approved_at': '2025-06-01',
            'is_active': True,
            'status': 'active'
        }]

        with patch('services.storage_resolver.resolve_storage_provider', return_value='s3_shared'), \
             patch('services.storage_resolver.get_s3_storage') as mock_s3:
            mock_s3.return_value.download.return_value = b'<html>template</html>'
            resp = client.get(
                '/api/tenant-admin/templates/str_invoice_nl',
                headers={'Authorization': 'Bearer test-token'}
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['template_type'] == 'str_invoice_nl'
        assert 'template_content' in data

    @patch('routes.tenant_admin_templates.DatabaseManager')
    def test_no_active_template_returns_404(self, mock_db_cls, client):
        """GET /<template_type> with no active template returns 404."""
        mock_db_cls.return_value.execute_query.return_value = []
        resp = client.get(
            '/api/tenant-admin/templates/str_invoice_nl',
            headers={'Authorization': 'Bearer test-token'}
        )
        assert resp.status_code == 404

    def test_invalid_template_type_returns_400(self, client):
        """GET /<invalid_type> returns 400."""
        resp = client.get(
            '/api/tenant-admin/templates/invalid_type',
            headers={'Authorization': 'Bearer test-token'}
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'Invalid template type' in data['error']

    def test_not_admin_returns_403(self, client_not_admin):
        """GET /<template_type> without admin role returns 403."""
        resp = client_not_admin.get(
            '/api/tenant-admin/templates/str_invoice_nl',
            headers={'Authorization': 'Bearer test-token'}
        )
        assert resp.status_code == 403


# ── GET /api/tenant-admin/templates/<template_type>/default ────────────────


class TestGetDefaultTemplate:

    @patch('routes.tenant_admin_templates.DatabaseManager')
    @patch('services.template_service.TemplateService')
    def test_success(self, mock_ts_cls, mock_db_cls, client):
        """GET /<template_type>/default returns default template."""
        mock_ts_cls.return_value._get_local_default_metadata.return_value = {
            'local_path': '/tmp/test_template.html',
            'field_mappings': {'fields': {}}
        }
        with patch('builtins.open', MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(return_value=MagicMock(
                    read=MagicMock(return_value='<html>default</html>')
                )),
                __exit__=MagicMock(return_value=False)
            )
        )):
            resp = client.get(
                '/api/tenant-admin/templates/str_invoice_nl/default',
                headers={'Authorization': 'Bearer test-token'}
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'template_content' in data

    @patch('routes.tenant_admin_templates.DatabaseManager')
    @patch('services.template_service.TemplateService')
    def test_no_default_returns_404(self, mock_ts_cls, mock_db_cls, client):
        """GET /<template_type>/default with no default returns 404."""
        mock_ts_cls.return_value._get_local_default_metadata.return_value = None
        resp = client.get(
            '/api/tenant-admin/templates/str_invoice_nl/default',
            headers={'Authorization': 'Bearer test-token'}
        )
        assert resp.status_code == 404


# ── POST /api/tenant-admin/templates/preview ───────────────────────────────


class TestPreviewTemplate:

    @patch('routes.tenant_admin_templates.DatabaseManager')
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_preview_success(self, mock_preview_cls, mock_db_cls, client):
        """POST /preview generates preview."""
        mock_preview_cls.return_value.generate_preview.return_value = {
            'success': True, 'preview_html': '<html>preview</html>'
        }
        resp = client.post(
            '/api/tenant-admin/templates/preview',
            headers={'Authorization': 'Bearer test-token'},
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html>{{year}}</html>',
                'field_mappings': {}
            }
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_preview_missing_template_type(self, client):
        """POST /preview without template_type returns 400."""
        resp = client.post(
            '/api/tenant-admin/templates/preview',
            headers={'Authorization': 'Bearer test-token'},
            json={'template_content': '<html></html>'}
        )
        assert resp.status_code == 400
        assert 'template_type is required' in resp.get_json()['error']

    def test_preview_missing_content(self, client):
        """POST /preview without template_content returns 400."""
        resp = client.post(
            '/api/tenant-admin/templates/preview',
            headers={'Authorization': 'Bearer test-token'},
            json={'template_type': 'str_invoice_nl'}
        )
        assert resp.status_code == 400
        assert 'template_content is required' in resp.get_json()['error']


# ── POST /api/tenant-admin/templates/validate ──────────────────────────────


class TestValidateTemplate:

    @patch('routes.tenant_admin_templates.DatabaseManager')
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_validate_success(self, mock_preview_cls, mock_db_cls, client):
        """POST /validate returns validation results."""
        mock_preview_cls.return_value.validate_template.return_value = {
            'is_valid': True, 'errors': []
        }
        resp = client.post(
            '/api/tenant-admin/templates/validate',
            headers={'Authorization': 'Bearer test-token'},
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html>valid</html>'
            }
        )
        assert resp.status_code == 200

    def test_validate_missing_type(self, client):
        """POST /validate without template_type returns 400."""
        resp = client.post(
            '/api/tenant-admin/templates/validate',
            headers={'Authorization': 'Bearer test-token'},
            json={'template_content': '<html></html>'}
        )
        assert resp.status_code == 400


# ── POST /api/tenant-admin/templates/approve ───────────────────────────────


class TestApproveTemplate:

    @patch('routes.tenant_admin_templates.DatabaseManager')
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_approve_success(self, mock_preview_cls, mock_db_cls, client):
        """POST /approve activates template."""
        mock_preview_cls.return_value.approve_template.return_value = {
            'success': True, 'file_id': 'new-file-id'
        }
        resp = client.post(
            '/api/tenant-admin/templates/approve',
            headers={'Authorization': 'Bearer test-token'},
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html>approved</html>',
                'field_mappings': {}
            }
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    @patch('routes.tenant_admin_templates.DatabaseManager')
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_approve_validation_failure(self, mock_preview_cls, mock_db_cls, client):
        """POST /approve returns 400 on validation failure."""
        mock_preview_cls.return_value.approve_template.return_value = {
            'success': False, 'message': 'Template has validation errors'
        }
        resp = client.post(
            '/api/tenant-admin/templates/approve',
            headers={'Authorization': 'Bearer test-token'},
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<script>bad</script>'
            }
        )
        assert resp.status_code == 400

    def test_approve_missing_content(self, client):
        """POST /approve without template_content returns 400."""
        resp = client.post(
            '/api/tenant-admin/templates/approve',
            headers={'Authorization': 'Bearer test-token'},
            json={'template_type': 'str_invoice_nl'}
        )
        assert resp.status_code == 400


# ── POST /api/tenant-admin/templates/reject ────────────────────────────────


class TestRejectTemplate:

    def test_reject_success(self, client):
        """POST /reject logs rejection."""
        resp = client.post(
            '/api/tenant-admin/templates/reject',
            headers={'Authorization': 'Bearer test-token'},
            json={'template_type': 'str_invoice_nl', 'reason': 'Missing placeholders'}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_reject_missing_type(self, client):
        """POST /reject without template_type returns 400."""
        resp = client.post(
            '/api/tenant-admin/templates/reject',
            headers={'Authorization': 'Bearer test-token'},
            json={'reason': 'Bad template'}
        )
        assert resp.status_code == 400


# ── POST /api/tenant-admin/templates/ai-help ───────────────────────────────


class TestAIHelpTemplate:

    @patch('routes.tenant_admin_template_ai_routes.DatabaseManager')
    @patch('services.ai_template_assistant.AITemplateAssistant')
    def test_ai_help_success(self, mock_ai_cls, mock_db_cls, client):
        """POST /ai-help returns AI suggestions."""
        mock_ai_cls.return_value.get_fix_suggestions.return_value = {
            'success': True,
            'ai_suggestions': {'fixes': []},
            'tokens_used': 150
        }
        resp = client.post(
            '/api/tenant-admin/templates/ai-help',
            headers={'Authorization': 'Bearer test-token'},
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html>broken</html>',
                'validation_errors': [{'type': 'missing_placeholder', 'placeholder': 'year'}]
            }
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    @patch('routes.tenant_admin_template_ai_routes.DatabaseManager')
    @patch('services.ai_template_assistant.AITemplateAssistant')
    def test_ai_help_fallback_on_failure(self, mock_ai_cls, mock_db_cls, client):
        """POST /ai-help returns generic help when AI fails."""
        mock_ai_cls.return_value.get_fix_suggestions.return_value = {
            'success': False, 'error': 'API unavailable'
        }
        resp = client.post(
            '/api/tenant-admin/templates/ai-help',
            headers={'Authorization': 'Bearer test-token'},
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>',
                'validation_errors': [{'type': 'missing_placeholder', 'placeholder': 'year'}]
            }
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data.get('fallback') is True

    def test_ai_help_missing_errors(self, client):
        """POST /ai-help without validation_errors returns 400."""
        resp = client.post(
            '/api/tenant-admin/templates/ai-help',
            headers={'Authorization': 'Bearer test-token'},
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>'
            }
        )
        assert resp.status_code == 400
        assert 'validation_errors is required' in resp.get_json()['error']


# ── POST /api/tenant-admin/templates/apply-ai-fixes ────────────────────────


class TestApplyAIFixes:

    @patch('routes.tenant_admin_template_ai_routes.DatabaseManager')
    @patch('services.ai_template_assistant.AITemplateAssistant')
    def test_apply_fixes_success(self, mock_ai_cls, mock_db_cls, client):
        """POST /apply-ai-fixes applies fixes."""
        mock_ai_cls.return_value.apply_auto_fixes.return_value = '<html>fixed</html>'
        resp = client.post(
            '/api/tenant-admin/templates/apply-ai-fixes',
            headers={'Authorization': 'Bearer test-token'},
            json={
                'template_content': '<html>broken</html>',
                'fixes': [{'auto_fixable': True, 'fix': 'add placeholder'}]
            }
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['fixes_applied'] == 1

    def test_apply_fixes_missing_content(self, client):
        """POST /apply-ai-fixes without template_content returns 400."""
        resp = client.post(
            '/api/tenant-admin/templates/apply-ai-fixes',
            headers={'Authorization': 'Bearer test-token'},
            json={'fixes': []}
        )
        assert resp.status_code == 400

    def test_apply_fixes_missing_fixes(self, client):
        """POST /apply-ai-fixes without fixes returns 400."""
        resp = client.post(
            '/api/tenant-admin/templates/apply-ai-fixes',
            headers={'Authorization': 'Bearer test-token'},
            json={'template_content': '<html></html>'}
        )
        assert resp.status_code == 400


# ── DELETE /api/tenant-admin/templates/<template_type> ─────────────────────


class TestDeleteTemplate:

    @patch('routes.tenant_admin_template_ai_routes.DatabaseManager')
    def test_delete_success(self, mock_db_cls, client):
        """DELETE /<template_type> deactivates template."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.execute_query.side_effect = [
            [{'template_file_id': 'file-to-deactivate'}],  # SELECT
            None  # UPDATE
        ]
        resp = client.delete(
            '/api/tenant-admin/templates/str_invoice_nl',
            headers={'Authorization': 'Bearer test-token'}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'deactivated' in data['message'].lower()

    @patch('routes.tenant_admin_template_ai_routes.DatabaseManager')
    def test_delete_no_active_returns_404(self, mock_db_cls, client):
        """DELETE /<template_type> with no active template returns 404."""
        mock_db_cls.return_value.execute_query.return_value = []
        resp = client.delete(
            '/api/tenant-admin/templates/str_invoice_nl',
            headers={'Authorization': 'Bearer test-token'}
        )
        assert resp.status_code == 404

    def test_delete_invalid_type_returns_400(self, client):
        """DELETE /<invalid_type> returns 400."""
        resp = client.delete(
            '/api/tenant-admin/templates/invalid_type',
            headers={'Authorization': 'Bearer test-token'}
        )
        assert resp.status_code == 400


# ── Helper function tests ──────────────────────────────────────────────────


class TestGenericHelp:

    def test_generic_help_missing_placeholder(self):
        """_get_generic_help handles missing_placeholder errors."""
        from routes.tenant_admin_templates import _get_generic_help
        errors = [{'type': 'missing_placeholder', 'placeholder': 'year'}]
        result = _get_generic_help(errors, ['year'])
        assert len(result['fixes']) == 1
        assert 'year' in result['fixes'][0]['issue']

    def test_generic_help_security_error(self):
        """_get_generic_help handles security errors."""
        from routes.tenant_admin_templates import _get_generic_help
        errors = [{'type': 'security_error', 'message': 'Script tag found'}]
        result = _get_generic_help(errors, [])
        assert 'security' in result['fixes'][0]['issue'].lower() or 'script' in result['fixes'][0]['suggestion'].lower()

    def test_generic_help_syntax_error(self):
        """_get_generic_help handles syntax errors."""
        from routes.tenant_admin_templates import _get_generic_help
        errors = [{'type': 'syntax_error', 'message': 'Unclosed div tag', 'line': 5}]
        result = _get_generic_help(errors, [])
        assert len(result['fixes']) == 1

    def test_generic_help_unknown_error(self):
        """_get_generic_help handles unknown error types."""
        from routes.tenant_admin_templates import _get_generic_help
        errors = [{'type': 'other', 'message': 'Something went wrong'}]
        result = _get_generic_help(errors, [])
        assert len(result['fixes']) == 1
        assert result['fixes'][0]['confidence'] == 'low'
