# Date Sorting Fix — Bugfix Design

## Overview

The `compareValues()` function in `frontend/src/hooks/useTableSort.ts` does not detect ISO-8601 date strings (`YYYY-MM-DD`), causing them to fall through to the `String.localeCompare` fallback. While lexicographic comparison happens to work for same-length ISO dates in many cases, it fails for cross-month/year comparisons where string order diverges from chronological order (e.g. `"2024-02-01"` sorts after `"2024-11-30"` lexicographically in some locales). The fix adds a date-detection branch between the existing number check and the string fallback, using a regex pre-check plus `Date.parse()` validation for reliable ISO-8601 detection. This is a minimal, targeted change to a single pure function — no hook API or component changes required.

## Glossary

- **Bug_Condition (C)**: Both compared values are non-nullish, non-numeric strings, and at least one is a valid ISO-8601 date string — causing `compareValues` to use `localeCompare` instead of timestamp comparison
- **Property (P)**: When both values are ISO-8601 date strings, `compareValues` returns a value whose sign matches `Date.parse(a) - Date.parse(b)`, producing chronological ordering
- **Preservation**: All existing sorting behavior for numbers, plain strings, and nullish values must remain identical after the fix
- **`compareValues(a, b)`**: Pure function in `useTableSort.ts` that returns a numeric comparator value (negative, zero, or positive) used by `Array.sort()`
- **`isISODateString(value)`**: New helper function to detect ISO-8601 date strings via regex + `Date.parse()` validation
- **ISO-8601 date string**: A string matching the pattern `YYYY-MM-DD` with optional time component (e.g. `"2024-01-15"`, `"2024-01-15T10:30:00"`)

## Bug Details

### Bug Condition

The bug manifests when `compareValues` receives two non-nullish, non-numeric values where at least one is an ISO-8601 date string. The function's type-check cascade (nullish → number → string fallback) has no date branch, so date strings are compared lexicographically via `String(a).localeCompare(String(b))`.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type { a: unknown, b: unknown }
  OUTPUT: boolean

  RETURN NOT isNullish(input.a) AND NOT isNullish(input.b)
         AND NOT (isNumber(input.a) AND isNumber(input.b))
         AND (isISODateString(input.a) OR isISODateString(input.b))
END FUNCTION

FUNCTION isISODateString(value)
  INPUT: value of type unknown
  OUTPUT: boolean

  IF typeof value ≠ 'string' THEN RETURN false
  IF NOT value matches /^\d{4}-\d{2}-\d{2}(T.*)?$/ THEN RETURN false
  LET parsed = Date.parse(value)
  RETURN Number.isFinite(parsed)
END FUNCTION
```

### Examples

- **Cross-month**: Sorting `"2024-02-01"` vs `"2024-11-30"` ascending — expected: Feb before Nov; actual: may vary by locale since `localeCompare` treats these as arbitrary strings
- **Cross-year**: Sorting `"2023-12-31"` vs `"2024-01-01"` ascending — expected: 2023 before 2024; actual: correct by coincidence (lexicographic order matches), but this is not guaranteed behavior
- **Same month**: Sorting `"2024-01-05"` vs `"2024-01-15"` ascending — expected: 5th before 15th; actual: happens to work lexicographically, but relies on string comparison rather than date semantics
- **Mixed date/non-date**: Sorting `"2024-01-15"` vs `"not-a-date"` — expected: treated as strings (only one is a date); actual: currently uses `localeCompare` which is the correct fallback for mixed types

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Numeric value pairs must continue to sort via numeric comparison (`a - b`)
- Plain text string pairs (non-date, non-numeric) must continue to sort via case-insensitive `localeCompare`
- Null/undefined values must continue to sort to the end of the list regardless of sort direction
- Both-nullish pairs must continue to return `0` (equal)
- The `useTableSort` hook API (sortField, sortDirection, handleSort, getSortIndicator) must remain unchanged
- The `useFilterableTable` composition (filter → sort pipeline) must remain unchanged
- Sort toggle behavior (same field toggles direction, new field resets to asc) must remain unchanged

**Scope:**
All inputs where neither value is an ISO-8601 date string should be completely unaffected by this fix. This includes:

- Pairs of numbers
- Pairs of plain text strings
- Pairs involving null or undefined
- Mixed number/string pairs
- UI interactions (column clicks, filter changes, direction toggles)

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is straightforward:

1. **Missing date type branch in `compareValues`**: The function has a three-step cascade: nullish check → number check → string fallback. There is no date detection step. ISO-8601 date strings pass the nullish check (they're not null), fail the number check (`typeof "2024-01-15" !== 'number'`), and fall through to `String(a).localeCompare(String(b))`.

2. **Design oversight in table-filter-framework-v2**: The original `useTableSort` design (§2 of the framework spec) specified only three value types: null/undefined, numbers, and strings. Date columns like `TransactionDate` in `BankingMutatiesTab` store dates as ISO-8601 strings, which were not accounted for as a distinct comparison type.

3. **Coincidental correctness masking the bug**: For many ISO-8601 date pairs, lexicographic comparison produces the same result as chronological comparison (the format is designed to be sortable as strings). This made the bug hard to notice — it only manifests visibly when locale-specific `localeCompare` behavior diverges from byte-order comparison, or in edge cases with mixed date formats.

## Correctness Properties

Property 1: Bug Condition — Date strings sort chronologically

_For any_ pair of values `(a, b)` where both are valid ISO-8601 date strings (non-nullish, non-numeric, matching `YYYY-MM-DD` with optional time component and valid per `Date.parse`), the fixed `compareValues` function SHALL return a value whose sign equals `sign(Date.parse(a) - Date.parse(b))`, producing chronological ordering.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation — Non-date values sort identically

_For any_ pair of values `(a, b)` where the bug condition does NOT hold (neither value is an ISO-8601 date string, or values are nullish, or both are numbers), the fixed `compareValues` function SHALL produce exactly the same return value as the original `compareValues` function, preserving numeric, string, and nullish sorting behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `frontend/src/hooks/useTableSort.ts`

**Function**: `compareValues(a: unknown, b: unknown): number`

**Specific Changes**:

1. **Add `isISODateString` helper function** (above `compareValues`):
   - Accept `unknown` input, return `boolean`
   - Check `typeof value === 'string'` first (fast path rejection)
   - Apply regex `/^\d{4}-\d{2}-\d{2}(T[\d:.Z+-]*)?$/` to validate format
   - Call `Date.parse(value)` and verify result is finite via `Number.isFinite()`
   - The regex pre-check avoids expensive `Date.parse` calls on non-date strings

2. **Add date comparison branch in `compareValues`** (between the number check and string fallback):

   ```
   // After: if (isNumber(a) && isNumber(b)) { return a - b; }
   // Before: return String(a).localeCompare(...)

   // Both ISO date strings → chronological comparison
   if (isISODateString(a) && isISODateString(b)) {
     return Date.parse(a as string) - Date.parse(b as string);
   }
   ```

3. **Require both values to be dates**: Only use date comparison when both `a` and `b` are ISO date strings. If only one is a date, fall through to `localeCompare` — this preserves the existing mixed-type behavior and avoids surprising comparisons between dates and arbitrary strings.

4. **Placement rationale**: The date check goes after the number check because:
   - Numbers are cheaper to detect (`typeof` check) and more common in the codebase
   - Date detection requires regex + `Date.parse`, which is more expensive
   - The nullish → number → date → string cascade maintains a clear type-narrowing order

5. **No changes to hook API or components**: The fix is entirely within the `compareValues` pure function. No changes to `useTableSort`, `useFilterableTable`, `FilterableHeader`, or any table component.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior. All property-based tests use fast-check 4.4.0 with `@fast-check/jest` integration, consistent with the existing `useTableSort.property.test.ts` patterns.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm that `compareValues` uses `localeCompare` for date strings and produces incorrect ordering for specific date pairs.

**Test Plan**: Write tests that call the current `compareValues` with ISO-8601 date string pairs where chronological and lexicographic order diverge. Run on UNFIXED code to observe failures.

**Test Cases**:

1. **Cross-month divergence**: Compare `"2024-02-01"` vs `"2024-11-01"` — lexicographic may differ from chronological (will fail on unfixed code)
2. **Date pair ordering**: Compare `"2024-12-31"` vs `"2024-01-01"` — verify the sign matches `Date.parse` difference (will fail on unfixed code)
3. **Date with time component**: Compare `"2024-01-15T08:00:00"` vs `"2024-01-15T16:00:00"` — time-aware comparison (will fail on unfixed code)
4. **Full hook integration**: Sort an array of rows with `TransactionDate` field containing ISO dates, verify chronological order (will fail on unfixed code)

**Expected Counterexamples**:

- `compareValues("2024-02-01", "2024-11-01")` returns a positive value (localeCompare) instead of negative (chronological)
- Sorted date arrays are in lexicographic order rather than chronological order

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces chronological ordering.

**Pseudocode:**

```
FOR ALL (a, b) WHERE isISODateString(a) AND isISODateString(b) DO
  result := compareValues_fixed(a, b)
  expected := Date.parse(a) - Date.parse(b)
  ASSERT sign(result) = sign(expected)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL (a, b) WHERE NOT isBugCondition(a, b) DO
  ASSERT compareValues_original(a, b) = compareValues_fixed(a, b)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many test cases automatically across the input domain (numbers, strings, nulls, mixed types)
- It catches edge cases that manual unit tests might miss (e.g. numeric strings, empty strings, special characters)
- It provides strong guarantees that behavior is unchanged for all non-date inputs
- The existing `useTableSort.property.test.ts` already establishes PBT patterns with fast-check 4.4.0

**Test Plan**: Capture the behavior of the UNFIXED `compareValues` for non-date inputs, then write property-based tests verifying the fixed version produces identical results.

**Test Cases**:

1. **Number pair preservation**: Generate random finite number pairs, verify `compareValues_fixed(a, b) === compareValues_original(a, b)`
2. **Plain string preservation**: Generate random non-date string pairs, verify identical `localeCompare` results
3. **Nullish preservation**: Generate pairs involving null/undefined, verify identical sort-to-end behavior
4. **Mixed type preservation**: Generate mixed number/string pairs, verify identical fallback behavior

### Unit Tests

- Test `isISODateString` with valid dates: `"2024-01-15"`, `"2024-12-31"`, `"2024-01-15T10:30:00"`
- Test `isISODateString` with invalid inputs: `"not-a-date"`, `"2024-13-01"`, `""`, `null`, `42`, `"01-15-2024"`
- Test `compareValues` with date pairs: ascending and descending chronological order
- Test `compareValues` with mixed date/non-date: falls through to `localeCompare`
- Test full `useTableSort` hook with date column data: verify `sortedData` is chronologically ordered

### Property-Based Tests

- Generate random valid ISO-8601 date strings (year 1970–2099, month 01–12, day 01–28) and verify `compareValues` produces chronological ordering (fix checking)
- Generate random non-date values (numbers, plain strings, nullish) and verify `compareValues` produces identical results to the original function (preservation checking)
- Generate random row arrays with date fields and verify `useTableSort` produces chronologically sorted output with nullish values at the end

### Integration Tests

- Test `BankingMutatiesTab` sorting on `TransactionDate` column produces chronological order
- Test sort direction toggle on date columns: ascending = oldest first, descending = newest first
- Test that sorting on non-date columns (`TransactionAmount`, `TransactionDescription`) continues to work correctly after the fix
