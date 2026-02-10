"""
Invoice Service

Handles invoice processing business logic including:
- File upload and validation
- Duplicate detection
- Google Drive integration
- Transaction extraction and preparation

Extracted from app.py during refactoring (Phase 2.1)
"""

import os
from werkzeug.utils import secure_filename
from database import DatabaseManager
from google_drive_service import GoogleDriveService
from pdf_processor import PDFProcessor
from transaction_logic import TransactionLogic


class InvoiceService:
    """Service class for invoice processing operations"""
    
    ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'csv', 'mhtml', 'eml'}
    
    def __init__(self, test_mode=False):
        """
        Initialize InvoiceService
        
        Args:
            test_mode (bool): Whether to run in test mode (uses test database)
        """
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
        self.processor = PDFProcessor(test_mode=test_mode)
        self.transaction_logic = TransactionLogic(test_mode=test_mode)
        self.upload_cache = {}  # Cache for uploaded files to prevent duplicates
    
    def allowed_file(self, filename):
        """
        Check if file extension is allowed
        
        Args:
            filename (str): Name of the file to check
            
        Returns:
            bool: True if file extension is allowed
        """
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS
    
    def check_early_duplicates(self, filename, folder_name, drive_result):
        """
        Check for duplicate files before processing to prevent unnecessary work.
        This is an early check based on filename and folder.
        
        Args:
            filename (str): Name of the file
            folder_name (str): Name of the folder/vendor
            drive_result (dict): Google Drive upload result with 'id' and 'url'
            
        Returns:
            dict: Duplicate check result with keys:
                - has_duplicates (bool): Whether duplicates were found
                - message (str): Description of the result
                - duplicate_info (dict|None): Details about found duplicates
        """
        try:
            # Check if this exact file already exists in the database
            # Look for transactions with the same filename in Ref4 and same folder in ReferenceNumber
            query = """
                SELECT ID, TransactionDate, TransactionAmount, TransactionDescription, Ref3, Ref4
                FROM mutaties 
                WHERE Ref4 = %s 
                AND ReferenceNumber = %s
                AND TransactionDate > (CURDATE() - INTERVAL 6 MONTH)
                ORDER BY ID DESC
                LIMIT 5
            """
            
            results = self.db.execute_query(query, (filename, folder_name), fetch=True)
            
            if results and len(results) > 0:
                # Found potential duplicates
                duplicate_info = {
                    'has_duplicates': True,
                    'duplicate_count': len(results),
                    'existing_transactions': []
                }
                
                for result in results:
                    duplicate_info['existing_transactions'].append({
                        'id': result.get('ID'),
                        'date': str(result.get('TransactionDate', '')),
                        'amount': float(result.get('TransactionAmount', 0)),
                        'description': result.get('TransactionDescription', ''),
                        'file_url': result.get('Ref3', ''),
                        'filename': result.get('Ref4', '')
                    })
                
                return {
                    'has_duplicates': True,
                    'message': f'File "{filename}" already exists in folder "{folder_name}". Found {len(results)} matching transactions.',
                    'duplicate_info': duplicate_info
                }
            
            return {
                'has_duplicates': False,
                'message': 'No duplicates found',
                'duplicate_info': None
            }
            
        except Exception as e:
            print(f"Error in early duplicate check: {e}", flush=True)
            # On error, allow processing to continue (graceful degradation)
            return {
                'has_duplicates': False,
                'message': f'Duplicate check failed: {e}',
                'duplicate_info': None
            }

    
    def upload_to_drive(self, temp_path, filename, folder_name, tenant):
        """
        Upload file to Google Drive
        
        Args:
            temp_path (str): Path to temporary file
            filename (str): Name of the file
            folder_name (str): Name of the folder/vendor
            tenant (str): Tenant/administration name
            
        Returns:
            dict: Drive result with 'id' and 'url'
        """
        if self.test_mode:
            # Test mode - local storage
            return {
                'id': filename,
                'url': f'http://localhost:5000/uploads/{filename}'
            }
        
        # Production mode - Google Drive upload
        try:
            # Check cache first
            cache_key = f"{folder_name}_{filename}"
            if cache_key in self.upload_cache:
                print(f"Using cached file info for {filename}", flush=True)
                return self.upload_cache[cache_key]
            
            print(f"Initializing Google Drive service for tenant: {tenant}", flush=True)
            drive_service = GoogleDriveService(administration=tenant)
            drive_folders = drive_service.list_subfolders()
            
            # Find the folder ID for the selected folder
            folder_id = None
            for folder in drive_folders:
                if folder['name'] == folder_name:
                    folder_id = folder['id']
                    print(f"Found folder: {folder_name} (ID: {folder_id})", flush=True)
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
                self.upload_cache[cache_key] = drive_result
                print(f"Cached file info for {cache_key}", flush=True)
                print(f"File result: {drive_result['url']}", flush=True)
                return drive_result
            else:
                print(f"Folder '{folder_name}' not found in Google Drive folders: {[f['name'] for f in drive_folders]}", flush=True)
                print("Using local storage as fallback", flush=True)
                return {
                    'id': filename,
                    'url': f'http://localhost:5000/uploads/{filename}'
                }
        except Exception as e:
            print(f"Google Drive upload failed for tenant {tenant}: {type(e).__name__}: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            # Fallback to local storage
            return {
                'id': filename,
                'url': f'http://localhost:5000/uploads/{filename}'
            }
    
    def process_invoice_file(self, temp_path, drive_result, folder_name, tenant):
        """
        Process invoice file and extract transaction data
        
        Args:
            temp_path (str): Path to temporary file
            drive_result (dict): Google Drive upload result
            folder_name (str): Name of the folder/vendor
            tenant (str): Tenant/administration name
            
        Returns:
            dict: Processing result with extracted data
        """
        print("Starting file processing...", flush=True)
        result = self.processor.process_file(temp_path, drive_result, folder_name)
        print("File processed, extracting transactions...", flush=True)
        transactions = self.processor.extract_transactions(result)
        print(f"Extracted {len(transactions)} transactions", flush=True)
        
        # Get last transactions for smart defaults
        last_transactions = self.transaction_logic.get_last_transactions(folder_name, tenant)
        prepared_transactions = []
        
        if last_transactions:
            print(f"Found {len(last_transactions)} previous transactions for reference", flush=True)
            
            # Get vendor-specific parsed data
            lines = result['txt'].split('\n')
            vendor_data = self.processor._parse_vendor_specific(lines, folder_name.lower())
            
            # Create new transaction records
            new_data = {
                'folder_name': folder_name,
                'description': f"PDF processed from {drive_result.get('url', 'unknown')}",
                'amount': 0,  # Will be updated from PDF parsing
                'drive_url': drive_result['url'],
                'filename': os.path.basename(temp_path),
                'vendor_data': vendor_data,
                'administration': tenant
            }
            
            prepared_transactions = self.transaction_logic.prepare_new_transactions(
                last_transactions, 
                new_data
            )
            print(f"Prepared {len(prepared_transactions)} new transaction records for approval", flush=True)
        
        # Determine which parser was used
        parser_used = "pdfplumber" if "pdfplumber" in result['txt'] else "PyPDF2"
        
        # Get vendor data
        lines = result['txt'].split('\n')
        vendor_data = self.processor._parse_vendor_specific(lines, folder_name.lower())
        
        return {
            'success': True,
            'folder': result['folder'],
            'extracted_text': result['txt'],
            'vendor_data': vendor_data,
            'transactions': transactions,
            'prepared_transactions': prepared_transactions,
            'template_transactions': last_transactions if last_transactions else [],
            'parser_used': parser_used
        }
    
    def move_file_to_folder(self, temp_path, filename, result_folder):
        """
        Move uploaded file to the correct vendor folder
        
        Args:
            temp_path (str): Path to temporary file
            filename (str): Name of the file
            result_folder (str): Destination folder path
            
        Returns:
            str: Final path of the moved file
        """
        import shutil
        
        if not os.path.exists(result_folder):
            os.makedirs(result_folder, exist_ok=True)
        
        final_path = os.path.join(result_folder, filename)
        
        try:
            shutil.move(temp_path, final_path)
            print(f"File moved to: {final_path}", flush=True)
            return final_path
        except Exception as move_error:
            print(f"Error moving file: {move_error}", flush=True)
            # Clean up temp file if move fails
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
    
    def cleanup_temp_file(self, temp_path):
        """
        Clean up temporary file
        
        Args:
            temp_path (str): Path to temporary file
        """
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print(f"Cleaned up temp file: {temp_path}", flush=True)
            except Exception as e:
                print(f"Error cleaning up temp file: {e}", flush=True)
