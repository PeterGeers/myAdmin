"""
Tax Processing Routes Blueprint
Handles BTW (VAT) and Toeristenbelasting (Tourist Tax) declaration routes
"""
from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from database import DatabaseManager
from btw_processor import BTWProcessor
from toeristenbelasting_processor import ToeristenbelastingProcessor
from mutaties_cache import get_cache
from services.template_service import TemplateService
import os

# Create blueprint
tax_bp = Blueprint('tax', __name__)

# Global variables set by app.py
flag = False  # Test mode flag
logger = None  # Logger instance

def set_test_mode(test_mode):
    """Set test mode flag"""
    global flag
    flag = test_mode

def set_logger(log_instance):
    """Set logger instance"""
    global logger
    logger = log_instance


# BTW (VAT) Declaration routes
@tax_bp.route('/api/btw/generate-report', methods=['POST'])
@cognito_required(required_permissions=['btw_read', 'btw_process'])
def btw_generate_report(user_email, user_roles):
    """Generate BTW declaration report using TemplateService with field mappings
    
    Supports multiple output destinations:
    - download: Return content to frontend for download (default)
    - gdrive: Upload to tenant's Google Drive
    - s3: Upload to AWS S3 (future implementation)
    """
    try:
        data = request.get_json()
        administration = data.get('administration')
        year = data.get('year')
        quarter = data.get('quarter')
        output_destination = data.get('output_destination', 'download')  # Default to download
        folder_id = data.get('folder_id')  # Optional Google Drive folder ID
        
        if not all([administration, year, quarter]):
            return jsonify({
                'success': False, 
                'error': 'Administration, year, and quarter are required'
            }), 400
        
        # Get cache and database instances
        cache = get_cache()
        db = DatabaseManager(test_mode=flag)
        cache.get_data(db)
        
        # Generate structured report data using new generator
        from report_generators import btw_aangifte_generator
        
        report_data = btw_aangifte_generator.generate_btw_report(
            cache=cache,
            db=db,
            administration=administration,
            year=int(year),
            quarter=int(quarter)
        )
        
        if not report_data.get('success'):
            return jsonify(report_data), 500
        
        # Initialize TemplateService
        template_service = TemplateService(db)
        
        # Prepare template data
        template_data = btw_aangifte_generator.prepare_template_data(report_data)
        
        # Try to get template metadata from database
        template_type = 'btw_aangifte_html'
        metadata = None
        
        try:
            metadata = template_service.get_template_metadata(administration, template_type)
        except Exception as e:
            if logger:
                logger.warning(f"Could not get template metadata from database: {e}")
        
        # Load template
        if metadata and metadata.get('template_file_id'):
            # Load from Google Drive
            try:
                template_content = template_service.fetch_template_from_drive(
                    metadata['template_file_id'],
                    administration
                )
                field_mappings = metadata.get('field_mappings', {})
            except Exception as e:
                if logger:
                    logger.error(f"Failed to fetch template from Google Drive: {e}")
                # Fallback to filesystem
                metadata = None
        
        if not metadata:
            # Fallback: Load from filesystem
            template_path = os.path.join('backend', 'templates', 'html', 'btw_aangifte_template.html')
            
            if not os.path.exists(template_path):
                if logger:
                    logger.error(f"Template not found: {template_path}")
                return jsonify({'success': False, 'error': 'Template not found'}), 500
            
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
            # Use default field mappings (simple placeholder replacement)
            field_mappings = {
                'fields': {key: {'path': key, 'format': 'text'} for key in template_data.keys()},
                'formatting': {
                    'locale': 'nl_NL',
                    'currency': 'EUR',
                    'date_format': 'YYYY-MM-DD',
                    'number_decimals': 2
                }
            }
        
        # Apply field mappings using TemplateService
        html_report = template_service.apply_field_mappings(
            template_content,
            template_data,
            field_mappings
        )
        
        # Generate filename
        filename = f'BTW_Aangifte_{administration}_{year}_Q{quarter}.html'
        
        # Handle output destination
        from services.output_service import OutputService
        output_service = OutputService(db)
        
        output_result = output_service.handle_output(
            content=html_report,
            filename=filename,
            destination=output_destination,
            administration=administration,
            content_type='text/html',
            folder_id=folder_id
        )
        
        # Prepare transaction for saving (using existing logic)
        btw_processor = BTWProcessor(test_mode=flag)
        transaction = btw_processor._prepare_btw_transaction(
            administration, 
            year, 
            quarter, 
            report_data['calculations']
        )
        
        # Return result based on destination
        if output_destination == 'download':
            return jsonify({
                'success': True,
                'html_report': output_result['content'],
                'transaction': transaction,
                'calculations': report_data['calculations'],
                'quarter_end_date': report_data['metadata']['end_date'],
                'filename': output_result['filename']
            })
        else:
            # For gdrive or s3, return URL and metadata
            return jsonify({
                'success': True,
                'destination': output_result['destination'],
                'url': output_result.get('url'),
                'transaction': transaction,
                'calculations': report_data['calculations'],
                'quarter_end_date': report_data['metadata']['end_date'],
                'filename': output_result['filename'],
                'message': output_result['message']
            })
        
    except Exception as e:
        # Check if it's a Google Drive authentication error
        from google_drive_service import GoogleDriveAuthenticationError
        
        if isinstance(e, GoogleDriveAuthenticationError):
            if logger:
                logger.error(f"Google Drive authentication error: {e.to_dict()}")
            return jsonify({
                'success': False,
                **e.to_dict()
            }), 401  # 401 Unauthorized for auth errors
        
        if logger:
            logger.error(f"Failed to generate BTW report: {e}")
            import traceback
            traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@tax_bp.route('/api/btw/save-transaction', methods=['POST'])
@cognito_required(required_permissions=['transactions_create'])
def btw_save_transaction(user_email, user_roles):
    """Save BTW transaction to database"""
    try:
        data = request.get_json()
        transaction = data.get('transaction')
        
        if not transaction:
            return jsonify({'success': False, 'error': 'Transaction data required'}), 400
        
        btw_processor = BTWProcessor(test_mode=flag)
        result = btw_processor.save_btw_transaction(transaction)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@tax_bp.route('/api/btw/upload-report', methods=['POST'])
@cognito_required(required_permissions=['btw_process'])
def btw_upload_report(user_email, user_roles):
    """Upload BTW report to Google Drive"""
    try:
        data = request.get_json()
        html_content = data.get('html_content')
        filename = data.get('filename')
        
        if not all([html_content, filename]):
            return jsonify({
                'success': False, 
                'error': 'HTML content and filename are required'
            }), 400
        
        btw_processor = BTWProcessor(test_mode=flag)
        result = btw_processor.upload_report_to_drive(html_content, filename)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# Toeristenbelasting (Tourist Tax) Declaration routes
@tax_bp.route('/api/toeristenbelasting/generate-report', methods=['POST'])
@cognito_required(required_permissions=['str_read', 'reports_read'])
def toeristenbelasting_generate_report(user_email, user_roles):
    """Generate Toeristenbelasting declaration report
    
    Supports multiple output destinations:
    - download: Return content to frontend for download (default)
    - gdrive: Upload to tenant's Google Drive
    - s3: Upload to AWS S3 (future implementation)
    """
    try:
        data = request.get_json()
        year = data.get('year')
        output_destination = data.get('output_destination', 'download')  # Default to download
        folder_id = data.get('folder_id')  # Optional Google Drive folder ID
        
        if not year:
            return jsonify({
                'success': False, 
                'error': 'Year is required'
            }), 400
        
        processor = ToeristenbelastingProcessor(test_mode=flag)
        result = processor.generate_toeristenbelasting_report(year)
        
        # If report generation failed, return error
        if not result.get('success'):
            return jsonify(result), 500
        
        # Handle output destination if report was successful
        if output_destination != 'download':
            # Get administration from result (should be in the report data)
            # For now, we'll use a default or extract from the report
            # This may need to be passed as a parameter in the future
            administration = result.get('administration', 'default')
            
            db = DatabaseManager(test_mode=flag)
            from services.output_service import OutputService
            output_service = OutputService(db)
            
            # Generate filename
            filename = f'Toeristenbelasting_{administration}_{year}.html'
            
            output_result = output_service.handle_output(
                content=result.get('html_report', ''),
                filename=filename,
                destination=output_destination,
                administration=administration,
                content_type='text/html',
                folder_id=folder_id
            )
            
            # Update result with output information
            result['destination'] = output_result['destination']
            result['url'] = output_result.get('url')
            result['filename'] = output_result['filename']
            result['message'] = output_result['message']
            
            # Remove html_report from response for gdrive/s3 destinations
            if 'html_report' in result:
                del result['html_report']
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@tax_bp.route('/api/toeristenbelasting/available-years', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def toeristenbelasting_available_years(user_email, user_roles):
    """Get available years for Toeristenbelasting (current year and 3 years back)"""
    try:
        from datetime import datetime
        current_year = datetime.now().year
        
        # Generate years: current year and 3 years back
        years = [str(current_year - i) for i in range(4)]
        
        return jsonify({
            'success': True,
            'years': years
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
