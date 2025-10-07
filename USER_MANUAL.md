# PDF Transaction Processor - User Manual
Questions : 
Can we add BTW invoice parsing to pdf_processor.py and vendor_parsers.py
## Overview
The PDF Transaction Processor is a web application that automates the processing of PDF invoices, extracting transaction data and storing it in your MySQL database. It replaces manual R script processing with an intuitive web interface.

## Quick Start Commands

### Starting the Application

**Windows:**
```bash
# Batch file:
start.bat

# PowerShell (recommended):
.\start.ps1
```

**Linux/Mac:**
```bash
# Make executable and run:
chmod +x start.sh
./start.sh
```

**Manual (any OS):**
```bash
# From the myAdmin root directory
cd backend && python app.py & cd ../frontend && npm start
```

**Separate Terminals:**
```bash
# Terminal 1 - Backend
cd backend
python app.py

# Terminal 2 - Frontend  
cd frontend
npm start
```

### Stopping the Application
- Press `Ctrl+C` in both terminal windows
- Backend runs on: http://localhost:5000
- Frontend runs on: http://localhost:3000

## Development vs Production Mode

### Current Mode: Development (Test)
- Uses `mutaties_test` table (safe testing)
- Local file storage
- Debug logging enabled

### Switching to Production
1. **Backend**: Edit `backend/app.py`
   ```python
   # Change this line:
   config = Config(test_mode=True)
   processor = PDFProcessor(test_mode=True)
   transaction_logic = TransactionLogic(test_mode=True)
   
   # To this:
   config = Config(test_mode=False)
   processor = PDFProcessor(test_mode=False)
   transaction_logic = TransactionLogic(test_mode=False)
   ```

2. **Database**: Production mode uses `mutaties` table
3. **Storage**: Can be configured for Google Drive upload

## Using the Application

### 1. Upload PDF Invoice
1. Open http://localhost:3000
2. Click "Select PDF File" and choose your invoice
3. Select vendor folder from dropdown (e.g., "Booking.com")
4. Click "Upload & Process"

### 2. Review Parsed Data
The system displays three sections:
- **Parsed PDF Data**: Raw extracted text and file info
- **Parsed Vendor Data**: Structured data (dates, amounts, descriptions)
- **New Transaction Records**: Database-ready transactions

### 3. Approve Transactions
1. Review all transaction fields in the approval form
2. Edit any fields if needed (all are editable)
3. Click "✓ Approve & Save to Database"
4. Transactions are saved to database

## Supported Vendors

### Booking.com
- **Extracts**: Date, amounts, accommodation numbers, invoice numbers, Room Sales Commission
- **Database Lookup**: Matches accommodation numbers to property names
- **Account Codes**: 4007→1600 (main), 2010→4007 (VAT)

### Other Vendors
- Avance, Action, Mastercard, Visa, Bol.com, Picnic, Netflix, Temu, Ziggo
- Basic parsing implemented, can be enhanced as needed

## Database Integration

### Test Mode (Current)
- **Table**: `mutaties_test`
- **Safe**: No impact on production data
- **Purpose**: Testing and validation

### Production Mode
- **Table**: `mutaties`
- **Live**: Real transaction data
- **Backup**: Ensure database backup before use

### Transaction Structure
Each PDF creates 2 database records:
1. **Main Transaction**: Debet/Credit pair for invoice amount
2. **VAT Transaction**: Separate VAT calculation (21%)

## File Storage

### Development Mode
- **Location**: `backend/uploads/[VendorName]/`
- **URL**: Local file system
- **Ref3**: Local URL for testing

### Production Mode (Future)
- **Location**: Google Drive folders
- **URL**: Google Drive links
- **Ref3**: Google Drive URLs

## Troubleshooting

### Backend Won't Start
```bash
cd backend
pip install -r requirements.txt
python app.py
```

### Frontend Won't Start
```bash
cd frontend
npm install
npm start
```

### Database Connection Issues
1. Check `.env` file in backend folder
2. Verify MySQL credentials:
   ```
   DB_HOST=localhost
   DB_USER=peter
   DB_PASSWORD=your_password
   DB_NAME=finance
   ```

### PDF Processing Errors
- Ensure PDF is not password protected
- Check file size (large files may timeout)
- Verify PDF contains readable text

## Features

### Smart Transaction Preparation
- Uses last transaction as template
- Applies vendor-specific account codes
- Calculates VAT automatically (21%)
- Populates all database fields

### Accommodation Lookup (Booking.com)
- Queries `bnblookup` table with `lookUp = 'bdc'`
- Matches accommodation numbers to property names
- Stores property name in Ref1 field

### Approval Workflow
- All fields editable before saving
- Preview of template transactions
- Confirmation before database insert
- Cancel option available

## Database Fields Explained

- **TransactionNumber**: Vendor name + date
- **TransactionDate**: Extracted from PDF
- **TransactionDescription**: Includes property name, invoice number, commission type
- **TransactionAmount**: Main amount or VAT amount
- **Debet/Credit**: Account codes for double-entry bookkeeping
- **ReferenceNumber**: Base transaction identifier
- **Ref1**: Property/accommodation name
- **Ref2**: Invoice number
- **Ref3**: File URL (local or Google Drive)
- **Ref4**: Original filename
- **Administration**: Default "GoodwinSolutions"

## Next Steps

1. **Test thoroughly** with sample PDFs in development mode
2. **Verify database entries** in `mutaties_test` table
3. **Switch to production** when confident
4. **Add new vendors** as needed
5. **Configure Google Drive** for production file storage

## Support

For issues or enhancements:
1. Check console logs (F12 in browser)
2. Review backend terminal output
3. Verify database connectivity
4. Test with different PDF formats