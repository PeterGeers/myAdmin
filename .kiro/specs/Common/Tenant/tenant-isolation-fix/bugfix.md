# Bugfix Requirements Document

## Introduction

Critical tenant isolation security flaws and a cache data consistency bug exist in myAdmin.

**Security flaws (3 categories):** (1) the frontend falls back to `'all'` when no tenant is selected, sending unscoped requests to the backend; (2) backend routes use a `!= "all"` check that skips ownership validation, with some routes missing `user_tenants` filtering entirely; (3) cache/service layer uses `str.startswith()` for tenant filtering, causing prefix-matching data leaks between tenants with similar names (e.g., "Peter" matches "PeterPrive").

**Data consistency bug:** The in-memory cache (`mutaties_cache.py`) can serve inconsistent data between the summary and detail API calls due to concurrent cache mutations, TTL-triggered reloads mid-session, and lack of snapshot isolation. This was observed as the Aangifte IB report showing "Liquide middelen €97.151,18" in the summary but only €88.262,80 in the account detail breakdown (which turned out to be year 2025 data from a stale/intermediate cache state).

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN no tenant is selected in localStorage THEN the frontend sends `administration: 'all'` to API calls via `tenantApiService.ts`, `useBankingState.ts`, and `MutatiesReport.tsx`, bypassing tenant scoping entirely

1.2 WHEN the backend receives `administration = "all"` on `/api/pdf/validate-urls-stream` or `/api/pdf/validate-urls` THEN the system skips the tenant ownership check and processes data across all tenants without any `user_tenants` filtering

1.3 WHEN the backend receives `administration = "all"` on `/aangifte-ib-export` THEN the system passes the unfiltered administration value to the cache layer without applying a `user_tenants` filter on the returned data

1.4 WHEN a tenant name is a prefix of another tenant name (e.g., "Peter" and "PeterPrive") THEN the system's `str.startswith(administration)` filtering in `mutaties_cache.py`, `btw_aangifte_generator.py`, and `btw_processor.py` returns data belonging to both tenants, leaking data across tenant boundaries

### Expected Behavior (Correct)

2.1 WHEN no tenant is selected in localStorage THEN the frontend SHALL throw an error or block the request, preventing any API call from being made without an explicit tenant context

2.2 WHEN the backend receives `administration = "all"` or any value not in the user's `user_tenants` list on `/api/pdf/validate-urls-stream` or `/api/pdf/validate-urls` THEN the system SHALL reject the request with a 403 Access Denied response

2.3 WHEN the backend receives `administration = "all"` on `/aangifte-ib-export` THEN the system SHALL either reject the request or enforce `user_tenants` filtering on all data returned from the cache

2.4 WHEN filtering data by tenant in the cache/service layer THEN the system SHALL use exact string equality (`== administration`) instead of prefix matching (`str.startswith()`), ensuring "Peter" matches only "Peter" and not "PeterPrive"

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a valid tenant is selected in localStorage THEN the frontend SHALL CONTINUE TO send that tenant value in the `administration` parameter of all API calls

3.2 WHEN a user requests data for a specific tenant that exists in their `user_tenants` list THEN the backend SHALL CONTINUE TO return the scoped data for that tenant

3.3 WHEN routes already have proper `user_tenants` filtering after the `!= "all"` check (e.g., `/actuals-balance`, `/actuals-profitloss`, `/mutaties-table`, `/balance-data`, `/reference-analysis`) THEN those routes SHALL CONTINUE TO function correctly for valid tenant requests

3.4 WHEN a tenant name is unique and not a prefix of any other tenant THEN the cache/service layer SHALL CONTINUE TO return the correct data for that tenant after switching to exact match filtering

---

## Bug Analysis — Cache Data Consistency

### Root Cause

The `MutatiesCache` is a global singleton holding ALL tenants' data in a pandas DataFrame (`self.data`). Multiple request threads read from and mutate this DataFrame concurrently. The 30-minute TTL means the cache can reload mid-session, and operations like `_ensure_years_loaded()` append data via `pd.concat()` while other threads are reading.

### Observed Symptom

User opens Aangifte IB report → summary shows "Liquide middelen = €97.151,18" (correct, year 2026). User clicks to expand → detail shows accounts summing to €88.262,80 (incorrect — these are year 2025 values: €6.972,69 + €24.971,44 + €56.318,67). The discrepancy of €8.888,38 corresponds exactly to new 2026 transactions that were either not yet loaded or lost during a concurrent cache mutation.

### Current Behavior (Defect)

4.1 WHEN the cache TTL (30 minutes) expires between the summary API call and the detail API call THEN the detail call triggers a full cache reload from the database, potentially returning data from a different point in time than the summary

4.2 WHEN `_ensure_years_loaded()` is called by one request thread while another thread executes `self.data.copy()` THEN the copy may capture an intermediate state where `pd.concat()` has partially completed, resulting in incomplete or duplicated data

4.3 WHEN `invalidate_cache()` is called (e.g., after a banking import by another user/tab) between the summary and detail calls THEN the detail call serves from a fresh reload while the summary was served from the previous cache state

4.4 WHEN `self.data` is reassigned by `_refresh()` on one thread while another thread has passed the `_needs_refresh()` check but not yet called `.copy()` THEN the reading thread gets a reference to the new (possibly still-loading) DataFrame

### Expected Behavior (Correct)

5.1 WHEN a user requests report data THEN the summary and detail endpoints SHALL use the same consistent snapshot of cached data, regardless of cache refreshes or concurrent mutations happening between the two calls

5.2 WHEN the cache TTL expires and a refresh is triggered THEN in-flight requests that started before the refresh SHALL complete using the pre-refresh data, not a mix of old and new

5.3 WHEN `_ensure_years_loaded()` appends new data THEN concurrent readers SHALL NOT observe partial/intermediate states of the DataFrame

5.4 WHEN `invalidate_cache()` is called THEN the system SHALL either (a) complete all in-flight requests with the current data before invalidating, or (b) ensure the next load is atomic and consistent

### Unchanged Behavior (Regression Prevention)

6.1 WHEN the cache is refreshed THEN subsequent requests SHALL see the new data (the fix must not prevent cache updates from being visible)

6.2 WHEN multiple years are requested and some are not in cache THEN the system SHALL CONTINUE TO load them on demand

6.3 WHEN the cache TTL has not expired and no invalidation has occurred THEN requests SHALL CONTINUE TO be served from the in-memory cache without database access

### Reproduction Steps

1. Ensure backend is running with the mutaties_cache (TTL = 30 minutes)
2. Open Aangifte IB report for year 2026, note "Liquide middelen" amount
3. Wait for cache to expire (30 min) OR trigger `invalidate_cache()` via banking import
4. Click to expand "Liquide middelen" detail accounts
5. Observe that account amounts may sum to a different total than the summary row

### Affected Files

**Cache layer:**

- `backend/src/mutaties_cache.py` — `get_data()`, `_refresh()`, `_ensure_years_loaded()`, `query_aangifte_ib()`, `query_aangifte_ib_details()`

**Routes that call cache:**

- `backend/src/routes/aangifte_ib_routes.py` — separate HTTP requests for summary vs detail
- `backend/src/routes/financial_reporting_routes.py`
- `backend/src/actuals_routes.py`

### Proposed Fix Approach

**Option A: Snapshot-based reads (recommended)**

- On each request, capture `cache_snapshot = self.data` (reference, not copy) at the start
- Pass this snapshot to all query methods called within that request
- `_refresh()` and `_ensure_years_loaded()` assign a NEW DataFrame to `self.data` atomically (Python's GIL ensures reference assignment is atomic)
- Readers holding the old reference continue to use consistent old data

**Option B: Version stamping**

- Add a `cache_version` counter incremented on every refresh
- Return `cache_version` with summary data
- Detail call sends `cache_version`; if mismatch, force client to refetch summary

**Option C: Request-scoped cache token**

- Frontend requests both summary and details in a single batch API call
- Backend serves both from the same DataFrame snapshot
