# Implementation Plan: ZZP Invoice PDF Preview

## Overview

This plan implements a PDF preview capability and locale-aware email template for the ZZP Invoices module. The implementation is split into backend service/route work, frontend components, and integration wiring. Each task builds incrementally, with property-based and unit tests validating correctness at each stage.

## Tasks

- [x] 1. Backend: PDF Preview Service Layer
  - [x] 1.1 Implement `generate_preview_pdf` in PDFGeneratorService
    - Add `is_preview` parameter to `_render_html` method
    - Inject locale-aware watermark div (`CONCEPT` for nl_NL, `DRAFT` otherwise) when `is_preview=True`
    - Add `generate_preview_pdf(tenant, invoice)` method that calls `_render_html` with `is_preview=True` then `_html_to_pdf`
    - _Requirements: 1.1, 1.5, 7.3_

  - [x] 1.2 Write property test for watermark locale resolution (Property 3)
    - **Property 3: Watermark text is locale-dependent**
    - Use `hypothesis` with `st.text()` for country strings + known COUNTRY_LOCALE_MAP keys
    - Verify watermark is "CONCEPT" when resolved locale is `nl_NL`, "DRAFT" otherwise
    - **Validates: Requirements 1.5**

  - [x] 1.3 Write property test for locale resolution (Property 7)
    - **Property 7: Locale resolution from contact country**
    - Use `hypothesis` with `st.text()` for country strings
    - Verify `_resolve_locale` returns correct locale from COUNTRY_LOCALE_MAP or defaults to `nl_NL`
    - **Validates: Requirements 7.3, 8.2**

  - [x] 1.4 Implement `preview_invoice` in ZZPInvoiceService
    - Fetch invoice by ID with tenant isolation
    - Validate invoice status is `draft`, raise ValueError otherwise
    - Raise ValueError if invoice not found or wrong tenant
    - Call `generate_preview_pdf` and return BytesIO
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

  - [x] 1.5 Write property test for non-draft rejection (Property 1)
    - **Property 1: Non-draft invoices are rejected for preview**
    - Use `hypothesis` with `st.sampled_from(['sent', 'paid', 'overdue', 'credited', 'cancelled'])`
    - Verify ValueError is raised and no PDF generation occurs
    - **Validates: Requirements 1.3**

  - [x] 1.6 Write property test for tenant isolation (Property 2)
    - **Property 2: Tenant isolation on preview**
    - Use `hypothesis` with `st.tuples(st.text(min_size=1), st.text(min_size=1))` for tenant pairs
    - Verify ValueError (404) when invoice doesn't belong to requesting tenant
    - **Validates: Requirements 1.4, 2.3**

- [x] 2. Backend: PDF Preview API Route
  - [x] 2.1 Implement preview route in `zzp_routes.py`
    - Add `GET /api/zzp/invoices/<invoice_id>/preview` endpoint
    - Apply `@cognito_required(required_permissions=['zzp_read'])` and `@tenant_required()` decorators
    - Call `ZZPInvoiceService.preview_invoice(tenant, invoice_id)`
    - Return PDF bytes with `Content-Type: application/pdf` and `Content-Disposition: inline; filename="{invoice_number}_PREVIEW.pdf"`
    - Handle ValueError → 400/404, RuntimeError → 500
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 2.2 Write property test for Content-Disposition filename format (Property 4)
    - **Property 4: Content-Disposition filename format**
    - Use `hypothesis` with `st.text(min_size=1)` for invoice_number strings
    - Verify response header contains `inline; filename="{invoice_number}_PREVIEW.pdf"`
    - **Validates: Requirements 2.4**

  - [x] 2.3 Write unit tests for preview route
    - Test successful preview returns 200 with PDF content-type
    - Test non-draft invoice returns 400
    - Test non-existent invoice returns 404
    - Test PDF generation failure returns 500
    - _Requirements: 2.1, 2.3, 2.4, 2.5_

- [x] 3. Checkpoint - Backend preview service and route
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Backend: Email Composition Service
  - [x] 4.1 Implement `InvoiceEmailService` with `compose_email_preview`
    - Create or extend `InvoiceEmailService` class
    - Implement `_build_locale_subject(tenant, invoice, locale)` — NL: "Factuur {number} van {company}", EN/other: "Invoice {number} from {company}"
    - Implement `_build_locale_body(tenant, invoice, locale)` — HTML template with greeting, invoice details, amount, due date, sender
    - Implement `_resolve_tenant_admin_email(tenant)` — look up tenant profile for admin email (BCC)
    - Implement `compose_email_preview(tenant, invoice)` — orchestrate locale resolution, subject, body, recipient, BCC, attachment filename
    - Raise ValueError if contact has no email address
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.9, 8.12_

  - [x] 4.2 Write property test for email subject format (Property 8)
    - **Property 8: Email subject format by locale category**
    - Use `hypothesis` with `st.tuples(st.text(min_size=1), st.text(min_size=1))` for invoice_number, company
    - Verify NL subject format "Factuur {number} van {company}" and EN/other format "Invoice {number} from {company}"
    - **Validates: Requirements 8.3, 8.4, 8.5**

  - [x] 4.3 Write property test for email body fields (Property 9)
    - **Property 9: Email body contains all required fields**
    - Use `hypothesis` strategy generating valid invoice dicts with random data
    - Verify body contains greeting, invoice number, total with currency, due date, sender company
    - **Validates: Requirements 8.6, 8.7**

  - [x] 4.4 Write property test for missing contact email (Property 10)
    - **Property 10: Missing contact email blocks email composition**
    - Use `hypothesis` strategy generating contacts without email fields
    - Verify ValueError is raised indicating email is missing
    - **Validates: Requirements 8.9**

  - [x] 4.5 Write property test for BCC admin email (Property 12)
    - **Property 12: BCC includes tenant admin email**
    - Use `hypothesis` strategy generating valid invoices with tenant profiles containing admin emails
    - Verify composed email includes tenant admin email as BCC
    - **Validates: Requirements 8.12**

- [x] 5. Backend: Email Preview and Send Routes
  - [x] 5.1 Implement email preview route in `zzp_routes.py`
    - Add `GET /api/zzp/invoices/<invoice_id>/email-preview` endpoint
    - Apply `@cognito_required(required_permissions=['zzp_read'])` and `@tenant_required()` decorators
    - Call `ZZPInvoiceService.get_email_preview(tenant, invoice_id)`
    - Return JSON with subject, html_body, recipient, bcc, attachment_filename
    - Handle ValueError → 400/404
    - _Requirements: 8.8_

  - [x] 5.2 Implement `get_email_preview` in ZZPInvoiceService
    - Fetch invoice, validate draft status
    - Call `InvoiceEmailService.compose_email_preview(tenant, invoice)`
    - Return composed email dict
    - _Requirements: 8.1, 8.8, 8.9_

  - [x] 5.3 Write unit tests for email preview route and service
    - Test successful email preview returns 200 with correct JSON structure
    - Test non-draft invoice returns 400
    - Test contact without email returns 400
    - Test BCC field contains admin email
    - _Requirements: 8.8, 8.9, 8.12_

- [x] 6. Checkpoint - Backend email composition complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Frontend: Preview Service and Types
  - [x] 7.1 Add preview API functions to `zzpInvoiceService.ts`
    - Implement `getInvoicePreview(id: number): Promise<Blob>` — GET with blob response
    - Implement `getEmailPreview(id: number): Promise<EmailPreviewResponse>` — GET with JSON response
    - Add `EmailPreviewResponse` TypeScript interface
    - Add AbortController support for timeout (30s)
    - _Requirements: 2.1, 3.6, 6.6, 8.8_

- [x] 8. Frontend: InvoicePreviewModal Component
  - [x] 8.1 Create `InvoicePreviewModal.tsx` component
    - Create `frontend/src/components/zzp/InvoicePreviewModal.tsx`
    - Implement modal with 80% viewport width, 85% viewport height
    - Render `<iframe>` with PDF blob URL
    - Add close button and Escape key support
    - Add download button with filename `{invoice_number}_PREVIEW.pdf`
    - Add error fallback if iframe fails to render
    - Use translation keys from `zzp` namespace for modal title, close, download labels
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 7.2_

  - [x] 8.2 Write property test for download filename format (Property 11)
    - **Property 11: Download filename format**
    - Use `fast-check` with `fc.string()` for invoice_number
    - Verify download button uses filename `"{invoice_number}_PREVIEW.pdf"`
    - **Validates: Requirements 4.4**

  - [x] 8.3 Write unit tests for InvoicePreviewModal
    - Test modal renders iframe with blob URL
    - Test close button and Escape key dismiss modal
    - Test download button has correct filename attribute
    - Test error fallback displays when iframe fails
    - _Requirements: 4.1, 4.3, 4.4, 4.6_

- [x] 9. Frontend: EmailPreviewPanel Component
  - [x] 9.1 Create `EmailPreviewPanel.tsx` component
    - Create `frontend/src/components/zzp/EmailPreviewPanel.tsx`
    - Display subject, rendered HTML body, recipient, BCC, attachment filename
    - Add "Confirm Send" button with loading state
    - Add close/cancel button
    - Use translation keys from `zzp.invoices.email` namespace
    - _Requirements: 8.8, 8.11, 8.12_

  - [x] 9.2 Write unit tests for EmailPreviewPanel
    - Test panel renders all email fields (subject, body, recipient, BCC, attachment)
    - Test BCC field displays tenant admin email
    - Test confirm send button triggers callback
    - _Requirements: 8.8, 8.11, 8.12_

- [x] 10. Reduce property-based test iterations for faster execution
  - [x] 10.1 Reduce Hypothesis examples in backend test files
    - In `backend/tests/unit/test_zzp_preview_service.py`: change `@settings(max_examples=100)` to `@settings(max_examples=20)` for all property tests
    - In `backend/tests/unit/test_zzp_email_composition.py`: change `@settings(max_examples=100)` to `@settings(max_examples=20)` for all property tests
    - In `backend/tests/api/test_zzp_preview_routes.py`: change `@settings(max_examples=100)` to `@settings(max_examples=20)` for all property tests
    - _Requirements: 6.2_

  - [x] 10.2 Reduce fast-check iterations in frontend test files
    - In `frontend/src/__tests__/InvoicePreviewModal.test.ts`: change `numRuns: 100` to `numRuns: 20` for all property tests
    - In `frontend/src/__tests__/ZZPInvoiceDetail.preview.test.ts`: change `numRuns: 100` to `numRuns: 20` for all property tests
    - _Requirements: 6.2_

  - [x] 10.3 Re-run all backend property-based tests to verify they pass with fewer examples
    - Run `pytest backend/tests/unit/test_zzp_preview_service.py backend/tests/unit/test_zzp_email_composition.py backend/tests/api/test_zzp_preview_routes.py -v`
    - Verify all property tests still pass with 20 iterations
    - _Requirements: 6.2_

  - [x] 10.4 Re-run all frontend property-based tests to verify they pass with fewer examples
    - Run `npx vitest --run src/__tests__/InvoicePreviewModal.test.ts src/__tests__/ZZPInvoiceDetail.preview.test.ts`
    - Verify all property tests still pass with 20 iterations
    - _Requirements: 6.2_

- [x] 11. Frontend: Preview Flow in ZZPInvoiceDetail
  - [x] 11.1 Implement preview button and flow in `ZZPInvoiceDetail.tsx`
    - Add "Preview PDF" button visible only when `invoice.status === 'draft'`
    - Implement save-before-preview logic: if form isDirty, save first, then preview
    - Handle loading states: disable button, show spinner during preview generation
    - On success: create blob URL, open InvoicePreviewModal
    - On failure: show error toast with API error message or generic fallback
    - On timeout (30s): abort request, show timeout toast
    - On modal close: revoke blob URL
    - On component unmount: abort pending request, revoke blob URL
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4, 6.5, 6.6_

  - [x] 11.2 Write property test for preview button visibility (Property 5)
    - **Property 5: Preview button visibility matches draft status**
    - Use `fast-check` with `fc.constantFrom('draft', 'sent', 'paid', 'overdue', 'credited', 'cancelled')`
    - Verify button rendered iff status === 'draft'
    - **Validates: Requirements 3.1, 3.2**

  - [x] 11.3 Write property test for save-before-preview (Property 6)
    - **Property 6: Save-before-preview iff form is dirty**
    - Use `fast-check` with `fc.boolean()` for isDirty state
    - Verify save API called iff isDirty === true, not called iff isDirty === false
    - **Validates: Requirements 5.1, 5.2**

- [x] 12. Frontend: Email Send Flow in ZZPInvoiceDetail
  - [x] 12.1 Implement email preview and send flow in `ZZPInvoiceDetail.tsx`
    - Add "Send Invoice" button that triggers email preview fetch
    - On success: open EmailPreviewPanel with preview data
    - On confirm send: call existing send endpoint
    - Handle errors: missing email (show toast), send failure (show warning)
    - _Requirements: 8.8, 8.9, 8.10_

- [x] 13. Frontend: Translation Keys
  - [x] 13.1 Add translation keys for NL and EN locale files
    - Add keys under `zzp.invoices.preview`: button, loading, error messages, modal title, close, download
    - Add keys under `zzp.invoices.email`: panel title, send button, field labels (subject, recipient, bcc, attachment), error messages
    - Add to both Dutch (`nl`) and English (`en`) locale files
    - _Requirements: 7.1, 7.2, 7.4, 8.11_

- [x] 14. Checkpoint - Frontend components complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Integration and Wiring
  - [x] 15.1 Wire backend preview service into existing ZZP invoice module
    - Register preview and email-preview routes in the ZZP blueprint
    - Ensure PDFGeneratorService is injected/available in the service layer
    - Ensure InvoiceEmailService is instantiated and accessible
    - Verify tenant isolation works end-to-end
    - _Requirements: 1.1, 2.1, 2.2, 6.1_

  - [x] 15.2 Write integration tests for full preview flow
    - Test full preview flow with Flask test client (draft invoice → PDF response)
    - Test full email preview flow (draft invoice → JSON response with all fields)
    - Test non-draft rejection end-to-end
    - Test performance: 50 line items < 5s, 100 line items < 10s
    - _Requirements: 2.1, 2.6, 6.2, 6.7_

- [x] 16. Final Checkpoint - All tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks (including property tests and unit tests) are required
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python with pytest + hypothesis for property-based testing
- Frontend uses TypeScript with Vitest + @fast-check/vitest for property-based testing
- The preview feature is entirely stateless — no new database tables or migrations needed
- Blob URL cleanup is critical for memory management in the frontend

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "7.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "13.1"] },
    { "id": 2, "tasks": ["1.5", "1.6", "2.1", "4.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "4.2", "4.3", "4.4", "4.5"] },
    { "id": 4, "tasks": ["5.1", "5.2", "8.1", "9.1"] },
    { "id": 5, "tasks": ["5.3", "8.2", "8.3", "9.2"] },
    { "id": 6, "tasks": ["10.1", "10.2"] },
    { "id": 7, "tasks": ["10.3", "10.4"] },
    { "id": 8, "tasks": ["11.1", "12.1"] },
    { "id": 9, "tasks": ["11.2", "11.3"] },
    { "id": 10, "tasks": ["15.1"] },
    { "id": 11, "tasks": ["15.2"] }
  ]
}
```
