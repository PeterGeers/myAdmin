"""
STR Invoice Generator

Generates HTML table rows for STR (Short-Term Rental) invoices.
Supports both Dutch (NL) and English (UK) invoice formats.

This module is part of the template-based reporting system and works with
the TemplateService to generate complete invoice HTML.
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def generate_table_rows(invoice_data: Dict[str, Any], language: str = 'nl') -> str:
    """
    Generate HTML table rows for STR invoice line items.
    
    This function creates the itemized breakdown of charges including:
    - Accommodation/stay charges
    - VAT (if applicable)
    - Tourist tax (if applicable)
    - Total amount
    
    Args:
        invoice_data: Dictionary containing invoice data with keys:
            - listing: Property name
            - net_amount: Net accommodation charge
            - vat_amount: VAT amount (optional)
            - tourist_tax: Tourist tax amount (optional)
            - amountGross: Total gross amount
        language: Language code ('nl' for Dutch, 'en' for English)
    
    Returns:
        HTML string containing table rows for the invoice line items
    
    Example:
        >>> data = {
        ...     'listing': 'Beach House',
        ...     'net_amount': 500.00,
        ...     'vat_amount': 105.00,
        ...     'tourist_tax': 15.00,
        ...     'amountGross': 620.00
        ... }
        >>> rows = generate_table_rows(data, 'en')
    """
    try:
        # Extract values from invoice data
        listing = invoice_data.get('listing', 'Property')
        net_amount = float(invoice_data.get('net_amount', 0))
        vat_amount = float(invoice_data.get('vat_amount', 0))
        tourist_tax = float(invoice_data.get('tourist_tax', 0))
        amount_gross = float(invoice_data.get('amountGross', 0))
        
        # Language-specific labels
        if language == 'nl':
            stay_label = f"Verblijf {listing}"
            vat_label = "BTW"
            tourist_tax_label = "Toeristenbelasting"
            total_label = "Totaal"
        else:  # English
            stay_label = f"Stay at {listing}"
            vat_label = "VAT"
            tourist_tax_label = "Tourist Tax"
            total_label = "Total"
        
        # Build table rows
        rows = []
        
        # Accommodation row
        rows.append(
            f'                <tr>\n'
            f'                    <td>{stay_label}</td>\n'
            f'                    <td>1</td>\n'
            f'                    <td>€{net_amount:.2f}</td>\n'
            f'                    <td>€{net_amount:.2f}</td>\n'
            f'                </tr>'
        )
        
        # VAT row (if applicable)
        if vat_amount > 0:
            rows.append(
                f'                <tr>\n'
                f'                    <td>{vat_label}</td>\n'
                f'                    <td>1</td>\n'
                f'                    <td>€{vat_amount:.2f}</td>\n'
                f'                    <td>€{vat_amount:.2f}</td>\n'
                f'                </tr>'
            )
        
        # Tourist tax row (if applicable)
        if tourist_tax > 0:
            rows.append(
                f'                <tr>\n'
                f'                    <td>{tourist_tax_label}</td>\n'
                f'                    <td>1</td>\n'
                f'                    <td>€{tourist_tax:.2f}</td>\n'
                f'                    <td>€{tourist_tax:.2f}</td>\n'
                f'                </tr>'
            )
        
        # Total row
        rows.append(
            f'                <tr class="total-row">\n'
            f'                    <td colspan="3"><strong>{total_label}</strong></td>\n'
            f'                    <td><strong>€{amount_gross:.2f}</strong></td>\n'
            f'                </tr>'
        )
        
        # Join all rows
        table_rows_html = '\n'.join(rows)
        
        logger.info(f"Generated {len(rows)} table rows for STR invoice in language '{language}'")
        
        return table_rows_html
        
    except Exception as e:
        logger.error(f"Failed to generate STR invoice table rows: {e}")
        # Return minimal fallback
        return f'                <tr><td colspan="4">Error generating invoice details</td></tr>'


def prepare_invoice_data(booking_data: Dict[str, Any], custom_billing: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Prepare invoice data from booking data for template rendering.
    
    This function transforms raw booking data into a structured format
    suitable for invoice template rendering, including company information
    and billing details.
    
    Args:
        booking_data: Raw booking data from database
        custom_billing: Optional custom billing information to override defaults
    
    Returns:
        Dictionary containing all data needed for invoice template
    
    Example:
        >>> booking = {
        ...     'reservationCode': 'ABC123',
        ...     'guestName': 'John Doe',
        ...     'amountGross': 620.00,
        ...     'amountVat': 105.00,
        ...     'amountTouristTax': 15.00
        ... }
        >>> invoice_data = prepare_invoice_data(booking)
    """
    try:
        from datetime import datetime
        
        # Extract booking details
        amount_gross = float(booking_data.get('amountGross', 0))
        vat_amount = float(booking_data.get('amountVat', 0))
        tourist_tax = float(booking_data.get('amountTouristTax', 0))
        
        # Calculate net amount
        net_amount = amount_gross - vat_amount - tourist_tax
        
        # Parse dates
        checkin_date = booking_data.get('checkinDate', '')
        if isinstance(checkin_date, str):
            try:
                checkin_dt = datetime.strptime(checkin_date, '%Y-%m-%d')
            except:
                checkin_dt = datetime.now()
        else:
            checkin_dt = checkin_date
        
        checkout_date = booking_data.get('checkoutDate', '')
        if isinstance(checkout_date, str):
            try:
                checkout_dt = datetime.strptime(checkout_date, '%Y-%m-%d')
            except:
                checkout_dt = datetime.now()
        else:
            checkout_dt = checkout_date
        
        # Format dates
        invoice_date = checkin_dt.strftime('%d-%m-%Y')
        due_date = checkin_dt.strftime('%d-%m-%Y')
        checkin_formatted = checkin_dt.strftime('%d-%m-%Y')
        checkout_formatted = checkout_dt.strftime('%d-%m-%Y') if checkout_date else ''
        
        # Company information (default - should be configurable per tenant)
        company_info = {
            'company_name': 'Jabaki a Goodwin Solutions Company',
            'company_address': 'Beemsterstraat 3',
            'company_postal_city': '2131 ZA Hoofddorp',
            'company_country': 'Nederland',
            'company_vat': 'NL812613764B02',
            'company_coc': '24352408',
            'contact_email': 'peter@jabaki.nl'
        }
        
        # Billing information
        billing_name = booking_data.get('guestName', '')
        billing_address = f"Via {booking_data.get('channel', '')}"
        billing_city = f"Reservering: {booking_data.get('reservationCode', '')}"
        
        # Override with custom billing if provided
        if custom_billing:
            if custom_billing.get('name'):
                billing_name = custom_billing['name']
            if custom_billing.get('address'):
                billing_address = custom_billing['address']
            if custom_billing.get('city'):
                billing_city = custom_billing['city']
        
        # Prepare complete invoice data
        invoice_data = {
            # Booking details
            'reservationCode': booking_data.get('reservationCode', ''),
            'guestName': booking_data.get('guestName', ''),
            'channel': booking_data.get('channel', ''),
            'listing': booking_data.get('listing', ''),
            'checkinDate': checkin_formatted,
            'checkoutDate': checkout_formatted,
            'nights': int(booking_data.get('nights', 1)),
            'guests': int(booking_data.get('guests', 1)),
            
            # Financial details
            'amountGross': amount_gross,
            'amountTouristTax': tourist_tax,
            'amountChannelFee': float(booking_data.get('amountChannelFee', 0)),
            'amountNett': net_amount,
            'amountVat': vat_amount,
            'net_amount': net_amount,
            'tourist_tax': tourist_tax,
            'vat_amount': vat_amount,
            
            # Billing information
            'billing_name': billing_name,
            'billing_address': billing_address,
            'billing_city': billing_city,
            
            # Dates
            'invoice_date': invoice_date,
            'due_date': due_date,
            
            # Company information
            **company_info
        }
        
        logger.info(f"Prepared invoice data for reservation {invoice_data['reservationCode']}")
        
        return invoice_data
        
    except Exception as e:
        logger.error(f"Failed to prepare invoice data: {e}")
        raise Exception(f"Failed to prepare invoice data: {str(e)}")
