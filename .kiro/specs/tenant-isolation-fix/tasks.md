# Tasks — Tenant Isolation & Cache Consistency Fix

## Phase 1: Critical Security — `str.startswith()` Replacement (30 min)

This is the highest-risk flaw — exploitable if any tenant name is a prefix of another.

- [x] 1.1 Replace `str.startswith(administration)` with `== administration` in `mutaties_cache.py` (2 locations: lines 483, 532)
- [x] 1.2 Replace `str.startswith(administration)` with `== administration` in `btw_aangifte_generator.py` (3 locations: lines 237, 277, 328)
- [x] 1.3 Replace `str.startswith(administration)` with `== administration` in `btw_processor.py` (3 methods)
- [x] 1.4 Run existing tests to verify no regressions: `pytest tests/unit/test_aangifte_ib_generator.py tests/unit/test_btw_processor.py -v`
- [x] 1.5 Verify with manual query that "GoodwinSolutions" exact match still returns correct data

**Time estimate:** 30 min  
**Dependencies:** None

---

## Phase 2: Frontend — Remove `|| 'all'` Fallback (45 min)

- [x] 2.1 Update `tenantApiService.ts`: Replace `currentTenant || 'all'` with throwing an error when `currentTenant` is null/empty in `tenantAwareGet`
- [x] 2.2 Update `tenantApiService.ts`: Same fix for `tenantAwarePost` — require `currentTenant` before making request
- [x] 2.3 Fix `useBankingState.ts:251`: Add early return guard `if (!tenant) return;` before the fetch call
- [x] 2.4 Fix `MutatiesReport.tsx:119`: Remove `|| 'all'` fallback (component already has a `if (!currentTenant)` guard above)
- [x] 2.5 Search for any other `|| 'all'` patterns in frontend: `grep -r "|| 'all'" frontend/src/ --include="*.ts" --include="*.tsx"`
- [x] 2.6 Run frontend tests: `npm run test -- --run`
- [x] 2.7 Manual test: clear localStorage, verify app shows "select tenant" prompt without making API calls

**Time estimate:** 45 min  
**Dependencies:** None (can run in parallel with Phase 1)

---

## Phase 3: Backend Routes — Fix `'all'` Bypass (1 hour)

- [x] 3.1 Fix `pdf_validation_routes.py` — `/api/pdf/validate-urls-stream`: Either reject `'all'` with 403, or add `user_tenants` IN-clause filtering to the validator query
- [x] 3.2 Fix `pdf_validation_routes.py` — `/api/pdf/validate-urls`: Same fix as 3.1
- [x] 3.3 Fix `aangifte_ib_routes.py` — `/aangifte-ib-export`: Pass `user_tenants` to `query_aangifte_ib_details` calls and ensure the export respects tenant boundaries
- [x] 3.4 Add `user_tenants` parameter to `mutaties_cache.query_aangifte_ib()` — always filter by user's accessible tenants when provided
- [x] 3.5 Update route calls to `query_aangifte_ib()` to pass `user_tenants` parameter
- [x] 3.6 Audit: verify all other routes with `!= "all"` pattern have proper `user_tenants` filtering downstream (actuals_routes, reporting_routes, financial_reporting_routes — already confirmed safe)
- [x] 3.7 Run backend tests: `pytest tests/unit/ tests/api/ -v -k "aangifte or pdf_valid or cache"`

**Time estimate:** 1 hour  
**Dependencies:** Phase 1 (cache changes)

---

## Phase 4: Cache Consistency — Atomic Reference Swapping (1.5 hours)

- [x] 4.1 Update `MutatiesCache` class docstring to document thread-safety model
- [x] 4.2 Add `get_snapshot(db_manager)` method that returns the current `self.data` reference (for request-scoped usage)
- [x] 4.3 Refactor `_refresh()` — already uses atomic assignment `self.data = pd.read_sql(...)` (verified, no change needed)
- [x] 4.4 Refactor `_ensure_years_loaded()` — already uses atomic `self.data = pd.concat(...)` (verified, no change needed)
- [x] 4.5 Remove unnecessary `self.data.copy()` calls in query methods — replaced with direct reference read since filtering creates new DataFrames
- [x] 4.6 Update `query_aangifte_ib()` and `query_aangifte_ib_details()` to accept optional `snapshot` parameter
- [x] 4.7 Update `aangifte_ib_routes.py` export endpoint to use snapshot for consistent summary+details
- [x] 4.8 Run focused tests: `pytest tests/unit/test_mutaties_cache.py tests/unit/test_aangifte_ib_generator.py`

**Time estimate:** 1.5 hours  
**Dependencies:** Phase 3 (cache method signature changes)

---

## Phase 5: Verification & Documentation (30 min)

- [ ] 5.1 Run full backend test suite:
- [ ] 5.2 Run full frontend test suite:
- [x] 5.3 Manual integration test: open Aangifte IB, verify summary matches detail totals
- [x] 5.4 Manual security test: verify that with tenant "GoodwinSolutions" selected, no data from "PeterPrive" or "kimgeers" leaks through
- [ ] 5.5 ~~Update `gitBug.md` with resolution notes~~ (file will be removed)
- [x] 5.6 Clean up debug scripts: remove `backend/scripts/debug_liquide*.py` (already done)

**Time estimate:** 30 min  
**Dependencies:** All previous phases

---

## Summary

| Phase | Focus                      | Time      | Priority |
| ----- | -------------------------- | --------- | -------- |
| 1     | `startswith` → exact match | 30 min    | CRITICAL |
| 2     | Frontend `'all'` removal   | 45 min    | HIGH     |
| 3     | Backend route fixes        | 1 hour    | HIGH     |
| 4     | Cache atomic swaps         | 1.5 hours | MEDIUM   |
| 5     | Verification               | 30 min    | —        |

**Total estimated time: ~4.5 hours**
