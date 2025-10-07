from flask import Flask, jsonify, request
from flask_cors import CORS
from config import Config
from pdf_processor import PDFProcessor
from transaction_logic import TransactionLogic
from google_drive_service import GoogleDriveService
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
ALLOWED_EXTENSIONS = {'pdf'}

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
            
            print("Starting PDF processing...", flush=True)
            result = processor.process_pdf(temp_path, drive_result, folder_name)
            print("PDF processed, extracting transactions...", flush=True)
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

if __name__ == '__main__':
    print("Starting Flask server...")
    app.run(debug=True, port=5000, host='127.0.0.1')