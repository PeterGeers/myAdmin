# Bugfix Requirements Document

## Introduction

After an annual closure (jaarafsluiting), the banking account balance check (`check_banking_accounts`) and sequence number check (`check_sequence_numbers`) still aggregate ALL transactions instead of scoping to transactions since the last year closure. This causes incorrect balance calculations and false sequence gap reports, because closed-year transactions should no longer be included in these checks. The `year_closure_status` table already tracks which years have been closed, but neither function consults it.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN an annual closure exists for an administration THEN the system calculates banking account balances by summing ALL transactions across all years, including transactions from closed years

1.2 WHEN an annual closure exists for an administration THEN the system checks sequence numbers starting from a hardcoded default date ('2025-01-01') or a manually provided start date, without considering the last closure date

1.3 WHEN multiple annual closures exist (e.g. 2023 and 2024 are both closed) THEN the system still includes transactions from all closed years in balance calculations and sequence checks

### Expected Behavior (Correct)

2.1 WHEN an annual closure exists for an administration THEN the system SHALL query the `year_closure_status` table to find the most recent closed year and derive the opening balance date (January 1 of the year following the last closed year) as the start boundary for balance calculations

2.2 WHEN an annual closure exists for an administration THEN the system SHALL automatically set the sequence check start date to the opening balance date (January 1 of the year following the last closed year), instead of using a hardcoded default or requiring manual input

2.3 WHEN multiple annual closures exist THEN the system SHALL use the most recent (latest) closed year to derive the opening balance date as the boundary

2.4 WHEN an annual closure exists THEN the frontend SHALL display the start date as the opening balance date in a read-only field, so the user can see which date is being used but cannot change it to an invalid value

2.5 WHEN the backend returns the opening balance date THEN the frontend SHALL use it to populate the sequence start date field as read-only, replacing the current editable date input

### Unchanged Behavior (Regression Prevention)

3.1 WHEN no annual closure exists for an administration THEN the system SHALL CONTINUE TO calculate balances using all transactions (current fallback behavior)

3.2 WHEN no annual closure exists for an administration THEN the system SHALL CONTINUE TO use the existing default start date for sequence number checks, and the start date field SHALL remain editable

3.3 WHEN an end_date parameter is provided for balance checks THEN the system SHALL CONTINUE TO respect the end_date upper bound filter in combination with the closure-based lower bound

3.4 WHEN checking sequence numbers THEN the system SHALL CONTINUE TO detect gaps, report sequence issues, and return the same response structure

---

## Bug Condition

### Bug Condition Function

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type BankingCheckInput (administration, check_type)
  OUTPUT: boolean

  // Returns true when the administration has at least one closed year
  RETURN EXISTS(record IN year_closure_status WHERE record.administration = X.administration)
END FUNCTION
```

### Property Specification — Fix Checking

```pascal
// Property: Fix Checking — Balance and sequence checks scope to post-closure transactions
FOR ALL X WHERE isBugCondition(X) DO
  last_closed_year ← MAX(year) FROM year_closure_status WHERE administration = X.administration
  opening_balance_date ← January 1 of (last_closed_year + 1)

  IF X.check_type = "balance" THEN
    result ← check_banking_accounts'(X)
    ASSERT all transactions in result have TransactionDate >= opening_balance_date
  END IF

  IF X.check_type = "sequence" THEN
    result ← check_sequence_numbers'(X)
    ASSERT all transactions checked have TransactionDate >= opening_balance_date
  END IF

  // Frontend property: start date is read-only and shows opening_balance_date
  ASSERT frontend.sequenceStartDate = opening_balance_date
  ASSERT frontend.sequenceStartDate.isReadOnly = true
END FOR
```

### Preservation Checking

```pascal
// Property: Preservation Checking — No closure means unchanged behavior
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT check_banking_accounts(X) = check_banking_accounts'(X)
  ASSERT check_sequence_numbers(X) = check_sequence_numbers'(X)
END FOR
```
