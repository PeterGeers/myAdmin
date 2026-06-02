# Implementation Plan: Invoice Processing Test Tool

## Overview

Implement a SysAdmin-only diagnostic interface for testing the invoice processing pipeline in dry-run mode. The tool provides full pipeline transparency with performance metrics, AI usage preview, custom prompt testing, and detailed error diagnostics — all without writing to the database or external storage.

## Tasks

- [x] 1. Set up backend service and blueprint structure
  - [x] 1.1 Create `InvoiceTestService` class with constructor and method stubs
    - Create `backend/src/services/invoice_test_service.py`
    - Initialize `PDFProcessor(test_mode=True)` and `CsvRuleEngine()`
    - Define method stubs: `process_file_dry_run`, `rerun_with_custom_prompt`, `get_vendor_history`
    - Implement stdout capture utility using `io.StringIO` + `contextlib.redirect_stdout`
    - Implement `_format_stack_trace(e, max_frames=50)` helper
    - _Requirements: 2.2, 2.3, 8.5_

  - [x] 1.2 Create `sysadmin_test_tool_bp` blueprint with route stubs and validation
    - Create `backend/src/routes/sysadmin_test_tool.py`
    - Register blueprint under `sysadmin_bp` at `/test-tool/`
    - Define routes: `POST /process`, `POST /rerun-prompt`, `GET /vendor-history`
    - Apply `@cognito_required(required_roles=['SysAdmin'])` decorator on all routes
    - Implement file type validation (PDF, JPG, JPEG, PNG, CSV, EML, MHTML)
    - Implement file size validation (max 20 MB)
    - Implement vendor name validation (`^[a-zA-Z0-9_-]{1,100}$`)
    - Implement prompt length validation (1–10,000 characters)
    - Return 401 for unauthenticated, 403 for non-SysAdmin, 400 for invalid inputs
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.5, 6.4, 7.1_

  - [x] 1.3 Write property tests for input validation (backend)
    - **Property 1: File extension validation** — accept iff extension in {pdf, jpg, jpeg, png, csv, eml, mhtml} case-insensitive
    - **Property 9: Prompt length validation** — accept 1–10,000 chars, reject 0 or >10,000
    - **Property 10: Vendor name validation** — accept iff matches `^[a-zA-Z0-9_-]{1,100}$`
    - **Validates: Requirements 2.1, 2.5, 6.3, 6.4, 7.1**

- [x] 2. Implement dry-run pipeline execution
  - [x] 2.1 Implement `process_file_dry_run` method with timing and stage-by-stage error collection
    - Wrap pipeline execution in `try/finally` for temp file cleanup
    - Capture stdout during execution for execution log
    - Implement stage-by-stage try/except: file parsing → text extraction → AI/CSV extraction → transaction formatting → transaction preparation
    - Accumulate errors array with stage, error_type, message, stack_trace
    - Measure total pipeline duration in milliseconds
    - Measure AI API call duration separately
    - Collect AI model name and token usage from response
    - Return partial results for completed stages when later stages fail
    - _Requirements: 2.2, 2.3, 2.4, 2.6, 2.7, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 2.2 Implement raw text truncation and extraction result formatting
    - Truncate raw text to 50,000 characters with `raw_text_truncated` flag
    - Ensure all 5 extraction result fields are present (date, total_amount, vat_amount, description, vendor) with empty/0 defaults
    - Set `parser_used` to "ai", "csv_rule", or "ai_failed"
    - Include `folder_name` in result
    - Truncate execution log to most recent 10,000 characters
    - _Requirements: 3.1, 3.2, 3.3, 3.6, 3.7, 8.5_

  - [x] 2.3 Write property tests for pipeline output invariants (backend)
    - **Property 4: Raw text truncation invariant** — text >50k chars truncated to exactly 50k with flag true; ≤50k returned in full with flag false
    - **Property 5: Extraction result field completeness** — all 5 fields present as keys
    - **Property 6: Parser used is valid enum value** — exactly one of "ai", "csv_rule", "ai_failed"
    - **Property 13: Execution log truncation** — at most 10,000 characters, truncated to most recent
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.6, 8.5**

  - [x] 2.4 Implement AI usage preview and cost calculation
    - Compute cost estimate as `(total_tokens / 1,000,000) × rate_per_million` rounded to 6 decimal places
    - Build `ai_usage_preview` object with administration, feature, tokens_used, cost_estimate, cost_breakdown
    - Handle case where AI response lacks token info (tokens_used=0, cost_estimate=0.000000)
    - For CSV rule extraction, omit AI-specific metrics entirely (null values)
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 4.6_

  - [x] 2.5 Write property tests for AI metrics and cost calculation (backend)
    - **Property 7: AI metrics conditional on parser used** — ai → non-negative values; csv_rule → all null
    - **Property 8: Cost calculation correctness** — verify formula (tokens / 1,000,000) × rate to 6 decimal places
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.6, 5.1, 5.2**

- [x] 3. Implement custom prompt re-run and vendor history
  - [x] 3.1 Implement `rerun_with_custom_prompt` method
    - Accept text_content, custom_prompt, and optional vendor_hint
    - Call AIExtractor with the custom prompt against the provided text
    - Measure AI API call duration, collect model name and token usage
    - Compute AI usage preview for re-run (administration="test-tool-rerun", feature="invoice_extraction_rerun")
    - Return extraction result, performance metrics, and usage preview
    - Handle AI failures gracefully with error details
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6, 6.7, 6.8, 5.3_

  - [x] 3.2 Implement `get_vendor_history` method
    - Call `TransactionLogic.get_last_transactions` for the vendor with limit of 20
    - Return list of transactions with date, amount, description
    - Handle vendor not found (return empty list with message)
    - Default folder name to "TestVendor" when not provided
    - _Requirements: 7.2, 7.3, 7.4, 7.5_

  - [x] 3.3 Write property tests for vendor history and dry-run safety (backend)
    - **Property 11: Vendor history count limit** — returned list at most 20 items
    - **Property 2: Dry-run produces no side effects** — zero DB writes, zero Drive/S3 uploads
    - **Property 3: Temporary file cleanup** — all temp files removed after request
    - **Property 12: Partial result preservation on failure** — completed stages present in response
    - **Validates: Requirements 7.3, 2.2, 2.3, 2.6, 8.4**

- [x] 4. Checkpoint - Backend implementation complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Wire up backend API endpoints
  - [x] 5.1 Implement POST `/process` endpoint handler
    - Parse multipart/form-data: extract file and form fields
    - Validate file presence, type, size, and emptiness (0 bytes)
    - Save uploaded file to temp location
    - Default folderName to "TestVendor" if not provided
    - Call `InvoiceTestService.process_file_dry_run`
    - Return full JSON response with pipeline_result, performance, ai_usage_preview, execution_log, errors
    - _Requirements: 2.1, 2.4, 2.5, 2.6, 2.7, 7.4_

  - [x] 5.2 Implement POST `/rerun-prompt` endpoint handler
    - Parse JSON body: text_content, custom_prompt, vendor_hint
    - Validate prompt length (1–10,000 chars)
    - Call `InvoiceTestService.rerun_with_custom_prompt`
    - Return extraction_result, performance, ai_usage_preview, errors
    - _Requirements: 6.3, 6.4, 6.7, 6.8_

  - [x] 5.3 Implement GET `/vendor-history` endpoint handler
    - Parse query params: folderName (required), administration (optional)
    - Validate folderName format
    - Call `InvoiceTestService.get_vendor_history`
    - Return vendor_name, transactions list, count
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [x] 5.4 Register blueprint in sysadmin blueprint
    - Import and register `sysadmin_test_tool_bp` in the existing sysadmin blueprint module
    - Verify route accessibility under `/api/sysadmin/test-tool/`
    - _Requirements: 1.1, 1.3_

  - [-] 5.5 Write integration tests for API endpoints
    - Test 401 for unauthenticated requests
    - Test 403 for non-SysAdmin authenticated requests
    - Test 400 for invalid file types, oversized files, empty files, invalid vendor names, invalid prompts
    - Test 200 for successful process with mocked pipeline
    - Test 200 for successful rerun-prompt with mocked AI
    - Test 200 for vendor-history endpoint
    - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.5, 2.7, 6.4, 7.1_

- [x] 6. Checkpoint - Backend API complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Create frontend TypeScript types and API service
  - [x] 7.1 Create TypeScript interfaces for pipeline data models
    - Create `frontend/src/types/invoiceTestTool.ts`
    - Define interfaces: `PipelineResult`, `ExtractionResult`, `Transaction`, `PreparedTransaction`, `PerformanceMetrics`, `TokenUsage`, `AIUsagePreview`, `PipelineError`, `ModelFailure`, `CsvRuleDebug`
    - Define response types for process, rerun-prompt, and vendor-history endpoints
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2_

  - [x] 7.2 Create API service for test tool endpoints
    - Create `frontend/src/services/invoiceTestToolService.ts`
    - Implement `processFile(file, folderName?, administration?)` — multipart POST
    - Implement `rerunPrompt(textContent, customPrompt, vendorHint?)` — JSON POST
    - Implement `getVendorHistory(folderName, administration?)` — GET
    - Use existing auth token handling pattern
    - _Requirements: 2.1, 6.3, 7.2_

- [x] 8. Build frontend components
  - [x] 8.1 Create `InvoiceTestTool` tab component with upload form
    - Create `frontend/src/components/SysAdmin/InvoiceTestTool.tsx`
    - Implement file input accepting PDF/JPG/JPEG/PNG/CSV/EML/MHTML
    - Implement vendor name text input with validation
    - Implement administration text input (optional)
    - Implement submit button with loading state
    - Handle file size validation (20 MB client-side)
    - Display error messages for validation failures
    - _Requirements: 1.3, 2.1, 7.1, 7.4_

  - [x] 8.2 Create `PipelineResultsPanel` component
    - Create `frontend/src/components/SysAdmin/PipelineResultsPanel.tsx`
    - Display raw text with truncation indicator
    - Display extraction result with all 5 fields (show empty fields explicitly)
    - Display formatted transactions or empty-state
    - Display prepared transactions or empty-state
    - Display parser used and vendor/folder name
    - Present stages in sequential pipeline order
    - Inline `PerformanceMetrics`: total duration, AI duration, model name, token usage
    - Inline `AIUsagePreview`: usage log entry, cost breakdown
    - Inline `ExecutionLog`: collapsible stdout display
    - Inline `ErrorDisplay`: stage-by-stage errors with stack traces, model failures, CSV rule debug
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 8.3 Create `CustomPromptEditor` component
    - Create `frontend/src/components/SysAdmin/CustomPromptEditor.tsx`
    - Display original prompt used for extraction (read-only)
    - Provide editable textarea pre-populated with current prompt (max 10,000 chars)
    - Show character count and validation errors
    - Implement submit button with loading state and disabled during re-run
    - Display re-run result alongside original for comparison
    - Display re-run timing and token usage
    - Preserve original result and prompt text on re-run failure
    - Display error message on failure
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [x] 8.4 Create `VendorHistoryPanel` component
    - Create `frontend/src/components/SysAdmin/VendorHistoryPanel.tsx`
    - Display up to 20 previous transactions in read-only list (date, amount, description)
    - Display message when no transaction history found
    - Fetch vendor history when vendor name is provided and submitted
    - _Requirements: 7.2, 7.3, 7.5_

  - [x] 8.5 Write property tests for frontend validation logic
    - **Property 9: Prompt length validation (frontend)** — accept 1–10,000 chars, reject empty or >10,000
    - **Property 10: Vendor name validation (frontend)** — accept iff matches `^[a-zA-Z0-9_-]{1,100}$`
    - **Property 4: Raw text truncation display (frontend)** — verify truncation indicator logic
    - Create `frontend/src/components/SysAdmin/__tests__/InvoiceTestTool.prop.test.tsx`
    - **Validates: Requirements 6.4, 7.1, 3.1**

- [x] 9. Integrate tab into SysAdmin Dashboard
  - [x] 9.1 Register InvoiceTestTool as a tab in SysAdminDashboard
    - Add "Invoice Test Tool" tab to the existing SysAdmin Dashboard tab list
    - Lazy-load the InvoiceTestTool component
    - Ensure tab only renders for authenticated SysAdmin users
    - _Requirements: 1.1, 1.3_

  - [x] 9.2 Write unit tests for frontend components
    - Test component rendering with mock data
    - Test loading states and disabled submit during processing
    - Test error display for validation failures
    - Test comparison view after prompt re-run
    - Test empty states for formatted/prepared transactions
    - Create `frontend/src/components/SysAdmin/__tests__/InvoiceTestTool.test.tsx`
    - _Requirements: 6.5, 6.6, 6.8, 3.4, 3.5_

- [x] 10. Final checkpoint - All components integrated and tested
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The backend uses Python (Flask) and the frontend uses TypeScript (React + Chakra UI)
- Existing components (`PDFProcessor`, `AIExtractor`, `CsvRuleEngine`, `TransactionLogic`) are wrapped, not forked
- All pipeline execution is stateless and side-effect-free (dry-run mode)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "7.1"] },
    { "id": 1, "tasks": ["1.2", "7.2"] },
    { "id": 2, "tasks": ["1.3", "2.1"] },
    { "id": 3, "tasks": ["2.2", "2.4", "3.1", "3.2"] },
    { "id": 4, "tasks": ["2.3", "2.5", "3.3"] },
    { "id": 5, "tasks": ["5.1", "5.2", "5.3", "5.4"] },
    { "id": 6, "tasks": ["5.5", "8.1"] },
    { "id": 7, "tasks": ["8.2", "8.3", "8.4"] },
    { "id": 8, "tasks": ["8.5", "9.1"] },
    { "id": 9, "tasks": ["9.2"] }
  ]
}
```
