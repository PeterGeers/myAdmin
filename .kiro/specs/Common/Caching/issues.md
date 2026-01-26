# Caching Architecture Issues & Considerations

## Current Implementation (Backend Caching)

**Status:** ✅ Implemented  
**Location:** `backend/src/mutaties_cache.py`  
**Date Identified:** January 26, 2026

### How It Works

The backend maintains a **single global in-memory cache** that loads ALL tenant data from `vw_mutaties`:

```python
# Cache loads ALL tenants
query = "SELECT * FROM vw_mutaties"  # No WHERE clause
self.data = pd.read_sql(query, conn)  # ~100k+ rows in memory
```

**Security Filtering:** Applied at route level after cache retrieval

```python
df = cache.get_data(db)  # Get ALL data
df = df[df['administration'].isin(user_tenants)]  # Filter to user's tenants
```

**Cache Lifecycle:**

- Loads on first request to actuals endpoints
- Auto-refreshes every 30 minutes (TTL)
- Shared across all users
- Cleared on backend restart

### Pros ✅

1. **Performance:** One cache serves all users - no duplicate loading
2. **Simplicity:** Single cache instance, easy to manage
3. **Fast queries:** Pandas operations on in-memory data
4. **Multi-user efficient:** Scales well with many concurrent users

### Cons ❌

1. **Memory usage:** ALL tenant data loaded into backend RAM
2. **Security concern:** All tenant data in memory (filtered before return)
3. **Scalability:** Memory grows with total data across all tenants
4. **Cold start:** First user experiences 10+ second delay on cache load

---

## Proposed Alternative: Frontend Per-Tenant Caching

**Status:** 🔄 Under Consideration  
**Priority:** Medium  
**Complexity:** Medium

### Concept

Move caching to the frontend where each user loads only their tenant's data:

```typescript
// Frontend loads and caches tenant data
const [cachedMutaties, setCachedMutaties] = useState<MutatiesData[]>([]);

useEffect(() => {
  // Load vw_mutaties for current tenant only
  authenticatedGet(`/api/reports/vw-mutaties?tenant=${currentTenant}`)
    .then((response) => response.json())
    .then((data) => {
      setCachedMutaties(data);
      // Optionally persist to localStorage
      localStorage.setItem(`mutaties_${currentTenant}`, JSON.stringify(data));
    });
}, [currentTenant]);

// All reports use cachedMutaties (no more API calls)
const balanceData = cachedMutaties.filter((row) => row.VW === "N");
const profitLossData = cachedMutaties.filter((row) => row.VW === "Y");
```

### Pros ✅

1. **Security:** Each user only has their tenant data in browser
2. **Memory:** Less backend memory usage (no global cache)
3. **Isolation:** Better tenant data isolation
4. **Scalability:** Backend memory doesn't grow with tenant count

### Cons ❌

1. **Database load:** Each user makes separate database query
2. **Cache loss:** Data lost on page refresh (unless using localStorage)
3. **Network:** Larger initial payload to frontend
4. **Complexity:** Need to manage cache invalidation in frontend
5. **Multi-tenant users:** Users with multiple tenants load data multiple times

---

## Alternative: Hybrid Backend Per-Tenant Caching

**Status:** 🔄 Under Consideration  
**Priority:** Low  
**Complexity:** High

### Concept

Backend maintains separate cache per tenant:

```python
# Global tenant-specific caches
_tenant_caches = {}

def get_tenant_cache(tenant_id):
    if tenant_id not in _tenant_caches:
        _tenant_caches[tenant_id] = MutatiesCache()
    return _tenant_caches[tenant_id]

# In routes
cache = get_tenant_cache(tenant)
df = cache.get_data(db, tenant_filter=tenant)
```

### Pros ✅

1. **Security:** Tenant data isolated in separate caches
2. **Performance:** Still fast for multi-user scenarios
3. **Memory:** Only active tenants consume memory

### Cons ❌

1. **Complexity:** More complex cache management
2. **Memory:** Multiple caches can use more memory than single cache
3. **Synchronization:** Need to manage multiple cache lifecycles

---

## Decision Factors

### Choose Frontend Caching If:

- ✅ Users typically work with one tenant at a time
- ✅ Tenant datasets are relatively small (<10k rows)
- ✅ Security isolation is critical
- ✅ Few concurrent users

### Keep Backend Caching If:

- ✅ Many concurrent users
- ✅ Users frequently switch tenants
- ✅ Large datasets (>50k rows per tenant)
- ✅ Performance is critical

### Choose Hybrid If:

- ✅ Many tenants with varying activity levels
- ✅ Need both security and performance
- ✅ Have resources for complex implementation

---

## Current Performance Metrics

**Backend Cache:**

- Load time: ~10 seconds for 103,290 rows
- Memory usage: ~80MB
- Query time (after cache): <100ms
- TTL: 30 minutes

**Observed Issues:**

- First user to access actuals experiences 10+ second delay
- "No year options available" message appears during cache loading
- Profit/loss data loads slower than balance data (same cache, different processing)

## Implementation Results (January 26, 2026)

### Cache Warmup Implementation - ✅ SUCCESS

**What Was Implemented:**

1. Backend endpoint: `/api/cache/warmup` (POST)
2. Frontend calls warmup when ActualsReport component mounts
3. Cache loads on first FIN Reports access instead of first data query

**Performance Results:**

- ✅ **First user after backend restart:** ~10 seconds (cache loading)
- ✅ **All subsequent users:** <1 second (instant access)
- ✅ **Cache persists between frontend sessions:** Users can close browser and return - cache still loaded
- ✅ **Shared across all users:** One cache load benefits everyone

**Why It's Fast:**

- Backend cache is **shared across ALL users and sessions**
- Cache stays in memory on backend server (not per-user)
- No per-session loading - first user loads, everyone benefits
- Cache persists until backend restart or 30-minute TTL expires

### Known Trade-off: Data Freshness

**Issue Identified:**
When data is modified (add/edit/delete transactions), changes don't appear in Actuals reports immediately.

**Root Cause:**
Cache doesn't know about data changes until it refreshes (30-minute TTL or manual refresh).

**Current Workaround:**

- Wait 30 minutes for automatic refresh
- Restart backend container
- Use SysAdmin cache refresh endpoint: `/api/cache/refresh` (POST)

**Future Solutions (Not Implemented Yet):**

1. **Automatic cache invalidation** - Invalidate cache when data changes
   - Add `invalidate_cache()` calls to save endpoints:
     - `/api/banking/save-transactions`
     - `/api/str/save`
     - `/api/str/write-future`
     - `/api/btw/save-transaction`
2. **Manual refresh button** - Let users force refresh when needed
3. **Shorter TTL** - Reduce from 30 minutes to 5-10 minutes
4. **Smart invalidation** - Only invalidate when specific tables change

**Decision:** Trade-off accepted for now - speed is more important than immediate freshness. Can revisit if data freshness becomes critical.

---

## Recommendations

### Short Term (Current)

1. ✅ Keep backend caching (already implemented)
2. ✅ Add cache warmup endpoint (implemented)
3. ✅ Frontend calls warmup on Actuals page load (implemented)

### Medium Term (Next Sprint)

1. 🔄 Monitor memory usage with production data volumes
2. 🔄 Add cache metrics endpoint for monitoring
3. 🔄 Consider implementing cache preloading on backend startup for production

### Long Term (Future)

1. ⏳ Evaluate frontend caching if security concerns arise
2. ⏳ Consider Redis for distributed caching if scaling beyond single server
3. ⏳ Implement incremental cache updates instead of full refresh

---

## Related Files

- `backend/src/mutaties_cache.py` - Cache implementation
- `backend/src/actuals_routes.py` - Routes using cache
- `backend/src/app.py` - Cache warmup endpoint
- `frontend/src/components/reports/ActualsReport.tsx` - Frontend cache warmup call

---

## Notes

- Cache is cleared on backend container restart
- No persistence layer (all in-memory)
- Security filtering happens after cache retrieval
- Consider adding cache hit/miss metrics for monitoring
