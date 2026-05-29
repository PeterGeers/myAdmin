# Requirements Document

## Introduction

This feature removes all legacy vendor-specific parsers from the myAdmin invoice processing pipeline. The system currently uses AI extraction (OpenRouter API) as the primary method and falls back to 22 vendor-specific regex parsers when AI extraction fails or returns no valid amount. After this cleanup, the system will rely exclusively on AI extraction with improved error handling, eliminating the maintenance burden of brittle regex-based parsers.

## Glossary

- **AI_Extractor**: The `AIExtractor` class that calls the OpenRouter API to extract structured invoice data (date, description, total amount, VAT amount) from raw text content
- **PDF_Processor**: The `PDFProcessor` class responsible for reading PDF/image/CSV/EML/MHTML files, extracting text, and orchestrating data extraction
- **Invoice_Service**: The `InvoiceService` class that coordinates file upload, processing, duplicate detection, and transaction preparation
- **Vendor_Parsers**: The legacy `VendorParsers` class containing 22 regex-based parser methods for specific vendors (to be removed)
- **Fallback_Chain**: The current control flow in `_parse_vendor_specific()` that tries AI extraction first, then falls back to vendor-specific parsers

## Requirements

### Requirement 1: Remove Vendor Parser Module

**User Story:** As a developer, I want the vendor parser module removed entirely, so that the codebase is simpler and there is no dead code to maintain.

#### Acceptance Criteria

1. THE PDF_Processor SHALL NOT import or reference the VendorParsers class
2. THE PDF_Processor SHALL NOT contain a `_parse_vendor_specific` method or any method that dispatches to vendor-specific parsing functions
3. WHEN the system is deployed, THE `vendor_parsers.py` file SHALL NOT exist in the `backend/src/` directory
4. THE Invoice_Service SHALL NOT call `_parse_vendor_specific()` or include any `vendor_data` field in its return values
5. THE test suite SHALL NOT contain import statements for VendorParsers or assertions that depend on vendor-specific parsing methods
6. WHEN a PDF is processed, THE PDF_Processor SHALL rely solely on AI extraction to produce invoice data without falling back to vendor-specific parsers

### Requirement 2: AI-Only Extraction Flow

**User Story:** As a developer, I want the invoice processing to use only AI extraction, so that the system has a single, consistent extraction path.

#### Acceptance Criteria

1. WHEN a PDF file is processed, THE PDF_Processor SHALL extract text from the PDF and pass the text content along with the vendor folder name to the AI_Extractor
2. WHEN the AI_Extractor returns a result containing a total_amount greater than zero, THE PDF_Processor SHALL use that result as the extracted vendor data without invoking any vendor-specific fallback parser
3. IF the AI_Extractor returns a result where total_amount is zero or the result is empty, THEN THE PDF_Processor SHALL return a result with success set to false and an error message indicating extraction failure, without attempting any fallback parser
4. IF the AI_Extractor raises an exception during extraction, THEN THE PDF_Processor SHALL log the exception message to the console and return a result with success set to false and an error message indicating extraction failure
5. WHEN the AI_Extractor returns a valid result, THE PDF_Processor SHALL include at minimum the following fields in the extracted vendor data: date, total_amount, vat_amount, description, and vendor

### Requirement 3: Remove Fallback Chain

**User Story:** As a developer, I want the if/elif vendor matching chain removed, so that there is no conditional branching based on folder names for parsing.

#### Acceptance Criteria

1. THE PDF_Processor SHALL NOT contain any if/elif chain that matches folder names to parser methods
2. THE PDF*Processor SHALL NOT call any method prefixed with `parse*` on a vendor-specific parser object
3. WHEN a folder name is provided, THE PDF_Processor SHALL pass it to the AI_Extractor as context for extraction only, not for routing to a specific parser
4. THE `_parse_vendor_specific` method SHALL be replaced by a method that exclusively calls the AI_Extractor without any vendor-specific branching logic

### Requirement 4: Parser Used Reporting

**User Story:** As a user, I want the system to accurately report which extraction method was used, so that I can understand how my invoice was processed.

#### Acceptance Criteria

1. WHEN the AI_Extractor returns a result with a total_amount greater than zero, THE Invoice_Service SHALL report the parser_used field as "ai"
2. WHEN the AI_Extractor returns no valid amount or raises an exception, THE Invoice_Service SHALL report the parser_used field as "ai_failed"
3. THE Invoice_Service SHALL NOT report parser_used as "vendor_specific" or any vendor name
4. THE Invoice_Service SHALL only use the values "ai", "ai_failed", and "csv_rule" for the parser_used field

### Requirement 5: Error Handling for AI Failures

**User Story:** As a user, I want clear feedback when AI extraction fails, so that I can take corrective action such as manual entry.

#### Acceptance Criteria

1. WHEN the AI_Extractor returns a result with total_amount equal to zero, THE PDF_Processor SHALL return a data structure with total_amount set to 0.0, vat_amount set to 0.0, and a description field containing the folder name followed by the text "invoice" to indicate extraction was unsuccessful
2. WHEN the AI_Extractor raises an exception during extraction, THE PDF_Processor SHALL log the error details including the folder name and the exception message to standard output before returning a failure result
3. IF the OpenRouter API is unreachable for all configured models (each timing out after 10 seconds), THEN THE AI_Extractor SHALL return the fallback data structure with total_amount set to 0.0 and description containing the folder name
4. WHEN the PDF_Processor returns a result with total_amount equal to zero, THE Invoice_Service SHALL return an HTTP 200 response with success set to true and the extraction result included in the response data, allowing the user to manually enter transaction data
5. WHEN AI extraction fails, THE Invoice_Service SHALL set the parser_used field to "ai_failed" in the response data so the client can distinguish between successful and failed extractions

### Requirement 6: CSV Aggregation Rules

**User Story:** As a developer, I want structured CSV files with known column layouts handled by declarative business rules rather than AI extraction, so that numeric aggregation is deterministic, cost-free, and reliable.

#### Acceptance Criteria

1. WHEN a CSV file is processed and the folder name matches a configured CSV aggregation rule, THE PDF_Processor SHALL apply the business rule instead of calling the AI_Extractor
2. THE system SHALL support a declarative CSV rule format specifying at minimum: a folder name match pattern, an amount column name, an aggregation operation (sum), a date column name, a date operation (max), a default description, and a fixed VAT amount
3. WHEN the Airbnb CSV rule is applied, THE system SHALL sum the `Nettobedag` column, use the maximum value of `Datum van dienst` as the transaction date, set VAT to 0.0, and set the description to "Hosting Fee" followed by the filename
4. IF a CSV file matches no configured aggregation rule, THEN THE PDF_Processor SHALL pass the CSV text content to the AI_Extractor for extraction
5. THE CSV aggregation rules SHALL be defined in a dedicated configuration structure (not hardcoded in if/elif chains) so that new CSV rules can be added without modifying extraction logic
6. WHEN a CSV aggregation rule is applied successfully, THE Invoice_Service SHALL report the parser_used field as "csv_rule"

### Requirement 7: Test Cleanup

**User Story:** As a developer, I want all tests referencing vendor parsers updated or removed, so that the test suite remains green and reflects the new architecture.

#### Acceptance Criteria

1. THE test suite SHALL NOT contain any imports of the VendorParsers class or the vendor_parsers module
2. THE test suite SHALL NOT contain test cases that exercise individual vendor parser methods, nor any mock or patch references to a vendor_parsers attribute or object
3. WHEN the test suite is executed via pytest, THE test suite SHALL produce zero failures caused by missing vendor parser references including ImportError, AttributeError, and NameError
4. THE test suite SHALL contain tests verifying AI-only extraction behavior covering at minimum: successful extraction returning a valid amount, extraction returning no valid amount resulting in total_amount of zero, and AI_Extractor raising an exception resulting in a logged error and total_amount of zero
5. THE test suite SHALL NOT contain assertions that verify the existence of a vendor_parsers attribute on the PDF_Processor class
