# FIN Module Overview

**Status**: Active  
**Purpose**: Financial transaction processing, reporting, and tax declarations

## What the FIN Module Does

The FIN module handles all financial operations for myAdmin, from invoice processing to tax declarations.

Every transaction uses double-entry bookkeeping (debit and credit accounts). Accounts are classified as either P&L (profit/loss) or Balance Sheet, which determines how they behave in reports and at year-end.

## Core Concepts

### Double-Entry Bookkeeping

Every transaction in the `mutaties` table uses double-entry format:

- **Debet** (debit account code)
- **Credit** (credit account code)
- **TransactionAmount** (always positive, no sign)

The `vw_mutaties` view splits each transaction into two rows: one for the debit account (positive amount) and one for the credit account (negative amount). The sum is therefore always zero.

### VW Classification (Verlies/Winst = Profit/Loss)

The entire FIN module is built on this principle:

- **VW='Y' (Yes)**: P&L accounts - Revenue (8000-8999) and Expenses (4000-7999)
  - Reports automatically filter by year
  - Start at zero each year
- **VW='N' (No)**: Balance Sheet accounts - Assets, Liabilities, Equity (0000-3999)
  - **Current behavior**: Reports include all transactions from beginning of time to report date
  - **Planned change**: Year-end closure will create opening balance transactions, so reports only need to query from the start of the year
  - Balances carry forward year to year

This VW logic is implemented in `mutaties_cache.py` and handles most year-end behavior automatically.

### Transaction Structure

The `mutaties` table stores all financial transactions:

**Core Fields**:

- `ID` - Auto-increment primary key
- `TransactionNumber` - Batch identifier (e.g., "Rabo 2024-01-15", "Invoice 2024-001")
- `TransactionDate` - Transaction date
- `TransactionDescription` - Description
- `TransactionAmount` - Amount (decimal 20,2)
- `Debet` - Debit account code (10 chars)
- `Credit` - Credit account code (10 chars)
- `administration` - Tenant identifier

**Reference Fields** (flexible, meaning depends on transaction type):

- `ReferenceNumber` - Primary reference used for matching and grouping transactions
  - Matches invoices with their bank payments
  - Often uses short supplier name (e.g., "Amazon", "KPN")
  - Creates sub-administrations within accounts (e.g., different projects or cost centers)
- `Ref1` - Context-dependent (e.g., bank account number for banking, vendor full name for invoices)
- `Ref2` - Context-dependent (e.g., invoice number, transaction reference, payment method)
- `Ref3` - Often used for Google Drive URL (1020 chars)
- `Ref4` - Often used for source file path or additional notes

**Common Usage Patterns**:

| Transaction Type | ReferenceNumber       | Ref1        | Ref2         | Ref3           | Ref4          |
| ---------------- | --------------------- | ----------- | ------------ | -------------- | ------------- |
| Invoice          | Supplier short name   | Vendor name | Invoice #    | GDrive URL\*   | File name     |
| Bank Payment     | Supplier short name   | Account #   | Bank ref\*\* | Bank ref 2\*\* | CSV file path |
| Manual Entry     | User-defined          | -           | -            | Supporting doc | Notes         |
| Year-end Closure | "YearClose YYYY"      | -           | -            | -              | -             |
| Opening Balance  | "OpeningBalance YYYY" | -           | -            | -              | -             |

\*Ref3 for invoices: Google Drive URL makes the invoice clickable in the app  
\*\*Ref2 and Ref3 for banking: Used for completeness checking and reconciliation

## Current Capabilities

### 1. Invoice Processing

**Routes**: `backend/src/routes/invoice_routes.py`

- Upload PDF/EML/MHTML invoices
- AI-powered extraction (OpenRouter API) with 250+ vendor-specific parsers as fallback
- Manual review and approval workflow
- Google Drive storage integration
- Duplicate detection

**Key Files**:

- `ai_extractor.py` - AI-powered invoice extraction
- `pdf_processor.py` - PDF parsing
- `duplicate_checker.py` - Duplicate detection
- `transaction_logic.py` - Transaction saving logic

### 2. Banking Processor

**Routes**: `backend/src/routes/banking_routes.py`

- Import Rabobank CSV statements
- Pattern-based automatic account assignment
- Duplicate detection and filtering
- Bulk transaction import
- Balance checking and reconciliation

**Key Files**:

- `banking_processor.py` - Bank statement processing
- `pattern_analyzer.py` - Transaction pattern analysis

**API Endpoints**:

- `POST /api/banking/scan-files` - Scan for bank files
- `POST /api/banking/process-files` - Process bank statements
- `POST /api/banking/apply-patterns` - Apply pattern matching
- `POST /api/banking/save-transactions` - Save to database
- `GET /api/banking/mutaties` - Get transactions
- `PUT /api/banking/mutaties/:id` - Update transaction

### 3. Tax Declarations

#### BTW (VAT) Declaration

**Routes**: `backend/src/routes/tax_routes.py`

- Quarterly VAT declarations
- Automatic calculation from transaction data
- HTML report generation using template system
- Google Drive upload

**Key Files**:

- `btw_processor.py` - VAT calculation logic
- `report_generators/btw_aangifte_generator.py` - Report generation

**API Endpoints**:

- `POST /api/btw/generate-report` - Generate BTW report
- `POST /api/btw/save-transaction` - Save BTW transaction
- `POST /api/btw/upload-report` - Upload to Google Drive

#### Aangifte IB (Income Tax)

**Routes**: `backend/src/reporting_routes.py`

- Annual income tax declarations
- P&L summary by category
- Template-based report generation
- XLSX export

**Key Files**:

- `report_generators/aangifte_ib_generator.py` - Income tax report

**API Endpoints**:

- `POST /aangifte-ib` - Generate IB report
- `POST /aangifte-ib-details` - Get detailed data
- `POST /aangifte-ib-export` - Export HTML
- `POST /aangifte-ib-xlsx-export` - Export XLSX
- `POST /aangifte-ib-xlsx-export-stream` - Stream XLSX export

#### Toeristenbelasting (Tourist Tax)

**Routes**: `backend/src/routes/tax_routes.py`

- Annual tourist tax declarations for STR properties
- Based on BNB booking data
- Night counts and tax calculations

**Key Files**:

- `toeristenbelasting_processor.py` - Tourist tax logic
- `report_generators/toeristenbelasting_generator.py` - Report generation

**API Endpoints**:

- `POST /api/toeristenbelasting/generate-report` - Generate report
- `GET /api/toeristenbelasting/available-years` - Get available years

### 4. Financial Reports

**Routes**: `backend/src/reporting_routes.py`

**P&L Statement**:

- Revenue and expense summary by account
- Filtered by year (VW='Y' logic)
- Comparison across periods

**Balance Sheet**:

- Assets, liabilities, equity summary
- Currently: Cumulative from beginning of time (VW='N' logic)
- After year-end closure: Will use opening balance transactions for performance
- Point-in-time snapshot

**XLSX Export**:

- Export transactions to Excel
- Currently calculates opening balances on-the-fly
- After year-end closure: Will use opening balance transactions
- Formatted for accountant review

**Key Files**:

- `xlsx_export.py` - Excel export logic
- `report_generators/financial_report_generator.py` - Report data preparation
- `reporting_routes.py` - Report endpoints

**API Endpoints**:

- `GET /get-financial-summary` - Financial summary
- `GET /get-str-revenue` - STR revenue data
- `GET /get-account-summary` - Account summary
- `GET /get-mutaties-table` - Transaction table
- `GET /get-balance-data` - Balance data
- `GET /get-trends-data` - Trend analysis
- `GET /get-filter-options` - Available filters
- `GET /get-available-data/:type` - Available years/references
- `GET /get-check-reference` - Reference analysis
- `GET /get-reference-analysis` - Detailed reference analysis
- `GET /get-available-years` - Available years

### 5. Missing Invoice Tracking

**Routes**: `backend/src/routes/missing_invoices_routes.py`

- Identify transactions without supporting documents
- Upload receipts for existing transactions
- Link documents to transactions

**API Endpoints**:

- `POST /api/transactions` - Get transactions
- `POST /api/upload-receipt` - Upload receipt
- `POST /api/update-transaction-refs` - Update references

### 6. PDF Validation

**Routes**: `backend/src/routes/pdf_validation_routes.py`

- Validate Google Drive URLs in transaction records
- Real-time progress tracking with Server-Sent Events
- Automatic file/folder URL resolution
- Manual update for broken links

**API Endpoints**:

- `GET /api/pdf/validate-urls-stream` - Stream validation progress
- `GET /api/pdf/validate-urls` - Validate URLs
- `POST /api/pdf/update-record` - Update record
- `GET /api/pdf/get-administrations` - Get administrations
- `GET /api/pdf/validate-single-url` - Validate single URL

### 7. Chart of Accounts Management

**Routes**: `backend/src/routes/chart_of_accounts_routes.py`

- Manage account codes and descriptions
- VW classification
- Parent account relationships
- Multi-tenant support

**API Endpoints**:

- `GET /api/tenant-admin/chart-of-accounts` - Get accounts
- `POST /api/tenant-admin/chart-of-accounts` - Create account
- `PUT /api/tenant-admin/chart-of-accounts/:code` - Update account
- `DELETE /api/tenant-admin/chart-of-accounts/:code` - Delete account
- `GET /api/tenant-admin/chart-of-accounts/export` - Export accounts

## Data Model

### Core Tables

**mutaties** - Financial transactions (double-entry format)

- `ID` - Primary key (auto-increment)
- `TransactionNumber` - Batch identifier
- `TransactionDate` - Transaction date
- `TransactionDescription` - Description
- `TransactionAmount` - Amount (decimal 20,2)
- `Debet` - Debit account code (10 chars)
- `Credit` - Credit account code (10 chars)
- `ReferenceNumber` - Primary reference
- `Ref1`, `Ref2`, `Ref3`, `Ref4` - Additional references
- `administration` - Tenant identifier

**vw_mutaties** - Reporting view (single-line format)

- Transforms double-entry into single lines
- `Reknum` - Account code (from Debet or Credit)
- `Amount` - Signed amount (positive for debit, negative for credit)
- `AccountName` - Account description
- `Parent` - Parent account code
- `VW` - Verlies/Winst classification ('Y' = P&L, 'N' = Balance Sheet)
- `jaar`, `kwartaal`, `maand`, `week` - Date components
- `Aangifte` - Declaration reference
- All original fields from mutaties
- Used by all reports and queries

### Supporting Tables

**bnb** - Realized STR bookings (used for tourist tax)
**bnbplanned** - Planned STR bookings
**bnbfuture** - Future STR revenue
**tenants** - Multi-tenant configuration

## Architecture Patterns

### Caching Layer

**Location**: `backend/src/mutaties_cache.py`, `bnb_cache.py`

- In-memory caching of transaction data
- VW logic implementation
- Performance optimization for reports

### Template System

**Location**: `backend/src/services/template_service.py`

- HTML template rendering for reports
- Field mapping for tax forms
- Reusable report generation

### Output Service

**Location**: `backend/src/services/output_service.py`

- Unified output handling (download, Google Drive, email)
- Google Drive folder management
- Content type handling

## What's NOT in FIN Module

- **Year-end closure process** - Planned for implementation (will create opening balance transactions)
- **Multi-currency support** - Single currency only
- **Depreciation calculations** - Manual entry required
- **Budget vs actual** - Not implemented
- **Consolidated reporting** - Single tenant per report

## Integration Points

### With STR Module

- Tourist tax declarations use BNB booking data
- STR revenue flows into financial reports
- Channel-specific revenue tracking

### With Google Drive

- Invoice storage
- Report uploads
- Document validation

### With AWS

- Cognito authentication
- SNS notifications
- Multi-tenant isolation

## Key Implementation Files

### Routes (API Endpoints)

- `routes/invoice_routes.py` - Invoice upload and approval
- `routes/banking_routes.py` - Bank statement import
- `routes/tax_routes.py` - Tax declarations
- `routes/missing_invoices_routes.py` - Missing invoice tracking
- `routes/pdf_validation_routes.py` - PDF validation
- `routes/chart_of_accounts_routes.py` - Chart of accounts management
- `reporting_routes.py` - Financial reports

### Processors (Business Logic)

- `banking_processor.py` - Bank statement processing
- `btw_processor.py` - VAT calculations
- `toeristenbelasting_processor.py` - Tourist tax calculations
- `pdf_processor.py` - PDF parsing
- `ai_extractor.py` - AI invoice extraction
- `transaction_logic.py` - Transaction saving

### Report Generators

- `report_generators/btw_aangifte_generator.py` - VAT reports
- `report_generators/aangifte_ib_generator.py` - Income tax reports
- `report_generators/toeristenbelasting_generator.py` - Tourist tax reports
- `report_generators/financial_report_generator.py` - Financial reports

### Services

- `services/template_service.py` - Template rendering
- `services/output_service.py` - Output handling
- `services/google_drive_service.py` - Google Drive integration

### Data Access

- `database.py` - Database connection and queries
- `mutaties_cache.py` - Transaction caching with VW logic
- `bnb_cache.py` - BNB data caching

## Development Guidelines

### Adding New Reports

1. Create generator in `report_generators/`
2. Add route in appropriate routes file
3. Use `TemplateService` for HTML rendering
4. Use `OutputService` for delivery
5. Follow existing patterns (see BTW or IB generators)

### Adding New Transaction Types

1. Add processor in `backend/src/`
2. Create route in `routes/`
3. Ensure proper account code assignment
4. Add to `mutaties` table with Debet/Credit
5. Update cache if needed

### Modifying Tax Logic

1. Update processor (e.g., `btw_processor.py`)
2. Update generator (e.g., `btw_aangifte_generator.py`)
3. Update template if needed
4. Test with historical data
5. Document changes in spec

## Testing

### Test Structure

- `tests/unit/` - Unit tests for processors
- `tests/api/` - API endpoint tests
- `tests/integration/` - Integration tests
- `tests/database/` - Database tests

### Key Test Files

- `test_btw_processor.py` - VAT logic tests
- `test_banking_processor.py` - Bank import tests
- `test_mutaties_cache.py` - VW logic tests

## Related Specifications

- `.kiro/specs/FIN/VAT Rules/` - BTW calculation rules
- `.kiro/specs/FIN/InkomstenBelasting/` - Income tax rules
- `.kiro/specs/FIN/BankingProcessor/` - Bank import specs
- `.kiro/specs/FIN/Reports/` - Report specifications
- `.kiro/specs/Common/templates/` - Template system

## Quick Reference

### Common Tasks

**Generate BTW Report**:

```
POST /api/btw/generate-report
Body: { administration, year, quarter, output_destination }
```

**Import Bank Statement**:

```
POST /api/banking/process-files
Body: FormData with CSV file
```

**Upload Invoice**:

```
POST /api/upload
Body: FormData with PDF/EML file
```

**Get Financial Summary**:

```
GET /get-financial-summary?date_from=2024-01-01&date_to=2024-12-31&administration=X
```

### Account Codes

Account codes (Grootboekrekening) are tenant-specific and configurable:

- Each tenant defines their own chart of accounts
- Account codes are classified as VW='Y' (P&L) or VW='N' (Balance Sheet)
- Parent account relationships create hierarchies
- Managed via Chart of Accounts Management (see section 7)

Common patterns (but not enforced):

- Lower ranges (0000-3999): Often used for Balance Sheet accounts
- Higher ranges (4000-8999): Often used for P&L accounts
- But each tenant can organize as they prefer

### VW Logic in Action

**P&L Report for 2024**:

```sql
SELECT * FROM vw_mutaties
WHERE VW='Y'
AND jaar = 2024
```

**Balance Sheet as of 2024-12-31**:

```sql
SELECT * FROM vw_mutaties
WHERE VW='N'
AND TransactionDate <= '2024-12-31'
```

## Summary

The FIN module is a practical, working system built around simple but powerful concepts:

1. **Double-entry bookkeeping** with Debet/Credit accounts
2. **VW classification** handles most year-end logic automatically
3. **Template system** provides flexible report generation
4. **Caching layer** ensures performance
5. **Multi-tenant** architecture maintains data isolation
6. **Integration** with Google Drive and AWS services

Focus on understanding these core patterns rather than theoretical features that don't exist yet.
