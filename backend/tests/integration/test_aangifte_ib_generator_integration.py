"""
Integration tests for Aangifte IB Generator

Tests the generator with realistic data structures similar to production.
"""

import pytest
from unittest.mock import Mock
from report_generators.aangifte_ib_generator import generate_table_rows


class TestAangifteIBGeneratorIntegration:
    """Integration tests with realistic data"""
    
    def test_generates_report_with_realistic_data(self):
        """Test generator with realistic financial data structure"""
        # Realistic report data similar to production
        report_data = [
            {'Parent': '1000', 'Aangifte': 'Liquide middelen', 'Amount': 88262.80},
            {'Parent': '1000', 'Aangifte': 'kortlopende schulden', 'Amount': -132.73},
            {'Parent': '2000', 'Aangifte': 'BTW', 'Amount': -1430.31},
            {'Parent': '3000', 'Aangifte': 'Financiële vaste activa', 'Amount': 79153.43},
            {'Parent': '3000', 'Aangifte': 'Materiële vaste activa', 'Amount': 33884.56},
            {'Parent': '3000', 'Aangifte': 'Ondernemingsvermogen', 'Amount': -228591.51},
            {'Parent': '4000', 'Aangifte': 'Andere kosten', 'Amount': 34958.68},
            {'Parent': '4000', 'Aangifte': 'Auto- en transportkosten', 'Amount': 1923.79},
            {'Parent': '4000', 'Aangifte': 'Huisvestingskosten', 'Amount': 70000.00},
            {'Parent': '4000', 'Aangifte': 'Verkoopkosten', 'Amount': 12106.75},
            {'Parent': '8000', 'Aangifte': 'Bijzondere baten en lasten', 'Amount': -1862.91},
            {'Parent': '8000', 'Aangifte': 'opbrengsten', 'Amount': -88272.55}
        ]
        
        # Mock cache with realistic account details
        mock_cache = Mock()
        
        def mock_query_details(year, administration, parent, aangifte, user_tenants):
            """Return realistic account details based on parent and aangifte"""
            details_map = {
                ('1000', 'Liquide middelen'): [
                    {'Reknum': '1002', 'AccountName': 'NL80RABO0107936917 RCRT', 'Amount': 6972.69},
                    {'Reknum': '1011', 'AccountName': 'NL89RABO1342368843 sparen', 'Amount': 24971.44},
                    {'Reknum': '1012', 'AccountName': 'NL67RABO1342368851 sparen', 'Amount': 56318.67}
                ],
                ('1000', 'kortlopende schulden'): [
                    {'Reknum': '1300', 'AccountName': 'Debiteuren', 'Amount': -132.73}
                ],
                ('2000', 'BTW'): [
                    {'Reknum': '2010', 'AccountName': 'Betaalde BTW', 'Amount': 164091.95},
                    {'Reknum': '2020', 'AccountName': 'Ontvangen BTW Hoog', 'Amount': -115195.00},
                    {'Reknum': '2021', 'AccountName': 'Ontvangen BTW Laag', 'Amount': -50327.26}
                ],
                ('4000', 'Andere kosten'): [
                    {'Reknum': '4001', 'AccountName': 'Onkosten', 'Amount': 26349.54},
                    {'Reknum': '4010', 'AccountName': 'Toeristenbelasting', 'Amount': 6118.34},
                    {'Reknum': '4011', 'AccountName': 'Heffingen gemeente etc.', 'Amount': 326.82}
                ]
            }
            return details_map.get((parent, aangifte), [])
        
        mock_cache.query_aangifte_ib_details = mock_query_details
        
        # Generate rows
        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=['GoodwinSolutions']
        )
        
        # Verify structure
        assert len(rows) > 0
        
        # Check we have expected row types (resultaat may be filtered if close to zero)
        row_types = {row['row_type'] for row in rows}
        assert 'parent' in row_types
        assert 'aangifte' in row_types
        assert 'account' in row_types
        assert 'grand_total' in row_types
        # resultaat may not be present if the sum is close to zero
        
        # Verify parent rows
        parent_rows = [row for row in rows if row['row_type'] == 'parent']
        parent_codes = {row['parent'] for row in parent_rows}
        assert '1000' in parent_codes
        assert '2000' in parent_codes
        assert '3000' in parent_codes
        assert '4000' in parent_codes
        assert '8000' in parent_codes
        
        # Verify aangifte rows
        aangifte_rows = [row for row in rows if row['row_type'] == 'aangifte']
        assert len(aangifte_rows) == len(report_data)
        
        # Verify account rows exist
        account_rows = [row for row in rows if row['row_type'] == 'account']
        assert len(account_rows) > 0
        
        # Verify specific account details
        account_1002 = next((row for row in account_rows if row['aangifte'] == '1002'), None)
        assert account_1002 is not None
        assert account_1002['description'] == 'NL80RABO0107936917 RCRT'
        # Dutch locale format: 6.972,69 (period for thousands, comma for decimal)
        assert account_1002['amount'] == '6.972,69'
        
        # Verify resultaat calculation (may not be present if close to zero)
        expected_resultaat = sum(item['Amount'] for item in report_data)
        resultaat_row = next((row for row in rows if row['row_type'] == 'resultaat'), None)
        
        # Resultaat row only appears if amount is >= 0.01
        if abs(expected_resultaat) >= 0.01:
            assert resultaat_row is not None
            assert abs(resultaat_row['amount_raw'] - expected_resultaat) < 0.01
        else:
            # If resultaat is close to zero, it may be filtered out
            pass
        
        # Verify grand total
        grand_total_row = next((row for row in rows if row['row_type'] == 'grand_total'), None)
        assert grand_total_row is not None
        assert grand_total_row['parent'] == 'GRAND TOTAL'
    
    def test_handles_mixed_positive_negative_amounts(self):
        """Test that positive and negative amounts are handled correctly"""
        report_data = [
            {'Parent': '1000', 'Aangifte': 'Assets', 'Amount': 50000.00},
            {'Parent': '2000', 'Aangifte': 'Liabilities', 'Amount': -30000.00},
            {'Parent': '3000', 'Aangifte': 'Income', 'Amount': -20000.00},
            {'Parent': '4000', 'Aangifte': 'Expenses', 'Amount': 15000.00}
        ]
        
        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []
        
        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='TestAdmin',
            user_tenants=['TestAdmin']
        )
        
        # Find parent rows and verify amounts
        parent_rows = [row for row in rows if row['row_type'] == 'parent']
        
        parent_1000 = next(row for row in parent_rows if row['parent'] == '1000')
        assert parent_1000['amount_raw'] == 50000.00
        
        parent_2000 = next(row for row in parent_rows if row['parent'] == '2000')
        assert parent_2000['amount_raw'] == -30000.00
        
        # Verify resultaat
        resultaat_row = next(row for row in rows if row['row_type'] == 'resultaat')
        assert resultaat_row['amount_raw'] == 15000.00  # 50000 - 30000 - 20000 + 15000
    
    def test_security_user_tenants_filtering(self):
        """Test that user_tenants parameter is properly passed for security"""
        report_data = [
            {'Parent': '1000', 'Aangifte': 'Test', 'Amount': 100.0}
        ]
        
        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []
        
        user_tenants = ['GoodwinSolutions', 'PeterPrive']
        
        generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=user_tenants
        )
        
        # Verify cache was called with user_tenants
        assert mock_cache.query_aangifte_ib_details.called
        call_kwargs = mock_cache.query_aangifte_ib_details.call_args.kwargs
        assert 'user_tenants' in call_kwargs
        assert call_kwargs['user_tenants'] == user_tenants
    
    def test_formatting_consistency(self):
        """Test that all amounts are consistently formatted"""
        report_data = [
            {'Parent': '1000', 'Aangifte': 'Test1', 'Amount': 1234.56},
            {'Parent': '2000', 'Aangifte': 'Test2', 'Amount': -9876.54}
        ]
        
        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = [
            {'Reknum': '1001', 'AccountName': 'Account 1', 'Amount': 123.45}
        ]
        
        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='TestAdmin',
            user_tenants=['TestAdmin']
        )
        
        # Check all amounts are formatted with commas and 2 decimals
        for row in rows:
            amount = row['amount']
            # Dutch locale format: 1.234,56 (period for thousands, comma for decimal)
            # Should have format like "1.234,56" or "-1.234,56"
            if row['amount_raw'] >= 1000 or row['amount_raw'] <= -1000:
                assert '.' in amount, f"Amount {amount} should have thousand separator (period)"
            assert ',' in amount, f"Amount {amount} should have decimal separator (comma)"
            # Check decimal places (after comma)
            decimal_part = amount.split(',')[-1]
            assert len(decimal_part) == 2, f"Amount {amount} should have 2 decimal places"
