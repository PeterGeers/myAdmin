# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Date Fields Serialized as HTTP Date Strings
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate `datetime.date` objects are serialized as HTTP date strings instead of ISO-8601
  - **Scoped PBT Approach**: Use Hypothesis to generate `datetime.date` objects, pass them through Flask's `jsonify` serialization path, and assert the output matches ISO-8601 format `^\d{4}-\d{2}-\d{2}$`
  - Create test file: `backend/tests/unit/test_bug_condition_date_sorting.py`
  - Test that simulates the serialization path: create a dict with `datetime.date` values for `TransactionDate`, `checkinDate`, `checkoutDate` fields, serialize via Flask's JSON encoder, and assert output matches ISO-8601 regex
  - Use `@given(st.dates())` to generate date values and verify they would be correctly serialized
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves Flask serializes dates as HTTP date strings like `"Mon, 15 Jan 2024 00:00:00 GMT"` instead of `"2024-01-15"`)
  - Document counterexamples found (e.g., `datetime.date(2024, 1, 15)` → `"Mon, 15 Jan 2024 00:00:00 GMT"`)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Date Fields Unchanged by normalize_dates
  - **IMPORTANT**: Follow observation-first methodology
  - **IMPORTANT**: Write these tests BEFORE implementing the fix
  - Create test file: `backend/tests/unit/test_preservation_date_sorting.py`
  - Observe: non-date fields (strings, ints, floats, None, booleans) pass through unchanged
  - Observe: fields not listed in `date_fields` parameter are never modified
  - Observe: `None` values in date fields remain `None`
  - Observe: already-ISO string values in date fields pass through unchanged
  - Write property-based tests with Hypothesis:
    - `@given` with composite strategy generating random row dicts with mixed field types
    - Assert that `normalize_dates(rows, ['TransactionDate'])` preserves all non-`TransactionDate` fields exactly
    - Assert that `normalize_dates(rows, date_fields)` with `None` date values preserves `None`
    - Assert that `normalize_dates([], date_fields)` returns empty list
    - Assert that rows with missing date field keys are not modified or errored
  - **NOTE**: Since `normalize_dates` doesn't exist yet, write the tests importing from `backend.src.utils.date_utils` — create a minimal stub that passes through data unchanged (identity function) to verify preservation tests pass on unfixed code
  - Run tests on UNFIXED code (with stub)
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline preservation behavior)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Implement the date sorting fix
  - [x] 3.1 Create `normalize_dates` utility function
    - Create file: `backend/src/utils/date_utils.py`
    - Implement `normalize_dates(rows: list[dict], date_fields: list[str]) -> list[dict]`
    - Iterate over rows, for each specified date field: if value is `datetime.date` or `datetime.datetime`, call `.isoformat()` (for `datetime.datetime`, use `.date().isoformat()` to get date-only)
    - Skip `None` values gracefully
    - Skip fields not present in the row dict
    - Pass through values that are already strings unchanged
    - Mutate in place and return the list (matching `banking_service.py` pattern)
    - Add type hints and docstring
    - _Bug_Condition: isBugCondition(input) where date fields are datetime.date objects not pre-converted to ISO strings_
    - _Expected_Behavior: all date fields in specified list become ISO-8601 strings matching `^\d{4}-\d{2}-\d{2}$`_
    - _Preservation: non-date fields, None values, already-string values, and missing fields are unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.3, 3.4, 3.5, 3.6_

  - [x] 3.2 Apply fix to `/api/reports/mutaties-table` endpoint
    - File: `backend/src/routes/reporting_routes.py`
    - Import `normalize_dates` from `backend.src.utils.date_utils`
    - After `results = cursor.fetchall()`, add: `normalize_dates(results, ['TransactionDate'])`
    - _Requirements: 2.1_

  - [x] 3.3 Apply fix to `/api/reports/check-reference` endpoint
    - File: `backend/src/routes/reporting_routes.py`
    - After fetching transactions, add: `normalize_dates(transactions, ['TransactionDate'])`
    - _Requirements: 2.2_

  - [x] 3.4 Apply fix to `/api/bnb/bnb-table` endpoint
    - File: `backend/src/routes/bnb_routes.py`
    - Import `normalize_dates` from `backend.src.utils.date_utils`
    - After `results = cursor.fetchall()`, add: `normalize_dates(results, ['checkinDate', 'checkoutDate'])`
    - _Requirements: 2.3_

  - [x] 3.5 Apply fix to `/api/str-invoice/search-booking` endpoint
    - File: `backend/src/routes/str_invoice_routes.py`
    - Import `normalize_dates` from `backend.src.utils.date_utils`
    - After `results = cursor.fetchall()`, add: `normalize_dates(results, ['checkinDate', 'checkoutDate'])`
    - _Requirements: 2.4_

  - [x] 3.6 Apply fix to `/api/bnb/bnb-guest-bookings` endpoint
    - File: `backend/src/routes/bnb_routes.py`
    - After fetching guest bookings, add: `normalize_dates(results, ['checkinDate', 'checkoutDate'])`
    - _Requirements: 2.3_

  - [x] 3.7 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Date Fields Serialized as ISO-8601
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (ISO-8601 format)
    - Now that `normalize_dates` is implemented, simulate the fixed serialization path
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — dates are now ISO-8601)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.8 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Date Fields Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2 (now using real `normalize_dates` instead of stub)
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — non-date fields untouched)
    - Confirm all preservation tests still pass after fix
    - _Requirements: 3.1, 3.3, 3.4, 3.5, 3.6_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `pytest backend/tests/unit/test_bug_condition_date_sorting.py backend/tests/unit/test_preservation_date_sorting.py -v`
  - Verify bug condition test PASSES (fix works)
  - Verify preservation tests PASS (no regressions)
  - Run any existing tests that touch the affected routes to confirm no breakage
  - Ensure all tests pass, ask the user if questions arise
