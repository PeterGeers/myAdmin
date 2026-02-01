"""
Unit tests for AITemplateAssistant
Tests AI-powered template assistance functionality including prompt building,
template sanitization, response parsing, and auto-fix application.
"""

import sys
import os
import pytest
import json
from unittest.mock import Mock, MagicMock, patch

# Add backend/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.ai_template_assistant import AITemplateAssistant


class TestAITemplateAssistantInit:
    """Test AITemplateAssistant initialization"""
    
    def test_init_with_api_key(self):
        """Test initialization when API key is set"""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key-123'}):
            assistant = AITemplateAssistant()
            
            assert assistant.api_key == 'test-key-123'
            assert assistant.api_url == 'https://openrouter.ai/api/v1/chat/completions'
            assert isinstance(assistant.models, list)
            assert len(assistant.models) > 0
            assert 'deepseek/deepseek-chat' in assistant.models  # Primary model
    
    def test_init_without_api_key(self):
        """Test initialization when API key is not set"""
        with patch.dict(os.environ, {}, clear=True):
            assistant = AITemplateAssistant()
            
            assert assistant.api_key is None
    
    def test_init_with_custom_model(self):
        """Test initialization with fallback model chain"""
        with patch.dict(os.environ, {
            'OPENROUTER_API_KEY': 'test-key'
        }):
            assistant = AITemplateAssistant()
            
            # Verify fallback chain includes cheap and reliable models
            assert 'deepseek/deepseek-chat' in assistant.models
            assert 'anthropic/claude-3.5-sonnet' in assistant.models  # Paid fallback


class TestTemplateSanitization:
    """Test template sanitization to remove PII"""
    
    def setup_method(self):
        """Setup test fixtures"""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}):
            self.assistant = AITemplateAssistant()
    
    def test_sanitize_removes_email_addresses(self):
        """Test that email addresses are removed from template"""
        template = """
        <html>
            <body>
                <p>Contact: john.doe@example.com</p>
                <p>Support: support@company.co.uk</p>
            </body>
        </html>
        """
        
        sanitized = self.assistant._sanitize_template(template)
        
        assert 'john.doe@example.com' not in sanitized
        assert 'support@company.co.uk' not in sanitized
        assert 'email@example.com' in sanitized
    
    def test_sanitize_preserves_email_placeholders(self):
        """Test that email placeholders are preserved"""
        template = """
        <html>
            <body>
                <p>Contact: {{ contact_email }}</p>
                <p>User: {{ user_email }}</p>
            </body>
        </html>
        """
        
        sanitized = self.assistant._sanitize_template(template)
        
        assert '{{ contact_email }}' in sanitized
        assert '{{ user_email }}' in sanitized
    
    def test_sanitize_removes_phone_numbers(self):
        """Test that phone numbers are removed from template"""
        template = """
        <html>
            <body>
                <p>Phone: 1234567890</p>
                <p>Mobile: 9876543210123</p>
            </body>
        </html>
        """
        
        sanitized = self.assistant._sanitize_template(template)
        
        assert '1234567890' not in sanitized
        assert '9876543210123' not in sanitized
        assert '0123456789' in sanitized
    
    def test_sanitize_preserves_phone_placeholders(self):
        """Test that phone placeholders are preserved"""
        template = """
        <html>
            <body>
                <p>Phone: {{ phone_number }}</p>
            </body>
        </html>
        """
        
        sanitized = self.assistant._sanitize_template(template)
        
        assert '{{ phone_number }}' in sanitized
    
    def test_sanitize_removes_street_addresses(self):
        """Test that street addresses are sanitized from template"""
        template = """
        <html>
            <body>
                <p>Address: 123 Main Street</p>
                <p>Location: 456 Oak Avenue</p>
                <p>Office: 789 Park Boulevard</p>
            </body>
        </html>
        """
        
        sanitized = self.assistant._sanitize_template(template)
        
        # Check that specific addresses are replaced with generic one
        assert '456 Oak Avenue' not in sanitized or sanitized.count('123 Main Street') >= 2
        assert '789 Park Boulevard' not in sanitized or sanitized.count('123 Main Street') >= 2
        # The generic replacement should be present
        assert '123 Main Street' in sanitized
    
    def test_sanitize_preserves_address_placeholders(self):
        """Test that address placeholders are preserved"""
        template = """
        <html>
            <body>
                <p>Address: {{ street_address }}</p>
            </body>
        </html>
        """
        
        sanitized = self.assistant._sanitize_template(template)
        
        assert '{{ street_address }}' in sanitized


class TestErrorFormatting:
    """Test error formatting for AI prompts"""
    
    def setup_method(self):
        """Setup test fixtures"""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}):
            self.assistant = AITemplateAssistant()
    
    def test_format_errors_empty_list(self):
        """Test formatting empty error list"""
        errors = []
        
        formatted = self.assistant._format_errors(errors)
        
        assert formatted == "No errors"
    
    def test_format_errors_single_error(self):
        """Test formatting single error"""
        errors = [
            {
                'type': 'missing_placeholder',
                'message': 'Required placeholder not found',
                'severity': 'error'
            }
        ]
        
        formatted = self.assistant._format_errors(errors)
        
        assert '1.' in formatted
        assert '[missing_placeholder]' in formatted
        assert 'Required placeholder not found' in formatted
        assert '[severity: error]' in formatted
    
    def test_format_errors_multiple_errors(self):
        """Test formatting multiple errors"""
        errors = [
            {
                'type': 'syntax_error',
                'message': 'Unclosed tag',
                'severity': 'error',
                'line': 45
            },
            {
                'type': 'missing_placeholder',
                'message': 'Missing invoice_number',
                'severity': 'error'
            }
        ]
        
        formatted = self.assistant._format_errors(errors)
        
        assert '1.' in formatted
        assert '2.' in formatted
        assert 'Unclosed tag' in formatted
        assert '(line 45)' in formatted
        assert 'Missing invoice_number' in formatted
    
    def test_format_errors_with_line_numbers(self):
        """Test formatting errors with line numbers"""
        errors = [
            {
                'type': 'syntax_error',
                'message': 'Parse error',
                'severity': 'error',
                'line': 123
            }
        ]
        
        formatted = self.assistant._format_errors(errors)
        
        assert '(line 123)' in formatted


class TestPromptBuilding:
    """Test AI prompt building"""
    
    def setup_method(self):
        """Setup test fixtures"""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}):
            self.assistant = AITemplateAssistant()
    
    def test_build_prompt_includes_template_type(self):
        """Test that prompt includes template type"""
        prompt = self.assistant._build_prompt(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=['invoice_number']
        )
        
        assert 'str_invoice_nl' in prompt
    
    def test_build_prompt_includes_required_placeholders(self):
        """Test that prompt includes required placeholders"""
        prompt = self.assistant._build_prompt(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=['invoice_number', 'guest_name', 'amount']
        )
        
        assert 'invoice_number' in prompt
        assert 'guest_name' in prompt
        assert 'amount' in prompt
    
    def test_build_prompt_includes_validation_errors(self):
        """Test that prompt includes validation errors"""
        errors = [
            {
                'type': 'missing_placeholder',
                'message': 'Missing required field',
                'severity': 'error'
            }
        ]
        
        prompt = self.assistant._build_prompt(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=errors,
            required_placeholders=[]
        )
        
        assert 'Missing required field' in prompt
        assert 'missing_placeholder' in prompt
    
    def test_build_prompt_includes_template_content(self):
        """Test that prompt includes template content"""
        template = '<html><body><h1>Test</h1></body></html>'
        
        prompt = self.assistant._build_prompt(
            template_type='str_invoice_nl',
            template_content=template,
            validation_errors=[],
            required_placeholders=[]
        )
        
        assert '<html>' in prompt
        assert '<h1>Test</h1>' in prompt
    
    def test_build_prompt_truncates_long_template(self):
        """Test that very long templates are truncated"""
        # Create a template longer than 10KB
        long_template = '<html><body>' + ('x' * 15000) + '</body></html>'
        
        prompt = self.assistant._build_prompt(
            template_type='str_invoice_nl',
            template_content=long_template,
            validation_errors=[],
            required_placeholders=[]
        )
        
        assert 'template truncated' in prompt.lower()
    
    def test_build_prompt_requests_json_format(self):
        """Test that prompt requests JSON response format"""
        prompt = self.assistant._build_prompt(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=[]
        )
        
        assert 'JSON' in prompt or 'json' in prompt
        assert 'analysis' in prompt
        assert 'fixes' in prompt
        assert 'auto_fixable' in prompt


class TestAIResponseParsing:
    """Test AI response parsing"""
    
    def setup_method(self):
        """Setup test fixtures"""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}):
            self.assistant = AITemplateAssistant()
    
    def test_parse_valid_json_response(self):
        """Test parsing valid JSON response"""
        response = json.dumps({
            'analysis': 'Template is missing required placeholders',
            'fixes': [
                {
                    'issue': 'Missing invoice_number',
                    'suggestion': 'Add placeholder',
                    'code_example': '{{ invoice_number }}',
                    'location': 'header',
                    'auto_fixable': True
                }
            ],
            'auto_fix_available': True,
            'confidence': 'high'
        })
        
        parsed = self.assistant._parse_ai_response(response)
        
        assert parsed['analysis'] == 'Template is missing required placeholders'
        assert len(parsed['fixes']) == 1
        assert parsed['fixes'][0]['issue'] == 'Missing invoice_number'
        assert parsed['auto_fix_available'] is True
        assert parsed['confidence'] == 'high'
    
    def test_parse_json_in_markdown_code_block(self):
        """Test parsing JSON wrapped in markdown code blocks"""
        response = """
        Here's the analysis:
        ```json
        {
            "analysis": "Test analysis",
            "fixes": [],
            "auto_fix_available": false,
            "confidence": "medium"
        }
        ```
        """
        
        parsed = self.assistant._parse_ai_response(response)
        
        assert parsed['analysis'] == 'Test analysis'
        assert parsed['fixes'] == []
        assert parsed['auto_fix_available'] is False
        assert parsed['confidence'] == 'medium'
    
    def test_parse_json_in_generic_code_block(self):
        """Test parsing JSON in generic code blocks"""
        response = """
        ```
        {
            "analysis": "Generic code block",
            "fixes": [],
            "auto_fix_available": false,
            "confidence": "low"
        }
        ```
        """
        
        parsed = self.assistant._parse_ai_response(response)
        
        assert parsed['analysis'] == 'Generic code block'
    
    def test_parse_invalid_json_returns_fallback(self):
        """Test that invalid JSON returns fallback structure"""
        response = "This is not valid JSON at all"
        
        parsed = self.assistant._parse_ai_response(response)
        
        assert 'analysis' in parsed
        assert parsed['analysis'] == response
        assert parsed['fixes'] == []
        assert parsed['auto_fix_available'] is False
        assert parsed['confidence'] == 'low'
    
    def test_parse_adds_missing_fields(self):
        """Test that missing required fields are added"""
        response = json.dumps({
            'fixes': [{'issue': 'test'}]
            # Missing analysis, auto_fix_available, confidence
        })
        
        parsed = self.assistant._parse_ai_response(response)
        
        assert 'analysis' in parsed
        assert 'auto_fix_available' in parsed
        assert 'confidence' in parsed
        assert parsed['fixes'] == [{'issue': 'test'}]


class TestAutoFixApplication:
    """Test auto-fix application"""
    
    def setup_method(self):
        """Setup test fixtures"""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}):
            self.assistant = AITemplateAssistant()
    
    def test_apply_auto_fixes_skips_non_fixable(self):
        """Test that non-auto-fixable fixes are skipped"""
        template = '<html><body></body></html>'
        fixes = [
            {
                'issue': 'Manual fix required',
                'code_example': '<div>test</div>',
                'auto_fixable': False
            }
        ]
        
        result = self.assistant.apply_auto_fixes(template, fixes)
        
        assert result == template  # Unchanged
    
    def test_apply_auto_fixes_adds_missing_placeholder(self):
        """Test that missing placeholders are added"""
        template = '<html><body></body></html>'
        fixes = [
            {
                'issue': 'Missing placeholder invoice_number',
                'code_example': '<div>{{ invoice_number }}</div>',
                'location': 'body',
                'auto_fixable': True
            }
        ]
        
        result = self.assistant.apply_auto_fixes(template, fixes)
        
        assert '{{ invoice_number }}' in result
        assert result != template  # Changed
    
    def test_apply_auto_fixes_multiple_fixes(self):
        """Test applying multiple auto-fixes"""
        template = '<html><body></body></html>'
        fixes = [
            {
                'issue': 'Missing placeholder invoice_number',
                'code_example': '<div>{{ invoice_number }}</div>',
                'location': 'body',
                'auto_fixable': True
            },
            {
                'issue': 'Missing placeholder guest_name',
                'code_example': '<div>{{ guest_name }}</div>',
                'location': 'body',
                'auto_fixable': True
            }
        ]
        
        result = self.assistant.apply_auto_fixes(template, fixes)
        
        assert '{{ invoice_number }}' in result
        assert '{{ guest_name }}' in result
    
    def test_apply_auto_fixes_returns_original_on_error(self):
        """Test that original template is returned if fixes fail"""
        template = '<html><body></body></html>'
        fixes = [
            {
                'issue': 'Missing placeholder',
                'code_example': None,  # Invalid - will cause error
                'location': 'body',
                'auto_fixable': True
            }
        ]
        
        result = self.assistant.apply_auto_fixes(template, fixes)
        
        assert result == template  # Original returned


class TestAddPlaceholder:
    """Test placeholder addition logic"""
    
    def setup_method(self):
        """Setup test fixtures"""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}):
            self.assistant = AITemplateAssistant()
    
    def test_add_placeholder_to_header_section(self):
        """Test adding placeholder to header section"""
        template = '<html><header><h1>Title</h1></header><body></body></html>'
        code = '<div>{{ test }}</div>'
        
        result = self.assistant._add_placeholder(template, code, 'header section')
        
        assert '{{ test }}' in result
        assert result.index('{{ test }}') < result.index('</header>')
    
    def test_add_placeholder_to_footer_section(self):
        """Test adding placeholder to footer section"""
        template = '<html><body></body><footer>Footer</footer></html>'
        code = '<div>{{ test }}</div>'
        
        result = self.assistant._add_placeholder(template, code, 'footer section')
        
        assert '{{ test }}' in result
        assert result.index('{{ test }}') < result.index('</footer>')
    
    def test_add_placeholder_to_body_section(self):
        """Test adding placeholder to body section"""
        template = '<html><body><main>Content</main></body></html>'
        code = '<div>{{ test }}</div>'
        
        result = self.assistant._add_placeholder(template, code, 'body section')
        
        assert '{{ test }}' in result
        assert result.index('{{ test }}') < result.index('</main>')
    
    def test_add_placeholder_default_location(self):
        """Test adding placeholder to default location (before </body>)"""
        template = '<html><body>Content</body></html>'
        code = '<div>{{ test }}</div>'
        
        result = self.assistant._add_placeholder(template, code, 'unknown location')
        
        assert '{{ test }}' in result
        assert result.index('{{ test }}') < result.index('</body>')
    
    def test_add_placeholder_no_body_tag(self):
        """Test adding placeholder when no body tag exists"""
        template = '<html><div>Content</div></html>'
        code = '<div>{{ test }}</div>'
        
        result = self.assistant._add_placeholder(template, code, '')
        
        assert '{{ test }}' in result
        # Should be appended to end
        assert result.endswith(code) or result.endswith(code + '\n')


class TestGetFixSuggestions:
    """Test getting fix suggestions from AI"""
    
    def setup_method(self):
        """Setup test fixtures"""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}):
            self.assistant = AITemplateAssistant()
    
    def test_get_fix_suggestions_no_api_key(self):
        """Test that error is returned when API key is not set"""
        with patch.dict(os.environ, {}, clear=True):
            assistant = AITemplateAssistant()
            
            result = assistant.get_fix_suggestions(
                template_type='str_invoice_nl',
                template_content='<html></html>',
                validation_errors=[],
                required_placeholders=[]
            )
            
            assert result['success'] is False
            assert 'not configured' in result['error'].lower()
    
    @patch('requests.post')
    def test_get_fix_suggestions_success(self, mock_post):
        """Test successful AI fix suggestions"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': json.dumps({
                            'analysis': 'Test analysis',
                            'fixes': [],
                            'auto_fix_available': False,
                            'confidence': 'high'
                        })
                    }
                }
            ]
        }
        mock_post.return_value = mock_response
        
        result = self.assistant.get_fix_suggestions(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=['invoice_number']
        )
        
        assert result['success'] is True
        assert 'ai_suggestions' in result
        assert result['ai_suggestions']['analysis'] == 'Test analysis'
    
    @patch('requests.post')
    def test_get_fix_suggestions_api_error(self, mock_post):
        """Test handling of API errors"""
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_post.return_value = mock_response
        
        result = self.assistant.get_fix_suggestions(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=[]
        )
        
        assert result['success'] is False
        assert 'error' in result
    
    @patch('requests.post')
    def test_get_fix_suggestions_timeout(self, mock_post):
        """Test handling of request timeout"""
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()
        
        result = self.assistant.get_fix_suggestions(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=[]
        )
        
        assert result['success'] is False
        assert 'timed out' in result['error'].lower()
    
    @patch('requests.post')
    def test_get_fix_suggestions_network_error(self, mock_post):
        """Test handling of network errors"""
        import requests
        mock_post.side_effect = requests.exceptions.RequestException('Network error')
        
        result = self.assistant.get_fix_suggestions(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=[]
        )
        
        assert result['success'] is False
        assert 'error' in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])



class TestAIUsageTracking:
    """Test AI usage tracking integration"""
    
    def setup_method(self):
        """Setup test fixtures"""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}):
            self.mock_db = Mock()
            self.assistant = AITemplateAssistant(db=self.mock_db)
    
    def test_init_with_database_creates_tracker(self):
        """Test that providing database creates usage tracker"""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}):
            mock_db = Mock()
            assistant = AITemplateAssistant(db=mock_db)
            
            assert assistant.db == mock_db
            assert assistant.usage_tracker is not None
    
    def test_init_without_database_no_tracker(self):
        """Test that not providing database doesn't create tracker"""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}):
            assistant = AITemplateAssistant()
            
            assert assistant.db is None
            assert assistant.usage_tracker is None
    
    @patch('requests.post')
    def test_logs_usage_on_successful_request(self, mock_post):
        """Test that successful AI request logs usage"""
        # Mock successful API response with token usage
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': json.dumps({
                            'analysis': 'Test analysis',
                            'fixes': [],
                            'auto_fix_available': False,
                            'confidence': 'high'
                        })
                    }
                }
            ],
            'usage': {
                'prompt_tokens': 500,
                'completion_tokens': 300,
                'total_tokens': 800
            }
        }
        mock_post.return_value = mock_response
        
        # Mock the usage tracker
        self.assistant.usage_tracker.log_ai_request = Mock(return_value=True)
        
        result = self.assistant.get_fix_suggestions(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=['invoice_number'],
            administration='TestTenant'
        )
        
        assert result['success'] is True
        assert result['tokens_used'] == 800
        
        # Verify usage was logged
        self.assistant.usage_tracker.log_ai_request.assert_called_once_with(
            administration='TestTenant',
            template_type='str_invoice_nl',
            tokens_used=800,
            model_used='google/gemini-flash-1.5'  # First model in fallback chain
        )
    
    @patch('requests.post')
    def test_logs_usage_with_fallback_token_calculation(self, mock_post):
        """Test usage logging when total_tokens is not provided"""
        # Mock response with separate prompt/completion tokens
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': json.dumps({
                            'analysis': 'Test',
                            'fixes': [],
                            'auto_fix_available': False,
                            'confidence': 'high'
                        })
                    }
                }
            ],
            'usage': {
                'prompt_tokens': 600,
                'completion_tokens': 400
                # No total_tokens field
            }
        }
        mock_post.return_value = mock_response
        
        self.assistant.usage_tracker.log_ai_request = Mock(return_value=True)
        
        result = self.assistant.get_fix_suggestions(
            template_type='btw_aangifte',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=[],
            administration='TestTenant'
        )
        
        assert result['success'] is True
        assert result['tokens_used'] == 1000  # 600 + 400
        
        # Verify usage was logged with calculated total
        self.assistant.usage_tracker.log_ai_request.assert_called_once()
        call_args = self.assistant.usage_tracker.log_ai_request.call_args
        assert call_args[1]['tokens_used'] == 1000
    
    @patch('requests.post')
    def test_no_logging_without_administration(self, mock_post):
        """Test that usage is not logged when administration is not provided"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': json.dumps({
                            'analysis': 'Test',
                            'fixes': [],
                            'auto_fix_available': False,
                            'confidence': 'high'
                        })
                    }
                }
            ],
            'usage': {
                'total_tokens': 500
            }
        }
        mock_post.return_value = mock_response
        
        self.assistant.usage_tracker.log_ai_request = Mock(return_value=True)
        
        result = self.assistant.get_fix_suggestions(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=[]
            # No administration parameter
        )
        
        assert result['success'] is True
        
        # Verify usage was NOT logged
        self.assistant.usage_tracker.log_ai_request.assert_not_called()
    
    @patch('requests.post')
    def test_no_logging_without_tracker(self, mock_post):
        """Test that no error occurs when tracker is not available"""
        # Create assistant without database
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}):
            assistant = AITemplateAssistant()  # No db parameter
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': json.dumps({
                            'analysis': 'Test',
                            'fixes': [],
                            'auto_fix_available': False,
                            'confidence': 'high'
                        })
                    }
                }
            ],
            'usage': {
                'total_tokens': 500
            }
        }
        mock_post.return_value = mock_response
        
        # Should not raise exception even with administration provided
        result = assistant.get_fix_suggestions(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=[],
            administration='TestTenant'
        )
        
        assert result['success'] is True
    
    @patch('requests.post')
    def test_no_logging_with_zero_tokens(self, mock_post):
        """Test that usage is not logged when token count is zero"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': json.dumps({
                            'analysis': 'Test',
                            'fixes': [],
                            'auto_fix_available': False,
                            'confidence': 'high'
                        })
                    }
                }
            ],
            'usage': {
                'total_tokens': 0
            }
        }
        mock_post.return_value = mock_response
        
        self.assistant.usage_tracker.log_ai_request = Mock(return_value=True)
        
        result = self.assistant.get_fix_suggestions(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=[],
            administration='TestTenant'
        )
        
        assert result['success'] is True
        
        # Verify usage was NOT logged (zero tokens)
        self.assistant.usage_tracker.log_ai_request.assert_not_called()
    
    @patch('requests.post')
    def test_logging_failure_does_not_break_request(self, mock_post):
        """Test that logging failure doesn't affect the main request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': json.dumps({
                            'analysis': 'Test',
                            'fixes': [],
                            'auto_fix_available': False,
                            'confidence': 'high'
                        })
                    }
                }
            ],
            'usage': {
                'total_tokens': 500
            }
        }
        mock_post.return_value = mock_response
        
        # Mock logging to fail
        self.assistant.usage_tracker.log_ai_request = Mock(return_value=False)
        
        # Should still succeed even if logging fails
        result = self.assistant.get_fix_suggestions(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=[],
            administration='TestTenant'
        )
        
        assert result['success'] is True
        
        # Verify logging was attempted
        self.assistant.usage_tracker.log_ai_request.assert_called_once()
    
    @patch('requests.post')
    def test_logs_correct_model_used(self, mock_post):
        """Test that the correct model is logged when using fallback"""
        # First model fails, second succeeds
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': json.dumps({
                            'analysis': 'Test',
                            'fixes': [],
                            'auto_fix_available': False,
                            'confidence': 'high'
                        })
                    }
                }
            ],
            'usage': {
                'total_tokens': 750
            }
        }
        
        # First call fails, second succeeds
        mock_post.side_effect = [mock_response_fail, mock_response_success]
        
        self.assistant.usage_tracker.log_ai_request = Mock(return_value=True)
        
        result = self.assistant.get_fix_suggestions(
            template_type='str_invoice_nl',
            template_content='<html></html>',
            validation_errors=[],
            required_placeholders=[],
            administration='TestTenant'
        )
        
        assert result['success'] is True
        
        # Verify the second model was logged
        call_args = self.assistant.usage_tracker.log_ai_request.call_args
        assert call_args[1]['model_used'] == 'meta-llama/llama-3.2-3b-instruct:free'  # Second model
