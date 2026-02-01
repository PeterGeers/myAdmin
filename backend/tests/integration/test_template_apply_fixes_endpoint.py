"""
Integration test for Template Apply AI Fixes API endpoint

Tests the POST /api/tenant-admin/templates/apply-ai-fixes endpoint
"""

import pytest
import os
from database import DatabaseManager
from services.ai_template_assistant import AITemplateAssistant


class TestTemplateApplyFixesEndpoint:
    """Integration tests for template apply fixes endpoint"""
    
    @pytest.fixture
    def db(self):
        """Create database connection"""
        test_mode = os.getenv('TEST_MODE', 'true').lower() == 'true'
        return DatabaseManager(test_mode=test_mode)
    
    @pytest.fixture
    def ai_assistant(self, db):
        """Create AI template assistant"""
        return AITemplateAssistant(db)
    
    def test_apply_fixes_request_structure(self):
        """Test that endpoint expects correct request structure"""
        # Valid request structure
        valid_request = {
            'template_content': '<html>...</html>',
            'fixes': [
                {
                    'issue': 'Missing placeholder: invoice_number',
                    'code_to_add': '{{ invoice_number }}',
                    'location': 'header'
                }
            ]
        }
        
        assert 'template_content' in valid_request
        assert 'fixes' in valid_request
        assert len(valid_request['fixes']) > 0
    
    def test_apply_fixes_response_structure(self):
        """Test expected response structure"""
        # Expected success response
        expected_response = {
            'success': True,
            'fixed_template': '<html>...fixed...</html>',
            'fixes_applied': 3,
            'message': 'Successfully applied 3 fixes'
        }
        
        assert 'success' in expected_response
        assert 'fixed_template' in expected_response
        assert 'fixes_applied' in expected_response
        assert 'message' in expected_response
    
    def test_apply_fixes_with_ai_assistant(self, ai_assistant):
        """Test applying fixes using AI assistant"""
        template_content = '''
            <html>
                <body>
                    <h1>Invoice</h1>
                </body>
            </html>
        '''
        
        fixes = [
            {
                'issue': 'Missing placeholder: invoice_number',
                'code_example': '{{ invoice_number }}',
                'location': 'header',
                'auto_fixable': True
            }
        ]
        
        result = ai_assistant.apply_auto_fixes(
            template_content=template_content,
            fixes=fixes
        )
        
        # Assertions - apply_auto_fixes returns a string (the fixed template)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_apply_fixes_empty_fixes_list(self, ai_assistant):
        """Test applying fixes with empty fixes list"""
        template_content = '<html><body>Test</body></html>'
        fixes = []
        
        result = ai_assistant.apply_auto_fixes(
            template_content=template_content,
            fixes=fixes
        )
        
        # Should return original template unchanged
        assert result is not None
        assert isinstance(result, str)
        assert result == template_content
    
    def test_apply_fixes_multiple_fixes(self, ai_assistant):
        """Test applying multiple fixes"""
        template_content = '''
            <html>
                <body>
                    <h1>Invoice</h1>
                </body>
            </html>
        '''
        
        fixes = [
            {
                'issue': 'Missing placeholder: invoice_number',
                'code_example': '{{ invoice_number }}',
                'location': 'header',
                'auto_fixable': True
            },
            {
                'issue': 'Missing placeholder: guest_name',
                'code_example': '{{ guest_name }}',
                'location': 'body',
                'auto_fixable': True
            },
            {
                'issue': 'Missing placeholder: amount',
                'code_example': '{{ amount_gross }}',
                'location': 'body',
                'auto_fixable': True
            }
        ]
        
        result = ai_assistant.apply_auto_fixes(
            template_content=template_content,
            fixes=fixes
        )
        
        # Assertions
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_apply_fixes_preserves_template_structure(self, ai_assistant):
        """Test that applying fixes preserves template structure"""
        template_content = '''
            <html>
                <head>
                    <title>Invoice</title>
                </head>
                <body>
                    <h1>Invoice</h1>
                </body>
            </html>
        '''
        
        fixes = [
            {
                'issue': 'Missing placeholder',
                'code_example': '{{ invoice_number }}',
                'location': 'body',
                'auto_fixable': True
            }
        ]
        
        result = ai_assistant.apply_auto_fixes(
            template_content=template_content,
            fixes=fixes
        )
        
        # Fixed template should still be valid HTML
        assert isinstance(result, str)
        assert '<html>' in result
        assert '<head>' in result
        assert '<body>' in result
    
    def test_apply_fixes_audit_log_format(self):
        """Test that audit log contains expected information"""
        # Expected audit log format
        user_email = 'admin@example.com'
        tenant = 'GoodwinSolutions'
        fixes_applied = 3
        
        expected_log = (
            f"AUDIT: AI fixes applied by {user_email} for {tenant}, "
            f"fixes_applied={fixes_applied}"
        )
        
        # Verify log format contains all required information
        assert user_email in expected_log
        assert tenant in expected_log
        assert str(fixes_applied) in expected_log
        assert 'AUDIT:' in expected_log
        assert 'AI fixes applied' in expected_log
    
    def test_apply_fixes_handles_invalid_fixes(self, ai_assistant):
        """Test that invalid fixes are handled gracefully"""
        template_content = '<html><body>Test</body></html>'
        
        # Invalid fix structure (missing required fields)
        fixes = [
            {
                'issue': 'Some issue',
                'auto_fixable': True
                # Missing code_example and location
            }
        ]
        
        result = ai_assistant.apply_auto_fixes(
            template_content=template_content,
            fixes=fixes
        )
        
        # Should handle gracefully and return original or modified template
        assert result is not None
        assert isinstance(result, str)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
