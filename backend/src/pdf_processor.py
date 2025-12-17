from pypdf import PdfReader
import pdfplumber
import re
from datetime import datetime
from typing import Dict, List, Optional
from vendor_parsers import VendorParsers
from config import Config
import os
import subprocess
from PIL import Image
try:
    import pytesseract
    # Configure Tesseract path for Windows
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
except ImportError:
    pytesseract = None

class PDFProcessor:
    def __init__(self, test_mode: bool = False):
        self.vendor_parsers = VendorParsers()
        self.config = Config(test_mode=test_mode)
        
    def process_file(self, file_path, drive_result, folder_name='Unknown'):
        """Process PDF, image, or CSV file"""
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.pdf':
            return self._process_pdf(file_path, drive_result, folder_name)
        elif file_ext in ['.jpg', '.jpeg', '.png']:
            return self._process_image(file_path, drive_result, folder_name)
        elif file_ext == '.csv':
            return self._process_csv(file_path, drive_result, folder_name)
        elif file_ext == '.mhtml':
            return self._process_mhtml(file_path, drive_result, folder_name)
        elif file_ext == '.eml':
            return self._process_eml(file_path, drive_result, folder_name)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")
    
    def process_pdf(self, file_path, drive_result, folder_name='Unknown'):
        """Legacy method for backward compatibility"""
        return self.process_file(file_path, drive_result, folder_name)
    
    def _process_pdf(self, file_path, drive_result, folder_name='Unknown'):
        text_lines = []
        
        # Try PyPDF2 first
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                
                for page in pdf_reader.pages:
                    try:
                        text = page.extract_text()
                        if text.strip():  # Only add if text was extracted
                            text_lines.extend(text.split('\n'))
                    except Exception as e:
                        print(f"PyPDF2 error on page: {e}")
        except Exception as e:
            print(f"PyPDF2 error: {e}")
        
        # If PyPDF2 failed or extracted no text, try pdfplumber
        if not text_lines:
            print("Using pdfplumber as fallback...")
            try:
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            text_lines.extend(text.split('\n'))
                print(f"pdfplumber extracted {len(text_lines)} lines")
            except Exception as e:
                print(f"pdfplumber error: {e}")
                text_lines = [f"[Error reading PDF with both libraries: {str(e)}]"]
        else:
            print(f"PyPDF2 extracted {len(text_lines)} lines")
        
        # Use configured folder structure
        storage_folder = self.config.get_storage_folder(folder_name)
        self.config.ensure_folder_exists(storage_folder)
        
        return {
            'name': drive_result['id'],
            'url': drive_result['url'],
            'txt': '\n'.join(text_lines),
            'folder': storage_folder
        }
    
    def _process_image(self, file_path, drive_result, folder_name='Unknown'):
        """Process image file using AI vision, fallback to OCR"""
        from image_ai_processor import ImageAIProcessor
        
        # Get previous transactions for context
        previous_transactions = []
        try:
            from database import DatabaseManager
            db = DatabaseManager()
            previous_transactions = db.get_previous_transactions(folder_name, limit=3)
        except Exception as e:
            print(f"Could not get previous transactions: {e}")
        
        # Use AI vision processor
        processor = ImageAIProcessor()
        result = processor.process_image(file_path, folder_name, previous_transactions)
        
        # Format as text for compatibility
        text_lines = [
            f"[AI/OCR Extracted Data]",
            f"Date: {result['date']}",
            f"Total Amount: €{result['total_amount']:.2f}",
            f"VAT Amount: €{result['vat_amount']:.2f}",
            f"Description: {result['description']}",
            f"Vendor: {result['vendor']}"
        ]
        
        storage_folder = self.config.get_storage_folder(folder_name)
        self.config.ensure_folder_exists(storage_folder)
        
        return {
            'name': drive_result['id'],
            'url': drive_result['url'],
            'txt': '\n'.join(text_lines),
            'folder': storage_folder,
            'ai_data': result  # Store structured data for direct use
        }
    
    def _process_csv(self, file_path, drive_result, folder_name='Unknown'):
        """Process CSV file (e.g., AirBnB tax files)"""
        import pandas as pd
        text_lines = []
        
        try:
            # Read CSV file
            df = pd.read_csv(file_path)
            print(f"CSV loaded: {len(df)} rows, columns: {list(df.columns)}")
            
            # Convert DataFrame to text representation for processing
            text_lines.append(f"[CSV File: {os.path.basename(file_path)}]")
            text_lines.append(f"[Rows: {len(df)}, Columns: {len(df.columns)}]")
            text_lines.append(f"[Columns: {', '.join(df.columns)}]")
            
            # Add sample data
            if len(df) > 0:
                text_lines.append("[Sample Data:]")
                for i, row in df.head(3).iterrows():
                    text_lines.append(f"Row {i+1}: {dict(row)}")
            
            # Store CSV data for vendor-specific processing
            text_lines.append("[CSV_DATA_START]")
            text_lines.append(df.to_json(orient='records'))
            text_lines.append("[CSV_DATA_END]")
            
            print(f"CSV processed: {len(text_lines)} info lines")
            
        except Exception as e:
            print(f"CSV processing error: {e}")
            text_lines = [f"[Error processing CSV: {str(e)}]"]
        
        # Use configured folder structure
        storage_folder = self.config.get_storage_folder(folder_name)
        self.config.ensure_folder_exists(storage_folder)
        
        return {
            'name': drive_result['id'],
            'url': drive_result['url'],
            'txt': '\n'.join(text_lines),
            'folder': storage_folder
        }
    
    def _process_mhtml(self, file_path, drive_result, folder_name='Unknown'):
        """Process MHTML email file"""
        import html
        import re
        from datetime import datetime
        
        text_lines = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
            
            # Decode HTML entities
            content = html.unescape(content)
            
            # Extract text from HTML content
            text_content = re.sub(r'<[^>]+>', ' ', content)
            
            # Clean up whitespace and split into lines
            lines = [line.strip() for line in text_content.split('\n') if line.strip()]
            
            # Look for delivery date patterns
            delivery_date = None
            for line in lines:
                date_match = re.search(r'bezorging van (\w+dag)\s+(\d{1,2})\s+(\w+)', line, re.IGNORECASE)
                if date_match:
                    day, date_num, month = date_match.groups()
                    month_map = {
                        'januari': '01', 'februari': '02', 'maart': '03', 'april': '04',
                        'mei': '05', 'juni': '06', 'juli': '07', 'augustus': '08',
                        'september': '09', 'oktober': '10', 'november': '11', 'december': '12'
                    }
                    if month.lower() in month_map:
                        current_year = datetime.now().year
                        delivery_date = f"{current_year}-{month_map[month.lower()]}-{date_num.zfill(2)}"
                        break
            
            # Extract amounts
            total_amount = 0
            total_match = re.search(r'<strong>(\d+)</strong>.*?<strong>(\d+)</strong>', content)
            if total_match:
                euros, cents = total_match.groups()
                total_amount = round(float(f"{euros}.{cents}"), 2)
            
            # Create summary
            text_lines.append(f"[MHTML Email: {os.path.basename(file_path)}]")
            if delivery_date:
                text_lines.append(f"[Delivery Date: {delivery_date}]")
            if total_amount > 0:
                text_lines.append(f"[Total Amount: €{total_amount:.2f}]")
            
            text_lines.extend(lines[:50])
            
        except Exception as e:
            text_lines = [f"[Error processing MHTML: {str(e)}]"]
        
        storage_folder = self.config.get_storage_folder(folder_name)
        self.config.ensure_folder_exists(storage_folder)
        
        return {
            'name': drive_result['id'],
            'url': drive_result['url'],
            'txt': '\n'.join(text_lines),
            'folder': storage_folder
        }
    
    def _process_eml(self, file_path, drive_result, folder_name='Unknown'):
        """Process EML email file"""
        import re
        from datetime import datetime
        
        text_lines = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
            
            # Find the plain text part (after Content-Type: text/plain)
            text_match = re.search(r'Content-Type: text/plain.*?\n\n(.*?)(?=--_)', content, re.DOTALL)
            if text_match:
                plain_text = text_match.group(1).strip()
            else:
                # Fallback: look for text between multipart boundaries
                boundary_match = re.search(r'boundary="([^"]+)"', content)
                if boundary_match:
                    boundary = boundary_match.group(1)
                    parts = content.split(f'--{boundary}')
                    for part in parts:
                        if 'Content-Type: text/plain' in part:
                            text_start = part.find('\n\n')
                            if text_start != -1:
                                plain_text = part[text_start+2:].strip()
                                break
                    else:
                        plain_text = content
                else:
                    plain_text = content
            
            # Extract delivery date
            delivery_date = None
            date_match = re.search(r'bezorging van (\w+dag)\s+(\d{1,2})\s+(\w+)\s+(\d{4})', plain_text)
            if date_match:
                day, date_num, month, year = date_match.groups()
                month_map = {
                    'januari': '01', 'februari': '02', 'maart': '03', 'april': '04',
                    'mei': '05', 'juni': '06', 'juli': '07', 'augustus': '08',
                    'september': '09', 'oktober': '10', 'november': '11', 'december': '12'
                }
                if month.lower() in month_map:
                    delivery_date = f"{year}-{month_map[month.lower()]}-{date_num.zfill(2)}"
            
            # Extract total amount
            total_amount = 0
            total_match = re.search(r'Totaal\s*-+\s*([\d.]+)', plain_text)
            if total_match:
                total_amount = round(float(total_match.group(1)), 2)
            
            # Extract order number
            order_match = re.search(r'Order\s+([\d-]+)', plain_text)
            order_number = order_match.group(1) if order_match else None
            
            # Create summary
            text_lines.append(f"[EML Email: {os.path.basename(file_path)}]")
            if delivery_date:
                text_lines.append(f"[Delivery Date: {delivery_date}]")
            if total_amount > 0:
                text_lines.append(f"[Total Amount: €{total_amount:.2f}]")
            if order_number:
                text_lines.append(f"[Order Number: {order_number}]")
            
            # Add plain text content (clean lines only)
            plain_lines = [line.strip() for line in plain_text.split('\n') if line.strip()]
            text_lines.extend(plain_lines)
            
        except Exception as e:
            text_lines = [f"[Error processing EML: {str(e)}]"]
        
        storage_folder = self.config.get_storage_folder(folder_name)
        self.config.ensure_folder_exists(storage_folder)
        
        return {
            'name': drive_result['id'],
            'url': drive_result['url'],
            'txt': '\n'.join(text_lines),
            'folder': storage_folder
        }
    
    def extract_transactions(self, file_data):
        lines = file_data['txt'].split('\n')
        folder_name = file_data['folder'].lower()
        
        # If image was processed with AI, use that data directly
        if 'ai_data' in file_data:
            print("Using AI-extracted data from image")
            return self._format_vendor_transactions(file_data['ai_data'], file_data)
        
        # Try vendor-specific parser first
        vendor_data = self._parse_vendor_specific(lines, folder_name)
        if vendor_data:
            return self._format_vendor_transactions(vendor_data, file_data)
        
        # Fallback to generic parsing
        return self._generic_parse(lines, file_data)
    
    def _parse_vendor_specific(self, lines, folder_name):
        """Parse using AI or fallback to vendor-specific logic"""
        # Try AI extraction first
        try:
            from ai_extractor import AIExtractor
            ai_extractor = AIExtractor()
            
            # Get previous transactions for this vendor
            previous_transactions = []
            try:
                from database import DatabaseManager
                db = DatabaseManager()
                previous_transactions = db.get_previous_transactions(folder_name, limit=3)
                print(f"Found {len(previous_transactions)} previous transactions for reference")
            except Exception as e:
                print(f"Could not get previous transactions: {e}")
            
            # Convert lines to text
            text_content = '\n'.join(lines)
            
            print(f"Starting AI extraction for {folder_name}...", flush=True)
            # Use AI to extract data with previous transaction context
            ai_result = ai_extractor.extract_invoice_data(text_content, folder_name, previous_transactions)
            
            if ai_result and ai_result['total_amount'] > 0:
                print(f"AI extraction successful for {folder_name}: €{ai_result['total_amount']}", flush=True)
                return ai_result
            else:
                print(f"AI extraction returned no valid amount, using traditional parser for {folder_name}", flush=True)
        except Exception as e:
            print(f"AI extraction error: {e}, falling back to traditional parser", flush=True)
        
        # Fallback to traditional parsers
        if 'action' in folder_name:
            return self.vendor_parsers.parse_action(lines)
        elif 'mastercard' in folder_name:
            return self.vendor_parsers.parse_mastercard(lines)
        elif 'visa' in folder_name:
            return self.vendor_parsers.parse_visa(lines)
        elif 'bol' in folder_name:
            return self.vendor_parsers.parse_bolcom(lines)
        elif 'picnic' in folder_name:
            return self.vendor_parsers.parse_picnic(lines)
        elif 'netflix' in folder_name:
            return self.vendor_parsers.parse_netflix(lines)
        elif 'temu' in folder_name:
            return self.vendor_parsers.parse_temu(lines)
        elif 'avance' in folder_name:
            return self.vendor_parsers.parse_avance(lines)
        elif 'booking' in folder_name:
            return self.vendor_parsers.parse_booking(lines)
        elif 'ziggo' in folder_name:
            return self.vendor_parsers.parse_ziggo(lines)
        elif 'coursera' in folder_name:
            return self.vendor_parsers.parse_coursera(lines)
        elif 'btw' in folder_name:
            print(f"BTW: Calling BTW parser for folder: {folder_name}", flush=True)
            return self.vendor_parsers.parse_btw(lines)
        elif 'vodafone' in folder_name:
            return self.vendor_parsers.parse_vodafone(lines)
        elif 'kuwait' in folder_name.lower():
            return self.vendor_parsers.parse_kuwait(lines)
        elif 'amazon' in folder_name.lower():
            return self.vendor_parsers.parse_amazon(lines)
        elif 'google' in folder_name.lower():
            return self.vendor_parsers.parse_google(lines)
        elif 'vandenheuvelhoveniers' in folder_name.lower():
            return self.vendor_parsers.parse_vandenheuvelhoveniers(lines)
        elif 'guesty' in folder_name.lower():
            return self.vendor_parsers.parse_guesty(lines)
        elif 'gamma' in folder_name.lower():
            return self.vendor_parsers.parse_gamma(lines)
        elif 'airbnb' in folder_name.lower():
            return self.vendor_parsers.parse_airbnb_csv(lines)
        return None
    
    def _format_vendor_transactions(self, vendor_data, file_data):
        """Format vendor-specific data into standard transaction format"""
        transactions = []
        
        # Get reference number from folder name
        folder_name = file_data['folder'].split('/')[-1] if '/' in file_data['folder'] else file_data['folder']
        reference_number = folder_name.replace('testFacturen/', '').replace('Facturen/', '')
        
        # Get last transactions to copy debit/credit accounts like R script
        try:
            from database import DatabaseManager
            db = DatabaseManager()
            last_transactions = db.get_last_transactions(reference_number)
            # Use first transaction for main amount, second for VAT (like R script df[1] and df[2])
            main_debet = last_transactions[0]['Debet'] if last_transactions else '4000'
            main_credit = last_transactions[0]['Credit'] if last_transactions else '1300'
            vat_debet = last_transactions[1]['Debet'] if len(last_transactions) > 1 else '2010'
            vat_credit = last_transactions[1]['Credit'] if len(last_transactions) > 1 else main_debet
        except Exception as e:
            print(f"Error getting last transactions: {e}")
            main_debet, main_credit = '4000', '1300'
            vat_debet, vat_credit = '2010', '4000'
        
        if isinstance(vendor_data, list):  # Multiple transactions (e.g., credit cards)
            for item in vendor_data:
                transactions.append({
                    'date': item['date'],
                    'description': item['description'],
                    'amount': item['amount'],
                    'debet': main_debet,
                    'credit': main_credit,
                    'ref': file_data['folder'],
                    'ref1': None,
                    'ref2': None,
                    'ref3': file_data['url'],
                    'ref4': file_data['name']
                })
        else:  # Single transaction with amounts
            if 'total_amount' in vendor_data:
                transactions.append({
                    'date': vendor_data['date'],
                    'description': vendor_data['description'],
                    'amount': vendor_data['total_amount'],
                    'debet': main_debet,
                    'credit': main_credit,
                    'ref': file_data['folder'],
                    'ref1': None,
                    'ref2': None,
                    'ref3': file_data['url'],
                    'ref4': file_data['name']
                })
            # Only add VAT transaction if VAT amount > 0
            if 'vat_amount' in vendor_data and vendor_data['vat_amount'] > 0:
                transactions.append({
                    'date': vendor_data['date'],
                    'description': f"VAT - {vendor_data['description']}",
                    'amount': vendor_data['vat_amount'],
                    'debet': vat_debet,
                    'credit': vat_credit,
                    'ref': file_data['folder'],
                    'ref1': None,
                    'ref2': None,
                    'ref3': file_data['url'],
                    'ref4': file_data['name']
                })
        
        # Perform duplicate detection after data extraction but before database insertion
        # This integrates with existing workflow while maintaining compatibility
        try:
            duplicate_info = self._check_for_duplicates(transactions, reference_number, file_data)
            if duplicate_info and duplicate_info.get('has_duplicates', False):
                # Add duplicate information to transactions for frontend handling
                for transaction in transactions:
                    transaction['duplicate_info'] = duplicate_info
                print(f"Duplicate detected for {reference_number}: {duplicate_info['duplicate_count']} matches found")
        except Exception as e:
            # Graceful degradation - log error but continue with import
            print(f"Error during duplicate detection: {e}")
            # Continue processing without duplicate detection
        
        return transactions
    
    def _generic_parse(self, lines, file_data):
        """Generic parsing for unknown vendors"""
        transactions = []
        
        date_patterns = [
            r'\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b',
            r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b'
        ]
        amount_patterns = [
            r'[-+]?€?[\d,]+\.\d{2}',
            r'\([\d,]+\.\d{2}\)'
        ]
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 10:
                continue
                
            date_match = None
            for pattern in date_patterns:
                date_match = re.search(pattern, line)
                if date_match:
                    break
                    
            amount_matches = []
            for pattern in amount_patterns:
                amount_matches.extend(re.findall(pattern, line))
            
            if date_match and amount_matches:
                amount_str = amount_matches[-1]
                is_negative = '(' in amount_str or amount_str.startswith('-')
                amount = float(re.sub(r'[^\d.]', '', amount_str))
                
                description = re.sub(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b', '', line)
                description = re.sub(r'[-+]?€?[\d,]+\.\d{2}', '', description)
                description = re.sub(r'\s+', ' ', description).strip()
                
                transactions.append({
                    'date': date_match.group(),
                    'description': description or line[:50],
                    'amount': amount,
                    'debet': amount if is_negative else 0,
                    'credit': amount if not is_negative else 0,
                    'ref': file_data['folder'],
                    'ref1': None,
                    'ref2': None,
                    'ref3': file_data['url'],
                    'ref4': file_data['name']
                })
        
        return transactions
    
    def _check_for_duplicates(self, transactions, reference_number, file_data):
        """
        Check for duplicate transactions using the DuplicateChecker component.
        
        This method integrates duplicate detection into the PDF processing workflow
        by checking each transaction against existing database records.
        
        Args:
            transactions: List of formatted transaction dictionaries
            reference_number: The reference number (folder name) for the transactions
            file_data: File data containing URL and other metadata
        
        Returns:
            Dictionary containing duplicate information or None if no duplicates found
        
        Requirements: 5.1, 5.3, 5.4
        """
        if not transactions:
            return None
        
        try:
            from duplicate_checker import DuplicateChecker
            from database import DatabaseManager
            
            # Initialize duplicate checker with database manager
            db = DatabaseManager()
            duplicate_checker = DuplicateChecker(db)
            
            # Check the main transaction (first one) for duplicates
            # This follows the pattern of checking the primary transaction amount
            main_transaction = transactions[0]
            
            # Prepare transaction data for duplicate checking
            transaction_date = main_transaction['date']
            transaction_amount = float(main_transaction['amount'])
            
            # Normalize date format to YYYY-MM-DD if needed
            if '/' in transaction_date:
                # Convert DD/MM/YYYY or MM/DD/YYYY to YYYY-MM-DD
                date_parts = transaction_date.split('/')
                if len(date_parts) == 3:
                    # Assume DD/MM/YYYY format (European)
                    day, month, year = date_parts
                    transaction_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            elif '-' in transaction_date and len(transaction_date.split('-')[0]) == 2:
                # Convert DD-MM-YYYY to YYYY-MM-DD
                date_parts = transaction_date.split('-')
                if len(date_parts) == 3:
                    day, month, year = date_parts
                    transaction_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
            # Check for duplicates using the DuplicateChecker
            duplicates = duplicate_checker.check_for_duplicates(
                reference_number=reference_number,
                transaction_date=transaction_date,
                transaction_amount=transaction_amount
            )
            
            if duplicates:
                # Format duplicate information for frontend
                duplicate_info = duplicate_checker.format_duplicate_info(duplicates)
                
                # Add new transaction data for comparison and decision logging
                duplicate_info['new_transaction'] = {
                    'ReferenceNumber': reference_number,
                    'TransactionDate': transaction_date,
                    'TransactionAmount': transaction_amount,
                    'TransactionDescription': main_transaction['description'],
                    'Debet': main_transaction['debet'],
                    'Credit': main_transaction['credit'],
                    'Ref3': file_data['url'],  # File URL for cleanup decisions
                    'Ref4': file_data['name']  # File ID
                }
                
                return duplicate_info
            
            return None
            
        except ImportError as e:
            print(f"Duplicate checker not available: {e}")
            return None
        except Exception as e:
            print(f"Error during duplicate detection: {e}")
            return None
    
    def handle_duplicate_decision(
        self,
        decision: str,
        duplicate_info: Dict,
        transactions: List[Dict],
        file_data: Dict,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict:
        """
        Handle user decision regarding duplicate transactions with comprehensive error handling.
        
        This method processes the user's decision to either continue with the duplicate
        import or cancel it, implementing robust error handling and recovery mechanisms.
        
        Args:
            decision: User decision ('continue' or 'cancel')
            duplicate_info: Information about the duplicate transaction(s)
            transactions: List of formatted transaction dictionaries
            file_data: File data containing URL and metadata
            user_id: Optional user identifier for audit purposes
            session_id: Optional session identifier for tracking
        
        Returns:
            Dictionary containing the result of the decision processing with error details
        
        Requirements: 3.1, 3.3, 4.1, 4.5, 6.1, 6.2, 6.3
        """
        # Input validation with detailed error messages
        validation_result = self._validate_duplicate_decision_inputs(
            decision, duplicate_info, transactions, file_data
        )
        if not validation_result['valid']:
            return validation_result['error_response']
        
        # Initialize error tracking
        errors = []
        warnings = []
        
        try:
            # Component initialization with error handling
            components = self._initialize_duplicate_components()
            if not components['success']:
                return self._create_error_response(
                    'component_initialization_failed',
                    components['error'],
                    errors=['Failed to initialize required components'],
                    user_message='System components unavailable. Please try again later.'
                )
            
            db = components['db']
            duplicate_checker = components['duplicate_checker']
            file_cleanup_manager = components['file_cleanup_manager']
            
            # Audit logging with error handling
            audit_result = self._log_duplicate_decision_with_retry(
                duplicate_checker, decision, duplicate_info, user_id, session_id
            )
            if not audit_result['success']:
                warnings.append(f"Audit logging failed: {audit_result['error']}")
            
            # Process decision with comprehensive error handling
            if decision == 'continue':
                return self._handle_continue_decision_enhanced(
                    duplicate_info, transactions, file_data, 
                    audit_result['success'], errors, warnings
                )
            elif decision == 'cancel':
                return self._handle_cancel_decision_enhanced(
                    duplicate_info, transactions, file_data, file_cleanup_manager,
                    audit_result['success'], errors, warnings
                )
            else:
                return self._create_error_response(
                    'invalid_decision',
                    f'Invalid decision: {decision}',
                    errors=[f'Decision must be "continue" or "cancel", got: {decision}'],
                    user_message='Invalid action selected. Please choose Continue or Cancel.'
                )
                
        except ImportError as e:
            error_msg = f"Required modules not available: {str(e)}"
            return self._create_error_response(
                'import_error', error_msg,
                errors=[error_msg],
                user_message='System components not available. Please contact support.'
            )
        except Exception as e:
            error_msg = f"Unexpected error in duplicate decision handling: {str(e)}"
            print(error_msg)
            return self._create_error_response(
                'unexpected_error', error_msg,
                errors=[error_msg],
                user_message='An unexpected error occurred. Please try again or contact support.'
            )
    
    def _handle_continue_decision(
        self,
        duplicate_info: Dict,
        transactions: List[Dict],
        file_data: Dict,
        log_success: bool
    ) -> Dict:
        """
        Handle the "Continue" decision for duplicate imports.
        
        When user chooses to continue, process the transaction normally while
        maintaining all existing transaction formatting and database insertion logic.
        
        Args:
            duplicate_info: Information about the duplicate transaction(s)
            transactions: List of formatted transaction dictionaries
            file_data: File data containing URL and metadata
            log_success: Whether audit logging was successful
        
        Returns:
            Dictionary containing the result of continue processing
        
        Requirements: 3.1, 3.3
        """
        try:
            # Remove duplicate_info from transactions to prevent it from being stored
            clean_transactions = []
            for transaction in transactions:
                clean_transaction = {k: v for k, v in transaction.items() if k != 'duplicate_info'}
                clean_transactions.append(clean_transaction)
            
            # Preserve all existing file references and storage locations
            # The transactions already contain the correct file URLs and storage paths
            
            message_parts = [
                f"Duplicate import approved. Processing {len(clean_transactions)} transaction(s)."
            ]
            
            if not log_success:
                message_parts.append("Note: Audit logging may have failed.")
            
            return {
                'success': True,
                'action_taken': 'continue',
                'transactions': clean_transactions,
                'cleanup_performed': False,
                'message': ' '.join(message_parts)
            }
            
        except Exception as e:
            print(f"Error in continue decision handling: {e}")
            return {
                'success': False,
                'action_taken': 'continue_error',
                'transactions': [],
                'cleanup_performed': False,
                'message': f'Error processing continue decision: {str(e)}'
            }
    
    def _handle_cancel_decision(
        self,
        duplicate_info: Dict,
        transactions: List[Dict],
        file_data: Dict,
        file_cleanup_manager: 'FileCleanupManager',
        log_success: bool
    ) -> Dict:
        """
        Handle the "Cancel" decision for duplicate imports.
        
        When user chooses to cancel, perform appropriate file cleanup based on
        URL comparison and return user to pre-import state.
        
        Args:
            duplicate_info: Information about the duplicate transaction(s)
            transactions: List of formatted transaction dictionaries
            file_data: File data containing URL and metadata
            file_cleanup_manager: FileCleanupManager instance for cleanup operations
            log_success: Whether audit logging was successful
        
        Returns:
            Dictionary containing the result of cancel processing
        
        Requirements: 4.1, 4.5
        """
        try:
            cleanup_performed = False
            cleanup_details = []
            
            # Get URLs for comparison
            new_file_url = file_data.get('url', '')
            new_file_id = file_data.get('name', '')
            
            # Check existing transactions for file URLs
            existing_transactions = duplicate_info.get('existing_transactions', [])
            
            if existing_transactions:
                existing_file_url = existing_transactions[0].get('ref3', '')
                
                # Determine if file cleanup is needed based on URL comparison
                should_cleanup = file_cleanup_manager.should_cleanup_file(
                    new_file_url, existing_file_url
                )
                
                if should_cleanup:
                    # URLs are different, cleanup the new file
                    cleanup_success = file_cleanup_manager.cleanup_uploaded_file(
                        new_file_url, new_file_id
                    )
                    
                    if cleanup_success:
                        cleanup_performed = True
                        cleanup_details.append("New file removed successfully.")
                    else:
                        cleanup_details.append("File cleanup attempted but may have failed.")
                else:
                    # URLs are the same, no cleanup needed
                    cleanup_details.append("File URLs match - no cleanup performed.")
            else:
                # No existing transactions found, cleanup the new file
                cleanup_success = file_cleanup_manager.cleanup_uploaded_file(
                    new_file_url, new_file_id
                )
                
                if cleanup_success:
                    cleanup_performed = True
                    cleanup_details.append("New file removed successfully.")
                else:
                    cleanup_details.append("File cleanup attempted but may have failed.")
            
            # Build result message
            message_parts = ["Duplicate import cancelled."]
            message_parts.extend(cleanup_details)
            
            if not log_success:
                message_parts.append("Note: Audit logging may have failed.")
            
            return {
                'success': True,
                'action_taken': 'cancel',
                'transactions': [],  # No transactions to process
                'cleanup_performed': cleanup_performed,
                'message': ' '.join(message_parts)
            }
            
        except Exception as e:
            print(f"Error in cancel decision handling: {e}")
            return {
                'success': False,
                'action_taken': 'cancel_error',
                'transactions': [],
                'cleanup_performed': False,
                'message': f'Error processing cancel decision: {str(e)}'
            }
    
    def _validate_duplicate_decision_inputs(
        self, 
        decision: str, 
        duplicate_info: Dict, 
        transactions: List[Dict], 
        file_data: Dict
    ) -> Dict:
        """
        Validate inputs for duplicate decision handling with comprehensive error messages.
        
        Args:
            decision: User decision to validate
            duplicate_info: Duplicate information to validate
            transactions: Transaction list to validate
            file_data: File data to validate
        
        Returns:
            Dictionary with validation result and error response if invalid
        """
        try:
            # Validate decision parameter
            if not decision or not isinstance(decision, str):
                return {
                    'valid': False,
                    'error_response': self._create_error_response(
                        'invalid_decision_parameter',
                        'Decision parameter is required and must be a string',
                        errors=['Decision parameter missing or invalid type'],
                        user_message='Invalid action selected. Please choose Continue or Cancel.'
                    )
                }
            
            decision = decision.strip().lower()
            if decision not in ['continue', 'cancel']:
                return {
                    'valid': False,
                    'error_response': self._create_error_response(
                        'invalid_decision_value',
                        f'Invalid decision value: {decision}',
                        errors=[f'Decision must be "continue" or "cancel", got: {decision}'],
                        user_message='Invalid action selected. Please choose Continue or Cancel.'
                    )
                }
            
            # Validate duplicate_info parameter
            if not duplicate_info or not isinstance(duplicate_info, dict):
                return {
                    'valid': False,
                    'error_response': self._create_error_response(
                        'invalid_duplicate_info',
                        'Duplicate info parameter is required and must be a dictionary',
                        errors=['Duplicate info parameter missing or invalid type'],
                        user_message='Invalid duplicate information. Please refresh and try again.'
                    )
                }
            
            # Validate transactions parameter
            if not transactions or not isinstance(transactions, list):
                return {
                    'valid': False,
                    'error_response': self._create_error_response(
                        'invalid_transactions',
                        'Transactions parameter is required and must be a list',
                        errors=['Transactions parameter missing or invalid type'],
                        user_message='Invalid transaction data. Please refresh and try again.'
                    )
                }
            
            # Validate file_data parameter
            if not file_data or not isinstance(file_data, dict):
                return {
                    'valid': False,
                    'error_response': self._create_error_response(
                        'invalid_file_data',
                        'File data parameter is required and must be a dictionary',
                        errors=['File data parameter missing or invalid type'],
                        user_message='Invalid file information. Please refresh and try again.'
                    )
                }
            
            # Validate required fields in file_data
            required_file_fields = ['url', 'name']
            missing_fields = [field for field in required_file_fields if field not in file_data]
            if missing_fields:
                return {
                    'valid': False,
                    'error_response': self._create_error_response(
                        'missing_file_data_fields',
                        f'Missing required file data fields: {missing_fields}',
                        errors=[f'File data missing required fields: {missing_fields}'],
                        user_message='Incomplete file information. Please refresh and try again.'
                    )
                }
            
            return {'valid': True}
            
        except Exception as e:
            return {
                'valid': False,
                'error_response': self._create_error_response(
                    'validation_error',
                    f'Error during input validation: {str(e)}',
                    errors=[f'Validation error: {str(e)}'],
                    user_message='Error validating input. Please refresh and try again.'
                )
            }
    
    def _initialize_duplicate_components(self) -> Dict:
        """
        Initialize duplicate detection components with comprehensive error handling.
        
        Returns:
            Dictionary containing initialized components or error information
        """
        try:
            # Initialize database manager with connection validation
            try:
                from database import DatabaseManager
                db = DatabaseManager()
                
                # Test database connection
                test_connection = db.get_connection()
                if test_connection:
                    test_connection.close()
                else:
                    raise DatabaseConnectionError("Could not establish database connection")
                    
            except ImportError as e:
                return {
                    'success': False,
                    'error': f'DatabaseManager not available: {str(e)}',
                    'component': 'database_manager'
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Database initialization failed: {str(e)}',
                    'component': 'database_manager'
                }
            
            # Initialize duplicate checker
            try:
                from duplicate_checker import DuplicateChecker
                duplicate_checker = DuplicateChecker(db)
            except ImportError as e:
                return {
                    'success': False,
                    'error': f'DuplicateChecker not available: {str(e)}',
                    'component': 'duplicate_checker'
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'DuplicateChecker initialization failed: {str(e)}',
                    'component': 'duplicate_checker'
                }
            
            # Initialize file cleanup manager
            try:
                from file_cleanup_manager import FileCleanupManager
                file_cleanup_manager = FileCleanupManager()
            except ImportError as e:
                return {
                    'success': False,
                    'error': f'FileCleanupManager not available: {str(e)}',
                    'component': 'file_cleanup_manager'
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'FileCleanupManager initialization failed: {str(e)}',
                    'component': 'file_cleanup_manager'
                }
            
            return {
                'success': True,
                'db': db,
                'duplicate_checker': duplicate_checker,
                'file_cleanup_manager': file_cleanup_manager
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error during component initialization: {str(e)}',
                'component': 'unknown'
            }
    
    def _log_duplicate_decision_with_retry(
        self,
        duplicate_checker: 'DuplicateChecker',
        decision: str,
        duplicate_info: Dict,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict:
        """
        Log duplicate decision with retry logic and comprehensive error handling.
        
        Args:
            duplicate_checker: DuplicateChecker instance
            decision: User decision to log
            duplicate_info: Duplicate information
            user_id: Optional user identifier
            session_id: Optional session identifier
        
        Returns:
            Dictionary containing logging result and error information
        """
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                # Extract new transaction data from duplicate_info
                new_transaction_data = duplicate_info.get('new_transaction', {})
                
                # Attempt to log the decision
                log_success = duplicate_checker.log_duplicate_decision(
                    decision=decision,
                    duplicate_info=duplicate_info,
                    new_transaction_data=new_transaction_data,
                    user_id=user_id,
                    session_id=session_id
                )
                
                if log_success:
                    return {
                        'success': True,
                        'attempts': attempt + 1,
                        'message': f'Decision logged successfully on attempt {attempt + 1}'
                    }
                else:
                    if attempt < max_retries - 1:
                        print(f"Audit logging attempt {attempt + 1} failed, retrying...")
                        import time
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        return {
                            'success': False,
                            'attempts': max_retries,
                            'error': 'All audit logging attempts failed',
                            'error_type': 'audit_logging_failed'
                        }
                        
            except Exception as e:
                error_msg = f"Audit logging attempt {attempt + 1} error: {str(e)}"
                print(error_msg)
                
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    return {
                        'success': False,
                        'attempts': max_retries,
                        'error': error_msg,
                        'error_type': 'audit_logging_exception'
                    }
        
        return {
            'success': False,
            'attempts': max_retries,
            'error': 'Maximum retry attempts exceeded',
            'error_type': 'max_retries_exceeded'
        }
    
    def _handle_continue_decision_enhanced(
        self,
        duplicate_info: Dict,
        transactions: List[Dict],
        file_data: Dict,
        audit_success: bool,
        errors: List[str],
        warnings: List[str]
    ) -> Dict:
        """
        Enhanced continue decision handling with comprehensive error management.
        
        Args:
            duplicate_info: Information about the duplicate transaction(s)
            transactions: List of formatted transaction dictionaries
            file_data: File data containing URL and metadata
            audit_success: Whether audit logging was successful
            errors: List to collect error messages
            warnings: List to collect warning messages
        
        Returns:
            Dictionary containing the result of continue processing with error details
        """
        try:
            # Validate transaction data before processing
            validation_errors = self._validate_transaction_data(transactions)
            if validation_errors:
                errors.extend(validation_errors)
                return self._create_error_response(
                    'transaction_validation_failed',
                    'Transaction data validation failed',
                    errors=errors,
                    warnings=warnings,
                    user_message='Invalid transaction data. Please refresh and try again.'
                )
            
            # Remove duplicate_info from transactions to prevent it from being stored
            clean_transactions = []
            for transaction in transactions:
                try:
                    clean_transaction = {k: v for k, v in transaction.items() if k != 'duplicate_info'}
                    clean_transactions.append(clean_transaction)
                except Exception as e:
                    errors.append(f"Error cleaning transaction data: {str(e)}")
            
            if not clean_transactions and transactions:
                errors.append("Failed to clean transaction data")
                return self._create_error_response(
                    'transaction_cleaning_failed',
                    'Failed to prepare transaction data',
                    errors=errors,
                    warnings=warnings,
                    user_message='Error preparing transaction data. Please try again.'
                )
            
            # Build success message with warnings if applicable
            message_parts = [
                f"Duplicate import approved. Processing {len(clean_transactions)} transaction(s)."
            ]
            
            if not audit_success:
                warnings.append("Audit logging may have failed")
                message_parts.append("Note: Audit logging may have failed.")
            
            if warnings:
                message_parts.append(f"Warnings: {'; '.join(warnings)}")
            
            return {
                'success': True,
                'action_taken': 'continue',
                'transactions': clean_transactions,
                'cleanup_performed': False,
                'message': ' '.join(message_parts),
                'errors': errors,
                'warnings': warnings,
                'audit_logged': audit_success
            }
            
        except Exception as e:
            error_msg = f"Error in enhanced continue decision handling: {str(e)}"
            errors.append(error_msg)
            print(error_msg)
            
            return self._create_error_response(
                'continue_processing_error',
                error_msg,
                errors=errors,
                warnings=warnings,
                user_message='Error processing continue decision. Please try again.'
            )
    
    def _handle_cancel_decision_enhanced(
        self,
        duplicate_info: Dict,
        transactions: List[Dict],
        file_data: Dict,
        file_cleanup_manager: 'FileCleanupManager',
        audit_success: bool,
        errors: List[str],
        warnings: List[str]
    ) -> Dict:
        """
        Enhanced cancel decision handling with comprehensive error management.
        
        Args:
            duplicate_info: Information about the duplicate transaction(s)
            transactions: List of formatted transaction dictionaries
            file_data: File data containing URL and metadata
            file_cleanup_manager: FileCleanupManager instance for cleanup operations
            audit_success: Whether audit logging was successful
            errors: List to collect error messages
            warnings: List to collect warning messages
        
        Returns:
            Dictionary containing the result of cancel processing with error details
        """
        try:
            cleanup_performed = False
            cleanup_details = []
            cleanup_errors = []
            
            # Get URLs for comparison with error handling
            try:
                new_file_url = file_data.get('url', '')
                new_file_id = file_data.get('name', '')
                
                if not new_file_url:
                    warnings.append("No file URL found for cleanup")
                    cleanup_details.append("No file URL available for cleanup.")
                
            except Exception as e:
                error_msg = f"Error extracting file information: {str(e)}"
                errors.append(error_msg)
                cleanup_errors.append(error_msg)
            
            # Check existing transactions for file URLs with error handling
            try:
                existing_transactions = duplicate_info.get('existing_transactions', [])
                
                if existing_transactions and new_file_url:
                    existing_file_url = existing_transactions[0].get('ref3', '')
                    
                    # Determine if file cleanup is needed based on URL comparison
                    try:
                        should_cleanup = file_cleanup_manager.should_cleanup_file(
                            new_file_url, existing_file_url
                        )
                        
                        if should_cleanup:
                            # URLs are different, cleanup the new file
                            try:
                                cleanup_success = file_cleanup_manager.cleanup_uploaded_file(
                                    new_file_url, new_file_id
                                )
                                
                                if cleanup_success:
                                    cleanup_performed = True
                                    cleanup_details.append("New file removed successfully.")
                                else:
                                    warnings.append("File cleanup may have failed")
                                    cleanup_details.append("File cleanup attempted but may have failed.")
                                    
                            except Exception as cleanup_error:
                                error_msg = f"File cleanup error: {str(cleanup_error)}"
                                cleanup_errors.append(error_msg)
                                warnings.append("File cleanup failed")
                                cleanup_details.append("File cleanup failed - manual cleanup may be required.")
                        else:
                            # URLs are the same, no cleanup needed
                            cleanup_details.append("File URLs match - no cleanup performed.")
                            
                    except Exception as comparison_error:
                        error_msg = f"URL comparison error: {str(comparison_error)}"
                        cleanup_errors.append(error_msg)
                        warnings.append("Could not compare file URLs")
                        cleanup_details.append("Could not determine if cleanup is needed.")
                        
                elif new_file_url:
                    # No existing transactions found, cleanup the new file
                    try:
                        cleanup_success = file_cleanup_manager.cleanup_uploaded_file(
                            new_file_url, new_file_id
                        )
                        
                        if cleanup_success:
                            cleanup_performed = True
                            cleanup_details.append("New file removed successfully.")
                        else:
                            warnings.append("File cleanup may have failed")
                            cleanup_details.append("File cleanup attempted but may have failed.")
                            
                    except Exception as cleanup_error:
                        error_msg = f"File cleanup error: {str(cleanup_error)}"
                        cleanup_errors.append(error_msg)
                        warnings.append("File cleanup failed")
                        cleanup_details.append("File cleanup failed - manual cleanup may be required.")
                        
            except Exception as e:
                error_msg = f"Error processing existing transactions: {str(e)}"
                errors.append(error_msg)
                cleanup_errors.append(error_msg)
            
            # Build result message with all details
            message_parts = ["Duplicate import cancelled."]
            message_parts.extend(cleanup_details)
            
            if not audit_success:
                warnings.append("Audit logging may have failed")
                message_parts.append("Note: Audit logging may have failed.")
            
            if cleanup_errors:
                errors.extend(cleanup_errors)
                message_parts.append("Some cleanup operations encountered errors.")
            
            if warnings:
                message_parts.append(f"Warnings: {'; '.join(warnings)}")
            
            return {
                'success': True,
                'action_taken': 'cancel',
                'transactions': [],  # No transactions to process
                'cleanup_performed': cleanup_performed,
                'message': ' '.join(message_parts),
                'errors': errors,
                'warnings': warnings,
                'audit_logged': audit_success,
                'cleanup_details': cleanup_details
            }
            
        except Exception as e:
            error_msg = f"Error in enhanced cancel decision handling: {str(e)}"
            errors.append(error_msg)
            print(error_msg)
            
            return self._create_error_response(
                'cancel_processing_error',
                error_msg,
                errors=errors,
                warnings=warnings,
                user_message='Error processing cancel decision. Please try again.'
            )
    
    def _validate_transaction_data(self, transactions: List[Dict]) -> List[str]:
        """
        Validate transaction data for required fields and proper formatting.
        
        Args:
            transactions: List of transaction dictionaries to validate
        
        Returns:
            List of validation error messages (empty if valid)
        """
        validation_errors = []
        
        if not transactions:
            validation_errors.append("No transactions provided for validation")
            return validation_errors
        
        required_fields = ['date', 'description', 'amount', 'debet', 'credit']
        
        for i, transaction in enumerate(transactions):
            if not isinstance(transaction, dict):
                validation_errors.append(f"Transaction {i+1} is not a dictionary")
                continue
            
            # Check required fields
            missing_fields = [field for field in required_fields if field not in transaction]
            if missing_fields:
                validation_errors.append(f"Transaction {i+1} missing fields: {missing_fields}")
            
            # Validate field types and values
            try:
                if 'amount' in transaction:
                    amount = float(transaction['amount'])
                    if amount <= 0:
                        validation_errors.append(f"Transaction {i+1} has invalid amount: {amount}")
            except (ValueError, TypeError):
                validation_errors.append(f"Transaction {i+1} has invalid amount format")
            
            # Validate date format
            if 'date' in transaction:
                date_str = transaction['date']
                if not date_str or not isinstance(date_str, str):
                    validation_errors.append(f"Transaction {i+1} has invalid date format")
        
        return validation_errors
    
    def _create_error_response(
        self,
        error_code: str,
        error_message: str,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
        user_message: Optional[str] = None
    ) -> Dict:
        """
        Create standardized error response with comprehensive error information.
        
        Args:
            error_code: Unique error code for categorization
            error_message: Detailed error message for logging
            errors: List of specific error messages
            warnings: List of warning messages
            user_message: User-friendly error message
        
        Returns:
            Standardized error response dictionary
        """
        return {
            'success': False,
            'error_code': error_code,
            'error_message': error_message,
            'errors': errors or [],
            'warnings': warnings or [],
            'user_message': user_message or 'An error occurred. Please try again.',
            'timestamp': datetime.now().isoformat(),
            'action_taken': 'error',
            'transactions': [],
            'cleanup_performed': False
        }