# Tenant Isolation Fix — Bugfix Design

## Overview

This design addresses four related tenant isolation flaws in myAdmin that together allow cross-tenant data leakage. Three are security vulnerabilities (frontend `'all'` fallback, backend bypass on unprotected routes, prefix-matching in cache filtering) and one is a data consistency bug (concurrent cache mutations causing inconsistent reads between summary and detail API calls).

The fix strategy is minimal and targeted:

1. **Frontend**: Replace `|| 'all'` fallbacks with error-throwing guards
2. **Backend**: Reject `'all'` as administration value; enforce `user_tenants` on all routes
3. **Cache filtering**: Switch from `str.startswith()` to exact `==` equality
4. **Cache consistency**: Implement snapshot-based reads (Option A) so all queries within a request operate on the same DataFrame reference

## Glossary

- **Bug_Condition (C)**: The set of inputs/states that trigger cross-tenant data leakage or inconsistent reads
- **Property (P)**: Correct behavior — strict tenant isolation with exact-match filtering and snapshot-consistent reads
- **Preservation**: Existing valid-tenant behavior that must remain unchanged after the fix
- **`tenantAwareGet`**: Frontend function in `tenantApiService.ts` that appends `administration` to API requests
- **`MutatiesCache`**: Global singleton in `mutaties_cache.py` holding all tenants' data in a pandas DataFrame
- **`user_tenants`**: Server-side list of tenant names the authenticated user is authorized to access (from JWT/Cognito)
- **Snapshot**: A captured reference to `self.data` at the start of a request, providing read consistency

## Bug Details

### Bug Condition

The bug manifests across four vectors: (1) the frontend sends `administration: 'all'` when no tenant is selected, (2) backend routes pass `'all'` through to the cache without filtering, (3) the cache uses prefix matching that leaks data between tenants with overlapping name prefixes, and (4) concurrent cache mutations cause mid-request data inconsistency.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type {source: 'frontend' | 'backend' | 'cache_filter' | 'cache_consistency', request: Request}
  OUTPUT: boolean

  // Vector 1: Frontend sends 'all'
  IF input.source == 'frontend'
    RETURN input.request.administration == 'all'
         OR input.request.administration == null
         OR input.request.administration == ''

  // Vector 2: Backend allows 'all' through
  IF input.source == 'backend'
    RETURN input.request.administration == 'all'
         AND route NOT IN routes_with_proper_user_tenants_filtering

  // Vector 3: Prefix matching causes cross-tenant leak
  IF input.source == 'cache_filter'
    RETURN EXISTS tenant_b IN all_tenants
           WHERE tenant_b != input.request.administration
           AND tenant_b.startswith(input.request.administration)

  // Vector 4: Cache mutation between summary and detail calls
  IF input.source == 'cache_consistency'
    RETURN cache_was_mutated_between(summary_call, detail_call)

END FUNCTION
```

### Examples

- **Vector 1**: User opens app without selecting a tenant → `localStorage.getItem('selectedTenant')` returns `null` → `tenantAwareGet` sends `administration: 'all'` → backend returns all data
- **Vector 2**: User sends `GET /api/pdf/validate-urls?administration=all` → route checks `administration != "all"` but still allows `'all'` through the condition `if administration != "all" and administration not in user_tenants` → skips the 403, processes all tenants
- **Vector 3**: Tenant "Peter" queries data → `df["administration"].str.startswith("Peter")` → returns rows for both "Peter" AND "PeterPrive"
- **Vector 4**: User requests Aangifte IB summary (cache state v1) → cache TTL expires → user expands detail (cache state v2 after reload) → summary shows €97,151.18, detail shows €88,262.80

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Valid tenant requests (tenant in `user_tenants`) continue to return correctly scoped data
- Routes with existing proper `user_tenants` filtering (`/actuals-balance`, `/actuals-profitloss`, `/mutaties-table`, `/balance-data`, `/reference-analysis`) continue to work
- Mouse/keyboard interactions, UI rendering, and non-API frontend behavior remain unchanged
- Cache refreshes still propagate to subsequent requests (new snapshots see new data)
- On-demand year loading continues to work
- Cache invalidation continues to work for subsequent requests

**Scope:**
All inputs where a valid, authorized tenant is explicitly provided should be completely unaffected by this fix. This includes:

- Normal API requests with a valid `administration` parameter
- Requests from users with single-tenant access
- Requests from users with multi-tenant access using a specific tenant
- Cache reads that happen between refreshes (no mutation window)

## Hypothesized Root Cause

Based on the bug analysis, the root causes are:

1. **Frontend `|| 'all'` pattern**: The `tenantAwareGet` function uses `currentTenant || 'all'` as a fallback, and `useBankingState.fetchMutaties` uses `tenant || 'all'`. This was likely a development convenience that was never hardened for production multi-tenant use.

2. **Backend conditional bypass**: The `pdf_validation_routes.py` checks `if administration != "all" and administration not in user_tenants` — this means when `administration == "all"`, the condition is `False` and the 403 is skipped. The `aangifte-ib-export` route checks `if administration != "all" and administration not in user_tenants` with the same bypass logic.

3. **Historical prefix matching**: The `str.startswith(administration)` pattern was likely introduced when tenant names were guaranteed unique and non-overlapping. Adding "PeterPrive" as a tenant broke this assumption.

4. **Singleton cache without snapshot isolation**: `MutatiesCache` uses `self.data = pd.concat(...)` and `self.data = pd.read_sql(...)` which reassign the reference. Without snapshot capture, concurrent readers can observe mid-mutation states or different data versions within a single logical request.

## Correctness Properties

Property 1: Bug Condition — No `'all'` Administration Reaches Data Layer

_For any_ API request where `administration == 'all'` or is empty/null, the system SHALL either reject the request with a 403 error (backend) or prevent the request from being sent (frontend), ensuring no unscoped query reaches the data layer.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Bug Condition — Exact Match Tenant Filtering

_For any_ cache/service query filtering by administration, the system SHALL use exact string equality (`== administration`) such that tenant "Peter" matches ONLY rows where `administration == "Peter"` and NOT rows where `administration == "PeterPrive"`.

**Validates: Requirements 2.4**

Property 3: Bug Condition — Snapshot Consistency

_For any_ request that calls multiple cache query methods (e.g., summary + details), all query methods within that request SHALL operate on the same DataFrame reference (snapshot), ensuring consistent data regardless of concurrent cache mutations.

**Validates: Requirements 5.1, 5.2, 5.3**

Property 4: Preservation — Valid Tenant Requests Unchanged

_For any_ request where a valid tenant is provided (tenant ∈ `user_tenants` AND tenant ≠ `'all'`), the system SHALL return exactly the same data as before the fix, preserving all existing functionality for authorized single-tenant requests.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 6.1, 6.2, 6.3**

## Fix Implementation

### Changes Required

**File**: `frontend/src/services/tenantApiService.ts`

**Function**: `tenantAwareGet`

**Specific Changes**:

1. **Remove `|| 'all'` fallback**: Replace `administration: currentTenant || 'all'` with a guard that throws an error if `currentTenant` is null/empty
2. **Use `requireTenant()`**: The file already has this utility — use it in `tenantAwareGet` and `tenantAwarePost`

---

**File**: `frontend/src/hooks/useBankingState.ts`

**Function**: `fetchMutaties`

**Specific Changes**:

1. **Remove `|| 'all'` fallback**: Replace `administration: tenant || 'all'` with early return if tenant is null
2. **Guard pattern**: `if (!tenant) return;` before making the API call

---

**File**: `frontend/src/components/reports/MutatiesReport.tsx`

**Function**: `fetchMutatiesData`

**Specific Changes**:

1. **Remove `|| 'all'` fallback**: Replace `administration: currentTenant || 'all'` with the existing `if (!currentTenant) return` guard that already exists in the function (ensure it exits before reaching the params construction)

---

**File**: `backend/src/routes/pdf_validation_routes.py`

**Functions**: `pdf_validate_urls_stream`, `pdf_validate_urls`

**Specific Changes**:

1. **Reject `'all'`**: Change condition from `if administration != "all" and administration not in user_tenants` to `if administration not in user_tenants` (which implicitly rejects `'all'` since it's never in `user_tenants`)
2. **Remove `"all"` special case**: The condition `administration != "all"` should no longer bypass the check

---

**File**: `backend/src/routes/aangifte_ib_routes.py`

**Function**: `aangifte_ib_export`

**Specific Changes**:

1. **Reject `'all'`**: Change from `if administration != "all" and administration not in user_tenants` to `if administration not in user_tenants`
2. **Consistent check**: Align with the `aangifte_ib` and `aangifte_ib_details` endpoints which already use `if administration not in user_tenants` without the `!= "all"` bypass

---

**File**: `backend/src/mutaties_cache.py`

**Functions**: `query_aangifte_ib`, `query_aangifte_ib_details`, `get_data`

**Specific Changes**:

1. **Exact match filtering**: Replace `df["administration"].str.startswith(administration)` with `df["administration"] == administration` in both `query_aangifte_ib` and `query_aangifte_ib_details`
2. **Remove `!= "all"` guard**: Since backend now rejects `'all'`, the `if administration != "all"` guard can be simplified (or kept as defense-in-depth)
3. **Snapshot-based reads**: Modify `get_data()` to return a snapshot reference. Modify `_refresh()` and `_ensure_years_loaded()` to assign NEW DataFrames atomically:
   - `get_data()` captures `snapshot = self.data` after ensuring refresh, returns this reference
   - `_refresh()` builds the new DataFrame locally, then does `self.data = new_df` (atomic under GIL)
   - `_ensure_years_loaded()` builds new DataFrame via `pd.concat([self.data, new_data])`, then assigns `self.data = combined` (atomic under GIL)
   - Callers pass the snapshot to query methods instead of re-reading `self.data`
4. **Query methods accept optional snapshot parameter**: `query_aangifte_ib(year, administration, snapshot=None)` — uses `snapshot` if provided, else falls back to `self.data.copy()`

---

**File**: `backend/src/report_generators/btw_aangifte_generator.py`

**Specific Changes**:

1. **Exact match filtering**: Replace all 3 instances of `df["administration"].str.startswith(administration)` with `df["administration"] == administration`

---

**File**: `backend/src/btw_processor.py`

**Specific Changes**:

1. **Exact match filtering**: Replace all 3 instances of `df["administration"].str.startswith(administration)` with `df["administration"] == administration`

---

**File**: `backend/src/routes/aangifte_ib_routes.py`

**Functions**: `aangifte_ib`, `aangifte_ib_details`

**Specific Changes for Snapshot Consistency**:

1. **Capture snapshot once**: `snapshot = cache.get_data(db)` returns a stable reference
2. **Pass snapshot to query methods**: `cache.query_aangifte_ib(year, administration, snapshot=snapshot)`
3. **Filter `user_tenants` on the snapshot**: `snapshot = snapshot[snapshot["administration"].isin(user_tenants)]`

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that call the affected functions with buggy inputs and verify the vulnerabilities exist. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:

1. **Frontend `'all'` fallback test**: Mock `localStorage.getItem('selectedTenant')` returning `null`, verify `tenantAwareGet` sends `administration: 'all'` (will pass on unfixed code, demonstrating the vulnerability)
2. **Backend bypass test**: Call `/api/pdf/validate-urls?administration=all` with valid auth, verify it does NOT return 403 (will pass on unfixed code, demonstrating the bypass)
3. **Prefix matching leak test**: Insert data for "Peter" and "PeterPrive", call `query_aangifte_ib(2026, "Peter")`, verify it returns data from BOTH tenants (will pass on unfixed code, demonstrating the leak)
4. **Cache inconsistency test**: Simulate cache mutation between two query calls on the same `MutatiesCache` instance (will demonstrate different data returned)

**Expected Counterexamples**:

- `tenantAwareGet` sends `administration: 'all'` when no tenant is selected
- Backend allows `'all'` through without 403
- `str.startswith("Peter")` matches both "Peter" and "PeterPrive" rows
- Two sequential `self.data.copy()` calls return different DataFrames if `_refresh()` runs between them

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  IF input.source == 'frontend'
    result := tenantAwareGet_fixed(input.endpoint)
    ASSERT result THROWS Error("No tenant selected")

  IF input.source == 'backend'
    result := route_handler_fixed(input.request)
    ASSERT result.status_code == 403

  IF input.source == 'cache_filter'
    result := query_aangifte_ib_fixed(input.year, input.administration)
    ASSERT ALL rows IN result HAVE row.administration == input.administration

  IF input.source == 'cache_consistency'
    snapshot := get_data_fixed(db)
    result1 := query_fixed(snapshot, params1)
    MUTATE cache  // simulate concurrent refresh
    result2 := query_fixed(snapshot, params2)
    ASSERT result1 and result2 use SAME underlying data
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  // Valid tenant, proper authorization
  ASSERT route_handler_original(input) == route_handler_fixed(input)
  ASSERT query_aangifte_ib_original(input) == query_aangifte_ib_fixed(input)
  // Cache still refreshes for new requests
  ASSERT get_data_fixed(db) reflects latest database state
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many random valid tenant names and verifies exact-match filtering returns correct results
- It catches edge cases like empty strings, whitespace, special characters in tenant names
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for valid tenant requests, then write property-based tests capturing that behavior.

**Test Cases**:

1. **Valid tenant request preservation**: Verify `query_aangifte_ib("2026", "PeterPrive")` returns only PeterPrive data (same result before and after fix)
2. **Multi-tenant user access preservation**: Verify users with multiple tenants can still access each one individually
3. **Cache refresh visibility preservation**: Verify that after a cache refresh, NEW requests see the updated data
4. **On-demand year loading preservation**: Verify `_ensure_years_loaded()` still works for missing years

### Unit Tests

- Frontend: `tenantAwareGet` throws when no tenant selected
- Frontend: `tenantAwarePost` throws when no tenant and no `data.administration`
- Backend: `pdf_validate_urls_stream` returns 403 for `administration=all`
- Backend: `pdf_validate_urls` returns 403 for `administration=all`
- Backend: `aangifte_ib_export` returns 403 for `administration=all`
- Cache: `query_aangifte_ib` with exact match returns only matching tenant
- Cache: `query_aangifte_ib_details` with exact match returns only matching tenant
- Cache: Snapshot remains stable after `_refresh()` is called
- BTW: `btw_processor` exact match filtering
- BTW: `btw_aangifte_generator` exact match filtering

### Property-Based Tests

- Generate random pairs of tenant names where one is a prefix of the other → verify exact-match filtering never returns the longer name when querying the shorter
- Generate random valid tenant names → verify `query_aangifte_ib` returns only rows matching that exact tenant
- Generate random cache states (DataFrames) → simulate concurrent `_refresh()` → verify snapshot holders still see their original data
- Generate random administration values including `'all'`, empty, null → verify frontend throws for all invalid values and backend returns 403

### Integration Tests

- Full flow: User with tenant "Peter" requests Aangifte IB → verify no "PeterPrive" data leaks
- Full flow: Summary and detail calls return consistent totals (snapshot isolation)
- Full flow: Frontend with no tenant selected → verify no API call is made
- Full flow: Backend receives `'all'` → verify 403 on all affected routes
