from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from config import Config
from pdf_processor import PDFProcessor
from transaction_logic import TransactionLogic
from google_drive_service import GoogleDriveService
from banking_processor import BankingProcessor
from str_processor import STRProcessor
from str_database import STRDatabase
from database import DatabaseManager
from btw_processor import BTWProcessor
from pdf_validation import PDFValidator
from reporting_routes import reporting_bp
from actuals_routes import actuals_bp
from bnb_routes import bnb_bp
from str_channel_routes import str_channel_bp
from str_invoice_routes import str_invoice_bp
from xlsx_export import XLSXExportProcessor
from route_validator import check_route_conflicts
import os
from datetime import datetime
from werkzeug.utils import secure_filename

# Create Flask app without static folder to prevent route conflicts
app = Flask(__name__, static_folder=None)
build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')

# Register API blueprints IMMEDIATELY after app creation
app.register_blueprint(reporting_bp, url_prefix='/api/reports')
app.register_blueprint(actuals_bp, url_prefix='/api/reports')
app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
app.register_blueprint(str_channel_bp, url_prefix='/api/str-channel')
app.register_blueprint(str_invoice_bp, url_prefix='/api/str-invoice')

CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:3000", "http://127.0.0.1:5000"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# In-memory cache for uploaded files to prevent duplicates during session
upload_cache = {}

# MODE CONFIGURATION
# Set flag = True for TEST mode (uses mutaties_test table, local storage)
# Set flag = False for PRODUCTION mode (uses mutaties table, Google Drive)
flag = False

config = Config(test_mode=flag)
processor = PDFProcessor(test_mode=flag)
transaction_logic = TransactionLogic(test_mode=flag)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'csv', 'mhtml', 'eml'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Serve static files
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files from React build"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    static_folder = os.path.join(build_folder, 'static')
    
    # Handle nested paths like css/main.css or js/main.js
    if '/' in filename:
        return send_from_directory(static_folder, filename)
    else:
        return send_from_directory(static_folder, filename)

@app.route('/manifest.json')
def serve_manifest():
    """Serve React manifest.json"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'manifest.json')

@app.route('/favicon.ico')
def serve_favicon():
    """Serve React favicon"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'favicon.ico')

@app.route('/logo192.png')
def serve_logo192():
    """Serve React logo192.png"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'logo192.png')

@app.route('/logo512.png')
def serve_logo512():
    """Serve React logo512.png"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'logo512.png')



# Serve React build files
@app.route('/')
def serve_index():
    """Serve React index.html"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    if not os.path.exists(build_folder):
        return jsonify({'error': 'Frontend not built'}), 404
    return send_from_directory(build_folder, 'index.html')

@app.errorhandler(404)
def handle_404(e):
    """Handle 404 errors by serving React app for non-API routes"""
    # For API routes, return JSON error - DO NOT serve HTML
    if request.path.startswith('/api/'):
        print(f"404 API route: {request.path}", flush=True)
        return jsonify({'error': 'API endpoint not found', 'path': request.path}), 404
    
    # Only serve React app for non-API routes
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    if not os.path.exists(build_folder):
        return jsonify({'error': 'Frontend not built'}), 404
    return send_from_directory(build_folder, 'index.html')

@app.route('/api/folders', methods=['GET'])
def get_folders():
    """Return available vendor folders with optional regex filtering"""
    try:
        regex_pattern = request.args.get('regex')
        print(f"get_folders called, flag={flag}, regex={regex_pattern}", flush=True)
        
        if flag:  # Test mode - use local folders
            folders = list(config.vendor_folders.values())
            print(f"Test mode: returning {len(folders)} local folders", flush=True)
        else:  # Production mode - use Google Drive folders
            try:
                print("Production mode: fetching Google Drive folders", flush=True)
                drive_service = GoogleDriveService()
                drive_folders = drive_service.list_subfolders()
                folders = [folder['name'] for folder in drive_folders]
                print(f"Google Drive: found {len(folders)} folders", flush=True)
            except Exception as e:
                print(f"Google Drive error: {e}", flush=True)
                import traceback
                traceback.print_exc()
                # Fallback to local folders if Google Drive fails
                folders = list(config.vendor_folders.values())
                print(f"Fallback: returning {len(folders)} local folders", flush=True)
        
        # Apply regex filter if provided
        if regex_pattern:
            import re
            try:
                compiled_regex = re.compile(regex_pattern, re.IGNORECASE)
                filtered_folders = [folder for folder in folders if compiled_regex.search(folder)]
                print(f"Regex '{regex_pattern}' filtered {len(folders)} folders to {len(filtered_folders)}", flush=True)
                folders = filtered_folders
            except re.error as e:
                print(f"Invalid regex pattern '{regex_pattern}': {e}", flush=True)
                return jsonify({'error': f'Invalid regex pattern: {e}'}), 400
        
        return jsonify(folders)
    except Exception as e:
        print(f"Error in get_folders: {e}", flush=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/test', methods=['GET'])
def test():
    """Test endpoint"""
    print("Test endpoint called", flush=True)
    return jsonify({'status': 'Server is working'})

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get environment status"""
    use_test = os.getenv('TEST_MODE', 'false').lower() == 'true'
    db_name = os.getenv('TEST_DB_NAME', 'testfinance') if use_test else os.getenv('DB_NAME', 'finance')
    folder_name = os.getenv('TEST_FACTUREN_FOLDER_NAME', 'testFacturen') if use_test else os.getenv('FACTUREN_FOLDER_NAME', 'Facturen')
    
    return jsonify({
        'mode': 'Test' if use_test else 'Production',
        'database': db_name,
        'folder': folder_name
    })

@app.route('/api/str/test', methods=['GET'])
def str_test():
    """STR test endpoint"""
    print("STR test endpoint called", flush=True)
    return jsonify({'status': 'STR endpoints working', 'openpyxl_available': True})

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'endpoints': ['str/upload', 'str/scan-files', 'str/process-files', 'str/save', 'str/write-future']})



@app.route('/api/create-folder', methods=['POST'])
def create_folder():
    """Create a new folder in Google Drive"""
    try:
        data = request.get_json()
        folder_name = data.get('folderName')
        if folder_name:
            # Create local folder
            folder_path = config.get_storage_folder(folder_name)
            config.ensure_folder_exists(folder_path)
            
            # Create Google Drive folder in correct parent
            try:
                drive_service = GoogleDriveService()
                use_test = os.getenv('TEST_MODE', 'false').lower() == 'true'
                parent_folder_id = os.getenv('TEST_FACTUREN_FOLDER_ID') if use_test else os.getenv('FACTUREN_FOLDER_ID')
                
                if parent_folder_id:
                    drive_result = drive_service.create_folder(folder_name, parent_folder_id)
                    print(f"Created Google Drive folder: {folder_name} in {'test' if use_test else 'production'} parent", flush=True)
                    return jsonify({'success': True, 'path': folder_path, 'drive_folder': drive_result})
            except Exception as drive_error:
                print(f"Google Drive folder creation failed: {drive_error}", flush=True)
            
            return jsonify({'success': True, 'path': folder_path})
        return jsonify({'success': False, 'error': 'No folder name provided'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload', methods=['POST', 'OPTIONS'])
def upload_file():
    """Upload and process PDF file"""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:3000')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        return response
        
    print("\n*** UPLOAD ENDPOINT CALLED ***", flush=True)
    try:
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
                    # Check cache first
                    cache_key = f"{folder_name}_{filename}"
                    if cache_key in upload_cache:
                        print(f"Using cached file info for {filename}", flush=True)
                        drive_result = upload_cache[cache_key]
                    else:
                        drive_service = GoogleDriveService()
                        drive_folders = drive_service.list_subfolders()
                        print(f"Available Google Drive folders: {[f['name'] for f in drive_folders]}", flush=True)
                        print(f"Test mode: {flag}, looking for folder: {folder_name}", flush=True)
                        
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
                                drive_result = existing_file['file']
                            else:
                                print(f"Uploading new file to Google Drive folder: {folder_name} (ID: {folder_id})", flush=True)
                                drive_result = drive_service.upload_file(temp_path, filename, folder_id)
                            
                            # Cache the result
                            upload_cache[cache_key] = drive_result
                            print(f"Cached file info for {cache_key}", flush=True)
                        
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
            try:
                shutil.move(temp_path, final_path)
                print(f"File moved to: {final_path}", flush=True)
            except Exception as move_error:
                print(f"Error moving file: {move_error}", flush=True)
                # Clean up temp file if move fails
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            
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
    try:
        processor = BankingProcessor(test_mode=flag)
        folder_path = request.args.get('folder', processor.download_folder)
        
        files = processor.get_csv_files(folder_path)
        return jsonify({
            'success': True,
            'files': files,
            'folder': folder_path
        })
    except Exception as e:
        print(f"Banking scan files error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/process-files', methods=['POST'])
def banking_process_files():
    """Process selected CSV files"""
    try:
        data = request.get_json()
        file_paths = data.get('files', [])
        test_mode = data.get('test_mode', True)
        
        processor = BankingProcessor(test_mode=test_mode)
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
        print(f"Banking process files error: {e}", flush=True)
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
        table_name = 'mutaties'  # Always use 'mutaties' table
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
            ref_num = pattern.get('referenceNumber')
            if not ref_num:
                continue
                
            # Escape special regex characters
            escaped_ref = str(ref_num).replace('/', '\\/')
            
            debet_val = pattern.get('debet')
            credit_val = pattern.get('credit')
            
            if debet_val and str(debet_val) < '1300':
                key = f"{pattern.get('administration')}_{debet_val}_{credit_val}"
                if key not in debet_patterns:
                    debet_patterns[key] = {
                        'debet': debet_val,
                        'credit': credit_val,
                        'patterns': []
                    }
                debet_patterns[key]['patterns'].append(escaped_ref)
                
            if credit_val and str(credit_val) < '1300':
                key = f"{pattern.get('administration')}_{debet_val}_{credit_val}"
                if key not in credit_patterns:
                    credit_patterns[key] = {
                        'debet': debet_val,
                        'credit': credit_val,
                        'patterns': []
                    }
                credit_patterns[key]['patterns'].append(escaped_ref)
        
        # Apply patterns to transactions
        import re
        
        for transaction in transactions:
            description = str(transaction.get('TransactionDescription', ''))
            
            # If Credit is empty, try debet patterns
            if not transaction.get('Credit'):
                for pattern_group in debet_patterns.values():
                    if pattern_group['patterns']:
                        pattern_regex = '|'.join(pattern_group['patterns'])
                        try:
                            match = re.search(pattern_regex, description, re.IGNORECASE)
                            if match:
                                transaction['ReferenceNumber'] = match.group(0)
                                transaction['Credit'] = pattern_group['credit']
                                break
                        except re.error:
                            continue
            
            # If Debet is empty, try credit patterns  
            elif not transaction.get('Debet'):
                for pattern_group in credit_patterns.values():
                    if pattern_group['patterns']:
                        pattern_regex = '|'.join(pattern_group['patterns'])
                        try:
                            match = re.search(pattern_regex, description, re.IGNORECASE)
                            if match:
                                transaction['ReferenceNumber'] = match.group(0)
                                transaction['Debet'] = pattern_group['debet']
                                break
                        except re.error:
                            continue
        
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
    try:
        data = request.get_json()
        transactions = data.get('transactions', [])
        test_mode = data.get('test_mode', True)
        
        db = DatabaseManager(test_mode=test_mode)
        table_name = 'mutaties'  # Always use 'mutaties' table
        
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
        print(f"Banking save transactions error: {e}", flush=True)
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
        print(f"Banking lookups error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/mutaties', methods=['GET'])
def banking_mutaties():
    """Get mutaties with filters"""
    try:
        db = DatabaseManager(test_mode=flag)
        table_name = 'mutaties_test' if flag else 'mutaties'
        
        # Get filter parameters
        years = request.args.get('years', str(datetime.now().year)).split(',')
        administration = request.args.get('administration', 'all')
        
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        # Years filter
        if years and years != ['']:
            year_placeholders = ','.join(['%s'] * len(years))
            where_conditions.append(f"YEAR(TransactionDate) IN ({year_placeholders})")
            params.extend(years)
        
        # Administration filter
        if administration != 'all':
            where_conditions.append("Administration = %s")
            params.append(administration)
        
        where_clause = 'WHERE ' + ' AND '.join(where_conditions) if where_conditions else ''
        
        query = f"""
            SELECT ID, TransactionNumber, TransactionDate, TransactionDescription, 
                   TransactionAmount, Debet, Credit, ReferenceNumber, 
                   Ref1, Ref2, Ref3, Ref4, Administration
            FROM {table_name} 
            {where_clause}
            ORDER BY TransactionDate DESC, ID DESC
        """
        cursor.execute(query, params)
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'mutaties': results,
            'count': len(results),
            'table': table_name
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/filter-options', methods=['GET'])
def banking_filter_options():
    """Get filter options for mutaties"""
    try:
        db = DatabaseManager(test_mode=flag)
        table_name = 'mutaties_test' if flag else 'mutaties'
        
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get distinct years
        cursor.execute(f"SELECT DISTINCT YEAR(TransactionDate) as year FROM {table_name} WHERE TransactionDate IS NOT NULL ORDER BY year DESC")
        years = [str(row['year']) for row in cursor.fetchall()]
        
        # Get distinct administrations
        cursor.execute(f"SELECT DISTINCT Administration FROM {table_name} WHERE Administration IS NOT NULL ORDER BY Administration")
        administrations = [row['Administration'] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'years': years,
            'administrations': administrations
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/update-mutatie', methods=['POST'])
def banking_update_mutatie():
    """Update a mutatie record"""
    try:
        data = request.get_json()
        record_id = data.get('ID')
        
        print(f"Update request for ID: {record_id}", flush=True)
        print(f"Data received: {data}", flush=True)
        
        if not record_id:
            return jsonify({'success': False, 'error': 'No ID provided'}), 400
        
        db = DatabaseManager(test_mode=flag)
        table_name = 'mutaties_test' if flag else 'mutaties'
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Update the record
        update_query = f"""
            UPDATE {table_name} SET 
                TransactionNumber = %s,
                TransactionDate = %s,
                TransactionDescription = %s,
                TransactionAmount = %s,
                Debet = %s,
                Credit = %s,
                ReferenceNumber = %s,
                Ref1 = %s,
                Ref2 = %s,
                Ref3 = %s,
                Ref4 = %s,
                Administration = %s
            WHERE ID = %s
        """
        
        # Convert date to proper format
        transaction_date = data.get('TransactionDate')
        if transaction_date and 'GMT' in str(transaction_date):
            from datetime import datetime
            transaction_date = datetime.strptime(transaction_date, '%a, %d %b %Y %H:%M:%S %Z').strftime('%Y-%m-%d')
        
        cursor.execute(update_query, (
            data.get('TransactionNumber'),
            transaction_date,
            data.get('TransactionDescription'),
            data.get('TransactionAmount'),
            data.get('Debet'),
            data.get('Credit'),
            data.get('ReferenceNumber'),
            data.get('Ref1'),
            data.get('Ref2'),
            data.get('Ref3'),
            data.get('Ref4'),
            data.get('Administration'),
            record_id
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Record {record_id} updated successfully'
        })
        
    except Exception as e:
        print(f"Update error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/check-accounts', methods=['GET'])
def banking_check_accounts():
    """Check banking account balances"""
    try:
        processor = BankingProcessor(test_mode=flag)
        end_date = request.args.get('end_date')
        balances = processor.check_banking_accounts(end_date=end_date)
        
        return jsonify({
            'success': True,
            'balances': balances
        })
        
    except Exception as e:
        print(f"Banking check accounts error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/check-sequence', methods=['GET'])
def banking_check_sequence():
    """Check sequence numbers for account"""
    try:
        processor = BankingProcessor(test_mode=flag)
        account_code = request.args.get('account_code')
        administration = request.args.get('administration')
        start_date = request.args.get('start_date', '2025-01-01')
        
        result = processor.check_sequence_numbers(account_code, administration, start_date)
        return jsonify(result)
        
    except Exception as e:
        print(f"Check sequence error: {e}", flush=True)
        import traceback
        traceback.print_exc()
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

# BTW (VAT) Declaration routes
@app.route('/api/btw/generate-report', methods=['POST'])
def btw_generate_report():
    """Generate BTW declaration report"""
    try:
        data = request.get_json()
        administration = data.get('administration')
        year = data.get('year')
        quarter = data.get('quarter')
        
        if not all([administration, year, quarter]):
            return jsonify({
                'success': False, 
                'error': 'Administration, year, and quarter are required'
            }), 400
        
        btw_processor = BTWProcessor(test_mode=flag)
        result = btw_processor.generate_btw_report(administration, year, quarter)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/btw/save-transaction', methods=['POST'])
def btw_save_transaction():
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

@app.route('/api/btw/upload-report', methods=['POST'])
def btw_upload_report():
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




@app.route('/api/reports/aangifte-ib', methods=['GET'])
def aangifte_ib():
    """Get Aangifte IB data grouped by Parent and Aangifte"""
    try:
        db = DatabaseManager(test_mode=flag)
        
        # Get parameters
        year = request.args.get('year')
        administration = request.args.get('administration', 'all')
        
        if not year:
            return jsonify({'success': False, 'error': 'Year is required'}), 400
        
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build WHERE conditions based on VW logic
        # VW = N (Balance): all records up to end of selected year
        # VW = Y (P&L): only records from selected year
        where_conditions = [
            "((VW = 'N' AND TransactionDate <= %s) OR (VW = 'Y' AND jaar = %s))"
        ]
        params = [f"{year}-12-31", year]
        
        if administration != 'all':
            where_conditions.append("Administration LIKE %s")
            params.append(f"{administration}%")
        
        where_clause = ' AND '.join(where_conditions)
        
        # Get summary data grouped by Parent and Aangifte
        summary_query = f"""
            SELECT Parent, Aangifte, SUM(Amount) as Amount
            FROM vw_mutaties 
            WHERE {where_clause}
            GROUP BY Parent, Aangifte
            ORDER BY Parent, Aangifte
        """
        
        cursor.execute(summary_query, params)
        summary_data = cursor.fetchall()
        
        # Get available years
        years_query = "SELECT DISTINCT jaar FROM vw_mutaties WHERE jaar IS NOT NULL ORDER BY jaar DESC"
        cursor.execute(years_query)
        available_years = [str(row['jaar']) for row in cursor.fetchall()]
        
        # Get available administrations for the selected year
        admin_query = "SELECT DISTINCT Administration FROM vw_mutaties WHERE jaar = %s AND Administration IS NOT NULL ORDER BY Administration"
        cursor.execute(admin_query, [year])
        available_administrations = [row['Administration'] for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'data': summary_data,
            'available_years': available_years,
            'available_administrations': available_administrations
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/reports/aangifte-ib-details', methods=['GET'])
def aangifte_ib_details():
    """Get underlying accounts for a specific Parent and Aangifte"""
    try:
        db = DatabaseManager(test_mode=flag)
        
        # Get parameters
        year = request.args.get('year')
        administration = request.args.get('administration', 'all')
        parent = request.args.get('parent')
        aangifte = request.args.get('aangifte')
        
        if not all([year, parent, aangifte]):
            return jsonify({'success': False, 'error': 'Year, parent, and aangifte are required'}), 400
        
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build WHERE conditions based on VW logic
        where_conditions = [
            "((VW = 'N' AND TransactionDate <= %s) OR (VW = 'Y' AND jaar = %s))",
            "Parent = %s", 
            "Aangifte = %s"
        ]
        params = [f"{year}-12-31", year, parent, aangifte]
        
        if administration != 'all':
            where_conditions.append("Administration LIKE %s")
            params.append(f"{administration}%")
        
        where_clause = ' AND '.join(where_conditions)
        
        # Get detailed account data
        details_query = f"""
            SELECT Reknum, AccountName, SUM(Amount) as Amount
            FROM vw_mutaties 
            WHERE {where_clause}
            GROUP BY Reknum, AccountName
            ORDER BY Reknum
        """
        
        cursor.execute(details_query, params)
        details_data = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'data': details_data,
            'parent': parent,
            'aangifte': aangifte
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/reports/aangifte-ib-export', methods=['POST'])
def aangifte_ib_export():
    """Generate HTML export for Aangifte IB report"""
    try:
        data = request.get_json()
        year = data.get('year')
        administration = data.get('administration', 'all')
        report_data = data.get('data', [])
        
        if not year:
            return jsonify({'success': False, 'error': 'Year is required'}), 400
        
        # Calculate totals
        parent_totals = {}
        grand_total = 0
        for row in report_data:
            parent = row['Parent']
            amount = float(row['Amount'])
            if parent not in parent_totals:
                parent_totals[parent] = 0
            parent_totals[parent] += amount
            grand_total += amount
        
        parent4000_total = parent_totals.get('4000', 0)
        parent8000_total = parent_totals.get('8000', 0)
        resultaat = parent4000_total + parent8000_total
        
        # Generate HTML
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Aangifte IB - {year}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        .parent-row {{ background-color: #e6e6e6; font-weight: bold; }}
        .resultaat-positive {{ background-color: #ffcccc; font-weight: bold; }}
        .resultaat-negative {{ background-color: #ccffcc; font-weight: bold; }}
        .grand-total {{ background-color: #ffa500; font-weight: bold; color: white; }}
        .amount {{ text-align: right; }}
        .indent {{ padding-left: 30px; }}
    </style>
</head>
<body>
    <h1>Aangifte Inkomstenbelasting - {year}</h1>
    <p><strong>Administration:</strong> {administration if administration != 'all' else 'All'}</p>
    <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <table>
        <thead>
            <tr>
                <th>Parent</th>
                <th>Aangifte</th>
                <th class="amount">Amount (€)</th>
            </tr>
        </thead>
        <tbody>
"""
        
        # Group data by parent
        grouped = {}
        for row in report_data:
            parent = row['Parent']
            if parent not in grouped:
                grouped[parent] = []
            grouped[parent].append(row)
        
        # Add rows
        for parent, items in sorted(grouped.items()):
            parent_total = sum(float(item['Amount']) for item in items)
            html_content += f'<tr class="parent-row"><td>{parent}</td><td></td><td class="amount">{parent_total:,.2f}</td></tr>'
            
            for item in items:
                amount = float(item['Amount'])
                html_content += f'<tr><td class="indent"></td><td>{item["Aangifte"]}</td><td class="amount">{amount:,.2f}</td></tr>'
        
        # Add resultaat row
        resultaat_class = 'resultaat-positive' if resultaat >= 0 else 'resultaat-negative'
        html_content += f'<tr class="{resultaat_class}"><td>RESULTAAT</td><td></td><td class="amount">{resultaat:,.2f}</td></tr>'
        
        # Add grand total
        html_content += f'<tr class="grand-total"><td>GRAND TOTAL</td><td></td><td class="amount">{grand_total:,.2f}</td></tr>'
        
        html_content += """
        </tbody>
    </table>
</body>
</html>
"""
        
        return jsonify({
            'success': True,
            'html': html_content,
            'filename': f'Aangifte_IB_{administration}_{year}.html'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/reports/aangifte-ib-xlsx-export', methods=['POST'])
def aangifte_ib_xlsx_export():
    """Generate XLSX export for Aangifte IB"""
    try:
        data = request.get_json()
        administrations = data.get('administrations', [])
        years = data.get('years', [])
        
        if not administrations or not years:
            return jsonify({'success': False, 'error': 'Administrations and years are required'}), 400
        
        # Debug: Check available administrations
        db = DatabaseManager(test_mode=flag)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT DISTINCT Administration FROM vw_mutaties WHERE Administration IS NOT NULL ORDER BY Administration")
        available_admins = [row['Administration'] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        xlsx_processor = XLSXExportProcessor(test_mode=flag)
        results = xlsx_processor.generate_xlsx_export(administrations, years)
        
        successful_results = [r for r in results if r['success']]
        
        return jsonify({
            'success': True,
            'results': results,
            'available_administrations': available_admins,
            'message': f'Generated {len(successful_results)} XLSX files out of {len(results)} requested'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# PDF Validation routes
@app.route('/api/pdf/validate-urls-stream', methods=['GET'])
def pdf_validate_urls_stream():
    """Stream PDF validation progress with Server-Sent Events"""
    from flask import Response
    import json
    
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

@app.route('/api/pdf/validate-urls', methods=['GET'])
def pdf_validate_urls():
    """Validate all Google Drive URLs in mutaties table"""
    import json
    
    def generate_progress():
        with app.app_context():
            try:
                validator = PDFValidator(test_mode=flag)
                
                # Parse range parameter
                range_param = request.args.get('range', '1-100')
                start_record, end_record = map(int, range_param.split('-'))
                print(f"Starting validation for range: {range_param}")
                
                # Send initial message
                yield f"data: {json.dumps({'type': 'progress', 'current': 0, 'total': 0, 'ok_count': 0, 'failed_count': 0}, default=str)}\n\n"
                
                # Use the generator method for progress updates
                for progress_data in validator.validate_pdf_urls_with_progress(start_record, end_record):
                    if progress_data.get('validation_results') is not None:
                        # Convert dates to strings for JSON serialization
                        validation_results = progress_data['validation_results']
                        for result in validation_results:
                            if 'record' in result and 'TransactionDate' in result['record']:
                                if result['record']['TransactionDate']:
                                    result['record']['TransactionDate'] = str(result['record']['TransactionDate'])
                        
                        # Final result
                        yield f"data: {json.dumps({'type': 'complete', 'validation_results': validation_results, 'total_records': progress_data['total'], 'ok_count': progress_data['ok_count'], 'failed_count': progress_data['failed_count']}, default=str)}\n\n"
                    else:
                        # Progress update
                        yield f"data: {json.dumps({'type': 'progress', **progress_data}, default=str)}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    # Regular non-streaming response with range support
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

@app.route('/api/pdf/update-record', methods=['POST'])
def pdf_update_record():
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

@app.route('/api/pdf/get-administrations', methods=['GET'])
def pdf_get_administrations():
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

@app.route('/api/pdf/validate-single-url', methods=['GET'])
def pdf_validate_single_url():
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

if __name__ == '__main__':
    print("Starting Flask development server...")
    print("For production, use: waitress-serve --host=127.0.0.1 --port=5000 wsgi:app")
    
    # Validate routes before starting
    if not check_route_conflicts(app):
        print("ERROR: Route conflicts detected. Fix before starting.")
        exit(1)
    
    # Add request logging
    @app.before_request
    def log_request():
        if request.path.startswith('/api/'):
            print(f"API Request: {request.method} {request.path}", flush=True)
    
    app.run(debug=True, port=5000, host='127.0.0.1')