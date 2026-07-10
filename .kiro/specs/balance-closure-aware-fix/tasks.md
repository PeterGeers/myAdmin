# Implementation Plan

## Overview

This task list implements the closure-aware fix for balance sheet accounts (VW='N') being double-counted or under-counted because year filtering doesn't account for fiscal year closure state. The fix introduces a shared `get_closure_aware_start_year()` helper and applies it consistently in all four affected code paths.

**Methodology**: Bug condition exploration → Preservation tests → Implementation → Validation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2"] },
    { "id": 1, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7"] },
    { "id": 2, "tasks": ["3.8", "3.9"] },
    { "id": 3, "tasks": ["4", "5"] },
    { "id": 4, "tasks": ["6"] }
  ]
}
```

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Closure-Aware Double-Counting and Under-Counting
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate double-counting (actuals_routes, make_ledgers) and under-counting (aangifte_ib)
  - **Scoped PBT Approach**: Scope the property to concrete failing cases:
    - Case 1: Year 2023 closed, OpeningBalance in 2024, query target_year=2025 via actuals-balance (non-per_year). Assert account total equals single-count (not 2x).
    - Case 2: Year 2023 closed, OpeningBalance in 2024, query per_year=true for year 2025. Assert open-year balance is single-count.
    - Case 3: No closures, transactions in 2022-2024, query_aangifte_ib(2024) for VW='N'. Assert balance includes 2022-2023 accumulated history.
    - Case 4: Year 2023 closed, OpeningBalance in 2024, make_ledgers for 2025. Assert beginning balance is single-count.
  - Test file: `backend/tests/unit/test_closure_aware_bug_condition.py`
  - Setup: Insert year_closure_status record, raw transactions for closed year, OpeningBalance record in following year
  - Assertions match Expected Behavior from design: cumulation starts at `last_closed_year + 1`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct — it proves the bug exists)
  - Document counterexamples found (e.g., "actuals-balance returns €20,000 instead of €10,000 due to double-counting")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Balance-Sheet and Non-Boundary Queries Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **GOAL**: Capture existing correct behavior for inputs where the bug condition does NOT hold
  - Observe on UNFIXED code:
    - P&L queries (VW='Y') return period-based results regardless of closure state
    - Administrations with no closures return cumulative `jaar <= target_year` results
    - Querying a closed year returns `jaar == target_year` data only
    - Tenant isolation (`administration = %s`) filters correctly
    - Fallback behavior when `year_closure_status` table is empty
  - Write property-based tests (using hypothesis):
    - Property: For all VW='Y' queries, result is unchanged by closure state (date-range filtering only)
    - Property: For all administrations with no closures, balance queries return `jaar <= target_year` cumulation
    - Property: For all queries where target_year is closed, result equals `jaar == target_year` data only
    - Property: For all queries, tenant isolation is enforced (no cross-tenant data leakage)
  - Test file: `backend/tests/unit/test_closure_aware_preservation.py`
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Implement closure-aware fix
  - [x] 3.1 Create shared helper module `backend/src/utils/closure_helpers.py`
    - Implement `get_closure_aware_start_year(db, administration)` function
    - Query `year_closure_status` for `MAX(year) WHERE administration = %s`
    - Return `last_closed_year + 1` when closures exist, `None` when no closures
    - Handle edge cases: empty table, unreachable table (return None as safe fallback)
    - Add docstring explaining the closure-aware cumulation pattern
    - _Bug_Condition: isBugCondition(input) where query includes both closed year raw data AND OpeningBalance_
    - _Expected_Behavior: get_closure_aware_start_year returns last_closed_year + 1 or None_
    - _Preservation: When no closures exist, returns None so callers fall back to jaar <= target_year_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.2 Fix `/actuals-balance` non-per_year mode in `backend/src/actuals_routes.py`
    - Import `get_closure_aware_start_year` from closure_helpers
    - Call helper once at route level to get `start_year`
    - After `filtered = filtered[filtered["jaar"] <= max_year]`, add: `if start_year: filtered = filtered[filtered["jaar"] >= start_year]`
    - Only apply lower bound for VW='N' (balance sheet) accounts
    - _Bug_Condition: isBugCondition where code_path == 'actuals_balance_total' and target_year > last_closed_year_
    - _Expected_Behavior: Filter with jaar >= start_year AND jaar <= max_year_
    - _Preservation: VW='Y' queries and no-closure administrations unchanged_
    - _Requirements: 1.2, 2.2, 2.5, 3.1_

  - [x] 3.3 Fix `/actuals-balance` per_year mode in `backend/src/actuals_routes.py`
    - For open years, change `jaar <= year` to `(jaar >= start_year) & (jaar <= year)`
    - Use the same `start_year` computed once at route level
    - Only apply lower bound for VW='N' accounts
    - _Bug_Condition: isBugCondition where code_path == 'actuals_balance_per_year' and target_year > last_closed_year_
    - _Expected_Behavior: Filter with jaar >= start_year AND jaar <= year for open years_
    - _Preservation: Closed year branch continues to return jaar == year data_
    - _Requirements: 1.1, 2.1, 2.6, 3.2_

  - [x] 3.4 Fix `query_aangifte_ib()` in `backend/src/mutaties_cache.py`
    - Accept optional `start_year` parameter (computed by caller using the helper)
    - For VW='N' accounts, change mask from `jaar == year_int` to `(jaar >= start_year) & (jaar <= year_int)`
    - When `start_year` is None, fall back to `jaar <= year_int` (no closures — full cumulation)
    - Update caller to pass `start_year` from `get_closure_aware_start_year()`
    - _Bug_Condition: isBugCondition where code_path == 'query_aangifte_ib' and hasUnclosedPriorYears_
    - _Expected_Behavior: Cumulate from start_year through target_year for balance sheet accounts_
    - _Preservation: VW='Y' accounts continue period-based filtering_
    - _Requirements: 1.3, 2.3, 2.5, 3.1_

  - [x] 3.5 Fix `make_ledgers()` in `backend/src/report_generators/financial_report_generator.py`
    - Import and call `get_closure_aware_start_year(db, administration)` at function entry
    - Change balance query from `WHERE ... AND jaar < %s` to `WHERE ... AND jaar >= %s AND jaar < %s`
    - When `start_year` is None, retain original `jaar < %s` behavior (no closures fallback)
    - _Bug_Condition: isBugCondition where code_path == 'make_ledgers_financial' and target_year > last_closed_year_
    - _Expected_Behavior: Beginning balance uses jaar >= start_year AND jaar < target_year_
    - _Preservation: No-closure administrations retain original jaar < target_year behavior_
    - _Requirements: 1.4, 2.4, 2.5_

  - [x] 3.6 Fix `make_ledgers()` in `backend/src/xlsx_export.py`
    - Same logic as 3.5 — add `jaar >= start_year` to the balance query
    - When `start_year` is None, retain original behavior
    - _Bug_Condition: isBugCondition where code_path == 'make_ledgers_xlsx' and target_year > last_closed_year_
    - _Expected_Behavior: Beginning balance uses jaar >= start_year AND jaar < target_year_
    - _Preservation: No-closure administrations retain original jaar < target_year behavior_
    - _Requirements: 1.4, 2.4, 2.5_

  - [x] 3.7 Handle edge cases in helper and callers
    - Target year is closed → callers use `jaar == target_year` (existing logic, verify it still works)
    - Future year data excluded → verify `jaar <= target_year` upper bound is preserved
    - _Requirements: 2.6, 2.7_

  - [x] 3.8 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Closure-Aware Start Year Prevents Double-Counting and Under-Counting
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_closure_aware_bug_condition.py -v`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.9 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Balance-Sheet and Non-Boundary Queries Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_closure_aware_preservation.py -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all preservation tests still pass after fix (no regressions introduced)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Write unit tests for the shared helper
  - Test file: `backend/tests/unit/test_closure_helpers.py`
  - Test `get_closure_aware_start_year()` with:
    - No closures (empty year_closure_status) → returns None
    - Single closure (year 2023 closed) → returns 2024
    - Multiple closures (years 2021, 2022, 2023 closed) → returns 2024 (MAX + 1)
    - Database error/unreachable → returns None (safe fallback)
  - Test edge cases:
    - Target year equals last closed year (caller handles this separately)
    - Only very old years closed (e.g., 2018) with large gap to target
  - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_closure_helpers.py -v`
  - _Requirements: 2.5, 3.5_

- [x] 5. Write integration tests
  - Test file: `backend/tests/integration/test_closure_aware_integration.py`
  - Test full `/actuals-balance` API flow with real database containing closure records
  - Test XLSX export pipeline end-to-end with closure-aware beginning balances
  - Test aangifte_ib flow with various closure states
  - Test that year_end_service closure process creates OpeningBalance records the fixed queries handle correctly
  - Test cross-path consistency: all four code paths produce same balance for same account/year/closure state
  - Run: `cd backend && source .venv/bin/activate && pytest tests/integration/test_closure_aware_integration.py -v`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [ ] 6. Checkpoint — Ensure all tests pass
  - Run full test suite: `cd backend && source .venv/bin/activate && pytest tests/unit/test_closure_aware_bug_condition.py tests/unit/test_closure_aware_preservation.py tests/unit/test_closure_helpers.py tests/integration/test_closure_aware_integration.py -v`
  - Verify: bug condition test passes (bug is fixed)
  - Verify: preservation tests pass (no regressions)
  - Verify: unit tests for helper pass
  - Verify: integration tests pass
  - Ensure no existing tests are broken: `pytest tests/ -v --tb=short`
  - Ask the user if questions arise

## Notes

- The helper generalizes the pattern already in `banking_checks._get_opening_balance_date()` but returns a year integer instead of a date string
- All four code paths must be fixed together to maintain consistency across reporting views
- The exploration test (task 1) intentionally fails on unfixed code — this is expected and confirms the bug exists
- Preservation tests (task 2) must pass on unfixed code — they capture existing correct behavior
- After implementation (task 3), both exploration and preservation tests must pass
