# Language-Specific Features Guide

This guide describes how different features in myAdmin work with multiple languages.

---

## Overview

myAdmin supports **Dutch (Nederlands)** and **English** across all modules and features. This document explains how language affects each feature and what to expect when using the system in different languages.

---

## Core Modules

### Invoice Management

#### What's Translated

✅ **User Interface:**

- Upload buttons and file selection
- Processing status messages
- Edit and approval workflow labels
- Success and error messages

✅ **Data Display:**

- Column headers in invoice list
- Field labels in edit forms
- Validation messages
- Export options

✅ **Formatting:**

- Invoice dates (DD-MM-YYYY vs MM/DD/YYYY)
- Invoice amounts (€1.234,56 vs €1,234.56)
- Tax percentages

#### What's NOT Translated

❌ **Invoice Content:**

- Vendor names (as they appear on invoices)
- Invoice descriptions (original text preserved)
- Line item descriptions (original text preserved)
- Google Drive folder names (user-defined)

#### Language-Specific Behavior

**Dutch:**

- Date format: 18-02-2026
- Amount format: €1.234,56
- Tax labels: "BTW", "Excl. BTW", "Incl. BTW"

**English:**

- Date format: 2/18/2026
- Amount format: €1,234.56
- Tax labels: "VAT", "Excl. VAT", "Incl. VAT"

---

### Banking Processor

#### What's Translated

✅ **User Interface:**

- CSV upload interface
- Transaction list headers
- Filter labels and buttons
- Pattern management interface
- Duplicate detection messages

✅ **Data Display:**

- Column headers (Date, Description, Amount, Account)
- Status indicators (Processed, Duplicate, Pending)
- Action buttons (Import, Edit, Delete, Approve)
- Pagination controls

✅ **Formatting:**

- Transaction dates
- Transaction amounts
- Balance calculations

#### What's NOT Translated

❌ **Transaction Data:**

- Bank transaction descriptions (original from CSV)
- Account names (as defined in chart of accounts)
- Pattern rules (technical identifiers)
- CSV file content

#### Language-Specific Behavior

**Dutch:**

- Date format: 18-02-2026
- Amount format: €1.234,56
- Negative amounts: -€1.234,56
- CSV date parsing: DD-MM-YYYY expected

**English:**

- Date format: 2/18/2026
- Amount format: €1,234.56
- Negative amounts: -€1,234.56
- CSV date parsing: MM/DD/YYYY expected

---

### STR (Short-Term Rental) Processor

#### What's Translated

✅ **User Interface:**

- File upload interface (Airbnb/Booking.com)
- Booking list headers
- Filter and search labels
- Status indicators
- Action buttons

✅ **Data Display:**

- Column headers (Check-in, Check-out, Guest, Amount)
- Booking status (Realized, Planned, Future)
- Platform names (translated labels)
- Revenue summaries

✅ **Formatting:**

- Check-in/check-out dates
- Revenue amounts
- Occupancy percentages
- Average Daily Rate (ADR)

#### What's NOT Translated

❌ **Booking Data:**

- Guest names (as provided by platforms)
- Listing names (user-defined)
- Platform-specific codes
- Original booking descriptions

#### Language-Specific Behavior

**Dutch:**

- Date format: 18-02-2026
- Amount format: €1.234,56
- Platform labels: "Airbnb", "Booking.com"
- Status: "Gerealiseerd", "Gepland", "Toekomstig"

**English:**

- Date format: 2/18/2026
- Amount format: €1,234.56
- Platform labels: "Airbnb", "Booking.com"
- Status: "Realized", "Planned", "Future"

---

### STR Pricing Optimizer

#### What's Translated

✅ **User Interface:**

- Pricing dashboard labels
- Recommendation cards
- Chart titles and legends
- Filter controls
- Action buttons

✅ **Data Display:**

- Column headers (Listing, Current ADR, Recommended ADR)
- Pricing strategy labels
- Event-based pricing rules
- Comparison metrics

✅ **Formatting:**

- Dates (pricing periods)
- Currency amounts (ADR, revenue)
- Percentages (occupancy, price changes)

#### What's NOT Translated

❌ **Pricing Data:**

- Listing names (user-defined)
- Event names (user-defined)
- Custom pricing rules (technical)

#### Language-Specific Behavior

**Dutch:**

- Date format: 18-02-2026
- Amount format: €1.234,56
- Percentage format: 12,5%
- Labels: "Gemiddelde Dagprijs", "Aanbevolen Prijs"

**English:**

- Date format: 2/18/2026
- Amount format: €1,234.56
- Percentage format: 12.5%
- Labels: "Average Daily Rate", "Recommended Price"

---

### Reports & Analytics

#### What's Translated

✅ **Report Interface:**

- Report titles and descriptions
- Filter labels (date range, account, category)
- Export buttons (Excel, PDF, CSV)
- Chart titles and legends
- Table headers

✅ **Report Content:**

- Column headers
- Row labels (where applicable)
- Summary sections
- Totals and subtotals
- Chart axis labels

✅ **Formatting:**

- All dates in reports
- All currency amounts
- All percentages
- All number values

#### What's NOT Translated

❌ **Business Data:**

- Account names (from chart of accounts)
- Category names (user-defined)
- Transaction descriptions (original data)
- Custom report names (user-defined)

#### Available Reports

**Financial Reports:**

- Mutaties Report (Transactions Report)
- BTW Report (VAT Report)
- Aangifte IB Report (Income Tax Declaration)
- Reference Analysis Report
- Toeristenbelasting Report (Tourist Tax Report)
- Actuals Report

**BNB Reports:**

- BNB Revenue Report
- BNB Country Bookings Report
- BNB Returning Guests Report
- BNB Violins Report (distribution analysis)
- BNB Actuals Report
- BNB Future Report

#### Language-Specific Behavior

**Dutch:**

- Report titles: "Mutaties Rapport", "BTW Rapport", "Aangifte IB"
- Date format: 18-02-2026
- Amount format: €1.234,56
- Percentage format: 12,5%
- Excel column headers in Dutch

**English:**

- Report titles: "Transactions Report", "VAT Report", "Income Tax Declaration"
- Date format: 2/18/2026
- Amount format: €1,234.56
- Percentage format: 12.5%
- Excel column headers in English

---

### PDF Validation System

#### What's Translated

✅ **User Interface:**

- Validation dashboard
- Progress indicators
- Filter controls (year, admin)
- Action buttons (Validate, Update, Export)
- Status messages

✅ **Data Display:**

- Column headers (Transaction, PDF Link, Status)
- Status indicators (Valid, Invalid, Missing)
- Validation results
- Error messages

✅ **Formatting:**

- Transaction dates
- Transaction amounts
- Validation timestamps

#### What's NOT Translated

❌ **Technical Data:**

- Google Drive URLs
- File paths
- Error codes
- Technical validation messages

#### Language-Specific Behavior

**Dutch:**

- Status: "Geldig", "Ongeldig", "Ontbreekt"
- Messages: "Validatie voltooid", "Fout bij validatie"
- Date format: 18-02-2026

**English:**

- Status: "Valid", "Invalid", "Missing"
- Messages: "Validation complete", "Validation error"
- Date format: 2/18/2026

---

## Administrative Features

### User Management

#### What's Translated

✅ **User Interface:**

- User list headers
- Create/Edit user forms
- Role assignment labels
- Status indicators
- Action buttons

✅ **Email Notifications:**

- User invitation emails (subject and body)
- Password reset emails
- Account update notifications

✅ **Formatting:**

- User creation dates
- Last login dates

#### What's NOT Translated

❌ **User Data:**

- User names (as entered)
- Email addresses
- Role names (technical identifiers)
- Tenant names

#### Language-Specific Behavior

**Dutch:**

- Invitation email: "Welkom bij myAdmin"
- Status: "Actief", "Inactief", "Uitgenodigd"
- Roles: "Beheerder", "Gebruiker", "Tenant Beheerder"

**English:**

- Invitation email: "Welcome to myAdmin"
- Status: "Active", "Inactive", "Invited"
- Roles: "Administrator", "User", "Tenant Administrator"

---

### Tenant Management

#### What's Translated

✅ **User Interface:**

- Tenant list headers
- Create/Edit tenant forms
- Module management interface
- Configuration settings
- Action buttons

✅ **Data Display:**

- Column headers
- Status indicators
- Module names
- Configuration labels

#### What's NOT Translated

❌ **Tenant Data:**

- Tenant names (user-defined)
- Administration IDs (technical)
- Contact information (as entered)
- Custom configuration values

#### Language-Specific Behavior

**Dutch:**

- Module names: "Financieel", "STR", "Banking"
- Status: "Actief", "Inactief"
- Settings: "Standaard Taal", "Modules Ingeschakeld"

**English:**

- Module names: "Financial", "STR", "Banking"
- Status: "Active", "Inactive"
- Settings: "Default Language", "Enabled Modules"

---

### Chart of Accounts

#### What's Translated

✅ **User Interface:**

- Account list headers
- Create/Edit account forms
- Filter labels
- Export/Import buttons
- Action buttons

✅ **Data Display:**

- Column headers (Account Number, Name, Type)
- Account type labels
- Status indicators

#### What's NOT Translated

❌ **Account Data:**

- Account names (user-defined business data)
- Account descriptions (user-defined)
- Account numbers (technical identifiers)

**Note**: Chart of accounts is **tenant-specific business data**. Each tenant defines account names in their preferred language. The system does not translate account names because they are business-specific, not system-level data.

#### Language-Specific Behavior

**Dutch:**

- Type labels: "Activa", "Passiva", "Opbrengsten", "Kosten"
- Actions: "Exporteren", "Importeren", "Toevoegen"

**English:**

- Type labels: "Assets", "Liabilities", "Revenue", "Expenses"
- Actions: "Export", "Import", "Add"

---

## System Features

### Authentication

#### What's Translated

✅ **Login Page:**

- Page title and description
- Form labels (Email, Password)
- Button text (Login, Forgot Password)
- Error messages
- Success messages

✅ **AWS Cognito Hosted UI:**

- Limited translation (handled by AWS)
- Sign-in/Sign-up pages
- Password reset flow
- MFA pages

#### Language-Specific Behavior

**Dutch:**

- Login button: "Inloggen"
- Error: "Ongeldige inloggegevens"
- Success: "Succesvol ingelogd"

**English:**

- Login button: "Login"
- Error: "Invalid credentials"
- Success: "Successfully logged in"

---

### Navigation

#### What's Translated

✅ **Main Navigation:**

- Dashboard
- Reports (Rapporten)
- Banking (Bankieren)
- STR (Kortetermijnverhuur)
- Admin (Beheer)

✅ **Breadcrumbs:**

- Page navigation paths
- Back buttons

#### Language-Specific Behavior

**Dutch:**

- Dashboard → Rapporten → Mutaties Rapport

**English:**

- Dashboard → Reports → Transactions Report

---

### Error Messages

#### What's Translated

✅ **All Error Messages:**

- API errors (400, 401, 403, 404, 500)
- Network errors
- Validation errors
- Business logic errors
- System errors

✅ **Error Pages:**

- 404 Not Found
- 403 Forbidden
- 500 Server Error
- 503 Service Unavailable

#### Language-Specific Behavior

**Dutch:**

- 404: "Pagina niet gevonden"
- 500: "Serverfout"
- Network: "Netwerkfout - controleer uw verbinding"

**English:**

- 404: "Page not found"
- 500: "Server error"
- Network: "Network error - check your connection"

---

## Data Entry and Validation

### Form Validation

#### What's Translated

✅ **Validation Messages:**

- Required field messages
- Format validation (email, phone, URL)
- Length validation (min/max)
- Range validation (numbers, dates)
- Business rule validation

#### Language-Specific Behavior

**Dutch:**

- Required: "Dit veld is verplicht"
- Email: "Ongeldig e-mailadres"
- Date: "Ongeldige datum"

**English:**

- Required: "This field is required"
- Email: "Invalid email address"
- Date: "Invalid date"

---

### Date Entry

#### Format Expectations

**Dutch:**

- Expected format: DD-MM-YYYY
- Example: 18-02-2026
- Date pickers show Dutch format
- Manual entry accepts DD-MM-YYYY

**English:**

- Expected format: MM/DD/YYYY
- Example: 2/18/2026
- Date pickers show English format
- Manual entry accepts MM/DD/YYYY

**Tip**: Always use the date picker to avoid format confusion!

---

### Number Entry

#### Format Expectations

**Dutch:**

- Decimal separator: Comma (,)
- Example: 1234,56
- System interprets comma as decimal point

**English:**

- Decimal separator: Period (.)
- Example: 1234.56
- System interprets period as decimal point

**Tip**: Use the correct decimal separator for your language to avoid errors!

---

## Export and Import

### Excel Exports

#### What's Translated

✅ **Excel Files:**

- Column headers
- Sheet names (where applicable)
- Summary sections
- Formatted dates
- Formatted numbers

#### Language-Specific Behavior

**Dutch:**

- Column headers in Dutch
- Dates: DD-MM-YYYY
- Numbers: 1.234,56
- Sheet names: "Mutaties", "Samenvatting"

**English:**

- Column headers in English
- Dates: MM/DD/YYYY
- Numbers: 1,234.56
- Sheet names: "Transactions", "Summary"

---

### CSV Imports

#### Format Expectations

**Dutch:**

- Date format: DD-MM-YYYY
- Decimal separator: Comma (,)
- CSV delimiter: Semicolon (;) or comma (,)

**English:**

- Date format: MM/DD/YYYY
- Decimal separator: Period (.)
- CSV delimiter: Comma (,)

**Tip**: Ensure your CSV file matches the format for your selected language!

---

## Best Practices

### Choosing a Language

✅ **Choose based on:**

- Your primary language
- Your organization's language
- The language of your financial data
- The language you're most comfortable with

✅ **Be consistent:**

- Use the same language for all tasks
- Avoid switching languages frequently
- Train team members in the same language

### Data Entry

✅ **Always:**

- Use date pickers instead of manual entry
- Use the correct decimal separator for your language
- Double-check date formats before submitting
- Verify number formats in reports

### Reports and Exports

✅ **Remember:**

- Reports are generated in your current language
- Switch language before generating if needed
- Excel exports match your language format
- Share reports with users who understand the language

### Collaboration

✅ **When working with others:**

- Agree on a common language for the team
- Document which language is used for data entry
- Be aware of date/number format differences
- Communicate language preferences clearly

---

## Summary

myAdmin provides comprehensive language support across all features:

✅ **Fully Translated:**

- All user interface elements
- All system messages
- All reports and exports
- All email notifications
- All date and number formatting

❌ **Not Translated:**

- User-entered data (names, descriptions)
- Business-specific data (accounts, categories)
- Technical identifiers (codes, IDs)
- Third-party content (invoice text, bank descriptions)

**Key Takeaway**: The system interface is fully translated, but your business data remains in the language you entered it.

---

**Last Updated**: February 2026
**Version**: 1.0
