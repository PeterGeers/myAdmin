"""
PDF Validation Routes Blueprint
Handles PDF URL validation and Google Drive integration
"""
from flask import Blueprint, request, jsonify, Response
from auth.cognito_utils import cognito_required
from pdf_validation import PDFValidator
import json

# Create blueprint
pdf_validation_bp = Blueprint('pdf_validation', __name__)

# Global variables set by app.py
flag = False  # Test mode flag

def set_test_mode(test_mode):
    """Set test mode flag"""
    global flag
    flag = test_mode


@pdf_validation_bp.route('/api/pdf/validate-urls-stream', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def pdf_validate_urls_stream(user_email, user_roles):
    """Stream PDF validation progress with Server-Sent Events"""
    validator = PDFValidator(test_mode=flag)
    year = request.args.get('year', '2025')
    administration = request.args.get('administration', 'all')
    
    def generate_progress():
        try:
            for progress_data in validator.validate_pdf_urls_with_progress(year, administration):
                if progress_data.get('validation_results') is not None:
                    validation_results = progress_data['validation_results']
                    for result in validation_results:
                        if 'record' in result and 'TransactionDate' in result['record']:
                            if result['record']['TransactionDate']:
                                date_obj = result['record']['TransactionDate']
                                if hasattr(date_obj, 'strftime'):
                                    result['record']['TransactionDate'] = date_obj.strftime('%Y-%m-%d')
                                else:
                                    result['record']['TransactionDate'] = str(date_obj)[:10]
                    
                    yield f"data: {json.dumps({'type': 'complete', 'validation_results': validation_results, 'total_records': progress_data['total'], 'ok_count': progress_data['ok_count'], 'failed_count': progress_data['failed_count']}, default=str)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'progress', **progress_data}, default=str)}\n\n"
                    
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return Response(generate_progress(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
    })


@pdf_validation_bp.route('/api/pdf/validate-urls', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def pdf_validate_urls(user_email, user_roles):
    """Validate all Google Drive URLs in mutaties table"""
    try:
        validator = PDFValidator(test_mode=flag)
        
        # Parse year and administration parameters
        year = request.args.get('year', '2025')
        administration = request.args.get('administration', 'all')
        print(f"Validating year: {year}, administration: {administration}")
        
        # Get results from the year-specific method
        results = []
        for progress_data in validator.validate_pdf_urls_with_progress(year, administration):
            if progress_data.get('validation_results') is not None:
                results = progress_data
                break
        
        # Format dates in validation results
        validation_results = results.get('validation_results', [])
        for result in validation_results:
            if 'record' in result and 'TransactionDate' in result['record']:
                if result['record']['TransactionDate']:
                    # Convert datetime to YYYY-MM-DD format
                    date_obj = result['record']['TransactionDate']
                    if hasattr(date_obj, 'strftime'):
                        result['record']['TransactionDate'] = date_obj.strftime('%Y-%m-%d')
                    else:
                        result['record']['TransactionDate'] = str(date_obj)[:10]
        
        return jsonify({
            'success': True,
            'validation_results': validation_results,
            'total_records': results.get('total', 0),
            'ok_count': results.get('ok_count', 0),
            'failed_count': results.get('failed_count', 0)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@pdf_validation_bp.route('/api/pdf/update-record', methods=['POST'])
@cognito_required(required_permissions=['invoices_update'])
def pdf_update_record(user_email, user_roles):
    """Update all records with matching Ref3/Ref4"""
    try:
        data = request.get_json()
        old_ref3 = data.get('old_ref3')
        old_ref4 = data.get('old_ref4')
        reference_number = data.get('reference_number')
        ref3 = data.get('ref3')
        ref4 = data.get('ref4')
        
        print(f"Update request: old_ref3={old_ref3}, ref3={ref3}, ref_num={reference_number}")
        
        if not old_ref3:
            return jsonify({'success': False, 'error': 'Original Ref3 is required'}), 400
        
        validator = PDFValidator(test_mode=flag)
        success = validator.update_record(old_ref3, reference_number, ref3, ref4)
        
        if success:
            return jsonify({'success': True, 'message': 'Records updated successfully'})
        else:
            return jsonify({'success': False, 'error': 'No records found to update or no changes made'}), 400
        
    except Exception as e:
        print(f"Update error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@pdf_validation_bp.route('/api/pdf/get-administrations', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def pdf_get_administrations(user_email, user_roles):
    """Get available administrations for a specific year"""
    try:
        year = request.args.get('year', '2025')
        validator = PDFValidator(test_mode=flag)
        administrations = validator.get_administrations_for_year(year)
        
        return jsonify({
            'success': True,
            'administrations': administrations
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@pdf_validation_bp.route('/api/pdf/validate-single-url', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def pdf_validate_single_url(user_email, user_roles):
    """Validate a single Google Drive URL"""
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({'success': False, 'error': 'URL parameter is required'}), 400
        
        validator = PDFValidator(test_mode=flag)
        
        # Create a mock record for validation
        mock_record = {
            'ID': 0,
            'TransactionNumber': '',
            'TransactionDate': '',
            'TransactionDescription': '',
            'TransactionAmount': 0,
            'ReferenceNumber': '',
            'Ref3': url,
            'Ref4': '',
            'Administration': ''
        }
        
        result = validator._validate_single_record(mock_record)
        
        return jsonify({
            'success': True,
            'status': result['status']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
