# Requirements Document

## Introduction

This feature adds a PDF preview capability to the ZZP Invoices module. When a user opens a draft invoice, they can generate and view a preview of the final PDF invoice before sending it. This allows users to verify layout, branding, line items, totals, and formatting without committing to the send flow (which books financial records and emails the client).

## Glossary

- **Preview_Service**: The backend service component responsible for generating a temporary PDF preview for draft invoices without side effects (no storage, no booking, no email).
- **Preview_Viewer**: The frontend component that displays the generated PDF preview to the user in a modal or panel.
- **Draft_Invoice**: An invoice with status `draft` that has not yet been sent, booked, or stored.
- **PDF_Generator**: The existing `PDFGeneratorService` that renders invoice HTML templates to PDF using tenant branding and locale settings.
- **ZZP_Invoice_Detail**: The existing frontend page (`ZZPInvoiceDetail`) where users view and edit draft invoices.
- **Tenant**: The authenticated user's administration context, used for multi-tenant data isolation.

## Requirements

### Requirement 1: Generate PDF Preview for Draft Invoices

**User Story:** As a ZZP freelancer, I want to generate a PDF preview of my draft invoice, so that I can verify the layout and content before sending it to my client.

#### Acceptance Criteria

1. WHEN the user requests a PDF preview for a draft invoice, THE Preview_Service SHALL generate a PDF by invoking the PDF_Generator with the same template, tenant branding, and locale settings as the final send flow.
2. THE Preview_Service SHALL return the generated PDF bytes directly to the client without storing the file in Google Drive or any persistent storage.
3. IF the invoice status is not `draft`, THEN THE Preview_Service SHALL return an error indicating that only draft invoices can be previewed.
4. IF the invoice does not exist or does not belong to the current Tenant, THEN THE Preview_Service SHALL return a 404 error.
5. THE Preview_Service SHALL include a watermark on the preview PDF using the locale of the invoice contact: "CONCEPT" for Dutch (NL) locale and "DRAFT" for English (EN) locale.
6. IF the PDF_Generator fails to render the preview, THEN THE Preview_Service SHALL return an error indicating that the preview could not be generated and include the failure reason.

### Requirement 2: Backend API Endpoint for PDF Preview

**User Story:** As a frontend developer, I want a dedicated API endpoint for PDF preview, so that the preview can be requested independently from the send flow.

#### Acceptance Criteria

1. THE Preview_Service SHALL expose a GET endpoint at `/api/zzp/invoices/<invoice_id>/preview` that returns the PDF as binary content with `Content-Type: application/pdf`.
2. WHEN the endpoint is called, THE Preview_Service SHALL authenticate the request using the existing JWT/Cognito middleware and enforce tenant isolation so that users can only preview invoices belonging to their own tenant.
3. IF the requested invoice_id does not exist or does not belong to the authenticated user's tenant, THEN THE Preview_Service SHALL return HTTP 404 with a JSON error response indicating the invoice was not found.
4. WHEN the PDF is generated successfully, THE Preview_Service SHALL return HTTP 200 with the PDF content and a `Content-Disposition` header set to `inline` with filename `<invoice_number>_PREVIEW.pdf`.
5. IF PDF generation fails due to an internal error, THEN THE Preview_Service SHALL return HTTP 500 with a JSON error response indicating that PDF generation failed, without exposing internal details.
6. THE Preview_Service SHALL generate the preview PDF within 10 seconds for invoices containing up to 100 line items.

### Requirement 3: Frontend Preview Button on Draft Invoices

**User Story:** As a ZZP freelancer, I want a clearly visible preview button when viewing a draft invoice, so that I can easily trigger the PDF preview.

#### Acceptance Criteria

1. WHILE the invoice status is `draft`, THE ZZP_Invoice_Detail SHALL display a "Preview PDF" button in the action area.
2. IF the invoice status is not `draft`, THEN THE ZZP_Invoice_Detail SHALL NOT render the "Preview PDF" button.
3. WHEN the user clicks the "Preview PDF" button, THE ZZP_Invoice_Detail SHALL disable the button, display a loading spinner within the button, and call the preview API endpoint.
4. WHEN the preview API returns a successful response, THE ZZP_Invoice_Detail SHALL open the generated PDF in the Preview_Viewer modal and re-enable the "Preview PDF" button.
5. IF the preview request fails, THEN THE ZZP_Invoice_Detail SHALL re-enable the "Preview PDF" button and display an error toast indicating the reason for failure, using the error message from the API when available or a generic failure message otherwise.
6. IF the preview request does not respond within 30 seconds, THEN THE ZZP_Invoice_Detail SHALL abort the request, re-enable the "Preview PDF" button, and display an error toast indicating a timeout.

### Requirement 4: Display PDF Preview in the Browser

**User Story:** As a ZZP freelancer, I want to view the PDF preview directly in my browser, so that I can inspect it without downloading a file.

#### Acceptance Criteria

1. WHEN the preview PDF is received from the API, THE Preview_Viewer SHALL display the PDF in a modal overlay using an embedded `<iframe>` or `<object>` element with the PDF blob URL, leveraging the browser's native PDF rendering.
2. THE Preview_Viewer SHALL size the modal to use a minimum of 80% of the viewport width and 85% of the viewport height.
3. THE Preview_Viewer SHALL provide a visible close button and support the Escape key to dismiss the preview modal.
4. WHEN the user clicks the download button, THE Preview_Viewer SHALL trigger a file download using the filename format `<invoice_number>_PREVIEW.pdf`.
5. WHILE the preview modal is open, THE Preview_Viewer SHALL allow the user to close it and return to the invoice detail view with all previously saved form data intact.
6. IF the PDF fails to render in the embedded viewer (empty blob or rendering error), THEN THE Preview_Viewer SHALL display an error message indicating the preview could not be displayed and offer the download button as a fallback.

### Requirement 5: Preview Reflects Current Unsaved Changes

**User Story:** As a ZZP freelancer, I want the preview to reflect my latest edits even if I haven't saved yet, so that I can check my changes before saving and sending.

#### Acceptance Criteria

1. WHEN the user requests a PDF preview and the draft invoice has unsaved changes (form state differs from last persisted state), THE ZZP_Invoice_Detail SHALL save the invoice before requesting the PDF preview from the API.
2. WHEN the user requests a PDF preview and the draft invoice has no unsaved changes, THE ZZP_Invoice_Detail SHALL request the PDF preview from the API without performing a save.
3. IF the save triggered by a preview request fails, THEN THE ZZP_Invoice_Detail SHALL display an error toast indicating the save failure and abort the preview request.
4. WHEN the save succeeds, THE ZZP_Invoice_Detail SHALL request the PDF preview from the API using the saved invoice ID.
5. IF the PDF preview API request fails, THEN THE ZZP_Invoice_Detail SHALL display an error toast indicating the preview could not be generated.
6. WHILE the save-then-preview sequence is in progress, THE ZZP_Invoice_Detail SHALL display a loading indicator and disable the preview button to prevent duplicate requests.

### Requirement 6: Performance and Resource Management

**User Story:** As a system administrator, I want the preview feature to be lightweight and not impact system resources, so that it does not degrade performance for other users.

#### Acceptance Criteria

1. THE Preview_Service SHALL generate the preview PDF without writing to persistent storage (no Google Drive upload, no database record for the preview).
2. THE Preview_Service SHALL generate the preview PDF within 5 seconds (measured from request receipt to response completion) for invoices with up to 50 line items.
3. IF the preview generation exceeds 30 seconds, THEN THE Preview_Service SHALL abort the generation and return an error indicating a timeout.
4. WHILE a preview is being generated, THE ZZP_Invoice_Detail SHALL disable the "Preview PDF" button to prevent duplicate requests.
5. WHEN the preview modal is closed, THE Preview_Viewer SHALL revoke the PDF blob URL from browser memory.
6. IF the user navigates away from the ZZP_Invoice_Detail page while a preview request is in progress, THEN THE ZZP_Invoice_Detail SHALL cancel the pending request and release any associated resources.
7. THE Preview_Service SHALL generate the preview PDF within 15 seconds for invoices with more than 50 and up to 200 line items.

### Requirement 7: Internationalization

**User Story:** As a ZZP freelancer, I want the preview button and related UI text to be available in my configured language, so that the interface is consistent.

#### Acceptance Criteria

1. THE ZZP_Invoice_Detail SHALL use translation keys from the `zzp` namespace (under the `invoices` category) for the "Preview PDF" button label, the loading indicator text, and the error toast messages related to preview.
2. THE Preview_Viewer SHALL use translation keys from the `zzp` namespace for the modal title, close button label, and download button label.
3. THE Preview_Service SHALL resolve the PDF preview locale from the contact's `country` field using the same `COUNTRY_LOCALE_MAP` resolution as the send flow, defaulting to `nl_NL` when the contact country is empty or unmapped.
4. THE ZZP_Invoice_Detail SHALL provide all preview-related translation keys in both the Dutch (`nl`) and English (`en`) locale files.

### Requirement 8: Email Template for Sending ZZP Invoices

**User Story:** As a ZZP freelancer, I want the invoice email sent to my client to use a professional, locale-aware template with all relevant invoice details, so that my client receives a clear and complete notification with the PDF invoice attached.

#### Acceptance Criteria

1. WHEN a ZZP invoice is sent, THE Preview_Service SHALL compose an email using a structured HTML template that includes the invoice number, total amount formatted with the locale-appropriate currency symbol, and due date formatted according to the resolved locale.
2. WHEN composing the email, THE Preview_Service SHALL resolve the email template locale from the contact's `country` field using the same `COUNTRY_LOCALE_MAP` resolution as the PDF preview, defaulting to `nl_NL` when the contact country is empty or unmapped.
3. WHILE the locale is resolved to `nl_NL`, THE Preview_Service SHALL render the email template in Dutch with a Dutch subject line in the format: "Factuur {invoice_number} van {tenant_company_name}".
4. WHILE the locale is resolved to `en_US` or any English locale (en_GB, en_AU), THE Preview_Service SHALL render the email template in English with an English subject line in the format: "Invoice {invoice_number} from {tenant_company_name}".
5. WHILE the locale is resolved to a non-Dutch, non-English locale (e.g., de_DE, fr_FR), THE Preview_Service SHALL fall back to the English email template and English subject line format.
6. WHEN the email is composed, THE Preview_Service SHALL attach the final PDF invoice (not the preview version) to the email with filename `{invoice_number}.pdf`.
7. THE Preview_Service SHALL include in the email body: a greeting addressing the contact by `company_name` (or `contact_person` if `company_name` is empty), a statement that an invoice is attached, the invoice number, the total amount with currency symbol, the due date, and the sender's company name from the tenant profile.
8. WHEN the user initiates the send flow, THE ZZP_Invoice_Detail SHALL display a preview of the email showing the resolved subject line, the rendered HTML body, the recipient email address, and the attachment filename before confirming the send action.
9. IF the contact does not have an email address configured (no email with `email_type` of `invoice` or `is_primary` set to true, and no other email), THEN THE Preview_Service SHALL prevent the send action and return an error indicating that the contact email address is missing.
10. IF the email delivery fails after the send action is confirmed, THEN THE Preview_Service SHALL log the failure and return a warning to the user indicating the failure reason, while retaining the invoice in `sent` status without reversing the financial booking, so the user can resend the email manually.
11. THE ZZP_Invoice_Detail SHALL use translation keys from the `zzp` namespace (under the `invoices.email` category) for all email preview UI elements including the preview panel title, send confirmation button label, and email field labels.
12. WHEN the invoice email is sent to the customer, THE Preview_Service SHALL include the tenant administrator's email address as a BCC recipient so that the freelancer receives a copy of the sent email in their own inbox.
