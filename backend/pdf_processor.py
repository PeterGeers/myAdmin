import PyPDF2
import pdfplumber
import re
from datetime import datetime
from vendor_parsers import VendorParsers
from config import Config

class PDFProcessor:
    def __init__(self, test_mode: bool = False):
        self.vendor_parsers = VendorParsers()
        self.config = Config(test_mode=test_mode)
        
    def process_pdf(self, file_path, drive_result, folder_name='Unknown'):
        text_lines = []
        
        # Try PyPDF2 first
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
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
        return None
    
    def _format_vendor_transactions(self, vendor_data, file_data):
        """Format vendor-specific data into standard transaction format"""
        transactions = []
        
        if isinstance(vendor_data, list):  # Multiple transactions (e.g., credit cards)
            for item in vendor_data:
                transactions.append({
                    'date': item['date'],
                    'description': item['description'],
                    'amount': item['amount'],
                    'debet': item['amount'] if item['is_debit'] else 0,
                    'credit': item['amount'] if not item['is_debit'] else 0,
                    'ref': file_data['folder'],
                    'ref3': file_data['url'],
                    'ref4': file_data['name']
                })
        else:  # Single transaction with amounts
            if 'total_amount' in vendor_data:
                transactions.append({
                    'date': vendor_data['date'],
                    'description': vendor_data['description'],
                    'amount': vendor_data['total_amount'],
                    'debet': vendor_data['total_amount'],
                    'credit': 0,
                    'ref': file_data['folder'],
                    'ref3': file_data['url'],
                    'ref4': file_data['name']
                })
            # Only add VAT transaction if VAT amount > 0
            if 'vat_amount' in vendor_data and vendor_data['vat_amount'] > 0:
                transactions.append({
                    'date': vendor_data['date'],
                    'description': f"VAT - {vendor_data['description']}",
                    'amount': vendor_data['vat_amount'],
                    'debet': vendor_data['vat_amount'],
                    'credit': 0,
                    'ref': file_data['folder'],
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