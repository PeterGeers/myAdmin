# Tasks — ZZP Module

## Phase 1: Foundation — Database, Module Registration & Shared Services

> Estimated: 3–4 days | Dependencies: FIN module active | Reqs: 1, 2, 3

### 1.1 Database Migration

- [x] Create `backend/sql/phase_zzp_tables.sql` with all tables in FK order: `contacts`, `contact_emails`, `products`, `invoices`, `invoice_lines`, `vw_invoice_vat_summary` (view), `invoice_number_sequences`, `time_entries`
- [x] Run migration against dev database and verify all tables, indexes, and FK constraints
- [x] Add `INSERT INTO tenant_modules` seed statement for test tenant

### 1.2 Module Registration

- [x] Add `'ZZP'` entry to `MODULE_REGISTRY` in `backend/src/services/module_registry.py` with `depends_on: ['FIN']`, all `required_params` (invoice prefix, credit note prefix, payment terms, currency, padding, debtor/creditor accounts, email subject, BCC, retention years, time tracking enabled, product types, contact types, field configs), `required_tax_rates`, and `required_roles`
- [x] Implement dependency enforcement: ZZP cannot activate unless FIN is active for the tenant
- [x] Verify `@module_required('ZZP')` returns HTTP 403 when ZZP is not enabled

### 1.3 Field Config Mixin

- [x] Create `backend/src/services/field_config_mixin.py` with `FieldConfigMixin` class: `get_field_config()`, `validate_fields()`, `strip_hidden_fields()`
- [x] Unit test: required field missing → `ValueError`; hidden fields stripped from response; `ALWAYS_REQUIRED` fields cannot be overridden to hidden

### 1.4 Contact Service (Backend)

- [x] Create `backend/src/services/contact_service.py` with `ContactService(FieldConfigMixin)`: `list_contacts`, `get_contact`, `get_contact_by_client_id`, `create_contact`, `update_contact`, `soft_delete_contact`, `get_invoice_email`, `get_contact_types`, `_validate_contact_type`, `_check_contact_in_use`
- [x] Enforce `client_id` uniqueness within tenant, validate `contact_type` against `zzp.contact_types` parameter set
- [x] Handle `contact_emails` sub-table: create/update/delete emails with contact, support `email_type` (general/invoice/other) and `is_primary` flag
- [x] `get_invoice_email`: return email with `email_type='invoice'`, fallback to `is_primary=True`
- [x] `soft_delete_contact`: check `_check_contact_in_use` (query `invoices` table) before deactivating
- [x] Unit tests for CRUD, uniqueness, soft-delete protection, email fallback logic

### 1.5 Contact Routes (Backend)

- [x] Create `backend/src/routes/contact_routes.py` with `contact_bp` blueprint
- [x] Implement endpoints: `GET /api/contacts` (list, filter by type), `GET /api/contacts/<id>`, `POST /api/contacts`, `PUT /api/contacts/<id>`, `DELETE /api/contacts/<id>`, `GET /api/contacts/types`
- [x] Apply decorator chain: `@cognito_required()` → `@tenant_required()` → `@module_required('ZZP')`
- [x] Register blueprint in `app.py`

### 1.6 Product Service (Backend)

- [x] Create `backend/src/services/product_service.py` with `ProductService(FieldConfigMixin)`: `list_products`, `get_product`, `get_product_by_code`, `create_product`, `update_product`, `soft_delete_product`, `get_product_types`, `_validate_vat_code`, `_validate_product_type`
- [x] Validate `vat_code` via `TaxRateService` (only high/low/zero), validate `product_type` against `zzp.product_types` parameter set
- [x] Enforce `product_code` uniqueness within tenant
- [x] `soft_delete_product`: check usage in `invoice_lines` before deactivating
- [x] Unit tests for CRUD, VAT code validation, product type validation, soft-delete protection

### 1.7 Product Routes (Backend)

- [x] Create `backend/src/routes/product_routes.py` with `product_bp` blueprint
- [x] Implement endpoints: `GET /api/products`, `GET /api/products/<id>`, `POST /api/products`, `PUT /api/products/<id>`, `DELETE /api/products/<id>`, `GET /api/products/types`
- [x] Apply decorator chain, register blueprint in `app.py`

### 1.8 Field Config API

- [x] Add `GET /api/zzp/field-config/<entity>` and `PUT /api/zzp/field-config/<entity>` to ZZP routes
- [x] `GET` returns merged config (defaults + tenant overrides) for entity (contacts/products/invoices/time_entries)
- [x] `PUT` requires `zzp_tenant` permission, validates that `ALWAYS_REQUIRED` fields stay required

### Phase 1 Testing

- [x] API tests for contact CRUD (create, read, update, soft-delete, uniqueness, email handling)
- [x] API tests for product CRUD (create, read, update, soft-delete, VAT validation, type validation)
- [x] API tests for field config endpoints
- [x] API tests for module gating (403 when ZZP not enabled, 403 when FIN not active)

---

## Phase 2: Invoice Engine — Core CRUD, Numbering & Calculations

> Estimated: 3–4 days | Dependencies: Phase 1 | Reqs: 4, 5, 14

### 2.1 Invoice Number Generation

- [x] Create `invoice_number_sequences` logic in `ZZPInvoiceService._generate_invoice_number()` with `SELECT ... FOR UPDATE` row-level locking
- [x] Read prefix from `zzp.invoice_prefix` parameter, padding from `zzp.invoice_number_padding`
- [x] Format: `{PREFIX}-{YEAR}-{SEQUENCE}` (e.g., `INV-2026-0001`)
- [x] Unit test: sequential numbering, concurrent safety (two requests same tenant/year), year rollover

### 2.2 Invoice Service — CRUD

- [x] Create `backend/src/services/zzp_invoice_service.py` with `ZZPInvoiceService(FieldConfigMixin)`
- [x] `create_invoice`: validate contact exists, generate invoice number, calculate due_date from `payment_terms_days`, insert header + lines, calculate totals
- [x] `update_invoice`: only allow when `status='draft'`, validate and recalculate lines/totals
- [x] `get_invoice`: return header + lines + VAT summary (from `vw_invoice_vat_summary`) + contact info
- [x] `list_invoices`: support filters (status, contact_id, date range, invoice_type), pagination with `LIMIT/OFFSET`

### 2.3 Line Calculations

- [x] `_calculate_line`: lookup VAT rate via `TaxRateService.get_tax_rate(tenant, 'btw', vat_code, invoice_date)`, compute `line_total = quantity * unit_price`, `vat_amount = line_total * vat_rate / 100`
- [x] `_calculate_totals`: sum line totals → subtotal, sum VAT amounts → vat_total, subtotal + vat_total → grand_total; update invoice header; read `vw_invoice_vat_summary` for grouped VAT breakdown
- [x] Unit tests: single line, multiple lines with different VAT rates, zero-rate lines, rounding

### 2.4 Multi-Currency Support

- [x] Default currency from `zzp.default_currency` parameter (EUR)
- [x] Store `currency` and `exchange_rate` on invoice header
- [x] Exchange rate manually entered at invoice creation for non-default currencies
- [x] Conversion to default currency happens at booking time (Phase 3)

### 2.5 Invoice Routes

- [x] Add to `backend/src/routes/zzp_routes.py`: `GET /api/zzp/invoices`, `GET /api/zzp/invoices/<id>`, `POST /api/zzp/invoices`, `PUT /api/zzp/invoices/<id>`
- [x] Apply decorator chain on all routes
- [x] Register ZZP blueprint in `app.py` (if not already done)

### Phase 2 Testing

- [x] API tests for invoice CRUD (create draft, update draft, get with lines, list with filters)
- [x] Unit tests for invoice number generation (sequential, concurrent, year rollover)
- [x] Unit tests for line/total calculations (VAT rates, rounding, multi-line, zero-rate)
- [x] Test that sent invoices cannot be edited (financial fields locked)

---

## Phase 3: Invoice Lifecycle — Booking, PDF, Email & Send Flow

> Estimated: 4–5 days | Dependencies: Phase 2 | Reqs: 6, 8, 9

### 3.1 Invoice Booking Helper

- [x] Create `backend/src/services/invoice_booking_helper.py` with `InvoiceBookingHelper`
- [x] `book_outgoing_invoice`: debit debtor account (`zzp.debtor_account`), credit revenue account; separate entries per VAT rate bucket from `vw_invoice_vat_summary`; set `ReferenceNumber` = contact's `client_id`, `Ref2` = invoice number, `Ref3` = PDF URL, `Ref4` = filename
- [x] `book_incoming_invoice`: debit expense account, credit creditor account (`zzp.creditor_account`); single VAT line for total VAT
- [x] Use `TransactionLogic.save_approved_transactions()` pattern for writing to `mutaties`
- [x] Skip zero-amount lines (Req 6.10)
- [x] Multi-currency: convert amounts using stored `exchange_rate` when currency ≠ default
- [x] Unit tests: outgoing booking entries (correct accounts, amounts, references), incoming booking, zero-VAT skip, multi-currency conversion

### 3.2 PDF Generator Service

- [x] Create `backend/src/services/pdf_generator_service.py` with `PDFGeneratorService`
- [x] Add `weasyprint>=60.0` to `requirements.txt`
- [x] Create default invoice HTML template at `backend/src/templates/zzp_invoice_default.html` (A4, company logo, contact details, line items table, VAT summary, payment details with Client_ID, totals)
- [x] `generate_invoice_pdf`: load template via `TemplateService`, render with invoice data, inject tenant logo, convert to PDF via `weasyprint.HTML(string=html).write_pdf()`, return `BytesIO`
- [x] `generate_copy_invoice_pdf`: same as above but with "COPY" watermark
- [x] `_get_tenant_logo`: read from tenant config/parameter
- [x] Handle missing logo gracefully (no placeholder)
- [x] Unit tests: PDF generation produces valid bytes, template rendering with all fields, logo present/absent

### 3.3 SES Email Extension

- [x] Add `send_email_with_attachments()` method to existing `SESEmailService` using `send_raw_email` with MIME multipart
- [x] Support PDF attachment + optional additional attachments
- [x] Support BCC parameter for tenant copy
- [x] Unit test: MIME message construction, attachment encoding, BCC handling

### 3.4 Invoice Email Service

- [x] Create `backend/src/services/invoice_email_service.py` with `InvoiceEmailService`
- [x] `send_invoice_email`: get recipient via `ContactService.get_invoice_email()` (invoice email → fallback general), build subject from `zzp.email_subject_template`, build HTML body from template, attach PDF + optional supporting docs, include BCC from `zzp.invoice_email_bcc`
- [x] `send_reminder_email`: similar flow with reminder template
- [x] On success: update invoice status to 'sent', record `sent_at`
- [x] On failure: log error, keep status as 'draft', return error message
- [x] Unit tests: email construction, recipient fallback, success/failure status handling

### 3.5 Send Invoice Flow

- [x] Implement `send_invoice` in `ZZPInvoiceService`: assert draft status → generate PDF → store via `OutputService` → book in FIN → optionally send email → update status to 'sent'
- [x] Add `POST /api/zzp/invoices/<id>/send` route with request body `{ output_destination, send_email }`
- [x] Add `GET /api/zzp/invoices/<id>/pdf` route for PDF download/regeneration

### 3.6 Invoice Storage

- [x] Store generated PDF via `OutputService` (Google Drive /s3 shared, S3 per tenant config)
- [x] Store URL in `mutaties.Ref3`, filename in `mutaties.Ref4` via booking helper
- [x] Retrieval: query `mutaties` by `Ref2` (invoice number) + `ReferenceNumber` (client_id)
- [x] Fallback: regenerate copy PDF marked "COPY" if stored document unavailable

### Phase 3 Testing

- [x] Integration test: full send flow (draft → PDF → book → email → sent status)
- [x] API test: send endpoint, PDF download endpoint
- [x] Unit tests for booking helper (correct mutaties entries, references, zero-skip)
- [x] Unit tests for PDF generation and email sending

---

## Phase 4: Credit Notes, Payment Checking & Debtor Management

> Estimated: 3–4 days | Dependencies: Phase 3 | Reqs: 7, 10, 12

### 4.1 Credit Notes

- [x] Implement `create_credit_note` in `ZZPInvoiceService`: copy lines from original with negated amounts, assign CN number using `zzp.credit_note_prefix` (e.g., `CN-2026-0001`), link to original via `original_invoice_id`
- [x] Implement `book_credit_note` in `InvoiceBookingHelper`: create reversal entries in `mutaties` offsetting original booking
- [x] On send: book reversal, update original invoice status to 'credited'
- [x] Add `POST /api/zzp/invoices/<id>/credit` route
- [x] Unit tests: credit note creation (negated amounts, correct numbering), reversal booking entries, original status update

### 4.2 Payment Check Helper

- [x] Create `backend/src/services/payment_check_helper.py` with `PaymentCheckHelper`
- [x] `run_payment_check`: query recent bank transactions from `mutaties`, extract `ReferenceNumber` (= client_id), match against open invoices (status 'sent'/'overdue')
- [x] Exact match (within €0.01 tolerance): update invoice status to 'paid'
- [x] Partial match: record partial payment, keep status as 'sent'
- [x] Add `POST /api/zzp/payment-check/run` and `GET /api/zzp/payment-check/status` routes
- [x] Unit tests: exact match, partial match, no match, tolerance boundary

### 4.3 Overdue Detection

- [x] Implement `mark_overdue` in `ZZPInvoiceService`: batch update all invoices where `status='sent'` and `due_date < CURDATE()`
- [x] Can be triggered manually via payment check or scheduled (cron/manual trigger)

### 4.4 Debtor/Creditor Service & Routes

- [x] Add debtor/creditor endpoints to `zzp_routes.py`: `GET /api/zzp/debtors/receivables`, `GET /api/zzp/debtors/payables`, `GET /api/zzp/debtors/aging`, `POST /api/zzp/debtors/send-reminder/<id>`
- [x] Receivables: list outgoing invoices with status 'sent'/'overdue', grouped by contact (filter `contact_type` = client/both)
- [x] Payables: list incoming invoices with unpaid status, grouped by contact (filter `contact_type` = supplier/both)
- [x] Aging analysis: single query with `DATEDIFF` buckets (current, 1–30, 31–60, 61–90, 90+), total per contact and overall
- [x] Send reminder: use `InvoiceEmailService.send_reminder_email()` for overdue invoices

### Phase 4 Testing

- [x] Unit tests for credit note creation and reversal booking
- [x] Unit tests for payment matching (exact, partial, tolerance)
- [x] API tests for debtor/creditor endpoints (receivables, payables, aging)
- [x] API test for send reminder endpoint
- [x] Integration test: invoice → overdue → reminder flow

---

## Phase 5: Time Tracking

> Estimated: 2–3 days | Dependencies: Phase 2 (invoices exist) | Reqs: 11

### 5.1 Time Tracking Service (Backend)

- [x] Create `backend/src/services/time_tracking_service.py` with `TimeTrackingService(FieldConfigMixin)`
- [x] `create_entry`: validate contact exists, validate product if provided, calculate monetary value (hours × rate), insert with `is_billable` default true
- [x] `update_entry`: only allow if `is_billed=False`
- [x] `delete_entry`: only allow if `is_billed=False`
- [x] `list_entries`: support filters (contact_id, project_name, date range, is_billable, is_billed), pagination
- [x] `get_unbilled_entries`: return unbilled billable entries for a contact
- [x] `mark_as_billed`: set `is_billed=True` and `invoice_id` on selected entries
- [x] `get_summary`: group by contact/project/period (week/month/quarter/year), return hours + monetary totals
- [x] Respect `zzp.time_tracking_enabled` parameter — return 404 when disabled

### 5.2 Time Tracking Routes

- [x] Add to `zzp_routes.py`: `GET /api/zzp/time-entries`, `POST /api/zzp/time-entries`, `PUT /api/zzp/time-entries/<id>`, `DELETE /api/zzp/time-entries/<id>`, `GET /api/zzp/time-entries/summary`
- [x] Apply decorator chain on all routes

### 5.3 Invoice from Time Entries

- [x] Implement `create_invoice_from_time_entries` in `ZZPInvoiceService`: accept contact_id + entry_ids, create draft invoice with lines from selected time entries, mark entries as billed
- [x] Map time entry → invoice line: product_id, description, quantity=hours, unit_price=hourly_rate, vat_code from product

### 5.4 Supporting Document Upload

- [x] Add endpoint for uploading supporting documents linked to contact/invoice/period
- [x] Store via `OutputService` (Google Drive), maintain references on invoice record
- [x] When sending invoice, allow selecting linked documents as additional attachments

### Phase 5 Testing

- [x] Unit tests for time entry CRUD (create, update, delete, billed protection)
- [x] Unit tests for summary grouping (by contact, project, period)
- [x] API tests for time entry endpoints
- [x] Integration test: time entries → create invoice → entries marked as billed

---

## Phase 6: Recurring Invoices (Copy Last Invoice)

> Estimated: 1–2 days | Dependencies: Phase 2 | Reqs: 13

### 6.1 Copy Last Invoice Logic

- [x] Implement `copy_last_invoice` in `ZZPInvoiceService`: query most recent invoice for contact, copy header + lines into new draft, auto-advance date
- [x] `_advance_date`: calculate next date based on gap between last two invoices for the contact (default: +1 month if only one invoice exists)
- [x] Set `copied_from_invoice_id` on response for UI reference

### 6.2 Copy Last Invoice Route

- [x] Add `POST /api/zzp/invoices/copy-last/<contact_id>` to `zzp_routes.py`
- [x] Return new draft invoice pre-filled from last invoice

### Phase 6 Testing

- [x] Unit test: copy logic (lines copied, date advanced, amounts preserved)
- [x] Unit test: no previous invoice → error
- [x] API test: copy-last endpoint returns valid draft

---

## Phase 7: Frontend — Shared Components & Types

> Estimated: 2–3 days | Dependencies: Phase 1 backend complete | Reqs: all frontend

### 7.1 TypeScript Types

- [x] Create `frontend/src/types/zzp.ts` with all interfaces: `Contact`, `ContactEmail`, `Product`, `Invoice`, `InvoiceLine`, `VatSummaryLine`, `TimeEntry`, `InvoiceStatus`, `InvoiceType`, `ContactType`

### 7.2 Frontend Service Layer

- [x] Create `frontend/src/services/contactService.ts` — CRUD calls for contacts
- [x] Create `frontend/src/services/productService.ts` — CRUD calls for products
- [x] Create `frontend/src/services/zzpInvoiceService.ts` — invoice CRUD, send, credit, copy-last, PDF download
- [x] Create `frontend/src/services/timeTrackingService.ts` — time entry CRUD, summary
- [x] Create `frontend/src/services/debtorService.ts` — receivables, payables, aging, send reminder
- [x] Create `frontend/src/services/fieldConfigService.ts` — get/update field config per entity

### 7.3 Shared Hooks & Components

- [x] Create `frontend/src/hooks/useFieldConfig.ts` — fetch field config, expose `isVisible()`, `isRequired()`, `loading`
- [x] Create `frontend/src/components/zzp/InvoiceStatusBadge.tsx` — status badge with color mapping (draft=gray, sent=blue, paid=green, overdue=red, credited=purple)
- [x] Create `frontend/src/components/zzp/InvoiceLineEditor.tsx` — editable line items table with product lookup, quantity, price, VAT code, calculated totals
- [x] Create `frontend/src/components/zzp/AgingChart.tsx` — stacked bar chart (Recharts) for aging analysis

### 7.4 i18n Keys

- [x] Add `zzp` namespace translation keys (NL + EN) for all UI labels: invoices, contacts, products, time tracking, debtors, statuses, types, actions

---

## Phase 8: Frontend — Pages & Modals

> Estimated: 4–5 days | Dependencies: Phase 7, backend Phases 1–4 | Reqs: all frontend

### 8.1 Navigation & Routing

- [x] Add ZZP navigation section (visible only when ZZP module enabled for tenant)
- [x] Add routes: `/zzp/invoices`, `/zzp/invoices/:id`, `/zzp/time-tracking`, `/zzp/contacts`, `/zzp/products`, `/zzp/debtors`
- [x] Protect routes with `ProtectedRoute` requiring `zzp_read` permission

### 8.2 Contacts Page

- [x] Create `frontend/src/pages/ZZPContacts.tsx` — table with client_id, company_name, contact_type badge, contact_person, city, phone; filter by contact_type; row-click opens modal
- [x] Create `frontend/src/components/zzp/ContactModal.tsx` — Formik form with field visibility via `useFieldConfig('contacts')`, email sub-table for multiple emails with type indicator

### 8.3 Products Page

- [x] Create `frontend/src/pages/ZZPProducts.tsx` — table with product_code, name, type badge, unit_price, vat_code, unit_of_measure, external_reference, active; row-click opens modal
- [x] Create `frontend/src/components/zzp/ProductModal.tsx` — Formik form with field visibility, product type dropdown from API, VAT code dropdown (high/low/zero)

### 8.4 Invoices Page

- [x] Create `frontend/src/pages/ZZPInvoices.tsx` — table with invoice number, contact, date, due date, status badge, grand total; filter by status/contact/date range; header actions: new invoice, export, copy last
- [x] Create `frontend/src/pages/ZZPInvoiceDetail.tsx` — full invoice view with `InvoiceLineEditor`, VAT summary, totals; editable when draft, read-only when sent/paid
- Create `frontend/src/components/zzp/InvoiceDetailModal.tsx` — modal wrapper for invoice detail with send/credit actions

### 8.5 Time Tracking Page

- [x] ### 8.5 Time Tracking Page
- Create `frontend/src/pages/ZZPTimeTracking.tsx` — mobile-first design: responsive card layout on small screens, table on desktop; quick-add flow (contact + hours + date); summary tabs with Recharts bar chart
- Create `frontend/src/components/zzp/TimeEntryModal.tsx` — Formik form with contact dropdown, product dropdown, date, hours, rate, project, description, billable toggle
- Conditionally render based on `zzp.time_tracking_enabled` parameter
- "Invoice selected" action: select unbilled entries → create invoice from time entries

### 8.6 Debtors Page

- [x] ### 8.6 Debtors Page
- Create `frontend/src/pages/ZZPDebtors.tsx` — two tabs: Debiteuren (receivables) and Crediteuren (payables); aging analysis with `AgingChart`; row-click shows related invoices; send reminder button per overdue invoice

### Phase 8 Testing

- [ ] ### Phase 8 Testing
- Manual smoke test: full CRUD flow for contacts, products, invoices
- Verify field config visibility/required behavior in forms
- Verify mobile responsiveness on time tracking page
- Verify status badges, aging chart rendering

---

## Phase 9: Integration, Polish & Documentation

> Estimated: 2–3 days | Dependencies: all previous phases

### 9.1 End-to-End Integration

- [ ] Full flow test: create contact → create product → create invoice → send (PDF + book + email) → payment check → paid
- [ ] Full flow test: create invoice → send → create credit note → send credit note → original marked credited
- [ ] Full flow test: time entries → create invoice from entries → entries marked billed
- [ ] Full flow test: copy last invoice → edit draft → send
- [ ] Verify multi-tenant isolation: tenant A cannot see tenant B's data

### 9.2 Overdue & Reminder Flow

- [ ] Verify overdue detection: sent invoice past due date → status updated to overdue
- [ ] Verify reminder email sending for overdue invoices

### 9.3 Edge Cases & Error Handling

- [ ] Verify soft-delete protection: cannot delete contact/product referenced by invoice
- [ ] Verify sent invoice immutability: financial fields locked after send
- [ ] Verify concurrent invoice numbering: no duplicates under load
- [ ] Verify missing logo handling: PDF generates without logo placeholder
- [ ] Verify email failure handling: status stays draft, error returned

### 9.4 Railway Deployment

- [ ] Run `backend/sql/phase_zzp_tables.sql` against Railway production database after merging to main
- [ ] Verify all tables, views, indexes, and ZZP module seed on Railway
- [ ] Smoke test ZZP endpoints on production

### 9.5 Documentation

- [ ] Update spec README.md with final status and change log
- [ ] Create end-user documentation section per `.kiro/specs/Common/end-user-documentation/` pattern

---

## Phase 10 (Future): Advanced Time Tracking Input Methods

> Estimated: 3–5 days | Dependencies: Phase 5 | Reqs: 11.12, 11.13

### 10.1 Client Timesheet Import (Phase 2 of Req 11)

- [ ] Add `POST /api/zzp/time-entries/import-timesheet` endpoint
- [ ] Support PDF and Excel upload, parse into time entry records
- [ ] Link imported entries to corresponding contact
- [ ] UI: upload button on time tracking page with file picker and mapping preview

### 10.2 Calendar Import (Phase 3 of Req 11)

- [ ] Support iCal/ICS format import from Google Calendar / Apple Calendar
- [ ] Convert selected calendar events into time entries
- [ ] Map calendar entries to contacts and products/services
- [ ] UI: calendar import wizard with event selection and mapping

---

## Phase 11: Parameter Table Column Filtering (Req 16)

> Estimated: 0.5 day | Dependencies: Phase 1 (ParameterManagement exists) | Reqs: 16

### 11.1 Add FilterPanel with Search Filters to ParameterManagement

- [x] 11.1 Refactor `frontend/src/components/TenantAdmin/ParameterManagement.tsx` to use the generic filter framework (`FilterPanel` + `SearchFilterConfig`) for column filtering
  - Remove `nsFilter` state and the `<Select placeholder="All namespaces">` dropdown
  - Import `FilterPanel` from `../../components/filters/FilterPanel` and `SearchFilterConfig` from `../../components/filters/types`
  - Add filter state for each column: `namespace`, `key`, `value`, `value_type`, `scope_origin` (all empty strings)
  - Create a `SearchFilterConfig[]` array with 5 search filters (one per column), placed in a `FilterPanel` with `layout="horizontal"` and `size="sm"` between the page header and the table
  - Implement `filteredParams` computed from `allParams`: case-insensitive substring matching with AND logic across all active filters
  - Update `load()` to call `getParameters()` without the `nsFilter` parameter (all filtering is now client-side)
  - Render `filteredParams` instead of `allParams` in the `<Tbody>`
  - Reference: `frontend/src/components/filters/FilterPanel.tsx`, `frontend/src/components/filters/types.ts`, `.kiro/steering/ui-patterns.md` Filters section
  - _Requirements: 16.1, 16.2, 16.3, 16.4_
  - _Design: §14.1_

- [x] 11.2 Write unit test for ParameterManagement filter integration
  - Test that `FilterPanel` renders between header and table with 5 search inputs
  - Test that `filteredParams` AND logic correctly filters `allParams` by namespace + key simultaneously (the framework handles rendering/debounce — only test the integration)
  - _Requirements: 16.1, 16.3_

- [x] 11.3 Git commit and push Phase 11 to `feature/zzp-module`

---

## Phase 12: Ledger Parameters & Invoice Revenue Account (Reqs 17, 18, 19)

> Estimated: 1.5 days | Dependencies: Phase 3 (booking helper exists) | Reqs: 17, 18, 19

### 12.1 Add ZZP Ledger Parameters to Registry

- [x] 12.1 Add three new entries to `backend/src/config/ledger_parameters.json` (the registry that drives the Account Modal toggles — actual values are stored in `rekeningschema.parameters` JSON column per account)
  - Add `zzp_invoice_ledger` entry: `{ "key": "zzp_invoice_ledger", "type": "boolean", "label_en": "ZZP Invoice Ledger", "label_nl": "ZZP Factuur Grootboek", "description_en": "Account available as revenue ledger for ZZP invoices", "description_nl": "Rekening beschikbaar als omzetrekening voor ZZP facturen", "module": "ZZP" }`
  - Add `zzp_debtor_account` entry: `{ "key": "zzp_debtor_account", "type": "boolean", "label_en": "ZZP Debtor Account", "label_nl": "ZZP Debiteurenrekening", "description_en": "Account used as debtor ledger for ZZP invoices", "description_nl": "Rekening gebruikt als debiteurenrekening voor ZZP facturen", "module": "ZZP" }`
  - Add `zzp_creditor_account` entry: `{ "key": "zzp_creditor_account", "type": "boolean", "label_en": "ZZP Creditor Account", "label_nl": "ZZP Crediteurenrekening", "description_en": "Account used as creditor ledger for ZZP invoices", "description_nl": "Rekening gebruikt als crediteurenrekening voor ZZP facturen", "module": "ZZP" }`
  - The Account Modal already reads this registry and renders toggles — no frontend changes needed. When a tenant admin toggles `zzp_invoice_ledger` on an account, it writes `{"zzp_invoice_ledger": true}` into `rekeningschema.parameters` for that account row.
  - _Requirements: 17.1, 19.1_
  - _Design: §14.2, §14.4_

### 12.2 Invoice Ledger API Endpoint

- [x] 12.2 Add `GET /api/zzp/accounts/invoice-ledgers` endpoint to `backend/src/routes/zzp_routes.py`
  - Apply decorator chain: `@cognito_required(required_permissions=['zzp_read'])` → `@tenant_required()`
  - Query `rekeningschema` where `JSON_EXTRACT(parameters, '$.zzp_invoice_ledger') = true` for the tenant, ordered by `nummer`
  - Return `{ success: true, data: [{ account_code, account_name }] }`
  - Fallback: if no flagged accounts, return the account matching `zzp.revenue_account` parameter (default `8001`)
  - _Requirements: 17.3, 17.4_
  - _Design: §14.2_

### 12.3 Database Migration for Revenue Account Column

- [x] 12.3 Create SQL migration to add `revenue_account` column to `invoices` table
  - Create `backend/sql/phase_zzp_revenue_account.sql` with: `ALTER TABLE invoices ADD COLUMN revenue_account VARCHAR(10) DEFAULT NULL AFTER exchange_rate;`
  - _Requirements: 18.3_
  - _Design: §14.3, §14.11_

### 12.4 Invoice Service — Revenue Account Support

- [x] 12.4 Update `backend/src/services/zzp_invoice_service.py` to support `revenue_account` on invoices
  - In `create_invoice()`: read `revenue_account` from request data, default to `zzp.revenue_account` parameter if not provided, include in INSERT statement
  - In `update_invoice()`: allow updating `revenue_account` on draft invoices
  - Ensure `get_invoice()` returns `revenue_account` in the response dict
  - _Requirements: 18.2, 18.3_
  - _Design: §14.3_

### 12.5 Remove Hardcoded Fallbacks from Booking Helper

- [x] 12.5 Refactor `backend/src/services/invoice_booking_helper.py` to remove all hardcoded account fallbacks
  - Add `REQUIRED_BOOKING_PARAMS` class constant mapping param keys to display names
  - Change `_get_param(self, tenant, key, default)` signature to `_get_param(self, tenant, key)` — remove the `default` parameter
  - Raise `ValueError` with descriptive message naming the missing parameter when not configured
  - Update all callers in `book_outgoing_invoice()`: remove `'1300'`, `'8001'` defaults from `_get_param()` calls
  - Update all callers in `book_incoming_invoice()`: remove `'1600'`, `'4000'`, `'2010'` defaults from `_get_param()` calls
  - Update all callers in `book_credit_note()`: remove `'1300'`, `'8001'`, `'2010'` defaults from `_get_param()` calls
  - _Requirements: 19.2, 19.3, 19.5_
  - _Design: §14.4_

### 12.6 Booking Helper — Use Invoice-Level Revenue Account

- [x] 12.6 Update `book_outgoing_invoice()` and `book_credit_note()` in `invoice_booking_helper.py` to use invoice-level revenue account
  - In `book_outgoing_invoice()`: read `revenue_account` from `invoice.get('revenue_account')`, fall back to `_get_param(tenant, 'revenue_account')` only if not set
  - In `book_credit_note()`: read `revenue_account` from `original_invoice.get('revenue_account')`, fall back to `_get_param(tenant, 'revenue_account')` only if not set
  - Use the resolved `revenue_acct` for both the main entry credit account and VAT entry debit account
  - _Requirements: 18.4, 18.5, 18.6_
  - _Design: §14.3_

### 12.7 Frontend — Revenue Account Dropdown

- [x] 12.7 Add revenue account dropdown to the invoice creation/edit form in the frontend
  - Add `revenue_account?: string` to the `Invoice` interface in `frontend/src/types/zzp.ts`
  - Add `getInvoiceLedgerAccounts()` method to `frontend/src/services/zzpInvoiceService.ts` calling `GET /api/zzp/accounts/invoice-ledgers`
  - Add a `<Select>` dropdown in the invoice detail/modal component (e.g., `ZZPInvoiceDetail.tsx` or `InvoiceDetailModal.tsx`) listing accounts from the API
  - Default to the first account in the list for new invoices
  - Disable the dropdown when invoice status is not `draft`
  - Add i18n key `zzp.invoices.revenueAccount` / `zzp.invoices.omzetrekening` for the label
  - _Requirements: 18.1, 18.2_
  - _Design: §14.3_

### 12.8 Booking Account Validation

- [x] 12.8 Add validation when saving `zzp.debtor_account` or `zzp.creditor_account` parameters
  - Add `_validate_booking_account()` helper in `zzp_routes.py` or `zzp_invoice_service.py`
  - Validate that the account code exists in `rekeningschema` with the corresponding ledger flag (`zzp_debtor_account`, `zzp_creditor_account`, or `zzp_invoice_ledger`) set to true
  - Raise `ValueError` if the account is not flagged
  - _Requirements: 19.6_
  - _Design: §14.4_

- [x] 12.9 Write unit tests for ledger parameters and booking helper changes
  - Test `ledger_parameters.json` contains all three new ZZP entries
  - Test invoice ledger API returns flagged accounts
  - Test invoice ledger API fallback when no accounts flagged
  - Test `_get_param()` raises `ValueError` when parameter not configured (no hardcoded default)
  - Test `book_outgoing_invoice()` uses invoice-level `revenue_account` when set
  - Test `book_outgoing_invoice()` falls back to parameter when invoice `revenue_account` is None
  - Test `book_credit_note()` uses original invoice's `revenue_account`
  - Test booking account validation rejects unflagged accounts
  - _Requirements: 17.1–17.4, 18.3–18.6, 19.1–19.6_

- [x] 12.10 Write property tests for booking helper
  - **Property 2: Booking entries use invoice-level revenue account**
  - **Validates: Requirements 18.4, 18.5, 18.6**
  - **Property 3: Missing required booking parameters raise descriptive errors**
  - **Validates: Requirements 19.2, 19.3, 19.5**

- [x] 12.11 Git commit and push Phase 12 to `feature/zzp-module`

- [x] 12. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

---

## Phase 13: Invoice PDF Header Details & Branding Namespace (Req 20)

> Estimated: 1 day | Dependencies: Phase 3 (PDF generator exists) | Reqs: 20

### 13.1 Rename Branding Namespace and Add ZZP Branding

- [x] 13.1 Update `backend/src/services/parameter_schema.py` to rename `branding` to `str_branding` and add `zzp_branding`
  - Rename the `'branding'` key to `'str_branding'` with `'module': 'STR'`, `'label': 'STR Branding'`, `'label_nl': 'STR Huisstijl'`; keep all existing params unchanged
  - Add new `'zzp_branding'` namespace with `'module': 'ZZP'`, `'label': 'ZZP Branding'`, `'label_nl': 'ZZP Huisstijl'`
  - Include all keys from old branding plus two new keys: `company_iban` (IBAN shown on invoices) and `company_phone` (phone number)
  - _Requirements: 20.1, 20.2_
  - _Design: §14.5_

The preferred iban number is in the ledger account (IBAN: NL80RABO0107936917 Bank Account: ✓) and is also used for import transactions from the bank if can add the Invoice IBAN to it

### 13.2 Update STR Invoice Generator to Read from str_branding

- [x] 13.2 Update `backend/src/report_generators/str_invoice_generator.py` and `backend/src/auth/tenant_context.py` to use `str_branding` instead of `branding`
  - In `tenant_context.py` `_map_config_key_to_param()`: change the mapping for `company_*` and `contact_email` keys from `('branding', config_key)` to `('str_branding', config_key)` — or make it context-aware if both ZZP and STR need different branding
  - Alternatively, update `str_invoice_generator.py` to use `ParameterService` directly with `str_branding` namespace instead of `get_tenant_config()`
  - Verify STR invoice generation still works after the rename
  - _Requirements: 20.2_
  - _Design: §14.5_

### 13.3 Update PDF Generator to Read from zzp_branding

- [x] 13.3 Update `backend/src/services/pdf_generator_service.py` to read from `zzp_branding` namespace
  - In `_get_branding()`: change `get_param('branding', key, ...)` to `get_param('zzp_branding', key, ...)` and add `company_iban` and `company_phone` to the keys list
  - In `_get_tenant_logo()`: change `get_param('branding', 'company_logo_file_id', ...)` to `get_param('zzp_branding', 'company_logo_file_id', ...)`
  - In `_render_html()`: add `'{{tenant_iban}}'` and `'{{tenant_phone}}'` to the replacements dict, sourced from branding
  - Ensure missing fields render as empty strings (no placeholder text)
  - _Requirements: 20.3, 20.5_
  - _Design: §14.5_
  - The PDF generator (task 13.3) will need to query rekeningschema where invoice_bank_account = true and read the iban from that account's parameters JSON.

### 13.4 Update Default Invoice Template with Full Header

- [x] 13.4 Update `backend/src/templates/zzp_invoice_default.html` with sender/recipient header layout
  - Add sender (tenant) section: logo, company name, address, postal/city, country, BTW, KvK, IBAN, phone, email
  - Add recipient (client) section: company name, contact person, street address, postal code + city, country, client VAT
  - Add CSS to collapse empty `<p>` and `<br/>` elements when fields are not configured
  - Update the inline fallback template `_INLINE_DEFAULT_TEMPLATE` in `pdf_generator_service.py` to match
  - _Requirements: 20.4, 20.5, 20.6_
  - _Design: §14.5_

### 13.5 Register zzp_invoice Template Type

- [x] 13.5 Register `zzp_invoice` as a template type in Template Management
  - Add `'zzp_invoice'` entry to `TEMPLATE_TYPES` in the template service with label, label_nl, default_file, and module
  - Ensure the template is editable via the existing Template Management tab
  - _Requirements: 20.7_
  - _Design: §14.5_

### 13.6 Data Migration for Branding Parameters

- [x] 13.6 Create SQL migration script for branding parameter migration
  - Create `backend/sql/phase_zzp_branding_migration.sql`
  - Copy `branding.*` parameters to `zzp_branding.*` for tenants with ZZP module active
  - Copy `branding.*` parameters to `str_branding.*` for tenants with STR module active
  - Include commented-out DELETE statement for old `branding` params (to run after verification)
  - _Requirements: 20.1, 20.2_
  - _Design: §14.11_

- [x] 13.7 Write unit tests for branding changes
  - Test `parameter_schema.py` contains `zzp_branding` namespace with all required keys
  - Test `parameter_schema.py` has `str_branding` (not `branding`) with module STR
  - Test PDF generator reads from `zzp_branding` namespace
  - Test missing `zzp_branding` params result in empty strings (no placeholders)
  - Test `zzp_invoice` is registered as a template type
  - _Requirements: 20.1–20.7_

- [-] 13.8 Git commit and push Phase 13 to `feature/zzp-module`

---

## Phase 14: Locale-Aware Invoice Formatting (Req 21)

> Estimated: 1 day | Dependencies: Phase 3 (PDF generator exists) | Reqs: 21

### 14.1 Add Babel Dependency

- [ ] 14.1 Add `babel>=2.14.0` to `backend/requirements.txt`
  - _Requirements: 21.1_
  - _Design: §14.6_

### 14.2 Implement Locale-Aware Formatting in PDF Generator

- [ ] 14.2 Add locale resolution and formatting methods to `backend/src/services/pdf_generator_service.py`
  - Add `COUNTRY_LOCALE_MAP` dict mapping country codes/names (NL, DE, US, GB, FR, BE + Dutch/English names) to Babel locale identifiers
  - Add `DEFAULT_LOCALE = 'nl_NL'`
  - Add `_resolve_locale(self, contact)` method: resolve locale from contact's country field, try exact/uppercase/title case match, default to `nl_NL`
  - Add `_format_amount(self, val, currency_code, locale)` using `babel.numbers.format_currency()`
  - Add `_format_qty(self, val, locale)` using `babel.numbers.format_decimal()` — integer if whole, otherwise 2 decimals
  - Add `_format_date(self, val, locale)` using `babel.dates.format_date()` with `format='short'`
  - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5_
  - _Design: §14.6_

### 14.3 Integrate Locale Formatting into \_render_html()

- [ ] 14.3 Update `_render_html()` in `pdf_generator_service.py` to use locale-aware formatters
  - Resolve locale from `invoice.get('contact', {})` via `_resolve_locale()`
  - Read currency from `invoice.get('currency', 'EUR')`
  - Replace hardcoded `_nl_amount()`, `_nl_qty()`, `_nl_date()` with locale-aware `_format_amount()`, `_format_qty()`, `_format_date()`
  - Update lines HTML generation to use locale formatters for quantity, unit_price, and line_total
  - Update replacements dict: `invoice_date`, `due_date`, `subtotal`, `vat_total`, `grand_total` use locale formatters
  - Remove the old `_nl_amount`, `_nl_qty`, `_nl_date` inner functions
  - _Requirements: 21.1, 21.2, 21.3_
  - _Design: §14.6_

- [ ] 14.4 Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14.5 Write unit tests for locale formatting
  - Test `_resolve_locale()` returns `nl_NL` for 'NL', 'Nederland', 'Netherlands'
  - Test `_resolve_locale()` returns `en_US` for 'US', 'United States'
  - Test `_resolve_locale()` returns `nl_NL` for empty/unknown country
  - Test `_format_amount()` produces correct format per locale (e.g., `€ 1.250,00` for nl_NL, `€1,250.00` for en_US)
  - Test `_format_amount()` uses invoice currency code, not locale default currency
  - Test `_format_date()` produces correct format per locale (e.g., `15-05-2026` for nl_NL, `5/15/26` for en_US)
  - Test `_format_qty()` returns integer for whole numbers, locale-formatted decimal otherwise
  - _Requirements: 21.1–21.5_

- [ ] 14.6 Write property tests for locale formatting
  - **Property 4: Locale-aware formatting matches client country**
  - **Validates: Requirements 21.1, 21.2, 21.3, 21.4**
  - **Property 5: Currency symbol from invoice currency code**
  - **Validates: Requirements 21.5**

- [ ] 14.7 Git commit and push Phase 14 to `feature/zzp-module`

---

## Phase 15: Strict Send Flow (Req 22)

> Estimated: 1 day | Dependencies: Phase 3 (send flow exists) | Reqs: 22

### 15.1 Add Storage Health Check

- [ ] 15.1 Add `check_health()` method to `OutputService` if not already present
  - Implement a lightweight connectivity test to the configured storage provider (Google Drive API ping, S3 HeadBucket, etc.)
  - Return `{ 'healthy': True/False, 'reason': '...' }`
  - _Requirements: 22.7_
  - _Design: §14.7_

### 15.2 Refactor Send Flow with Strict Ordering

- [ ] 15.2 Refactor `send_invoice()` in `backend/src/services/zzp_invoice_service.py` to enforce strict send flow
  - Add pre-flight storage health check at the start: call `output_service.check_health(tenant)`, abort with descriptive error if unhealthy
  - Wrap PDF storage in try/except: on failure, return `{ success: False, error: "Storage unavailable — invoice not sent: {error}" }` — do NOT create mutaties, keep status as draft
  - Check that `storage_result` contains a URL; if not, abort with error
  - After successful storage + booking, update status to `sent` BEFORE attempting email
  - Wrap email sending in try/except: on failure, set `email_warning` but keep status as `sent` (financial records are complete)
  - Return `{ success: True, invoice_number: ..., warning: "..." }` when email fails but booking succeeded
  - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 22.6, 22.7_
  - _Design: §14.7_

### 15.3 Frontend — Handle Warning in Send Response

- [ ] 15.3 Update `frontend/src/services/zzpInvoiceService.ts` and the invoice send UI to handle the `warning` field
  - Update the `sendInvoice()` response type to include optional `warning` field
  - In the send invoice UI handler: if response has `success: true` but also `warning`, show a warning toast with the message (not an error toast)
  - _Requirements: 22.6_
  - _Design: §14.7_

- [ ] 15.4 Write unit tests for strict send flow
  - Test send flow executes in order: health check → generate → store → book → email
  - Test storage health check failure aborts send (invoice stays draft, no mutaties)
  - Test storage failure (exception) aborts send (invoice stays draft, no mutaties)
  - Test storage returns no URL aborts send
  - Test email failure after successful booking: invoice status = sent, warning returned, mutaties exist with Ref3/Ref4
  - Test successful send: all mutaties have Ref3 = storage URL, Ref4 = filename
  - Test `check_health()` is called before any PDF generation
  - _Requirements: 22.1–22.7_

- [ ] 15.5 Write property tests for send flow
  - **Property 6: Storage result flows to Ref3/Ref4 on mutaties**
  - **Validates: Requirements 22.2, 22.3, 22.4**
  - **Property 7: Storage failure aborts send flow**
  - **Validates: Requirements 22.5**
  - **Property 8: Email failure is soft failure**
  - **Validates: Requirements 22.6**

- [ ] 15.6 Git commit and push Phase 15 to `feature/zzp-module`

---

## Phase 16: Integration Testing & Migration (Reqs 16–22)

> Estimated: 1 day | Dependencies: Phases 11–15 | Reqs: 16–22

### 16.1 Integration Tests

- [ ] 16.1 Write integration tests covering cross-requirement flows
  - Test full send flow with real OutputService mock: store → book (with Ref3/Ref4) → email
  - Test end-to-end invoice creation with revenue account selection → send → verify mutaties use correct revenue account
  - Test VAT accounts from TaxRateService in booking entries (no hardcoded VAT accounts)
  - Test account validation on parameter save (reject unflagged accounts)
  - _Requirements: 17.3, 18.1–18.6, 19.4, 19.6, 22.1–22.4_

### 16.2 Run Database Migrations

- [ ] 16.2 Run all new SQL migrations against dev database
  - Run `backend/sql/phase_zzp_revenue_account.sql` (add `revenue_account` column)
  - Run `backend/sql/phase_zzp_branding_migration.sql` (copy branding params to zzp_branding/str_branding)
  - Verify column exists and data migrated correctly
  - _Requirements: 18.3, 20.1, 20.2_

### 16.3 Final Checkpoint

- [ ] 16.3 Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Verify no regressions in existing Phase 1–10 functionality
  - Verify STR invoice generation still works after branding namespace rename

- [ ] 16.4 Git commit and push Phase 16 to `feature/zzp-module`

## Notes

- Each task references specific requirements (16–22) and design sections (§14.1–§14.11) for traceability
- Checkpoints ensure incremental validation between phases
- Property tests validate universal correctness properties from design §14.8
- Unit tests validate specific examples and edge cases
- Database migrations should be run in order: revenue_account column first, then branding migration
