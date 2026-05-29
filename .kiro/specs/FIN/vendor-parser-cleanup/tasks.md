# Implementation Plan: Vendor Parser Cleanup

## Overview

Remove all 22 legacy vendor-specific regex parsers from the invoice processing pipeline, making AI extraction the sole method for PDF/image/EML/MHTML files. Introduce a declarative `CsvRuleEngine` for structured CSV aggregation, update `parser_used` reporting to only use `"ai"`, `"ai_failed"`, and `"csv_rule"`, and clean up all related tests.

## Tasks

- [x] 1. Create CsvRuleEngine module
  - [x] 1.1 Create `backend/src/csv_rules.py` with `CsvAggregationRule` dataclass and `CsvRuleEngine` class
    - Define `CsvAggregationRule` dataclass with fields: folder_pattern, amount_column, amount_operation, date_column, date_operation, description_template, vat_amount
    - Define `CSV_RULES` registry list with the Airbnb rule (folder_pattern="airbnb", amount_column="Nettobedag", amount_operation="sum", date_column="Datum van dienst", date_operation="max", description_template="Hosting Fee; {filename}", vat_amount=0.0)
    - Implement `CsvRuleEngine` class with `get_rule()`, `apply()`, `_extract_csv_data()`, and `_extract_filename()` methods
    - _Requirements: 6.1, 6.2, 6.3, 6.5_

  - [x] 1.2 Write property test for CSV rule routing (Property 5)
    - **Property 5: CSV rule routing**
    - Generate random folder names; verify that matching folders route to CsvRuleEngine and non-matching folders fall through to AI
    - **Validates: Requirements 6.1, 6.4**

  - [x] 1.3 Write property test for CSV aggregation correctness (Property 6)
    - **Property 6: CSV aggregation correctness**
    - Generate random DataFrames with Nettobedag/Datum van dienst columns; verify sum, max date, vat=0.0, and description prefix
    - **Validates: Requirements 6.3**

  - [x] 1.4 Write unit tests for CsvRuleEngine
    - Test `get_rule()` returns matching rule for "airbnb" folder
    - Test `get_rule()` returns None for non-matching folder
    - Test `apply()` correctly aggregates CSV data
    - Test `apply()` returns None when CSV data is malformed or missing expected columns
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 2. Refactor PDFProcessor to remove vendor parsers and add AI-only extraction
  - [x] 2.1 Remove VendorParsers dependency from `backend/src/pdf_processor.py`
    - Remove `from vendor_parsers import VendorParsers` import
    - Remove `self.vendor_parsers = VendorParsers()` from `__init__`
    - Remove the entire `_parse_vendor_specific()` method (if/elif chain)
    - Add `from csv_rules import CsvRuleEngine` import
    - Add `self.csv_rule_engine = CsvRuleEngine()` in `__init__`
    - _Requirements: 1.1, 1.2, 3.1, 3.2_

  - [x] 2.2 Implement `_extract_with_ai()` method in PDFProcessor
    - Create method that calls `AIExtractor.extract_invoice_data()` with text content and folder name
    - Include previous transaction context retrieval from DatabaseManager
    - Log AI extraction start, success, and failure messages to stdout
    - Return AI result on success, None on exception
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.3, 3.4_

  - [x] 2.3 Implement `_apply_csv_rule()` method in PDFProcessor
    - Create method that delegates to `CsvRuleEngine.get_rule()` and `CsvRuleEngine.apply()`
    - Return None if no rule matches or rule application fails
    - _Requirements: 6.1, 6.4_

  - [x] 2.4 Update `extract_transactions()` routing logic in PDFProcessor
    - Route image files with `ai_data` key directly
    - Route CSV files through `_apply_csv_rule()` first, fall through to AI if no match
    - Route all other files (PDF/EML/MHTML) through `_extract_with_ai()`
    - Handle AI failure by returning failure data structure with total_amount=0.0, vat_amount=0.0, description containing folder name
    - _Requirements: 1.6, 2.1, 2.2, 2.3, 5.1, 6.1, 6.4_

  - [x] 2.5 Implement `_log_ai_usage()` method in PDFProcessor
    - Log AI extraction usage to `ai_usage_log` table via `AIUsageTracker`
    - Use actual token counts from `_usage` metadata in AI result
    - Skip logging if no token data available; never fail extraction due to logging errors
    - _Requirements: 2.1_

  - [x] 2.6 Write property test for AI-only extraction path (Property 1)
    - **Property 1: AI-only extraction path**
    - Generate random folder names and text content (not matching CSV rules); mock AIExtractor; verify it's called with correct args and no vendor parser is invoked
    - **Validates: Requirements 1.6, 2.1, 3.3**

  - [x] 2.7 Write property test for valid AI result passthrough (Property 2)
    - **Property 2: Valid AI result passthrough**
    - Generate random valid AI results (total_amount > 0); verify output contains all required fields (date, total_amount, vat_amount, description, vendor)
    - **Validates: Requirements 2.2, 2.5**

  - [x] 2.8 Write property test for AI failure fallback structure (Property 3)
    - **Property 3: AI failure produces correct fallback structure**
    - Generate random folder names and exceptions; verify fallback structure has total_amount=0.0, vat_amount=0.0, description containing folder name, and logging occurs
    - **Validates: Requirements 2.3, 2.4, 5.1, 5.2**

- [x] 3. Checkpoint - Verify PDFProcessor refactoring
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Update AIExtractor to include token usage metadata
  - [x] 4.1 Modify `AIExtractor.extract_invoice_data()` in `backend/src/ai_extractor.py` to capture token usage
    - After successful API response, extract `usage` field from OpenRouter response JSON
    - Include `_usage` metadata key in return value with prompt_tokens, completion_tokens, total_tokens, and model
    - Ensure `_fallback_data()` returns `_usage` with all zeros
    - _Requirements: 2.1, 2.5_

- [x] 5. Update InvoiceService for parser_used reporting
  - [x] 5.1 Modify `InvoiceService.process_invoice_file()` in `backend/src/services/invoice_service.py`
    - Remove all calls to `_parse_vendor_specific()`
    - Remove `vendor_data` field from return dictionaries
    - Add call to `_determine_parser_used()` to set parser_used in response
    - _Requirements: 1.4, 4.1, 4.2, 4.3, 4.4_

  - [x] 5.2 Implement `_determine_parser_used()` method in InvoiceService
    - Return `"csv_rule"` when CSV rule marker is present in transaction data
    - Return `"ai"` when extraction produced a valid amount (> 0)
    - Return `"ai_failed"` when no transactions or amount is zero
    - Never return `"vendor_specific"` or any vendor name
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.5, 6.6_

  - [x] 5.3 Write property test for parser_used field correctness (Property 4)
    - **Property 4: parser_used field correctness**
    - Generate random extraction scenarios; verify parser_used is always in {"ai", "ai_failed", "csv_rule"}
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 5.5, 6.6**

  - [x] 5.4 Write unit tests for InvoiceService parser_used reporting
    - Test `_determine_parser_used()` returns "ai" for successful extraction
    - Test `_determine_parser_used()` returns "ai_failed" for zero amount
    - Test `_determine_parser_used()` returns "csv_rule" for CSV rule results
    - Test response does not contain `vendor_data` key
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 6. Checkpoint - Verify InvoiceService and AIExtractor changes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Delete vendor_parsers.py and clean up tests
  - [x] 7.1 Delete `backend/src/vendor_parsers.py`
    - Remove the entire 979-line vendor parsers file
    - _Requirements: 1.3_

  - [x] 7.2 Clean up test files that reference VendorParsers
    - Remove `from vendor_parsers import VendorParsers` imports from all test files
    - Remove test cases that exercise individual vendor parser methods
    - Remove mock/patch references to vendor_parsers attributes
    - Remove `hasattr(processor, 'vendor_parsers')` assertions
    - Update `test_pdf_processor.py` and `test_duplicate_integration_e2e.py`
    - _Requirements: 7.1, 7.2, 7.5_

  - [x] 7.3 Add tests verifying AI-only extraction behavior
    - Add test for successful AI extraction returning valid amount
    - Add test for AI extraction returning no valid amount (total_amount=0)
    - Add test for AIExtractor raising exception resulting in logged error and total_amount=0
    - Add test verifying no VendorParsers import exists in pdf_processor.py
    - _Requirements: 7.3, 7.4_

- [x] 8. Final checkpoint - Full test suite verification
  - Ensure all tests pass with zero failures caused by missing vendor parser references (ImportError, AttributeError, NameError), ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project uses pytest with Hypothesis for property-based testing (Python backend)
- All code changes are in `backend/src/` and `backend/tests/`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "4.1"] },
    { "id": 3, "tasks": ["2.4", "2.5"] },
    { "id": 4, "tasks": ["2.6", "2.7", "2.8", "5.1"] },
    { "id": 5, "tasks": ["5.2"] },
    { "id": 6, "tasks": ["5.3", "5.4", "7.1"] },
    { "id": 7, "tasks": ["7.2"] },
    { "id": 8, "tasks": ["7.3"] }
  ]
}
```
