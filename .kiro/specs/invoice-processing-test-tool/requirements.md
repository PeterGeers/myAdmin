# Requirements Document

## Introduction

The Invoice Processing Test Tool is a SysAdmin-only diagnostic interface for testing the invoice processing pipeline in dry-run mode. It allows system administrators to upload invoice files and inspect every stage of the extraction pipeline — from raw text extraction through AI analysis to final transaction preparation — without writing to the database or uploading to external storage. This tool is essential for debugging extraction issues, testing AI prompt changes, and validating pipeline behavior without polluting production data.

## Glossary

- **Test_Tool**: The Invoice Processing Test Tool component accessible only to System Administrators
- **Pipeline**: The complete invoice processing chain: file parsing → text extraction → AI/CSV extraction → transaction formatting → transaction preparation
- **Dry_Run**: An execution mode where the pipeline processes a file but produces no side effects (no database writes, no Google Drive uploads, no S3 uploads)
- **AI_Extractor**: The component that sends extracted text to OpenRouter API models to extract structured invoice data (date, amount, VAT, description, vendor)
- **CSV_Rule_Engine**: The declarative rule-based parser for structured CSV files (e.g., Airbnb statements)
- **PDFProcessor**: The component responsible for parsing files (PDF, image, CSV, EML, MHTML) and extracting raw text content
- **Pipeline_Result**: The complete output of a dry-run execution including raw text, AI extraction result, formatted transactions, and prepared transactions
- **Extraction_Prompt**: The AI prompt template sent to OpenRouter API for invoice data extraction
- **System_Administrator**: A user with the SysAdmin role in AWS Cognito

## Requirements

### Requirement 1: Access Control

**User Story:** As a System Administrator, I want the test tool to be restricted to SysAdmin users only, so that sensitive pipeline internals and AI prompts are not exposed to regular users.

#### Acceptance Criteria

1. THE Test_Tool SHALL require the SysAdmin role for access to both the frontend tab and backend API endpoints
2. IF an authenticated non-SysAdmin user attempts to access any Test_Tool API endpoint, THEN THE Test_Tool SHALL return a 403 Forbidden response with an error message indicating insufficient permissions
3. THE Test_Tool SHALL appear as a tab within the existing SysAdmin Dashboard interface
4. IF an unauthenticated request is made to any Test_Tool API endpoint, THEN THE Test_Tool SHALL return a 401 Unauthorized response with an error message indicating authentication is required

### Requirement 2: File Upload in Dry-Run Mode

**User Story:** As a System Administrator, I want to upload an invoice file and have it processed in dry-run mode, so that I can inspect the pipeline output without affecting production data.

#### Acceptance Criteria

1. THE Test_Tool SHALL accept file uploads with extensions: PDF, JPG, JPEG, PNG, CSV, EML, MHTML with a maximum file size of 20 MB
2. WHEN a file is uploaded, THE Test_Tool SHALL process the file through the complete pipeline without writing to the database
3. WHEN a file is uploaded, THE Test_Tool SHALL process the file without uploading to Google Drive or S3
4. WHEN a file is uploaded, THE Test_Tool SHALL execute the full pipeline sequence: file parsing, text extraction, AI/CSV extraction, transaction formatting, and transaction preparation
5. IF an unsupported file type is uploaded, THEN THE Test_Tool SHALL reject the upload and return an error message indicating the allowed file types
6. THE Test_Tool SHALL clean up any temporary files created during processing, including when any pipeline stage fails or the request is interrupted
7. IF an uploaded file is empty (0 bytes) or cannot be parsed by the PDFProcessor, THEN THE Test_Tool SHALL return an error message indicating the file is empty or corrupted

### Requirement 3: Pipeline Output Transparency

**User Story:** As a System Administrator, I want to see the complete output of each pipeline stage, so that I can diagnose extraction issues and understand how the pipeline processes a specific file.

#### Acceptance Criteria

1. WHEN a file is processed, THE Test_Tool SHALL display the raw extracted text from the file, truncated to a maximum of 50,000 characters with an indication if truncation occurred
2. WHEN a file is processed using AI extraction, THE Test_Tool SHALL display the structured AI extraction result including date, total amount, VAT amount, description, and vendor, showing empty fields as explicitly blank rather than omitting them
3. WHEN a file is processed using csv_rule extraction, THE Test_Tool SHALL display the structured extraction result with the same field layout as AI extraction (date, total amount, VAT amount, description, and vendor)
4. WHEN a file is processed, THE Test_Tool SHALL display the formatted transactions (output of the transaction formatting stage), or an empty-state indication if no transactions were produced
5. WHEN a file is processed, THE Test_Tool SHALL display the proposed prepared transactions (output of the transaction preparation stage), or an empty-state indication if no transactions were produced
6. WHEN a file is processed, THE Test_Tool SHALL display which parser was used: "ai", "csv_rule", or "ai_failed"
7. WHEN a file is processed, THE Test_Tool SHALL display the vendor/folder name determined by the pipeline
8. WHEN a file is processed, THE Test_Tool SHALL present all pipeline stage outputs in sequential pipeline order: raw text, extraction result, formatted transactions, prepared transactions, parser used, and vendor name

### Requirement 4: Performance Metrics

**User Story:** As a System Administrator, I want to see timing information for the extraction process, so that I can identify performance bottlenecks and monitor AI response times.

#### Acceptance Criteria

1. WHEN a file is processed, THE Test_Tool SHALL measure and display the total pipeline execution time in milliseconds, measured from the start of file parsing to the completion of transaction preparation
2. WHEN AI extraction is used, THE Test_Tool SHALL measure and display the AI API call duration in milliseconds, measured from the request initiation to receiving the response
3. WHEN AI extraction is used, THE Test_Tool SHALL display the AI model name that was used for the successful extraction
4. WHEN AI extraction is used, THE Test_Tool SHALL display token usage information including prompt tokens, completion tokens, and total tokens as reported by the AI API response
5. IF AI extraction fails and fallback data is returned, THEN THE Test_Tool SHALL display zero values for token counts and indicate that no model completed extraction successfully
6. IF the CSV_Rule_Engine is used instead of AI extraction, THEN THE Test_Tool SHALL omit AI-specific metrics (API call duration, model name, and token usage) from the performance output

### Requirement 5: AI Usage Log Preview

**User Story:** As a System Administrator, I want to see what would be written to the AI usage log, so that I can verify cost tracking accuracy and monitor token consumption before deploying prompt changes.

#### Acceptance Criteria

1. WHEN AI extraction is used, THE Test_Tool SHALL display the AI usage log entry that would be stored, including: administration (tenant identifier), feature identifier (formatted as the extraction feature name), tokens used (integer), and cost estimate (decimal to 6 places)
2. WHEN AI extraction is used, THE Test_Tool SHALL display the cost calculation breakdown showing: the model name used, the pricing rate per 1 million tokens for that model, the total token count, and the resulting cost estimate computed as (tokens / 1,000,000) × rate
3. WHEN a custom prompt re-run is performed, THE Test_Tool SHALL display the AI usage log entry that would be generated for the re-run, using the same fields as criterion 1 with token counts and cost from the re-run response
4. THE Test_Tool SHALL NOT write any entries to the ai_usage_log table (dry-run mode)
5. IF the AI response does not include token usage information, THEN THE Test_Tool SHALL display the usage log entry with tokens_used as 0 and cost_estimate as 0.000000, and indicate that token data was unavailable

### Requirement 6: Custom Prompt Testing

**User Story:** As a System Administrator, I want to edit the AI extraction prompt and re-run the extraction, so that I can test prompt improvements and compare results without deploying code changes.

#### Acceptance Criteria

1. WHEN a file has been processed using AI extraction, THE Test_Tool SHALL display the prompt that was used for extraction
2. WHEN a file has been processed using AI extraction, THE Test_Tool SHALL provide an editable text area pre-populated with the current extraction prompt, supporting prompts up to 10,000 characters
3. WHEN the System Administrator submits a modified prompt that is between 1 and 10,000 characters, THE Test_Tool SHALL re-run AI extraction using the modified prompt against the same extracted text
4. IF the System Administrator submits an empty prompt or a prompt exceeding 10,000 characters, THEN THE Test_Tool SHALL display a validation error indicating the allowed prompt length range
5. WHEN a re-run is in progress, THE Test_Tool SHALL display a loading indicator and disable the submit action until the re-run completes or fails
6. WHEN a re-run completes successfully, THE Test_Tool SHALL display the new extraction result alongside the original result for comparison
7. WHEN a re-run completes successfully, THE Test_Tool SHALL display timing (AI API call duration in milliseconds) and token usage (prompt tokens, completion tokens, total tokens) for the re-run
8. IF the AI extraction fails during a re-run, THEN THE Test_Tool SHALL display an error message indicating the failure reason and preserve the original result and the modified prompt text

### Requirement 7: Vendor Context Configuration

**User Story:** As a System Administrator, I want to specify a vendor/folder name for the test extraction, so that the pipeline can use vendor-specific context and previous transaction history during extraction.

#### Acceptance Criteria

1. THE Test_Tool SHALL provide a text input field for the vendor/folder name before file upload, accepting alphanumeric characters, hyphens, and underscores with a maximum length of 100 characters
2. WHEN a vendor name is provided, THE Test_Tool SHALL pass the vendor name to the pipeline so that extraction uses vendor-specific context including previous transaction history for field matching
3. WHEN a vendor name is provided, THE Test_Tool SHALL retrieve and display up to the 20 most recent previous transactions for that vendor in a read-only list showing date, amount, and description
4. IF no vendor name is provided, THEN THE Test_Tool SHALL default to "TestVendor" as the folder name
5. IF a vendor name is provided but no previous transactions exist for that vendor, THEN THE Test_Tool SHALL display a message indicating no transaction history was found and proceed with extraction without historical context

### Requirement 8: Error Handling and Diagnostics

**User Story:** As a System Administrator, I want to see detailed error information when the pipeline fails, so that I can diagnose issues with specific file types or extraction scenarios.

#### Acceptance Criteria

1. IF the file parsing stage fails, THEN THE Test_Tool SHALL display the error type, error message, and stack trace (limited to the most recent 50 frames)
2. IF the AI extraction fails or times out (no successful response within 10 seconds per model), THEN THE Test_Tool SHALL display the failure reason for each model attempted, including the model name and whether the failure was a timeout, an API error, or an invalid response
3. IF the CSV rule matching fails, THEN THE Test_Tool SHALL display which rules were evaluated, whether the folder pattern matched, and the reason each rule did not produce a result (no pattern match versus data parsing error)
4. WHEN any pipeline stage fails, THE Test_Tool SHALL still display results from all successfully completed prior stages
5. THE Test_Tool SHALL capture and display the pipeline execution log (stdout print statements produced during processing), truncated to the most recent 10,000 characters if the log exceeds that length
6. IF all AI models are exhausted without a successful extraction, THEN THE Test_Tool SHALL display a summary listing every model attempted and its individual failure reason
