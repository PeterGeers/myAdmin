# Implementation Plan: Booking.com Multi-File Import

## Overview

Enhance the Booking.com import workflow to support uploading multiple CSV/Excel files simultaneously. The backend gets a new `_process_booking_multi()` method in `STRProcessor` that concatenates files, deduplicates by Book number, and processes through the existing Booking.com algorithm. The frontend enables multi-file selection for the `booking` platform with filename display and hint text. No changes needed to `str_routes.py` or `STRDatabase.insert_planned_bookings()`.

## Tasks

- [x] 1. Implement backend multi-file concatenation and processing
  - [x] 1.1 Add `_process_booking_multi(file_paths)` method to `STRProcessor` in `backend/src/str_processor.py`
    - Read each file path into a DataFrame (Excel via `pd.read_excel`, TSV via `pd.read_csv(sep='\t')`, or CSV via `pd.read_csv`)
    - Collect successful DataFrames and track failed filenames in an error list
    - If all files fail to parse, raise `ValueError` with the list of failed filenames
    - Concatenate all DataFrames with `pd.concat(dfs, ignore_index=True)`
    - Deduplicate by `Book number` keeping the last occurrence (`drop_duplicates(subset='Book number', keep='last')`)
    - Set `sourceFile` to `"{date} multi-import ({n} files)"` when multiple files provided, or `"{date} {filename}"` for single file
    - Process each row through the existing Booking.com algorithm (reuse per-row logic from `_process_booking`)
    - Return list of booking dicts
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4_

  - [x] 1.2 Modify `process_str_files()` to delegate to `_process_booking_multi` for booking platform
    - Add `elif platform.lower() in ['booking', 'booking.com']: return self._process_booking_multi(file_paths)` before the generic single-file loop
    - Preserve existing `_process_booking()` method unchanged for backward compatibility
    - _Requirements: 5.1, 7.1, 7.2_

  - [x] 1.3 Write property test: Concatenation preserves all rows (Property 1)
    - **Property 1: Concatenation preserves all rows**
    - Use Hypothesis to generate N random DataFrames with valid Booking.com columns
    - Verify `len(concat) == sum(len(df) for df in dfs)` before deduplication
    - Create test in `backend/tests/unit/test_str_booking_multi_import.py`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 2.1**

  - [x] 1.4 Write property test: Partial failure resilience (Property 2)
    - **Property 2: Partial failure resilience**
    - Use Hypothesis to generate mix of valid file paths and invalid file paths
    - Verify valid rows are processed and invalid filenames appear in error list
    - `@settings(max_examples=100)`
    - **Validates: Requirements 2.2**

  - [x] 1.5 Write property test: Deduplication keeps exactly one record per Book number (Property 3)
    - **Property 3: Deduplication keeps exactly one record per Book number**
    - Use Hypothesis to generate DataFrames with overlapping Book numbers
    - Verify uniqueness after dedup and that retained row matches last occurrence
    - `@settings(max_examples=100)`
    - **Validates: Requirements 2.3**

- [x] 2. Checkpoint - Ensure all backend concatenation tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement algorithm equivalence and sourceFile formatting
  - [x] 3.1 Extract per-row Booking.com calculation logic into a shared helper used by both `_process_booking` and `_process_booking_multi`
    - Extract the per-row calculation block (uplift factor, tax calculation, normalization, status determination) into a reusable internal method like `_calculate_booking_row(row, df_columns, source_file)`
    - Update `_process_booking` to call this shared helper
    - Update `_process_booking_multi` to call this shared helper
    - This ensures algorithm equivalence between single-file and multi-file paths
    - _Requirements: 3.1, 7.1_

  - [x] 3.2 Write property test: Multi-file algorithm equivalence (Property 4)
    - **Property 4: Multi-file algorithm equivalence**
    - Use Hypothesis to generate random booking rows with valid financial data
    - Compare `_process_booking_multi` output vs processing each row individually through `_process_booking`
    - Verify identical `amountGross`, `amountChannelFee`, `amountVat`, `amountTouristTax`, `amountNett`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 3.1, 7.1**

  - [x] 3.3 Write property test: sourceFile format reflects file count (Property 5)
    - **Property 5: sourceFile format reflects file count**
    - Use Hypothesis to generate random file counts (1 and N>1)
    - Verify single-file format `"YYYY-MM-DD {filename}"` and multi-file format `"YYYY-MM-DD multi-import (N files)"`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 3.4**

  - [x] 3.4 Write property test: Scoped overwrite invariant (Property 6)
    - **Property 6: Scoped overwrite invariant**
    - Use Hypothesis to generate random channel/listing pairs for existing and incoming data
    - Verify `insert_planned_bookings` deletes only imported pairs and leaves others unchanged
    - Use a mock or test database connection
    - `@settings(max_examples=100)`
    - **Validates: Requirements 4.1, 4.2**

  - [x] 3.5 Write unit tests for backend multi-file import
    - Create example-based tests in `backend/tests/unit/test_str_booking_multi_import.py`
    - Test: All files fail → `ValueError` raised with filenames (Req 2.5)
    - Test: Specific Green Studio + Red Studio import leaves Child Friendly untouched (Req 4.3)
    - Test: Response structure has expected keys from multi-file processing (Req 5.2)
    - Test: Single file upload works unchanged for all platforms (Req 7.2)
    - Test: Single booking file uses same delete-by-channel/listing strategy (Req 7.3)
    - _Requirements: 2.5, 4.3, 5.2, 7.2, 7.3_

- [x] 4. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement frontend multi-file selection and display
  - [x] 5.1 Enable multi-file input for booking platform in `frontend/src/components/STRProcessor.tsx`
    - Add `multiple` attribute to the file `<Input>` when `selectedPlatform === 'booking'` (same pattern as `vrbo`)
    - Update `handleFileUpload` to handle multiple files for `booking` platform: store all files in `selectedFiles`, keep first in `selectedFile`
    - Ensure `accept` attribute includes `.csv,.tsv,.xlsx,.xls` for booking platform
    - _Requirements: 1.1, 1.3_

  - [x] 5.2 Display all selected filenames and add hint text
    - Display all selected filenames in the existing `selectedFiles` text element (already shows for vrbo)
    - Add informational hint `<Alert>` for `booking` platform explaining multi-file support (similar to existing vrbo and payout hints)
    - _Requirements: 1.2, 6.4_

  - [x] 5.3 Update success message and warning display for multi-file imports
    - When multi-file booking import completes, display total number of files processed in success message (Req 6.1)
    - Display realised/planned/already-loaded counts in summary (Req 6.2) — already works via existing summary display
    - Display warning when backend reports failed files (Req 6.3) — parse error message for failed filenames
    - Ensure process button remains disabled when no files selected (Req 1.4) — already works via `!selectedFile` check
    - _Requirements: 1.4, 6.1, 6.2, 6.3_

  - [x] 5.4 Write property test: All selected filenames are displayed (Property 7)
    - **Property 7: All selected filenames are displayed**
    - Use fast-check to generate random filename lists
    - Render component with mock files and verify all filenames appear in rendered output
    - Create test in `frontend/src/components/STRProcessor.test.tsx`
    - `fc.assert(..., { numRuns: 100 })`
    - **Validates: Requirements 1.2**

  - [x] 5.5 Write unit tests for frontend multi-file import
    - Test: Booking platform enables multi-select on file input (Req 1.1)
    - Test: File input accepts .csv, .tsv, .xls, .xlsx for booking (Req 1.3)
    - Test: Process button disabled when no files selected (Req 1.4)
    - Test: Multi-file success shows file count (Req 6.1)
    - Test: Summary shows realised/planned/already-loaded counts (Req 6.2)
    - Test: Failed files warning displayed (Req 6.3)
    - Test: Booking platform shows multi-file hint (Req 6.4)
    - _Requirements: 1.1, 1.3, 1.4, 6.1, 6.2, 6.3, 6.4_

- [x] 6. Checkpoint - Ensure all frontend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Integration wiring and final verification
  - [x] 7.1 Verify end-to-end flow: multi-file upload through route to processor
    - Confirm `str_routes.py` already passes `temp_paths` list to `process_str_files()` — no changes needed
    - Confirm temp file cleanup works for multiple files — already handled by existing loop
    - Confirm response structure is unchanged for multi-file uploads
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 7.2 Write integration tests
    - Test: Mixed .csv/.tsv/.xls/.xlsx files processed together (Req 2.4)
    - Test: Route passes all file paths to processor (Req 5.1)
    - Test: Temp files cleaned up after success and failure (Req 5.4)
    - Test: Single-file upload backward compat for all platforms (Req 7.2)
    - Create tests in `backend/tests/integration/test_str_multi_file_integration.py`
    - _Requirements: 2.4, 5.1, 5.4, 7.2_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Commit and push to main
  - Stage all changed files related to this feature
  - Create a commit with message: `feat: add Booking.com multi-file import support`
  - Push to main branch

## Notes

- All tasks are required
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- No changes needed to `str_routes.py` — it already handles `getlist('file')` and passes all paths
- No changes needed to `STRDatabase.insert_planned_bookings()` — it already deletes by `(channel, listing)` pair
- Backend tests use pytest + Hypothesis; frontend tests use Vitest + fast-check
