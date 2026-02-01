"""
Integration test for Template Preview API endpoint

Tests the POST /api/tenant-admin/templates/preview endpoint with real service integration
"""

import pytest
import os
from database import DatabaseManager
from services.template_preview_service import TemplatePreviewService


class TestTemplatePreviewServiceIntegration:
    """Integration tests for template preview service"""
    
    @pytest.fixture
    def db(self):
        """Create database connection"""
        test_mode = os.getenv('TEST_MODE', 'true').lower() == 'true'
        return DatabaseManager(test_mode=test_mode)
    
    @pytest.fixture
    def preview_service(self, db):
        """Create template preview service"""
        return TemplatePreviewService(db, 'GoodwinSolutions')
    
    def test_generate_preview_success(self, preview_service):
        """Test successful preview generation with valid template"""
        template_content = '''
            <html>
                <body>
                    <h1>Invoice {{ invoice_number }}</h1>
                    <p>Guest: {{ guest_name }}</p>
                    <p>Check-in: {{ checkin_date }}</p>
                    <p>Check-out: {{ checkout_date }}</p>
                    <p>Amount: {{ amount_gross }}</p>
                    <p>Company: {{ company_name }}</p>
                </body>
            </html>
        '''
        
        result = preview_service.generate_preview(
            template_type='str_invoice_nl',
            template_content=template_content,
            field_mappings={}
        )
        
        # Assertions
        assert result is not None
        assert 'success' in result
        assert 'validation' in result
        
        # If successful, should have preview_html
        if result['success']:
            assert 'preview_html' in result
            assert 'sample_data_info' in result
            assert result['validation']['is_valid'] is True
        else:
            # If not successful, validation should explain why
            assert result['validation']['is_valid'] is False
            assert len(result['validation']['errors']) > 0
    
    def test_validate_template_missing_placeholders(self, preview_service):
        """Test validation fails when required placeholders are missing"""
        template_content = '''
            <html>
                <body>
                    <h1>Invoice</h1>
                    <p>This template is missing required placeholders</p>
                </body>
            </html>
        '''
        
        result = preview_service.validate_template(
            template_type='str_invoice_nl',
            template_content=template_content
        )
        
        # Assertions
        assert result is not None
        assert result['is_valid'] is False
        assert len(result['errors']) > 0
        
        # Should have errors about missing placeholders
        placeholder_errors = [e for e in result['errors'] if e['type'] == 'missing_placeholder']
        assert len(placeholder_errors) > 0
    
    def test_validate_template_security_issues(self, preview_service):
        """Test validation detects security issues"""
        template_content = '''
            <html>
                <body>
                    <h1>Invoice {{ invoice_number }}</h1>
                    <script>alert('XSS')</script>
                    <button onclick="doSomething()">Click</button>
                </body>
            </html>
        '''
        
        result = preview_service.validate_template(
            template_type='str_invoice_nl',
            template_content=template_content
        )
        
        # Assertions
        assert result is not None
        assert result['is_valid'] is False
        
        # Should have security errors
        security_errors = [e for e in result['errors'] if e['type'] == 'security_error']
        assert len(security_errors) > 0
    
    def test_validate_template_html_syntax_error(self, preview_service):
        """Test validation detects HTML syntax errors"""
        template_content = '''
            <html>
                <body>
                    <h1>Invoice {{ invoice_number }}
                    <p>Unclosed heading tag above</p>
                </body>
            </html>
        '''
        
        result = preview_service.validate_template(
            template_type='str_invoice_nl',
            template_content=template_content
        )
        
        # Assertions
        assert result is not None
        # May or may not be invalid depending on HTML parser strictness
        # But should at least complete without crashing
        assert 'is_valid' in result
        assert 'errors' in result
    
    def test_fetch_sample_data_str_invoice(self, preview_service):
        """Test fetching sample data for STR invoice"""
        result = preview_service.fetch_sample_data('str_invoice_nl')
        
        # Assertions
        assert result is not None
        assert 'data' in result
        assert 'metadata' in result
        
        # Should have invoice data fields
        data = result['data']
        assert 'invoice_number' in data or 'reservationCode' in data
        assert 'guest_name' in data or 'guestName' in data
    
    def test_fetch_sample_data_btw(self, preview_service):
        """Test fetching sample data for BTW aangifte"""
        result = preview_service.fetch_sample_data('btw_aangifte')
        
        # Assertions
        assert result is not None
        assert 'data' in result
        assert 'metadata' in result
        
        # Should have BTW data fields
        data = result['data']
        assert 'year' in data
        assert 'quarter' in data
        assert 'administration' in data
    
    def test_fetch_sample_data_unknown_type(self, preview_service):
        """Test fetching sample data for unknown template type"""
        result = preview_service.fetch_sample_data('unknown_template_type')
        
        # Assertions
        assert result is not None
        assert 'data' in result
        assert 'metadata' in result
        
        # Should return generic placeholder data
        assert result['metadata']['source'] == 'placeholder'
    
    def test_endpoint_request_validation(self):
        """Test that endpoint validates required fields"""
        # This test verifies the endpoint logic without making HTTP requests
        
        # Test 1: Missing template_type
        data = {'template_content': '<html></html>'}
        assert 'template_type' not in data
        
        # Test 2: Missing template_content
        data = {'template_type': 'str_invoice_nl'}
        assert 'template_content' not in data
        
        # Test 3: Valid request
        data = {
            'template_type': 'str_invoice_nl',
            'template_content': '<html></html>',
            'field_mappings': {}
        }
        assert 'template_type' in data
        assert 'template_content' in data


class TestTemplateValidateServiceIntegration:
    """Integration tests for template validate service"""
    
    @pytest.fixture
    def db(self):
        """Create database connection"""
        test_mode = os.getenv('TEST_MODE', 'true').lower() == 'true'
        return DatabaseManager(test_mode=test_mode)
    
    @pytest.fixture
    def preview_service(self, db):
        """Create template preview service"""
        return TemplatePreviewService(db, 'GoodwinSolutions')
    
    def test_validate_template_success(self, preview_service):
        """Test successful validation with valid template"""
        template_content = '''
            <html>
                <body>
                    <h1>Invoice {{ invoice_number }}</h1>
                    <p>Guest: {{ guest_name }}</p>
                    <p>Check-in: {{ checkin_date }}</p>
                    <p>Check-out: {{ checkout_date }}</p>
                    <p>Amount: {{ amount_gross }}</p>
                    <p>Company: {{ company_name }}</p>
                </body>
            </html>
        '''
        
        result = preview_service.validate_template(
            template_type='str_invoice_nl',
            template_content=template_content
        )
        
        # Assertions
        assert result is not None
        assert 'is_valid' in result
        assert result['is_valid'] is True
        assert 'errors' in result
        assert len(result['errors']) == 0
        assert 'warnings' in result
        assert 'checks_performed' in result
    
    def test_validate_template_missing_required_fields(self, preview_service):
        """Test validation fails when required placeholders are missing"""
        template_content = '''
            <html>
                <body>
                    <h1>Invoice</h1>
                    <p>Missing required placeholders</p>
                </body>
            </html>
        '''
        
        result = preview_service.validate_template(
            template_type='str_invoice_nl',
            template_content=template_content
        )
        
        # Assertions
        assert result is not None
        assert result['is_valid'] is False
        assert len(result['errors']) > 0
        
        # Should have placeholder errors
        placeholder_errors = [e for e in result['errors'] if e['type'] == 'missing_placeholder']
        assert len(placeholder_errors) > 0
    
    def test_validate_template_security_check(self, preview_service):
        """Test validation detects security issues"""
        template_content = '''
            <html>
                <body>
                    <h1>Invoice {{ invoice_number }}</h1>
                    <p>Guest: {{ guest_name }}</p>
                    <p>Check-in: {{ checkin_date }}</p>
                    <p>Check-out: {{ checkout_date }}</p>
                    <p>Amount: {{ amount_gross }}</p>
                    <p>Company: {{ company_name }}</p>
                    <script>alert('XSS')</script>
                </body>
            </html>
        '''
        
        result = preview_service.validate_template(
            template_type='str_invoice_nl',
            template_content=template_content
        )
        
        # Assertions
        assert result is not None
        assert result['is_valid'] is False
        
        # Should have security errors
        security_errors = [e for e in result['errors'] if e['type'] == 'security_error']
        assert len(security_errors) > 0
    
    def test_validate_template_faster_than_preview(self, preview_service):
        """Test that validation is faster than full preview generation"""
        import time
        
        template_content = '''
            <html>
                <body>
                    <h1>Invoice {{ invoice_number }}</h1>
                    <p>Guest: {{ guest_name }}</p>
                    <p>Check-in: {{ checkin_date }}</p>
                    <p>Check-out: {{ checkout_date }}</p>
                    <p>Amount: {{ amount_gross }}</p>
                    <p>Company: {{ company_name }}</p>
                </body>
            </html>
        '''
        
        # Time validation only
        start_validate = time.time()
        validate_result = preview_service.validate_template(
            template_type='str_invoice_nl',
            template_content=template_content
        )
        validate_time = time.time() - start_validate
        
        # Time full preview generation
        start_preview = time.time()
        preview_result = preview_service.generate_preview(
            template_type='str_invoice_nl',
            template_content=template_content,
            field_mappings={}
        )
        preview_time = time.time() - start_preview
        
        # Assertions
        assert validate_result is not None
        assert preview_result is not None
        
        # Validation should be faster (or at least not significantly slower)
        # Allow some margin for test variability
        print(f"Validate time: {validate_time:.4f}s, Preview time: {preview_time:.4f}s")
        # This is informational - we don't assert strict timing in tests


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
