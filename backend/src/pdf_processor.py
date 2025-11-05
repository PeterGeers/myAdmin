from pypdf import PdfReader
import pdfplumber
import re
from datetime import datetime
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
        """Process image file using OCR"""
        text_lines = []
        
        try:
            # Check if Tesseract is available
            try:
                import subprocess
                subprocess.run([r'C:\Program Files\Tesseract-OCR\tesseract.exe', '--version'], capture_output=True, check=True)
                tesseract_available = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                tesseract_available = False
            
            if tesseract_available:
                # Open image and perform OCR
                image = Image.open(file_path)
                
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Perform OCR
                text = pytesseract.image_to_string(image)
                if text.strip():
                    text_lines.extend(text.split('\n'))
                else:
                    text_lines = ["[No text extracted from image]"]
                    
                print(f"OCR extracted {len(text_lines)} lines from image")
            else:
                # Tesseract not available, provide basic image info
                image = Image.open(file_path)
                text_lines = [
                    f"[Image file processed: {os.path.basename(file_path)}]",
                    f"[Image size: {image.size[0]}x{image.size[1]}]",
                    f"[Image mode: {image.mode}]",
                    "[OCR not available - Tesseract not installed]",
                    "[Manual text extraction required]"
                ]
                print(f"Image processed without OCR: {len(text_lines)} info lines")
            
        except Exception as e:
            print(f"Image processing error: {e}")
            text_lines = [f"[Error processing image: {str(e)}]"]
        
        # Use configured folder structure
        storage_folder = self.config.get_storage_folder(folder_name)
        self.config.ensure_folder_exists(storage_folder)
        
        return {
            'name': drive_result['id'],
            'url': drive_result['url'],
            'txt': '\n'.join(text_lines),
            'folder': storage_folder
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
    
    def extract_transactions(self, file_data):
        lines = file_data['txt'].split('\n')
        folder_name = file_data['folder'].lower()
        
        # Try vendor-specific parser first
        vendor_data = self._parse_vendor_specific(lines, folder_name)
        if vendor_data:
            return self._format_vendor_transactions(vendor_data, file_data)
        
        # Fallback to generic parsing
        return self._generic_parse(lines, file_data)
    
    def _parse_vendor_specific(self, lines, folder_name):
        """Parse using vendor-specific logic"""
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
        
        # If no transactions found, return demo transaction
        if not transactions:
            demo_transaction = {
                'date': '2024-01-01',
                'description': f"Sample transaction from {file_data['folder']}",
                'amount': 100.00,
                'debet': 100.00,
                'credit': 0.00,
                'ref': file_data['folder'],
                'ref3': file_data['url'],
                'ref4': file_data['folder']
            }
            transactions.append(demo_transaction)
        
        return transactions