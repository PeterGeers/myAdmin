# Product Overview

myAdmin is a comprehensive financial transaction processing and administrative tooling system for managing invoices, banking transactions, and short-term rental (STR) operations.

## Core Modules

### Invoice Management

- AI-powered universal invoice extraction via OpenRouter API
- 250+ vendor-specific parsers as fallback
- PDF/EML/MHTML file processing
- Google Drive integration for storage
- Manual edit and approval workflow

### Banking Processor

- CSV bank statement processing (Rabobank format)
- Pattern-based automatic account assignment
- Duplicate detection and filtering
- Bulk transaction import

### STR (Short-Term Rental) Processor

- Airbnb/Booking.com revenue file processing
- Realized vs planned booking separation
- Future revenue summaries
- Multi-platform support

### STR Pricing Optimizer

- AI-powered pricing recommendations with business logic
- Historical vs recommended ADR comparison
- Event-based pricing uplifts
- 14-month pricing strategy generation

### Reports & Analytics

- Interactive dashboards with Recharts
- P&L statements and balance sheets
- BNB revenue analytics (violin/box plots)
- Aangifte IB (Income Tax) declarations
- Excel/XLSX export capabilities

### PDF Validation System

- Google Drive URL validation in transaction records
- Real-time progress tracking
- Automatic file/folder URL resolution
- Manual update for broken links

## Key Features

- **Test/Production Mode**: Environment-based switching via `.env` configuration
- **Multi-tenant Support**: Tenant-based data isolation with AWS Cognito authentication
- **AWS Integration**: SNS notifications for alerts
- **Real-time Updates**: Server-Sent Events for progress tracking
- **Audit Logging**: Comprehensive audit trail for all operations
