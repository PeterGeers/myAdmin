"""
PDF/file parsing strategies for different file types.

Extracts text content from PDF, image, CSV, MHTML, and EML files.
Also contains generic line-based parsing for unknown vendors.
"""

import io
import os
import re
import shutil
from datetime import datetime

import pdfplumber
from pypdf import PdfReader


def resolve_tesseract_cmd():
    """Resolve the tesseract binary path from the environment.

    Resolution order:
    1. The ``TESSERACT_CMD`` environment variable, if set.
    2. ``shutil.which("tesseract")`` (binary on PATH).
    3. ``None`` when no binary is found.

    Never returns a hardcoded OS-specific path, so OCR works on Linux/WSL and
    degrades gracefully (``None``) when tesseract is absent.
    """
    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd:
        return env_cmd
    return shutil.which("tesseract")


try:
    import pytesseract
    from PIL import (
        Image,  # noqa: F401  # availability probe: OCR path is skipped if Pillow is absent
    )

    # Resolve the binary from the environment; only set it when found so a
    # missing binary leaves pytesseract's default intact rather than pointing at
    # a path that cannot exist.
    _tesseract_cmd = resolve_tesseract_cmd()
    if _tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd
except ImportError:
    pytesseract = None


def ocr_pdf_pages(file_path):
    """Recover text from a PDF with no text layer via OCR.

    Renders each page with PyMuPDF at 300 dpi, converts the pixmap to a PIL
    image, and runs tesseract over it. This is the fallback for "Microsoft:
    Print To PDF" vector-outline PDFs where ``pypdf``/``pdfplumber`` return no
    text. PyMuPDF does its own rendering, so no Ghostscript/poppler/ImageMagick
    system dependency is needed.

    Degrades gracefully — returns ``[]`` (never raises) when the tesseract
    binary is unavailable or the ``pymupdf``/``pytesseract``/``PIL`` imports
    fail, so the import pipeline falls through to the honest "No data found"
    failure rather than crashing.

    Args:
        file_path: Path to the PDF file

    Returns:
        List of non-empty recovered text lines across all pages (``[]`` when
        OCR is unavailable or recovers nothing).
    """
    if resolve_tesseract_cmd() is None:
        print("OCR skipped: tesseract binary not found (resolve_tesseract_cmd -> None)")
        return []

    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf  # legacy module name for PyMuPDF

        import pytesseract
        from PIL import Image
    except ImportError as e:
        print(f"OCR skipped: optional dependency unavailable ({e})")
        return []

    text_lines = []
    try:
        with pymupdf.open(file_path) as doc:
            for page_number, page in enumerate(doc, start=1):
                try:
                    pixmap = page.get_pixmap(dpi=300)
                    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                    page_text = pytesseract.image_to_string(image)
                    for line in page_text.split("\n"):
                        if line.strip():
                            text_lines.append(line)
                except Exception as e:
                    print(f"OCR error on page {page_number}: {e}")
        print(f"OCR recovered {len(text_lines)} lines")
    except Exception as e:
        print(f"OCR error opening PDF: {e}")
        return []

    return text_lines


def process_pdf(file_path, drive_result, config, folder_name="Unknown"):
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
        with open(file_path, "rb") as file:
            pdf_reader = PdfReader(file)

            for page in pdf_reader.pages:
                try:
                    text = page.extract_text()
                    if text.strip():
                        text_lines.extend(text.split("\n"))
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
                        text_lines.extend(text.split("\n"))
            print(f"pdfplumber extracted {len(text_lines)} lines")
        except Exception as e:
            print(f"pdfplumber error: {e}")
            text_lines = [f"[Error reading PDF with both libraries: {e!s}]"]
    else:
        print(f"PyPDF2 extracted {len(text_lines)} lines")

    # If both text-layer extractors produced nothing (e.g. a "Microsoft: Print
    # To PDF" vector-outline PDF), fall back to OCR. This fires only for
    # bug-condition inputs; text-layer PDFs skip it entirely.
    if not text_lines:
        print("No text layer found; attempting OCR fallback...")
        text_lines.extend(ocr_pdf_pages(file_path))

    # Use configured folder structure
    storage_folder = config.get_storage_folder(folder_name)
    config.ensure_folder_exists(storage_folder)

    return {
        "name": drive_result["id"],
        "url": drive_result["url"],
        "txt": "\n".join(text_lines),
        "folder": storage_folder,
    }


def process_image(file_path, drive_result, config, folder_name="Unknown", tenant=None):
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
        "[AI/OCR Extracted Data]",
        f"Date: {result['date']}",
        f"Total Amount: €{result['total_amount']:.2f}",
        f"VAT Amount: €{result['vat_amount']:.2f}",
        f"Description: {result['description']}",
        f"Vendor: {result['vendor']}",
    ]

    storage_folder = config.get_storage_folder(folder_name)
    config.ensure_folder_exists(storage_folder)

    return {
        "name": drive_result["id"],
        "url": drive_result["url"],
        "txt": "\n".join(text_lines),
        "folder": storage_folder,
        "ai_data": result,
    }


def process_csv(file_path, drive_result, config, folder_name="Unknown"):
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
                text_lines.append(f"Row {i + 1}: {dict(row)}")

        # Store CSV data for vendor-specific processing
        text_lines.append("[CSV_DATA_START]")
        text_lines.append(df.to_json(orient="records"))
        text_lines.append("[CSV_DATA_END]")

        print(f"CSV processed: {len(text_lines)} info lines")

    except Exception as e:
        print(f"CSV processing error: {e}")
        text_lines = [f"[Error processing CSV: {e!s}]"]

    # Use configured folder structure
    storage_folder = config.get_storage_folder(folder_name)
    config.ensure_folder_exists(storage_folder)

    return {
        "name": drive_result["id"],
        "url": drive_result["url"],
        "txt": "\n".join(text_lines),
        "folder": storage_folder,
    }


def process_mhtml(file_path, drive_result, config, folder_name="Unknown"):
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
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            content = file.read()

        # Decode HTML entities
        content = html.unescape(content)

        # Extract text from HTML content
        text_content = re.sub(r"<[^>]+>", " ", content)

        # Clean up whitespace and split into lines
        lines = [line.strip() for line in text_content.split("\n") if line.strip()]

        # Look for delivery date patterns
        delivery_date = None
        for line in lines:
            date_match = re.search(
                r"bezorging van (\w+dag)\s+(\d{1,2})\s+(\w+)", line, re.IGNORECASE
            )
            if date_match:
                _day, date_num, month = date_match.groups()
                month_map = {
                    "januari": "01",
                    "februari": "02",
                    "maart": "03",
                    "april": "04",
                    "mei": "05",
                    "juni": "06",
                    "juli": "07",
                    "augustus": "08",
                    "september": "09",
                    "oktober": "10",
                    "november": "11",
                    "december": "12",
                }
                if month.lower() in month_map:
                    current_year = datetime.now().year
                    delivery_date = (
                        f"{current_year}-{month_map[month.lower()]}-{date_num.zfill(2)}"
                    )
                    break

        # Extract amounts
        total_amount = 0
        total_match = re.search(
            r"<strong>(\d+)</strong>.*?<strong>(\d+)</strong>", content
        )
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
        text_lines = [f"[Error processing MHTML: {e!s}]"]

    storage_folder = config.get_storage_folder(folder_name)
    config.ensure_folder_exists(storage_folder)

    return {
        "name": drive_result["id"],
        "url": drive_result["url"],
        "txt": "\n".join(text_lines),
        "folder": storage_folder,
    }


def process_eml(file_path, drive_result, config, folder_name="Unknown"):
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
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            content = file.read()

        # Find the plain text part (after Content-Type: text/plain)
        text_match = re.search(
            r"Content-Type: text/plain.*?\n\n(.*?)(?=--_)", content, re.DOTALL
        )
        if text_match:
            plain_text = text_match.group(1).strip()
        else:
            # Fallback: look for text between multipart boundaries
            boundary_match = re.search(r'boundary="([^"]+)"', content)
            if boundary_match:
                boundary = boundary_match.group(1)
                parts = content.split(f"--{boundary}")
                for part in parts:
                    if "Content-Type: text/plain" in part:
                        text_start = part.find("\n\n")
                        if text_start != -1:
                            plain_text = part[text_start + 2 :].strip()
                            break
                else:
                    plain_text = content
            else:
                plain_text = content

        # Extract delivery date
        delivery_date = None
        date_match = re.search(
            r"bezorging van (\w+dag)\s+(\d{1,2})\s+(\w+)\s+(\d{4})", plain_text
        )
        if date_match:
            _day, date_num, month, year = date_match.groups()
            month_map = {
                "januari": "01",
                "februari": "02",
                "maart": "03",
                "april": "04",
                "mei": "05",
                "juni": "06",
                "juli": "07",
                "augustus": "08",
                "september": "09",
                "oktober": "10",
                "november": "11",
                "december": "12",
            }
            if month.lower() in month_map:
                delivery_date = f"{year}-{month_map[month.lower()]}-{date_num.zfill(2)}"

        # Extract total amount
        total_amount = 0
        total_match = re.search(r"Totaal\s*-+\s*([\d.]+)", plain_text)
        if total_match:
            total_amount = round(float(total_match.group(1)), 2)

        # Extract order number
        order_match = re.search(r"Order\s+([\d-]+)", plain_text)
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
        plain_lines = [line.strip() for line in plain_text.split("\n") if line.strip()]
        text_lines.extend(plain_lines)

    except Exception as e:
        text_lines = [f"[Error processing EML: {e!s}]"]

    storage_folder = config.get_storage_folder(folder_name)
    config.ensure_folder_exists(storage_folder)

    return {
        "name": drive_result["id"],
        "url": drive_result["url"],
        "txt": "\n".join(text_lines),
        "folder": storage_folder,
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
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b",
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
    ]
    amount_patterns = [r"[-+]?€?[\d,]+\.\d{2}", r"\([\d,]+\.\d{2}\)"]

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
            is_negative = "(" in amount_str or amount_str.startswith("-")
            amount = float(re.sub(r"[^\d.]", "", amount_str))

            description = re.sub(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b", "", line)
            description = re.sub(r"[-+]?€?[\d,]+\.\d{2}", "", description)
            description = re.sub(r"\s+", " ", description).strip()

            transactions.append(
                {
                    "date": date_match.group(),
                    "description": description or line[:50],
                    "amount": amount,
                    "debet": amount if is_negative else 0,
                    "credit": amount if not is_negative else 0,
                    "ref": file_data["folder"],
                    "ref1": None,
                    "ref2": None,
                    "ref3": file_data["url"],
                    "ref4": file_data["name"],
                }
            )

    return transactions
