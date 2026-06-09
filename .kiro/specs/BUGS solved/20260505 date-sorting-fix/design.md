# Date Sorting Fix — Bugfix Design

## Overview

Several backend endpoints return Python `datetime.date` objects without explicit `.isoformat()` conversion. Flask's `jsonify` serializes these as HTTP date strings (e.g., `"Mon, 15 Jan 2024 00:00:00 GMT"`) instead of ISO-8601 format (`"2024-01-15"`). The frontend's `isISODateString()` regex in `useTableSort.ts` cannot match these HTTP date strings, causing date column sorting to fall back to lexicographic string comparison instead of chronological comparison.

The fix is backend-only: introduce a shared utility function that normalizes `datetime.date` objects in query result dictionaries to ISO-8601 strings, then apply it in the four affected endpoints before returning JSON responses.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — when an API response contains `datetime.date` objects that Flask serializes as HTTP date strings instead of ISO-8601
- **Property (P)**: The desired behavior — all date fields in API responses are ISO-8601 formatted strings (`"YYYY-MM-DD"`) enabling correct chronological sorting
- **Preservation**: Existing behavior that must remain unchanged — the `/api/banking/mutaties` endpoint's working date serialization, non-date field values, and the frontend sorting logic for numbers and strings
- **`isISODateString()`**: The function in `frontend/src/hooks/useTableSort.ts` that detects ISO-8601 date strings via regex `/^\d{4}-\d{2}-\d{2}(T[\d:.Z+-]*)?$/`
- **`DatabaseManager.execute_query()`**: Returns list of dictionaries from `cursor(dictionary=True)` — date columns come back as Python `datetime.date` objects
- **HTTP date string**: Flask's default serialization of `datetime.date` objects, e.g., `"Mon, 15 Jan 2024 00:00:00 GMT"`

## Bug Details

### Bug Condition

The bug manifests when any of the four affected endpoints return query results containing `datetime.date` objects without converting them to ISO strings before passing to `jsonify()`. Flask's default JSON encoder calls `http_date()` on date objects, producing HTTP-formatted date strings that the frontend cannot recognize as dates.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type APIResponse
  OUTPUT: boolean

  RETURN input.endpoint IN {'/api/reports/mutaties-table',
                            '/api/reports/check-reference',
                            '/api/bnb/bnb-table',
                            '/api/str-invoice/search-booking'}
         AND input.response contains fields (TransactionDate | checkinDate | checkoutDate)
         AND those fields are Python datetime.date objects (not pre-converted to ISO strings)
         AND jsonify() serializes them as HTTP date strings
END FUNCTION
```

### Examples

- **Mutaties Table**: `TransactionDate` = `datetime.date(2024, 1, 15)` → serialized as `"Mon, 15 Jan 2024 00:00:00 GMT"` → frontend `isISODateString()` returns `false` → lexicographic sort produces `"Fri, 01 Mar..."` before `"Mon, 15 Jan..."` (incorrect)
- **Check Reference**: Same `TransactionDate` issue — transactions sorted by day-name prefix instead of chronologically
- **BNB Table**: `checkinDate` = `datetime.date(2024, 3, 5)` → `"Tue, 05 Mar 2024 00:00:00 GMT"` → sorting by check-in date is alphabetical by weekday
- **Search Booking**: `checkoutDate` = `datetime.date(2024, 3, 10)` → `"Sun, 10 Mar 2024 00:00:00 GMT"` → same issue
- **Working endpoint** (banking/mutaties): explicitly does `row['TransactionDate'] = val.isoformat()` → produces `"2024-01-15"` → `isISODateString()` returns `true` → chronological sort works

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- `/api/banking/mutaties` endpoint must continue to serialize `TransactionDate` as ISO-8601 (already working)
- `/api/str/future-trend` endpoint must continue to return `date` as ISO strings (stored as `char(12)`)
- Non-date fields (`TransactionDescription`, `Amount`, `guestName`, `reservationCode`, `channel`, etc.) must remain in their current format
- Numeric fields must continue to be returned as numbers
- Null/undefined values must continue to be returned as `null`
- Frontend `useTableSort` hook logic must not be modified
- Frontend `isISODateString()` regex must not be modified

**Scope:**
All inputs that do NOT involve the four affected endpoints' date fields should be completely unaffected by this fix. This includes:

- All non-date columns in the affected endpoints
- All other endpoints in the application
- Frontend sorting behavior for numeric and string columns
- Null handling in sort comparisons

## Hypothesized Root Cause

Based on the code analysis, the root cause is confirmed (not hypothesized):

1. **Missing `.isoformat()` conversion in `reporting_routes.py`**: The `/mutaties-table` endpoint (line ~240) fetches results via `cursor.fetchall()` and passes them directly to `jsonify({'success': True, 'data': results})` without converting `TransactionDate` fields. Same for `/check-reference` (line ~535).

2. **Missing `.isoformat()` conversion in `bnb_routes.py`**: The `/bnb-table` endpoint (line ~350) fetches from `vw_bnb_total` and returns `results` directly — `checkinDate` and `checkoutDate` remain as `datetime.date` objects.

3. **Missing `.isoformat()` conversion in `str_invoice_routes.py`**: The `/search-booking` endpoint (line ~100) fetches from `vw_bnb_total` and returns `results` directly in `jsonify({'success': True, 'bookings': results})`.

4. **No centralized date serialization**: The project lacks a utility function to normalize date objects in query results. The banking service solved this ad-hoc with an inline loop (lines 561-563 of `banking_service.py`).

## Correctness Properties

Property 1: Bug Condition - Date Fields Serialized as ISO-8601

_For any_ API response from the affected endpoints where date fields (`TransactionDate`, `checkinDate`, `checkoutDate`) are present, the fixed endpoints SHALL return those fields as ISO-8601 formatted strings matching the pattern `YYYY-MM-DD` (e.g., `"2024-01-15"`), such that the frontend `isISODateString()` function returns `true` for each date value.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

Property 2: Preservation - Non-Date Fields and Other Endpoints Unchanged

_For any_ API response where the bug condition does NOT hold (non-date fields in affected endpoints, or any field in unaffected endpoints), the fixed code SHALL produce exactly the same response values as the original code, preserving numeric types, string values, null handling, and the existing working date serialization in `/api/banking/mutaties`.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

**Approach**: Create a shared utility function `normalize_dates(rows, date_fields)` that converts specified `datetime.date` fields to ISO strings in a list of row dictionaries. Apply it in each affected endpoint before returning results.

This approach is preferred over a custom JSON encoder because:

- It's explicit and targeted (only converts known date fields)
- It follows the existing pattern in `banking_service.py`
- It doesn't risk unintended side effects on other serialized types
- It's easy to test in isolation

**File**: `backend/src/utils/date_utils.py` (new file)

**Function**: `normalize_dates(rows, date_fields)`

**Specific Changes**:

1. **Create utility function** (`backend/src/utils/date_utils.py`):
   - `normalize_dates(rows: list[dict], date_fields: list[str]) -> list[dict]`
   - Iterates over rows, converts any `datetime.date` or `datetime.datetime` objects in specified fields to `.isoformat()`
   - Returns the same list (mutates in place for efficiency, matching the banking_service pattern)
   - Handles `None` values gracefully (skips them)

2. **Fix `/api/reports/mutaties-table`** (`backend/src/reporting_routes.py`):
   - After `results = cursor.fetchall()`, call `normalize_dates(results, ['TransactionDate'])`

3. **Fix `/api/reports/check-reference`** (`backend/src/reporting_routes.py`):
   - After `transactions = db.execute_query(...)`, call `normalize_dates(transactions, ['TransactionDate'])`

4. **Fix `/api/bnb/bnb-table`** (`backend/src/bnb_routes.py`):
   - After `results = cursor.fetchall()`, call `normalize_dates(results, ['checkinDate', 'checkoutDate'])`

5. **Fix `/api/str-invoice/search-booking`** (`backend/src/str_invoice_routes.py`):
   - After `results = cursor.fetchall()`, call `normalize_dates(results, ['checkinDate', 'checkoutDate'])`

6. **Fix `/api/bnb/bnb-guest-bookings`** (`backend/src/bnb_routes.py`):
   - This endpoint also returns `checkinDate` and `checkoutDate` from the `bnb` table — apply same fix for consistency

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm the root cause by showing that `datetime.date` objects are serialized as HTTP date strings.

**Test Plan**: Write pytest tests that call the affected endpoints (or simulate their serialization logic) and assert that date fields match ISO-8601 format. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:

1. **Mutaties Table Date Format**: Call `/api/reports/mutaties-table` and check `TransactionDate` matches `^\d{4}-\d{2}-\d{2}$` (will fail on unfixed code)
2. **Check Reference Date Format**: Call `/api/reports/check-reference` and check `TransactionDate` format (will fail on unfixed code)
3. **BNB Table Date Format**: Call `/api/bnb/bnb-table` and check `checkinDate`/`checkoutDate` format (will fail on unfixed code)
4. **Search Booking Date Format**: Call `/api/str-invoice/search-booking` and check `checkinDate`/`checkoutDate` format (will fail on unfixed code)

**Expected Counterexamples**:

- Date fields contain strings like `"Mon, 15 Jan 2024 00:00:00 GMT"` instead of `"2024-01-15"`
- Root cause confirmed: no `.isoformat()` call before `jsonify()`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := normalize_dates(query_results, date_fields)
  FOR ALL row IN result DO
    FOR ALL field IN date_fields DO
      ASSERT row[field] matches /^\d{4}-\d{2}-\d{2}$/
      ASSERT isISODateString(row[field]) = true
    END FOR
  END FOR
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT normalize_dates(input, date_fields) preserves non-date fields exactly
  ASSERT normalize_dates(input, date_fields) preserves None values as None
  ASSERT normalize_dates(input, date_fields) preserves string fields unchanged
  ASSERT normalize_dates(input, date_fields) preserves numeric fields unchanged
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many random row dictionaries with mixed field types
- It catches edge cases (empty lists, None values, already-string dates, mixed types)
- It provides strong guarantees that non-date fields are never modified

**Test Plan**: Generate random dictionaries with various field types and verify that `normalize_dates` only modifies the specified date fields while leaving everything else untouched.

**Test Cases**:

1. **Non-Date Field Preservation**: Generate rows with string, int, float, None, and bool fields — verify they are unchanged after `normalize_dates`
2. **Already-ISO String Preservation**: If a date field is already a string (e.g., from a `char` column), verify it passes through unchanged
3. **None Date Preservation**: If a date field is `None`, verify it remains `None`
4. **Banking Endpoint Unchanged**: Verify `/api/banking/mutaties` continues to work with its existing inline conversion

### Unit Tests

- Test `normalize_dates()` with `datetime.date` objects → produces ISO strings
- Test `normalize_dates()` with `None` values → preserves `None`
- Test `normalize_dates()` with already-string values → passes through unchanged
- Test `normalize_dates()` with empty list → returns empty list
- Test `normalize_dates()` with fields not present in row → no error
- Test `normalize_dates()` with `datetime.datetime` objects → produces ISO date string

### Property-Based Tests

- Generate random lists of row dictionaries with `datetime.date` fields and verify all dates become ISO strings after `normalize_dates` (Hypothesis, `@given` with `st.dates()`)
- Generate random row dictionaries with mixed types and verify non-date fields are preserved exactly (Hypothesis, `@given` with composite strategies)
- Generate random date values and verify the output matches `isISODateString` regex from the frontend

### Integration Tests

- Test full endpoint response format for `/api/reports/mutaties-table` with real database
- Test full endpoint response format for `/api/bnb/bnb-table` with real database
- Test that frontend `isISODateString()` accepts the fixed output format (Vitest)
- Test that `useTableSort` correctly sorts dates from fixed endpoints chronologically (Vitest)
