# Multi-Tenant Concurrency & Memory Safety

## Status: Backlog (Analysis Complete)

## Context

Analysis of what happens when multiple tenants use the invoice processing pipeline and other backend features simultaneously. Two areas investigated:

1. **Tenant isolation** — can concurrent requests leak data between tenants?
2. **Memory pressure** — do shared caches grow unbounded with more tenants?

---

## Current State (What's Safe)

The core invoice processing flow (upload → extract → approve → save) is **safe for concurrent multi-tenant use**:

- `InvoiceService`, `PDFProcessor`, `TransactionLogic` are instantiated per-request
- Each request gets its own DB connection from the pool via `get_cursor()` context manager
- The `approve_transactions` endpoint enforces `txn["Administration"] = tenant` before saving
- Duplicate detection queries include `AND administration = %s`
- `GoogleDriveService` is instantiated per-request with tenant-specific credentials

---

## Issues Found

### Priority 1: Tenant Isolation Gaps (Security)

| #   | Issue                                                     | Severity | Impact                                                     |
| --- | --------------------------------------------------------- | -------- | ---------------------------------------------------------- |
| 1   | `pdf_update_record` endpoint missing `@tenant_required()` | **High** | Cross-tenant record modification via Ref3                  |
| 2   | `pdf_get_administrations` endpoint missing tenant filter  | Medium   | Information disclosure (all administrations visible)       |
| 3   | Shared `uploads/` folder — file name collision            | Medium   | Concurrent uploads with same filename overwrite each other |

### Priority 2: Memory Growth (Stability)

| #   | Issue                                                                  | Severity | Impact                                          |
| --- | ---------------------------------------------------------------------- | -------- | ----------------------------------------------- |
| 4   | `MutatiesCache` — single global DataFrame for ALL tenants              | High     | 50–200 MB+, grows linearly with tenants × years |
| 5   | `BnbCache` — single global DataFrame for ALL tenants                   | Medium   | 10–50 MB, same unbounded growth pattern         |
| 6   | `QueryCache` (duplicate_query_optimizer) — no max size                 | Medium   | Unbounded dict, only TTL-based cleanup          |
| 7   | `ScalabilityManager` — 65 DB connections + 74 threads always allocated | Low      | Fixed ~150 MB overhead regardless of load       |

---

## Recommended Fixes

### Fix #1 — Namespace temp files (Issue #3)

**Effort**: Small (30 min)
**File**: `backend/src/routes/invoice_routes.py`

```python
import uuid
unique_filename = f"{tenant}_{uuid.uuid4().hex[:8]}_{filename}"
temp_path = os.path.join(UPLOAD_FOLDER, unique_filename)
```

### Fix #2 — Add `@tenant_required()` to `pdf_update_record` (Issue #1)

**Effort**: Small (1 hour)
**File**: `backend/src/routes/pdf_validation_routes.py`

```python
@pdf_validation_bp.route("/api/pdf/update-record", methods=["POST"])
@cognito_required(required_permissions=["invoices_update"])
@tenant_required()
def pdf_update_record(user_email, user_roles, tenant, user_tenants):
    # Pass tenant to validator.update_record() and add WHERE administration = %s
```

Also requires updating `PDFValidator.update_record()` to accept and filter by tenant.

### Fix #3 — Filter `pdf_get_administrations` by user access (Issue #2)

**Effort**: Small (30 min)
**File**: `backend/src/routes/pdf_validation_routes.py`

```python
@pdf_validation_bp.route("/api/pdf/get-administrations", methods=["GET"])
@cognito_required(required_permissions=["invoices_read"])
@tenant_required()
def pdf_get_administrations(user_email, user_roles, tenant, user_tenants):
    administrations = validator.get_administrations_for_year(year)
    filtered = [a for a in administrations if a in user_tenants]
    return jsonify({"success": True, "administrations": filtered})
```

### Fix #4 — Add max_size to QueryCache (Issue #6)

**Effort**: Small (1 hour)
**File**: `backend/src/duplicate_query_optimizer.py`

Add LRU eviction with `max_size=500` (same pattern as `PersistentPatternCache`). Evict oldest entries when limit is reached.

### Fix #5 — Make MutatiesCache tenant-aware (Issue #4)

**Effort**: Medium (4–6 hours)
**File**: `backend/src/mutaties_cache.py`

Replace single DataFrame with `Dict[str, DataFrame]` keyed by tenant. Each tenant gets independent TTL. Inactive tenants (no access for 2× TTL) get evicted. Limits peak memory to active tenants only.

### Fix #6 — Make BnbCache tenant-aware (Issue #5)

**Effort**: Medium (2–3 hours)
**File**: `backend/src/bnb_cache.py`

Same pattern as Fix #5. Scope BNB data by tenant with independent eviction.

### Fix #7 — Memory alerting via health endpoint (Quick Win)

**Effort**: Small (1 hour)

Surface the existing `MutatiesCache.memory_usage` stats (already logged) through the system health endpoint. Add alert threshold in `ResourceMonitor` for process RSS.

---

## Estimated Memory Profile

| Scenario                         | Estimated RSS |
| -------------------------------- | ------------- |
| Idle (caches cold)               | ~150–200 MB   |
| 2 tenants, caches warm           | ~300–400 MB   |
| 5 tenants, active use            | ~400–600 MB   |
| 10 tenants, heavy concurrent use | ~600 MB–1 GB  |

Main driver: total data volume across all tenants loaded into MutatiesCache + BnbCache. Per-request allocations (PDF processing, API calls) are transient and GC'd.

---

## Architecture Note

If 10+ active tenants are expected, the "cache everything in one process" model will eventually hit Railway container memory limits. Options:

- Per-tenant cache partitioning (Fixes #5/#6 above)
- External cache (Redis) for hot data
- On-demand DB queries with MySQL query-level caching
- Horizontal scaling with tenant-affinity routing
