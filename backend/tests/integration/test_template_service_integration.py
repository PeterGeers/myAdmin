"""
Integration tests for TemplateService integration with tax form routes

Tests that BTW Aangifte, Aangifte IB, and Toeristenbelasting routes
properly use TemplateService for template loading and field mapping.
"""

import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.template_service import TemplateService
from database import DatabaseManager


class TestTemplateServiceIntegration:
    """Test TemplateService integration with tax form generation"""
    
    @pytest.fixture
    def db(self):
        """Create database manager instance"""
        return DatabaseManager(test_mode=True)
    
    @pytest.fixture
    def template_service(self, db):
        """Create TemplateService instance"""
        return TemplateService(db)
    
    def test_template_service_initialization(self, template_service):
        """Test that TemplateService initializes correctly"""
        assert template_service is not None
        assert template_service.db is not None
    
    def test_apply_field_mappings_simple(self, template_service):
        """Test simple field mapping application"""
        template = "<html><body><h1>{{ title }}</h1><p>{{ content }}</p></body></html>"
        data = {
            'title': 'Test Report',
            'content': 'This is test content'
        }
        field_mappings = {
            'fields': {
                'title': {'path': 'title', 'format': 'text'},
                'content': {'path': 'content', 'format': 'text'}
            },
            'formatting': {
                'locale': 'nl_NL',
                'currency': 'EUR'
            }
        }
        
        result = template_service.apply_field_mappings(template, data, field_mappings)
        
        assert 'Test Report' in result
        assert 'This is test content' in result
        assert '{{ title }}' not in result
        assert '{{ content }}' not in result
    
    def test_apply_field_mappings_with_html_content(self, template_service):
        """Test field mapping with pre-generated HTML content (like table rows)"""
        template = "<html><body><table>{{ table_rows }}</table></body></html>"
        data = {
            'table_rows': '<tr><td>Row 1</td></tr><tr><td>Row 2</td></tr>'
        }
        field_mappings = {
            'fields': {
                'table_rows': {'path': 'table_rows', 'format': 'html'}
            },
            'formatting': {}
        }
        
        result = template_service.apply_field_mappings(template, data, field_mappings)
        
        assert '<tr><td>Row 1</td></tr>' in result
        assert '<tr><td>Row 2</td></tr>' in result
        assert '{{ table_rows }}' not in result
    
    def test_apply_field_mappings_with_missing_field(self, template_service):
        """Test field mapping with missing field uses default"""
        template = "<html><body><p>{{ missing_field }}</p></body></html>"
        data = {}
        field_mappings = {
            'fields': {
                'missing_field': {'path': 'missing_field', 'format': 'text', 'default': 'Default Value'}
            },
            'formatting': {}
        }
        
        result = template_service.apply_field_mappings(template, data, field_mappings)
        
        assert 'Default Value' in result
        assert '{{ missing_field }}' not in result
    
    def test_btw_aangifte_template_structure(self, template_service):
        """Test BTW Aangifte template structure with typical data"""
        # Simulate BTW Aangifte template data
        template = """
        <html>
        <head><title>BTW Aangifte {{ year }} Q{{ quarter }}</title></head>
        <body>
            <h1>BTW Aangifte {{ administration }}</h1>
            <p>Jaar: {{ year }}, Kwartaal: {{ quarter }}</p>
            <p>Einddatum: {{ end_date }}</p>
            <table>{{ balance_rows }}</table>
            <table>{{ quarter_rows }}</table>
            <p>Ontvangen BTW: {{ received_btw }}</p>
            <p>Vooruitbetaald BTW: {{ prepaid_btw }}</p>
            <p>{{ payment_instruction }}</p>
        </body>
        </html>
        """
        
        data = {
            'administration': 'GoodwinSolutions',
            'year': '2025',
            'quarter': '1',
            'end_date': '2025-03-31',
            'balance_rows': '<tr><td>2010</td><td>BTW te betalen</td><td>€1.000,00</td></tr>',
            'quarter_rows': '<tr><td>2020</td><td>BTW ontvangen</td><td>€500,00</td></tr>',
            'received_btw': '€500,00',
            'prepaid_btw': '€-500,00',
            'payment_instruction': '€1000 te ontvangen'
        }
        
        field_mappings = {
            'fields': {key: {'path': key, 'format': 'text'} for key in data.keys()},
            'formatting': {'locale': 'nl_NL', 'currency': 'EUR'}
        }
        
        result = template_service.apply_field_mappings(template, data, field_mappings)
        
        # Verify all placeholders are replaced
        assert '{{ administration }}' not in result
        assert '{{ year }}' not in result
        assert '{{ quarter }}' not in result
        assert 'GoodwinSolutions' in result
        assert '2025' in result
        assert '€1.000,00' in result
    
    def test_aangifte_ib_template_structure(self, template_service):
        """Test Aangifte IB template structure with typical data"""
        template = """
        <html>
        <head><title>Aangifte IB {{ year }}</title></head>
        <body>
            <h1>Aangifte Inkomstenbelasting {{ year }}</h1>
            <p>Administratie: {{ administration }}</p>
            <p>Gegenereerd: {{ generated_date }}</p>
            <table>{{ table_rows }}</table>
        </body>
        </html>
        """
        
        data = {
            'year': '2025',
            'administration': 'PeterPrive',
            'generated_date': '2025-01-31 12:00:00',
            'table_rows': '<tr><td>4000</td><td>Omzet</td><td>€10.000,00</td></tr>'
        }
        
        field_mappings = {
            'fields': {key: {'path': key, 'format': 'text'} for key in data.keys()},
            'formatting': {'locale': 'nl_NL'}
        }
        
        result = template_service.apply_field_mappings(template, data, field_mappings)
        
        # Verify all placeholders are replaced
        assert '{{ year }}' not in result
        assert '{{ administration }}' not in result
        assert 'PeterPrive' in result
        assert '2025' in result
        assert '€10.000,00' in result
