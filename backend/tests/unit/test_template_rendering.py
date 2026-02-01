"""
Unit tests for Template Rendering
Tests template rendering with field mappings, value formatting, and edge cases
"""

import sys
import os
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# Add backend/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.template_preview_service import TemplatePreviewService


class TestTemplateRendering:
    """Test template rendering with field mappings"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    def test_render_template_basic(self):
        """Test basic template rendering with simple placeholders"""
        # Setup
        template_content = """
        <html>
            <body>
                <h1>{{ title }}</h1>
                <p>{{ content }}</p>
            </body>
        </html>
        """
        sample_data = {
            'title': 'Test Title',
            'content': 'Test Content'
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert 'Test Title' in rendered, "Should replace title placeholder"
        assert 'Test Content' in rendered, "Should replace content placeholder"
        assert '{{ title }}' not in rendered, "Should not have unreplaced placeholders"
        assert '{{ content }}' not in rendered, "Should not have unreplaced placeholders"
    
    def test_render_template_with_date_formatting(self):
        """Test date value formatting"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>Date: {{ date_field }}</p>
            </body>
        </html>
        """
        sample_data = {
            'date_field': datetime(2026, 2, 1, 10, 30, 0)
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert '01-02-2026' in rendered, "Should format date as DD-MM-YYYY"
        assert '{{ date_field }}' not in rendered, "Should replace date placeholder"
    
    def test_render_template_with_number_formatting(self):
        """Test number value formatting (currency)"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>Amount: {{ amount }}</p>
                <p>Price: {{ price }}</p>
            </body>
        </html>
        """
        sample_data = {
            'amount': 1234.56,
            'price': 999.99
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert '1,234.56' in rendered, "Should format amount with thousands separator"
        assert '999.99' in rendered, "Should format price with 2 decimals"
        assert '{{ amount }}' not in rendered, "Should replace amount placeholder"
        assert '{{ price }}' not in rendered, "Should replace price placeholder"
    
    def test_render_template_with_integer_formatting(self):
        """Test integer value formatting"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>Count: {{ count }}</p>
            </body>
        </html>
        """
        sample_data = {
            'count': 42
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert '42.00' in rendered, "Should format integer as decimal"
        assert '{{ count }}' not in rendered, "Should replace count placeholder"
    
    def test_render_template_with_missing_values(self):
        """Test rendering when sample data is missing values"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>Name: {{ name }}</p>
                <p>Email: {{ email }}</p>
                <p>Phone: {{ phone }}</p>
            </body>
        </html>
        """
        sample_data = {
            'name': 'John Doe'
            # email and phone are missing
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert 'John Doe' in rendered, "Should replace available values"
        assert '[email]' in rendered, "Should use placeholder marker for missing email"
        assert '[phone]' in rendered, "Should use placeholder marker for missing phone"
    
    def test_render_template_with_whitespace_variations(self):
        """Test rendering with various whitespace in placeholders"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>{{field1}}</p>
                <p>{{ field2 }}</p>
                <p>{{  field3  }}</p>
                <p>{{ field4}}</p>
                <p>{{field5 }}</p>
            </body>
        </html>
        """
        sample_data = {
            'field1': 'Value 1',
            'field2': 'Value 2',
            'field3': 'Value 3',
            'field4': 'Value 4',
            'field5': 'Value 5'
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert 'Value 1' in rendered, "Should handle no whitespace"
        assert 'Value 2' in rendered, "Should handle single space"
        assert 'Value 3' in rendered, "Should handle multiple spaces"
        assert 'Value 4' in rendered, "Should handle trailing space"
        assert 'Value 5' in rendered, "Should handle leading space"
    
    def test_render_template_with_multiple_occurrences(self):
        """Test rendering when same placeholder appears multiple times"""
        # Setup
        template_content = """
        <html>
            <body>
                <h1>{{ company_name }}</h1>
                <p>Welcome to {{ company_name }}</p>
                <footer>© {{ company_name }}</footer>
            </body>
        </html>
        """
        sample_data = {
            'company_name': 'Acme Corp'
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert rendered.count('Acme Corp') == 3, "Should replace all occurrences"
        assert '{{ company_name }}' not in rendered, "Should not have unreplaced placeholders"
    
    def test_render_template_with_special_characters(self):
        """Test rendering with special characters in values"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>Name: {{ name }}</p>
                <p>Address: {{ address }}</p>
            </body>
        </html>
        """
        sample_data = {
            'name': "O'Brien & Associates",
            'address': '123 Main St. <Suite #5>'
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert "O'Brien & Associates" in rendered, "Should handle apostrophes and ampersands"
        assert '123 Main St. <Suite #5>' in rendered, "Should handle special characters"
    
    def test_render_template_with_string_values(self):
        """Test rendering with string values (no formatting)"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>{{ text1 }}</p>
                <p>{{ text2 }}</p>
            </body>
        </html>
        """
        sample_data = {
            'text1': 'Simple text',
            'text2': 'Text with numbers 123'
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert 'Simple text' in rendered, "Should render simple text"
        assert 'Text with numbers 123' in rendered, "Should render text with numbers"
    
    def test_render_template_with_empty_string(self):
        """Test rendering with empty string values"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>Field: {{ field }}</p>
            </body>
        </html>
        """
        sample_data = {
            'field': ''
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert 'Field: </p>' in rendered or 'Field: <' in rendered, \
            "Should render empty string (no placeholder marker)"
        assert '{{ field }}' not in rendered, "Should replace placeholder even with empty value"
    
    def test_render_template_with_none_value(self):
        """Test rendering with None values"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>Field: {{ field }}</p>
            </body>
        </html>
        """
        sample_data = {
            'field': None
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        # None should be converted to string 'None'
        assert 'None' in rendered or '[field]' in rendered, \
            "Should handle None value"
    
    def test_render_template_exception_handling(self):
        """Test rendering handles exceptions gracefully"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>{{ field }}</p>
            </body>
        </html>
        """
        sample_data = {
            'field': 'value'
        }
        field_mappings = {}
        
        # Mock re.sub to raise exception
        with patch('re.sub', side_effect=Exception("Regex error")):
            # Execute
            rendered = self.service._render_template(
                template_content,
                sample_data,
                field_mappings
            )
        
        # Assert - should return original template on error
        assert '{{ field }}' in rendered, "Should return original template on error"
    
    def test_render_template_with_large_numbers(self):
        """Test rendering with large numbers"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>Amount: {{ amount }}</p>
            </body>
        </html>
        """
        sample_data = {
            'amount': 1234567.89
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert '1,234,567.89' in rendered, "Should format large numbers with thousands separators"
    
    def test_render_template_with_negative_numbers(self):
        """Test rendering with negative numbers"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>Balance: {{ balance }}</p>
            </body>
        </html>
        """
        sample_data = {
            'balance': -500.50
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert '-500.50' in rendered, "Should format negative numbers correctly"
    
    def test_render_template_with_zero(self):
        """Test rendering with zero values"""
        # Setup
        template_content = """
        <html>
            <body>
                <p>Count: {{ count }}</p>
            </body>
        </html>
        """
        sample_data = {
            'count': 0
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert '0.00' in rendered, "Should format zero correctly"
    
    def test_render_template_complex_html(self):
        """Test rendering with complex HTML structure"""
        # Setup
        template_content = """
        <html>
            <head>
                <title>{{ page_title }}</title>
            </head>
            <body>
                <header>
                    <h1>{{ company_name }}</h1>
                </header>
                <main>
                    <section>
                        <h2>Invoice {{ invoice_number }}</h2>
                        <table>
                            <tr>
                                <td>Guest:</td>
                                <td>{{ guest_name }}</td>
                            </tr>
                            <tr>
                                <td>Amount:</td>
                                <td>{{ amount }}</td>
                            </tr>
                        </table>
                    </section>
                </main>
                <footer>
                    <p>{{ footer_text }}</p>
                </footer>
            </body>
        </html>
        """
        sample_data = {
            'page_title': 'Invoice Document',
            'company_name': 'Acme Corp',
            'invoice_number': 'INV-2026-001',
            'guest_name': 'John Doe',
            'amount': 500.00,
            'footer_text': 'Thank you for your business'
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert 'Invoice Document' in rendered, "Should replace title"
        assert 'Acme Corp' in rendered, "Should replace company name"
        assert 'INV-2026-001' in rendered, "Should replace invoice number"
        assert 'John Doe' in rendered, "Should replace guest name"
        assert '500.00' in rendered, "Should replace and format amount"
        assert 'Thank you for your business' in rendered, "Should replace footer text"
        assert '{{' not in rendered, "Should not have any unreplaced placeholders"
    
    def test_render_template_with_html_table_rows(self):
        """Test rendering with HTML table rows as values"""
        # Setup
        template_content = """
        <html>
            <body>
                <table>
                    {{ table_rows }}
                </table>
            </body>
        </html>
        """
        sample_data = {
            'table_rows': '<tr><td>Row 1</td></tr><tr><td>Row 2</td></tr>'
        }
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert '<tr><td>Row 1</td></tr>' in rendered, "Should render HTML table rows"
        assert '<tr><td>Row 2</td></tr>' in rendered, "Should render HTML table rows"
        assert '{{ table_rows }}' not in rendered, "Should replace table_rows placeholder"


class TestFieldMappings:
    """Test field mapping functionality (future enhancement)"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    def test_render_template_field_mappings_parameter_exists(self):
        """Test that field_mappings parameter is accepted"""
        # Setup
        template_content = "<html><body>{{ field }}</body></html>"
        sample_data = {'field': 'value'}
        field_mappings = {'field': 'custom_field'}
        
        # Execute - should not raise exception
        try:
            rendered = self.service._render_template(
                template_content,
                sample_data,
                field_mappings
            )
            assert True, "Should accept field_mappings parameter"
        except TypeError:
            assert False, "Should accept field_mappings parameter"
    
    def test_render_template_with_empty_field_mappings(self):
        """Test rendering with empty field mappings"""
        # Setup
        template_content = "<html><body>{{ field }}</body></html>"
        sample_data = {'field': 'value'}
        field_mappings = {}
        
        # Execute
        rendered = self.service._render_template(
            template_content,
            sample_data,
            field_mappings
        )
        
        # Assert
        assert 'value' in rendered, "Should render normally with empty mappings"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
