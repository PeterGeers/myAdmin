# Bug Report: Aangifte IB Expand Failure in Table

**Date**: 2026-02-07 15:21  
**Severity**: High  
**Component**: Frontend - AangifteIbReport  
**Status**: Investigating

## Problem Description

In the Aangifte IB Summary table:

1. Clicking the + sign before **Parent** correctly expands to show **Aangifte** items ✅
2. Clicking the + sign before **Aangifte** items fails with a 500 error ❌

**Error Message**:

```
GET http://localhost:3000/api/reports/aangifte-ib-details?administration=GoodwinSolutions&year=2025&parent=2000&aangifte=BTW 500 (INTERNAL SERVER ERROR)
```

## Root Cause Analysis

### Current Behavior

The frontend makes an API call to `/api/reports/aangifte-ib-details` every time a user clicks the + button on an Aangifte row to fetch account details (Reknum, AccountName, Amount).

### Issues Identified

1. **Unnecessary API Call**: The expand/collapse UI should not require reloading data from the backend. The data structure suggests that account details should either:
   - Be included in the initial `/api/reports/aangifte-ib` response
   - Be cached client-side after the first fetch

2. **Backend 500 Error**: The backend endpoint is failing, likely due to:
   - Column name case sensitivity issues in the cache query
   - Missing data in the cache for the requested year (2025)
   - Incorrect filtering logic

### Code Analysis

**Frontend** (`AangifteIbReport.tsx` lines 310-330):

```typescript
onClick={() => {
  if (isDetailExpanded) {
    setSelectedAangifteRow(null);
    setAangifteIbDetails([]);
  } else {
    fetchAangifteIbDetails(group.parent, item.Aangifte);  // ← API call here
  }
}}
```

**Backend** (`app.py` line 2559-2598):

- Endpoint: `/api/reports/aangifte-ib-details`
- Calls: `cache.query_aangifte_ib_details(year, administration, parent, aangifte, user_tenants)`

**Cache** (`mutaties_cache.py` lines 189-230):

- Method: `query_aangifte_ib_details()`
- Filters by: `df['Parent']`, `df['Aangifte']`, `df['administration']`
- Returns: Account details grouped by `Reknum` and `AccountName`

## Proposed Solutions

### Option 1: Include Account Details in Initial Response (Recommended)

**Pros**:

- Single API call
- Faster UX (no loading delay on expand)
- Simpler frontend logic
- Reduces backend load

**Cons**:

- Slightly larger initial payload

**Implementation**:

1. Modify `/api/reports/aangifte-ib` to include account details in the response
2. Update frontend to store and display account details from initial data
3. Remove `fetchAangifteIbDetails()` API call
4. Keep expand/collapse as pure UI state management

### Option 2: Fix Backend Error + Add Client-Side Caching

**Pros**:

- Smaller initial payload
- Lazy loading of details

**Cons**:

- More complex frontend logic
- Additional API calls
- Slower UX on first expand

**Implementation**:

1. Debug and fix the backend 500 error
2. Add client-side caching in frontend to avoid repeated API calls
3. Add loading state for expand operations

### Option 3: Hybrid Approach

**Pros**:

- Balance between payload size and UX
- Flexible for different data sizes

**Cons**:

- Most complex implementation

**Implementation**:

1. Include account details for "hot" items (e.g., top 10 Parent/Aangifte combinations)
2. Lazy load details for remaining items
3. Cache loaded details client-side

## Recommended Action

**Implement Option 1** - Include account details in initial response.

**Rationale**:

- Aangifte IB reports typically have a manageable number of records
- Users expect instant expand/collapse (no loading delays)
- Simpler code is easier to maintain
- Reduces backend API calls and load

## Next Steps

1. [ ] Investigate backend 500 error (check logs for stack trace)
2. [ ] Determine if year 2025 data exists in the database
3. [ ] Test cache query manually to verify column names
4. [ ] Decide on solution approach (Option 1 recommended)
5. [ ] Implement chosen solution
6. [ ] Update tests
7. [ ] Verify fix in production

## Additional Notes

- The error occurs with year=2025, which may not have data yet
- The backend uses an in-memory cache (`mutaties_cache.py`) for performance
- The cache auto-refreshes every 30 minutes (TTL)
- Tenant filtering is correctly implemented with `@tenant_required()` decorator

If I press export HTML all details on account level are shown.
