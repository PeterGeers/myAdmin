"""
Invoice Routes Blueprint

Handles invoice upload, processing, and approval endpoints.
Extracted from app.py during refactoring (Phase 2.2)
"""

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.invoice_service import InvoiceService
import os

invoice_bp = Blueprint('invoices', __name__)

# Upload folder configuration
UPLOAD_FOLDER = 'uploads'

# Access to flag from app.py (test mode)
flag = False

def set_test_mode(test_mode):
    """Set the test mode flag from app.py"""
    global flag
    flag = test_mode


@invoice_bp.route('/api/upload', methods=['POST', 'OPTIONS'])
@cognito_required(required_permissions=['invoices_create'])
@tenant_required()
def upload_file(user_email, user_roles, tenant, user_tenants):
    """Upload and process PDF file"""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:3000')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        return response
        
    print("\n*** UPLOAD ENDPOINT CALLED ***", flush=True)
    print(f"Tenant: {tenant}", flush=True)
    
    try:
        # Initialize invoice service
        invoice_service = InvoiceService(test_mode=flag)
        
        print("=== UPLOAD REQUEST START ===", flush=True)
        print(f"Request method: {request.method}", flush=True)
        print(f"Request files: {list(request.files.keys())}", flush=True)
        print(f"Request form field count: {len(request.form)}", flush=True)
        
        if 'file' not in request.files:
            print("ERROR: No file in request", flush=True)
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        folder_name = request.form.get('folderName', 'General')
        print(f"File: {file.filename}, Folder: {folder_name}", flush=True)
        
        if file.filename == '':
            print("ERROR: No file selected", flush=True)
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if file and invoice_service.allowed_file(file.filename):
            filename = secure_filename(file.filename)
            temp_path = os.path.join(UPLOAD_FOLDER, filename)
            print(f"Saving file to: {temp_path}", flush=True)
            file.save(temp_path)
            print("File saved successfully", flush=True)
            
            # Upload to Google Drive
            drive_result = invoice_service.upload_to_drive(temp_path, filename, folder_name, tenant)
            
            # Check if user wants to force upload (bypass duplicate check)
            force_upload = request.form.get('forceUpload', 'false').lower() == 'true'
            
            if not force_upload:
                # Early duplicate detection - check before processing
                print("Checking for duplicates before processing...", flush=True)
                duplicate_check_result = invoice_service.check_early_duplicates(
                    filename, folder_name, drive_result
                )
                if duplicate_check_result['has_duplicates']:
                    print(f"Duplicate detected - stopping upload: {duplicate_check_result['message']}", flush=True)
                    # Clean up temp file
                    invoice_service.cleanup_temp_file(temp_path)
                    return jsonify({
                        'success': False,
                        'error': 'duplicate_detected',
                        'message': duplicate_check_result['message'],
                        'duplicate_info': duplicate_check_result['duplicate_info']
                    }), 409
            else:
                print("Force upload enabled - bypassing duplicate check...", flush=True)
            
            print("No duplicates found - proceeding with processing...", flush=True)
            
            # Process the invoice file
            result = invoice_service.process_invoice_file(temp_path, drive_result, folder_name, tenant)
            
            # Move file to the correct vendor folder
            try:
                invoice_service.move_file_to_folder(temp_path, filename, result['folder'])
            except Exception as move_error:
                print(f"Error moving file: {move_error}", flush=True)
                # Continue even if move fails - file is already processed
            
            return jsonify({
                'success': True,
                'filename': filename,
                'folder': result['folder'],
                'extractedText': result['extracted_text'],
                'vendorData': result['vendor_data'],
                'transactions': result['transactions'],
                'preparedTransactions': result['prepared_transactions'],
                'templateTransactions': result['template_transactions'],
                'parserUsed': result['parser_used']
            })
        
        return jsonify({'success': False, 'error': 'Invalid file type'}), 400
        
    except Exception as e:
        print(f"\n=== UPLOAD ERROR ===", flush=True)
        print(f"Error type: {type(e).__name__}", flush=True)
        print(f"Error message: {str(e)}", flush=True)
        import traceback
        print("Full traceback:", flush=True)
        traceback.print_exc()
        print("=== END ERROR ===", flush=True)
        return jsonify({'success': False, 'error': f"{type(e).__name__}: {str(e)}"}), 500



@invoice_bp.route('/api/approve-transactions', methods=['POST'])
@cognito_required(required_permissions=['transactions_create'])
def approve_transactions(user_email, user_roles):
    """Save approved transactions to database"""
    from transaction_logic import TransactionLogic
    
    try:
        transaction_logic = TransactionLogic(test_mode=flag)
        data = request.get_json()
        transactions = data.get('transactions', [])
        
        saved_transactions = transaction_logic.save_approved_transactions(transactions)
        
        return jsonify({
            'success': True,
            'savedTransactions': saved_transactions,
            'message': f'Successfully saved {len(saved_transactions)} transactions'
        })
    except Exception as e:
        print(f"Approval error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500
