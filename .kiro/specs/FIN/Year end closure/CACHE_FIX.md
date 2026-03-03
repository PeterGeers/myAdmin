# Cache Invalidation Fix for Aangifte IB

## Problem

After closing or reopening a year, the Aangifte IB report showed stale data because the in-memory cache (`mutaties_cache.py`) was not being invalidated.

## Root Cause

The `reopen_year()` method in `year_end_service.py` was missing the cache invalidation call. While `close_year()` properly invalidated the cache, reopening a year did not, causing the cache to show old data until the 30-minute TTL expired.

## Solution

Added cache invalidation to `reopen_year()` method:

```python
# Commit all changes
conn.commit()

# Invalidate cache so reports pick up changes
from mutaties_cache import invalidate_cache
invalidate_cache()

# Return success result
return {
    'success': True,
    'year': year,
    'message': f'Year {year} reopened successfully'
}
```

## How Cache Works

### Cache Behavior

The `MutatiesCache` class in `mutaties_cache.py`:

1. **Loads data**: Reads entire `vw_mutaties` view into memory (pandas DataFrame)
2. **TTL (Time To Live)**: Auto-refreshes after 30 minutes
3. **Manual invalidation**: Can be forced via `invalidate_cache()`
4. **Thread-safe**: Uses locks to prevent race conditions

### When Cache is Invalidated

Cache is now invalidated after:

1. **Closing a year** (`close_year()`) - Creates YearClose and OpeningBalance transactions
2. **Reopening a year** (`reopen_year()`) - Deletes YearClose and OpeningBalance transactions

### When Cache is NOT Invalidated

Cache is NOT invalidated for operations that don't affect Aangifte IB calculations:

- **PDF validation** - Updates Ref3/Ref4 (Google Drive URLs)
- **Missing invoices** - Updates Ref3/Ref4 (file references)
- **Revolut migration** - Updates Ref2 (reference fields)

These operations only update reference fields, not financial amounts or account assignments.

## Testing

### Before Fix

1. Close year 2025 for GoodwinSolutions
2. View Aangifte IB for 2025
3. Reopen year 2025
4. View Aangifte IB for 2025 again
5. **Problem**: Still shows old accounts from history (cache not refreshed)

### After Fix

1. Close year 2025 for GoodwinSolutions
2. View Aangifte IB for 2025 → Shows only 2025 accounts ✅
3. Reopen year 2025
4. View Aangifte IB for 2025 → Shows all historical accounts again ✅
5. **Fixed**: Cache is invalidated immediately after reopen

## Deployment

### Backend Restart Required

After applying this fix, restart the backend:

```bash
docker-compose restart backend
```

### Verification Steps

1. Reopen year 2025 for both tenants (GoodwinSolutions and PeterPrive)
2. Verify Aangifte IB shows historical accounts (before closure)
3. Close year 2025 again
4. Verify Aangifte IB shows only 2025 accounts (after closure)
5. Check that transitions are immediate (no 30-minute delay)

## Related Files

- `backend/src/services/year_end_service.py` - Year-end closure service (MODIFIED)
- `backend/src/mutaties_cache.py` - In-memory cache implementation
- `backend/src/reporting_routes.py` - Aangifte IB endpoints (uses cache)

## Status

- ✅ Fix applied to `reopen_year()` method
- ⏳ Backend restart needed
- ⏳ Testing required (reopen and re-close year 2025)
