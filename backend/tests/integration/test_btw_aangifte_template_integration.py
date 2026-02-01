"""
Integration tests for BTW Aangifte Report Template

Tests the complete flow from data generation to HTML output using the
template and generator.
"""

import pytest
from unittest.mock import Mock
import pandas as pd
from report_generators import btw_aangifte_generator
import os


def _render_template(template_content: str, data: dict) -> str:
    """Simple template rendering using placeholder replacement"""
    result = template_content
    for key, value in data.items():
        placeholder = '{{ ' + key + ' }}'
        result = result.replace(placeholder, str(value))
    return result


@pytest.mark.integration
class TestBTWAangifteTemplateIntegration:
    """Integration tests for BTW Aangifte template rendering"""
    
    def test_template_rendering_with_real_data(self):
        """Test template rendering with realistic BTW data"""
        # Mock cache
        cache = Mock()
        db = Mock()
        
        # Mock balance data (accounts 2010, 2020, 2021)
        balance_df = pd.DataFrame({
            'TransactionDate': ['2025-01-15', '2025-02-20', '2025-03-10'],
            'administration': ['GoodwinSolutions', 'GoodwinSolutions', 'GoodwinSolutions'],
            'Reknum': ['2010', '2020', '2021'],
            'AccountName': ['Betaalde BTW', 'Ontvangen BTW Hoog', 'Ontvangen BTW Laag'],
            'Amount': [164091.95, -115195.00, -50327.26],
            'jaar': [2025, 2025, 2025],
            'kwartaal': [1, 1, 1]
        })
        
        cache.get_data.return_value = balance_df
        
        # Generate report
        report_result = btw_aangifte_generator.generate_btw_report(
            cache=cache,
            db=db,
            administration='GoodwinSolutions',
            year=2025,
            quarter=1
        )
        
        assert report_result['success'] is True
        
        # Get template data
        template_data = btw_aangifte_generator.prepare_template_data(report_result)
        
        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'templates',
            'html',
            'btw_aangifte_template.html'
        )
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Render template
        html_output = _render_template(template_content, template_data)
        
        # Verify HTML output contains expected content
        assert 'BTW aangifte' in html_output  # lowercase 'aangifte' in template
        assert '2025' in html_output
        assert 'Q1' in html_output or '1' in html_output
        assert 'GoodwinSolutions' in html_output
        
        # Verify structure sections are present
        assert 'Eindbalans' in html_output or 'Saldo BTW' in html_output
        assert 'Gegevens kwartaal' in html_output or 'BTW Gegevens' in html_output
        assert 'Samenvatting' in html_output or 'BTW Berekening' in html_output
        
        # Verify table structure
        assert '<table>' in html_output
        assert '<th>Reknum</th>' in html_output or '<th>Rekening</th>' in html_output
        assert '<th>AccountName</th>' in html_output or '<th>Omschrijving</th>' in html_output
        assert 'Amount' in html_output or 'Bedrag' in html_output
        
        # Verify account names
        assert 'Betaalde BTW' in html_output
        assert 'Ontvangen BTW Hoog' in html_output
        assert 'Ontvangen BTW Laag' in html_output
        
        # Verify currency formatting
        assert '€' in html_output
        
        # Verify summary section with calculations
        assert 'Netto:' in html_output or 'te betalen' in html_output or 'te ontvangen' in html_output
        assert 'Ontvangen BTW:' in html_output or 'Vooruitbetaalde BTW:' in html_output
    
    def test_template_all_placeholders_replaced(self):
        """Test that all template placeholders are replaced"""
        # Mock cache
        cache = Mock()
        db = Mock()
        
        # Mock minimal data
        balance_df = pd.DataFrame({
            'TransactionDate': ['2025-04-15', '2025-05-20', '2025-06-10'],
            'administration': ['TestAdmin', 'TestAdmin', 'TestAdmin'],
            'Reknum': ['2010', '2020', '2021'],
            'AccountName': ['Betaalde BTW', 'Ontvangen BTW Hoog', 'Ontvangen BTW Laag'],
            'Amount': [10000.00, -5000.00, -2000.00],
            'jaar': [2025, 2025, 2025],
            'kwartaal': [2, 2, 2]
        })
        
        cache.get_data.return_value = balance_df
        
        # Generate report
        report_result = btw_aangifte_generator.generate_btw_report(
            cache=cache,
            db=db,
            administration='TestAdmin',
            year=2025,
            quarter=2
        )
        
        template_data = btw_aangifte_generator.prepare_template_data(report_result)
        
        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'templates',
            'html',
            'btw_aangifte_template.html'
        )
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Render template
        html_output = _render_template(template_content, template_data)
        
        # Verify no unreplaced placeholders remain
        assert '{{' not in html_output
        assert '}}' not in html_output
    
    def test_template_html_validity(self):
        """Test that generated HTML is valid"""
        # Mock cache
        cache = Mock()
        db = Mock()
        
        balance_df = pd.DataFrame({
            'TransactionDate': ['2025-07-15', '2025-08-20', '2025-09-10'],
            'administration': ['TestAdmin', 'TestAdmin', 'TestAdmin'],
            'Reknum': ['2010', '2020', '2021'],
            'AccountName': ['Betaalde BTW', 'Ontvangen BTW Hoog', 'Ontvangen BTW Laag'],
            'Amount': [10000.00, -5000.00, -2000.00],
            'jaar': [2025, 2025, 2025],
            'kwartaal': [3, 3, 3]
        })
        
        cache.get_data.return_value = balance_df
        
        # Generate report
        report_result = btw_aangifte_generator.generate_btw_report(
            cache=cache,
            db=db,
            administration='TestAdmin',
            year=2025,
            quarter=3
        )
        
        template_data = btw_aangifte_generator.prepare_template_data(report_result)
        
        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'templates',
            'html',
            'btw_aangifte_template.html'
        )
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Render template
        html_output = _render_template(template_content, template_data)
        
        # Basic HTML structure checks
        assert html_output.startswith('<!DOCTYPE html>')
        assert '<html>' in html_output
        assert '</html>' in html_output
        assert '<head>' in html_output
        assert '</head>' in html_output
        assert '<body>' in html_output
        assert '</body>' in html_output
        
        # Check for proper tag closure
        assert html_output.count('<table>') == html_output.count('</table>')
        assert html_output.count('<div') == html_output.count('</div>')
    
    def test_quarter_calculations(self):
        """Test BTW calculations for different quarters"""
        # Mock cache
        cache = Mock()
        db = Mock()
        
        # Test data with known values
        balance_df = pd.DataFrame({
            'TransactionDate': ['2025-10-15', '2025-11-20', '2025-12-10'],
            'administration': ['TestAdmin', 'TestAdmin', 'TestAdmin'],
            'Reknum': ['2010', '2020', '2021'],
            'AccountName': ['Betaalde BTW', 'Ontvangen BTW Hoog', 'Ontvangen BTW Laag'],
            'Amount': [30000.00, -20000.00, -8000.00],
            'jaar': [2025, 2025, 2025],
            'kwartaal': [4, 4, 4]
        })
        
        cache.get_data.return_value = balance_df
        
        # Generate report
        report_result = btw_aangifte_generator.generate_btw_report(
            cache=cache,
            db=db,
            administration='TestAdmin',
            year=2025,
            quarter=4
        )
        
        # Verify calculations are present in report result
        assert 'calculations' in report_result
        calculations = report_result['calculations']
        
        assert 'total_balance' in calculations
        assert 'received_btw' in calculations
        assert 'prepaid_btw' in calculations
        assert 'payment_instruction' in calculations
        
        # Verify template data has formatted values
        template_data = btw_aangifte_generator.prepare_template_data(report_result)
        assert 'payment_instruction' in template_data
        assert 'received_btw' in template_data
        assert 'prepaid_btw' in template_data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
