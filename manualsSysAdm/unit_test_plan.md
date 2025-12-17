# myAdmin Backend Unit Test Plan

## Core Components

### 1. Database Layer
- **DatabaseManager** (`database.py`)
  - Test/production mode switching
  - Connection handling
  - Query execution
  - Transaction management

### 2. PDF Processing
- **PDFProcessor** (`pdf_processor.py`)
  - PDF text extraction (PyPDF2 + pdfplumber)
  - Vendor-specific parsing
  - File handling
- **VendorParsers** (`vendor_parsers.py`)
  - Kuwait Petroleum parser
  - Booking.com parser
  - Date/amount extraction

### 3. Google Drive Integration
- **GoogleDriveService** (`google_drive_service.py`)
  - Authentication
  - File upload/download
  - Folder operations
  - Test/production folder switching

### 4. Transaction Logic
- **TransactionLogic** (`transaction_logic.py`)
  - Transaction preparation
  - Template matching
  - Data validation
  - Database operations

### 5. Banking Processor
- **BankingProcessor** (`banking_processor.py`)
  - CSV file processing
  - Pattern matching
  - Duplicate detection
  - Account balance checks

### 6. STR Processor
- **STRProcessor** (`str_processor.py`)
  - Airbnb/Booking.com file processing
  - Revenue calculations
  - Status separation (realized/planned)
- **STRDatabase** (`str_database.py`)
  - BNB data operations
  - Future summary generation

### 7. Reporting
- **XLSXExportProcessor** (`xlsx_export.py`)
  - Excel file generation
  - R script logic implementation
  - Balance calculations

### 8. PDF Validation
- **PDFValidator** (`pdf_validation.py`)
  - URL validation
  - Progress tracking
  - Record updates

## Test Categories

### Unit Tests
- Individual function testing
- Mock external dependencies
- Edge case handling
- Error conditions

### Integration Tests
- Database connectivity
- Google Drive API
- File processing workflows
- API endpoint responses

### Environment Tests
- Test/production mode switching
- Configuration validation
- Credential handling

## Priority Test Files

### High Priority
1. `test_database.py` - Database operations
2. `test_pdf_processor.py` - PDF processing core
3. `test_transaction_logic.py` - Business logic
4. `test_banking_processor.py` - Banking workflows

### Medium Priority
5. `test_str_processor.py` - STR processing
6. `test_google_drive.py` - Drive integration
7. `test_reporting.py` - Report generation

### Low Priority
8. `test_pdf_validation.py` - URL validation
9. `test_api_endpoints.py` - Flask routes
10. `test_environment.py` - Mode switching

## Test Data Requirements
- Sample PDF files (Kuwait, Booking.com)
- Test CSV files (Rabobank format)
- Mock database records
- Test Google Drive folders
- Sample STR files (Airbnb, Booking)

## Test Infrastructure
- pytest framework
- Mock/patch for external services
- Test database setup/teardown
- Temporary file handling
- Environment variable mocking