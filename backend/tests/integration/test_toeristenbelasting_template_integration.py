"""
Integration tests for Toeristenbelasting Report Template

Tests the complete flow from data generation to HTML output using the
template and generator.
"""

import pytest
from unittest.mock import Mock
import pandas as pd
from report_generators import toeristenbelasting_generator
import os


def _render_template(template_content: str, data: dict) -> str:
    """Simple template rendering using placeholder replacement"""
    result = template_content
    for key, value in data.items():
        placeholder = '{{ ' + key + ' }}'
        result = result.replace(placeholder, str(value))
    return result


@pytest.mark.integration
class TestToeristenbelastingTemplateIntegration:
    """Integration tests for toeristenbelasting template rendering"""
    
    def test_template_rendering_with_real_data(self):
        """Test template rendering with realistic data"""
        # Mock cache
        cache = Mock()
        db = Mock()
        
        # Create realistic financial data
        df = pd.DataFrame({
            'jaar': [2025, 2025, 2025, 2025],
            'Reknum': ['8003', '8003', '4007', '4007'],
            'Amount': [-10620.0, -5310.0, -100.0, -50.0]
        })
        cache.get_data.return_value = df
        
        # Mock BNB cache with realistic booking data
        bnb_cache = Mock()
        bnb_cache.query_by_year.return_value = [
            {'nights': 5, 'amountGross': 520.0, 'amountVat': 88.0},
            {'nights': 3, 'amountGross': 300.0, 'amountVat': 50.0},
            {'nights': 7, 'amountGross': 700.0, 'amountVat': 120.0}
        ]
        bnb_cache.query_cancelled_by_year.return_value = [
            {'nights': 2, 'amountGross': 200.0, 'amountVat': 35.0}
        ]
        bnb_cache.query_realised_by_year.return_value = [
            {'nights': 5, 'amountGross': 520.0, 'amountVat': 88.0},
            {'nights': 3, 'amountGross': 300.0, 'amountVat': 50.0},
            {'nights': 7, 'amountGross': 700.0, 'amountVat': 120.0}
        ]
        
        # Generate report data
        report_result = toeristenbelasting_generator.generate_toeristenbelasting_report(
            cache=cache,
            bnb_cache=bnb_cache,
            db=db,
            year=2025
        )
        
        assert report_result['success'] is True
        
        # Get template data
        template_data = report_result['template_data']
        
        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'templates',
            'html',
            'toeristenbelasting_template.html'
        )
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Render template
        html_output = _render_template(template_content, template_data)
        
        # Verify HTML output contains expected content
        assert 'Aangifte Toeristenbelasting 2025' in html_output
        assert 'DGA' in html_output
        assert 'peter@pgeers.nl' in html_output
        assert '06921893861' in html_output
        
        # Verify rental statistics
        assert '15' in html_output  # Total nights (5+3+7)
        assert '2' in html_output   # Cancelled nights
        
        # Verify financial data is present
        assert '€' in html_output  # Currency symbol
        
        # Verify structure sections are present
        assert 'Contactgegevens' in html_output
        assert 'Periode en Accommodatie' in html_output
        assert 'Verhuurgegevens' in html_output
        assert 'Financiële Gegevens' in html_output
        assert 'Berekening Belastbare Omzet' in html_output
        assert 'Ondertekening' in html_output
        
        # Verify table structure
        assert '<table>' in html_output
        assert '<th>Omschrijving</th>' in html_output
        assert '<th class="number">Bedrag (€)</th>' in html_output
        
        # Verify calculation rows
        assert '[1] Ontvangsten excl. BTW en excl. Toeristenbelasting' in html_output
        assert '[2] Ontvangsten logies inwoners excl. BTW' in html_output
        assert '[3] Kortingen / provisie / commissie' in html_output
        assert '[4] No-show omzet' in html_output
        assert '[5] Totaal 2 + 3 + 4' in html_output
        assert '[6] Belastbare omzet logies' in html_output
        assert 'Verwachte belastbare omzet 2026' in html_output
    
    def test_template_all_placeholders_replaced(self):
        """Test that all template placeholders are replaced"""
        # Mock cache
        cache = Mock()
        db = Mock()
        
        df = pd.DataFrame({
            'jaar': [2025],
            'Reknum': ['8003'],
            'Amount': [-10620.0]
        })
        cache.get_data.return_value = df
        
        # Mock BNB cache
        bnb_cache = Mock()
        bnb_cache.query_by_year.return_value = [
            {'nights': 5, 'amountGross': 520.0, 'amountVat': 88.0}
        ]
        bnb_cache.query_cancelled_by_year.return_value = []
        bnb_cache.query_realised_by_year.return_value = [
            {'nights': 5, 'amountGross': 520.0, 'amountVat': 88.0}
        ]
        
        # Generate report
        report_result = toeristenbelasting_generator.generate_toeristenbelasting_report(
            cache=cache,
            bnb_cache=bnb_cache,
            db=db,
            year=2025
        )
        
        template_data = report_result['template_data']
        
        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'templates',
            'html',
            'toeristenbelasting_template.html'
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
        
        df = pd.DataFrame({
            'jaar': [2025],
            'Reknum': ['8003'],
            'Amount': [-10620.0]
        })
        cache.get_data.return_value = df
        
        # Mock BNB cache
        bnb_cache = Mock()
        bnb_cache.query_by_year.return_value = [
            {'nights': 5, 'amountGross': 520.0, 'amountVat': 88.0}
        ]
        bnb_cache.query_cancelled_by_year.return_value = []
        bnb_cache.query_realised_by_year.return_value = [
            {'nights': 5, 'amountGross': 520.0, 'amountVat': 88.0}
        ]
        
        # Generate report
        report_result = toeristenbelasting_generator.generate_toeristenbelasting_report(
            cache=cache,
            bnb_cache=bnb_cache,
            db=db,
            year=2025
        )
        
        template_data = report_result['template_data']
        
        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'templates',
            'html',
            'toeristenbelasting_template.html'
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
