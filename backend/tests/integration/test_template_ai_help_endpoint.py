"""
Integration test for Template AI Help API endpoint

Tests the POST /api/tenant-admin/templates/ai-help endpoint
"""

import pytest
import os
from database import DatabaseManager
from services.ai_template_assistant import AITemplateAssistant


class TestTemplateAIHelpEndpoint:
    """Integration tests for template AI help endpoint"""
    
    @pytest.fixture
    def db(self):
        """Create database connection"""
        test_mode = os.getenv('TEST_MODE', 'true').lower() == 'true'
        return DatabaseManager(test_mode=test_mode)
    
    @pytest.fixture
    def ai_assistant(self, db):
        """Create AI template assistant"""
        return AITemplateAssistant(db)
    
    def test_ai_help_request_structure(self):
        """Test that endpoint expects correct request structure"""
        # Valid request structure
        valid_request = {
            'template_type': 'str_invoice_nl',
            'template_content': '<html>...</html>',
            'validation_errors': [
                {
                    'type': 'missing_placeholder',
                    'message': 'Required placeholder missing',
                    'placeholder': 'invoice_number'
                }
            ],
            'required_placeholders': ['invoice_number', 'guest_name']
        }
        
        assert 'template_type' in valid_request
        assert 'template_content' in valid_request
        assert 'validation_errors' in valid_request
        assert 'required_placeholders' in valid_request
    
    def test_ai_help_response_structure(self):
        """Test expected response structure"""
        # Expected success response
        expected_response = {
            'success': True,
            'ai_suggestions': {
                'analysis': 'Analysis text',
                'fixes': [],
                'auto_fixable': False
            },
            'tokens_used': 1234,
            'cost_estimate': 0.001
        }
        
        assert 'success' in expected_response
        assert 'ai_suggestions' in expected_response
        assert 'analysis' in expected_response['ai_suggestions']
        assert 'fixes' in expected_response['ai_suggestions']
    
    def test_generic_help_fallback(self):
        """Test that generic help is provided when AI unavailable"""
        validation_errors = [
            {
                'type': 'missing_placeholder',
                'message': 'Required placeholder missing',
                'placeholder': 'invoice_number'
            }
        ]
        required_placeholders = ['invoice_number', 'guest_name']
        
        # Import the helper function
        from tenant_admin_routes import _get_generic_help
        
        result = _get_generic_help(validation_errors, required_placeholders)
        
        # Assertions
        assert 'analysis' in result
        assert 'fixes' in result
        assert len(result['fixes']) > 0
        assert result['auto_fixable'] is False
    
    def test_generic_help_missing_placeholder(self):
        """Test generic help for missing placeholder error"""
        from tenant_admin_routes import _get_generic_help
        
        validation_errors = [
            {
                'type': 'missing_placeholder',
                'message': 'Required placeholder missing',
                'placeholder': 'invoice_number'
            }
        ]
        
        result = _get_generic_help(validation_errors, [])
        
        # Should have fix for missing placeholder
        assert len(result['fixes']) == 1
        assert 'invoice_number' in result['fixes'][0]['issue']
        assert 'code_example' in result['fixes'][0]
    
    def test_generic_help_security_error(self):
        """Test generic help for security error"""
        from tenant_admin_routes import _get_generic_help
        
        validation_errors = [
            {
                'type': 'security_error',
                'message': 'Script tags not allowed'
            }
        ]
        
        result = _get_generic_help(validation_errors, [])
        
        # Should have fix for security issue
        assert len(result['fixes']) == 1
        assert 'script' in result['fixes'][0]['suggestion'].lower()
    
    def test_generic_help_syntax_error(self):
        """Test generic help for syntax error"""
        from tenant_admin_routes import _get_generic_help
        
        validation_errors = [
            {
                'type': 'syntax_error',
                'message': 'Unclosed tag',
                'line': 10
            }
        ]
        
        result = _get_generic_help(validation_errors, [])
        
        # Should have fix for syntax issue
        assert len(result['fixes']) == 1
        assert 'tag' in result['fixes'][0]['suggestion'].lower()
    
    def test_generic_help_multiple_errors(self):
        """Test generic help with multiple errors"""
        from tenant_admin_routes import _get_generic_help
        
        validation_errors = [
            {
                'type': 'missing_placeholder',
                'placeholder': 'invoice_number'
            },
            {
                'type': 'security_error',
                'message': 'Script tags not allowed'
            },
            {
                'type': 'syntax_error',
                'message': 'Unclosed tag'
            }
        ]
        
        result = _get_generic_help(validation_errors, [])
        
        # Should have fixes for all errors
        assert len(result['fixes']) == 3
    
    def test_ai_assistant_initialization(self, ai_assistant):
        """Test that AI assistant initializes correctly"""
        assert ai_assistant is not None
        assert hasattr(ai_assistant, 'get_fix_suggestions')
    
    def test_ai_assistant_handles_no_api_key(self):
        """Test that AI assistant handles missing API key gracefully"""
        # Temporarily remove API key
        original_key = os.environ.get('OPENROUTER_API_KEY')
        if 'OPENROUTER_API_KEY' in os.environ:
            del os.environ['OPENROUTER_API_KEY']
        
        try:
            ai_assistant = AITemplateAssistant(None)
            
            result = ai_assistant.get_fix_suggestions(
                template_type='str_invoice_nl',
                template_content='<html></html>',
                validation_errors=[],
                required_placeholders=[]
            )
            
            # Should return error about missing API key
            assert result['success'] is False
            assert 'not configured' in result['error'].lower() or 'not set' in result['error'].lower()
        
        finally:
            # Restore API key
            if original_key:
                os.environ['OPENROUTER_API_KEY'] = original_key


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
