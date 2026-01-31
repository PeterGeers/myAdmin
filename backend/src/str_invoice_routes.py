from flask import Blueprint, request, jsonify, render_template_string
import logging
from database import DatabaseManager
import re
from datetime import datetime, timedelta
import os
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required

logger = logging.getLogger(__name__)

str_invoice_bp = Blueprint('str_invoice', __name__)

@str_invoice_bp.route('/search-booking', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
@tenant_required()
def search_booking(user_email, user_roles, tenant, user_tenants):
    """Search for booking by guest name or reservation code - filtered by tenant and date range"""
    try:
        query = request.args.get('query', '').strip()
        if not query:
            return jsonify({'success': False, 'error': 'Search query required'}), 400
        
        # Get limit parameter (default 20, use 0 or 'all' for no limit)
        limit_param = request.args.get('limit', '20')
        limit = 0 if limit_param in ['0', 'all'] else int(limit_param)
        
        # Get startDate parameter (default to 90 days ago if not provided)
        start_date_param = request.args.get('startDate', '')
        if start_date_param:
            start_date = start_date_param
        else:
            start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
        
        # Current date (no future bookings)
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Search by guest name or reservation code with tenant and date filtering
        if limit > 0:
            search_query = """
            SELECT * FROM vw_bnb_total 
            WHERE (guestName LIKE %s OR reservationCode LIKE %s)
            AND administration = %s
            AND checkinDate >= %s
            AND checkinDate <= %s
            ORDER BY checkinDate DESC
            LIMIT %s
            """
            search_pattern = f"%{query}%"
            cursor.execute(search_query, [search_pattern, search_pattern, tenant, start_date, current_date, limit])
        else:
            # No limit - return all results (but still filtered by tenant and date)
            search_query = """
            SELECT * FROM vw_bnb_total 
            WHERE (guestName LIKE %s OR reservationCode LIKE %s)
            AND administration = %s
            AND checkinDate >= %s
            AND checkinDate <= %s
            ORDER BY checkinDate DESC
            """
            search_pattern = f"%{query}%"
            cursor.execute(search_query, [search_pattern, search_pattern, tenant, start_date, current_date])
        
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True, 
            'bookings': results, 
            'date_range': {
                'from': start_date,
                'to': current_date
            }
        })
        
    except Exception as e:
        logger.error(f'Error in endpoint: {str(e)}')
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@str_invoice_bp.route('/generate-invoice', methods=['POST'])
@cognito_required(required_permissions=['str_create'])
@tenant_required()
def generate_invoice(user_email, user_roles, tenant, user_tenants):
    """Generate STR invoice for a specific booking using TemplateService with field mappings
    
    Supports multiple output destinations:
    - download: Return content to frontend for download (default)
    - gdrive: Upload to tenant's Google Drive
    - s3: Upload to AWS S3 (future implementation)
    """
    try:
        data = request.get_json()
        reservation_code = data.get('reservationCode')
        language = data.get('language', 'nl')  # 'nl' or 'en'
        custom_billing = data.get('customBilling', {})
        output_destination = data.get('output_destination', 'download')  # Default to download
        folder_id = data.get('folder_id')  # Optional Google Drive folder ID
        
        if not reservation_code:
            return jsonify({'success': False, 'error': 'Reservation code required'}), 400
        
        # Get booking details
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        booking_query = """
        SELECT amountGross, checkinDate, checkoutDate, guestName, channel, 
               listing, nights, guests, reservationCode, amountTouristTax,
               amountChannelFee, amountNett, amountVat, administration
        FROM vw_bnb_total 
        WHERE reservationCode = %s AND administration IN ({})
        LIMIT 1
        """.format(', '.join(['%s'] * len(user_tenants)))
        
        cursor.execute(booking_query, [reservation_code] + user_tenants)
        booking = cursor.fetchone()
        
        cursor.close()
        connection.close()
        
        if not booking:
            return jsonify({'success': False, 'error': 'Booking not found or access denied'}), 404
        
        # Additional validation: ensure booking administration is in user_tenants
        booking_admin = booking.get('administration')
        if booking_admin not in user_tenants:
            return jsonify({
                'success': False, 
                'error': f'Access denied to administration: {booking_admin}'
            }), 403
        
        # Import generator and TemplateService
        from report_generators import str_invoice_generator
        from services.template_service import TemplateService
        
        # Initialize TemplateService
        template_service = TemplateService(db)
        
        # Prepare invoice data using generator
        invoice_data = str_invoice_generator.prepare_invoice_data(booking, custom_billing)
        
        # Generate table rows (complex section pre-generated by generator)
        table_rows = str_invoice_generator.generate_table_rows(invoice_data, language)
        
        # Add table_rows to invoice_data
        invoice_data['table_rows'] = table_rows
        
        # Try to get template metadata from database
        template_type = f'str_invoice_{language}'
        metadata = None
        
        try:
            metadata = template_service.get_template_metadata(booking_admin, template_type)
        except Exception as e:
            logger.warning(f"Could not get template metadata from database: {e}")
        
        # Load template
        if metadata and metadata.get('template_file_id'):
            # Load from Google Drive
            try:
                template_content = template_service.fetch_template_from_drive(
                    metadata['template_file_id'],
                    booking_admin
                )
                field_mappings = metadata.get('field_mappings', {})
            except Exception as e:
                logger.error(f"Failed to fetch template from Google Drive: {e}")
                # Fallback to filesystem
                metadata = None
        
        if not metadata:
            # Fallback: Load from filesystem
            template_file = f'str_invoice_{language}_template.html'
            template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'html', template_file)
            
            if not os.path.exists(template_path):
                logger.error(f"Template not found: {template_path}")
                return jsonify({'success': False, 'error': 'Template not found'}), 500
            
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
            # Use default field mappings (simple placeholder replacement)
            field_mappings = {
                'fields': {key: {'path': key, 'format': 'text'} for key in invoice_data.keys()},
                'formatting': {
                    'locale': 'nl_NL' if language == 'nl' else 'en_US',
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
        
        # Generate filename
        filename = f'Invoice_{reservation_code}_{language.upper()}.html'
        
        # Handle output destination
        from services.output_service import OutputService
        output_service = OutputService(db)
        
        output_result = output_service.handle_output(
            content=html_content,
            filename=filename,
            destination=output_destination,
            administration=booking_admin,
            content_type='text/html',
            folder_id=folder_id
        )
        
        # Return result based on destination
        if output_destination == 'download':
            return jsonify({
                'success': True, 
                'html': output_result['content'],
                'booking_data': invoice_data,
                'filename': output_result['filename']
            })
        else:
            # For gdrive or s3, return URL and metadata
            return jsonify({
                'success': True,
                'destination': output_result['destination'],
                'url': output_result.get('url'),
                'booking_data': invoice_data,
                'filename': output_result['filename'],
                'message': output_result['message']
            })
        
    except Exception as e:
        logger.error(f'Error in endpoint: {str(e)}')
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


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
@tenant_required()
def upload_template_to_drive(user_email, user_roles, tenant, user_tenants):
    """Upload STR invoice templates to Google Drive - tenant-specific
    
    DESIGN DECISION: STR Templates are TENANT-SPECIFIC
    
    Rationale:
    - STR invoices are property-specific and may require different branding per tenant
    - Different tenants may have different property portfolios and business requirements
    - Templates should be isolated by tenant to prevent cross-tenant template access
    - Each tenant should manage their own invoice templates independently
    
    Security: This endpoint requires tenant filtering to ensure templates are uploaded
    to tenant-specific folders and users can only manage their own tenant's templates.
    """
    try:
        from google_drive_service import GoogleDriveService
        
        drive_service = GoogleDriveService()
        
        # Use tenant-specific folder structure
        # Base template folder ID - this should be configurable per tenant in the future
        base_template_folder_id = "12FJAYbX5MI3wpGxwahcHykRQfUCRZob1"
        
        # Create or find tenant-specific subfolder
        tenant_folder_name = f"templates_{tenant}"
        
        # Check if tenant folder exists, create if not
        tenant_folder_result = drive_service.check_file_exists(tenant_folder_name, base_template_folder_id)
        
        if tenant_folder_result['exists']:
            tenant_folder_id = tenant_folder_result['file']['id']
        else:
            # Create tenant-specific folder
            tenant_folder = drive_service.create_folder(tenant_folder_name, base_template_folder_id)
            tenant_folder_id = tenant_folder['id']
        
        results = []
        templates = ['str_invoice_nl.html', 'str_invoice_en.html']
        
        for template_name in templates:
            # Use tenant-specific template naming
            tenant_template_name = f"{tenant}_{template_name}"
            template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', template_name)
            
            if os.path.exists(template_path):
                try:
                    # Check if tenant-specific template already exists
                    existing = drive_service.check_file_exists(tenant_template_name, tenant_folder_id)
                    
                    if existing['exists']:
                        results.append({
                            'template': tenant_template_name,
                            'status': 'already_exists',
                            'url': existing['file']['url'],
                            'tenant': tenant
                        })
                    else:
                        # Read and upload content with tenant-specific naming
                        with open(template_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        upload_result = drive_service.upload_text_file(
                            content, tenant_template_name, tenant_folder_id, 'text/html'
                        )
                        
                        results.append({
                            'template': tenant_template_name,
                            'status': 'uploaded',
                            'url': upload_result['url'],
                            'tenant': tenant
                        })
                        
                except Exception as e:
                    results.append({
                        'template': tenant_template_name,
                        'status': 'error',
                        'error': 'Internal server error',
                        'tenant': tenant
                    })
            else:
                results.append({
                    'template': tenant_template_name,
                    'status': 'not_found',
                    'tenant': tenant
                })
        
        return jsonify({
            'success': True,
            'message': f'Template upload completed for tenant: {tenant}',
            'results': results,
            'tenant': tenant,
            'tenant_folder_url': f'https://drive.google.com/drive/folders/{tenant_folder_id}',
            'base_folder_url': f'https://drive.google.com/drive/folders/{base_template_folder_id}'
        })
        
    except Exception as e:
        logger.error(f'Error in endpoint: {str(e)}')
        return jsonify({'success': False, 'error': 'Internal server error'}), 500