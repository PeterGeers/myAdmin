# Implementation Plan: Airbnb Multi-File Import

## Overview

Enhance the Airbnb import workflow to support uploading multiple CSV files simultaneously. The backend gets a new `_process_airbnb_multi()` method and a `_calculate_airbnb_row()` helper in `STRProcessor` that concatenates files, deduplicates by `Bevestigingscode`, and processes through the Airbnb algorithm (15% channel fee factor). The old `_process_airbnb()` method is removed entirely — a single file is just a list of one. The frontend enables multi-file selection for the `airbnb` platform with `.csv`-only accept, filename display, and hint text. No changes needed to `str_routes.py` or `STRDatabase.insert_planned_bookings()`.

## Tasks

- [x] 1. Implement backend per-row calculation helper and multi-file processing
  - [x] 1.1 Extract `_calculate_airbnb_row(row, df_columns, source_file)` method in `backend/src/str_processor.py`
    - Extract the per-row calculation logic from the existing `_process_airbnb()` method into a new `_calculate_airbnb_row(self, row, df_columns, source_file)` method
    - Handle Dutch column mapping: `Begindatum`, `Einddatum`, `Naam van de gast`, `Advertentie`, `# nachten`, `Inkomsten`, `Bevestigingscode`, `Status`, `Contact`, `# volwassenen`, `# kinderen`, `# baby's`, `Gereserveerd`
    - Parse `Inkomsten` using European currency format (`€ 1.841,18` → `1841.18`)
    - Skip rows where status contains `Geannuleerd` and earnings == 0 (return `None`)
    - Calculate financials: `amountChannelFee = paidOut × 0.15`, `amountGross = paidOut + amountChannelFee`, then `calculate_str_taxes()`
    - Normalize listing name via `_normalize_listing_name()`
    - Detect country via `detect_country('airbnb', phone=phone, addinfo=add_info)`
    - Return booking dict or `None` if row should be skipped
    - _Requirements: 3.1, 3.2, 3.5, 3.6_

  - [x] 1.2 Add `_process_airbnb_multi(file_paths)` method to `STRProcessor` in `backend/src/str_processor.py`
    - Read each file path into a DataFrame via `pd.read_csv()`
    - Collect successful DataFrames and track failed filenames in an error list
    - If all files fail to parse, raise `ValueError` with the list of failed filenames
    - Concatenate all DataFrames with `pd.concat(dfs, ignore_index=True)`
    - Deduplicate by `Bevestigingscode` keeping the last occurrence (`drop_duplicates(subset='Bevestigingscode', keep='last')`)
    - Set `sourceFile` to `"{date} multi-import ({n} files)"` when multiple files provided, or `"{date} {filename}"` for single file
    - Process each row through `_calculate_airbnb_row(row, combined.columns, source_file)`
    - Log warnings for any failed files
    - Return list of booking dicts
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.4_

  - [x] 1.3 Modify `process_str_files()` to delegate to `_process_airbnb_multi` for airbnb platform
    - Add `elif platform.lower() == 'airbnb': return self._process_airbnb_multi(file_paths)` before the generic single-file loop
    - _Requirements: 5.1_

  - [x] 1.4 Remove old `_process_airbnb(file_path)` method
    - Delete the old single-file `_process_airbnb()` method entirely
    - Update `_process_single_file()` to remove the `airbnb` branch (it's now handled by `process_str_files` directly)
    - A single file is just a list of one passed through `_process_airbnb_multi()`
    - _Requirements: 3.1_

  - [x] 1.5 Write property test: Concatenation preserves all rows (Property 1)
    - **Property 1: Concatenation preserves all rows**
    - Use Hypothesis to generate N random DataFrames with valid Airbnb columns (`Begindatum`, `Einddatum`, `Inkomsten`, `Bevestigingscode`, etc.)
    - Verify `len(concat) == sum(len(df) for df in dfs)` before deduplication
    - Create test in `backend/tests/unit/test_str_airbnb_multi_import.py`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 2.1**

  - [x] 1.6 Write property test: Partial failure resilience (Property 2)
    - **Property 2: Partial failure resilience**
    - Use Hypothesis to generate mix of valid file paths and invalid file paths
    - Verify valid rows are processed and invalid filenames appear in error list
    - `@settings(max_examples=100)`
    - **Validates: Requirements 2.2**

  - [x] 1.7 Write property test: Deduplication keeps exactly one record per Bevestigingscode (Property 3)
    - **Property 3: Deduplication keeps exactly one record per Bevestigingscode**
    - Use Hypothesis to generate DataFrames with overlapping `Bevestigingscode` values
    - Verify uniqueness after dedup and that retained row matches last occurrence
    - `@settings(max_examples=100)`
    - **Validates: Requirements 2.3**

- [x] 2. Checkpoint - Ensure all backend concatenation tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement financial calculation tests and sourceFile formatting
  - [x] 3.1 Write property test: Financial calculation correctness (Property 4)
    - **Property 4: Financial calculation correctness**
    - Use Hypothesis to generate random booking rows with valid non-negative `Inkomsten` values
    - Verify `amountChannelFee == paidOut × 0.15`, `amountGross == paidOut + amountChannelFee`
    - Verify tax amounts match output of `calculate_str_taxes()` for the same gross and check-in date
    - Verify listing normalization is applied consistently
    - `@settings(max_examples=100)`
    - **Validates: Requirements 3.1, 3.2**

  - [x] 3.2 Write property test: sourceFile format reflects file count (Property 5)
    - **Property 5: sourceFile format reflects file count**
    - Use Hypothesis to generate random file counts (1 and N>1)
    - Verify single-file format `"YYYY-MM-DD {filename}"` and multi-file format `"YYYY-MM-DD multi-import (N files)"`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 3.4**

  - [x] 3.3 Write property test: European currency parsing round-trip (Property 6)
    - **Property 6: European currency parsing round-trip**
    - Use Hypothesis to generate random non-negative monetary amounts
    - Format as European currency string (`€ X.XXX,XX`), parse back through the Airbnb earnings parser
    - Verify equivalence within floating-point rounding tolerance of 0.01
    - `@settings(max_examples=100)`
    - **Validates: Requirements 3.5**

  - [x] 3.4 Write property test: Scoped overwrite invariant (Property 7)
    - **Property 7: Scoped overwrite invariant**
    - Use Hypothesis to generate random channel/listing pairs for existing and incoming data
    - Verify `insert_planned_bookings` deletes only imported pairs and leaves others unchanged
    - Use a mock or test database connection
    - `@settings(max_examples=100)`
    - **Validates: Requirements 4.1, 4.2**

  - [x] 3.5 Write unit tests for backend Airbnb multi-file import
    - Create example-based tests in `backend/tests/unit/test_str_airbnb_multi_import.py`
    - Test: All files fail → `ValueError` raised with filenames (Req 2.4)
    - Test: Cancelled rows with zero earnings are skipped (Req 3.6)
    - Test: Multiple listings in combined data all appear in output (Req 3.3)
    - Test: Specific Green Studio + Red Studio import leaves Child Friendly untouched (Req 4.3)
    - Test: Response structure has expected keys from multi-file processing (Req 5.2)
    - Test: Single airbnb file processed through same `_process_airbnb_multi` path (Req 5.1)
    - _Requirements: 2.4, 3.3, 3.6, 4.3, 5.1, 5.2_

- [x] 4. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement frontend multi-file selection and display
  - [x] 5.1 Enable multi-file input for airbnb platform in `frontend/src/components/STRProcessor.tsx`
    - Add `'airbnb'` to the `multiple` condition: `multiple={selectedPlatform === 'vrbo' || selectedPlatform === 'booking' || selectedPlatform === 'airbnb'}`
    - Update `handleFileUpload` to handle multiple files for `airbnb` platform: add `selectedPlatform === 'airbnb'` to the multi-file branch
    - Change `accept` attribute to `.csv` only when platform is `airbnb` (Airbnb exports are CSV-only, unlike Booking.com which also uses Excel/TSV)
    - _Requirements: 1.1, 1.3_

  - [x] 5.2 Display all selected filenames and add hint text
    - Selected filenames already display via the existing `selectedFiles` text element
    - Add informational hint `<Alert>` for `airbnb` platform explaining multi-file support (similar to existing `booking` and `vrbo` hints)
    - _Requirements: 1.2, 6.4_

  - [x] 5.3 Update success message and warning display for multi-file Airbnb imports
    - When multi-file airbnb import completes, display total number of files processed in success message (Req 6.1)
    - Display realised/planned/already-loaded counts in summary (Req 6.2) — already works via existing summary display
    - Display warning when backend reports failed files (Req 6.3) — parse error message for failed filenames, same pattern as booking
    - Ensure process button remains disabled when no files selected (Req 1.4) — already works via `!selectedFile` check
    - _Requirements: 1.4, 6.1, 6.2, 6.3_

  - [x] 5.4 Write property test: All selected filenames are displayed (Property 8)
    - **Property 8: All selected filenames are displayed**
    - Use fast-check to generate random filename lists
    - Render component with mock files and verify all filenames appear in rendered output
    - Create test in `frontend/src/components/STRProcessor.test.tsx`
    - `fc.assert(..., { numRuns: 100 })`
    - **Validates: Requirements 1.2**

  - [x] 5.5 Write unit tests for frontend Airbnb multi-file import
    - Test: Airbnb platform enables multi-select on file input (Req 1.1)
    - Test: File input accepts `.csv` only for airbnb (Req 1.3)
    - Test: Process button disabled when no files selected (Req 1.4)
    - Test: Multi-file success shows file count (Req 6.1)
    - Test: Summary shows realised/planned/already-loaded counts (Req 6.2)
    - Test: Failed files warning displayed (Req 6.3)
    - Test: Airbnb platform shows multi-file hint (Req 6.4)
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
    - Test: Route passes all file paths to processor for airbnb (Req 5.1)
    - Test: Temp files cleaned up after success and failure (Req 5.4)
    - Test: Single airbnb file upload works through multi path (Req 5.1)
    - Create tests in `backend/tests/integration/test_str_airbnb_multi_file_integration.py`
    - _Requirements: 5.1, 5.4_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Commit and push to main
  - [x] 9.1 Stage all changed files related to this feature
    - Stage backend changes: `backend/src/str_processor.py`
    - Stage frontend changes: `frontend/src/components/STRProcessor.tsx`
    - Stage new test files: `backend/tests/unit/test_str_airbnb_multi_import.py`, `backend/tests/integration/test_str_airbnb_multi_file_integration.py`, `frontend/src/components/STRProcessor.test.tsx`
    - Stage spec files: `.kiro/specs/str-airbnb-multi-file-import/`
    - Use `git add` with specific files — avoid `git add .`
  - [x] 9.2 Commit with descriptive message
    - Commit message: `feat(str): add Airbnb multi-file import with concat, dedup by Bevestigingscode, and 15% channel fee calculation`
  - [x] 9.3 Push to main
    - `git push origin main`

## Notes

- All tasks are required — no optional tasks
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- No changes needed to `str_routes.py` — it already handles `getlist('file')` and passes all paths
- No changes needed to `STRDatabase.insert_planned_bookings()` — it already deletes by `(channel, listing)` pair
- The old `_process_airbnb()` method is removed entirely — no backward compatibility needed
- Backend tests use pytest + Hypothesis; frontend tests use Vitest + fast-check
