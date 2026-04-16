# Requirements Document — ZZP Module

## Introduction

The ZZP (Zelfstandige Zonder Personeel / Freelancer) module extends the myAdmin financial platform with invoicing, time tracking, and debtor/creditor management for freelancers. It is the first consumer of a set of shared helpers (contacts, invoice booking, payment checking, PDF generation, email sending) that are designed for reuse by future modules (Webshop, Logistics, etc.).

The ZZP module requires the FIN module to be active and registers as 'ZZP' in the `MODULE_REGISTRY`. Most core financial functions (BTW-aangifte, bankadministratie, belastingaangifte, jaarverslag, archief, cloud storage) are already handled by FIN. The ZZP module adds: facturatie, urenregistratie, debiteuren/crediteurenbeheer, and the shared contact/product registry.

## Glossary

- **ZZP_Module**: The ZZP administration module registered in `MODULE_REGISTRY` as 'ZZP', requiring FIN to be active
- **Contact_Registry**: Shared multi-tenant table storing business contact details (client ID, name, address, VAT number, KvK number, multiple email addresses with type indicator), reusable by future modules
- **Client_ID**: A short unique reference code per contact per tenant (e.g., "ACME", "KPN") used as the `ReferenceNumber` in `mutaties` and included in payment details for automatic matching
- **Product_Registry**: Shared multi-tenant table storing products/services with a configurable `type` parameter set and VAT codes limited to high, low, and zero rates
- **Invoice_Engine**: The set of services responsible for creating, numbering, tracking, and managing invoices (both outgoing and incoming)
- **Invoice_Booking_Helper**: Shared helper function that creates `mutaties` entries using double-entry bookkeeping for both incoming and outgoing invoices
- **Payment_Check_Helper**: Shared helper function that leverages existing reference matching from banking import to determine if invoices are paid
- **PDF_Generator**: Shared service that converts HTML invoice templates to PDF documents with proper logo support (using weasyprint or similar)
- **Email_Sender**: Shared helper function that sends invoice documents via AWS SES using the existing `SESEmailService`
- **Invoice_Number**: A tenant-specific sequential identifier following the format `{PREFIX}-{YEAR}-{SEQUENCE}` (e.g., INV-2026-0001)
- **Credit_Note**: A document that partially or fully reverses a previously issued invoice, linked to the original invoice
- **Recurring_Invoice**: An invoice configuration that automatically generates new invoices at a defined interval (weekly, monthly, quarterly, yearly)
- **Time_Entry**: A record of hours worked for a specific contact and optional project, used for billing and tax deduction purposes
- **Invoice_Status**: The lifecycle state of an invoice: draft, sent, paid, overdue, cancelled, or credited
- **Tenant**: An administration entity identified by the `administration` field, providing data isolation across all queries
- **FIN_Module**: The existing Financial Administration module that provides double-entry bookkeeping, chart of accounts, tax rates, and transaction management
- **Mutaties**: The core financial transactions table using double-entry bookkeeping (Debet/Credit) filtered by `administration`
- **Parameter_Table**: The `parameters` table storing system, tenant, and role-scoped configuration values with namespace/key pairs, managed via the ParameterService
- **Ledger_Parameter_Registry**: The JSON configuration file (`ledger_parameters.json`) defining known parameter keys for `rekeningschema.parameters`, served via API for frontend rendering in the Account Modal
- **Chart_of_Accounts**: The `rekeningschema` table storing the Tenant's chart of accounts with account numbers, names, and a `parameters` JSON column for account-level flags (e.g., `bank_account`, `zzp_invoice_ledger`)

## Requirements

### Requirement 1: ZZP Module Registration

**User Story:** As a tenant administrator, I want to enable the ZZP module for my administration, so that freelancer-specific features become available to authorized users.

#### Acceptance Criteria

1. THE ZZP_Module SHALL be registered in `MODULE_REGISTRY` as 'ZZP' with required dependency on the FIN_Module
2. WHEN a user accesses a ZZP route without the ZZP_Module enabled for the Tenant, THE ZZP_Module SHALL return HTTP 403 with an error message indicating the module is not enabled
3. THE ZZP_Module SHALL enforce permissions using the format `zzp_crud`, `zzp_read`, `zzp_export`, and `zzp_tenant`
4. THE ZZP_Module SHALL use the decorator chain `@cognito_required()` then `@tenant_required()` then `@module_required('ZZP')` on all ZZP routes
5. WHEN the FIN_Module is not active for a Tenant, THE ZZP_Module SHALL not be activatable for that Tenant

### Requirement 2: Shared Contact Registry

**User Story:** As a ZZP user, I want to manage a registry of business contacts, so that I can reuse contact information across invoices and other modules.

#### Acceptance Criteria

1. THE Contact_Registry SHALL store the following attributes per contact: client ID (short unique reference code per tenant, e.g., "ACME", "KPN"), company name, contact person name, street address, postal code, city, country, VAT number, KvK number (Chamber of Commerce), phone number, IBAN, and multiple email addresses with a type indicator (general, invoice, other)
2. THE Contact_Registry SHALL include an `administration` field for multi-tenant isolation, filtering all queries by Tenant
3. WHEN a contact is created, THE Contact_Registry SHALL only require the client ID and company name; all other fields SHALL be optional
4. THE Contact_Registry SHALL support multiple email addresses per contact, with at least one flagged as the invoice email address
5. WHEN a contact is retrieved, THE Contact_Registry SHALL return the contact data scoped to the requesting Tenant only
6. THE Contact_Registry SHALL support create, read, update, and soft-delete operations via a `ContactService`
7. WHEN a contact is referenced by an existing invoice, THE Contact_Registry SHALL prevent hard deletion of that contact
8. THE Contact_Registry SHALL enforce uniqueness of the Client_ID within a Tenant

### Requirement 3: Shared Product/Service Registry

**User Story:** As a ZZP user, I want to maintain a catalog of products and services, so that I can quickly add line items to invoices.

#### Acceptance Criteria

1. THE Product_Registry SHALL store the following attributes per product: name, description, type, unit price, VAT code reference (high, low, or zero only), unit of measure, and active status
2. THE Product_Registry SHALL include an `administration` field for multi-tenant isolation
3. THE Product_Registry SHALL reference VAT codes from the existing `tax_rates` table via the `TaxRateService`, limited to high, low, and zero rate codes
4. THE Product_Registry SHALL define product types as a configurable parameter set (via the parameter system), not hardcoded values
5. WHEN a future module requires additional product types, THE Product_Registry SHALL accept new type values by updating the parameter set without schema changes
6. WHEN a product is referenced by an existing invoice line, THE Product_Registry SHALL prevent hard deletion of that product

### Requirement 4: Invoice Creation and Management

**User Story:** As a ZZP user, I want to create and manage outgoing invoices, so that I can bill my clients for services rendered.

#### Acceptance Criteria

1. THE Invoice_Engine SHALL create invoices with the following data: invoice number, contact reference, invoice date, due date, payment terms (days), currency, status, and optional notes
2. THE Invoice_Engine SHALL support invoice line items with: product/service reference, description override, quantity, unit price, VAT code, VAT amount, and line total
3. THE Invoice_Engine SHALL calculate line totals as quantity multiplied by unit price (excluding VAT)
4. THE Invoice_Engine SHALL calculate VAT amounts per line using the rate from the `TaxRateService` for the invoice date
5. THE Invoice_Engine SHALL calculate invoice totals as: subtotal (sum of all line totals excluding VAT), VAT summary grouped per VAT code (sum of VAT amounts per code), and grand total (subtotal plus total VAT)
6. THE Invoice_Engine SHALL track Invoice_Status through the lifecycle: draft, sent, paid, overdue, cancelled, credited
7. WHEN an invoice is in draft status, THE Invoice_Engine SHALL allow editing of all invoice fields
8. WHEN an invoice has been sent, THE Invoice_Engine SHALL prevent modification of financial fields (amounts, VAT, line items)
9. THE Invoice_Engine SHALL filter all invoice queries by the `administration` field of the requesting Tenant

### Requirement 5: Invoice Numbering

**User Story:** As a ZZP user, I want invoices to be automatically numbered per tenant, so that I have a consistent and sequential numbering scheme.

#### Acceptance Criteria

1. THE Invoice_Engine SHALL generate Invoice_Numbers in the format `{PREFIX}-{YEAR}-{SEQUENCE}` where PREFIX is configurable per Tenant, YEAR is the four-digit invoice year, and SEQUENCE is a zero-padded sequential number (minimum 4 digits)
2. THE Invoice_Engine SHALL ensure Invoice_Numbers are unique within a Tenant and year combination
3. WHEN a new invoice is created for a Tenant in a given year, THE Invoice_Engine SHALL assign the next available sequence number for that Tenant and year
4. IF two concurrent requests attempt to create invoices for the same Tenant and year, THEN THE Invoice_Engine SHALL use database-level locking to prevent duplicate sequence numbers

### Requirement 6: Invoice Booking in FIN

**User Story:** As a ZZP user, I want invoices to be automatically booked in the financial administration, so that my bookkeeping stays up to date without manual entry.

#### Acceptance Criteria

1. THE Invoice_Booking_Helper SHALL create `mutaties` entries using double-entry bookkeeping when an outgoing invoice is sent
2. THE Invoice_Booking_Helper SHALL create `mutaties` entries using double-entry bookkeeping when an incoming invoice is approved
3. WHEN booking an outgoing invoice, THE Invoice_Booking_Helper SHALL debit the debtor account and credit the revenue account, with separate entries for VAT
4. WHEN booking an incoming invoice, THE Invoice_Booking_Helper SHALL debit the expense account and credit the creditor account, with separate entries for VAT
5. THE Invoice_Booking_Helper SHALL use account codes from the Tenant's chart of accounts (`rekeningschema`)
6. THE Invoice_Booking_Helper SHALL follow the existing `TransactionLogic.save_approved_transactions()` pattern for writing to the `mutaties` table
7. THE Invoice_Booking_Helper SHALL set the `ReferenceNumber` field to the contact's Client_ID for matching with bank payments
8. THE Invoice_Booking_Helper SHALL set the `Ref2` field to the Invoice_Number for traceability
9. THE Invoice_Booking_Helper SHALL include the contact's Client_ID in the payment reference details so that incoming bank payments can be automatically matched
10. THE Invoice_Booking_Helper SHALL skip zero-amount transaction lines (e.g., zero-VAT lines) consistent with existing behavior

### Requirement 7: Payment Checking

**User Story:** As a ZZP user, I want the system to automatically detect when invoices are paid, so that invoice statuses stay current without manual updates.

#### Acceptance Criteria

1. THE Payment_Check_Helper SHALL match bank transactions in `mutaties` against open invoices using the `ReferenceNumber` field (which contains the contact's Client_ID)
2. WHEN a bank transaction matches an open invoice by reference and the amount matches within a tolerance of €0.01, THE Payment_Check_Helper SHALL update the Invoice_Status to 'paid'
3. WHEN a bank transaction partially matches an open invoice amount, THE Payment_Check_Helper SHALL record the partial payment and keep the Invoice_Status as 'sent'
4. THE Payment_Check_Helper SHALL leverage the existing pattern matching logic from the banking import process
5. THE Payment_Check_Helper SHALL filter all payment matching queries by the Tenant's `administration` field

### Requirement 8: PDF Invoice Generation

**User Story:** As a ZZP user, I want to generate professional PDF invoices with my company logo, so that I can send polished documents to my clients.

#### Acceptance Criteria

1. THE PDF_Generator SHALL convert HTML invoice templates to PDF documents
2. THE PDF_Generator SHALL render embedded images including company logos in the generated PDF
3. THE PDF_Generator SHALL use a library capable of HTML-to-PDF conversion with CSS support (weasyprint or equivalent)
4. THE PDF_Generator SHALL retrieve the company logo from the Tenant's configuration
5. THE PDF_Generator SHALL use the existing `TemplateService` for HTML template rendering with field mappings
6. THE PDF_Generator SHALL produce PDF output as a `BytesIO` object compatible with the existing `OutputService`
7. WHEN the Tenant has no logo configured, THE PDF_Generator SHALL generate the PDF without a logo placeholder
8. THE PDF_Generator SHALL support A4 page format with configurable margins
9. THE PDF_Generator SHALL include the contact's Client_ID in the payment details section of the invoice so the client can include it in their bank transfer reference

### Requirement 9: Invoice Email Sending

**User Story:** As a ZZP user, I want to send invoices directly to clients via email, so that I can deliver invoices without leaving the application.

#### Acceptance Criteria

1. THE Email_Sender SHALL send invoice emails using the existing `SESEmailService`
2. THE Email_Sender SHALL attach the generated PDF invoice to the email
3. THE Email_Sender SHALL support attaching additional supporting documents alongside the invoice PDF
4. THE Email_Sender SHALL use the contact's invoice email address as the recipient; WHEN no invoice email is set, THE Email_Sender SHALL fall back to the contact's general email address
5. THE Email_Sender SHALL use a configurable email subject template per Tenant
6. THE Email_Sender SHALL use a configurable email body template (HTML) per Tenant
7. WHEN an invoice email is sent successfully, THE Email_Sender SHALL update the Invoice_Status from 'draft' to 'sent' and record the send timestamp
8. IF the email sending fails, THEN THE Email_Sender SHALL log the error, keep the Invoice_Status as 'draft', and return an error message to the user

### Requirement 10: Credit Notes and Corrections

**User Story:** As a ZZP user, I want to issue credit notes for incorrect or cancelled invoices, so that I can maintain accurate financial records.

#### Acceptance Criteria

1. THE Invoice_Engine SHALL support creating a Credit_Note linked to an original invoice
2. THE Invoice_Engine SHALL assign a separate sequential number to credit notes using the same numbering mechanism as invoices but with a distinct prefix (e.g., CN-2026-0001)
3. WHEN a Credit_Note is created, THE Invoice_Engine SHALL copy line items from the original invoice with negated amounts
4. WHEN a Credit_Note is finalized, THE Invoice_Booking_Helper SHALL create reversal entries in `mutaties` that offset the original invoice booking
5. WHEN a full Credit_Note is issued for an invoice, THE Invoice_Engine SHALL update the original invoice status to 'credited'

### Requirement 11: Time Tracking (Urenregistratie)

**User Story:** As a ZZP user, I want to track hours worked per client and project using multiple input methods, so that I can bill accurately and claim tax deductions regardless of how I record my time.

#### Acceptance Criteria

1. THE ZZP_Module SHALL store Time_Entry records with: date, contact reference, optional project name, product/service reference, hours worked (decimal), hourly rate, description, and billable flag
2. THE ZZP_Module SHALL include an `administration` field on Time_Entry records for multi-tenant isolation
3. THE ZZP_Module SHALL calculate the monetary value of a Time_Entry as hours multiplied by hourly rate
4. THE ZZP_Module SHALL link Time_Entry records to Product_Registry line items so that hours map directly to invoiceable products/services
5. WHEN generating an invoice for a contact, THE ZZP_Module SHALL allow selecting unbilled Time_Entry records to include as invoice line items
6. WHEN Time_Entry records are added to an invoice, THE ZZP_Module SHALL mark those Time_Entry records as billed with a reference to the invoice
7. THE ZZP_Module SHALL provide a summary view of hours per contact, per project, and per period (week, month, quarter, year)
8. THE ZZP_Module SHALL support uploading supporting documents (e.g., client timesheets, contracts, delivery confirmations) and linking them to a contact, invoice, or billing period
9. WHEN sending an invoice, THE ZZP_Module SHALL allow selecting linked supporting documents to attach alongside the invoice PDF
10. THE ZZP_Module SHALL store uploaded supporting documents using the existing `OutputService` (Google Drive) and maintain references on the invoice record

#### Time Entry Input Methods (incremental)

11. **Manual entry (Phase 1):** THE ZZP_Module SHALL support manual entry of hours linked to a contact and product/service line, with optional project name and description
12. **Client timesheet import (Phase 2):** THE ZZP_Module SHALL support uploading a client-provided timesheet (PDF/Excel) and creating Time_Entry records from it, linked to the corresponding contact
13. **(Phase 3):** THE ZZP_Module SHALL support importing calendar events from Google Calendar or Apple Calendar (via iCal/ICS format) and converting selected events into Time_Entry records, mapping calendar entries to contacts and products/services

### Requirement 12: Debtor and Creditor Management (Debiteuren/Crediteurenbeheer)

**User Story:** As a ZZP user, I want an overview of outstanding receivables and payables, so that I can manage my cash flow and send payment reminders.

#### Acceptance Criteria

1. THE ZZP_Module SHALL provide an accounts receivable overview listing all outgoing invoices with status 'sent' or 'overdue', grouped by contact
2. THE ZZP_Module SHALL provide an accounts payable overview listing all incoming invoices with unpaid status, grouped by contact
3. WHEN an outgoing invoice's due date has passed and the Invoice_Status is 'sent', THE ZZP_Module SHALL automatically update the Invoice_Status to 'overdue'
4. THE ZZP_Module SHALL calculate the total outstanding amount per contact and overall for both receivables and payables
5. THE ZZP_Module SHALL support sending payment reminder emails for overdue invoices using the Email_Sender
6. THE ZZP_Module SHALL provide an aging analysis showing outstanding amounts in buckets: current, 1-30 days overdue, 31-60 days overdue, 61-90 days overdue, and 90+ days overdue

### Requirement 13: Recurring Invoices

**User Story:** As a ZZP user, I want to create follow-up invoices for recurring clients with minimal effort, so that I only need to confirm or adjust what changed since the last invoice.

#### Acceptance Criteria

1. THE Invoice_Engine SHALL support creating Recurring_Invoice configurations with: contact reference, line items (as template), interval (weekly, monthly, quarterly, yearly), start date, optional end date, and active status
2. WHEN a Recurring_Invoice's next scheduled date is reached, THE Invoice_Engine SHALL generate a new invoice in 'draft' status pre-filled with the line items from the previous invoice for that contact
3. THE Invoice_Engine SHALL present the pre-filled draft to the user showing only the fields that typically change: invoice date, period, and hours/quantities per line item
4. THE Invoice_Engine SHALL auto-advance the invoice date and period based on the configured interval, requiring no manual date entry for standard cases
5. WHEN the user confirms a recurring draft, THE Invoice_Engine SHALL only require input for changed values; unchanged line items (description, rate, VAT code) SHALL carry over automatically
6. THE Invoice_Engine SHALL allow adding, removing, or modifying line items on a recurring draft before finalizing
7. THE Invoice_Engine SHALL calculate the next scheduled date based on the interval from the previous generation date
8. WHILE a Recurring_Invoice is active and has no end date, THE Invoice_Engine SHALL continue generating invoices indefinitely at the configured interval
9. WHEN a Recurring_Invoice has an end date that has passed, THE Invoice_Engine SHALL stop generating new invoices and mark the configuration as inactive
10. THE Invoice_Engine SHALL filter all Recurring_Invoice configurations by the Tenant's `administration` field

### Requirement 14: Multi-Currency Support

**User Story:** As a ZZP user, I want to create invoices in different currencies, so that I can bill international clients in their preferred currency.

#### Acceptance Criteria

1. THE Invoice_Engine SHALL support specifying a currency code (ISO 4217) per invoice, defaulting to the Tenant's configured default currency (EUR)
2. THE Invoice_Engine SHALL store the exchange rate used at the time of invoice creation for non-default currencies
3. WHEN booking a non-default currency invoice in FIN, THE Invoice_Booking_Helper SHALL convert amounts to the Tenant's default currency using the stored exchange rate
4. THE Invoice_Engine SHALL display invoice amounts in the invoice's specified currency on the PDF and in the UI
5. THE ZZP_Module SHALL display receivable and payable overviews in the Tenant's default currency, converting outstanding foreign currency amounts using stored exchange rates

### Requirement 15: Invoice Archival and Document Storage

**User Story:** As a ZZP user, I want generated invoices to be archived and accessible, so that I can retrieve them for the retention period defined in the tenant parameters.

#### Acceptance Criteria

1. WHEN an invoice PDF is generated, THE Invoice_Engine SHALL store the document using the existing `OutputService`, supporting all storage platforms configured for invoices in FIN (Google Drive, S3 shared bucket, S3 tenant-specific bucket)
2. THE Invoice_Engine SHALL store the storage URL in `Ref3` and the document filename in `Ref4` on the corresponding `mutaties` entry using the existing FIN transaction logic, maintaining the link between the invoice and the stored PDF document
3. WHEN a user requests a previously generated invoice, THE Invoice_Engine SHALL retrieve the stored document via the storage URL in `Ref3` of the `mutaties` entry
4. IF the stored document is unavailable, THE Invoice_Engine SHALL support generating a copy invoice marked as "COPY" based on available data in the invoice tables and `mutaties` entries
5. THE Invoice_Engine SHALL retain invoice documents for the retention period defined in the tenant parameters, defaulting to 7 years if not configured

### Requirement 16: Parameter Table Column Filtering

**User Story:** As a tenant administrator, I want to filter the Advanced Parameters table by any column, so that I can quickly find specific parameters in a large list.

**Implementation pattern:** Follow the BankingProcessor `columnFilters` pattern — inline `Input size="xs"` elements in a second `<Tr>` row inside `<Thead>`, with debounced state updates (150ms). Reference: `frontend/src/components/BankingProcessor.tsx` columnFilters implementation and `.kiro/steering/ui-patterns.md` Filters section.

#### Acceptance Criteria

1. THE Parameter_Table UI SHALL add a second header row with `Input size="xs"` filter fields for each visible column (namespace, key, value, type, scope), following the BankingProcessor columnFilters pattern
2. THE Parameter_Table UI SHALL debounce filter input changes (150ms) before applying them to the displayed rows, consistent with the BankingProcessor pattern
3. WHEN a user enters text in a column filter, THE Parameter_Table UI SHALL filter the displayed rows client-side using case-insensitive substring matching (AND logic across all active filters)
4. THE Parameter_Table UI SHALL remove the existing namespace dropdown filter, replacing it with the per-column inline filters which provide the same functionality via the namespace column filter

### Requirement 17: ZZP Invoice Ledger Parameter

**User Story:** As a tenant administrator, I want to flag specific revenue accounts in the chart of accounts as available for ZZP invoicing, so that users can select the appropriate revenue ledger when creating invoices.

**Implementation pattern:** Follow the existing `ledger_parameters.json` pattern — add a new entry alongside `bank_account`, `asset_account`, etc. The key is stored as a boolean in `rekeningschema.parameters` JSON column (e.g., `{"zzp_invoice_ledger": true}`). The Account Modal already renders parameter toggles from this registry. Reference: `backend/src/config/ledger_parameters.json`.

#### Acceptance Criteria

1. THE Ledger_Parameter_Registry (`ledger_parameters.json`) SHALL include a new entry `{ "key": "zzp_invoice_ledger", "type": "boolean", "label_en": "ZZP Invoice Ledger", "label_nl": "ZZP Factuur Grootboek", "module": "ZZP" }`, following the same structure as `bank_account` and `asset_account`
2. WHEN a tenant administrator edits an account in the Chart_of_Accounts modal, THE parameter toggle for `zzp_invoice_ledger` SHALL appear automatically (rendered from the registry), allowing the administrator to set it to true or false
3. THE ZZP_Module SHALL provide an API endpoint that returns all accounts from the Chart_of_Accounts where `JSON_EXTRACT(parameters, '$.zzp_invoice_ledger') = true` for the requesting Tenant
4. IF no accounts have `zzp_invoice_ledger` set to true for a Tenant, THEN THE ZZP_Module SHALL fall back to the `zzp.revenue_account` parameter value (default 8001)

### Requirement 18: Invoice Revenue Account Selection

**User Story:** As a ZZP user, I want to select the revenue account (credit account) when creating an invoice, so that I can book different types of work to different revenue ledgers.

#### Acceptance Criteria

1. WHEN creating or editing a draft invoice, THE Invoice_Engine SHALL display a dropdown listing all accounts flagged with `zzp_invoice_ledger` in the Chart_of_Accounts for the Tenant
2. THE Invoice_Engine SHALL default the revenue account dropdown to the `zzp.revenue_account` parameter value (default 8001) when creating a new invoice
3. WHEN the user selects a revenue account from the dropdown, THE Invoice_Engine SHALL store the selected account code on the invoice record
4. WHEN booking an outgoing invoice, THE Invoice_Booking_Helper SHALL use the revenue account stored on the invoice record instead of the global `zzp.revenue_account` parameter
5. WHEN booking VAT entries for an outgoing invoice, THE Invoice_Booking_Helper SHALL use the invoice's stored revenue account as the debit account for VAT lines
6. WHEN booking a Credit_Note, THE Invoice_Booking_Helper SHALL use the revenue account from the original invoice for the reversal entries

### Requirement 19: Parameter-Driven Booking Accounts

**User Story:** As a tenant administrator, I want all ZZP booking accounts (debtor, creditor, revenue, VAT) to be driven by parameters and selectable from the chart of accounts, so that no account codes are hardcoded.

**Implementation pattern:** Follow the existing `ledger_parameters.json` pattern. Add `zzp_debtor_account` and `zzp_creditor_account` as boolean keys (same as `bank_account`, `asset_account`). These flags mark accounts in `rekeningschema.parameters` as eligible for selection. The `zzp.debtor_account` and `zzp.creditor_account` parameters in `ParameterService` store the selected account code. The booking helper reads from `ParameterService` with no hardcoded fallbacks. Reference: `backend/src/config/ledger_parameters.json`, `backend/src/services/invoice_booking_helper.py`.

#### Acceptance Criteria

1. THE Ledger_Parameter_Registry (`ledger_parameters.json`) SHALL include new entries `zzp_debtor_account` (boolean, module ZZP, label "ZZP Debtor Account" / "ZZP Debiteurenrekening") and `zzp_creditor_account` (boolean, module ZZP, label "ZZP Creditor Account" / "ZZP Crediteurenrekening"), following the same structure as `bank_account` and `asset_account`
2. THE Invoice_Booking_Helper SHALL read the debtor account from `zzp.debtor_account` parameter and the creditor account from `zzp.creditor_account` parameter, with no hardcoded fallback values in the `_get_param` method
3. THE Invoice_Booking_Helper SHALL read the default revenue account from `zzp.revenue_account` parameter, with no hardcoded fallback value
4. THE ZZP_Module SHALL read VAT ledger accounts from the TaxRateService, which resolves accounts from the `tax_rates` table parameters
5. IF a required booking account parameter (`zzp.debtor_account`, `zzp.creditor_account`, or `zzp.revenue_account`) is not configured for a Tenant, THEN THE Invoice_Booking_Helper SHALL raise a descriptive error indicating which parameter is missing, rather than silently using a default
6. WHEN a tenant administrator configures `zzp.debtor_account` or `zzp.creditor_account`, THE ZZP_Module SHALL validate that the account code exists in the Tenant's Chart_of_Accounts via `JSON_EXTRACT(parameters, '$.zzp_debtor_account') = true` or `JSON_EXTRACT(parameters, '$.zzp_creditor_account') = true` respectively

### Requirement 20: Invoice PDF Header Details

**User Story:** As a ZZP user, I want the invoice PDF to include complete header details for both my company and the client, so that the invoice meets legal and professional standards.

**Implementation pattern:** Currently the `branding` namespace in `parameter_schema.py` is shared across all modules (STR invoices also read from it). ZZP needs its own branding namespace (`zzp_branding`) so ZZP and STR can have different company details and logos. The existing `branding` namespace should be renamed to `str_branding` for STR-specific use. The invoice HTML template is editable via the existing Template Management tab. Reference: `backend/src/services/parameter_schema.py`, `backend/src/services/pdf_generator_service.py`, `frontend/src/components/TenantAdmin/TemplateManagement/`.

#### Acceptance Criteria

1. THE parameter_schema SHALL define a new `zzp_branding` namespace (module: ZZP) with keys: `company_logo_file_id`, `company_name`, `company_address`, `company_postal_city`, `company_country`, `company_vat`, `company_coc`, `company_iban`, `company_phone`, `contact_email` — following the same structure as the current `branding` namespace
2. THE existing `branding` namespace SHALL be renamed to `str_branding` (module: STR) so STR invoices use their own branding parameters, and the STR invoice generator SHALL be updated to read from `str_branding` instead of `branding`
3. THE PDF_Generator SHALL read the Tenant's company details from `zzp_branding.*` parameters via `_get_branding()`, and render the tenant logo via `_get_tenant_logo()` reading `zzp_branding.company_logo_file_id`
4. THE PDF_Generator SHALL include the client's details in the invoice header: company name, contact person, street address, postal code, city, country, and VAT number, sourced from the Contact_Registry
5. IF a Tenant has not configured `zzp_branding` parameters, THEN THE PDF_Generator SHALL omit the missing fields from the header rather than displaying empty placeholders
6. THE PDF_Generator SHALL position the Tenant's details as the sender and the client's details as the recipient, following the layout defined in the `zzp_invoice` template (editable via Template Management)
7. THE default `zzp_invoice_default.html` template SHALL be registered as a template type in Template Management so tenants can customize the invoice layout, header positioning, and styling

### Requirement 21: Locale-Aware Invoice Formatting

**User Story:** As a ZZP user, I want invoice formatting (dates, currency, numbers) to match the client's country conventions, so that invoices are readable and professional for international clients.

#### Acceptance Criteria

1. WHEN generating an invoice PDF, THE PDF_Generator SHALL format dates according to the locale derived from the client's country in the Contact_Registry (e.g., dd-MM-yyyy for NL, MM/dd/yyyy for US, dd/MM/yyyy for UK)
2. WHEN generating an invoice PDF, THE PDF_Generator SHALL format currency amounts according to the locale derived from the client's country (e.g., € 1.250,00 for NL, €1,250.00 for US/UK)
3. WHEN generating an invoice PDF, THE PDF_Generator SHALL format decimal numbers (quantities, rates) according to the locale derived from the client's country (e.g., comma as decimal separator for NL, period for US/UK)
4. IF the client's country is not set in the Contact_Registry, THEN THE PDF_Generator SHALL default to Dutch (NL) locale formatting
5. THE PDF_Generator SHALL use the invoice's currency code (ISO 4217) for the currency symbol, independent of the locale used for number formatting

### Requirement 22: Storage URL and Filename in Mutaties Ref3/Ref4

**User Story:** As a ZZP user, I want the storage URL and filename to be written to the Ref3 and Ref4 fields when an invoice is sent, and I want the send operation to fail cleanly if storage is unavailable, so that my financial records are always complete and consistent.

**Implementation pattern:** The send flow must follow a strict order: **store PDF → book mutaties → send email**. Storage failure is a hard stop (invoice stays draft). Email failure is a soft failure (invoice is booked, user resends manually). A pre-flight storage health check on the send endpoint catches issues before the flow starts. Reference: `backend/src/services/zzp_invoice_service.py` `send_invoice()`, `backend/src/services/invoice_booking_helper.py`.

#### Acceptance Criteria

1. THE Invoice_Engine `send_invoice` flow SHALL execute in strict order: (1) generate PDF, (2) store PDF via OutputService, (3) book mutaties entries with Ref3/Ref4, (4) optionally send email
2. WHEN the PDF is stored successfully, THE Invoice_Engine SHALL write the storage URL to `Ref3` and the PDF filename (e.g., `INV-2026-0003.pdf`) to `Ref4` on all corresponding `mutaties` entries for that invoice
3. WHEN a credit note is sent, THE Invoice_Engine SHALL write the storage URL to `Ref3` and the PDF filename to `Ref4` on all corresponding `mutaties` entries for that credit note
4. THE Invoice_Engine SHALL pass the storage result (containing both URL and filename) from the OutputService to the Invoice_Booking_Helper before booking entries are created
5. IF the OutputService fails to store the PDF (storage error, connectivity issue, or no URL returned), THEN THE Invoice_Engine SHALL abort the send operation, keep the invoice status as `draft`, return a descriptive error to the user (e.g., "Storage unavailable — invoice not sent"), and SHALL NOT create any `mutaties` entries
6. IF the email sending fails after successful storage and booking, THEN THE Invoice_Engine SHALL keep the invoice status as `sent` (financial records are complete), log the email error, and return a warning to the user indicating the invoice was booked but the email needs to be resent manually
7. THE Invoice_Engine SHALL perform a pre-flight storage health check at the start of the `send_invoice` flow by calling `OutputService.check_health()` (a lightweight connectivity test to the configured storage provider), and SHALL abort with a descriptive error if the health check fails
