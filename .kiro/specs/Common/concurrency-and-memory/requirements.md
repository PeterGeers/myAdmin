# Requirements

## Phase 1: Tenant Isolation (Security)

### REQ-1.1: Prevent cross-tenant record modification

**As a** tenant user,
**I want** PDF validation update operations scoped to my administration,
**So that** I cannot accidentally or maliciously modify another tenant's records.

**Acceptance Criteria:**

- `POST /api/pdf/update-record` enforces `@tenant_required()` decorator
- `PDFValidator.update_record()` includes `WHERE administration = %s` in all queries
- Attempting to update a record from another tenant returns 403
- Existing functionality (updating own records) continues to work

### REQ-1.2: Prevent information disclosure via administrations endpoint

**As a** tenant user,
**I want** the administrations list filtered to only those I have access to,
**So that** I cannot see which other tenants exist in the system.

**Acceptance Criteria:**

- `GET /api/pdf/get-administrations` enforces `@tenant_required()` decorator
- Response only includes administrations present in `user_tenants`
- Users with access to multiple tenants see all their allowed administrations

### REQ-1.3: Prevent file collision during concurrent uploads

**As a** tenant user uploading an invoice,
**I want** my uploaded file to not be overwritten by another tenant's concurrent upload,
**So that** my invoice is processed with my actual file content.

**Acceptance Criteria:**

- Temp files are namespaced to avoid collisions (UUID or tenant prefix)
- Original filename is preserved in metadata/response (for display)
- Cleanup of temp files still works correctly
- Two tenants uploading `invoice.pdf` simultaneously both get correct results

---

## Phase 2: Memory Stability

### REQ-2.1: Bound the QueryCache

**As a** system operator,
**I want** the duplicate detection cache to have a maximum size,
**So that** rapid concurrent duplicate checks don't cause unbounded memory growth.

**Acceptance Criteria:**

- `QueryCache` has a configurable `max_size` (default: 500)
- LRU eviction removes oldest entries when limit is reached
- Cache hit/miss/eviction stats are available via health endpoint
- No change in duplicate detection accuracy

### REQ-2.2: Per-tenant MutatiesCache partitioning

**As a** system operator,
**I want** the mutaties cache to only hold data for active tenants,
**So that** inactive tenants don't consume memory and total usage stays bounded.

**Acceptance Criteria:**

- Cache is keyed by tenant (and year) with independent TTLs
- Inactive tenants (no access for 2× TTL) are evicted
- Peak memory is proportional to active tenants, not total tenants
- Reports still function correctly (same query results)
- Thread safety is maintained (existing lock pattern)

### REQ-2.3: Per-tenant BnbCache partitioning

**As a** system operator,
**I want** the BNB cache to only hold data for active tenants,
**So that** inactive tenants don't consume memory.

**Acceptance Criteria:**

- Same pattern as REQ-2.2 applied to BnbCache
- BNB analytics endpoints return same results
- TTL and eviction behavior is consistent with MutatiesCache

---

## Phase 3: Observability

### REQ-3.1: Memory usage in health endpoint

**As a** system operator,
**I want** cache memory usage surfaced through the health/status endpoint,
**So that** I can monitor memory pressure and get alerts before OOM.

**Acceptance Criteria:**

- Health endpoint includes MutatiesCache size (rows, MB, tenants loaded)
- Health endpoint includes BnbCache size (rows, MB)
- Health endpoint includes QueryCache entry count
- ResourceMonitor alerts when process RSS exceeds configurable threshold

---

## Out of Scope

- Redis/Memcached external caching (future consideration)
- Parquet/S3 cache tier (future consideration)
- Horizontal scaling / multiple backend instances
- Reducing ScalabilityManager thread/connection count (fixed overhead, acceptable)

## Success Metrics

- Zero cross-tenant data access possible via PDF validation endpoints
- Backend RSS stays under 512 MB with 5 active tenants
- No OOM kills on Railway with normal usage patterns
