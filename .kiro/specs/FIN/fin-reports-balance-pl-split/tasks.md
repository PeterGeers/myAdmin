# Implementation Plan: fin-reports-balance-pl-split

Status: In Progress

## Overview

Split the monolithic `ActualsReport.tsx` (814 lines) into dedicated `BalanceReport.tsx` and `ProfitLossReport.tsx` components, each rendered as a separate tab in `FinancialReportsGroup`. Backend changes add `per_year` and `includeRef` query params to existing endpoints in `backend/src/actuals_routes.py`, relax cache invalidation permissions in `backend/src/routes/cache_routes.py`, and the frontend fixes the Update Data button to actually call `POST /api/cache/invalidate` before re-fetching. Both new pages adopt responsive grid layout and the P&L page gains reference number expansion, pivot view, and split profit/loss charts.

## Phase 1: Backend API Changes (2–3 days)

- [x] 1. Backend: Add `per_year` param to actuals-balance endpoint
  - [x] 1.1 Modify `get_actuals_balance()` in `backend/src/actuals_routes.py` to accept `per_year=true` query param
    - When `per_year=true`:
      - Group by `(Parent, Reknum, AccountName, jaar)` instead of the current `(Parent, Reknum, AccountName)` sum across all years
      - Query `year_closure_status` table (via `db.execute_query`) to build `closedYears` array for the tenant's administration
      - For closed years: filter DataFrame to only that year's transactions (`df['jaar'] == year`), excluding opening balance transactions from prior years
      - For open years: cumulative from start through that year (`df['jaar'] <= year`)
      - Include `closedYears` integer array in JSON response alongside `data`
    - When `per_year` is absent or false: preserve existing behavior (backward compatible — current groupby without `jaar`)
    - The cache DataFrame already contains `jaar`, `Parent`, `Reknum`, `AccountName`, `Amount` columns from `vw_mutaties`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x]\* 1.2 Write pytest tests for `per_year=true` balance logic
    - Created `backend/tests/api/test_actuals_balance_per_year.py` (7 tests, all passing)
    - Tests: year-bucketed grouping, closedYears populated, closed year excludes prior, open year cumulative, backward compat, excludes P&L, filters zero amounts
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 2. Backend: Add `includeRef` param to actuals-profitloss endpoint
  - [x] 2.1 Modify `get_actuals_profitloss()` in `backend/src/actuals_routes.py` to accept `includeRef=true` query param
    - When `includeRef=true`: add `ReferenceNumber` to the `group_cols` list so individual transactions are returned (the column already exists in the cache DataFrame from `vw_mutaties`)
    - When absent or false: preserve existing grouped behavior (no `ReferenceNumber` in groupby)
    - _Requirements: 3.2_

  - [x]\* 2.2 Write pytest tests for `includeRef=true` profitloss logic
    - Created `backend/tests/api/test_actuals_profitloss_ref.py` (2 tests, all passing)
    - Tests: includeRef returns ReferenceNumber rows, without includeRef is grouped
    - _Requirements: 3.2_

- [x] 3. Backend: Relax cache invalidation permission
  - [x] 3.1 Change `POST /api/cache/invalidate` in `backend/src/routes/cache_routes.py` (line ~116)
    - Replaced `@cognito_required(required_roles=['SysAdmin'])` with `@cognito_required(required_permissions=['actuals_read'])`
    - Kept `@tenant_required(allow_sysadmin=True)` decorator as-is
    - This allows users with `Finance_CRUD` or `Finance_Read` roles (which grant `actuals_read` permission) to invalidate the cache
    - _Requirements: 7.1, 7.2_

  - [ ]\* 3.2 Write pytest test for cache invalidation permission change
    - Add to `backend/tests/api/` (e.g., `test_cache_invalidation_permission.py`)
    - Test that a user with `actuals_read` permission can call `POST /api/cache/invalidate` successfully
    - Test that an unauthenticated user is still rejected (401/403)
    - Test that a user without `actuals_read` permission is rejected (403)
    - _Requirements: 7.1_

- [x] 4. Checkpoint — Backend tests pass
  - All 9 new tests pass (7 balance per_year + 2 profitloss includeRef)
  - Existing tests unaffected (pre-existing failures in `test_actuals_routes_tenant.py` are auth-mocking issues, not regressions)

## Phase 2: Frontend Shared Types and Utilities (1–2 days)

- [x] 5. Frontend: Extract shared types and utilities
  - [x] 5.1 Create `frontend/src/types/financialReports.ts` with shared interfaces
    - `SharedFilterState { selectedYears: string[]; displayFormat: '2dec' | '0dec' | 'k' | 'm'; availableYears: string[] }`
    - `BalanceReportProps { selectedYears, displayFormat, availableYears, onYearsChange, onDisplayFormatChange }`
    - `ProfitLossReportProps { selectedYears, displayFormat, availableYears, onYearsChange, onDisplayFormatChange }`
    - `BalanceYearRecord { Parent: string; Reknum: string; AccountName: string; jaar: number; Amount: number }`
    - `PLRecord { Parent: string; Reknum: string; AccountName: string; jaar: number; kwartaal?: number; maand?: number; Amount: number; ReferenceNumber?: string }`
    - Note: existing types directory is at `frontend/src/types/` (contains `chartOfAccounts.ts`)
    - _Requirements: 1.6_

  - [x] 5.2 Create `frontend/src/utils/financialReportUtils.ts` with shared helper functions
    - `formatAmount(amount: number, format: string): string` — extract from `ActualsReport.tsx` (lines ~68–82), handles '2dec', '0dec', 'k', 'm' formats with `€` prefix and `nl-NL` locale
    - `invalidateAndFetch(fetchFn: () => Promise<void>): Promise<void>` — calls `authenticatedPost('/api/cache/invalidate', {})` from `apiService.ts`, then calls `fetchFn()`
    - `generateColumnKeys(years: string[], drillDownLevel: 'year' | 'quarter' | 'month'): string[]` — extract column key generation logic from `ActualsReport.tsx` `getColumnKeys()` (lines ~87–96)
    - `filterByVW(data: any[], vwFlag: 'N' | 'Y'): any[]` — filter records by VW flag
    - `splitChartData(data: PLRecord[], profitPrefix: string, lossPrefix: string): { profit: PLRecord[]; loss: PLRecord[] }` — splits P&L records into profit (Parent starts with "8") and loss (Parent starts with "4") sets
    - _Requirements: 7.1, 7.2, 3.4, 5.1_

  - [ ]\* 5.3 Write property tests (fast-check) for utility functions in `frontend/src/__tests__/financialReportUtils.property.test.ts`
    - [ ]\* 5.3.1 Property 1: VW flag filtering preserves only matching records
    - [ ]\* 5.3.2 Property 4: Drill-down column key generation
    - [ ]\* 5.3.3 Property 5: Chart data split partitions by Parent prefix

## Phase 3: BalanceReport Component (2–3 days)

- [x] 6. Frontend: Create BalanceReport component
  - [x] 6.1 Create `frontend/src/components/reports/BalanceReport.tsx`
  - [ ]\* 6.2 Write property test for closure-aware balance calculation
  - [ ]\* 6.3 Write property test for grand total equals sum of column values
  - [x] 6.4 Write unit tests for BalanceReport

## Phase 4: ProfitLossReport Component (3–4 days)

- [x] 7. Frontend: Create ProfitLossReport component
  - [x] 7.1 Create `frontend/src/components/reports/ProfitLossReport.tsx`
  - [x] 7.2 Add pivot view toggle to ProfitLossReport
  - [x] 7.3 Add split profit/loss bar charts to ProfitLossReport
  - [x] 7.4 Write unit tests for ProfitLossReport
- [x] 8. Checkpoint — Frontend component tests pass

## Phase 5: Tab Wiring and Integration (1–2 days)

- [x] 9. Frontend: Modify FinancialReportsGroup to wire new tabs
  - [x] 9.1 Update `frontend/src/components/reports/FinancialReportsGroup.tsx`
  - [ ]\* 9.2 Write unit tests for updated FinancialReportsGroup

## Phase 6: Responsive Layout and Cleanup (1 day)

- [x] 10. Responsive layout verification
- [x] 10.1 Update language for new tabs
- [x] 11. Checkpoint — All tests pass
- [x] 12. Cleanup and final wiring
  - [x] 12.1 Remove `ActualsReport.tsx`
  - [x] 12.2 Write integration tests for cache invalidation flow
- [x] 13. Final checkpoint — Full test suite passes

## Summary

| Phase                  | Tasks | Estimated Days | Key Deliverables                                                    |
| ---------------------- | ----- | -------------- | ------------------------------------------------------------------- |
| 1 — Backend API        | 1–4   | 2–3            | ✅ `per_year` param, `includeRef` param, cache permission fix       |
| 2 — Shared Types/Utils | 5     | 1–2            | `financialReports.ts` types, `financialReportUtils.ts` helpers      |
| 3 — BalanceReport      | 6     | 2–3            | `BalanceReport.tsx` with year-columns, closure awareness, pie chart |
| 4 — ProfitLossReport   | 7–8   | 3–4            | `ProfitLossReport.tsx` with ref expansion, pivot view, split charts |
| 5 — Tab Wiring         | 9     | 1–2            | Updated `FinancialReportsGroup.tsx` with shared state               |
| 6 — Cleanup            | 10–13 | 1              | Remove `ActualsReport.tsx`, responsive verification                 |
| **Total**              |       | **10–15**      |                                                                     |

## Notes

- Tasks marked with `*` are test tasks — recommended but can be deferred for faster MVP
- Each task references specific requirements from `requirements.md` for traceability
- Checkpoints (tasks 4, 8, 11, 13) ensure incremental validation
- Property tests validate the 5 correctness properties defined in `design.md`
- The `vw_mutaties` cache DataFrame already contains all needed columns: `VW`, `jaar`, `kwartaal`, `maand`, `Parent`, `Reknum`, `AccountName`, `ReferenceNumber`, `Amount`, `administration`
- The `POST /api/cache/invalidate` endpoint previously required `SysAdmin` role — changed to `actuals_read` permission to fix the "Update Data doesn't refresh" bug
- The pivot view is a client-side transformation of the same P&L data — no additional API call needed
