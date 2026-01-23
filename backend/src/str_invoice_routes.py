from flask import Blueprint, request, jsonify, render_template_string, render_template
from database import DatabaseManager
import re
from datetime import datetime, timedelta
import os
from auth.cognito_utils import cognito_required

str_invoice_bp = Blueprint('str_invoice', __name__)

@str_invoice_bp.route('/test', methods=['GET'])
@cognito_required(required_permissions=[])
def test_page(user_email, user_roles):
    """Diagnostic test page for STR Invoice API"""
    return render_template('str_test.html')

@str_invoice_bp.route('/search-booking', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def search_booking(user_email, user_roles):
    """Search for booking by guest name or reservation code"""
    try:
        query = request.args.get('query', '').strip()
        if not query:
            return jsonify({'success': False, 'error': 'Search query required'}), 400
        
        # Get limit parameter (default 20, use 0 or 'all' for no limit)
        limit_param = request.args.get('limit', '20')
        limit = 0 if limit_param in ['0', 'all'] else int(limit_param)
        
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Search by guest name or reservation code using regex-like matching
        if limit > 0:
            search_query = """
            SELECT * FROM vw_bnb_total 
            WHERE guestName LIKE %s OR reservationCode LIKE %s
            ORDER BY checkinDate DESC
            LIMIT %s
            """
            search_pattern = f"%{query}%"
            cursor.execute(search_query, [search_pattern, search_pattern, limit])
        else:
            # No limit - return all results
            search_query = """
            SELECT * FROM vw_bnb_total 
            WHERE guestName LIKE %s OR reservationCode LIKE %s
            ORDER BY checkinDate DESC
            """
            search_pattern = f"%{query}%"
            cursor.execute(search_query, [search_pattern, search_pattern])
        
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({'success': True, 'bookings': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@str_invoice_bp.route('/generate-invoice', methods=['POST'])
@cognito_required(required_permissions=['str_create'])
def generate_invoice(user_email, user_roles):
    """Generate STR invoice for a specific booking"""
    try:
        data = request.get_json()
        reservation_code = data.get('reservationCode')
        language = data.get('language', 'nl')  # 'nl' or 'en'
        custom_billing = data.get('customBilling', {})
        
        if not reservation_code:
            return jsonify({'success': False, 'error': 'Reservation code required'}), 400
        
        # Get booking details
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        booking_query = """
        SELECT amountGross, checkinDate, checkoutDate, guestName, channel, 
               listing, nights, guests, reservationCode, amountTouristTax,
               amountChannelFee, amountNett, amountVat
        FROM vw_bnb_total 
        WHERE reservationCode = %s
        LIMIT 1
        """
        
        cursor.execute(booking_query, [reservation_code])
        booking = cursor.fetchone()
        
        cursor.close()
        connection.close()
        
        if not booking:
            return jsonify({'success': False, 'error': 'Booking not found'}), 404
        
        # Calculate invoice details
        invoice_data = calculate_invoice_details(booking)
        
        # Override with custom billing if provided
        if custom_billing.get('name'):
            invoice_data['billing_name'] = custom_billing['name']
        if custom_billing.get('address'):
            invoice_data['billing_address'] = custom_billing['address']
        if custom_billing.get('city'):
            invoice_data['billing_city'] = custom_billing['city']
        
        # Generate HTML
        html_content = generate_invoice_html(invoice_data, language)
        
        return jsonify({
            'success': True, 
            'html': html_content,
            'booking_data': invoice_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def calculate_invoice_details(booking):
    """Calculate all invoice details from booking data"""
    amount_gross = float(booking.get('amountGross', 0))
    nights = int(booking.get('nights', 1))
    guests = int(booking.get('guests', 1))
    tourist_tax = float(booking.get('amountTouristTax', 0))
    
    # Use direct values without calculations
    vat_amount = float(booking.get('amountVat', 0))
    
    # Calculate net amount (gross - vat - tourist tax)
    net_amount = amount_gross - vat_amount - tourist_tax
    
    # Dates
    checkin_date = booking.get('checkinDate', '')
    if isinstance(checkin_date, str):
        try:
            checkin_dt = datetime.strptime(checkin_date, '%Y-%m-%d')
        except:
            checkin_dt = datetime.now()
    else:
        checkin_dt = checkin_date
    
    invoice_date = checkin_dt.strftime('%d-%m-%Y')
    due_date = checkin_dt.strftime('%d-%m-%Y')  # Same as invoice date for STR
    payment_date = checkin_dt.strftime('%d-%m-%Y')
    
    return {
        'reservationCode': booking.get('reservationCode', ''),
        'guestName': booking.get('guestName', ''),
        'channel': booking.get('channel', ''),
        'listing': booking.get('listing', ''),
        'checkinDate': checkin_dt.strftime('%d-%m-%Y'),
        'checkoutDate': booking.get('checkoutDate', ''),
        'nights': nights,
        'guests': guests,
        'amountGross': amount_gross,
        'amountTouristTax': tourist_tax,
        'amountChannelFee': float(booking.get('amountChannelFee', 0)),
        'amountNett': net_amount,
        'amountVat': vat_amount,
        # Keep legacy field names for template compatibility
        'net_amount': net_amount,
        'tourist_tax': tourist_tax,
        'vat_amount': vat_amount,
        'billing_name': booking.get('guestName', ''),
        'billing_address': f"Via {booking.get('channel', '')}",
        'billing_city': f"Reservering: {booking.get('reservationCode', '')}",
        'invoice_date': invoice_date,
        'due_date': due_date
    }

def generate_invoice_html(invoice_data, language='nl'):
    """Generate HTML invoice using template from local or Google Drive"""
    try:
        # Try local template first
        template_file = f'str_invoice_{language}.html'
        template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', template_file)
        
        template_content = None
        
        # Read from local file if exists
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
        else:
            # Fallback: could implement Google Drive template fetching here
            # For now, use a basic template
            template_content = get_basic_template(language)
        
        # Simple template replacement (basic Jinja2-like)
        html_content = template_content
        
        # Replace variables
        for key, value in invoice_data.items():
            placeholder = f"{{{{ {key} }}}}"
            html_content = html_content.replace(placeholder, str(value))
        
        # Handle conditional blocks for tourist tax
        if invoice_data.get('tourist_tax', 0) > 0:
            html_content = html_content.replace('{% if tourist_tax > 0 %}', '')
            html_content = html_content.replace('{% endif %}', '')
        else:
            pattern = r'{% if tourist_tax > 0 %}.*?{% endif %}'
            html_content = re.sub(pattern, '', html_content, flags=re.DOTALL)
        
        # Handle conditional blocks for VAT
        if invoice_data.get('vat_amount', 0) > 0:
            html_content = html_content.replace('{% if vat_amount > 0 %}', '')
            html_content = html_content.replace('{% endif %}', '')
        else:
            pattern = r'{% if vat_amount > 0 %}.*?{% endif %}'
            html_content = re.sub(pattern, '', html_content, flags=re.DOTALL)
        
        # Fix HTML entities first
        html_content = html_content.replace('&gt;', '>')
        html_content = html_content.replace('&lt;', '<')
        html_content = html_content.replace('&quot;', '"')
        html_content = html_content.replace('&amp;', '&')
        
        # Cleaning fee section removed from templates
        
        # Format currency values
        for key in ['net_amount', 'tourist_tax', 'vat_amount', 'amountGross']:
            value = invoice_data.get(key, 0)
            formatted_value = f"{value:.2f}"
            placeholder = f'{{{{ "%.2f"|format({key}) }}}}'
            html_content = html_content.replace(placeholder, formatted_value)
        
        return html_content
        
    except Exception as e:
        return f"<html><body><h1>Error generating invoice</h1><p>{str(e)}</p></body></html>"

def get_basic_template(language='nl'):
    """Return basic template if file not found"""
    if language == 'nl':
        return """
<!DOCTYPE html>
<html><head><title>Factuur</title></head>
<body>
<h1>FACTUUR</h1>
<p>Reservering: {{ reservationCode }}</p>
<p>Gast: {{ guestName }}</p>
<p>Totaal: €{{ amountGross }}</p>
</body></html>
"""
    else:
        return """
<!DOCTYPE html>
<html><head><title>Invoice</title></head>
<body>
<h1>INVOICE</h1>
<p>Reservation: {{ reservationCode }}</p>
<p>Guest: {{ guestName }}</p>
<p>Total: €{{ amountGross }}</p>
</body></html>
"""

@str_invoice_bp.route('/upload-template', methods=['POST'])
@cognito_required(required_permissions=['str_create'])
def upload_template_to_drive(user_email, user_roles):
    """Upload invoice templates to Google Drive"""
    try:
        from google_drive_service import GoogleDriveService
        
        drive_service = GoogleDriveService()
        template_folder_id = "12FJAYbX5MI3wpGxwahcHykRQfUCRZob1"
        
        results = []
        templates = ['str_invoice_nl.html', 'str_invoice_en.html']
        
        for template_name in templates:
            template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', template_name)
            
            if os.path.exists(template_path):
                try:
                    # Check if already exists
                    existing = drive_service.check_file_exists(template_name, template_folder_id)
                    
                    if existing['exists']:
                        results.append({
                            'template': template_name,
                            'status': 'already_exists',
                            'url': existing['file']['url']
                        })
                    else:
                        # Read and upload content
                        with open(template_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        upload_result = drive_service.upload_text_file(
                            content, template_name, template_folder_id, 'text/html'
                        )
                        
                        results.append({
                            'template': template_name,
                            'status': 'uploaded',
                            'url': upload_result['url']
                        })
                        
                except Exception as e:
                    results.append({
                        'template': template_name,
                        'status': 'error',
                        'error': str(e)
                    })
            else:
                results.append({
                    'template': template_name,
                    'status': 'not_found'
                })
        
        return jsonify({
            'success': True,
            'message': 'Template upload completed',
            'results': results,
            'folder_url': f'https://drive.google.com/drive/folders/{template_folder_id}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500