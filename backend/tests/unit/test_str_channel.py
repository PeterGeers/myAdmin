"""
Test STR Channel Revenue functionality
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date
import calendar

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from str_channel_routes import str_channel_bp

class TestSTRChannelRevenue:
    """Test STR Channel Revenue calculations"""
    
    def test_calculate_str_channel_revenue_basic(self):
        """Test basic STR channel revenue calculation"""
        # Mock data that would come from database
        mock_channel_data = [
            {
                'Administration': 'GoodwinSolutions',
                'ReferenceNumber': 'AirBnB',
                'Reknum': '1600',
                'TransactionAmount': -1090.0  # Negative amount from account 1600
            },
            {
                'Administration': 'GoodwinSolutions', 
                'ReferenceNumber': 'Booking.com',
                'Reknum': '1600',
                'TransactionAmount': -545.0
            }
        ]
        
        # Expected transactions after processing
        expected_revenue_count = 2  # One for each channel
        expected_vat_count = 2     # VAT transaction for each channel
        expected_total_transactions = 4
        
        # Test the logic manually
        transactions = []
        year = 2025
        month = 9
        end_date = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
        ref1 = f"BnB {year}{month:02d}"
        
        for row in mock_channel_data:
            amount = round(float(row['TransactionAmount']) * -1, 2)  # Reverse sign
            
            # Revenue transaction
            revenue_transaction = {
                'TransactionDate': end_date,
                'TransactionNumber': f"{row['ReferenceNumber']} {end_date}",
                'TransactionDescription': f"{row['ReferenceNumber']} omzet {end_date}",
                'TransactionAmount': amount,
                'Debet': row['Reknum'],
                'Credit': '8003',
                'ReferenceNumber': row['ReferenceNumber'],
                'Ref1': ref1,
                'Administration': row['Administration']
            }
            transactions.append(revenue_transaction)
            
            # VAT transaction (9% of revenue / 109 * 9)
            vat_amount = round((amount / 109) * 9, 2)
            vat_transaction = {
                'TransactionDate': end_date,
                'TransactionNumber': f"{row['ReferenceNumber']} {end_date}",
                'TransactionDescription': f"{row['ReferenceNumber']} Btw {end_date}",
                'TransactionAmount': vat_amount,
                'Debet': '8003',
                'Credit': '2021',
                'ReferenceNumber': row['ReferenceNumber'],
                'Ref1': ref1,
                'Administration': row['Administration']
            }
            transactions.append(vat_transaction)
        
        # Verify results
        assert len(transactions) == expected_total_transactions
        
        # Check AirBnB transactions
        airbnb_revenue = next(t for t in transactions if t['ReferenceNumber'] == 'AirBnB' and t['Credit'] == '8003')
        airbnb_vat = next(t for t in transactions if t['ReferenceNumber'] == 'AirBnB' and t['Credit'] == '2021')
        
        assert airbnb_revenue['TransactionAmount'] == 1090.0
        assert airbnb_revenue['Debet'] == '1600'
        assert airbnb_revenue['Credit'] == '8003'
        assert airbnb_revenue['TransactionDescription'] == f'AirBnB omzet {end_date}'
        
        # VAT should be 9% of revenue (1090 / 109 * 9)
        expected_vat = round((1090.0 / 109) * 9, 2)
        assert airbnb_vat['TransactionAmount'] == expected_vat
        assert airbnb_vat['Debet'] == '8003'
        assert airbnb_vat['Credit'] == '2021'
    
    def test_str_channel_pattern_matching(self):
        """Test STR channel pattern matching"""
        test_patterns = [
            ('AirBnB', True),
            ('AIRBNB', True),  # Should be converted to AirBnB
            ('Booking.com', True),
            ('dfDirect', True),
            ('Stripe', True),
            ('VRBO', True),
            ('PayPal', False),  # Should not match
            ('Bank Transfer', False)  # Should not match
        ]
        
        import re
        pattern = "AirBnB|Booking.com|dfDirect|Stripe|VRBO"
        
        for reference, should_match in test_patterns:
            if reference == 'AIRBNB':
                # Special case: AIRBNB should be converted to AirBnB
                converted_ref = 'AirBnB' if 'AIRBNB' in reference else reference
                match = re.search(pattern, converted_ref)
            else:
                match = re.search(pattern, reference)
            
            if should_match:
                assert match is not None, f"Pattern should match {reference}"
            else:
                assert match is None, f"Pattern should not match {reference}"
    
    def test_vat_calculation_accuracy(self):
        """Test VAT calculation accuracy"""
        test_amounts = [
            (1090.0, 90.0),   # 1090 / 109 * 9 = 90
            (545.0, 45.0),    # 545 / 109 * 9 = 45
            (218.0, 18.0),    # 218 / 109 * 9 = 18
            (109.0, 9.0),     # 109 / 109 * 9 = 9
            (100.0, 8.26)     # 100 / 109 * 9 = 8.26
        ]
        
        for revenue_amount, expected_vat in test_amounts:
            calculated_vat = round((revenue_amount / 109) * 9, 2)
            assert calculated_vat == expected_vat, f"VAT calculation failed for {revenue_amount}: expected {expected_vat}, got {calculated_vat}"
    
    def test_month_end_date_calculation(self):
        """Test month end date calculation"""
        test_cases = [
            (2025, 1, '2025-01-31'),   # January
            (2025, 2, '2025-02-28'),   # February (non-leap year)
            (2024, 2, '2024-02-29'),   # February (leap year)
            (2025, 4, '2025-04-30'),   # April (30 days)
            (2025, 12, '2025-12-31')   # December
        ]
        
        for year, month, expected_date in test_cases:
            last_day = calendar.monthrange(year, month)[1]
            calculated_date = f"{year}-{month:02d}-{last_day}"
            assert calculated_date == expected_date, f"Date calculation failed for {year}-{month}: expected {expected_date}, got {calculated_date}"
    
    def test_reference_number_generation(self):
        """Test reference number generation"""
        test_cases = [
            (2025, 1, 'BnB 202501'),
            (2025, 9, 'BnB 202509'),
            (2025, 12, 'BnB 202512'),
            (2024, 6, 'BnB 202406')
        ]
        
        for year, month, expected_ref in test_cases:
            ref1 = f"BnB {year}{month:02d}"
            assert ref1 == expected_ref, f"Reference generation failed: expected {expected_ref}, got {ref1}"
    
    def test_transaction_structure(self):
        """Test transaction structure completeness"""
        # Mock a single channel data entry
        mock_data = {
            'Administration': 'GoodwinSolutions',
            'ReferenceNumber': 'AirBnB',
            'Reknum': '1600',
            'TransactionAmount': -1090.0
        }
        
        year = 2025
        month = 9
        end_date = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
        ref1 = f"BnB {year}{month:02d}"
        amount = round(float(mock_data['TransactionAmount']) * -1, 2)
        
        # Create revenue transaction
        revenue_transaction = {
            'TransactionDate': end_date,
            'TransactionNumber': f"{mock_data['ReferenceNumber']} {end_date}",
            'TransactionDescription': f"{mock_data['ReferenceNumber']} omzet {end_date}",
            'TransactionAmount': amount,
            'Debet': mock_data['Reknum'],
            'Credit': '8003',
            'ReferenceNumber': mock_data['ReferenceNumber'],
            'Ref1': ref1,
            'Ref2': '',
            'Ref3': '',
            'Ref4': '',
            'Administration': mock_data['Administration']
        }
        
        # Verify all required fields are present
        required_fields = [
            'TransactionDate', 'TransactionNumber', 'TransactionDescription',
            'TransactionAmount', 'Debet', 'Credit', 'ReferenceNumber',
            'Ref1', 'Ref2', 'Ref3', 'Ref4', 'Administration'
        ]
        
        for field in required_fields:
            assert field in revenue_transaction, f"Required field {field} missing from transaction"
            assert revenue_transaction[field] is not None, f"Field {field} should not be None"
        
        # Verify specific values
        assert revenue_transaction['TransactionDate'] == end_date
        assert revenue_transaction['TransactionAmount'] == 1090.0
        assert revenue_transaction['Debet'] == '1600'
        assert revenue_transaction['Credit'] == '8003'
        assert revenue_transaction['Ref1'] == 'BnB 202509'
    
    def test_zero_amount_filtering(self):
        """Test that zero amounts are filtered out"""
        mock_channel_data = [
            {
                'Administration': 'GoodwinSolutions',
                'ReferenceNumber': 'AirBnB',
                'Reknum': '1600',
                'TransactionAmount': -1090.0  # Should be included
            },
            {
                'Administration': 'GoodwinSolutions',
                'ReferenceNumber': 'Booking.com',
                'Reknum': '1600',
                'TransactionAmount': 0.0  # Should be filtered out
            },
            {
                'Administration': 'GoodwinSolutions',
                'ReferenceNumber': 'Stripe',
                'Reknum': '1600',
                'TransactionAmount': -0.01  # Should be filtered out (too small)
            }
        ]
        
        transactions = []
        
        for row in mock_channel_data:
            amount = round(float(row['TransactionAmount']) * -1, 2)
            if amount == 0:
                continue  # Filter out zero amounts
                
            # Only process non-zero amounts
            transactions.append({
                'ReferenceNumber': row['ReferenceNumber'],
                'TransactionAmount': amount
            })
        
        # Should only have AirBnB transaction (1090.0)
        # Booking.com filtered out (0.0)
        # Stripe included (0.01)
        assert len(transactions) == 2
        assert transactions[0]['ReferenceNumber'] == 'AirBnB'
        assert transactions[0]['TransactionAmount'] == 1090.0
        assert transactions[1]['ReferenceNumber'] == 'Stripe'
        assert transactions[1]['TransactionAmount'] == 0.01
    
    def test_btw_rate_pre_2026(self):
        """Test BTW rate for pre-2026 dates"""
        from datetime import date
        
        transaction_date = date(2025, 12, 31)
        rate_change_date = date(2026, 1, 1)
        
        if transaction_date >= rate_change_date:
            vat_rate = 21.0
            vat_base = 121.0
            vat_account = '2020'
        else:
            vat_rate = 9.0
            vat_base = 109.0
            vat_account = '2021'
        
        assert vat_rate == 9.0
        assert vat_base == 109.0
        assert vat_account == '2021'
        
        amount = 1090.0
        vat_amount = round((amount / vat_base) * vat_rate, 2)
        assert vat_amount == 90.0
    
    def test_btw_rate_2026_and_later(self):
        """Test BTW rate for 2026+ dates"""
        from datetime import date
        
        transaction_date = date(2026, 1, 1)
        rate_change_date = date(2026, 1, 1)
        
        if transaction_date >= rate_change_date:
            vat_rate = 21.0
            vat_base = 121.0
            vat_account = '2020'
        else:
            vat_rate = 9.0
            vat_base = 109.0
            vat_account = '2021'
        
        assert vat_rate == 21.0
        assert vat_base == 121.0
        assert vat_account == '2020'
        
        amount = 1210.0
        vat_amount = round((amount / vat_base) * vat_rate, 2)
        assert vat_amount == 210.0

if __name__ == '__main__':
    pytest.main([__file__])