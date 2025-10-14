from flask import Flask, jsonify, request
from flask_cors import CORS
from config import Config
from pdf_processor import PDFProcessor
from transaction_logic import TransactionLogic
from google_drive_service import GoogleDriveService
from banking_processor import BankingProcessor
from str_processor import STRProcessor
from str_database import STRDatabase
from database import DatabaseManager
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:3000"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# MODE CONFIGURATION
# Set flag = True for TEST mode (uses mutaties_test table, local storage)
# Set flag = False for PRODUCTION mode (uses mutaties table, Google Drive)
flag = False

config = Config(test_mode=flag)
processor = PDFProcessor(test_mode=flag)
transaction_logic = TransactionLogic(test_mode=flag)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/folders', methods=['GET'])
def get_folders():
    """Return available vendor folders"""
    if flag:  # Test mode - use local folders
        folders = list(config.vendor_folders.values())
    else:  # Production mode - use Google Drive folders
        try:
            drive_service = GoogleDriveService()
            drive_folders = drive_service.list_subfolders()
            folders = [folder['name'] for folder in drive_folders]
        except Exception as e:
            print(f"Google Drive error: {e}", flush=True)
            # Fallback to local folders if Google Drive fails
            folders = list(config.vendor_folders.values())
    
    return jsonify(folders)

@app.route('/api/test', methods=['GET'])
def test():
    """Test endpoint"""
    print("Test endpoint called", flush=True)
    return jsonify({'status': 'Server is working'})

@app.route('/api/str/test', methods=['GET'])
def str_test():
    """STR test endpoint"""
    print("STR test endpoint called", flush=True)
    return jsonify({'status': 'STR endpoints working', 'openpyxl_available': True})

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'endpoints': ['str/upload', 'str/scan-files', 'str/process-files', 'str/save', 'str/write-future']})

@app.route('/api/upload', methods=['OPTIONS'])
def upload_options():
    """Handle preflight OPTIONS request"""
    print("OPTIONS request received", flush=True)
    response = jsonify({'status': 'OK'})
    response.headers.add('Access-Control-Allow-Origin', 'http://localhost:3000')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

@app.route('/api/create-folder', methods=['POST'])
def create_folder():
    """Create a new folder"""
    try:
        data = request.get_json()
        folder_name = data.get('folderName')
        if folder_name:
            folder_path = config.get_storage_folder(folder_name)
            config.ensure_folder_exists(folder_path)
            return jsonify({'success': True, 'path': folder_path})
        return jsonify({'success': False, 'error': 'No folder name provided'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload and process PDF file"""
    print("\n*** UPLOAD ENDPOINT CALLED ***", flush=True)
    try:
        print("=== UPLOAD REQUEST START ===", flush=True)
        print(f"Request method: {request.method}", flush=True)
        print(f"Request files: {list(request.files.keys())}", flush=True)
        print(f"Request form: {dict(request.form)}", flush=True)
        
        if 'file' not in request.files:
            print("ERROR: No file in request", flush=True)
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        folder_name = request.form.get('folderName', 'General')
        print(f"File: {file.filename}, Folder: {folder_name}", flush=True)
        
        if file.filename == '':
            print("ERROR: No file selected", flush=True)
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            temp_path = os.path.join(UPLOAD_FOLDER, filename)
            print(f"Saving file to: {temp_path}", flush=True)
            file.save(temp_path)
            print("File saved successfully", flush=True)
            
            # Upload to Google Drive in production mode
            if flag:  # Test mode - local storage
                drive_result = {
                    'id': filename,
                    'url': f'http://localhost:5000/uploads/{filename}'
                }
            else:  # Production mode - Google Drive upload
                try:
                    drive_service = GoogleDriveService()
                    drive_folders = drive_service.list_subfolders()
                    print(f"Available Google Drive folders: {[f['name'] for f in drive_folders]}", flush=True)
                    
                    # Find the folder ID for the selected folder
                    folder_id = None
                    for folder in drive_folders:
                        print(f"Checking folder: '{folder['name']}' vs '{folder_name}'", flush=True)
                        if folder['name'] == folder_name:
                            folder_id = folder['id']
                            print(f"Found matching folder ID: {folder_id}", flush=True)
                            break
                    
                    if folder_id:
                        # Check if file already exists
                        existing_file = drive_service.check_file_exists(filename, folder_id)
                        
                        if existing_file['exists']:
                            print(f"File {filename} already exists in Google Drive", flush=True)
                            
                            # Option 1: Use existing file
                            use_existing = request.form.get('useExisting', 'false').lower() == 'true'
                            if use_existing:
                                print("Using existing file from Google Drive", flush=True)
                                drive_result = existing_file['file']
                            else:
                                # Option 2: Rename with timestamp
                                from datetime import datetime
                                name, ext = os.path.splitext(filename)
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                new_filename = f"{name}_{timestamp}{ext}"
                                print(f"Renaming file to: {new_filename}", flush=True)
                                
                                drive_result = drive_service.upload_file(temp_path, new_filename, folder_id)
                                filename = new_filename  # Update filename for later use
                        else:
                            print(f"Uploading new file to Google Drive folder: {folder_name} (ID: {folder_id})", flush=True)
                            drive_result = drive_service.upload_file(temp_path, filename, folder_id)
                        
                        print(f"File result: {drive_result['url']}", flush=True)
                    else:
                        print(f"Folder '{folder_name}' not found in Google Drive folders: {[f['name'] for f in drive_folders]}", flush=True)
                        print("Using local storage as fallback", flush=True)
                        drive_result = {
                            'id': filename,
                            'url': f'http://localhost:5000/uploads/{filename}'
                        }
                except Exception as e:
                    print(f"Google Drive upload failed: {type(e).__name__}: {str(e)}", flush=True)
                    import traceback
                    traceback.print_exc()
                    # Fallback to local storage
                    drive_result = {
                        'id': filename,
                        'url': f'http://localhost:5000/uploads/{filename}'
                    }
            
            print("Starting file processing...", flush=True)
            result = processor.process_file(temp_path, drive_result, folder_name)
            print("File processed, extracting transactions...", flush=True)
            transactions = processor.extract_transactions(result)
            print(f"Extracted {len(transactions)} transactions", flush=True)
            
            # Get last transactions for smart defaults
            last_transactions = transaction_logic.get_last_transactions(folder_name)
            if last_transactions:
                print(f"Found {len(last_transactions)} previous transactions for reference", flush=True)
                
                # Get vendor-specific parsed data
                lines = result['txt'].split('\n')
                vendor_data = processor._parse_vendor_specific(lines, folder_name.lower())
                
                # Create new transaction records
                new_data = {
                    'folder_name': folder_name,
                    'description': f"PDF processed from {filename}",
                    'amount': 0,  # Will be updated from PDF parsing
                    'drive_url': drive_result['url'],
                    'filename': filename,
                    'vendor_data': vendor_data  # Pass parsed vendor data
                }
                
                prepared_transactions = transaction_logic.prepare_new_transactions(last_transactions, new_data)
                print(f"Prepared {len(prepared_transactions)} new transaction records for approval", flush=True)
            
            # Move file to the correct vendor folder
            import shutil
            final_folder = result['folder']
            if not os.path.exists(final_folder):
                os.makedirs(final_folder, exist_ok=True)
            final_path = os.path.join(final_folder, filename)
            shutil.move(temp_path, final_path)
            print(f"File moved to: {final_path}", flush=True)
            
            # vendor_data already extracted above
            
            # Determine which parser was used based on extracted text
            parser_used = "pdfplumber" if "pdfplumber" in result['txt'] else "PyPDF2"
            
            return jsonify({
                'success': True,
                'filename': filename,
                'folder': result['folder'],
                'extractedText': result['txt'],
                'vendorData': vendor_data,
                'transactions': transactions,
                'preparedTransactions': prepared_transactions if 'prepared_transactions' in locals() else [],
                'templateTransactions': last_transactions,
                'parserUsed': parser_used
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

@app.errorhandler(500)
def handle_500(e):
    print(f"500 error: {e}")
    return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

@app.route('/api/approve-transactions', methods=['POST'])
def approve_transactions():
    """Save approved transactions to database"""
    try:
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

# Banking processor routes
@app.route('/api/banking/scan-files', methods=['GET'])
def banking_scan_files():
    """Scan download folder for CSV files"""
    processor = BankingProcessor(test_mode=flag)
    folder_path = request.args.get('folder', processor.download_folder)
    
    try:
        files = processor.get_csv_files(folder_path)
        return jsonify({
            'success': True,
            'files': files,
            'folder': folder_path
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/process-files', methods=['POST'])
def banking_process_files():
    """Process selected CSV files"""
    data = request.get_json()
    file_paths = data.get('files', [])
    test_mode = data.get('test_mode', True)
    
    processor = BankingProcessor(test_mode=test_mode)
    
    try:
        df = processor.process_csv_files(file_paths)
        
        if df.empty:
            return jsonify({'success': False, 'error': 'No data found in files'}), 400
        
        records = processor.prepare_for_review(df)
        
        return jsonify({
            'success': True,
            'transactions': records,
            'count': len(records),
            'test_mode': test_mode
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/check-sequences', methods=['POST'])
def banking_check_sequences():
    """Check sequence numbers against database"""
    try:
        data = request.get_json()
        iban = data.get('iban')
        sequences = data.get('sequences', [])
        test_mode = data.get('test_mode', True)
        
        db = DatabaseManager(test_mode=test_mode)
        table_name = 'mutaties_test' if test_mode else 'mutaties'
        existing_sequences = db.get_existing_sequences(iban, table_name)
        
        # Check for duplicates
        duplicates = [seq for seq in sequences if seq in existing_sequences]
        
        return jsonify({
            'success': True,
            'existing_sequences': existing_sequences,
            'duplicates': duplicates
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/apply-patterns', methods=['POST'])
def banking_apply_patterns():
    """Apply pattern matching to predict debet/credit accounts"""
    try:
        data = request.get_json()
        transactions = data.get('transactions', [])
        test_mode = data.get('test_mode', True)
        
        if not transactions:
            return jsonify({'success': False, 'error': 'No transactions provided'}), 400
            
        db = DatabaseManager(test_mode=test_mode)
        administration = transactions[0].get('Administration')
        
        # Get patterns for this administration
        patterns_data = db.get_patterns(administration)
        
        # Build pattern groups
        debet_patterns = {}
        credit_patterns = {}
        
        for pattern in patterns_data:
            ref_num = pattern['referenceNumber']
            if not ref_num:
                continue
                
            # Escape special regex characters
            escaped_ref = ref_num.replace('/', '\\/')
            
            if pattern['debet'] and pattern['debet'] < '1300':
                key = f"{pattern['administration']}_{pattern['debet']}_{pattern['credit']}"
                if key not in debet_patterns:
                    debet_patterns[key] = {
                        'debet': pattern['debet'],
                        'credit': pattern['credit'],
                        'patterns': []
                    }
                debet_patterns[key]['patterns'].append(escaped_ref)
                
            if pattern['credit'] and pattern['credit'] < '1300':
                key = f"{pattern['administration']}_{pattern['debet']}_{pattern['credit']}"
                if key not in credit_patterns:
                    credit_patterns[key] = {
                        'debet': pattern['debet'],
                        'credit': pattern['credit'],
                        'patterns': []
                    }
                credit_patterns[key]['patterns'].append(escaped_ref)
        
        # Apply patterns to transactions
        import re
        
        for transaction in transactions:
            description = transaction.get('TransactionDescription', '')
            
            # If Credit is empty, try debet patterns
            if not transaction.get('Credit'):
                for pattern_group in debet_patterns.values():
                    pattern_regex = '|'.join(pattern_group['patterns'])
                    match = re.search(pattern_regex, description, re.IGNORECASE)
                    if match:
                        transaction['ReferenceNumber'] = match.group(0)
                        transaction['Credit'] = pattern_group['credit']
                        break
            
            # If Debet is empty, try credit patterns  
            elif not transaction.get('Debet'):
                for pattern_group in credit_patterns.values():
                    pattern_regex = '|'.join(pattern_group['patterns'])
                    match = re.search(pattern_regex, description, re.IGNORECASE)
                    if match:
                        transaction['ReferenceNumber'] = match.group(0)
                        transaction['Debet'] = pattern_group['debet']
                        break
        
        return jsonify({
            'success': True,
            'transactions': transactions,
            'patterns_found': len(patterns_data)
        })
        
    except Exception as e:
        print(f"Pattern matching error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/save-transactions', methods=['POST'])
def banking_save_transactions():
    """Save approved transactions to database with duplicate filtering"""
    data = request.get_json()
    transactions = data.get('transactions', [])
    test_mode = data.get('test_mode', True)
    
    try:
        db = DatabaseManager(test_mode=test_mode)
        table_name = 'mutaties_test' if test_mode else 'mutaties'
        
        # Group transactions by IBAN (Ref1)
        ibans = list(set([t.get('Ref1') for t in transactions if t.get('Ref1')]))
        transactions_to_save = []
        
        for iban in ibans:
            # Get existing sequences for this IBAN
            existing_sequences = db.get_existing_sequences(iban, table_name)
            
            # Filter transactions for this IBAN that don't exist
            iban_transactions = [t for t in transactions if t.get('Ref1') == iban]
            new_transactions = [t for t in iban_transactions if t.get('Ref2') not in existing_sequences]
            
            transactions_to_save.extend(new_transactions)
        
        # Save only new transactions
        processor = BankingProcessor(test_mode=test_mode)
        saved_count = processor.save_approved_transactions(transactions_to_save)
        
        total_count = len(transactions)
        duplicate_count = total_count - len(transactions_to_save)
        
        return jsonify({
            'success': True,
            'saved_count': saved_count,
            'total_count': total_count,
            'duplicate_count': duplicate_count,
            'table': table_name,
            'message': f'Saved {saved_count} new transactions, skipped {duplicate_count} duplicates'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/lookups', methods=['GET'])
def banking_lookups():
    """Get mapping data for account codes and descriptions"""
    try:
        db = DatabaseManager(test_mode=flag)
        
        # Get bank account lookups

        bank_accounts = db.get_bank_account_lookups()

        
        # Get recent transactions for account mapping

        recent_transactions = db.get_recent_transactions(limit=100)

        
        # Extract unique account codes and descriptions
        accounts = set()
        descriptions = set()
        
        for tx in recent_transactions:
            if tx.get('Debet'):
                accounts.add(tx['Debet'])
            if tx.get('Credit'):
                accounts.add(tx['Credit'])
            if tx.get('TransactionDescription'):
                descriptions.add(tx['TransactionDescription'])
        
        return jsonify({
            'success': True,
            'accounts': sorted(list(accounts)),
            'descriptions': sorted(list(descriptions)),
            'bank_accounts': bank_accounts
        })
        
    except Exception as e:

        return jsonify({'success': False, 'error': str(e)}), 500

# STR (Short Term Rental) routes
@app.route('/api/str/upload', methods=['POST', 'OPTIONS'])
def str_upload():
    """Upload and process single STR file"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'})
        
    try:

        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        platform = request.form.get('platform', 'airbnb')
        

        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        filename = secure_filename(file.filename)
        temp_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(temp_path)
        

        
        str_processor = STRProcessor(test_mode=flag)

        
        bookings = str_processor.process_str_files([temp_path], platform)

        
        if bookings:
            separated = str_processor.separate_by_status(bookings)
            summary = str_processor.generate_summary(bookings)
        else:
            separated = {'realised': [], 'planned': []}
            summary = {}
        
        os.remove(temp_path)  # Clean up
        
        # Convert numpy types to native Python types for JSON serialization
        def convert_types(obj):
            if hasattr(obj, 'item'):
                return obj.item()
            elif isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(v) for v in obj]
            return obj
        
        response_data = {
            'success': True,
            'realised': convert_types(separated['realised']),
            'planned': convert_types(separated['planned']),
            'already_loaded': convert_types(separated.get('already_loaded', [])),
            'summary': convert_types(summary),
            'platform': platform
        }
        
        return jsonify(response_data)
        
    except Exception as e:

        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/str/scan-files', methods=['GET'])
def str_scan_files():
    """Scan download folder for STR files"""

    str_processor = STRProcessor(test_mode=flag)
    folder_path = request.args.get('folder', str_processor.download_folder)
    
    try:
        files = str_processor.scan_str_files(folder_path)
        return jsonify({
            'success': True,
            'files': files,
            'folder': folder_path
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/str/process-files', methods=['POST'])
def str_process_files():
    """Process selected STR files"""

    data = request.get_json()
    platform = data.get('platform')
    file_paths = data.get('files', [])
    
    str_processor = STRProcessor(test_mode=flag)
    
    try:
        bookings = str_processor.process_str_files(file_paths, platform)
        
        if not bookings:
            return jsonify({'success': False, 'error': 'No bookings found in files'}), 400
        
        # Separate by status like R script
        separated = str_processor.separate_by_status(bookings)
        summary = str_processor.generate_summary(bookings)
        
        return jsonify({
            'success': True,
            'realised': separated['realised'],
            'planned': separated['planned'],
            'summary': summary,
            'platform': platform
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/str/save', methods=['POST'])
def str_save():
    """Save STR bookings to database like R script"""

    try:
        data = request.get_json()
        realised_bookings = data.get('realised', [])
        planned_bookings = data.get('planned', [])
        
        str_db = STRDatabase(test_mode=flag)
        str_processor = STRProcessor(test_mode=flag)
        
        results = {}
        
        # Save realised bookings to bnb table
        if realised_bookings:
            realised_count = str_db.insert_realised_bookings(realised_bookings)
            results['realised_saved'] = realised_count
        
        # Save planned bookings to bnbplanned table (clears table first)
        planned_count = str_db.insert_planned_bookings(planned_bookings)
        results['planned_saved'] = planned_count
        
        # Generate and save future summary to bnbfuture table
        if planned_bookings:
            future_summary = str_processor.generate_future_summary(planned_bookings)
            future_count = str_db.insert_future_summary(future_summary)
            results['future_summary_saved'] = future_count
        
        return jsonify({
            'success': True,
            'results': results,
            'message': f'Processed {len(realised_bookings)} realised, {len(planned_bookings)} planned bookings'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/str/write-future', methods=['POST'])
def str_write_future():
    """Write current BNB planned data to bnbfuture table"""

    try:
        str_db = STRDatabase(test_mode=flag)
        result = str_db.write_bnb_future_summary()
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f"Written {result['inserted']} future records for {result['date']}",
                'summary': result['summary']
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', result.get('message', 'Unknown error'))
            }), 400
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/str/summary', methods=['GET'])
def str_summary():
    """Get STR performance summary"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        str_db = STRDatabase(test_mode=flag)
        summary = str_db.get_str_summary(start_date, end_date)
        
        return jsonify({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



if __name__ == '__main__':
    print("Starting Flask server...")
    app.run(debug=True, port=5000, host='127.0.0.1')