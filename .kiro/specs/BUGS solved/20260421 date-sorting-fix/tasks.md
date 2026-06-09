# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** — Date Strings Use localeCompare Instead of Chronological Comparison
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate `compareValues` uses `localeCompare` for ISO-8601 date strings instead of timestamp comparison
  - **Scoped PBT Approach**: Generate pairs of valid ISO-8601 date strings (`YYYY-MM-DD`, year 1970–2099, month 01–12, day 01–28) using fast-check 4.4.0 and assert `sign(compareValues(a, b)) === sign(Date.parse(a) - Date.parse(b))`
  - **Test file**: `frontend/src/hooks/__tests__/useTableSort.dateFix.property.test.ts`
  - **Generator**: Create `isoDateArbitrary` that produces valid `YYYY-MM-DD` strings (pad month/day to 2 digits, restrict day to 01–28 for universal validity)
  - **Property**: For all `(a, b)` where both are ISO date strings, `sign(compareValues(a, b))` equals `sign(Date.parse(a) - Date.parse(b))`
  - Import `compareValues` directly — it is a module-level function in `useTableSort.ts` (will need to export it or test via the hook)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS — `compareValues` falls through to `localeCompare` for date strings, producing lexicographic order that diverges from chronological order for cross-month/year pairs
  - Document counterexamples found (e.g., `compareValues("2024-02-01", "2024-11-01")` returns positive via `localeCompare` instead of negative via timestamp diff)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 2.1, 2.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** — Non-Date Values Sort Identically to Original
  - **IMPORTANT**: Follow observation-first methodology
  - **Test file**: `frontend/src/hooks/__tests__/useTableSort.dateFix.property.test.ts` (same file as task 1)
  - **Generator**: Use existing `cellValueArbitrary` pattern from `useTableSort.property.test.ts` — generate numbers, plain strings, null, undefined (exclude ISO date strings by filtering with `fc.pre`)
  - **Observation step**: Run unfixed `compareValues` with non-date inputs and record behavior:
    - Observe: `compareValues(42, 17)` returns `25` (numeric diff)
    - Observe: `compareValues("banana", "apple")` returns positive (localeCompare)
    - Observe: `compareValues(null, "hello")` returns `1` (nullish to end)
    - Observe: `compareValues(null, null)` returns `0` (both nullish equal)
  - **Property**: For all `(a, b)` where `NOT isBugCondition({a, b})`, capture the return value of `compareValues(a, b)` on unfixed code — this becomes the baseline
  - **Implementation**: Since we test BEFORE the fix, the property simply asserts current behavior patterns:
    - Number pairs: `compareValues(a, b) === a - b`
    - Plain string pairs (non-date): `compareValues(a, b) === String(a).localeCompare(String(b), undefined, { sensitivity: 'base' })`
    - Nullish handling: nullish values return 1/-1/0 per existing logic
  - **Filter**: Use `fc.pre(!isISODateString(a) && !isISODateString(b))` to exclude date string inputs from the property domain
  - Verify tests PASS on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS — confirms baseline behavior for non-date inputs
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix for date string sorting in compareValues
  - [x] 3.1 Implement the fix
    - **File**: `frontend/src/hooks/useTableSort.ts`
    - Add `isISODateString(value: unknown): boolean` helper function above `compareValues`:
      - Return `false` if `typeof value !== 'string'`
      - Apply regex `/^\d{4}-\d{2}-\d{2}(T[\d:.Z+-]*)?$/` to validate ISO-8601 format
      - Call `Date.parse(value)` and return `Number.isFinite(parsed)`
      - Regex pre-check avoids expensive `Date.parse` on non-date strings
    - Add date comparison branch in `compareValues` between the number check and string fallback:
      ```
      // Both ISO date strings → chronological comparison
      if (isISODateString(a) && isISODateString(b)) {
        return Date.parse(a as string) - Date.parse(b as string);
      }
      ```
    - Only compare as dates when BOTH values are ISO date strings — mixed date/non-date falls through to `localeCompare`
    - Export `compareValues` and `isISODateString` for direct testing (or use a test-accessible pattern)
    - _Bug_Condition: isBugCondition(input) where both values are non-nullish, non-numeric, and at least one is an ISO-8601 date string_
    - _Expected_Behavior: sign(compareValues(a, b)) = sign(Date.parse(a) - Date.parse(b)) for ISO date pairs_
    - _Preservation: Non-date inputs (numbers, plain strings, nullish) produce identical results to original function_
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** — Date Strings Sort Chronologically
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior: `sign(compareValues(a, b)) === sign(Date.parse(a) - Date.parse(b))`
    - When this test passes, it confirms ISO-8601 date strings are now compared chronologically
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** — Non-Date Values Sort Identically
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions for numbers, plain strings, nullish values)
    - Confirm all tests still pass after fix (no regressions)

  - [x] 3.4 Backend: Serialize TransactionDate as ISO strings (discovered during verification)
    - **File**: `backend/src/services/banking_service.py` — `get_mutaties()` method
    - **Discovery**: Flask's `jsonify` serializes Python `datetime.date` objects as HTTP date format (`"Wed, 14 Jan 2026 00:00:00 GMT"`) instead of ISO format (`"2026-01-14"`). This meant the frontend `compareValues` never matched the ISO regex, falling through to `localeCompare` on day-of-week names — the actual root cause of the visible sorting issue.
    - **Fix**: After `cursor.fetchall()`, convert `TransactionDate` values to ISO strings via `.isoformat()` before returning:
      ```python
      for row in results:
          val = row.get('TransactionDate')
          if val and hasattr(val, 'isoformat'):
              row['TransactionDate'] = val.isoformat()
      ```
    - **Why this wasn't planned**: The spec assumed `TransactionDate` arrived at the frontend as ISO strings. The HTTP date format was only discovered when the frontend fix alone didn't resolve the sorting issue in the browser.
    - _Requirements: 1.1, 2.1, 2.2, 2.3_

- [x] 4. Checkpoint — Ensure all tests pass
  - Run the full test suite: `npx jest --testPathPattern="useTableSort" --run`
  - Verify both the new date fix property tests and the existing `useTableSort.property.test.ts` pass
  - Verify no regressions in sort state determinism (Property 3) or sort ordering correctness (Property 4)
  - Ensure all tests pass, ask the user if questions arise
