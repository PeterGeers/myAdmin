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