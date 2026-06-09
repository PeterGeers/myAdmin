# Requirements Document

## Introduction

The Aangifte IB (Income Tax) report export currently saves files to the server filesystem and uses SSE for progress. This fails on Railway's ephemeral storage and 60-second keep-alive timeout. This feature redesigns the export to stream a ZIP file (containing the XLSX workbook and all downloaded PDFs) directly to the browser, eliminating filesystem dependency and keeping the connection alive through chunked transfer.

## Glossary

- **Export_Service**: The backend service responsible for generating the ZIP archive containing the XLSX workbook and downloaded PDF files
- **ZIP_Stream**: A chunked HTTP response that incrementally sends ZIP file data to the browser as content becomes available
- **Frontend_Client**: The React application running on GitHub Pages that initiates the export and receives the streamed ZIP
- **Ledger_Data**: The database records queried by make_ledgers() containing financial transaction data for a given year and administration
- **DocUrl**: A field in Ledger_Data pointing to a PDF document stored in Google Drive or S3
- **ReferenceNumber**: A field in Ledger_Data used to group related documents into subfolders within the ZIP
- **Keep_Alive_Interval**: The maximum duration (less than 60 seconds) between data chunks sent to prevent Railway's proxy from dropping the connection
- **Deduplication**: The process of identifying and downloading each unique DocUrl only once, even when it appears in multiple ledger records
- **Progress_Header**: Custom HTTP headers or inline metadata sent before/during the stream to communicate progress state to the Frontend_Client

## Requirements

### Requirement 1: Streamed ZIP Generation

**User Story:** As a user, I want to download the Aangifte IB export as a single ZIP file streamed to my browser, so that the export works reliably on Railway without depending on server filesystem storage.

#### Acceptance Criteria

1. WHEN the user triggers the export, THE Export_Service SHALL generate a ZIP archive in-memory and stream it to the Frontend_Client using chunked transfer encoding
2. THE Export_Service SHALL include in the ZIP archive: one XLSX workbook named `{administration}{year}.xlsx` at the root level
3. THE Export_Service SHALL include in the ZIP archive: PDF files organized in folders named by ReferenceNumber (e.g., `{ReferenceNumber}/{filename}.pdf`)
4. THE Export_Service SHALL NOT write any files to the server filesystem during the export process
5. WHEN generating the ZIP, THE Export_Service SHALL use streaming ZIP construction so that bytes are sent to the client as each file entry is completed
6. WHEN generating the XLSX workbook, THE Export_Service SHALL apply the administration-specific template (via TemplateService) so that custom sheets and formatting from the template are preserved in the output

### Requirement 2: Connection Keep-Alive

**User Story:** As a user, I want the export download to complete successfully even when it takes several minutes, so that Railway's proxy does not terminate the connection.

#### Acceptance Criteria

1. WHILE the Export_Service is downloading PDF files from external storage, THE Export_Service SHALL send ZIP data bytes to the Frontend_Client at intervals shorter than the Keep_Alive_Interval (60 seconds)
2. WHEN a PDF file download from Google Drive or S3 takes longer than 30 seconds, THE Export_Service SHALL send padding bytes or a completed prior entry to maintain the data flow
3. THE Export_Service SHALL use a strategy that ensures at least one chunk of data is written to the response stream within every 50-second window

### Requirement 3: File Deduplication

**User Story:** As a user, I want duplicate document downloads avoided, so that the export completes faster and the ZIP does not contain redundant files.

#### Acceptance Criteria

1. WHEN multiple Ledger_Data records reference the same DocUrl, THE Export_Service SHALL download that file only once
2. THE Export_Service SHALL place the deduplicated file in each ReferenceNumber folder that references it (either as separate ZIP entries pointing to the same content, or as a single entry with the file in one folder)
3. WHEN deduplication is applied, THE Export_Service SHALL still reflect the correct file associations in the XLSX workbook data

### Requirement 4: Cross-Origin Compatibility

**User Story:** As a user accessing the frontend from GitHub Pages, I want the ZIP download to work without CORS errors, so that the export functions in the production deployment.

#### Acceptance Criteria

1. THE Export_Service SHALL respond with appropriate CORS headers allowing the GitHub Pages origin to receive the streamed response
2. THE Export_Service SHALL support the `Authorization` header and `X-Tenant` header in cross-origin preflight requests
3. WHEN the Frontend_Client sends a POST request with `credentials: 'include'`, THE Export_Service SHALL accept the request and stream the response without credential conflicts
4. THE Export_Service SHALL set `Content-Type` to `application/zip` and `Content-Disposition` to `attachment; filename="{administration}{year}.zip"` in the response headers

### Requirement 5: Progress Indication

**User Story:** As a user, I want to see download progress in the UI while the export is being generated, so that I know the operation is still active and approximately how far along it is.

#### Acceptance Criteria

1. WHEN the export begins, THE Export_Service SHALL include a custom response header indicating the total number of files to be processed
2. WHILE receiving the streamed ZIP, THE Frontend_Client SHALL display a progress indicator showing the download is in progress
3. THE Frontend_Client SHALL display the total bytes received as the progress metric during the download
4. IF the connection drops or an HTTP error occurs, THEN THE Frontend_Client SHALL display an error message to the user and allow retry

### Requirement 6: Authentication and Authorization

**User Story:** As an administrator, I want the export endpoint to enforce authentication and tenant-level access control, so that only authorized users can export data for their assigned administrations.

#### Acceptance Criteria

1. THE Export_Service SHALL require a valid Cognito JWT token with `reports_export` permission
2. THE Export_Service SHALL validate that the requested administration belongs to the authenticated user's tenant list
3. IF the user does not have access to the requested administration, THEN THE Export_Service SHALL return HTTP 403 with an error message before streaming begins
4. IF the JWT token is invalid or expired, THEN THE Export_Service SHALL return HTTP 401 before streaming begins

### Requirement 7: Error Handling During Stream

**User Story:** As a user, I want failed file downloads to be handled gracefully, so that the export still completes with available files rather than failing entirely.

#### Acceptance Criteria

1. IF a single PDF file download from Google Drive or S3 fails, THEN THE Export_Service SHALL skip that file and continue processing remaining files
2. WHEN file downloads fail, THE Export_Service SHALL include a `download_log.txt` file in the ZIP root listing all failed downloads with their DocUrl and ReferenceNumber
3. IF the XLSX workbook generation fails, THEN THE Export_Service SHALL return an HTTP error response before streaming begins
4. IF all PDF downloads fail but the XLSX was generated, THEN THE Export_Service SHALL still return a valid ZIP containing just the XLSX and the error log

### Requirement 8: Empty Data Handling

**User Story:** As a user, I want clear feedback when there is no data available for the selected year, so that I understand why no file is produced.

#### Acceptance Criteria

1. IF no Ledger_Data records exist for the requested administration and year, THEN THE Export_Service SHALL return HTTP 404 with an error message before streaming begins
2. WHEN Ledger_Data exists but no records have a DocUrl, THE Export_Service SHALL return a ZIP containing only the XLSX workbook (no PDF folders)

### Requirement 9: Frontend Download Trigger

**User Story:** As a user, I want to click "Export to Excel" and have the ZIP file download automatically to my computer, so that the experience is seamless.

#### Acceptance Criteria

1. WHEN the user clicks the export button, THE Frontend_Client SHALL send a POST request to the new ZIP export endpoint with the selected administration and year
2. WHILE the download is in progress, THE Frontend_Client SHALL display a loading state and disable the export button
3. WHEN the response stream completes successfully, THE Frontend_Client SHALL trigger a browser file save dialog with the filename `{administration}{year}.zip`
4. IF the server returns an error response (non-2xx status), THEN THE Frontend_Client SHALL display the error message to the user
