I was expecting some performance improvements on FIN Rapporten as a result of our changed approach.

It looks as if still all data is loaded and cached in the backend

To improve performance it would be nice if initially we just load the data from years open. Only when selecting closed years these selected years should be loaded.

What is your opinion and or do you have better ideas

---

## IMPLEMENTED: Option 3 - Hybrid Approach

**Status**: ✅ Implemented (March 3, 2026)

### What Was Changed

Modified `backend/src/mutaties_cache.py` to implement smart year-based caching:

1. **Initial Load (Optimized)**:
   - Loads only OPEN years (not yet closed)
   - Loads LAST CLOSED year (for year-end comparisons)
   - Skips older closed years

2. **On-Demand Loading**:
   - When user requests data from an older closed year
   - System automatically loads that year into cache
   - Seamless experience, slight delay only on first access

3. **Performance Benefits**:
   - Significantly faster initial load
   - Lower memory usage
   - Most common use cases (current year + previous year) are instant
   - Historical analysis still possible with minimal delay

### Technical Implementation

**New Methods Added**:

- `_get_years_to_load()`: Determines which years to load based on closure status
- `load_additional_year()`: Loads specific year on-demand when requested

**Modified Methods**:

- `_refresh()`: Now uses year filtering in SQL query
- `query_aangifte_ib()`: Auto-loads year if not in cache

**Query Optimization**:

```sql
-- Before: Load ALL years
SELECT * FROM vw_mutaties

-- After: Load only relevant years
SELECT * FROM vw_mutaties
WHERE jaar = 2025 OR jaar = 2026
```

### Expected Performance Improvement

For a tenant with 10 years of data:

- **Before**: Load ~500,000 rows (all years)
- **After**: Load ~100,000 rows (2-3 years)
- **Improvement**: ~80% reduction in initial load time and memory usage

### Testing

To verify the optimization is working:

1. Check backend logs on startup for: `"Years analysis: All=X, Closed=Y, Open=Z, Loading=W"`
2. Check cache stats: `GET /api/cache/status`
3. Access a closed year report and watch logs for: `"Loading additional year X into cache..."`

### Actual Results (GoodwinSolutions Test Database)

**Before Optimization**:

- Rows loaded: 104,842 (all 34 years from 1991-2028)
- Memory usage: 81.2 MB
- Load time: 2.56s

**After Optimization**:

- Rows loaded: 6,506 (4 years: 2025-2028)
- Memory usage: 5.4 MB
- Load time: 1.84s
- **Improvement**: 94% reduction in rows, 93% reduction in memory, 28% faster load

### Additional Fix: Year Selector Issue

**Problem**: Year selectors in reports (especially Aangifte IB) were showing limited years because they used `cache.get_available_years()` which only returned cached years.

**Solution** (March 3, 2026):

- Modified `get_available_years()` to accept optional `db_manager` parameter
- When `db_manager` provided, queries database directly: `SELECT DISTINCT YEAR(TransactionDate) FROM mutaties`
- Updated `aangifte-ib` endpoint to pass `db_manager` to `get_available_years()`
- Now year selectors show ALL years in database, not just cached years

**Files Modified**:

- `backend/src/mutaties_cache.py` - Updated `get_available_years()` method
- `backend/src/reporting_routes.py` - Updated `aangifte-ib` endpoint

### Future Enhancements

Potential improvements:

- Persistent cache for closed years (Redis or file-based)
- Pre-warming cache for commonly accessed years
- Automatic cleanup of rarely accessed years

Implementation Approach
Option 3: Hybrid Approach (Recommended)

Load all open years + current closed year (for year-end reports)
Keep closed years in a separate, persistent cache (Redis or file-based)
Load additional closed years on-demand
Benefits: Best balance of performance and functionality

I recommend Option 3 because:

Most users work with current year + maybe previous year
Year-end reports often need to compare current vs previous year
Historical analysis is less frequent and can tolerate slight delay
Closed years don't change, so they can be cached more aggressively
Would you like me to implement this optimization? It would involve:

Modifying mutaties_cache.py to check year closure status
Loading only open years + last closed year by default
Adding an on-demand loading mechanism for historical years
Updating the cache invalidation logic to be year-aware
This could significantly improve performance, especially for tenants with many years of da
