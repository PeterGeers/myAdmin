"""
Unit tests for STR Invoice Generator

Tests the str_invoice_generator module functions for generating
STR (Short-Term Rental) invoice HTML content.
"""

import pytest
from datetime import datetime
from report_generators import str_invoice_generator


class TestGenerateTableRows:
    """Test generate_table_rows function"""
    
    def test_generate_table_rows_nl_with_vat_and_tax(self):
        """Test generating table rows in Dutch with VAT and tourist tax"""
        invoice_data = {
            'listing': 'Beach House Amsterdam',
            'net_amount': 500.00,
            'vat_amount': 105.00,
            'tourist_tax': 15.00,
            'amountGross': 620.00
        }
        
        result = str_invoice_generator.generate_table_rows(invoice_data, 'nl')
        
        # Check that all expected rows are present
        assert 'Verblijf Beach House Amsterdam' in result
        assert 'BTW' in result
        assert 'Toeristenbelasting' in result
        assert 'Totaal' in result
        
        # Check amounts are formatted correctly
        assert '€500.00' in result
        assert '€105.00' in result
        assert '€15.00' in result
        assert '€620.00' in result
    
    def test_generate_table_rows_en_with_vat_and_tax(self):
        """Test generating table rows in English with VAT and tourist tax"""
        invoice_data = {
            'listing': 'Beach House Amsterdam',
            'net_amount': 500.00,
            'vat_amount': 105.00,
            'tourist_tax': 15.00,
            'amountGross': 620.00
        }
        
        result = str_invoice_generator.generate_table_rows(invoice_data, 'en')
        
        # Check that all expected rows are present
        assert 'Stay at Beach House Amsterdam' in result
        assert 'VAT' in result
        assert 'Tourist Tax' in result
        assert 'Total' in result
        
        # Check amounts are formatted correctly
        assert '€500.00' in result
        assert '€105.00' in result
        assert '€15.00' in result
        assert '€620.00' in result
    
    def test_generate_table_rows_without_vat(self):
        """Test generating table rows without VAT"""
        invoice_data = {
            'listing': 'Beach House Amsterdam',
            'net_amount': 500.00,
            'vat_amount': 0.00,
            'tourist_tax': 15.00,
            'amountGross': 515.00
        }
        
        result = str_invoice_generator.generate_table_rows(invoice_data, 'nl')
        
        # VAT row should not be present
        assert 'BTW' not in result
        
        # Other rows should be present
        assert 'Verblijf Beach House Amsterdam' in result
        assert 'Toeristenbelasting' in result
        assert 'Totaal' in result
    
    def test_generate_table_rows_without_tourist_tax(self):
        """Test generating table rows without tourist tax"""
        invoice_data = {
            'listing': 'Beach House Amsterdam',
            'net_amount': 500.00,
            'vat_amount': 105.00,
            'tourist_tax': 0.00,
            'amountGross': 605.00
        }
        
        result = str_invoice_generator.generate_table_rows(invoice_data, 'nl')
        
        # Tourist tax row should not be present
        assert 'Toeristenbelasting' not in result
        
        # Other rows should be present
        assert 'Verblijf Beach House Amsterdam' in result
        assert 'BTW' in result
        assert 'Totaal' in result
    
    def test_generate_table_rows_minimal(self):
        """Test generating table rows with minimal data (no VAT, no tax)"""
        invoice_data = {
            'listing': 'Beach House Amsterdam',
            'net_amount': 500.00,
            'vat_amount': 0.00,
            'tourist_tax': 0.00,
            'amountGross': 500.00
        }
        
        result = str_invoice_generator.generate_table_rows(invoice_data, 'nl')
        
        # Only accommodation and total rows should be present
        assert 'Verblijf Beach House Amsterdam' in result
        assert 'Totaal' in result
        assert 'BTW' not in result
        assert 'Toeristenbelasting' not in result
    
    def test_generate_table_rows_decimal_precision(self):
        """Test that amounts are formatted with 2 decimal places"""
        invoice_data = {
            'listing': 'Beach House Amsterdam',
            'net_amount': 500.123,
            'vat_amount': 105.456,
            'tourist_tax': 15.789,
            'amountGross': 621.368
        }
        
        result = str_invoice_generator.generate_table_rows(invoice_data, 'nl')
        
        # Check that amounts are rounded to 2 decimals
        assert '€500.12' in result
        assert '€105.46' in result
        assert '€15.79' in result
        assert '€621.37' in result


class TestPrepareInvoiceData:
    """Test prepare_invoice_data function"""
    
    def test_prepare_invoice_data_basic(self):
        """Test preparing invoice data with basic booking data"""
        booking_data = {
            'reservationCode': 'ABC123',
            'guestName': 'John Doe',
            'channel': 'Airbnb',
            'listing': 'Beach House Amsterdam',
            'checkinDate': '2025-06-15',
            'checkoutDate': '2025-06-20',
            'nights': 5,
            'guests': 2,
            'amountGross': 620.00,
            'amountVat': 105.00,
            'amountTouristTax': 15.00,
            'amountChannelFee': 62.00
        }
        
        result = str_invoice_generator.prepare_invoice_data(booking_data)
        
        # Check booking details
        assert result['reservationCode'] == 'ABC123'
        assert result['guestName'] == 'John Doe'
        assert result['channel'] == 'Airbnb'
        assert result['listing'] == 'Beach House Amsterdam'
        assert result['nights'] == 5
        assert result['guests'] == 2
        
        # Check financial calculations
        assert result['amountGross'] == 620.00
        assert result['amountVat'] == 105.00
        assert result['amountTouristTax'] == 15.00
        assert result['net_amount'] == 500.00  # 620 - 105 - 15
        
        # Check dates are formatted
        assert result['checkinDate'] == '15-06-2025'
        assert result['checkoutDate'] == '20-06-2025'
        assert result['invoice_date'] == '15-06-2025'
        assert result['due_date'] == '15-06-2025'
        
        # Check company info is present
        assert 'company_name' in result
        assert 'company_vat' in result
        assert 'contact_email' in result
    
    def test_prepare_invoice_data_with_custom_billing(self):
        """Test preparing invoice data with custom billing information"""
        booking_data = {
            'reservationCode': 'ABC123',
            'guestName': 'John Doe',
            'channel': 'Airbnb',
            'listing': 'Beach House Amsterdam',
            'checkinDate': '2025-06-15',
            'checkoutDate': '2025-06-20',
            'nights': 5,
            'guests': 2,
            'amountGross': 620.00,
            'amountVat': 105.00,
            'amountTouristTax': 15.00,
            'amountChannelFee': 62.00
        }
        
        custom_billing = {
            'name': 'Custom Company Ltd',
            'address': '123 Custom Street',
            'city': 'Amsterdam'
        }
        
        result = str_invoice_generator.prepare_invoice_data(booking_data, custom_billing)
        
        # Check custom billing is applied
        assert result['billing_name'] == 'Custom Company Ltd'
        assert result['billing_address'] == '123 Custom Street'
        assert result['billing_city'] == 'Amsterdam'
    
    def test_prepare_invoice_data_default_billing(self):
        """Test preparing invoice data with default billing (no custom)"""
        booking_data = {
            'reservationCode': 'ABC123',
            'guestName': 'John Doe',
            'channel': 'Airbnb',
            'listing': 'Beach House Amsterdam',
            'checkinDate': '2025-06-15',
            'checkoutDate': '2025-06-20',
            'nights': 5,
            'guests': 2,
            'amountGross': 620.00,
            'amountVat': 105.00,
            'amountTouristTax': 15.00,
            'amountChannelFee': 62.00
        }
        
        result = str_invoice_generator.prepare_invoice_data(booking_data)
        
        # Check default billing
        assert result['billing_name'] == 'John Doe'
        assert result['billing_address'] == 'Via Airbnb'
        assert result['billing_city'] == 'Reservering: ABC123'
    
    def test_prepare_invoice_data_date_parsing(self):
        """Test that various date formats are handled correctly"""
        booking_data = {
            'reservationCode': 'ABC123',
            'guestName': 'John Doe',
            'channel': 'Airbnb',
            'listing': 'Beach House Amsterdam',
            'checkinDate': datetime(2025, 6, 15),  # datetime object
            'checkoutDate': datetime(2025, 6, 20),  # datetime object
            'nights': 5,
            'guests': 2,
            'amountGross': 620.00,
            'amountVat': 105.00,
            'amountTouristTax': 15.00,
            'amountChannelFee': 62.00
        }
        
        result = str_invoice_generator.prepare_invoice_data(booking_data)
        
        # Check dates are formatted correctly
        assert result['checkinDate'] == '15-06-2025'
        assert result['checkoutDate'] == '20-06-2025'
    
    def test_prepare_invoice_data_zero_amounts(self):
        """Test preparing invoice data with zero VAT and tourist tax"""
        booking_data = {
            'reservationCode': 'ABC123',
            'guestName': 'John Doe',
            'channel': 'Airbnb',
            'listing': 'Beach House Amsterdam',
            'checkinDate': '2025-06-15',
            'checkoutDate': '2025-06-20',
            'nights': 5,
            'guests': 2,
            'amountGross': 500.00,
            'amountVat': 0.00,
            'amountTouristTax': 0.00,
            'amountChannelFee': 50.00
        }
        
        result = str_invoice_generator.prepare_invoice_data(booking_data)
        
        # Check calculations with zero amounts
        assert result['amountGross'] == 500.00
        assert result['amountVat'] == 0.00
        assert result['amountTouristTax'] == 0.00
        assert result['net_amount'] == 500.00  # 500 - 0 - 0
    
    def test_prepare_invoice_data_missing_optional_fields(self):
        """Test preparing invoice data with missing optional fields"""
        booking_data = {
            'reservationCode': 'ABC123',
            'guestName': 'John Doe',
            'checkinDate': '2025-06-15',
            'amountGross': 500.00
            # Missing: channel, listing, checkoutDate, nights, guests, etc.
        }
        
        result = str_invoice_generator.prepare_invoice_data(booking_data)
        
        # Check defaults are applied
        assert result['reservationCode'] == 'ABC123'
        assert result['guestName'] == 'John Doe'
        assert result['channel'] == ''
        assert result['listing'] == ''
        assert result['nights'] == 1
        assert result['guests'] == 1
        assert result['amountGross'] == 500.00


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
