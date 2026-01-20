# Mutaties Cache System Explanation

## Overview

The application uses an **in-memory cache** to speed up reporting queries. Instead of querying the database every time, it loads all data from `vw_mutaties` into memory (RAM) and serves queries from there.

## How It Works

### 1. **Cache Loading**

- On first request, the cache loads **all rows** from `vw_mutaties` view into a pandas DataFrame
- Data is stored in memory for fast access
- Typical load time: ~2-5 seconds for hundreds of thousands of rows
- Memory usage: ~50-200 MB depending on data size

### 2. **Automatic Refresh (TTL)**

- **TTL (Time To Live)**: 30 minutes by default
- After 30 minutes, the cache automatically refreshes on the next request
- This ensures data stays reasonably fresh without constant database queries

### 3. **Thread Safety**

- Uses locks to prevent multiple simultaneous refreshes
- Safe for concurrent requests from multiple users

### 4. **Performance Benefits**

- **Database queries**: Slow (1-5 seconds per complex query)
- **Cache queries**: Fast (10-100 milliseconds)
- **Speed improvement**: 10-50x faster for reporting

## Cache Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│ 1. First Request                                            │
│    → Cache is empty                                         │
│    → Load all data from vw_mutaties (2-5 seconds)          │
│    → Store in memory                                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Subsequent Requests (within 30 minutes)                  │
│    → Serve from memory cache (10-100ms)                    │
│    → No database query needed                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. After 30 Minutes                                         │
│    → Cache expires                                          │
│    → Next request triggers automatic refresh                │
│    → Load fresh data from database                          │
└─────────────────────────────────────────────────────────────┘
```

## When Cache is Used

The cache is used by these features:

- ✅ **Check Reference Numbers** (Banking Accounts tab)
- ✅ **Aangifte IB Reports** (Tax reporting)
- ✅ **Actuals Reports** (Financial reporting)
- ✅ **Filter Options** (Dropdowns for years, administrations, etc.)

## How to Reset/Refresh the Cache

### Method 1: API Endpoints (Recommended)

#### Check Cache Status

```bash
GET http://localhost:5000/api/cache/status
```

**Response:**

```json
{
  "success": true,
  "cache_active": true,
  "last_refresh": "2026-01-19T20:15:30",
  "record_count": 125000,
  "auto_refresh_enabled": true,
  "refresh_threshold_minutes": 30
}
```

#### Force Refresh Cache

```bash
POST http://localhost:5000/api/cache/refresh
```

**What it does:**

- Immediately reloads data from database
- Replaces old cache with fresh data
- Takes 2-5 seconds to complete

**Response:**

```json
{
  "success": true,
  "message": "Cache refreshed successfully",
  "record_count": 125000,
  "last_refresh": "2026-01-19T20:20:00"
}
```

#### Invalidate Cache

```bash
POST http://localhost:5000/api/cache/invalidate
```

**What it does:**

- Marks cache as invalid
- Next request will trigger automatic refresh
- Useful if you want to defer the refresh until the next query

**Response:**

```json
{
  "success": true,
  "message": "Cache invalidated successfully"
}
```

### Method 2: Restart Backend Container

```bash
docker restart myadmin-backend-1
```

**What it does:**

- Clears all memory (including cache)
- Cache will reload on first request after restart

### Method 3: Using PowerShell/curl

```powershell
# Check status
Invoke-RestMethod -Uri "http://localhost:5000/api/cache/status" -Method GET

# Force refresh
Invoke-RestMethod -Uri "http://localhost:5000/api/cache/refresh" -Method POST

# Invalidate
Invoke-RestMethod -Uri "http://localhost:5000/api/cache/invalidate" -Method POST
```

## When to Refresh the Cache

### Automatic Refresh (No Action Needed)

- ✅ Every 30 minutes automatically
- ✅ On first request after backend restart

### Manual Refresh Needed

- ❗ After importing new transactions
- ❗ After deleting transactions
- ❗ After updating transaction data
- ❗ After database schema changes
- ❗ When you see stale/outdated data

## Cache Statistics

The cache tracks these metrics:

- **Rows**: Number of transactions cached
- **Columns**: Number of fields per transaction
- **Memory**: RAM usage in MB
- **Last Loaded**: Timestamp of last refresh
- **Age**: How old the cache is (in seconds)
- **TTL**: Time until automatic refresh
- **Needs Refresh**: Boolean indicating if refresh is due

## Performance Comparison

### Without Cache (Direct Database Queries)

```
Check Reference Numbers: 3-5 seconds
Aangifte IB Report:      2-4 seconds
Filter Options:          1-2 seconds
Total for 3 operations:  6-11 seconds
```

### With Cache (In-Memory Queries)

```
Check Reference Numbers: 50-100ms
Aangifte IB Report:      30-80ms
Filter Options:          10-20ms
Total for 3 operations:  90-200ms (50x faster!)
```

## Technical Details

### Cache Implementation

- **File**: `backend/src/mutaties_cache.py`
- **Class**: `MutatiesCache`
- **Storage**: pandas DataFrame in memory
- **Thread Safety**: Uses Python threading.Lock
- **Singleton Pattern**: One global cache instance

### Data Source

- **View**: `vw_mutaties`
- **Columns**: All columns from the view
- **Filters**: None (loads everything)
- **Optimization**: TransactionDate converted to datetime for faster filtering

### Memory Management

- **Typical Size**: 50-200 MB for 100k-500k rows
- **Max Size**: Depends on available RAM
- **Cleanup**: Automatic when backend restarts

## Troubleshooting

### Problem: Seeing old/stale data

**Solution**: Force refresh the cache

```bash
POST http://localhost:5000/api/cache/refresh
```

### Problem: Cache not loading

**Solution**: Check backend logs

```bash
docker logs myadmin-backend-1 --tail 50
```

### Problem: Out of memory errors

**Solution**:

1. Reduce TTL to refresh more frequently
2. Add more RAM to server
3. Consider database-level caching instead

### Problem: Cache refresh is slow

**Solution**:

- Normal for large datasets (100k+ rows)
- Consider adding database indexes
- Check database performance

## Best Practices

1. **After Data Changes**: Always refresh cache manually
2. **Regular Monitoring**: Check cache status periodically
3. **Performance Testing**: Monitor cache hit rates
4. **Memory Usage**: Keep an eye on RAM consumption
5. **TTL Tuning**: Adjust 30-minute TTL if needed

## Future Improvements

Potential enhancements:

- [ ] Partial cache updates (only changed rows)
- [ ] Multiple cache instances (per administration)
- [ ] Redis-based distributed cache
- [ ] Cache warming on startup
- [ ] Automatic invalidation on data changes
