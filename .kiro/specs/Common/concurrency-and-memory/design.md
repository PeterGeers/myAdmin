# Design

## Phase 1: Tenant Isolation Fixes

### 1.1 — `pdf_update_record` tenant scoping

**File**: `backend/src/routes/pdf_validation_routes.py`

Current:

```python
@pdf_validation_bp.route("/api/pdf/update-record", methods=["POST"])
@cognito_required(required_permissions=["invoices_update"])
def pdf_update_record(user_email, user_roles):
    validator = PDFValidator(test_mode=flag)
    success = validator.update_record(old_ref3, reference_number, ref3, ref4)
```

Target:

```python
@pdf_validation_bp.route("/api/pdf/update-record", methods=["POST"])
@cognito_required(required_permissions=["invoices_update"])
@tenant_required()
def pdf_update_record(user_email, user_roles, tenant, user_tenants):
    validator = PDFValidator(test_mode=flag)
    success = validator.update_record(old_ref3, reference_number, ref3, ref4, tenant)
```

**Also requires**: updating `PDFValidator.update_record()` in `backend/src/pdf_validation.py` to accept `administration` parameter and add `AND administration = %s` to the UPDATE query's WHERE clause.

### 1.2 — `pdf_get_administrations` tenant filtering

**File**: `backend/src/routes/pdf_validation_routes.py`

Add `@tenant_required()` decorator and filter results:

```python
@tenant_required()
def pdf_get_administrations(user_email, user_roles, tenant, user_tenants):
    administrations = validator.get_administrations_for_year(year)
    filtered = [a for a in administrations if a in user_tenants]
    return jsonify({"success": True, "administrations": filtered})
```

### 1.3 — Temp file namespacing

**File**: `backend/src/routes/invoice_routes.py`

```python
import uuid

# Before saving
filename = secure_filename(file.filename)
unique_filename = f"{tenant}_{uuid.uuid4().hex[:8]}_{filename}"
temp_path = os.path.join(UPLOAD_FOLDER, unique_filename)
file.save(temp_path)
```

The original `filename` continues to be used for display and metadata (Ref4, Drive upload). Only the temp path gets the UUID prefix.

---

## Phase 2: Memory Stability

### 2.1 — QueryCache with max_size

**File**: `backend/src/duplicate_query_optimizer.py`

Add LRU eviction:

```python
class QueryCache:
    def __init__(self, default_ttl: int = 300, max_size: int = 500):
        self.cache = {}
        self.default_ttl = default_ttl
        self.max_size = max_size

    def set(self, key, value, ttl=None):
        # Evict expired first
        self._cleanup_expired()
        # If still at capacity, evict oldest by timestamp
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        self.cache[key] = {"value": value, "expires": time.time() + (ttl or self.default_ttl)}
        self.evictions += 1 if len(self.cache) >= self.max_size else 0

    def _evict_oldest(self):
        if not self.cache:
            return
        oldest_key = min(self.cache, key=lambda k: self.cache[k]["expires"])
        del self.cache[oldest_key]
        self.evictions += 1
```

### 2.2 — Per-tenant MutatiesCache

**File**: `backend/src/mutaties_cache.py`

Replace:

```python
self.data = None  # Single DataFrame for all tenants
```

With:

```python
self._tenant_data: Dict[str, TenantCacheEntry] = {}

@dataclass
class TenantCacheEntry:
    data: pd.DataFrame
    last_accessed: datetime
    last_loaded: datetime
    years_loaded: Set[int]
```

Key design decisions:

- **Key**: `tenant` string (not `tenant:year` — keep years together per tenant for report queries that span years)
- **Eviction**: Tenants not accessed for `2 × TTL` (60 min default) get evicted
- **Loading**: Same query but with `WHERE administration = %s` added
- **Thread safety**: Same lock pattern, but acquire per-tenant (or keep global lock — simpler, contention is low)
- **get_data() signature change**: `get_data(db_manager, tenant, requested_years=None)`
- **Backward compatibility**: All callers already pass `tenant` through service layer; update call sites in route handlers

### 2.3 — Per-tenant BnbCache

**File**: `backend/src/bnb_cache.py`

Same pattern as 2.2. Replace single `self.data` DataFrame with tenant-keyed dict. BNB data is already naturally per-tenant (listings belong to specific administrations).

---

## Phase 3: Observability

### 3.1 — Health endpoint extension

**File**: `backend/src/routes/system_health_routes.py` (or equivalent health endpoint)

Add cache stats section to health response:

```python
{
    "caches": {
        "mutaties": {
            "tenants_loaded": 3,
            "total_rows": 45000,
            "memory_mb": 85.2,
            "oldest_entry_age_minutes": 22
        },
        "bnb": {
            "tenants_loaded": 2,
            "total_rows": 1200,
            "memory_mb": 4.1
        },
        "query_cache": {
            "entries": 142,
            "max_size": 500,
            "hit_rate_percent": 67.3
        }
    },
    "process": {
        "rss_mb": 412.5,
        "alert_threshold_mb": 512
    }
}
```

---

## Security Considerations

- Phase 1 fixes close the defense-in-depth gaps documented in `database-patterns.md` (REQ13)
- No new endpoints or permissions introduced
- All changes are additive restrictions (tighter filtering, not relaxing)

## Performance Considerations

- Phase 2 trades memory for latency: first request per tenant triggers DB load (~200ms)
- Subsequent requests within TTL are instant (same as today)
- Net effect: lower baseline memory, occasional cold-start per tenant
- For 2–5 active tenants, this is negligible

## Dependencies

- Phase 1: No dependencies, can be done independently per fix
- Phase 2: Fixes #5/#6 share the same pattern — do MutatiesCache first, then apply to BnbCache
- Phase 3: Depends on Phase 2 (needs the per-tenant structure to report meaningful stats)
