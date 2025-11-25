# myAdmin

Comprehensive administrative tooling with ReactJS frontend and Python backend for financial transaction processing.

## Quick Start

```psh
# Start both servers
.\start.ps1

# Or manually:
cd backend && python app.py  # Port 5000
cd frontend && npm start     # Port 3000
```

## Components

### 📄 Import Invoices
- Upload PDFs, EML, and MHTML files to Google Drive or local storage
- AI-powered universal invoice data extraction via OpenRouter API
- Traditional vendor-specific parsers as fallback (251+ formats)
- Searchable folder dropdown with auto-selection
- Edit and approve transactions before saving
- MySQL storage with metadata

### 🏦 Banking Processor
- Process CSV bank statements (Rabobank format)
- Pattern matching for automatic account assignment
- Duplicate detection and filtering
- Bulk transaction import

### 🏠 STR (Short Term Rental) Processor
- Process Airbnb/Booking.com revenue files
- Separate realized vs planned bookings
- Generate future revenue summaries
- Multi-platform support

### 💰 STR Pricing Optimizer
- AI-powered pricing recommendations with business logic
- Historical vs recommended ADR comparison
- Quarterly summary tables by listing
- Monthly trend analysis with interactive charts
- Event-based pricing uplifts
- Guest fee adjustments for Child Friendly property
- 14-month pricing strategy generation

### 📊 myAdmin Reports
- Interactive dashboards with Recharts
- P&L statements and balance sheets
- BNB revenue analytics with violin/box plots
- BNB returning guests analysis
- Aangifte IB (Income Tax) declarations with VW logic
- HTML/XLSX export functionality
- Reference number validation

### 🔍 PDF Validation System
- Validate Google Drive URLs in transaction records
- Real-time progress tracking with dynamic progress bar
- Year and administration filtering
- Automatic file/folder URL resolution
- Manual update functionality for broken links
- Gmail URL detection for manual verification

## Database

- **MySQL**: Main transaction storage
- **Tables**: mutaties, bnb, bnbplanned, bnbfuture, pricing_recommendations, pricing_events, listings
- **Views**: vw_mutaties for reporting with VW logic
- **Config**: `.env` file with credentials
- **Pricing**: AI insights storage and business logic pricing

## Test/Production Mode

### Environment Switching
Switch between test and production environments using `.env`:

```env
# Production Mode (default)
TEST_MODE=false
DB_NAME=finance
FACTUREN_FOLDER_ID=your_production_folder_id
FACTUREN_FOLDER_NAME=Facturen
OPENROUTER_API_KEY=your_openrouter_api_key

# Test Mode
TEST_MODE=true
TEST_DB_NAME=testfinance
TEST_FACTUREN_FOLDER_ID=your_test_folder_id
TEST_FACTUREN_FOLDER_NAME=testFacturen
```

### Features
- **Database**: Automatic switching between `finance` and `testfinance`
- **Google Drive**: Separate folders for test and production
- **Status Display**: Mode indicator in all function headers
- **Route Validation**: Prevents conflicts at startup
- **Schema Validation**: Ensures API consistency

## Git Management

```bash
# Commit with timestamp
.\gitUpdate.ps1

# Commit with custom message
.\gitUpdate.ps1 "Your message here"
```

## Tech Stack

- **Frontend**: React, TypeScript, Chakra UI, Recharts
- **Backend**: Python, Flask, MySQL, Google Drive API, Gmail API
- **AI Integration**: OpenRouter API with GPT-3.5-turbo for invoice extraction
- **Processing**: PyPDF2, pdfplumber, pandas, openpyxl
- **Pricing**: Business logic with AI correction factors
- **Export**: HTML generation, XLSX with R script logic
- **Real-time**: Server-Sent Events for progress tracking