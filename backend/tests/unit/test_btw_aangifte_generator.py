"""
Unit tests for BTW Aangifte Generator

Tests the BTW Aangifte report generator functions including:
- Quarter end date calculation
- Balance data formatting
- Quarter data formatting
- BTW amount calculations
- Template data preparation
"""

import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd
from datetime import datetime

# Import the generator module
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from report_generators import btw_aangifte_generator


class TestQuarterEndDateCalculation:
    """Test quarter end date calculation"""
    
    def test_quarter_1_end_date(self):
        """Test Q1 end date (March 31)"""
        result = btw_aangifte_generator._calculate_quarter_end_date(2025, 1)
        assert result == '2025-03-31'
    
    def test_quarter_2_end_date(self):
        """Test Q2 end date (June 30)"""
        result = btw_aangifte_generator._calculate_quarter_end_date(2025, 2)
        assert result == '2025-06-30'
    
    def test_quarter_3_end_date(self):
        """Test Q3 end date (September 30)"""
        result = btw_aangifte_generator._calculate_quarter_end_date(2025, 3)
        assert result == '2025-09-30'
    
    def test_quarter_4_end_date(self):
        """Test Q4 end date (December 31)"""
        result = btw_aangifte_generator._calculate_quarter_end_date(2025, 4)
        assert result == '2025-12-31'
    
    def test_invalid_quarter(self):
        """Test invalid quarter raises error"""
        with pytest.raises(ValueError):
            btw_aangifte_generator._calculate_quarter_end_date(2025, 5)


class TestBTWCalculations:
    """Test BTW amount calculations"""
    
    def test_calculate_btw_amounts_positive_balance(self):
        """Test calculations with positive balance (te ontvangen)"""
        balance_data = [
            {'Reknum': '2010', 'AccountName': 'BTW te betalen', 'amount': 1000.0},
            {'Reknum': '2020', 'AccountName': 'BTW ontvangen', 'amount': 500.0}
        ]
        quarter_data = [
            {'Reknum': '2020', 'AccountName': 'BTW ontvangen', 'amount': 800.0},
            {'Reknum': '2021', 'AccountName': 'BTW vooruitbetaald', 'amount': 200.0}
        ]
        
        result = btw_aangifte_generator._calculate_btw_amounts(balance_data, quarter_data)
        
        assert result['total_balance'] == 1500.0
        assert result['received_btw'] == 1000.0
        assert result['prepaid_btw'] == -500.0
        assert result['payment_instruction'] == '€1500 te ontvangen'
    
    def test_calculate_btw_amounts_negative_balance(self):
        """Test calculations with negative balance (te betalen)"""
        balance_data = [
            {'Reknum': '2010', 'AccountName': 'BTW te betalen', 'amount': -1000.0}
        ]
        quarter_data = [
            {'Reknum': '2020', 'AccountName': 'BTW ontvangen', 'amount': 500.0}
        ]
        
        result = btw_aangifte_generator._calculate_btw_amounts(balance_data, quarter_data)
        
        assert result['total_balance'] == -1000.0
        assert result['received_btw'] == 500.0
        assert result['prepaid_btw'] == 1500.0
        assert result['payment_instruction'] == '€1000 te betalen'
    
    def test_calculate_btw_amounts_zero_balance(self):
        """Test calculations with zero balance"""
        balance_data = []
        quarter_data = []
        
        result = btw_aangifte_generator._calculate_btw_amounts(balance_data, quarter_data)
        
        assert result['total_balance'] == 0
        assert result['received_btw'] == 0
        assert result['prepaid_btw'] == 0
        assert result['payment_instruction'] == '€0 te ontvangen'
    
    def test_calculate_btw_amounts_only_received_btw(self):
        """Test calculations with only received BTW accounts"""
        balance_data = [
            {'Reknum': '2010', 'AccountName': 'BTW te betalen', 'amount': 100.0}
        ]
        quarter_data = [
            {'Reknum': '2020', 'AccountName': 'BTW ontvangen', 'amount': 300.0},
            {'Reknum': '2021', 'AccountName': 'BTW vooruitbetaald', 'amount': 200.0},
            {'Reknum': '8001', 'AccountName': 'Revenue', 'amount': 5000.0}  # Should be ignored
        ]
        
        result = btw_aangifte_generator._calculate_btw_amounts(balance_data, quarter_data)
        
        assert result['received_btw'] == 500.0  # Only 2020 + 2021
        assert result['total_balance'] == 100.0
        assert result['prepaid_btw'] == 400.0


class TestTableRowFormatting:
    """Test table row formatting"""
    
    def test_format_table_rows_with_data(self):
        """Test formatting table rows with valid data"""
        data = [
            {'Reknum': '2010', 'AccountName': 'BTW te betalen', 'amount': 1234.56},
            {'Reknum': '2020', 'AccountName': 'BTW ontvangen', 'amount': -567.89}
        ]
        
        result = btw_aangifte_generator._format_table_rows(data)
        
        assert '<tr>' in result
        assert '<td>2010</td>' in result
        assert '<td>BTW te betalen</td>' in result
        assert '€ 1.234,56' in result
        assert '<td>2020</td>' in result
        assert '<td>BTW ontvangen</td>' in result
        assert '€ -567,89' in result
    
    def test_format_table_rows_empty_data(self):
        """Test formatting with empty data"""
        result = btw_aangifte_generator._format_table_rows([])
        
        assert 'Geen gegevens beschikbaar' in result
        assert '<tr>' in result
    
    def test_format_table_rows_html_escaping(self):
        """Test HTML special characters are escaped"""
        data = [
            {'Reknum': '2010', 'AccountName': '<script>alert("XSS")</script>', 'amount': 100.0}
        ]
        
        result = btw_aangifte_generator._format_table_rows(data)
        
        assert '<script>' not in result
        assert '&lt;script&gt;' in result


class TestTemplateDataPreparation:
    """Test template data preparation"""
    
    def test_prepare_template_data_complete(self):
        """Test preparing complete template data"""
        report_data = {
            'balance_rows': '<tr><td>2010</td><td>BTW</td><td>€ 1.000,00</td></tr>',
            'quarter_rows': '<tr><td>2020</td><td>BTW</td><td>€ 500,00</td></tr>',
            'calculations': {
                'total_balance': 1500.0,
                'received_btw': 1000.0,
                'prepaid_btw': -500.0,
                'payment_instruction': '€1500 te ontvangen'
            },
            'metadata': {
                'administration': 'GoodwinSolutions',
                'year': 2025,
                'quarter': 1,
                'end_date': '2025-03-31',
                'generated_date': '2025-01-31 14:30:00'
            }
        }
        
        result = btw_aangifte_generator.prepare_template_data(report_data)
        
        assert result['administration'] == 'GoodwinSolutions'
        assert result['year'] == '2025'
        assert result['quarter'] == '1'
        assert result['end_date'] == '2025-03-31'
        assert result['generated_date'] == '2025-01-31 14:30:00'
        assert result['payment_instruction'] == '€1500 te ontvangen'
        assert '€ 1.000,00' in result['received_btw']
        assert '€ -500,00' in result['prepaid_btw']
    
    def test_prepare_template_data_missing_fields(self):
        """Test preparing template data with missing fields"""
        report_data = {
            'calculations': {},
            'metadata': {}
        }
        
        result = btw_aangifte_generator.prepare_template_data(report_data)
        
        assert result['administration'] == ''
        assert result['year'] == ''
        assert result['payment_instruction'] == '€0 te betalen'
        assert result['balance_rows'] == ''


class TestGetBalanceData:
    """Test balance data retrieval"""
    
    def test_get_balance_data_filters_correctly(self):
        """Test balance data filtering by date, administration, and accounts"""
        # Create mock cache and db
        mock_cache = Mock()
        mock_db = Mock()
        
        # Create sample dataframe
        df = pd.DataFrame({
            'TransactionDate': ['2025-01-15', '2025-02-20', '2025-04-10'],
            'administration': ['GoodwinSolutions', 'GoodwinSolutions', 'GoodwinSolutions'],
            'Reknum': ['2010', '2020', '2010'],
            'AccountName': ['BTW te betalen', 'BTW ontvangen', 'BTW te betalen'],
            'Amount': [1000.0, 500.0, 200.0]
        })
        
        mock_cache.get_data.return_value = df
        
        result = btw_aangifte_generator._get_balance_data(
            mock_cache, 
            mock_db, 
            'GoodwinSolutions', 
            '2025-03-31'
        )
        
        # Should only include first two records (before end date)
        assert len(result) == 2
        assert all(r['Reknum'] in ['2010', '2020'] for r in result)
    
    def test_get_balance_data_empty_result(self):
        """Test balance data with no matching records"""
        mock_cache = Mock()
        mock_db = Mock()
        
        df = pd.DataFrame({
            'TransactionDate': [],
            'administration': [],
            'Reknum': [],
            'AccountName': [],
            'Amount': []
        })
        
        mock_cache.get_data.return_value = df
        
        result = btw_aangifte_generator._get_balance_data(
            mock_cache, 
            mock_db, 
            'GoodwinSolutions', 
            '2025-03-31'
        )
        
        assert result == []


class TestGetQuarterData:
    """Test quarter data retrieval"""
    
    def test_get_quarter_data_filters_correctly(self):
        """Test quarter data filtering by year, quarter, administration, and accounts"""
        mock_cache = Mock()
        mock_db = Mock()
        
        df = pd.DataFrame({
            'jaar': [2025, 2025, 2025, 2024],
            'kwartaal': [1, 1, 2, 1],
            'administration': ['GoodwinSolutions', 'GoodwinSolutions', 'GoodwinSolutions', 'GoodwinSolutions'],
            'Reknum': ['2010', '2020', '2010', '2010'],
            'AccountName': ['BTW te betalen', 'BTW ontvangen', 'BTW te betalen', 'BTW te betalen'],
            'Amount': [1000.0, 500.0, 200.0, 300.0]
        })
        
        mock_cache.get_data.return_value = df
        
        result = btw_aangifte_generator._get_quarter_data(
            mock_cache, 
            mock_db, 
            'GoodwinSolutions', 
            2025, 
            1
        )
        
        # Should only include first two records (year 2025, quarter 1)
        assert len(result) == 2
        assert all(r['Reknum'] in ['2010', '2020'] for r in result)


class TestGenerateBTWReport:
    """Test main report generation function"""
    
    def test_generate_btw_report_success(self):
        """Test successful BTW report generation"""
        mock_cache = Mock()
        mock_db = Mock()
        
        # Create sample dataframe
        df = pd.DataFrame({
            'TransactionDate': ['2025-01-15', '2025-02-20'],
            'jaar': [2025, 2025],
            'kwartaal': [1, 1],
            'administration': ['GoodwinSolutions', 'GoodwinSolutions'],
            'Reknum': ['2010', '2020'],
            'AccountName': ['BTW te betalen', 'BTW ontvangen'],
            'Amount': [1000.0, 500.0]
        })
        
        mock_cache.get_data.return_value = df
        
        result = btw_aangifte_generator.generate_btw_report(
            cache=mock_cache,
            db=mock_db,
            administration='GoodwinSolutions',
            year=2025,
            quarter=1
        )
        
        assert result['success'] == True
        assert 'balance_rows' in result
        assert 'quarter_rows' in result
        assert 'calculations' in result
        assert 'metadata' in result
        assert result['metadata']['year'] == 2025
        assert result['metadata']['quarter'] == 1
        assert result['metadata']['end_date'] == '2025-03-31'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
