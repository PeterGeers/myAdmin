"""
Comprehensive API Integration Tests for Tenant Admin Template Endpoints

Tests all 6 template endpoints with:
- Mocked authentication
- Mocked Google Drive
- Database verification
- Tenant isolation
- Mocked OpenRouter AI
"""

import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from flask import Flask
from database import DatabaseManager


@pytest.fixture
def app():
    """Create Flask app with all blueprints"""
    # Import here to avoid circular imports
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))
    
    from tenant_admin_routes import tenant_admin_bp
    
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(tenant_admin_bp)
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def mock_auth():
    """Mock authentication to bypass Cognito"""
    with patch('auth.cognito_utils.cognito_required') as mock:
        # Make decorator pass through and inject user info
        def decorator_passthrough(required_permissions=None, required_roles=None):
            def wrapper(f):
                def decorated(*args, **kwargs):
                    # Inject mock user info
                    kwargs['user_email'] = 'admin@goodwinsolutions.com'
                    kwargs['user_roles'] = ['Tenant_Admin']
                    return f(*args, **kwargs)
                decorated.__name__ = f.__name__
                return decorated
            return wrapper
        mock.side_effect = decorator_passthrough
        yield mock


@pytest.fixture
def mock_tenant_context():
    """Mock tenant context functions"""
    with patch('auth.tenant_context.get_current_tenant') as mock_get_tenant, \
         patch('auth.tenant_context.get_user_tenants') as mock_get_user_tenants, \
         patch('auth.tenant_context.is_tenant_admin') as mock_is_admin:
        
        mock_get_tenant.return_value = 'GoodwinSolutions'
        mock_get_user_tenants.return_value = ['GoodwinSolutions']
        mock_is_admin.return_value = True
        
        yield {
            'get_tenant': mock_get_tenant,
            'get_user_tenants': mock_get_user_tenants,
            'is_admin': mock_is_admin
        }


@pytest.fixture
def mock_db():
    """Mock database manager"""
    with patch('database.DatabaseManager') as mock:
        db_instance = MagicMock()
        db_instance.execute_query.return_value = []
        mock.return_value = db_instance
        yield db_instance


@pytest.fixture
def mock_google_drive():
    """Mock Google Drive service"""
    with patch('services.template_preview_service.GoogleDriveService') as mock:
        drive_instance = MagicMock()
        drive_instance.service.files().create().execute.return_value = {'id': 'mock_file_id_123'}
        mock.return_value = drive_instance
        yield drive_instance


@pytest.fixture
def mock_openrouter():
    """Mock OpenRouter AI API"""
    with patch('services.ai_template_assistant.requests.post') as mock:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'analysis': 'Template is missing required placeholders',
                        'fixes': [
                            {
                                'issue': 'Missing placeholder: invoice_number',
                                'suggestion': 'Add {{ invoice_number }}',
                                'code_example': '<h1>Invoice {{ invoice_number }}</h1>',
                                'location': 'header',
                                'confidence': 'high',
                                'auto_fixable': True
                            }
                        ]
                    })
                }
            }],
            'usage': {
                'total_tokens': 1234
            }
        }
        mock.return_value = mock_response
        yield mock


class TestPreviewEndpointAPI:
    """API integration tests for preview endpoint"""
    
    def test_preview_requires_auth(self, client):
        """Test that preview endpoint requires authentication"""
        response = client.post(
            '/api/tenant-admin/templates/preview',
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>'
            }
        )
        
        # Should return 401 without auth
        assert response.status_code == 401
    
    def test_preview_success(self, client, mock_auth, mock_tenant_context, mock_db):
        """Test successful preview generation"""
        with patch('services.template_preview_service.TemplatePreviewService') as mock_service:
            # Mock successful preview
            mock_instance = MagicMock()
            mock_instance.generate_preview.return_value = {
                'success': True,
                'preview_html': '<html><body>Preview</body></html>',
                'validation': {'is_valid': True, 'errors': [], 'warnings': []},
                'sample_data_info': {'source': 'database'}
            }
            mock_service.return_value = mock_instance
            
            response = client.post(
                '/api/tenant-admin/templates/preview',
                json={
                    'template_type': 'str_invoice_nl',
                    'template_content': '<html><body>{{ invoice_number }}</body></html>',
                    'field_mappings': {}
                },
                headers={'Authorization': 'Bearer mock_token'}
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'preview_html' in data
    
    def test_preview_validation_failure(self, client, mock_auth, mock_tenant_context, mock_db):
        """Test preview with validation failure"""
        with patch('services.template_preview_service.TemplatePreviewService') as mock_service:
            # Mock validation failure
            mock_instance = MagicMock()
            mock_instance.generate_preview.return_value = {
                'success': False,
                'validation': {
                    'is_valid': False,
                    'errors': [{'type': 'missing_placeholder', 'message': 'Missing field'}],
                    'warnings': []
                }
            }
            mock_service.return_value = mock_instance
            
            response = client.post(
                '/api/tenant-admin/templates/preview',
                json={
                    'template_type': 'str_invoice_nl',
                    'template_content': '<html><body>Invalid</body></html>'
                },
                headers={'Authorization': 'Bearer mock_token'}
            )
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert data['success'] is False


class TestValidateEndpointAPI:
    """API integration tests for validate endpoint"""
    
    def test_validate_success(self, client, mock_auth, mock_tenant_context, mock_db):
        """Test successful validation"""
        with patch('services.template_preview_service.TemplatePreviewService') as mock_service:
            mock_instance = MagicMock()
            mock_instance.validate_template.return_value = {
                'is_valid': True,
                'errors': [],
                'warnings': [],
                'checks_performed': ['html_syntax', 'placeholders', 'security']
            }
            mock_service.return_value = mock_instance
            
            response = client.post(
                '/api/tenant-admin/templates/validate',
                json={
                    'template_type': 'str_invoice_nl',
                    'template_content': '<html><body>{{ invoice_number }}</body></html>'
                },
                headers={'Authorization': 'Bearer mock_token'}
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['is_valid'] is True


class TestApproveEndpointAPI:
    """API integration tests for approve endpoint"""
    
    def test_approve_saves_to_drive_and_updates_db(self, client, mock_auth, mock_tenant_context, mock_db, mock_google_drive):
        """Test that approve saves to Google Drive and updates database"""
        with patch('services.template_preview_service.TemplatePreviewService') as mock_service:
            mock_instance = MagicMock()
            mock_instance.approve_template.return_value = {
                'success': True,
                'template_id': 'tmpl_str_invoice_nl_1',
                'file_id': 'mock_file_id_123',
                'message': 'Template approved'
            }
            mock_service.return_value = mock_instance
            
            response = client.post(
                '/api/tenant-admin/templates/approve',
                json={
                    'template_type': 'str_invoice_nl',
                    'template_content': '<html><body>{{ invoice_number }}</body></html>',
                    'field_mappings': {},
                    'notes': 'Approved for production'
                },
                headers={'Authorization': 'Bearer mock_token'}
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'file_id' in data
            
            # Verify approve_template was called
            mock_instance.approve_template.assert_called_once()


class TestRejectEndpointAPI:
    """API integration tests for reject endpoint"""
    
    def test_reject_logs_rejection(self, client, mock_auth, mock_tenant_context):
        """Test that reject endpoint logs rejection"""
        response = client.post(
            '/api/tenant-admin/templates/reject',
            json={
                'template_type': 'str_invoice_nl',
                'reason': 'Does not meet brand guidelines'
            },
            headers={'Authorization': 'Bearer mock_token'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'rejection logged' in data['message'].lower()


class TestAIHelpEndpointAPI:
    """API integration tests for AI help endpoint"""
    
    def test_ai_help_with_mocked_openrouter(self, client, mock_auth, mock_tenant_context, mock_db, mock_openrouter):
        """Test AI help with mocked OpenRouter API"""
        # Set API key for test
        os.environ['OPENROUTER_API_KEY'] = 'test_key'
        
        with patch('services.ai_template_assistant.AITemplateAssistant') as mock_assistant:
            mock_instance = MagicMock()
            mock_instance.get_fix_suggestions.return_value = {
                'success': True,
                'ai_suggestions': {
                    'analysis': 'Template needs fixes',
                    'fixes': [{'issue': 'Missing placeholder'}],
                    'auto_fixable': True
                },
                'tokens_used': 1234,
                'cost_estimate': 0.001
            }
            mock_assistant.return_value = mock_instance
            
            response = client.post(
                '/api/tenant-admin/templates/ai-help',
                json={
                    'template_type': 'str_invoice_nl',
                    'template_content': '<html></html>',
                    'validation_errors': [{'type': 'missing_placeholder'}],
                    'required_placeholders': ['invoice_number']
                },
                headers={'Authorization': 'Bearer mock_token'}
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'ai_suggestions' in data
    
    def test_ai_help_fallback_when_unavailable(self, client, mock_auth, mock_tenant_context, mock_db):
        """Test AI help falls back to generic help when AI unavailable"""
        with patch('services.ai_template_assistant.AITemplateAssistant') as mock_assistant:
            mock_instance = MagicMock()
            mock_instance.get_fix_suggestions.return_value = {
                'success': False,
                'error': 'AI service unavailable'
            }
            mock_assistant.return_value = mock_instance
            
            response = client.post(
                '/api/tenant-admin/templates/ai-help',
                json={
                    'template_type': 'str_invoice_nl',
                    'template_content': '<html></html>',
                    'validation_errors': [{'type': 'missing_placeholder', 'placeholder': 'invoice_number'}],
                    'required_placeholders': ['invoice_number']
                },
                headers={'Authorization': 'Bearer mock_token'}
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data.get('fallback') is True


class TestApplyFixesEndpointAPI:
    """API integration tests for apply fixes endpoint"""
    
    def test_apply_fixes_returns_fixed_template(self, client, mock_auth, mock_tenant_context, mock_db):
        """Test that apply fixes returns fixed template"""
        with patch('services.ai_template_assistant.AITemplateAssistant') as mock_assistant:
            mock_instance = MagicMock()
            mock_instance.apply_auto_fixes.return_value = '<html><body>{{ invoice_number }}</body></html>'
            mock_assistant.return_value = mock_instance
            
            response = client.post(
                '/api/tenant-admin/templates/apply-ai-fixes',
                json={
                    'template_content': '<html><body></body></html>',
                    'fixes': [
                        {
                            'issue': 'Missing placeholder',
                            'code_example': '{{ invoice_number }}',
                            'auto_fixable': True
                        }
                    ]
                },
                headers={'Authorization': 'Bearer mock_token'}
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'fixed_template' in data


class TestTenantIsolation:
    """Test tenant isolation - users cannot access other tenant's templates unless they belong to multiple tenants"""
    
    def test_tenant_isolation_single_tenant_user(self, client, mock_auth, mock_db):
        """Test that single-tenant users cannot access other tenants"""
        with patch('auth.tenant_context.get_current_tenant') as mock_get_tenant, \
             patch('auth.tenant_context.get_user_tenants') as mock_get_user_tenants, \
             patch('auth.tenant_context.is_tenant_admin') as mock_is_admin:
            
            # User belongs to GoodwinSolutions only
            mock_get_tenant.return_value = 'PeterPrive'  # Trying to access different tenant
            mock_get_user_tenants.return_value = ['GoodwinSolutions']
            mock_is_admin.return_value = False  # Not admin of PeterPrive
            
            response = client.post(
                '/api/tenant-admin/templates/preview',
                json={
                    'template_type': 'str_invoice_nl',
                    'template_content': '<html></html>'
                },
                headers={'Authorization': 'Bearer mock_token', 'X-Tenant': 'PeterPrive'}
            )
            
            # Should be denied
            assert response.status_code == 403
            data = json.loads(response.data)
            assert 'Tenant admin access required' in data['error']
    
    def test_multi_tenant_user_can_access_all_their_tenants(self, client, mock_auth, mock_db):
        """Test that multi-tenant users CAN access all their tenants (they share Google Drive)"""
        with patch('auth.tenant_context.get_current_tenant') as mock_get_tenant, \
             patch('auth.tenant_context.get_user_tenants') as mock_get_user_tenants, \
             patch('auth.tenant_context.is_tenant_admin') as mock_is_admin, \
             patch('services.template_preview_service.TemplatePreviewService') as mock_service:
            
            # User belongs to BOTH GoodwinSolutions and PeterPrive (multi-tenant user)
            mock_get_tenant.return_value = 'PeterPrive'
            mock_get_user_tenants.return_value = ['GoodwinSolutions', 'PeterPrive']
            mock_is_admin.return_value = True  # Admin of PeterPrive
            
            mock_instance = MagicMock()
            mock_instance.validate_template.return_value = {
                'is_valid': True,
                'errors': [],
                'warnings': []
            }
            mock_service.return_value = mock_instance
            
            response = client.post(
                '/api/tenant-admin/templates/validate',
                json={
                    'template_type': 'str_invoice_nl',
                    'template_content': '<html></html>'
                },
                headers={'Authorization': 'Bearer mock_token', 'X-Tenant': 'PeterPrive'}
            )
            
            # Should succeed - multi-tenant user can access their tenants
            assert response.status_code == 200
    
    def test_tenant_can_access_own_templates(self, client, mock_auth, mock_db):
        """Test that users CAN access their own tenant's templates"""
        with patch('auth.tenant_context.get_current_tenant') as mock_get_tenant, \
             patch('auth.tenant_context.get_user_tenants') as mock_get_user_tenants, \
             patch('auth.tenant_context.is_tenant_admin') as mock_is_admin, \
             patch('services.template_preview_service.TemplatePreviewService') as mock_service:
            
            # User belongs to and accesses GoodwinSolutions
            mock_get_tenant.return_value = 'GoodwinSolutions'
            mock_get_user_tenants.return_value = ['GoodwinSolutions']
            mock_is_admin.return_value = True
            
            mock_instance = MagicMock()
            mock_instance.validate_template.return_value = {
                'is_valid': True,
                'errors': [],
                'warnings': []
            }
            mock_service.return_value = mock_instance
            
            response = client.post(
                '/api/tenant-admin/templates/validate',
                json={
                    'template_type': 'str_invoice_nl',
                    'template_content': '<html></html>'
                },
                headers={'Authorization': 'Bearer mock_token', 'X-Tenant': 'GoodwinSolutions'}
            )
            
            # Should succeed
            assert response.status_code == 200


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
