# Implementation Plan

Two independent defect surfaces are fixed here. The backend date parser (surface b) is a
pure function and is fixed and unit-tested first, in isolation. The frontend wizard contract
(surface a) is fixed second. Exploration and preservation tests are written BEFORE each fix.

## Surface (b) — Backend date parser (`_normalize_date`)

- [x] 1. Write bug condition exploration test for `_normalize_date` (non-padded dates)
  - **Property 1: Bug Condition** - Non-Padded Numeric Dates Rejected
  - **CRITICAL**: This test MUST FAIL (as a fix test) on unfixed code — on unfixed code it asserts the *wrong* `None` result to document the defect; after the fix it encodes the expected normalized output
  - **DO NOT attempt to fix the test or the code when it fails**
  - **GOAL**: Surface counterexamples that demonstrate the parser rejects valid non-zero-padded Dutch/ISO dates
  - **Scoped PBT Approach**: The accepted/rejected date sets are small and fully enumerated in the design's Fix Checking table, so scope the property to those concrete table rows (one assertion per row) for reproducibility rather than randomized generation
  - Add a `TestNormalizeDate` class to `backend/tests/unit/test_zzp_trip_import_validate.py`, calling `TripImportService._normalize_date` directly (static method, no DB needed), following the existing file's conventions (`sys.path` insert of `src`, `test_{function}_{scenario}_{expected}` naming)
  - Bug Condition inputs (from design, surface b): valid non-zero-padded numeric Dutch/ISO dates — `"5-5-2026"`, `"3-6-2026"`, `"17-5-2026"`, `"5-12-2026"`, `"5/5/2026"`, `"3/6/2026"`, `"17/5/2026"`, `"2026-5-5"`
  - Expected Behavior (post-fix assertions, from design Fix Checking table): `"5-5-2026"` → `"2026-05-05"`, `"3-6-2026"` → `"2026-06-03"`, `"17-5-2026"` → `"2026-05-17"`, `"5-12-2026"` → `"2026-12-05"`, `"5/5/2026"` → `"2026-05-05"`, `"3/6/2026"` → `"2026-06-03"`, `"17/5/2026"` → `"2026-05-17"`, `"2026-5-5"` → `"2026-05-05"`; each result matches `/^\d{4}-\d{2}-\d{2}$/`
  - Run on UNFIXED code: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_validate.py::TestNormalizeDate -v`
  - **EXPECTED OUTCOME**: Tests FAIL (unfixed `_normalize_date` returns `None` for every non-padded input — this proves the bug exists)
  - Document counterexamples found (e.g. "`_normalize_date('5-5-2026')` returns `None` instead of `'2026-05-05'` — 8 chars fails the fixed length/position guard")
  - Mark task complete when tests are written, run, and the failure is documented
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 2. Write preservation property tests for `_normalize_date` (BEFORE implementing fix)
  - **Property 2: Preservation** - Already-Valid Dates Unchanged, Invalid Dates Still Rejected
  - **IMPORTANT**: Follow observation-first methodology — run the UNFIXED `_normalize_date` on each non-bug-condition input, record its output, and assert that observed output
  - Add these cases to the `TestNormalizeDate` class in `backend/tests/unit/test_zzp_trip_import_validate.py`
  - Preserved already-valid inputs (observe → identical result): `"05-05-2026"` → `"2026-05-05"`, `"15-01-2026"` → `"2026-01-15"`, `"2026-05-05"` → `"2026-05-05"`, `"05/05/2026"` → `"2026-05-05"`
  - Rejected invalid inputs (observe → still `None`): `"5-5"` (missing year / 2 parts), `"2026"` (missing parts), `"5-mei"` (non-numeric), `"5-mei-2026"` (non-numeric component), `"32-5-2026"` (day out of range), `"5-13-2026"` (month out of range), `"0-5-2026"` (day out of range), `"5-5-1899"` (year < 1900), `""` (empty), `None` (non-string)
  - Run on UNFIXED code: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_validate.py::TestNormalizeDate -v`
  - **EXPECTED OUTCOME**: These preservation cases PASS on unfixed code (confirms the baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 3. Fix `_normalize_date` to accept non-zero-padded numeric dates via range validation

  - [x] 3.1 Redesign `_normalize_date` in `backend/src/services/zzp_trip_import_service.py`
    - Replace the three fixed `len(date_str) == 10` / fixed-separator-position branches with separator detection and numeric-range validation (per design Change 4)
    - Guard: falsy or non-string → `None`; `strip()` the input
    - Choose separator: `-` if present, else `/`, else `None` (reject if neither)
    - `split(sep)`; require exactly 3 parts; reject if any part is empty or not all-digits (`str.isdigit`) — this rejects `"5-5"` (2 parts), `"5-mei"` (non-numeric)
    - Infer ordering: first component 4 digits → ISO `YYYY-M-D`; otherwise Dutch `D-M-YYYY`
    - Validate ranges: `1 <= month <= 12`, `1 <= day <= 31`, `year >= 1900`; else `None`
    - Return zero-padded `"%04d-%02d-%02d" % (year, month, day)`; NO year inference
    - Leave the `_validate_date_format` error message unchanged (still lists `YYYY-MM-DD, DD-MM-YYYY, of DD/MM/YYYY`) — only the accepted-input surface widens
    - _Bug_Condition: isBugCondition(d) = isValidNumericDutchOrIsoDate(d) AND NOT isTenCharFixedPosition(d)_
    - _Expected_Behavior: _normalize_date(d) = zeroPaddedIso(d) matching /^\d{4}-\d{2}-\d{2}$/, no year inference_
    - _Preservation: already-padded/ISO inputs produce the identical result; missing-year / non-numeric / out-of-range still return None; downstream required-field, odometer-continuity, duplicate, category/purpose validation unchanged_
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 3.2 Verify the bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Non-Padded Numeric Dates Normalize Correctly
    - **IMPORTANT**: Re-run the SAME tests from task 1 — do NOT write new tests
    - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_validate.py::TestNormalizeDate -v`
    - **EXPECTED OUTCOME**: The non-padded cases now PASS (confirms the bug is fixed)
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Already-Valid Dates Unchanged, Invalid Dates Still Rejected
    - **IMPORTANT**: Re-run the SAME preservation cases from task 2 — do NOT write new tests
    - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_validate.py::TestNormalizeDate -v`
    - **EXPECTED OUTCOME**: All preserved-valid and rejected-invalid cases still PASS (no regressions)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 4. Add `validate_import` end-to-end test with non-padded dates (Requirement 5.4)
  - Add a test (e.g. `test_validate_import_non_padded_dates_all_valid`) to `backend/tests/unit/test_zzp_trip_import_validate.py` using the existing `mock_db` fixture and `make_valid_row` helper
  - Build a continuity-respecting set of rows whose only non-standard trait is non-padded dates, e.g. `make_valid_row(trip_date="5-5-2026", start_odometer=45000, end_odometer=45050)`, `make_valid_row(trip_date="6-5-2026", start_odometer=45050, end_odometer=45100)`, `make_valid_row(trip_date="17-5-2026", start_odometer=45100, end_odometer=45150)`
  - Assert `result["valid"] == len(rows)`, `result["errors"] == 0`, a populated `result["preview"]`, every `_status == "ok"`, and each normalized `trip_date` matches `/^\d{4}-\d{2}-\d{2}$/`
  - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_validate.py -v`
  - **EXPECTED OUTCOME**: PASSES only after task 3 (would be all-error on unfixed code)
  - _Requirements: 5.4, 6.5_

## Surface (a) — Frontend wizard contract

- [x] 5. Write bug condition exploration test for the wizard mapping (flat response)
  - **Property 1: Bug Condition** - Successful Import Response Not Mapped/Rendered/Committed
  - **CRITICAL**: On UNFIXED frontend code the mapping reads `resp.data` from a flat response and yields `undefined` — document that empty-preview cause
  - **DO NOT attempt to fix the test or the code when it fails**
  - **GOAL**: Surface the counterexample that a flat `{ success:true, total_rows:3, valid:3, warnings:0, errors:0, rows:[...], preview:[...] }` response read as `resp.data` is `undefined`, producing a null `validationResult` and an empty Preview
  - Capture, against the fixed service types, the post-fix expectations: mapping yields a populated state with `total_rows`/`valid`/`warnings`/`errors`/`preview`/`rows`; `getStatusBadge` returns the correct colorScheme/label for `_status` `ok`/`warning`/`error` and joins `_messages`; `commitImport` posts `{ vehicle_id, rows, skip_error_rows }`
  - Place the test alongside the existing frontend tests for `tripService` / `ZZPTripImport` (follow `33-frontend-testing.md` conventions and the project's existing test setup); if no suitable harness exists, perform the verification as part of the build/typecheck in task 7
  - **EXPECTED OUTCOME**: Documents that unfixed mapping stores `undefined` (empty preview); the mapping/badge/commit assertions FAIL until task 6
  - Mark task complete when the counterexample is written, run, and documented
  - _Requirements: 2.1, 2.2, 2.4, 2.5_

- [x] 6. Fix the wizard contract (flat mapping, underscore fields, commit payload)

  - [x] 6.1 Flatten `ApiImportResponse` and map flat fields into `validationResult`
    - In `frontend/src/services/tripService.ts`: retype `ApiImportResponse` with the flat top-level fields `{ success, total_rows, valid, warnings, errors, rows: ImportRow[], preview: ImportRow[], message?, error? }` (per design Change 1)
    - In `frontend/src/pages/ZZPTripImport.tsx` `handleNext` (Upload → Preview branch): build `validationResult` from the flat fields (`resp.total_rows`, `resp.valid`, `resp.warnings`, `resp.errors`, `resp.preview`, `resp.rows`) instead of `resp.data`
    - Extend the local `ImportValidationResult` interface in `ZZPTripImport.tsx` with `rows: ImportRow[]` so the commit step has the full validated set
    - _Bug_Condition: isBugCondition(X) = (X.success = true)_
    - _Expected_Behavior: mapResponseToPreviewState(X) IS NOT null AND state.total_rows = X.total_rows AND state.preview = X.preview AND previewRendersRows(state)_
    - _Preservation: success:false still shows the upload-failed toast and keeps the user on Upload; navigation gating unchanged_
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 6.2 Retype `ImportRow` to the backend underscore fields and read them in the UI
    - In `frontend/src/types/zzpTrips.ts`: retype `ImportRow` to use `_row_number` / `_status` (`'ok' | 'warning' | 'error'`) / `_messages: string[]` plus the row data fields (per design Change 2)
    - In `frontend/src/pages/ZZPTripImport.tsx`: update `getStatusBadge` to read `row._status` and `row._messages` (colorMap `ok→green/warning→yellow/error→red`, labelMap `OK/Waarschuwing/Fout`, tooltip joins `_messages`), and replace `row.row_number` with `row._row_number` in the preview table body
    - _Bug_Condition: isBugCondition(X) = (X.success = true), per-row fields are underscore-prefixed_
    - _Expected_Behavior: getStatusBadge renders the correct OK/warning/error badge and its _messages_
    - _Preservation: Import button stays disabled when valid === 0_
    - _Requirements: 2.4_

  - [x] 6.3 Send validated rows on commit
    - In `frontend/src/services/tripService.ts`: change `commitImport(vehicleId, rows: ImportRow[], skipErrorRows = true)` to POST `{ vehicle_id, rows, skip_error_rows: skipErrorRows }` (per design Change 3)
    - In `frontend/src/pages/ZZPTripImport.tsx` `handleCommit`: call `commitImport(selectedVehicle, validationResult?.rows ?? [], true)`
    - `ColumnMapping` may remain exported for other needs; it is no longer used by the commit call
    - _Bug_Condition: commit must send the validated rows the backend requires_
    - _Expected_Behavior: commitPayload(state) CONTAINS state.rows (plus vehicle_id and skip_error_rows)_
    - _Preservation: template download, step gating, and upload-error handling unchanged_
    - _Requirements: 2.5_

  - [x] 6.4 Verify the wizard exploration/mapping test now passes
    - **Property 1: Expected Behavior** - Successful Response Maps/Renders/Commits
    - **IMPORTANT**: Re-run the SAME verification from task 5 — do NOT write new tests
    - Confirm: a flat success response yields a populated `validationResult`; `getStatusBadge` renders correct badges from `_status`/`_messages`; `commitImport` posts `{ vehicle_id, rows, skip_error_rows }`
    - **EXPECTED OUTCOME**: Mapping/badge/commit-payload assertions PASS
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 6.5 Verify wizard preservation behavior is unchanged
    - **Property 2: Preservation** - Non-Successful Responses and Wizard Gating Unchanged
    - Confirm: `success:false` still shows the upload-failed toast and keeps the user on Upload; the Import button is disabled when `valid === 0`; Back disabled on Upload and only Back on the final Import step; template download unchanged
    - **EXPECTED OUTCOME**: Preservation behaviors unchanged (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.5_

- [x] 7. Verify surface (a) + surface (b) regress clean before starting surface (c)
  - Run the surface-(b) backend tests: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_validate.py -v` and confirm all pass (parser table cases, preservation cases, and the `validate_import` end-to-end non-padded test)
  - Run the frontend build/typecheck for `frontend/` (the project's build/typecheck command) and confirm surface (a) — `ApiImportResponse`, `ImportRow`, `getStatusBadge`, `handleNext`, `handleCommit`, and `commitImport` — all typecheck against the new shapes
  - This is an interim gate confirming surfaces (a) and (b) are green; the single full-suite-across-all-surfaces checkpoint + cleanup is task 12
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4, 6.5_

## Surface (c) — Excel handling (`_read_dataframe` / `parse_file` / `validate_import`)

This third surface lives entirely in `backend/src/services/zzp_trip_import_service.py`
(design Changes 5, 6, 7 and Properties 5, 6). It is backend-first and tests-before-fix,
mirroring the surface-(b) pattern: exploration test → preservation test → fix → verify.
All backend tests go under `backend/tests/unit/` following the existing
`test_zzp_trip_import_*.py` conventions (`sys.path` insert of `src`, the `mock_db` fixture
returning no existing trips, `TripImportService(db=mock_db)`, and
`test_{function}_{scenario}_{expected}` naming). In-memory `.xlsx` fixtures are built with
`pandas.ExcelWriter(buf, engine="openpyxl")` writing to an `io.BytesIO()`, then rewound
(`buf.seek(0)`) and passed to `parse_file` with a `.xlsx` filename; CSV fixtures use
`io.BytesIO` with semicolon-separated text.

- [x] 8. Write bug condition exploration test for Excel handling (wrong sheet, datetime date, error marker)
  - **Property 5: Bug Condition** - Wrong Sheet Read, Datetime Date Rejected, Error Marker Unflagged
  - **CRITICAL**: These assertions MUST capture the WRONG behavior on UNFIXED code — they document the three surface-(c) defects; after the fix the same scenarios become the fix assertions (task 11)
  - **DO NOT attempt to fix the test or the code when it fails**
  - **GOAL**: Surface counterexamples that demonstrate the first-sheet-only read, the datetime-valued date rejection, and the silent error-marker pass-through
  - Add a `TestExcelHandlingBugCondition` class to `backend/tests/unit/test_zzp_trip_import_service.py` (the parse/read surface), using the `mock_db` fixture and `TripImportService(db=mock_db)`
  - **Wrong-sheet** (from design Change 5 / Property 5(1)): build an in-memory `.xlsx` with a decoy FIRST sheet (e.g. `Blad1`) whose headers are only `[Vertrekadres, Categorie, Doel, Klant, Notities]`, plus a SECOND sheet (e.g. `ritten_import_template`) with ALL mapped headers `[Datum, Vertrekadres, Bestemming, Begin KM, Eind KM, Categorie, Doel, Klant, Notities]` and ≥2 continuity-respecting data rows; write both sheets via `pandas.ExcelWriter(buf, engine="openpyxl")` (one `df.to_excel(writer, sheet_name=...)` per sheet). Call `parse_file`, then `validate_import`, and assert the UNFIXED code reads the first sheet so required-field errors occur (e.g. `result["valid"] == 0`, every row `_status == "error"` with a "Verplicht veld ontbreekt"-style message for Datum/Bestemming/Begin KM/Eind KM)
  - **Datetime date** (from design Change 6 / Property 5(3)): assert `TripImportService._normalize_date("2026-05-05 00:00:00")` returns `None` on unfixed code (13+ chars fails the fixed-position guard); note that a `datetime.date(2026, 5, 5)` object would likewise not normalize
  - **Error marker** (from design Change 7 / Property 5(4)): assert a mapped `trip_date` cell equal to `"#N/A"` is NOT specially flagged on unfixed code — it produces only a generic "Ongeldig datumformaat"/required-field error with no message naming the column + marker (no "Formulewaarde niet berekend" text)
  - Run on UNFIXED code: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_service.py::TestExcelHandlingBugCondition -v`
  - **EXPECTED OUTCOME**: These assertions describe the current wrong behavior (first sheet read → `valid == 0`; `_normalize_date("2026-05-05 00:00:00")` is `None`; `#N/A` only generically flagged) — this proves the three defects exist
  - Document counterexamples found (e.g. "`parse_file` reads `Blad1` and ignores `ritten_import_template`, so every row is a required-field error"; "`_normalize_date('2026-05-05 00:00:00')` returns `None`"; "`#N/A` surfaces as 'Ongeldig datumformaat', hiding the unresolved-formula cause")
  - Mark task complete when the assertions are written, run, and the counterexamples documented
  - _Requirements: 8.1, 8.2, 8.4, 8.5_

- [x] 9. Write preservation property tests for Excel handling (BEFORE implementing fix)
  - **Property 6: Preservation** - Single-Sheet/First-Match/CSV Identical, Extra Columns Ignored, Cached Values and Empty/None Unchanged
  - **IMPORTANT**: Follow observation-first methodology — run the UNFIXED reader on each non-bug-condition input, record its output, and assert that observed output so it stays stable after the fix
  - Add a `TestExcelHandlingPreservation` class to `backend/tests/unit/test_zzp_trip_import_service.py`, using the `mock_db` fixture and `TripImportService(db=mock_db)`
  - **Single-sheet first-match** (Requirement 9.1): build a one-sheet `.xlsx` whose FIRST (only) sheet already has all mapped headers + continuity-respecting rows; observe `parse_file` → `validate_import` reads it correctly (record `result["valid"]`, `total_rows`, and the mapped row values) and assert those outputs
  - **CSV unaffected** (Requirement 9.2): build a semicolon-separated CSV (`io.BytesIO`) with the mapped headers + rows; observe it parses via the existing semicolon-first/comma-fallback path and assert the recorded result (worksheet selection must not affect CSV)
  - **Extra/unmapped columns ignored** (Requirement 9.3): add a sheet with the mapped headers plus trailing extra/`Unnamed`-style columns; observe the extra columns are ignored and the mapped fields still read; assert that
  - **Valid cached formula value** (Requirements 9.5, 9.6): a mapped cell carrying an ordinary (already-computed) value — e.g. a plain string/number that pandas reads directly — is read as that value and the row validates `ok`; assert the recorded value (no formula evaluation is performed)
  - **Empty/None cell** (Requirement 9.6): a mapped required cell that is empty/`None` triggers the normal required-field error (`_status == "error"`, "Verplicht veld ontbreekt"-style message), NOT an error-marker message; assert the recorded behavior
  - Run on UNFIXED code: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_service.py::TestExcelHandlingPreservation -v`
  - **EXPECTED OUTCOME**: All preservation cases PASS on unfixed code (confirms the baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 10. Fix Excel handling in `backend/src/services/zzp_trip_import_service.py`

  - [x] 10.1 Change 5 — header-matching worksheet selection
    - In `parse_file`, compute `required_headers` from the resolved `mapping` (`column_mapping or DEFAULT_COLUMN_MAPPING`): the set of mapping keys (file-column headers) whose internal field names are in `REQUIRED_IMPORT_FIELDS` — i.e. Datum, Vertrekadres, Bestemming, Begin KM, Eind KM, Categorie, Doel; EXCLUDE Klant/Notities (optional)
    - Thread it into the reader by widening the signature to `_read_dataframe(file_stream, ext, required_headers=None)`; the single `parse_file` call site passes `required_headers`, and the CSV path ignores it
    - CSV branch (`ext == ".csv"`): UNCHANGED semicolon-first / comma-fallback logic
    - Excel branch (`ext in (".xlsx", ".xls")`): read ALL sheets with `pd.read_excel(file_stream, sheet_name=None, dtype=str)` (ordered name→df dict); if `required_headers` is falsy, defensively return the first sheet (old behavior); otherwise iterate sheets in insertion order and return the FIRST sheet whose stripped column set (`{str(c).strip() for c in sheet_df.columns}`) is a superset of `required_headers`; if none match, raise a module-private `SheetSelectionError(found=..., expected=required_headers)`
    - In `parse_file`, catch `SheetSelectionError` BEFORE the generic `except Exception` ("Could not read file") branch and translate it into the standard `{ success: false, rows: [], total_rows: 0, ... }` envelope with an `error` string naming BOTH the columns found and the columns expected (`sorted(required_headers)`); do NOT silently fall back to the first sheet
    - The existing header-strip and column-mapping / `unmapped_columns` logic in `parse_file` runs unchanged on the selected sheet
    - _Bug_Condition: isBugCondition(wb) = NOT firstSheetContainsRequiredHeaders(wb)_
    - _Expected_Behavior: parse_file selects the first sheet whose stripped headers ⊇ required_headers, else success:false naming found vs expected_
    - _Preservation: single-sheet / first-sheet-matching workbooks select the same (first) sheet as before; CSV path unchanged; extra/Unnamed columns still ignored_
    - _Requirements: 8.1, 8.2, 8.3, 9.1, 9.2, 9.3_

  - [x] 10.2 Change 6 — datetime-aware `_normalize_date`
    - At the top of `TripImportService._normalize_date`, before the Change-4 separator/range logic: return `None` for a falsy value; if the value is a `datetime`/`date` object, return `value.strftime("%Y-%m-%d")`; if not a `str`, return `None`; otherwise `strip()` and split off a leading date token on whitespace or `'T'` (`"2026-05-05 00:00:00"` → `"2026-05-05"`, `"2026-05-05T00:00:00"` → `"2026-05-05"`) and fall through to the existing separator detection / 3-part split / numeric-range validation
    - Keep only the date portion — NO timezone, NO time component, NO year inference; a pure date string with no time is unaffected (surface-(b) behavior identical)
    - Ensure `_validate_date_format` passes the raw `date_value` through so an actual `datetime`/`date` object reaches the object branch; its "Ongeldig datumformaat" message is unchanged
    - _Bug_Condition: isBugCondition(d) = d is a datetime/date object OR an ISO string carrying a time component_
    - _Expected_Behavior: _normalize_date(d) = the zero-padded YYYY-MM-DD date portion only, matching /^\d{4}-\d{2}-\d{2}$/_
    - _Preservation: pure date strings (no time) normalize identically to surface (b); no time/timezone/year inference introduced_
    - _Requirements: 8.4, 9.4_

  - [x] 10.3 Change 7 — Excel error-marker detection
    - Add a module constant `EXCEL_ERROR_MARKERS = {"#N/A", "#REF!", "#VALUE!", "#NAME?", "#DIV/0!", "#NULL!", "#NUM!"}` and a helper `isExcelErrorMarker(value)` that returns `False` for non-strings and otherwise, on the stripped value, returns `True` when it is in `EXCEL_ERROR_MARKERS` OR matches the general leading-`#` error form (starts with `#` and ends with `!` or `?`)
    - Add a per-cell check (e.g. `_validate_error_markers(row)`) that iterates the mapped internal field names present in the row (skip `_`-prefixed helper keys); when a mapped cell equals a marker, append a specific message naming the column + marker (e.g. `"Formulewaarde niet berekend: '#N/A' in kolom trip_date"`) and set `row["_status"] = "error"`
    - Wire it into the `validate_import` Phase-1 per-row loop (alongside/`_clean_row`-adjacent to the existing `_validate_required_fields` / `_validate_date_format` calls) so the row is flagged `error` regardless of what the other checks conclude; NEVER evaluate formulas — only inspect the cached marker string pandas returns
    - A plain empty/`None` cell is NOT a marker (`isExcelErrorMarker` requires a `#…` string), so it still falls through to the existing required-field check
    - _Bug_Condition: isBugCondition(cell) = isExcelErrorMarker(cell) on a mapped cell_
    - _Expected_Behavior: the row is flagged _status="error" with a message naming the column + marker; no formula evaluated_
    - _Preservation: valid cached formula values read as that value (ok); plain empty/None still handled by the required-field check_
    - _Requirements: 8.5, 9.5, 9.6_

  - [x] 10.4 Verify the Excel bug condition exploration test now passes
    - **Property 5: Expected Behavior** - Correct Sheet Selected, Datetime Dates Normalize, Error Markers Flagged
    - **IMPORTANT**: Re-run the SAME `TestExcelHandlingBugCondition` tests from task 8 — do NOT write new tests
    - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_service.py::TestExcelHandlingBugCondition -v`
    - **EXPECTED OUTCOME**: Now the two-sheet workbook selects the SECOND (matching) sheet so its rows validate (`valid > 0`); `_normalize_date("2026-05-05 00:00:00")` returns `"2026-05-05"`; the `#N/A` cell flags the row `_status == "error"` with a message naming the column + marker — but these are asserted against the FIXED expectations in task 11, so update the task-8 assertions there, not here. For task 10.4, confirm the fix compiles and the direct `_normalize_date` datetime assertion now returns the date portion
    - _Requirements: 8.1, 8.2, 8.4, 8.5_

  - [x] 10.5 Verify Excel preservation tests still pass
    - **Property 6: Preservation** - Single-Sheet/First-Match/CSV Identical, Extra Columns Ignored, Cached Values and Empty/None Unchanged
    - **IMPORTANT**: Re-run the SAME `TestExcelHandlingPreservation` tests from task 9 — do NOT write new tests
    - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_service.py::TestExcelHandlingPreservation -v`
    - **EXPECTED OUTCOME**: All preservation cases still PASS (single-sheet/first-match select the same sheet; CSV unaffected; extra/Unnamed columns ignored; valid cached values read; empty/None still required-field error) — no regressions
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 11. Add `validate_import` end-to-end tests for the fixed Excel behavior
  - Add to `backend/tests/unit/test_zzp_trip_import_service.py` (using `mock_db` and `TripImportService(db=mock_db)`), as the post-fix assertions encoding Property 5
  - **Two-sheet selection** (`test_parse_file_decoy_first_sheet_selects_matching_second_sheet`): reuse the two-sheet `.xlsx` fixture from task 8 (decoy `Blad1` first + full `ritten_import_template` second with continuity-respecting rows); after the fix, assert `result["success"] is True`, the mapped `columns_found`/rows come from the second sheet, `total_rows` matches that sheet's data, and `validate_import` reports `valid > 0`
  - **No-match failure** (`test_parse_file_no_sheet_matches_returns_success_false`): build an `.xlsx` where NO sheet contains the required headers; assert `result["success"] is False` and the `error` string contains BOTH the found columns and the expected columns (`required_headers`); the wizard would stay on Upload
  - **Datetime-valued dates in-sheet** (optional reinforcement of 8.4): a sheet whose Datum column holds Excel datetime values surfacing as `"YYYY-MM-DD HH:MM:SS"` under `dtype=str`; after the fix those rows normalize to the `YYYY-MM-DD` date portion and validate `ok`
  - **Error marker in-sheet** (`test_validate_import_na_marker_flags_row_error`): a sheet row whose mapped `trip_date` cell is `"#N/A"`; assert that row `_status == "error"` and a `_messages` entry contains both the column name and `#N/A`
  - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_service.py -v`
  - **EXPECTED OUTCOME**: PASSES only after task 10 (all-error / `None` / unflagged on unfixed code)
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

## Final checkpoint (all three surfaces)

- [x] 12. Checkpoint — Run the full backend suite + frontend build/typecheck and clean up
  - Run the full backend trip-import test suite covering all three surfaces: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_validate.py tests/unit/test_zzp_trip_import_service.py -v` and confirm all pass — surface (b) parser table cases + the non-padded `validate_import` end-to-end test; surface (c) `TestExcelHandlingBugCondition` / `TestExcelHandlingPreservation`, the two-sheet selection, no-match failure, datetime-in-sheet, and error-marker tests
  - Run the frontend build/typecheck for `frontend/` (the project's build/typecheck command) and confirm surface (a) — `ApiImportResponse`, `ImportRow`, `getStatusBadge`, `handleNext`, `handleCommit`, and `commitImport` — all typecheck against the new shapes
  - Ensure all tests pass across all three surfaces; ask the user if questions arise
  - Clean up any temporary files or scratch output created during verification, including any in-memory/temporary `.xlsx` written to disk and anything under `.agent-output/` (in-memory `io.BytesIO` fixtures need no cleanup; delete any file-backed scratch)
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4, 6.5, 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_
