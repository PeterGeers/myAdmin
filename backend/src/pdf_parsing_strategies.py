"""
PDF/file parsing strategies for different file types.

Extracts text content from PDF, image, CSV, MHTML, and EML files.
Also contains generic line-based parsing for unknown vendors.
"""
from pypdf import PdfReader
import pdfplumber
import re
from datetime import datetime
import os

try:
    from PIL import Image
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
except ImportError:
    pytesseract = None


def process_pdf(file_path, drive_result, config, folder_name='Unknown'):
    """Process PDF file using PyPDF2 with pdfplumber fallback.
    
    Args:
        file_path: Path to the PDF file
        drive_result: Google Drive upload result with id and url
        config: Config instance for storage folder resolution
        folder_name: Vendor/folder name for storage organization
    
    Returns:
        Dictionary with name, url, txt, and folder fields
    """
    text_lines = []

    # Try PyPDF2 first
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PdfReader(file)

            for page in pdf_reader.pages:
                try:
                    text = page.extract_text()
                    if text.strip():
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
    storage_folder = config.get_storage_folder(folder_name)
    config.ensure_folder_exists(storage_folder)

    return {
        'name': drive_result['id'],
        'url': drive_result['url'],
        'txt': '\n'.join(text_lines),
        'folder': storage_folder
    }


def process_image(file_path, drive_result, config, folder_name='Unknown', tenant=None):
    """Process image file using AI vision, fallback to OCR.
    
    Args:
        file_path: Path to the image file
        drive_result: Google Drive upload result with id and url
        config: Config instance for storage folder resolution
        folder_name: Vendor/folder name for storage organization
        tenant: Optional tenant identifier for AI usage tracking
    
    Returns:
        Dictionary with name, url, txt, folder, and ai_data fields
    """
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
    try:
        from database import DatabaseManager
        db_for_tracker = DatabaseManager()
    except Exception:
        db_for_tracker = None
    processor = ImageAIProcessor(db=db_for_tracker, tenant=tenant)
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

    storage_folder = config.get_storage_folder(folder_name)
    config.ensure_folder_exists(storage_folder)

    return {
        'name': drive_result['id'],
        'url': drive_result['url'],
        'txt': '\n'.join(text_lines),
        'folder': storage_folder,
        'ai_data': result
    }


def process_csv(file_path, drive_result, config, folder_name='Unknown'):
    """Process CSV file (e.g., AirBnB tax files).
    
    Args:
        file_path: Path to the CSV file
        drive_result: Google Drive upload result with id and url
        config: Config instance for storage folder resolution
        folder_name: Vendor/folder name for storage organization
    
    Returns:
        Dictionary with name, url, txt, and folder fields
    """
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
    storage_folder = config.get_storage_folder(folder_name)
    config.ensure_folder_exists(storage_folder)

    return {
        'name': drive_result['id'],
        'url': drive_result['url'],
        'txt': '\n'.join(text_lines),
        'folder': storage_folder
    }


def process_mhtml(file_path, drive_result, config, folder_name='Unknown'):
    """Process MHTML email file.
    
    Args:
        file_path: Path to the MHTML file
        drive_result: Google Drive upload result with id and url
        config: Config instance for storage folder resolution
        folder_name: Vendor/folder name for storage organization
    
    Returns:
        Dictionary with name, url, txt, and folder fields
    """
    import html

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

    storage_folder = config.get_storage_folder(folder_name)
    config.ensure_folder_exists(storage_folder)

    return {
        'name': drive_result['id'],
        'url': drive_result['url'],
        'txt': '\n'.join(text_lines),
        'folder': storage_folder
    }


def process_eml(file_path, drive_result, config, folder_name='Unknown'):
    """Process EML email file.
    
    Args:
        file_path: Path to the EML file
        drive_result: Google Drive upload result with id and url
        config: Config instance for storage folder resolution
        folder_name: Vendor/folder name for storage organization
    
    Returns:
        Dictionary with name, url, txt, and folder fields
    """
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

    storage_folder = config.get_storage_folder(folder_name)
    config.ensure_folder_exists(storage_folder)

    return {
        'name': drive_result['id'],
        'url': drive_result['url'],
        'txt': '\n'.join(text_lines),
        'folder': storage_folder
    }


def generic_parse(lines, file_data):
    """Generic parsing for unknown vendors.
    
    Attempts to extract transactions by finding date and amount patterns in text lines.
    
    Args:
        lines: List of text lines to parse
        file_data: File data dictionary with folder, url, and name
    
    Returns:
        List of transaction dictionaries
    """
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
