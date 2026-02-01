"""
Integration test for STR Invoice generation using TemplateService

Tests that STR invoice generation properly uses TemplateService with field mappings.
"""

import pytest
import os
from database import DatabaseManager
from services.template_service import TemplateService
from report_generators import str_invoice_generator


class TestSTRInvoiceTemplateService:
    """Integration tests for STR invoice with TemplateService"""
    
    def test_str_invoice_with_template_service_and_field_mappings(self):
        """Test STR invoice generation using TemplateService with field mappings"""
        # Sample booking data
        booking_data = {
            'reservationCode': 'TEST-TS-001',
            'guestName': 'Test Guest',
            'channel': 'Airbnb',
            'listing': 'Test Property',
            'checkinDate': '2025-07-01',
            'checkoutDate': '2025-07-05',
            'nights': 4,
            'guests': 2,
            'amountGross': 520.00,
            'amountVat': 88.00,
            'amountTouristTax': 12.00,
            'amountChannelFee': 52.00,
            'administration': 'TestAdmin'
        }
        
        # Prepare invoice data using generator
        invoice_data = str_invoice_generator.prepare_invoice_data(booking_data)
        
        # Generate table rows (complex section)
        table_rows = str_invoice_generator.generate_table_rows(invoice_data, 'nl')
        invoice_data['table_rows'] = table_rows
        
        # Initialize TemplateService
        db = DatabaseManager(test_mode=True)
        template_service = TemplateService(db)
        
        # Load template from filesystem
        template_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'templates', 'html',
            'str_invoice_nl_template.html'
        )
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Create field mappings (simple text replacement for all fields)
        field_mappings = {
            'fields': {
                key: {'path': key, 'format': 'text'}
                for key in invoice_data.keys()
            },
            'formatting': {
                'locale': 'nl_NL',
                'currency': 'EUR',
                'date_format': 'DD-MM-YYYY',
                'number_decimals': 2
            }
        }
        
        # Apply field mappings using TemplateService
        html_content = template_service.apply_field_mappings(
            template_content,
            invoice_data,
            field_mappings
        )
        
        # Verify HTML structure
        assert '<!DOCTYPE html>' in html_content
        assert '<html lang="nl">' in html_content
        assert 'FACTUUR' in html_content
        
        # Verify booking details
        assert 'TEST-TS-001' in html_content
        assert 'Test Guest' in html_content
        assert 'Test Property' in html_content
        
        # Verify amounts
        assert '€420.00' in html_content  # net_amount
        assert '€88.00' in html_content   # vat_amount
        assert '€12.00' in html_content   # tourist_tax
        assert '€520.00' in html_content  # amountGross
        
        # Verify table rows were included
        assert 'Verblijf Test Property' in html_content
        assert 'BTW' in html_content
        assert 'Toeristenbelasting' in html_content
        assert 'Totaal' in html_content
        
        # Verify no placeholders remain
        assert '{{' not in html_content or '{{ table_rows }}' not in html_content
    
    def test_str_invoice_english_with_template_service(self):
        """Test English STR invoice generation using TemplateService"""
        # Sample booking data
        booking_data = {
            'reservationCode': 'TEST-TS-EN-001',
            'guestName': 'John Smith',
            'channel': 'Booking.com',
            'listing': 'Beach House',
            'checkinDate': '2025-08-01',
            'checkoutDate': '2025-08-05',
            'nights': 4,
            'guests': 2,
            'amountGross': 600.00,
            'amountVat': 100.00,
            'amountTouristTax': 16.00,
            'amountChannelFee': 60.00,
            'administration': 'TestAdmin'
        }
        
        # Prepare invoice data
        invoice_data = str_invoice_generator.prepare_invoice_data(booking_data)
        
        # Generate table rows in English
        table_rows = str_invoice_generator.generate_table_rows(invoice_data, 'en')
        invoice_data['table_rows'] = table_rows
        
        # Initialize TemplateService
        db = DatabaseManager(test_mode=True)
        template_service = TemplateService(db)
        
        # Load English template
        template_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'templates', 'html',
            'str_invoice_en_template.html'
        )
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Create field mappings
        field_mappings = {
            'fields': {
                key: {'path': key, 'format': 'text'}
                for key in invoice_data.keys()
            },
            'formatting': {
                'locale': 'en_US',
                'currency': 'EUR',
                'date_format': 'DD-MM-YYYY',
                'number_decimals': 2
            }
        }
        
        # Apply field mappings
        html_content = template_service.apply_field_mappings(
            template_content,
            invoice_data,
            field_mappings
        )
        
        # Verify HTML structure
        assert '<!DOCTYPE html>' in html_content
        assert '<html lang="en">' in html_content
        assert 'INVOICE' in html_content
        
        # Verify English labels
        assert 'Stay at Beach House' in html_content
        assert 'VAT' in html_content
        assert 'Tourist Tax' in html_content
        assert 'Total' in html_content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
