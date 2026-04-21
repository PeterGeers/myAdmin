# Bugfix Requirements Document

## Introduction

The `useTableSort` hook's `compareValues()` function does not detect ISO-8601 date strings, causing date columns (such as `TransactionDate` in Banking Mutaties) to sort lexicographically instead of chronologically. This regression was introduced with the table-filter-framework-v2 implementation. The fix must be generic since `useTableSort` is shared across 7+ table components, any of which may have date columns.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user sorts a column containing ISO-8601 date strings (e.g. "2024-01-15") THEN the system sorts the values using string `localeCompare`, producing lexicographic order instead of chronological order

1.2 WHEN a user sorts a date column in ascending order where dates span different months or years (e.g. "2024-02-01" vs "2024-11-01") THEN the system may produce incorrect ordering because string comparison does not respect date semantics

1.3 WHEN a user toggles the sort direction on a date column from ascending to descending THEN the system reverses the lexicographic order rather than reversing the chronological order

### Expected Behavior (Correct)

2.1 WHEN a user sorts a column containing ISO-8601 date strings THEN the system SHALL detect the date values and sort them chronologically by converting to `Date` objects (or equivalent numeric timestamps) for comparison

2.2 WHEN a user sorts a date column in ascending order THEN the system SHALL display rows from oldest date to newest date

2.3 WHEN a user sorts a date column in descending order THEN the system SHALL display rows from newest date to oldest date

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user sorts a column containing numeric values THEN the system SHALL CONTINUE TO sort using numeric comparison

3.2 WHEN a user sorts a column containing plain text strings (non-date, non-numeric) THEN the system SHALL CONTINUE TO sort using case-insensitive `localeCompare`

3.3 WHEN a user sorts a column containing null or undefined values THEN the system SHALL CONTINUE TO place those values at the end of the sorted list regardless of sort direction

3.4 WHEN a user sorts a column where both values are null or undefined THEN the system SHALL CONTINUE TO treat them as equal (return 0)

3.5 WHEN a user interacts with column filters, filter reset, or sort toggle behavior THEN the system SHALL CONTINUE TO function identically to current behavior

---

## Bug Condition

### Bug Condition Function

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type SortInput (pair of values being compared)
  OUTPUT: boolean

  // Returns true when at least one value is an ISO-8601 date string
  // and neither value is a number, null, or undefined
  RETURN (isISODateString(X.a) OR isISODateString(X.b))
         AND NOT isNumber(X.a) AND NOT isNumber(X.b)
         AND NOT isNullish(X.a) AND NOT isNullish(X.b)
END FUNCTION

FUNCTION isISODateString(value)
  INPUT: value of type unknown
  OUTPUT: boolean

  RETURN typeof value = 'string'
         AND value matches pattern YYYY-MM-DD (with optional time component)
         AND Date.parse(value) is a valid finite number
END FUNCTION
```

### Property Specification — Fix Checking

```pascal
// Property: Fix Checking — Date values sort chronologically
FOR ALL X WHERE isBugCondition(X) DO
  result ← compareValues'(X.a, X.b)
  expected ← Date.parse(X.a) - Date.parse(X.b)
  ASSERT sign(result) = sign(expected)
END FOR
```

### Property Specification — Preservation Checking

```pascal
// Property: Preservation Checking — Non-date values sort identically
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT compareValues(X.a, X.b) = compareValues'(X.a, X.b)
END FOR
```

**Key Definitions:**

- **F** (`compareValues`): The original function — falls through to `String(a).localeCompare(String(b))` for date strings
- **F'** (`compareValues'`): The fixed function — detects ISO-8601 date strings and compares them as timestamps
