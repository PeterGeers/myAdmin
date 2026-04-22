# Balance Check Annual Closure Bugfix Design

## Overview

After an annual closure (jaarafsluiting), the banking account balance check (`check_banking_accounts`) and sequence number check (`check_sequence_numbers`) in `backend/src/banking_processor.py` still aggregate ALL transactions instead of scoping to transactions since the last year closure. This causes incorrect balance calculations and false sequence gap reports because closed-year transactions should no longer be included.

The fix introduces a closure-aware lower bound: both functions query `year_closure_status` to find the most recent closed year, derive the opening balance date (January 1 of the year after the last closed year), and filter transactions `>= opening_balance_date`. A new API endpoint returns the opening balance date so the frontend can display it as a read-only start date field. Administrations without closures keep their current behavior unchanged.

## Glossary

- **Bug_Condition (C)**: The administration has at least one record in `year_closure_status` — meaning a year closure has been performed, but the balance/sequence checks ignore it
- **Property (P)**: When the bug condition holds, both check functions scope transactions to `>= opening_balance_date` (Jan 1 of last_closed_year + 1), and the frontend shows this date as read-only
- **Preservation**: Administrations with no year closures continue to use all transactions for balance checks and the default editable start date for sequence checks
- **opening_balance_date**: January 1 of the year following the most recent closed year. E.g., if 2024 is the last closed year, opening_balance_date = `2025-01-01`
- **check_banking_accounts**: Function in `banking_processor.py` (~line 222) that calculates account balances by summing `vw_mutaties.Amount`
- **check_sequence_numbers**: Function in `banking_processor.py` (~line 355) that checks Ref2 sequence gaps in `mutaties` since a start date
- **year_closure_status**: Table tracking closed fiscal years per administration (columns: year, administration, closed_date, closed_by, etc.)
- **vw_mutaties**: View used for balance calculations, contains `Amount`, `Reknum`, `Administration`, `TransactionDate`

## Bug Details

### Bug Condition

The bug manifests when an administration has completed at least one annual closure. The `check_banking_accounts` function sums ALL transactions across all years (no lower date bound), and `check_sequence_numbers` uses a hardcoded default start date (`2025-01-01`) or a manually provided date, neither of which considers the closure boundary. This means closed-year transactions are included in calculations that should only cover the current open period.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type { administration: string, check_type: "balance" | "sequence" }
  OUTPUT: boolean

  closed_years ← SELECT year FROM year_closure_status
                  WHERE administration = input.administration

  RETURN closed_years IS NOT EMPTY
END FUNCTION
```

### Examples

- **Single closure (2024 closed)**: Administration "PeterPrive" has year 2024 closed. `check_banking_accounts` sums all transactions from 2020–2025 instead of only 2025-01-01 onwards → balance is incorrect because it includes pre-closure amounts
- **Multiple closures (2023 and 2024 closed)**: Administration "GoodwinSolutions" has years 2023 and 2024 closed. Balance check should start from 2025-01-01 (year after latest closure), but currently includes all years → inflated or deflated balances
- **Sequence check with closure**: Administration has 2024 closed. Sequence check uses default `2025-01-01` which happens to be correct by coincidence, but if the user changes the start date to `2024-01-01`, closed-year transactions are included → false gap reports from the closed period
- **No closure (preservation)**: Administration "NewTenant" has no closures → all transactions should be included in balance check, and sequence start date remains editable with default → no change in behavior

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Administrations with NO year closures must continue to calculate balances using all transactions (no lower date bound)
- Administrations with NO year closures must continue to use the default editable start date for sequence checks
- The `end_date` parameter for balance checks must continue to work as an upper bound filter
- Sequence gap detection logic (comparing Ref2 values) must remain unchanged
- The response structure of both check endpoints must remain unchanged
- Mouse/keyboard interactions with the banking processor UI must remain unchanged for non-closure scenarios

**Scope:**
All administrations that do NOT have any records in `year_closure_status` should be completely unaffected by this fix. This includes:

- Balance calculations for no-closure administrations
- Sequence checks for no-closure administrations
- Frontend date input behavior for no-closure administrations
- All other banking processor functionality (mutaties, lookups, imports, etc.)

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **No closure-aware query boundary in `check_banking_accounts`**: The function (line ~252) builds a `SUM(Amount)` query on `vw_mutaties` filtered only by `Administration` and optionally `end_date`. There is no `TransactionDate >= opening_balance_date` condition, so all historical transactions are summed.

2. **No closure-aware start date in `check_sequence_numbers`**: The function (line ~355) accepts a `start_date` parameter defaulting to `'2025-01-01'`. This is a hardcoded coincidence — it doesn't query `year_closure_status` to determine the correct boundary. The frontend sends whatever the user types in the date field.

3. **No API endpoint for opening balance date**: There is no endpoint that returns the closure-derived opening balance date for an administration. The frontend has no way to know what the correct start date should be.

4. **Frontend date field always editable**: The sequence start date `<Input type="date">` (line ~1457) is always editable with a hardcoded default of `'2025-01-01'`. When a closure exists, this field should be read-only and show the opening balance date.

## Correctness Properties

Property 1: Bug Condition - Balance and sequence checks scope to post-closure transactions

_For any_ administration where at least one year closure exists in `year_closure_status`, the fixed `check_banking_accounts` function SHALL only sum transactions with `TransactionDate >= opening_balance_date` (where opening_balance_date = January 1 of max(closed_year) + 1), and the fixed `check_sequence_numbers` function SHALL only check sequences for transactions with `TransactionDate >= opening_balance_date`.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - No-closure administrations keep current behavior

_For any_ administration where NO year closure exists in `year_closure_status`, the fixed `check_banking_accounts` function SHALL produce the same result as the original function (all transactions summed), and the fixed `check_sequence_numbers` function SHALL accept the same start_date parameter with the same default behavior, preserving all existing functionality.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `backend/src/banking_processor.py`

**Function**: `check_banking_accounts` (~line 222)

**Specific Changes**:

1. **Query `year_closure_status` for the last closed year**: At the start of the function, after getting the database connection, query for the max closed year for the given administration.
2. **Derive opening_balance_date**: If a closed year exists, compute `opening_balance_date = f"{last_closed_year + 1}-01-01"`.
3. **Add `TransactionDate >= opening_balance_date` to the balance query**: Add this condition to both the `end_date` and non-`end_date` branches of the SUM query on `vw_mutaties`.
4. **Add the same filter to the "last transaction" subqueries**: The queries that find the last transaction per account should also respect the opening_balance_date boundary.

**Function**: `check_sequence_numbers` (~line 355)

**Specific Changes**:

1. **Query `year_closure_status` for the last closed year**: Same pattern as above.
2. **Override start_date when closure exists**: If a closed year exists, set `start_date = opening_balance_date` regardless of the parameter value. This ensures the sequence check always starts from the correct boundary.
3. **Keep existing start_date parameter for no-closure case**: When no closure exists, the function continues to use the provided `start_date` parameter with its default.

**File**: `backend/src/routes/banking_routes.py`

**New Endpoint**: `GET /api/banking/opening-balance-date`

**Specific Changes**:

1. **Create a new route** that accepts `administration` as a query parameter (or uses tenant from `@tenant_required()`).
2. **Query `year_closure_status`** for the max closed year for the tenant.
3. **Return** `{ success: true, opening_balance_date: "YYYY-01-01", last_closed_year: NNNN }` if a closure exists, or `{ success: true, opening_balance_date: null, last_closed_year: null }` if not.

**File**: `frontend/src/components/BankingProcessor.tsx`

**Specific Changes**:

1. **Add state for opening balance date**: `const [openingBalanceDate, setOpeningBalanceDate] = useState<string | null>(null)`
2. **Fetch opening balance date on mount / tenant change**: Call `GET /api/banking/opening-balance-date` and set state.
3. **When `openingBalanceDate` is set**: Update `sequenceStartDate` to the opening balance date and make the date input read-only.
4. **When `openingBalanceDate` is null**: Keep current behavior — editable date input with default `'2025-01-01'`.
5. **Pass opening_balance_date to check-accounts call**: Include it as a query parameter so the backend can use it (or let the backend derive it independently — preferred approach to avoid client-side tampering).

### Helper Pattern

Reuse the existing `_get_closed_years` pattern from `backend/src/actuals_routes.py` (line 116). Create a similar helper in `banking_processor.py` or extract a shared utility:

```python
def _get_opening_balance_date(db, administration):
    """Get the opening balance date based on the last closed year.

    Returns:
        str or None: 'YYYY-01-01' if closure exists, None otherwise
    """
    query = """
        SELECT MAX(year) as last_closed_year
        FROM year_closure_status
        WHERE administration = %s
    """
    rows = db.execute_query(query, [administration])
    if rows and rows[0]['last_closed_year']:
        return f"{rows[0]['last_closed_year'] + 1}-01-01"
    return None
```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that call `check_banking_accounts` and `check_sequence_numbers` for an administration with year closures, and assert that only post-closure transactions are included. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:

1. **Balance check with single closure**: Administration has 2024 closed, transactions exist in 2024 and 2025. Assert balance only includes 2025 transactions (will fail on unfixed code — includes all years)
2. **Balance check with multiple closures**: Administration has 2023 and 2024 closed. Assert balance starts from 2025-01-01 (will fail on unfixed code)
3. **Sequence check with closure**: Administration has 2024 closed. Assert sequence check only examines transactions >= 2025-01-01 (will fail on unfixed code if start_date is set to an earlier date)
4. **Balance check with end_date and closure**: Administration has 2024 closed, end_date is 2025-06-30. Assert transactions are in range [2025-01-01, 2025-06-30] (will fail on unfixed code — lower bound missing)

**Expected Counterexamples**:

- Balance calculations include transactions from closed years, producing incorrect totals
- Sequence checks include closed-year transactions, reporting false gaps from the closed period
- Possible causes: no `year_closure_status` query in either function, no `TransactionDate >= opening_balance_date` filter

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  last_closed_year ← MAX(year) FROM year_closure_status WHERE administration = input.administration
  opening_balance_date ← f"{last_closed_year + 1}-01-01"

  IF input.check_type = "balance" THEN
    result ← check_banking_accounts_fixed(input)
    ASSERT all transactions in result have TransactionDate >= opening_balance_date
  END IF

  IF input.check_type = "sequence" THEN
    result ← check_sequence_numbers_fixed(input)
    ASSERT all transactions checked have TransactionDate >= opening_balance_date
  END IF
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT check_banking_accounts_original(input) = check_banking_accounts_fixed(input)
  ASSERT check_sequence_numbers_original(input) = check_sequence_numbers_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many administration/date combinations automatically
- It catches edge cases in date boundary handling
- It provides strong guarantees that no-closure behavior is unchanged

**Test Plan**: Observe behavior on UNFIXED code first for no-closure administrations, then write property-based tests capturing that behavior.

**Test Cases**:

1. **No-closure balance preservation**: Verify that administrations without closures produce identical balance results before and after the fix
2. **No-closure sequence preservation**: Verify that administrations without closures produce identical sequence check results before and after the fix
3. **End-date filter preservation**: Verify that the end_date upper bound continues to work correctly in combination with the new lower bound
4. **Response structure preservation**: Verify that the response JSON structure is unchanged for both endpoints

### Unit Tests

- Test `_get_opening_balance_date` helper with single closure, multiple closures, and no closures
- Test `check_banking_accounts` with closure → only post-closure transactions summed
- Test `check_banking_accounts` without closure → all transactions summed (preservation)
- Test `check_sequence_numbers` with closure → start_date overridden to opening_balance_date
- Test `check_sequence_numbers` without closure → start_date parameter used as-is (preservation)
- Test new `/api/banking/opening-balance-date` endpoint returns correct date or null

### Property-Based Tests

- Generate random administration states (with/without closures, various closed years) and verify balance checks respect the correct boundary
- Generate random transaction date ranges and verify sequence checks only include post-closure transactions when closures exist
- Generate random no-closure administrations and verify identical behavior before and after fix

### Integration Tests

- Test full flow: create closure → check balance → verify only post-closure transactions included
- Test frontend: fetch opening balance date → verify date field becomes read-only with correct value
- Test frontend: no closure → verify date field remains editable with default value
- Test combined: closure exists + end_date parameter → verify both bounds applied correctly
