# Bugfix Requirements Document

## Introduction

Date column sorting fails in several tables across the application. The frontend sorting framework (`useTableSort.ts`) uses `isISODateString()` to detect date values and sort them chronologically. When dates arrive in non-ISO format, the detection fails and sorting falls back to lexicographic string comparison (`localeCompare`), which does not produce chronological order.

The root cause is that several backend endpoints return raw MySQL `DATE` objects via Flask's `jsonify`, which serializes them as HTTP date strings (e.g., `"Thu, 15 Jan 2024 00:00:00 GMT"`) instead of ISO-8601 format (e.g., `"2024-01-15"`). Endpoints that explicitly convert date objects to ISO strings using `.isoformat()` work correctly.

**Affected endpoints:**

- `/api/reports/mutaties-table` — `TransactionDate` field
- `/api/reports/check-reference` — `TransactionDate` field
- `/api/bnb/bnb-table` — `checkinDate`, `checkoutDate` fields
- `/api/str-invoice/search-booking` — `checkinDate`, `checkoutDate` fields

**Working reference:**

- `/api/banking/mutaties` — explicitly converts `TransactionDate` via `.isoformat()`
- `/api/str/future-trend` — `bnbfuture.date` is stored as `char(12)` (already ISO string)

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the `/api/reports/mutaties-table` endpoint returns data containing `TransactionDate` values THEN the system serializes Python `datetime.date` objects as HTTP date strings (e.g., "Mon, 15 Jan 2024 00:00:00 GMT") instead of ISO-8601 format

1.2 WHEN the `/api/reports/check-reference` endpoint returns transaction data containing `TransactionDate` values THEN the system serializes Python `datetime.date` objects as HTTP date strings instead of ISO-8601 format

1.3 WHEN the `/api/bnb/bnb-table` endpoint returns data containing `checkinDate` and `checkoutDate` values THEN the system serializes Python `datetime.date` objects as HTTP date strings instead of ISO-8601 format

1.4 WHEN the `/api/str-invoice/search-booking` endpoint returns booking data containing `checkinDate` and `checkoutDate` values THEN the system serializes Python `datetime.date` objects as HTTP date strings instead of ISO-8601 format

1.5 WHEN the frontend `isISODateString()` function receives a date value in HTTP date format (e.g., "Mon, 15 Jan 2024 00:00:00 GMT") THEN the system fails to detect it as a date and falls back to lexicographic string comparison

1.6 WHEN the user sorts a date column in the MutatiesReport, Check Reference transactions, BNB Revenue Analysis, or STR Invoice Generator tables THEN the system sorts dates lexicographically instead of chronologically, producing incorrect sort order

### Expected Behavior (Correct)

2.1 WHEN the `/api/reports/mutaties-table` endpoint returns data containing `TransactionDate` values THEN the system SHALL serialize them as ISO-8601 date strings (format: "YYYY-MM-DD")

2.2 WHEN the `/api/reports/check-reference` endpoint returns transaction data containing `TransactionDate` values THEN the system SHALL serialize them as ISO-8601 date strings (format: "YYYY-MM-DD")

2.3 WHEN the `/api/bnb/bnb-table` endpoint returns data containing `checkinDate` and `checkoutDate` values THEN the system SHALL serialize them as ISO-8601 date strings (format: "YYYY-MM-DD")

2.4 WHEN the `/api/str-invoice/search-booking` endpoint returns booking data containing `checkinDate` and `checkoutDate` values THEN the system SHALL serialize them as ISO-8601 date strings (format: "YYYY-MM-DD")

2.5 WHEN the frontend `isISODateString()` function receives a date value in ISO-8601 format (e.g., "2024-01-15") THEN the system SHALL correctly detect it as a date string

2.6 WHEN the user sorts a date column in any of the affected tables THEN the system SHALL sort dates in correct chronological order (ascending or descending as selected)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the `/api/banking/mutaties` endpoint returns data containing `TransactionDate` values THEN the system SHALL CONTINUE TO serialize them as ISO-8601 date strings and sorting SHALL CONTINUE TO work chronologically

3.2 WHEN the `/api/str/future-trend` endpoint returns data containing `date` values THEN the system SHALL CONTINUE TO return them as ISO-8601 strings (already stored as `char(12)` in database) and sorting SHALL CONTINUE TO work chronologically

3.3 WHEN non-date string columns are sorted (e.g., `TransactionDescription`, `guestName`, `channel`) THEN the system SHALL CONTINUE TO sort them using case-insensitive string comparison via `localeCompare`

3.4 WHEN numeric columns are sorted (e.g., `Amount`, `amountGross`, `nights`) THEN the system SHALL CONTINUE TO sort them using numeric comparison

3.5 WHEN null or undefined values appear in a sorted column THEN the system SHALL CONTINUE TO sort them to the end regardless of sort direction

3.6 WHEN the affected endpoints return non-date fields (e.g., `TransactionDescription`, `Amount`, `guestName`, `reservationCode`) THEN the system SHALL CONTINUE TO return them in their current format without modification

---

## Bug Condition

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type APIResponse
  OUTPUT: boolean

  // Returns true when the response contains date fields that are Python
  // datetime.date objects being serialized by Flask's jsonify without
  // explicit .isoformat() conversion
  RETURN X.endpoint IN {'/api/reports/mutaties-table', '/api/reports/check-reference',
                         '/api/bnb/bnb-table', '/api/str-invoice/search-booking'}
         AND X.response contains date fields (TransactionDate, checkinDate, checkoutDate)
         AND those fields are Python datetime.date objects (not pre-converted strings)
END FUNCTION
```

## Property Specification

```pascal
// Property: Fix Checking - Date Serialization
FOR ALL X WHERE isBugCondition(X) DO
  response ← endpoint'(X)
  FOR ALL date_field IN response.date_fields DO
    ASSERT matches(date_field, /^\d{4}-\d{2}-\d{2}$/)
    ASSERT isISODateString(date_field) = true
  END FOR
END FOR

// Property: Fix Checking - Sort Correctness
FOR ALL dates[] WHERE all elements match ISO-8601 format DO
  sorted_asc ← sort(dates, 'asc')
  FOR i FROM 0 TO length(sorted_asc) - 2 DO
    ASSERT Date.parse(sorted_asc[i]) <= Date.parse(sorted_asc[i+1])
  END FOR
END FOR
```

## Preservation Goal

```pascal
// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT endpoint(X) = endpoint'(X)
END FOR

// Specifically: working endpoints remain unchanged
FOR ALL X WHERE X.endpoint = '/api/banking/mutaties' DO
  ASSERT endpoint(X).TransactionDate matches /^\d{4}-\d{2}-\d{2}$/
END FOR
```
