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
