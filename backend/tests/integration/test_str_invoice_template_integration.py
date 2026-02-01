"""
Integration tests for STR Invoice Template System

Tests the complete flow from booking data to generated HTML invoice
using the template-based approach with report generators.
"""

import pytest
import os
from report_generators import str_invoice_generator


class TestSTRInvoiceTemplateIntegration:
    """Integration tests for STR invoice template system"""
    
    def test_complete_invoice_generation_nl(self):
        """Test complete invoice generation flow in Dutch"""
        # Sample booking data
        booking_data = {
            'reservationCode': 'TEST-NL-001',
            'guestName': 'Jan de Vries',
            'channel': 'Airbnb',
            'listing': 'Strandhuisje Amsterdam',
            'checkinDate': '2025-07-01',
            'checkoutDate': '2025-07-05',
            'nights': 4,
            'guests': 2,
            'amountGross': 520.00,
            'amountVat': 88.00,
            'amountTouristTax': 12.00,
            'amountChannelFee': 52.00
        }
        
        # Prepare invoice data
        invoice_data = str_invoice_generator.prepare_invoice_data(booking_data)
        
        # Generate table rows
        table_rows = str_invoice_generator.generate_table_rows(invoice_data, 'nl')
        
        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'templates', 'html', 
            'str_invoice_nl_template.html'
        )
        
        assert os.path.exists(template_path), f"Template not found: {template_path}"
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Replace placeholders
        html_content = template_content.replace('{{ table_rows }}', table_rows)
        
        for key, value in invoice_data.items():
            placeholder = f"{{{{ {key} }}}}"
            html_content = html_content.replace(placeholder, str(value))
        
        # Verify HTML structure
        assert '<!DOCTYPE html>' in html_content
        assert '<html lang="nl">' in html_content
        assert 'FACTUUR' in html_content
        
        # Verify booking details
        assert 'TEST-NL-001' in html_content
        assert 'Jan de Vries' in html_content
        assert 'Strandhuisje Amsterdam' in html_content
        
        # Verify amounts
        assert '€420.00' in html_content  # net_amount
        assert '€88.00' in html_content   # vat_amount
        assert '€12.00' in html_content   # tourist_tax
        assert '€520.00' in html_content  # amountGross
        
        # Verify Dutch labels
        assert 'Verblijf Strandhuisje Amsterdam' in html_content
        assert 'BTW' in html_content
        assert 'Toeristenbelasting' in html_content
        assert 'Totaal' in html_content
        
        # Verify no placeholders remain
        assert '{{' not in html_content
        assert '}}' not in html_content
    
    def test_complete_invoice_generation_en(self):
        """Test complete invoice generation flow in English"""
        # Sample booking data
        booking_data = {
            'reservationCode': 'TEST-EN-001',
            'guestName': 'John Smith',
            'channel': 'Booking.com',
            'listing': 'Beach House Amsterdam',
            'checkinDate': '2025-07-01',
            'checkoutDate': '2025-07-05',
            'nights': 4,
            'guests': 2,
            'amountGross': 520.00,
            'amountVat': 88.00,
            'amountTouristTax': 12.00,
            'amountChannelFee': 52.00
        }
        
        # Prepare invoice data
        invoice_data = str_invoice_generator.prepare_invoice_data(booking_data)
        
        # Generate table rows
        table_rows = str_invoice_generator.generate_table_rows(invoice_data, 'en')
        
        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'templates', 'html', 
            'str_invoice_en_template.html'
        )
        
        assert os.path.exists(template_path), f"Template not found: {template_path}"
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Replace placeholders
        html_content = template_content.replace('{{ table_rows }}', table_rows)
        
        for key, value in invoice_data.items():
            placeholder = f"{{{{ {key} }}}}"
            html_content = html_content.replace(placeholder, str(value))
        
        # Verify HTML structure
        assert '<!DOCTYPE html>' in html_content
        assert '<html lang="en">' in html_content
        assert 'INVOICE' in html_content
        
        # Verify booking details
        assert 'TEST-EN-001' in html_content
        assert 'John Smith' in html_content
        assert 'Beach House Amsterdam' in html_content
        
        # Verify amounts
        assert '€420.00' in html_content  # net_amount
        assert '€88.00' in html_content   # vat_amount
        assert '€12.00' in html_content   # tourist_tax
        assert '€520.00' in html_content  # amountGross
        
        # Verify English labels
        assert 'Stay at Beach House Amsterdam' in html_content
        assert 'VAT' in html_content
        assert 'Tourist Tax' in html_content
        assert 'Total' in html_content
        
        # Verify no placeholders remain
        assert '{{' not in html_content
        assert '}}' not in html_content
    
    def test_invoice_with_custom_billing(self):
        """Test invoice generation with custom billing information"""
        booking_data = {
            'reservationCode': 'TEST-CUSTOM-001',
            'guestName': 'Jane Doe',
            'channel': 'Direct',
            'listing': 'City Apartment',
            'checkinDate': '2025-08-01',
            'checkoutDate': '2025-08-03',
            'nights': 2,
            'guests': 1,
            'amountGross': 300.00,
            'amountVat': 0.00,
            'amountTouristTax': 6.00,
            'amountChannelFee': 0.00
        }
        
        custom_billing = {
            'name': 'Acme Corporation',
            'address': '123 Business Street',
            'city': 'Amsterdam, 1000 AA'
        }
        
        # Prepare invoice data with custom billing
        invoice_data = str_invoice_generator.prepare_invoice_data(booking_data, custom_billing)
        
        # Verify custom billing is applied
        assert invoice_data['billing_name'] == 'Acme Corporation'
        assert invoice_data['billing_address'] == '123 Business Street'
        assert invoice_data['billing_city'] == 'Amsterdam, 1000 AA'
        
        # Generate table rows
        table_rows = str_invoice_generator.generate_table_rows(invoice_data, 'nl')
        
        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'templates', 'html', 
            'str_invoice_nl_template.html'
        )
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Replace placeholders
        html_content = template_content.replace('{{ table_rows }}', table_rows)
        
        for key, value in invoice_data.items():
            placeholder = f"{{{{ {key} }}}}"
            html_content = html_content.replace(placeholder, str(value))
        
        # Verify custom billing appears in HTML
        assert 'Acme Corporation' in html_content
        assert '123 Business Street' in html_content
        assert 'Amsterdam, 1000 AA' in html_content
    
    def test_invoice_without_vat_and_tax(self):
        """Test invoice generation without VAT and tourist tax"""
        booking_data = {
            'reservationCode': 'TEST-SIMPLE-001',
            'guestName': 'Bob Johnson',
            'channel': 'Direct',
            'listing': 'Simple Room',
            'checkinDate': '2025-09-01',
            'checkoutDate': '2025-09-02',
            'nights': 1,
            'guests': 1,
            'amountGross': 100.00,
            'amountVat': 0.00,
            'amountTouristTax': 0.00,
            'amountChannelFee': 0.00
        }
        
        # Prepare invoice data
        invoice_data = str_invoice_generator.prepare_invoice_data(booking_data)
        
        # Generate table rows
        table_rows = str_invoice_generator.generate_table_rows(invoice_data, 'en')
        
        # Verify VAT and tourist tax rows are not present
        assert 'VAT' not in table_rows
        assert 'Tourist Tax' not in table_rows
        
        # Verify accommodation and total rows are present
        assert 'Stay at Simple Room' in table_rows
        assert 'Total' in table_rows
        assert '€100.00' in table_rows


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
