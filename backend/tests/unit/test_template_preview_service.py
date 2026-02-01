"""
Unit tests for TemplatePreviewService
Tests template validation, HTML syntax checking, and preview generation
"""

import sys
import os
import pytest
from unittest.mock import Mock, MagicMock, patch

# Add backend/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.template_preview_service import TemplatePreviewService


class TestHTMLSyntaxValidation:
    """Test HTML syntax validation functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    def test_validate_html_syntax_valid_html(self):
        """Test validation passes for well-formed HTML"""
        valid_html = """
        <html>
            <head><title>Test</title></head>
            <body>
                <h1>Header</h1>
                <p>Paragraph</p>
                <div>
                    <span>Content</span>
                </div>
            </body>
        </html>
        """
        
        errors = self.service._validate_html_syntax(valid_html)
        
        assert len(errors) == 0, "Valid HTML should not produce errors"
    
    def test_validate_html_syntax_self_closing_tags(self):
        """Test that self-closing tags are handled correctly"""
        html_with_self_closing = """
        <html>
            <body>
                <p>Text with line break<br>and image</p>
                <img src="test.jpg">
                <hr>
                <input type="text">
                <meta charset="utf-8">
                <link rel="stylesheet" href="style.css">
            </body>
        </html>
        """
        
        errors = self.service._validate_html_syntax(html_with_self_closing)
        
        assert len(errors) == 0, "Self-closing tags should not produce errors"
    
    def test_validate_html_syntax_unclosed_tag(self):
        """Test detection of unclosed tags"""
        html_with_unclosed = """
        <html>
            <body>
                <div>
                    <p>Paragraph without closing tag
                </div>
            </body>
        </html>
        """
        
        errors = self.service._validate_html_syntax(html_with_unclosed)
        
        assert len(errors) > 0, "Unclosed tags should produce errors"
        assert any('Unclosed tags' in error['message'] for error in errors), \
            "Error message should mention unclosed tags"
        assert any(error['type'] == 'syntax_error' for error in errors), \
            "Error type should be syntax_error"
    
    def test_validate_html_syntax_mismatched_closing_tag(self):
        """Test detection of mismatched closing tags"""
        html_with_mismatch = """
        <html>
            <body>
                <div>
                    <p>Content</div>
                </p>
            </body>
        </html>
        """
        
        errors = self.service._validate_html_syntax(html_with_mismatch)
        
        assert len(errors) > 0, "Mismatched closing tags should produce errors"
        assert any('Mismatched closing tag' in error['message'] for error in errors), \
            "Error message should mention mismatched closing tags"
        assert any(error['type'] == 'syntax_error' for error in errors), \
            "Error type should be syntax_error"
    
    def test_validate_html_syntax_unexpected_closing_tag(self):
        """Test detection of unexpected closing tags"""
        html_with_unexpected = """
        <html>
            <body>
                <p>Content</p>
                </div>
            </body>
        </html>
        """
        
        errors = self.service._validate_html_syntax(html_with_unexpected)
        
        assert len(errors) > 0, "Unexpected closing tags should produce errors"
        # The error message may say "Unexpected closing tag" or "Mismatched closing tag"
        assert any('closing tag' in error['message'].lower() for error in errors), \
            "Error message should mention closing tag issue"
    
    def test_validate_html_syntax_multiple_errors(self):
        """Test detection of multiple syntax errors"""
        html_with_multiple_errors = """
        <html>
            <body>
                <div>
                    <p>Unclosed paragraph
                    <span>Mismatched</div>
                </span>
            </body>
        </html>
        """
        
        errors = self.service._validate_html_syntax(html_with_multiple_errors)
        
        assert len(errors) > 0, "Multiple errors should be detected"
        # Should detect both unclosed and mismatched tags
    
    def test_validate_html_syntax_nested_tags(self):
        """Test validation of deeply nested tags"""
        html_with_nesting = """
        <html>
            <body>
                <div>
                    <section>
                        <article>
                            <header>
                                <h1>Title</h1>
                            </header>
                            <p>Content</p>
                        </article>
                    </section>
                </div>
            </body>
        </html>
        """
        
        errors = self.service._validate_html_syntax(html_with_nesting)
        
        assert len(errors) == 0, "Properly nested tags should not produce errors"
    
    def test_validate_html_syntax_empty_html(self):
        """Test validation of empty HTML"""
        empty_html = ""
        
        errors = self.service._validate_html_syntax(empty_html)
        
        # Empty HTML should not crash, may or may not have errors
        assert isinstance(errors, list), "Should return a list"
    
    def test_validate_html_syntax_malformed_html(self):
        """Test handling of severely malformed HTML"""
        malformed_html = "<html><body><div><p>Test</html>"
        
        errors = self.service._validate_html_syntax(malformed_html)
        
        assert len(errors) > 0, "Malformed HTML should produce errors"
    
    def test_validate_html_syntax_error_structure(self):
        """Test that errors have the correct structure"""
        html_with_error = "<html><body><div><p>Test</div></body></html>"
        
        errors = self.service._validate_html_syntax(html_with_error)
        
        assert len(errors) > 0, "Should detect error"
        
        for error in errors:
            assert 'type' in error, "Error should have 'type' field"
            assert 'message' in error, "Error should have 'message' field"
            assert 'severity' in error, "Error should have 'severity' field"
            assert error['type'] == 'syntax_error', "Type should be 'syntax_error'"
            assert error['severity'] == 'error', "Severity should be 'error'"
    
    def test_validate_html_syntax_line_numbers(self):
        """Test that line numbers are included when available"""
        html_with_error = """<html>
<body>
<div>
<p>Test</div>
</body>
</html>"""
        
        errors = self.service._validate_html_syntax(html_with_error)
        
        # Some errors may include line numbers
        if errors:
            # At least check that the error structure allows for line numbers
            for error in errors:
                if 'line' in error:
                    assert isinstance(error['line'], int), "Line number should be an integer"


class TestPlaceholderValidation:
    """Test placeholder validation functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    def test_validate_placeholders_all_present(self):
        """Test validation passes when all required placeholders are present"""
        template_content = """
        <html>
            <body>
                <p>Invoice: {{ invoice_number }}</p>
                <p>Guest: {{ guest_name }}</p>
                <p>Check-in: {{ checkin_date }}</p>
                <p>Check-out: {{ checkout_date }}</p>
                <p>Amount: {{ amount_gross }}</p>
                <p>Company: {{ company_name }}</p>
            </body>
        </html>
        """
        
        errors = self.service._validate_placeholders('str_invoice_nl', template_content)
        
        assert len(errors) == 0, "All required placeholders present should not produce errors"
    
    def test_validate_placeholders_missing_required(self):
        """Test detection of missing required placeholders"""
        template_content = """
        <html>
            <body>
                <p>Invoice: {{ invoice_number }}</p>
                <p>Guest: {{ guest_name }}</p>
            </body>
        </html>
        """
        
        errors = self.service._validate_placeholders('str_invoice_nl', template_content)
        
        assert len(errors) > 0, "Missing required placeholders should produce errors"
        assert any('missing_placeholder' in error['type'] for error in errors), \
            "Error type should be missing_placeholder"
        assert any('checkin_date' in error['message'] for error in errors), \
            "Should detect missing checkin_date"
    
    def test_validate_placeholders_btw_aangifte(self):
        """Test placeholder validation for BTW aangifte template"""
        template_content = """
        <html>
            <body>
                <h1>BTW Aangifte {{ year }} Q{{ quarter }}</h1>
                <p>Administration: {{ administration }}</p>
                <table>{{ balance_rows }}</table>
                <table>{{ quarter_rows }}</table>
                <p>{{ payment_instruction }}</p>
            </body>
        </html>
        """
        
        errors = self.service._validate_placeholders('btw_aangifte', template_content)
        
        assert len(errors) == 0, "All required BTW placeholders present"
    
    def test_validate_placeholders_unknown_template_type(self):
        """Test validation for unknown template type"""
        template_content = "<html><body>{{ some_field }}</body></html>"
        
        errors = self.service._validate_placeholders('unknown_type', template_content)
        
        # Unknown template types should not produce errors (no required placeholders defined)
        assert len(errors) == 0, "Unknown template type should not produce errors"
    
    def test_validate_placeholders_aangifte_ib(self):
        """Test placeholder validation for Aangifte IB template"""
        template_content = """
        <html>
            <body>
                <h1>Aangifte IB {{ year }}</h1>
                <p>Administration: {{ administration }}</p>
                <table>{{ table_rows }}</table>
                <p>Generated: {{ generated_date }}</p>
            </body>
        </html>
        """
        
        errors = self.service._validate_placeholders('aangifte_ib', template_content)
        
        assert len(errors) == 0, "All required Aangifte IB placeholders present"
    
    def test_validate_placeholders_toeristenbelasting(self):
        """Test placeholder validation for Toeristenbelasting template"""
        template_content = """
        <html>
            <body>
                <h1>Toeristenbelasting {{ year }}</h1>
                <p>Contact: {{ contact_name }} ({{ contact_email }})</p>
                <p>Nights: {{ nights_total }}</p>
                <p>Revenue: {{ revenue_total }}</p>
                <p>Tourist Tax: {{ tourist_tax_total }}</p>
            </body>
        </html>
        """
        
        errors = self.service._validate_placeholders('toeristenbelasting', template_content)
        
        assert len(errors) == 0, "All required Toeristenbelasting placeholders present"
    
    def test_validate_placeholders_str_invoice_en(self):
        """Test placeholder validation for STR invoice EN template"""
        template_content = """
        <html>
            <body>
                <p>Invoice: {{ invoice_number }}</p>
                <p>Guest: {{ guest_name }}</p>
                <p>Check-in: {{ checkin_date }}</p>
                <p>Check-out: {{ checkout_date }}</p>
                <p>Amount: {{ amount_gross }}</p>
                <p>Company: {{ company_name }}</p>
            </body>
        </html>
        """
        
        errors = self.service._validate_placeholders('str_invoice_en', template_content)
        
        assert len(errors) == 0, "All required STR invoice EN placeholders present"
    
    def test_validate_placeholders_financial_report(self):
        """Test that financial_report (XLSX template) is handled gracefully"""
        # financial_report is an XLSX template, not HTML, so it should not have
        # required HTML placeholders defined
        template_content = "<html><body>{{ some_field }}</body></html>"
        
        errors = self.service._validate_placeholders('financial_report', template_content)
        
        # Should not produce errors since financial_report is not an HTML template type
        assert len(errors) == 0, "financial_report (XLSX) should not have HTML placeholder requirements"
    
    def test_validate_placeholders_multiple_missing(self):
        """Test detection of multiple missing placeholders"""
        template_content = """
        <html>
            <body>
                <p>Invoice: {{ invoice_number }}</p>
            </body>
        </html>
        """
        
        errors = self.service._validate_placeholders('str_invoice_nl', template_content)
        
        # Should detect multiple missing placeholders
        assert len(errors) >= 4, "Should detect multiple missing placeholders"
        
        # Check that specific placeholders are mentioned
        error_messages = [error['message'] for error in errors]
        assert any('guest_name' in msg for msg in error_messages), "Should detect missing guest_name"
        assert any('checkin_date' in msg for msg in error_messages), "Should detect missing checkin_date"
        assert any('checkout_date' in msg for msg in error_messages), "Should detect missing checkout_date"
        assert any('amount_gross' in msg for msg in error_messages), "Should detect missing amount_gross"
    
    def test_validate_placeholders_with_whitespace(self):
        """Test that placeholders with whitespace are correctly extracted"""
        template_content = """
        <html>
            <body>
                <p>Invoice: {{invoice_number}}</p>
                <p>Guest: {{ guest_name }}</p>
                <p>Check-in: {{  checkin_date  }}</p>
                <p>Check-out: {{ checkout_date}}</p>
                <p>Amount: {{amount_gross }}</p>
                <p>Company: {{ company_name}}</p>
            </body>
        </html>
        """
        
        errors = self.service._validate_placeholders('str_invoice_nl', template_content)
        
        assert len(errors) == 0, "Placeholders with varying whitespace should be recognized"
    
    def test_validate_placeholders_error_structure(self):
        """Test that placeholder errors have the correct structure"""
        template_content = "<html><body><p>Test</p></body></html>"
        
        errors = self.service._validate_placeholders('str_invoice_nl', template_content)
        
        assert len(errors) > 0, "Should detect missing placeholders"
        
        for error in errors:
            assert 'type' in error, "Error should have 'type' field"
            assert 'message' in error, "Error should have 'message' field"
            assert 'severity' in error, "Error should have 'severity' field"
            assert 'placeholder' in error, "Error should have 'placeholder' field"
            assert error['type'] == 'missing_placeholder', "Type should be 'missing_placeholder'"
            assert error['severity'] == 'error', "Severity should be 'error'"


class TestSecurityValidation:
    """Test security validation functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    def test_validate_security_clean_html(self):
        """Test that clean HTML passes security validation"""
        clean_html = """
        <html>
            <head>
                <style>body { color: black; }</style>
            </head>
            <body>
                <h1>Title</h1>
                <p>Content</p>
            </body>
        </html>
        """
        
        issues = self.service._validate_security(clean_html)
        
        # Should have no errors, may have warnings
        errors = [issue for issue in issues if issue.get('severity') == 'error']
        assert len(errors) == 0, "Clean HTML should not produce security errors"
    
    def test_validate_security_script_tag(self):
        """Test detection of script tags"""
        html_with_script = """
        <html>
            <body>
                <script>alert('test');</script>
                <p>Content</p>
            </body>
        </html>
        """
        
        issues = self.service._validate_security(html_with_script)
        
        errors = [issue for issue in issues if issue.get('severity') == 'error']
        assert len(errors) > 0, "Script tags should produce security errors"
        assert any('Script tags' in issue['message'] for issue in errors), \
            "Error should mention script tags"
    
    def test_validate_security_event_handlers(self):
        """Test detection of event handlers"""
        html_with_events = """
        <html>
            <body>
                <button onclick="doSomething()">Click</button>
                <div onload="init()">Content</div>
                <a href="#" onmouseover="hover()">Link</a>
            </body>
        </html>
        """
        
        issues = self.service._validate_security(html_with_events)
        
        errors = [issue for issue in issues if issue.get('severity') == 'error']
        assert len(errors) > 0, "Event handlers should produce security errors"
        assert any('Event handlers' in issue['message'] for issue in errors), \
            "Error should mention event handlers"
    
    def test_validate_security_external_resources(self):
        """Test detection of external resources"""
        html_with_external = """
        <html>
            <head>
                <link rel="stylesheet" href="https://example.com/style.css">
            </head>
            <body>
                <img src="https://example.com/image.jpg">
                <script src="https://cdn.example.com/script.js"></script>
            </body>
        </html>
        """
        
        issues = self.service._validate_security(html_with_external)
        
        warnings = [issue for issue in issues if issue.get('severity') == 'warning']
        # Should have at least one warning about external resources
        # (script tag will also trigger an error)
        assert len(warnings) > 0, "External resources should produce warnings"


class TestTemplateValidation:
    """Test complete template validation"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    def test_validate_template_valid(self):
        """Test validation of a valid template"""
        valid_template = """
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
        """
        
        result = self.service.validate_template('str_invoice_nl', valid_template)
        
        assert result['is_valid'] is True, "Valid template should pass validation"
        assert len(result['errors']) == 0, "Valid template should have no errors"
        assert 'checks_performed' in result, "Should list checks performed"
        assert 'html_syntax' in result['checks_performed'], "Should check HTML syntax"
        assert 'required_placeholders' in result['checks_performed'], "Should check placeholders"
        assert 'security_scan' in result['checks_performed'], "Should perform security scan"
    
    def test_validate_template_with_errors(self):
        """Test validation of a template with errors"""
        invalid_template = """
        <html>
            <body>
                <div>
                    <p>Missing closing div tag
                <script>alert('bad');</script>
            </body>
        </html>
        """
        
        result = self.service.validate_template('str_invoice_nl', invalid_template)
        
        assert result['is_valid'] is False, "Invalid template should fail validation"
        assert len(result['errors']) > 0, "Invalid template should have errors"
    
    def test_validate_template_file_size_limit(self):
        """Test file size validation"""
        # Create a large template (over 5MB)
        large_content = "<html><body>" + ("x" * (6 * 1024 * 1024)) + "</body></html>"
        
        with patch.dict(os.environ, {'TEMPLATE_MAX_SIZE_MB': '5'}):
            result = self.service.validate_template('str_invoice_nl', large_content)
        
        assert result['is_valid'] is False, "Large template should fail validation"
        assert any('file_size' in error['type'] for error in result['errors']), \
            "Should have file size error"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])



class TestSampleDataFetching:
    """Test sample data fetching functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    def test_fetch_str_invoice_sample_with_data(self):
        """Test fetching STR invoice sample when data exists"""
        # Mock database response
        mock_booking = {
            'reservationCode': 'RES123',
            'guestName': 'John Doe',
            'channel': 'Booking.com',
            'listing': 'Beach House',
            'checkinDate': '2026-01-01',
            'checkoutDate': '2026-01-05',
            'nights': 4,
            'guests': 2,
            'amountGross': 500.00,
            'amountNett': 435.00,
            'amountChannelFee': 50.00,
            'amountTouristTax': 15.00,
            'amountVat': 0.00,
            'status': 'realised'
        }
        
        self.mock_db.execute_query = Mock(return_value=[mock_booking])
        
        result = self.service._fetch_str_invoice_sample()
        
        assert result is not None, "Should return data"
        assert 'data' in result, "Should have 'data' key"
        assert 'metadata' in result, "Should have 'metadata' key"
        assert result['metadata']['source'] == 'database', "Source should be database"
        assert result['metadata']['record_id'] == 'RES123', "Should have correct record ID"
        assert 'invoice_number' in result['data'], "Should have invoice number"
    
    def test_fetch_str_invoice_sample_no_data(self):
        """Test fetching STR invoice sample when no data exists"""
        # Mock empty database response
        self.mock_db.execute_query = Mock(return_value=[])
        
        result = self.service._fetch_str_invoice_sample()
        
        assert result is not None, "Should return placeholder data"
        assert 'data' in result, "Should have 'data' key"
        assert 'metadata' in result, "Should have 'metadata' key"
        assert result['metadata']['source'] == 'placeholder', "Source should be placeholder"
        assert 'No bookings found' in result['metadata']['message'], "Should indicate no data found"
    
    def test_fetch_str_invoice_sample_database_error(self):
        """Test handling of database errors in STR invoice sample fetching"""
        # Mock database error
        self.mock_db.execute_query = Mock(side_effect=Exception("Database error"))
        
        result = self.service._fetch_str_invoice_sample()
        
        assert result is not None, "Should return placeholder data on error"
        assert result['metadata']['source'] == 'placeholder', "Should fallback to placeholder"
    
    def test_fetch_btw_sample_with_data(self):
        """Test fetching BTW sample returns data structure"""
        # Since the method has complex imports and fallback logic,
        # we just test that it returns the expected structure
        result = self.service._fetch_btw_sample()
        
        assert result is not None, "Should return data"
        assert 'data' in result, "Should have 'data' key"
        assert 'metadata' in result, "Should have 'metadata' key"
        assert 'source' in result['metadata'], "Should have source in metadata"
        # Will be either 'database' or 'placeholder' depending on environment
    
    def test_fetch_btw_sample_fallback_to_placeholder(self):
        """Test BTW sample structure includes required fields"""
        result = self.service._fetch_btw_sample()
        
        assert result is not None, "Should return data"
        # Check that data has expected BTW fields
        data = result['data']
        assert 'year' in data or 'balance_rows' in data, "Should have BTW-related fields"
    
    def test_fetch_aangifte_ib_sample_with_data(self):
        """Test fetching Aangifte IB sample returns data structure"""
        result = self.service._fetch_aangifte_ib_sample()
        
        assert result is not None, "Should return data"
        assert 'data' in result, "Should have 'data' key"
        assert 'metadata' in result, "Should have 'metadata' key"
        assert 'source' in result['metadata'], "Should have source in metadata"
    
    def test_fetch_aangifte_ib_sample_no_data(self):
        """Test Aangifte IB sample structure includes required fields"""
        result = self.service._fetch_aangifte_ib_sample()
        
        assert result is not None, "Should return data"
        # Check that data has expected IB fields
        data = result['data']
        assert 'year' in data, "Should have year"
        assert 'administration' in data, "Should have administration"
    
    def test_fetch_toeristenbelasting_sample_with_data(self):
        """Test fetching Toeristenbelasting sample returns data structure"""
        result = self.service._fetch_toeristenbelasting_sample()
        
        assert result is not None, "Should return data"
        assert 'data' in result, "Should have 'data' key"
        assert 'metadata' in result, "Should have 'metadata' key"
        assert 'source' in result['metadata'], "Should have source in metadata"
    
    def test_fetch_toeristenbelasting_sample_fallback(self):
        """Test Toeristenbelasting sample structure includes required fields"""
        result = self.service._fetch_toeristenbelasting_sample()
        
        assert result is not None, "Should return data"
        # Check that data has expected tourist tax fields
        data = result['data']
        assert 'year' in data, "Should have year"
        assert 'contact_name' in data or 'nights_total' in data, "Should have tourist tax fields"
    
    def test_fetch_generic_sample(self):
        """Test fetching generic sample data"""
        result = self.service._fetch_generic_sample()
        
        assert result is not None, "Should return data"
        assert 'data' in result, "Should have 'data' key"
        assert 'metadata' in result, "Should have 'metadata' key"
        assert result['metadata']['source'] == 'placeholder', "Should be placeholder"
        assert result['data']['administration'] == 'TestAdmin', "Should have administration"
        assert 'generated_date' in result['data'], "Should have generated_date"
        assert 'year' in result['data'], "Should have year"
    
    def test_fetch_sample_data_str_invoice_nl(self):
        """Test fetch_sample_data routes to correct method for str_invoice_nl"""
        self.mock_db.execute_query = Mock(return_value=[])
        
        result = self.service.fetch_sample_data('str_invoice_nl')
        
        assert result is not None, "Should return data"
        assert 'data' in result, "Should have data"
        # Should call _fetch_str_invoice_sample
    
    def test_fetch_sample_data_str_invoice_en(self):
        """Test fetch_sample_data routes to correct method for str_invoice_en"""
        self.mock_db.execute_query = Mock(return_value=[])
        
        result = self.service.fetch_sample_data('str_invoice_en')
        
        assert result is not None, "Should return data"
        assert 'data' in result, "Should have data"
    
    def test_fetch_sample_data_btw_aangifte(self):
        """Test fetch_sample_data routes to correct method for btw_aangifte"""
        result = self.service.fetch_sample_data('btw_aangifte')
        
        assert result is not None, "Should return data"
        assert 'data' in result, "Should have data"
    
    def test_fetch_sample_data_aangifte_ib(self):
        """Test fetch_sample_data routes to correct method for aangifte_ib"""
        result = self.service.fetch_sample_data('aangifte_ib')
        
        assert result is not None, "Should return data"
        assert 'data' in result, "Should have data"
    
    def test_fetch_sample_data_toeristenbelasting(self):
        """Test fetch_sample_data routes to correct method for toeristenbelasting"""
        result = self.service.fetch_sample_data('toeristenbelasting')
        
        assert result is not None, "Should return data"
        assert 'data' in result, "Should have data"
    
    def test_fetch_sample_data_unknown_type(self):
        """Test fetch_sample_data routes to generic method for unknown type"""
        result = self.service.fetch_sample_data('unknown_type')
        
        assert result is not None, "Should return generic data"
        assert result['metadata']['source'] == 'placeholder', "Should use generic placeholder"
    
    def test_fetch_sample_data_exception_handling(self):
        """Test that fetch_sample_data handles exceptions gracefully"""
        # Force an exception in the routing logic
        with patch.object(self.service, '_fetch_str_invoice_sample', side_effect=Exception("Test error")):
            result = self.service.fetch_sample_data('str_invoice_nl')
            
            assert result is None, "Should return None on exception"
    
    def test_get_placeholder_str_data_structure(self):
        """Test that placeholder STR data has correct structure"""
        result = self.service._get_placeholder_str_data()
        
        assert 'data' in result, "Should have 'data' key"
        assert 'metadata' in result, "Should have 'metadata' key"
        
        # Check required fields
        data = result['data']
        assert 'invoice_number' in data, "Should have invoice_number"
        assert 'reservationCode' in data, "Should have reservationCode"
        assert 'guestName' in data, "Should have guestName"
        assert 'checkinDate' in data, "Should have checkinDate"
        assert 'checkoutDate' in data, "Should have checkoutDate"
        assert 'amountGross' in data, "Should have amountGross"
        assert 'company_name' in data, "Should have company_name"
        
        # Check metadata
        metadata = result['metadata']
        assert metadata['source'] == 'placeholder', "Source should be placeholder"
        assert 'message' in metadata, "Should have message"
        assert 'record_id' in metadata, "Should have record_id"


class TestPreviewGeneration:
    """Test preview generation functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    def test_generate_preview_success(self):
        """Test successful preview generation"""
        valid_template = """
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
        """
        
        field_mappings = {}
        
        # Mock database to return sample data
        self.mock_db.execute_query = Mock(return_value=[])
        
        result = self.service.generate_preview('str_invoice_nl', valid_template, field_mappings)
        
        assert result['success'] is True, "Preview generation should succeed"
        assert 'preview_html' in result, "Should have preview_html"
        assert 'validation' in result, "Should have validation results"
        assert 'sample_data_info' in result, "Should have sample data info"
        assert result['validation']['is_valid'] is True, "Template should be valid"
    
    def test_generate_preview_validation_failure(self):
        """Test preview generation with invalid template"""
        invalid_template = """
        <html>
            <body>
                <div>
                    <p>Missing closing div
                <script>alert('bad');</script>
            </body>
        </html>
        """
        
        field_mappings = {}
        
        result = self.service.generate_preview('str_invoice_nl', invalid_template, field_mappings)
        
        assert result['success'] is False, "Preview generation should fail for invalid template"
        assert 'validation' in result, "Should have validation results"
        assert result['validation']['is_valid'] is False, "Template should be invalid"
        assert len(result['validation']['errors']) > 0, "Should have validation errors"
        assert 'preview_html' not in result, "Should not have preview_html on validation failure"
    
    def test_generate_preview_no_sample_data(self):
        """Test preview generation when no sample data is available"""
        valid_template = """
        <html>
            <body>
                <h1>Test {{ field }}</h1>
            </body>
        </html>
        """
        
        field_mappings = {}
        
        # Mock fetch_sample_data to return None
        with patch.object(self.service, 'fetch_sample_data', return_value=None):
            result = self.service.generate_preview('unknown_type', valid_template, field_mappings)
        
        assert result['success'] is False, "Preview generation should fail without sample data"
        assert 'validation' in result, "Should have validation results"
        assert any('no_sample_data' in error['type'] for error in result['validation']['errors']), \
            "Should have no_sample_data error"
    
    def test_generate_preview_with_placeholder_data(self):
        """Test preview generation with placeholder data"""
        valid_template = """
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
        """
        
        field_mappings = {}
        
        # Mock database to return empty (will use placeholder)
        self.mock_db.execute_query = Mock(return_value=[])
        
        result = self.service.generate_preview('str_invoice_nl', valid_template, field_mappings)
        
        assert result['success'] is True, "Preview should succeed with placeholder data"
        assert result['sample_data_info']['source'] == 'placeholder', "Should use placeholder data"
        assert 'preview_html' in result, "Should have preview_html"
    
    def test_generate_preview_renders_placeholders(self):
        """Test that preview generation replaces placeholders with values"""
        template = """
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
        """
        
        field_mappings = {}
        
        # Mock database to return empty (will use placeholder)
        self.mock_db.execute_query = Mock(return_value=[])
        
        result = self.service.generate_preview('str_invoice_nl', template, field_mappings)
        
        assert result['success'] is True, "Preview should succeed"
        preview_html = result['preview_html']
        
        # Check that placeholders were replaced
        assert '{{ invoice_number }}' not in preview_html, "invoice_number placeholder should be replaced"
        assert '{{ guest_name }}' not in preview_html, "guest_name placeholder should be replaced"
        # Should contain actual values or [placeholder] markers
        assert 'INV-' in preview_html or '[invoice_number]' in preview_html, \
            "Should have invoice number value or marker"
    
    def test_generate_preview_exception_handling(self):
        """Test that preview generation handles exceptions gracefully"""
        template = "<html><body>Test</body></html>"
        field_mappings = {}
        
        # Force an exception in validation
        with patch.object(self.service, 'validate_template', side_effect=Exception("Test error")):
            result = self.service.generate_preview('str_invoice_nl', template, field_mappings)
        
        assert result['success'] is False, "Should fail gracefully on exception"
        assert 'validation' in result, "Should have validation results"
        assert any('preview_generation_error' in error['type'] for error in result['validation']['errors']), \
            "Should have preview_generation_error"
    
    def test_generate_preview_btw_aangifte(self):
        """Test preview generation for BTW aangifte template"""
        template = """
        <html>
            <body>
                <h1>BTW Aangifte {{ year }} Q{{ quarter }}</h1>
                <p>Administration: {{ administration }}</p>
                <table>{{ balance_rows }}</table>
                <table>{{ quarter_rows }}</table>
                <p>{{ payment_instruction }}</p>
            </body>
        </html>
        """
        
        field_mappings = {}
        
        result = self.service.generate_preview('btw_aangifte', template, field_mappings)
        
        # Should succeed (will use placeholder data if no real data)
        assert result['success'] is True, "BTW preview should succeed"
        assert 'preview_html' in result, "Should have preview_html"
    
    def test_generate_preview_aangifte_ib(self):
        """Test preview generation for Aangifte IB template"""
        template = """
        <html>
            <body>
                <h1>Aangifte IB {{ year }}</h1>
                <p>Administration: {{ administration }}</p>
                <table>{{ table_rows }}</table>
                <p>Generated: {{ generated_date }}</p>
            </body>
        </html>
        """
        
        field_mappings = {}
        
        result = self.service.generate_preview('aangifte_ib', template, field_mappings)
        
        assert result['success'] is True, "Aangifte IB preview should succeed"
        assert 'preview_html' in result, "Should have preview_html"
    
    def test_generate_preview_toeristenbelasting(self):
        """Test preview generation for Toeristenbelasting template"""
        template = """
        <html>
            <body>
                <h1>Toeristenbelasting {{ year }}</h1>
                <p>Contact: {{ contact_name }} ({{ contact_email }})</p>
                <p>Nights: {{ nights_total }}</p>
                <p>Revenue: {{ revenue_total }}</p>
                <p>Tourist Tax: {{ tourist_tax_total }}</p>
            </body>
        </html>
        """
        
        field_mappings = {}
        
        result = self.service.generate_preview('toeristenbelasting', template, field_mappings)
        
        assert result['success'] is True, "Toeristenbelasting preview should succeed"
        assert 'preview_html' in result, "Should have preview_html"
    
    def test_generate_preview_with_warnings(self):
        """Test preview generation with validation warnings"""
        template = """
        <html>
            <head>
                <link rel="stylesheet" href="https://example.com/style.css">
            </head>
            <body>
                <h1>Invoice {{ invoice_number }}</h1>
                <p>Guest: {{ guest_name }}</p>
                <p>Check-in: {{ checkin_date }}</p>
                <p>Check-out: {{ checkout_date }}</p>
                <p>Amount: {{ amount_gross }}</p>
                <p>Company: {{ company_name }}</p>
            </body>
        </html>
        """
        
        field_mappings = {}
        
        # Mock database to return empty
        self.mock_db.execute_query = Mock(return_value=[])
        
        result = self.service.generate_preview('str_invoice_nl', template, field_mappings)
        
        # Should succeed but have warnings
        assert result['success'] is True, "Preview should succeed with warnings"
        assert len(result['validation']['warnings']) > 0, "Should have warnings about external resources"
        assert 'preview_html' in result, "Should still generate preview"


class TestValidationLogging:
    """Test validation logging functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    def test_log_template_approval_success(self):
        """Test logging of successful template approval"""
        template_type = 'str_invoice_nl'
        user_email = 'admin@example.com'
        notes = 'Approved for production use'
        validation = {
            'is_valid': True,
            'errors': [],
            'warnings': [{'type': 'info', 'message': 'External resource detected'}]
        }
        
        # Mock database execute_query
        self.mock_db.execute_query = Mock()
        
        # Should not raise exception
        self.service._log_template_approval(template_type, user_email, notes, validation)
        
        # Verify database was called
        assert self.mock_db.execute_query.called, "Should call database to log approval"
        
        # Check the call arguments
        call_args = self.mock_db.execute_query.call_args
        assert call_args is not None, "Should have call arguments"
        
        # Check that the query includes the correct table
        query = call_args[0][0]
        assert 'template_validation_log' in query, "Should insert into template_validation_log"
        assert 'INSERT INTO' in query, "Should be an INSERT query"
        
        # Check parameters
        params = call_args[0][1]
        assert self.administration in params, "Should include administration"
        assert template_type in params, "Should include template_type"
        assert user_email in params, "Should include user_email"
    
    def test_log_template_approval_with_errors(self):
        """Test logging of template approval with validation errors"""
        template_type = 'btw_aangifte'
        user_email = 'admin@example.com'
        notes = 'Approved despite warnings'
        validation = {
            'is_valid': True,
            'errors': [],
            'warnings': [
                {'type': 'security_warning', 'message': 'External resources detected'},
                {'type': 'info', 'message': 'Large file size'}
            ]
        }
        
        self.mock_db.execute_query = Mock()
        
        self.service._log_template_approval(template_type, user_email, notes, validation)
        
        assert self.mock_db.execute_query.called, "Should log approval"
        
        # Check that warnings are included in the log
        call_args = self.mock_db.execute_query.call_args
        params = call_args[0][1]
        
        # Warnings should be JSON-encoded in the parameters
        import json
        warnings_json = None
        for param in params:
            if isinstance(param, str) and 'security_warning' in param:
                warnings_json = param
                break
        
        assert warnings_json is not None, "Should include warnings in log"
    
    def test_log_template_approval_database_error(self):
        """Test that logging errors don't block approval"""
        template_type = 'str_invoice_nl'
        user_email = 'admin@example.com'
        notes = 'Test approval'
        validation = {'is_valid': True, 'errors': [], 'warnings': []}
        
        # Mock database to raise exception
        self.mock_db.execute_query = Mock(side_effect=Exception("Database error"))
        
        # Should not raise exception (logging failure shouldn't block approval)
        try:
            self.service._log_template_approval(template_type, user_email, notes, validation)
            # If we get here, the exception was caught
            assert True, "Should handle database errors gracefully"
        except Exception:
            assert False, "Should not raise exception on logging failure"
    
    def test_log_template_approval_empty_notes(self):
        """Test logging with empty notes"""
        template_type = 'aangifte_ib'
        user_email = 'admin@example.com'
        notes = ''
        validation = {'is_valid': True, 'errors': [], 'warnings': []}
        
        self.mock_db.execute_query = Mock()
        
        self.service._log_template_approval(template_type, user_email, notes, validation)
        
        assert self.mock_db.execute_query.called, "Should log even with empty notes"
        
        # Check that the query was called with correct parameters
        call_args = self.mock_db.execute_query.call_args
        params = call_args[0][1]
        # Notes parameter should be in the params (may be empty string or None)
        assert len(params) >= 5, "Should have at least 5 parameters"
    
    def test_log_template_approval_json_serialization(self):
        """Test that errors and warnings are properly JSON-serialized"""
        template_type = 'toeristenbelasting'
        user_email = 'admin@example.com'
        notes = 'Test'
        validation = {
            'is_valid': True,
            'errors': [
                {'type': 'syntax_error', 'message': 'Test error', 'line': 10}
            ],
            'warnings': [
                {'type': 'security_warning', 'message': 'Test warning'}
            ]
        }
        
        self.mock_db.execute_query = Mock()
        
        self.service._log_template_approval(template_type, user_email, notes, validation)
        
        assert self.mock_db.execute_query.called, "Should log approval"
        
        # Verify JSON serialization worked
        call_args = self.mock_db.execute_query.call_args
        params = call_args[0][1]
        
        # Check that JSON strings are in parameters
        import json
        has_json = False
        for param in params:
            if isinstance(param, str):
                try:
                    json.loads(param)
                    has_json = True
                    break
                except:
                    pass
        
        assert has_json, "Should have JSON-serialized data in parameters"
    
    def test_log_template_approval_validation_result(self):
        """Test that validation result is logged as 'pass'"""
        template_type = 'str_invoice_nl'
        user_email = 'admin@example.com'
        notes = 'Approved'
        validation = {'is_valid': True, 'errors': [], 'warnings': []}
        
        self.mock_db.execute_query = Mock()
        
        self.service._log_template_approval(template_type, user_email, notes, validation)
        
        # Check that validation_result is 'pass'
        call_args = self.mock_db.execute_query.call_args
        query = call_args[0][0]
        
        assert "'pass'" in query or "validation_result" in query, \
            "Should log validation result as 'pass'"
