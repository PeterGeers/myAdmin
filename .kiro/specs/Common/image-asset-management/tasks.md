# Implementation Plan:

## Overview

Media Asset Management Service — implements requirements 1-13 from the requirements document. Covers backend service, database schema, API routes, code path migration, and frontend components.

## Task Dependency Graph

```json
{
  "waves": [
    ["1.1", "1.2", "1.3"],
    ["1.4", "1.5", "1.6", "1.7", "1.8", "1.9"],
    ["2.1", "2.2", "2.3", "2.4", "2.5"],
    ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6"],
    ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7"],
    ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7"],
    ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7", "6.8", "6.9", "6.10"],
    ["7.1", "7.2", "7.3"],
    ["8.1", "8.2", "8.3", "8.4"],
    ["9.1", "9.2", "9.3", "9.4", "9.5", "9.6", "9.7"]
  ]
}
```

## Tasks

## Phase 1: Foundation (Database + Core Service)

**Dependencies:** None
**Estimated time:** 3-4 days

- [x] **1.1** Create DDL migration script `migrations/20260811_create_s3_assets.sql`
  - `s3_assets` table with all columns, indexes, UNIQUE on (administration, s3_key)
  - `s3_asset_references` table with administration column, FK, unique constraint, indexes
  - Test: run migration on local Docker MySQL, verify tables exist

- [x] **1.2** Add `python-ulid` to `requirements.txt`

- [x] **1.3** Create `backend/src/services/media_asset_service.py` — skeleton
  - Class `MediaAssetService(db_manager, parameter_service)`
  - Implement `_generate_asset_id()` → `ast_<ULID>`
  - Implement `_resolve_bucket(category)` → reads env var based on CATEGORY_BUCKETS mapping
  - Implement `_build_s3_key(tenant, category, asset_id, filename)` → `{tenant}/{category}/{asset_id}_{filename}`
  - Implement `_validate_file(file_data, filename)` → checks extension + magic bytes + size limit
  - Unit tests for each internal method

- [x] **1.4** Implement `store_and_register(tenant, file_data, filename, category, entity_type, entity_id, metadata)`
  - Validate file (AC 3-7 from Req 1)
  - Compute SHA-256 content_hash
  - Generate asset_id
  - Build s3_key
  - Call `_upload_raw(bucket, key, file_data, content_type)`
  - INSERT into `s3_assets` (status=ACTIVE)
  - Optionally INSERT into `s3_asset_references` if entity_type provided
  - Return `{'success': True, 'asset': {...}, 'duplicate_of': ...}`
  - Handle DB-commit-after-S3-write failure (log orphaned key)
  - Unit tests with mocked S3 + DB

- [x] **1.5** Implement `attach(tenant, asset_id, entity_type, entity_id)`
  - Verify asset exists and belongs to tenant
  - INSERT into `s3_asset_references` (idempotent via unique constraint)
  - If asset was ORPHAN/DELETION_ELIGIBLE → revert to ACTIVE, clear orphaned_at
  - Update `s3_assets.updated_at`
  - Unit tests

- [x] **1.6** Implement `detach(tenant, asset_id, entity_type, entity_id)`
  - DELETE from `s3_asset_references`
  - Count remaining references
  - If zero → set status=ORPHAN, orphaned_at=NOW()
  - Return updated asset with reference_count
  - Unit tests

- [x] **1.7** Implement `replace(tenant, entity_type, entity_id, old_asset_id, new_asset_id)`
  - Within `db.transaction()`: detach old + attach new
  - Rollback on failure
  - Unit tests

- [x] **1.8** Implement `get_asset(tenant, asset_id)`
  - Query s3_assets + s3_asset_references
  - Generate presigned URL (with caching via `_get_presigned_url`)
  - Return metadata + URL + references
  - Unit tests

- [x] **1.9** Implement `_upload_raw` and `_delete_raw`
  - Thin wrappers around boto3 `put_object` / `delete_object`
  - Error handling, logging
  - Unit tests with mocked boto3

## Phase 2: Delete Lifecycle + Retention (Req 5, 10)

**Dependencies:** Phase 1
**Estimated time:** 2-3 days

- [x] **2.1** Register retention parameters in `ParameterService.CODE_DEFAULTS`
  - Namespace `asset_retention`, keys: `invoices_days`, `branding_days`, `templates_days`, `landing_pages_days`, `landing_pages_media_days`
  - Implement `_get_retention_days(tenant, category, media_type)` — resolution order: asset override → tenant param → system default

- [x] **2.2** Implement `transition_eligible(tenant)`
  - Query ORPHANs where `orphaned_at + retention < NOW()`
  - UPDATE status → DELETION_ELIGIBLE
  - Return count of transitioned assets

- [x] **2.3** Implement `delete_asset(tenant, asset_id, approved_by)`
  - SELECT FOR UPDATE (lock row)
  - Verify status = ORPHAN or DELETION_ELIGIBLE
  - Verify zero references (reference guard)
  - Call `_delete_raw(bucket, s3_key)`
  - DELETE from s3_asset_references + s3_assets
  - Audit log
  - Return success/failure

- [x] **2.4** Implement `force_delete(tenant, asset_id, operator, reason)`
  - Bypass reference guard
  - Full audit entry with reference_count, operator, reason
  - Only callable by admin_manage role (enforced at route level)

- [x] **2.5** Unit tests for full lifecycle: ACTIVE → ORPHAN → DELETION_ELIGIBLE → deleted
  - Test re-activation (attach while ORPHAN → back to ACTIVE)
  - Test reference guard blocks deletion
  - Test retention period calculation

## Phase 3: Reconciliation (Req 6)

**Dependencies:** Phase 1, Phase 2
**Estimated time:** 2-3 days

- [x] **3.1** Implement `run_reconciliation(tenant)` — Phase 1: S3 scan
  - List all objects in `{tenant}/` across both buckets
  - Compare against `s3_assets WHERE administration = tenant`
  - Identify unregistered objects and missing objects

- [x] **3.2** Implement reconciliation Phase 2: Reference verification
  - For each `s3_asset_references` row, check entity existence via ENTITY_TYPE_REGISTRY
  - Remove stale references
  - Update orphan status where refs drop to zero

- [x] **3.3** Implement reconciliation Phase 3: Transition eligible
  - Call `transition_eligible(tenant)` as final step

- [x] **3.4** Implement reconciliation report format
  - Store results in memory/cache for UI retrieval
  - Return summary: total, consistent, unregistered, missing, stale, newly_eligible

- [x] **3.5** SSE progress events for long-running scans
  - Follow existing SSE pattern in codebase
  - Phases: scanning_s3, checking_registry, verifying_references, transitioning, complete

- [x] **3.6** Entity Type Registry — module-level dict `ENTITY_TYPE_REGISTRY`
  - Entries for: invoice, branding, landing_page, template, report, zzp_invoice
  - Skip unknown entity_types with logged warning

## Phase 4: API Routes (Req 12, 13)

**Dependencies:** Phase 1, Phase 2, Phase 3
**Estimated time:** 3-4 days

- [x] **4.1** Create `backend/src/routes/media_asset_routes.py`
  - Blueprint: `media_asset_bp = Blueprint('media_assets', __name__, url_prefix='/api/assets')`
  - Register in `app.py`

- [x] **4.2** Regular user endpoints
  - `POST /api/assets/upload` — multipart upload, calls `store_and_register`
  - `GET /api/assets/<asset_id>` — calls `get_asset`
  - `POST /api/assets/<asset_id>/attach` — calls `attach`
  - `POST /api/assets/<asset_id>/detach` — calls `detach`
  - `POST /api/assets/replace` — calls `replace`
  - Permissions: module-specific (authenticated user)

- [x] **4.3** Asset search endpoint (for Asset Picker)
  - `GET /api/assets/search` — query params: q, category, media_type, sort, order, page, page_size
  - Implement `search_assets(tenant, filters)` in service
  - Paginated results with presigned URLs for images
  - Permission: any authenticated user

- [x] **4.4** Tenant admin endpoints
  - `GET /api/assets/dashboard` — summary stats
  - `POST /api/assets/scan` — trigger reconciliation (async + SSE)
  - `GET /api/assets/scan/<scan_id>/status` — SSE stream
  - `POST /api/assets/approve-delete` — bulk approve deletion
  - `POST /api/assets/import` — import unregistered objects
  - `GET /api/assets/duplicates` — list duplicate hash groups
  - `POST /api/assets/merge-duplicates` — merge duplicates
  - Permission: `storage_manage`

- [x] **4.5** Retention settings endpoints
  - `GET /api/assets/retention-settings` — resolved values with source indicator
  - `PUT /api/assets/retention-settings` — update tenant overrides
  - Permission: `storage_manage`

- [x] **4.6** System admin endpoints
  - `POST /api/assets/force-delete` — emergency delete
  - `POST /api/assets/migrate` — full migration trigger
  - `GET /api/assets/admin/tenants` — cross-tenant stats
  - Permission: `admin_manage`

- [x] **4.7** API tests for all endpoints (happy path + error cases + permission checks)

## Phase 5: Legacy Import + Reference Discovery (Req 8, 11)

**Dependencies:** Phase 1, Phase 4
**Estimated time:** 2-3 days

- [x] **5.1** Implement `import_legacy_assets(tenant, category)`
  - List S3 objects under `{tenant}/{category}/`
  - Skip objects already in `s3_assets` (match on s3_key)
  - INSERT new rows with status=ACTIVE, migrated_at=NOW()
  - Detect media_type from extension/content-type
  - Return summary report

- [x] **5.2** Implement reference discovery for invoices
  - Scan `mutaties` for `Ref3` (gdrive_url/s3_key) matching registered s3_keys
  - INSERT into `s3_asset_references` (entity_type='invoice', entity_id=mutaties.ID)

- [x] **5.3** Implement reference discovery for branding
  - Scan `parameter_values` where namespace='branding' for S3 key values
  - INSERT into `s3_asset_references` (entity_type='branding', entity_id='{tenant}:{key}')

- [x] **5.4** Implement reference discovery for landing pages
  - Scan `landing_pages` JSON content for S3 keys or asset URLs
  - INSERT into `s3_asset_references` (entity_type='landing_page', entity_id=landing_pages.id)

- [x] **5.5** Implement reference discovery for templates
  - Scan `parameter_values` where namespace='templates' for S3 key values
  - INSERT into `s3_asset_references` (entity_type='template', entity_id='{template_key}')

- [x] **5.6** Set status ORPHAN (orphaned_at=migration timestamp) for imported assets with zero discovered references

- [x] **5.7** Integration test: run import on test data, verify registry + references match S3 contents

## Phase 6: Code Path Migration (Req 9, 11)

**Dependencies:** Phase 1, Phase 5
**Estimated time:** 4-5 days

- [x] **6.1** Migrate `routes/storage.py` — logo upload
  - Replace direct `boto3.put_object` with `asset_svc.store_and_register(...)`
  - entity_type='branding', entity_id=f'{tenant}:company_logo'
  - Update `parameter_values` with new s3_key from `result['asset']['s3_key']`
  - Test: upload logo, verify asset registered + reference attached

- [x] **6.2** Migrate `services/invoice_service.py` — invoice PDF upload
  - Replace `storage.upload(...)` with `asset_svc.store_and_register(...)`
  - entity_type='invoice', entity_id=str(mutatie_id)
  - Use `result['asset']['s3_key']` where s3_key is stored in mutaties
  - Test: upload invoice, verify asset + reference

- [x] **6.3** Migrate `routes/missing_invoices_routes.py` — missing invoice upload
  - Same pattern as 6.2
  - Test: upload missing invoice file

- [x] **6.4** Migrate `routes/zzp_routes.py` — ZZP invoice upload
  - Replace StorageProvider.upload with `asset_svc.store_and_register(...)`
  - entity_type='zzp_invoice', entity_id=str(invoice_id)
  - Test: generate ZZP invoice, verify asset + reference

- [x] **6.5** Migrate `services/landing_page_publish_service.py` — publish
  - Replace direct `self._s3.put_object` for landing.json and index.html
  - Use `asset_svc.store_and_register(...)` with category='landing-pages', media_type='web_content'
  - entity_type='landing_page', entity_id=str(page_id)
  - Use `result['asset']['s3_key']` for storing the published URL reference

- [x] **6.6** Migrate `services/landing_page_publish_service.py` — unpublish
  - Replace direct `self._s3.delete_object` with `asset_svc.detach(...)` + `asset_svc.delete_asset(...)`
  - Only delete assets that become orphaned after detach
  - Test: publish → unpublish → verify assets orphaned/deleted

- [x] **6.7** Migrate `services/output_service.py` — report output
  - Replace StorageProvider.upload with `asset_svc.store_and_register(...)`
  - entity_type='report', entity_id=f'{report_type}:{timestamp}'
  - Test: generate report, verify asset + reference

- [x] **6.8** Migrate `routes/landing_page_routes.py` — landing page image upload
  - Replace direct `boto3.put_object` with `asset_svc.store_and_register(...)`
  - category='landing-pages', entity_type='landing_page'
  - Test: upload image for landing page

- [x] **6.9** Refactor `StorageProvider` interface
  - Make `upload()` and `delete()` log deprecation warnings
  - Add `_upload_raw()` and `_delete_raw()` as internal methods
  - Keep public `download()`, `list_files()` unchanged
  - Folder marker in `storage_resolver.py` uses `_upload_raw()` directly (excluded from registry)

- [x] **6.10** Update all tests that mock StorageProvider.upload/delete to use new paths

## Phase 7: Verification + Architectural Enforcement (Req 11 Phase 3)

**Dependencies:** Phase 6
**Estimated time:** 1-2 days

- [x] **7.1** Create architectural test `tests/architecture/test_no_direct_s3_writes.py`
  - Scan all .py files under `src/` for `put_object`, `delete_object`, `copy_object`
  - Allow-list: media_asset_service.py, s3_shared_storage.py, s3_tenant_storage.py, storage_resolver.py (.folder only)
  - Fail CI if any other file contains these calls

- [x] **7.2** Run post-migration reconciliation per tenant
  - Verify: zero unregistered S3 objects
  - Verify: zero missing S3 objects
  - Verify: all app-data references have corresponding `s3_asset_references` rows
  - Produce discrepancy report if issues found

- [x] **7.3** Remove deprecation shim from StorageProvider
  - Delete public `upload()` and `delete()` methods
  - Only `_upload_raw()` and `_delete_raw()` remain (internal)
  - Verify all tests pass

## Phase 8: Frontend — Asset Picker (Req 13)

**Dependencies:** Phase 4 (search endpoint)
**Estimated time:** 3-4 days

- [x] **8.1** Create reusable `AssetPicker` modal component
  - Grid layout with thumbnail previews / file icons
  - Search bar + category/media_type filters + sort dropdown
  - Pagination (20 per page)
  - Props: `onSelect(asset)`, `defaultCategory`, `defaultMediaType`, `allowedMediaTypes`

- [x] **8.2** Create `useAssetSearch` hook
  - Calls `GET /api/assets/search` with debounced query
  - Manages pagination state
  - Returns { assets, loading, error, page, setPage, setFilters }

- [x] **8.3** Integrate Asset Picker into upload controls
  - Add "Upload new" / "Choose existing" toggle wherever file upload exists
  - Landing page editor, branding settings, invoice attachment
  - Context-aware default filters per integration point

- [x] **8.4** Duplicate detection notification
  - After upload, check `result.duplicate_of`
  - Show non-blocking toast: "This file matches '{filename}'. Merge in Asset Admin."

## Phase 9: Frontend — Tenant Admin Asset Dashboard (Req 12)

**Dependencies:** Phase 4 (admin endpoints), Phase 3 (reconciliation)
**Estimated time:** 4-5 days

- [x] **9.1** Create Asset Administration page route (`/admin/assets`)
  - Permission gate: `storage_manage`
  - Dashboard tab with summary stats from `GET /api/assets/dashboard`

- [x] **9.2** Scan workflow UI
  - "Start Scan" button → `POST /api/assets/scan`
  - Progress bar with SSE events
  - Results grouped by category (healthy, orphaned, deletion_eligible, unregistered, missing, stale)

- [x] **9.3** Deletion approval workflow
  - Table of DELETION_ELIGIBLE assets with select checkboxes
  - Actions: Approve deletion, Extend retention, Re-attach
  - Confirmation dialog for compliance-sensitive categories (invoices)
  - Bulk action → `POST /api/assets/approve-delete`

- [x] **9.4** Unregistered objects management
  - Table of unregistered S3 objects
  - Actions: Import to registry, Delete from S3
  - Explicit confirmation for delete

- [x] **9.5** Retention settings panel
  - Show current values per category (value + source indicator)
  - Inline edit with save → `PUT /api/assets/retention-settings`

- [x] **9.6** Duplicates tab
  - List groups of assets with matching content_hash
  - Merge action: keep one, re-attach references, delete duplicate

- [x] **9.7** Storage summary view
  - Table: count + total size per category
  - Orphan summary: count, total size, oldest orphan
  - Top 10 largest orphans

## Notes

- Total estimated effort: 25-33 days
- Phases 1-4 are the core backend — deployable independently
- Phases 5-7 are migration — one-time operation per environment
- Phases 8-9 are frontend — can run in parallel with Phase 5-7
- Each phase is independently testable and deployable
- Migration runs in "dual mode" during Phase 6 — old paths still work but log deprecation warnings
