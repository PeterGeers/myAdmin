# Balance Closure-Aware Fix — Bugfix Design

## Overview

Balance sheet accounts (VW='N') are double-counted or under-counted across four reporting code paths because year filtering ignores fiscal year closure state. When a year is closed, an OpeningBalance record is created in the following year that carries forward all prior history. Code paths that cumulate raw transactions from closed years alongside the OpeningBalance that summarizes them produce inflated totals. The fix introduces a shared `get_closure_aware_start_year()` helper and applies it consistently in all affected paths so that cumulation always starts at `last_closed_year + 1`.

## Glossary

- **Bug_Condition (C)**: A balance sheet query whose year range includes both the last closed year's raw transactions AND the OpeningBalance record that already summarizes them, causing double-counting — OR a query that only looks at the target year and misses accumulated history when no OpeningBalance exists
- **Property (P)**: For balance sheet accounts, cumulation starts at `last_closed_year + 1` (the year containing the OpeningBalance), producing correct totals without double-counting or omission
- **Preservation**: P&L (VW='Y') filtering, closed-year single-year queries, tenant isolation, cache loading logic, and fallback behavior when no closures exist — all must remain unchanged
- **`get_closure_aware_start_year()`**: The new shared helper that queries `year_closure_status` and returns `last_closed_year + 1` or `None` (meaning no closures exist)
- **`year_closure_status`**: Existing table recording which fiscal years have been closed per administration
- **OpeningBalance**: A synthetic transaction created during year-end closure that carries forward all balance sheet account history into the next year
- **VW**: Account type flag — `'N'` = Balance Sheet (cumulative), `'Y'` = P&L (period-based)

## Bug Details

### Bug Condition

The bug manifests when a balance sheet (VW='N') query cumulates transactions across a year boundary where a fiscal year closure has occurred. The query includes both the closed year's raw transaction data AND the OpeningBalance record in the following year that already summarizes that data, resulting in double-counted balances. Conversely, when no closure exists for a prior year, queries that only look at the target year miss accumulated history.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type BalanceQuery { target_year, administration, code_path }
  OUTPUT: boolean

  closed_years := getClosedYears(input.administration)
  last_closed_year := MAX(closed_years) or NULL

  // Double-counting condition
  IF last_closed_year IS NOT NULL THEN
    IF input.code_path IN ['actuals_balance_per_year', 'actuals_balance_total'] THEN
      // Query uses jaar <= target_year, which includes last_closed_year
      RETURN input.target_year > last_closed_year
    END IF
    IF input.code_path IN ['make_ledgers_financial', 'make_ledgers_xlsx'] THEN
      // Query uses jaar < target_year for beginning balance
      RETURN input.target_year > last_closed_year
    END IF
  END IF

  // Under-counting condition (aangifte_ib)
  IF last_closed_year IS NULL OR last_closed_year < input.target_year - 1 THEN
    IF input.code_path == 'query_aangifte_ib' THEN
      // Query uses jaar == target_year only, missing unclosed prior years
      RETURN hasUnclosedPriorYears(input.target_year, closed_years)
    END IF
  END IF

  RETURN FALSE
END FUNCTION
```

### Examples

- **Double-counting in actuals-balance**: Year 2023 is closed (OpeningBalance exists for 2024). Querying `/actuals-balance?years=2025` uses `jaar <= 2025` which includes 2023's raw transactions + 2024's OpeningBalance that already contains 2023's totals. Account 1000 shows €20,000 instead of correct €10,000.
- **Double-counting in make_ledgers**: Year 2023 is closed. Generating XLSX for 2025 computes beginning balance with `jaar < 2025`, which sums 2023 raw data + 2024 OpeningBalance. Beginning balance is inflated.
- **Under-counting in aangifte_ib**: Years 2022-2023 have transactions but are NOT closed (no OpeningBalance exists). Querying aangifte_ib for 2024 uses `jaar == 2024` only, missing €50,000 of accumulated balance sheet history from 2022-2023.
- **Edge case — no closures**: Administration has never closed a year. All paths fall back to `jaar <= target_year` (full cumulation), which is correct because no OpeningBalance records exist.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- P&L accounts (VW='Y') continue to use period-based filtering (date range or single year) regardless of closure state
- Closed year queries (`target_year IN closed_years`) continue to return only that year's data
- Tenant isolation via `administration = %s` exact match remains enforced in all paths
- Cache loading logic (last closed year + open years) remains unchanged
- When `year_closure_status` is empty or unreachable, all paths fall back to cumulative `jaar <= target_year`
- Future year data (e.g., depreciation entries) is never included when `jaar > target_year`

**Scope:**
All inputs that do NOT involve balance sheet (VW='N') cumulation across a closure boundary are unaffected. This includes:

- All P&L queries
- Balance queries where no years are closed
- Balance queries where target year is itself closed
- Mouse/UI interactions, caching, authentication, and export formatting

## Hypothesized Root Cause

Based on the bug description, the most likely issues are:

1. **No closure-aware lower bound in actuals_routes.py**: The `/actuals-balance` endpoint uses `jaar <= target_year` (non-per_year) and `jaar <= year` (per_year open years) without establishing a lower bound at `last_closed_year + 1`. The `_get_closed_years()` helper exists but is only used for the per_year closed/open branch decision, not for bounding the cumulation range.

2. **Overly simplistic model in query_aangifte_ib()**: The function assumes "current year only" is sufficient because OpeningBalance carries forward history. This breaks when the prior year is NOT closed and no OpeningBalance exists — accumulated history is simply lost.

3. **Unbounded `jaar < target_year` in make_ledgers()**: Both implementations (financial_report_generator.py and xlsx_export.py) compute beginning balance by summing ALL years before the target. When a prior year is closed, this includes raw transactions from that year PLUS the OpeningBalance in the following year that summarizes them.

4. **No shared helper**: Each code path independently decides how to handle year ranges. The `_get_opening_balance_date()` pattern in banking_checks.py already does the right thing but is local to that module and returns a date string rather than a reusable year integer.

## Correctness Properties

Property 1: Bug Condition — Closure-Aware Start Year Prevents Double-Counting

_For any_ balance sheet query where at least one prior year is closed (isBugCondition returns true due to double-counting), the fixed function SHALL cumulate transactions starting from `last_closed_year + 1` through the target year, producing totals that count each transaction exactly once by relying on the OpeningBalance record to carry forward prior history.

**Validates: Requirements 2.1, 2.2, 2.4**

Property 2: Bug Condition — Closure-Aware Start Year Prevents Under-Counting

_For any_ balance sheet query where the aangifte_ib path uses only the target year but prior unclosed years have transactions (isBugCondition returns true due to under-counting), the fixed function SHALL cumulate transactions from `last_closed_year + 1` (or from the beginning if no closures exist) through the target year, capturing all accumulated history.

**Validates: Requirements 2.3, 2.5**

Property 3: Preservation — Non-Balance-Sheet and Non-Boundary Queries Unchanged

_For any_ input where the bug condition does NOT hold (P&L queries, queries with no closures, queries where target year is closed), the fixed function SHALL produce the same result as the original function, preserving all existing filtering, grouping, and aggregation behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `backend/src/utils/closure_helpers.py` (NEW)

**Function**: `get_closure_aware_start_year(db, administration)`

**Specific Changes**:

1. **Create shared helper module**: New file `backend/src/utils/closure_helpers.py` with a `get_closure_aware_start_year(db, administration)` function that queries `year_closure_status` for `MAX(year)` and returns `last_closed_year + 1` or `None`. This generalizes the pattern already in `banking_checks._get_opening_balance_date()`.

2. **Fix `/actuals-balance` non-per_year mode** (`backend/src/actuals_routes.py`):
   - After `filtered = filtered[filtered["jaar"] <= max_year]`, add lower-bound filter: `if start_year: filtered = filtered[filtered["jaar"] >= start_year]`
   - Call `get_closure_aware_start_year(db, administration)` once at route level

3. **Fix `/actuals-balance` per_year mode** (`backend/src/actuals_routes.py`):
   - For open years, change `jaar <= year` to `(jaar >= start_year) & (jaar <= year)`
   - Use the same `start_year` computed once at route level

4. **Fix `query_aangifte_ib()`** (`backend/src/mutaties_cache.py`):
   - Accept optional `start_year` parameter (computed by caller using the helper)
   - For VW='N' accounts, change mask from `jaar == year_int` to `(jaar >= start_year) & (jaar <= year_int)`
   - When `start_year` is None, fall back to `jaar <= year_int` (no closures — full cumulation)

5. **Fix `make_ledgers()` in financial_report_generator.py**:
   - Call `get_closure_aware_start_year(db, administration)` at function entry
   - Change balance query from `WHERE ... AND jaar < %s` to `WHERE ... AND jaar >= %s AND jaar < %s`
   - When `start_year` is None, retain original `jaar < %s` behavior

6. **Fix `make_ledgers()` in xlsx_export.py**:
   - Same logic as #5 — add `jaar >= start_year` to the balance query
   - When `start_year` is None, retain original behavior

7. **Handle edge cases in helper**:
   - No closures → return `None` (callers fall back to cumulative)
   - Target year is closed → callers should use `jaar == target_year` (existing logic handles this)

> **Out of scope**: Full recalculation mode (reading all years while excluding OpeningBalance records) is a separate audit/verification feature to be wired into tenant administration as its own deliverable. See future spec: `balance-verification-audit`.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that set up a `year_closure_status` record for a prior year, insert both raw transactions for the closed year AND an OpeningBalance record in the following year, then call each affected code path and assert the totals. Run on UNFIXED code to observe double-counting.

**Test Cases**:

1. **Actuals Balance Double-Count Test**: Insert 2023 closure + OpeningBalance in 2024. Call `/actuals-balance?years=2025`. Assert Account 1000 total includes 2023 raw data twice (will fail = bug confirmed on unfixed code)
2. **Actuals Balance Per-Year Double-Count Test**: Same setup, call with `per_year=true&years=2024,2025`. Assert 2025 open-year balance double-counts (will fail on unfixed code)
3. **Aangifte IB Under-Count Test**: No closures, transactions in 2022-2024. Call `query_aangifte_ib(2024)`. Assert balance accounts miss 2022-2023 history (will fail on unfixed code)
4. **Make Ledgers Double-Count Test**: Insert 2023 closure + OpeningBalance for 2024. Call `make_ledgers(db, 2025, admin)`. Assert beginning balance is inflated (will fail on unfixed code)

**Expected Counterexamples**:

- Account totals are 2x expected when a closed year's raw data is summed with OpeningBalance
- Account totals are missing prior-year history in aangifte_ib when no closure exists

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedFunction(input)
  ASSERT result.account_total == expectedTotal(input)
  // Where expectedTotal sums from last_closed_year+1 through target_year only
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) == fixedFunction(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many test cases automatically across the input domain (various year combinations, administrations, VW types)
- It catches edge cases that manual unit tests might miss (e.g., boundary years, empty result sets)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for P&L queries, closed-year queries, and no-closure administrations, then write property-based tests capturing that behavior.

**Test Cases**:

1. **P&L Preservation**: Verify VW='Y' queries return identical results before and after fix
2. **No-Closure Fallback Preservation**: Verify administrations with no closures return identical results
3. **Closed-Year Single-Year Preservation**: Verify querying a closed year returns `jaar == year` data only
4. **Tenant Isolation Preservation**: Verify administration filtering continues to isolate tenants

### Unit Tests

- Test `get_closure_aware_start_year()` with various closure states (no closures, single closure, multiple closures)
- Test actuals-balance route with mocked cache data and closure states
- Test `query_aangifte_ib()` with both closed and unclosed prior years
- Test `make_ledgers()` beginning balance calculation with closure awareness
- Test edge cases: empty `year_closure_status`, target year is closed, no transactions in start_year

### Property-Based Tests

- Generate random closure configurations and verify `get_closure_aware_start_year()` always returns `MAX(closed) + 1` or None
- Generate random account datasets with OpeningBalance records and verify no double-counting occurs (sum matches expected single-count total)
- Generate random VW='Y' datasets and verify fix produces identical results to original code
- Generate random year ranges without closures and verify fallback to `jaar <= target_year`

### Integration Tests

- Test full `/actuals-balance` API flow with real database containing closure records
- Test XLSX export pipeline end-to-end with closure-aware beginning balances
- Test aangifte_ib flow with various closure states
- Test that the `year_end_service.py` closure process correctly creates OpeningBalance records that the fixed queries then handle correctly
