# Requirements Document

## Introduction

The Media Asset Management Service treats all S3-stored assets as first-class domain objects with explicit lifecycle management. Instead of storing S3 keys directly in application data, assets are registered in a central MySQL Asset Registry (tables `s3_assets` and `s3_asset_references`) with tracked references. This enables safe cleanup of orphaned assets, consistency reconciliation between S3 and application data, and a clear upload-to-deletion lifecycle across all tenant contexts.

The service manages assets across multiple media types (images, videos, documents, web content) stored in the project's S3 buckets, organized by asset category (invoices, branding, templates, landing-pages).

### Scope

- This service manages ALL objects in S3 buckets defined within the myAdmin project: `myadmin-shared-{env}` and `myadmin-public-pages-{env}`
- This includes binary assets (images, PDFs, videos) AND generated web content (HTML, JSON files) stored in these buckets
- Other projects or services that may access the shared bucket are out of scope
- Future cross-project integration is acknowledged but not addressed in this version

### Out of Scope

- **Google Drive files** — invoice PDFs stored in Google Drive for legacy tenants are managed by the existing `GoogleDriveService`, not this Asset_Service
- **S3 folder markers** — zero-byte `.folder` objects used for folder structure creation are infrastructure metadata, not content assets. They are excluded from registry tracking but the Asset_Service still controls their creation via `_upload_raw` to prevent unmanaged writes
- **In-memory generated content** — transient data like API responses, SSE streams, or report previews that never persist to S3
- **External CDN caches** — CloudFront cached copies of public-pages assets are managed by CDN invalidation, not the Asset_Service

### Safety Model

The service uses a two-layer safety model:

1. **Asset Registry with references** — manages normal asset lifecycle (active/orphan/deletion-eligible) with reference guard preventing deletion of assets in use
2. **Periodic Reconciliation** — catches bugs and data inconsistencies between S3, registry, and application data; presents findings to tenant administrator for resolution

## Glossary

- **Asset_Service**: The backend service module responsible for media asset lifecycle operations (upload, register, attach, detach, replace, get, delete, reconcile, import)
- **Asset_Registry**: The MySQL tables (`s3_assets` and `s3_asset_references`) storing asset metadata, status, and reference information
- **Reference**: An explicit link between an asset and a consuming entity (landing page, invoice, member avatar, etc.), stored as a row in the `s3_asset_references` table
- **Orphan_Asset**: A registered asset with zero references, marked with status ORPHAN and an orphaned_at timestamp. Becomes DELETION_ELIGIBLE after the retention period elapses.
- **Deletion_Eligible**: An orphan asset whose retention period has elapsed. It is presented to the tenant administrator for approval but is NOT automatically deleted.
- **Retention_Period**: The tenant-configurable duration an Orphan_Asset must remain unreferenced before becoming eligible for deletion. Configured per tenant via `parameter_values` with system defaults as fallback.
- **Reconciliation_Job**: A periodic process that verifies consistency between S3 objects, Asset_Registry records, and application references
- **Tenant**: An isolated organizational unit in the multi-tenant system, identified by the `administration` value from AWS Cognito JWT
- **Bucket_Configuration**: The service-level configuration defining the S3 buckets managed by this project. The two buckets are `myadmin-shared-{env}` (for invoices, branding, templates) and `myadmin-public-pages-{env}` (for landing page assets served via CloudFront). The Asset_Service resolves which bucket to use based on asset category.
- **Asset_Consumer**: Any application entity that can reference an asset (landing page, invoice record, member profile, template, etc.)
- **Asset_Category**: A classification that determines the storage bucket and path prefix for an asset. Categories are: `invoices` (PDF documents in shared bucket under `{tenant}/invoices/`), `branding` (logos and letterheads in shared bucket under `{tenant}/branding/`), `templates` (invoice and report templates in shared bucket under `{tenant}/templates/`), and `landing-pages` (HTML, JSON, images, and videos in public-pages bucket under `{slug}/`)
- **Media_Type**: The broad classification of a file by content: `image` (JPEG, PNG, WebP, GIF — max 10 MB), `video` (MP4, WebM — max 100 MB), `document` (PDF — max 25 MB), or `web_content` (HTML, JSON — max 5 MB)

## Requirements

### Requirement 1: Asset Upload and Registration

**User Story:** As a tenant user, I want to upload media assets that are immediately registered and tracked in the system, so that every asset in S3 is managed from the moment it is stored.

#### Acceptance Criteria

1. WHEN a tenant user or system process uploads an asset, THE Asset_Service SHALL use `store_and_register` to: write the file to S3 at the category-specific path, insert a row in `s3_assets` with status ACTIVE, and optionally attach a reference — all in a single operation
2. THE Asset*Service SHALL generate a unique asset id using the format `ast*` followed by a ULID for each registered asset
3. THE Asset_Service SHALL validate that the uploaded file belongs to an allowed Media_Type by verifying both the file extension and the file content headers (magic bytes), where allowed types are: images (JPEG, PNG, WebP, GIF), videos (MP4, WebM), documents (PDF), and web content (HTML, JSON)
4. THE Asset_Service SHALL validate that the uploaded file does not exceed the size limit for its Media_Type: 10 MB for images, 100 MB for videos, 25 MB for documents, and 5 MB for web content
5. IF a file with an unsupported type is uploaded, THEN THE Asset_Service SHALL reject the upload with an error message indicating the detected file type and listing the allowed types grouped by Media_Type category
6. IF a file exceeding the maximum size for its Media_Type is uploaded, THEN THE Asset_Service SHALL reject the upload with an error message indicating the file size, the detected Media_Type, and the applicable size limit
7. IF the upload request contains no file or an empty file body, THEN THE Asset_Service SHALL reject the request with an error message indicating that a file is required
8. WHEN `store_and_register` is called with entity_type and entity_id, THE Asset_Service SHALL insert both the `s3_assets` record and the `s3_asset_references` row, so the asset is immediately ACTIVE with a reference
9. WHEN `store_and_register` is called without entity_type/entity_id (e.g., user uploads but hasn't saved the parent form yet), THE asset SHALL be registered with status ACTIVE and zero references. It becomes ORPHAN if the user abandons the form and the reference is never attached — handled by the normal lifecycle (Req 5 Delete Asset)

### Requirement 2: Attach Asset Reference

**User Story:** As a tenant user, I want assets to be linked to the content that uses them, so that the system knows which assets are actively in use.

#### Acceptance Criteria

1. WHEN content is saved with an asset reference, THE Asset_Service SHALL insert a row in the `s3_asset_references` table containing the asset_id, entity_type, and entity_id
2. THE Asset_Service SHALL update the referenced asset's updated_at timestamp in the `s3_assets` table when a reference is attached
3. WHEN a reference is attached to an Orphan_Asset, THE Asset_Service SHALL change the asset status back to ACTIVE and clear the orphaned_at timestamp
4. IF an attach operation references a non-existent asset_id, THEN THE Asset_Service SHALL return an error indicating the asset does not exist
5. THE Asset_Service SHALL enforce that all attach operations are scoped to the authenticated tenant
6. IF an attach operation specifies an entity_type and entity_id combination that already exists for the given asset_id, THEN THE Asset_Service SHALL treat the operation as idempotent and return success without creating a duplicate entry, enforced by the unique constraint on (asset_id, entity_type, entity_id)

#### Replace Asset (Convenience Operation)

7. WHEN a replace request is received specifying entity_type, entity_id, old_asset_id, and new_asset_id, THE Asset_Service SHALL atomically detach old_asset_id from the entity and attach new_asset_id to the entity within a single database transaction
8. IF the attach of new_asset_id fails during a replace operation, THEN THE Asset_Service SHALL roll back the entire transaction so that the old_asset_id reference remains intact
9. WHEN a replace request is received with old_asset_id set to null or empty, THE Asset_Service SHALL treat the operation as a simple attach of new_asset_id to the specified entity
10. IF the old_asset_id specified in a replace request does not have a matching reference for the given entity_type and entity_id, THEN THE Asset_Service SHALL return an error indicating the existing reference was not found and SHALL NOT attach the new asset

### Requirement 3: Detach Asset Reference

**User Story:** As a tenant user, I want assets to be unlinked when I remove them from content, so that unused assets can be identified and cleaned up.

#### Acceptance Criteria

1. WHEN a detach request is received specifying an asset_id, entity_type, and entity_id, THE Asset_Service SHALL delete the matching row from the `s3_asset_references` table and return the updated asset record including the current reference count and status
2. WHEN the last reference to an asset is removed, THE Asset_Service SHALL change the asset status to ORPHAN and record the current timestamp as orphaned_at
3. WHILE an asset still has remaining references after a detach, THE Asset_Service SHALL keep the asset status as ACTIVE
4. THE Asset_Service SHALL enforce that all detach operations are scoped to the authenticated tenant
5. IF a detach operation references a non-existent asset_id or a reference entry that does not match any stored row in `s3_asset_references` for that asset, THEN THE Asset_Service SHALL return an error indicating the resource does not exist

### Requirement 4: Retrieve Asset

**User Story:** As a tenant user, I want to retrieve asset metadata and access URLs, so that I can display or download assets in my content.

#### Acceptance Criteria

1. WHEN a tenant user requests an asset by asset_id, THE Asset_Service SHALL return the asset metadata including id, s3_key, mime_type, file_size, category, media_type, original_filename, status, created_at, and associated references from the `s3_asset_references` table
2. WHEN a tenant user requests an asset by asset_id, THE Asset_Service SHALL include a presigned S3 URL valid for 60 minutes in the response
3. THE Asset_Service SHALL enforce that asset retrieval is scoped to the authenticated tenant
4. IF a tenant user requests an asset belonging to a different tenant, THEN THE Asset_Service SHALL return a not-found error without revealing the asset exists
5. IF a tenant user requests an asset_id that does not exist in the `s3_assets` table, THEN THE Asset_Service SHALL return a not-found error
6. WHILE an asset has status ORPHAN, THE Asset_Service SHALL still permit retrieval of its metadata and presigned URL until the asset is permanently deleted

#### Presigned URL Performance

7. THE Asset_Service SHALL cache generated presigned URLs in memory (or a fast cache layer) with a TTL of 50 minutes, so that repeated requests for the same asset within the validity window do not re-compute the S3 signature
8. FOR assets in the `landing-pages` category served via CloudFront, THE Asset_Service SHALL return CloudFront-signed URLs instead of S3 presigned URLs, leveraging the existing CDN distribution for lower latency and better cache behavior
9. WHEN the Asset Picker (Req 13) returns paginated search results, THE Asset_Service SHALL generate presigned thumbnail URLs in batch (not per-item sequentially) to minimize latency for grid displays

### Requirement 5: Delete Asset (Tenant Admin Approval Required)

**User Story:** As a tenant administrator, I want orphaned assets to be flagged as eligible for deletion after the retention period, so that I can review and approve their removal with full visibility into what is being cleaned up.

**Principle:** Deletion is NEVER automatic. The system detects, proposes, and presents. The tenant administrator decides.

#### Acceptance Criteria

##### Lifecycle: ACTIVE → ORPHAN → DELETION_ELIGIBLE → Deleted

1. WHEN the last reference to an asset is removed, THE Asset_Service SHALL change status to ORPHAN and record orphaned_at (same as Req 3 AC 2)
2. WHEN an Orphan_Asset has exceeded its applicable retention period, THE Asset_Service SHALL change its status to DELETION_ELIGIBLE. No S3 object is deleted at this point.
3. IF an asset regains a reference while in ORPHAN or DELETION_ELIGIBLE status, THE Asset_Service SHALL revert status to ACTIVE and clear orphaned_at
4. ONLY WHEN a tenant administrator explicitly approves deletion (via the Asset Administration UI, Req 12) SHALL the Asset_Service delete the S3 object and remove the registry record

##### Retention Policy (Parameter-Driven per Tenant)

5. THE retention period SHALL be configured per tenant via the existing `parameter_values` system, with parameters scoped by category:
   - Parameter group: `asset_retention`
   - Parameter keys: `invoices_days`, `branding_days`, `templates_days`, `landing_pages_days`
   - System defaults (used when no tenant override exists): invoices=2555 (7 years), branding=30, templates=90, landing-pages=7
6. THE tenant administrator SHALL be able to configure retention periods for their tenant via the Asset Administration UI or the existing parameter management interface
7. THE retention_days column in `s3_assets` MAY override the tenant-level parameter for individual assets (e.g., a specific invoice PDF granted shorter retention after explicit approval)
8. WHEN evaluating whether an orphan is eligible for deletion, THE Asset_Service SHALL resolve the applicable retention in this order: asset-level `retention_days` → tenant-level parameter → system default

##### Deletion Execution

9. WHEN a tenant administrator approves deletion, THE Asset_Service SHALL verify within the same transaction that the asset still has zero references in `s3_asset_references` before performing the S3 deletion and registry removal
10. IF the asset has regained a reference between the eligibility check and the approval, THE Asset_Service SHALL skip that asset and report it as "re-activated"
11. WHEN an asset is successfully deleted, THE Asset_Service SHALL log the deletion with: asset_id, administration, bucket, category, approving user email, and deletion timestamp
12. IF a tenant administrator requests deletion of an asset that has one or more active references, THEN THE Asset_Service SHALL reject the request with an error indicating the asset is still in use and listing the number of active references
13. IF the S3 object deletion fails, THEN THE Asset_Service SHALL retain the `s3_assets` record, report the failure, and NOT leave the system in an inconsistent state
14. THE UI SHALL display a warning when the tenant administrator approves deletion of an asset in a compliance-sensitive category (invoices) whose retention period has not yet elapsed, requiring explicit confirmation

### Requirement 6: Reconciliation

**User Story:** As a tenant administrator, I want periodic consistency checks between S3, the Asset Registry, and application data, so that inconsistencies are detected and presented for my review.

#### Acceptance Criteria

1. WHEN the Reconciliation_Job executes, THE Asset_Service SHALL scan all buckets defined in the Bucket_Configuration and identify S3 objects under category-specific paths that have no corresponding row in the `s3_assets` table (unregistered S3 objects)
2. WHEN the Reconciliation_Job executes, THE Asset_Service SHALL identify `s3_assets` records where the referenced S3 object does not exist in the bucket stored on the record (missing S3 objects)
3. WHEN the Reconciliation_Job executes, THE Asset_Service SHALL identify rows in `s3_asset_references` pointing to application entities that no longer exist (stale references)
4. WHEN the Reconciliation_Job completes, THE Asset_Service SHALL produce a reconciliation report containing the administration, execution timestamp, and counts of total assets, consistent assets, unregistered S3 objects, missing S3 objects, and stale references
5. THE Reconciliation_Job SHALL be triggerable by the tenant administrator via the Asset Administration UI (Req 12 "Start Scan") and MAY additionally run on a configurable schedule (default: once daily)
6. THE Reconciliation_Job SHALL process assets scoped per tenant (administration) to maintain isolation
7. IF stale references are detected, THEN THE Asset_Service SHALL automatically remove the stale reference rows from `s3_asset_references` and update asset status to ORPHAN with orphaned_at set when zero references remain, or keep status as ACTIVE when references still exist
8. IF the Reconciliation_Job fails mid-execution, THEN THE Asset_Service SHALL log the failure with administration, timestamp, and error details, and SHALL NOT leave partially-processed records in an inconsistent state
9. WHEN unregistered S3 objects or missing S3 objects are detected, THE Reconciliation_Job SHALL report them in the reconciliation report and present them to the tenant administrator for action (import or delete) — no automatic creation or deletion without tenant admin approval

### Requirement 7: Asset Registry Data Model

**User Story:** As a developer, I want a well-defined MySQL schema for the Asset Registry, so that asset data is efficiently queryable and supports all lifecycle operations.

#### Acceptance Criteria

1. THE Asset*Registry SHALL use a table named `s3_assets` with columns: `id` (VARCHAR primary key storing `ast*`+ ULID),`administration`(VARCHAR NOT NULL for tenant isolation),`bucket`(VARCHAR NOT NULL),`s3_key`(VARCHAR NOT NULL),`mime_type`(VARCHAR NOT NULL),`file_size`(BIGINT NOT NULL),`category`(ENUM of`invoices`, `branding`, `templates`, `landing-pages`), `media_type`(ENUM of`image`, `video`, `document`, `web_content`), `original_filename`(VARCHAR NOT NULL),`content_hash`(VARCHAR(64) nullable for SHA-256 duplicate detection),`status`(ENUM of`ACTIVE`, `ORPHAN`, `DELETION_ELIGIBLE` with default`ACTIVE`),`retention_days`(INT nullable — overrides tenant-level retention parameter; NULL uses tenant/system default), `created_at`(DATETIME NOT NULL),`updated_at`(DATETIME),`orphaned_at`(DATETIME), and`migrated_at` (DATETIME)
2. THE Asset_Registry SHALL use a separate table named `s3_asset_references` with columns: `id` (BIGINT AUTO_INCREMENT primary key), `administration` (VARCHAR NOT NULL for tenant isolation — defense-in-depth, must match parent asset's administration), `asset_id` (VARCHAR NOT NULL referencing `s3_assets.id`), `entity_type` (VARCHAR NOT NULL), `entity_id` (VARCHAR NOT NULL), and `created_at` (DATETIME NOT NULL)
3. THE `s3_asset_references` table SHALL define a foreign key from `asset_id` to `s3_assets.id` with ON DELETE CASCADE
4. THE `s3_asset_references` table SHALL define a unique constraint on the combination of (asset_id, entity_type, entity_id) to prevent duplicate references
5. THE `s3_assets` table SHALL include indexes on (administration, status), (administration, category), (status, orphaned_at), and (administration, content_hash) to support efficient tenant-scoped queries, orphan cleanup, and duplicate detection
6. THE `s3_asset_references` table SHALL include an index on (entity_type, entity_id) to support efficient lookup of all assets referenced by a given entity

### Requirement 8: Legacy Asset Import

**User Story:** As a system operator, I want to register existing S3 objects in the Asset Registry without re-uploading them, so that all project assets are tracked with consistent lifecycle management.

#### Acceptance Criteria

1. WHEN the import process executes for a specified tenant and asset category, THE Asset_Service SHALL scan the corresponding S3 bucket and prefix (e.g., `{tenantId}/invoices/` in the shared bucket) and identify objects not already registered in the `s3_assets` table
2. WHEN an unregistered S3 object is found during import, THE Asset_Service SHALL insert a row in `s3_assets` with status ACTIVE, the detected mime_type, file_size, bucket, s3_key, category, media_type, original_filename derived from the S3 key, and migrated_at set to the current timestamp
3. THE Asset_Service SHALL NOT re-upload, move, copy, or modify existing S3 objects during the import process
4. WHEN an import creates an `s3_assets` record, THE Asset*Service SHALL generate a unique id using the format `ast*` followed by a ULID
5. THE Asset_Service SHALL support incremental import by skipping S3 objects whose s3_key already matches an existing row in `s3_assets`, allowing the import to run multiple times safely without creating duplicate records
6. WHEN the import process completes, THE Asset_Service SHALL return a summary report containing the administration, category, total objects scanned, newly registered count, and already-registered count
7. THE Asset_Service SHALL enforce that all import operations are scoped to the authenticated tenant
8. IF an S3 object cannot be classified into a valid Media_Type based on its extension and content headers, THEN THE Asset_Service SHALL skip the object and include it in the summary report as an unclassified item

### Requirement 9: Exclusive Asset Gateway

**User Story:** As a system architect, I want all S3 write and delete operations to be routed exclusively through the Asset_Service, so that no code path can create unregistered objects or delete referenced objects.

#### Acceptance Criteria

1. THE Asset_Service SHALL be the sole gateway for all S3 `put_object`, `copy_object`, and `delete_object` operations on buckets defined in the Bucket_Configuration. No application code outside the Asset_Service SHALL directly call these S3 operations on managed buckets.
2. THE `S3SharedStorage` and `S3TenantStorage` classes SHALL be refactored to delegate all write and delete operations through the Asset_Service, replacing their current direct `put_object` and `delete_object` calls with calls to the Asset_Service's `store_and_register` and `delete_asset` methods
3. THE `StorageProvider` interface SHALL expose only read operations (`download`, `list_files`, `get_presigned_url`) as public methods. Write and delete methods SHALL be marked as internal (`_upload_raw`, `_delete_raw`) and SHALL only be callable by the Asset_Service
4. WHEN any code path attempts to store a file in an S3 bucket defined in the Bucket_Configuration, THE Asset_Service SHALL ensure the resulting object is registered in `s3_assets` before returning success to the caller
5. ALL existing direct S3 callers identified during the code audit SHALL be migrated to use the Asset_Service. The specific files and their migration approach are documented in Requirement 11 Phase 2.
6. IF application code outside the Asset_Service attempts to call `put_object` or `delete_object` on a managed bucket, THE system SHALL enforce this through architectural tests (integration test that scans for direct boto3 S3 write/delete calls outside the Asset_Service module) that fail the CI build
7. THE Asset_Service SHALL expose `store_and_register` as the primary method for all S3 writes — it combines S3 upload + registry insertion + optional reference attachment in a single atomic operation
8. WHEN the `store_and_register` method is called, THE Asset_Service SHALL write the object to S3, insert a row in `s3_assets` with status ACTIVE, and optionally insert a row in `s3_asset_references` if entity_type and entity_id are provided, all within a single logical transaction (DB commit only after S3 write succeeds)
9. IF the S3 write in `store_and_register` fails, THEN THE Asset_Service SHALL NOT insert any registry records and SHALL return an error to the caller
10. IF the database commit fails AFTER a successful S3 write in `store_and_register`, THEN THE Asset_Service SHALL log the orphaned S3 key (bucket, key, timestamp) to an error log, and the Reconciliation_Job (Req 6) SHALL detect the unregistered object and report it for resolution. The system accepts this as an edge case handled by the reconciliation safety net.
11. THE Asset_Service SHALL provide a `delete_s3_object` internal method that is the only code path permitted to execute S3 `delete_object`. This method SHALL be called exclusively from `delete_asset` (Req 5) and the Reconciliation_Job (Req 6) after all safety checks pass.
12. THE Asset_Service SHALL enforce that all S3 operations are scoped to the authenticated tenant's prefix (e.g., `{tenantId}/invoices/`, `{tenantId}/branding/`). IF a request resolves to an S3 key outside the authenticated tenant's prefix, THE Asset_Service SHALL reject it with an authorization error. This is the only asset-specific tenant isolation rule; all other multi-tenant isolation (JWT validation, DB scoping) is inherited from the platform's `@cognito_required` and `@tenant_required` decorators.

### Requirement 10: Delete Protection (Reference Guard)

**User Story:** As a tenant user, I want assurance that no asset currently in use can be deleted from S3, so that my content never has broken image or document links.

#### Acceptance Criteria

1. BEFORE any S3 object deletion is executed, THE Asset_Service SHALL query `s3_asset_references` and verify that zero rows exist for the target asset_id within the same database transaction
2. IF the reference count is greater than zero at deletion time, THEN THE Asset_Service SHALL abort the deletion, return an error listing the number of active references and their entity_types, and SHALL NOT call `delete_object` on S3
3. WHEN an application entity is deleted (e.g., a landing page is unpublished, an invoice record is removed, a template is deleted), THE consuming module SHALL call `Asset_Service.detach(asset_id, entity_type, entity_id)` for each asset referenced by that entity BEFORE completing the entity deletion
4. IF a consuming module deletes an entity without detaching its asset references, THE Reconciliation_Job (Req 6) SHALL detect the stale references and clean them up, but THE Asset_Service SHALL NOT allow the S3 object to be deleted until the stale references are resolved (either cleaned by reconciliation or manually)
5. THE `S3SharedStorage.delete()` and `S3TenantStorage.delete()` public methods SHALL be removed or replaced with a method that delegates to `Asset_Service.delete_asset()`, which enforces the reference guard
6. WHEN the landing_page_publish_service unpublishes a page, IT SHALL call `Asset_Service.detach` for all assets referenced by that landing page and then call `Asset_Service.delete_asset` only for assets that become orphaned, rather than directly calling `delete_object`
7. THE Asset_Service SHALL support a `force_delete` parameter available only to system operators (admin role), which bypasses the reference guard, logs a warning with the asset_id, reference count, and operator identity, and proceeds with S3 deletion and registry removal. This is intended solely for emergency recovery.
8. WHEN a `force_delete` is executed, THE Asset_Service SHALL log an audit entry containing: asset_id, administration, operator email, reference count at time of deletion, reason (if provided), and timestamp

### Requirement 11: Migration of Existing S3 Operations

**User Story:** As a system operator, I want all existing S3 objects and code paths migrated to the Asset_Service model, so that the entire system operates under unified asset lifecycle management with no legacy bypass paths.

#### Acceptance Criteria

##### Phase 1: Registry Population (Legacy Import)

1. WHEN the migration is initiated, THE Asset_Service SHALL execute the Legacy Asset Import (Req 8) for ALL tenants and ALL asset categories (invoices, branding, templates, landing-pages) to register every existing S3 object in the `s3_assets` table
2. FOR each registered legacy asset, THE Asset_Service SHALL scan application data tables to discover existing references and insert corresponding rows in `s3_asset_references`:
   - Invoice records: scan `mutaties` for `gdrive_url` or `s3_key` columns matching the asset's `s3_key` → entity_type=`invoice`, entity_id=`mutaties.id`
   - Branding assets: scan tenant configuration or `parameter_values` for S3 keys matching branding paths → entity_type=`branding`, entity_id=`{tenant}:{asset_name}`
   - Landing page assets: scan `landing_pages` table for JSON content containing S3 keys or asset URLs → entity_type=`landing_page`, entity_id=`landing_pages.id`
   - Templates: scan template configuration for S3 key references → entity_type=`template`, entity_id=`{template_identifier}`
3. WHEN a legacy asset has been registered and its references discovered, THE Asset_Service SHALL set the asset status to ACTIVE if references were found, or ORPHAN with orphaned_at set to the migration timestamp if no references were found
4. THE migration process SHALL produce a summary report per tenant containing: total S3 objects scanned, newly registered, already registered, references created, orphans detected, and unclassified/skipped objects

##### Phase 2: Code Path Migration

5. ALL existing upload code paths identified during the code audit SHALL be refactored to call `Asset_Service.store_and_register()`. The specific callers to migrate:
   - `routes/storage.py` — branding logo upload (direct `boto3.put_object`) → `store_and_register`
   - `routes/landing_page_routes.py` — landing page image upload (direct `boto3.put_object`) → `store_and_register`
   - `services/landing_page_publish_service.py` — HTML/JSON publish (direct `put_object`) → `store_and_register` with media_type=`web_content`
   - `services/landing_page_publish_service.py` — unpublish delete (direct `delete_object`) → `Asset_Service.delete_asset()`
   - `services/invoice_service.py` — invoice PDF upload (via `S3SharedStorage.upload`) → `store_and_register`
   - `routes/missing_invoices_routes.py` — missing invoice upload (via `S3SharedStorage.upload`) → `store_and_register`
   - `routes/zzp_routes.py` — ZZP invoice PDF upload (via StorageProvider) → `store_and_register`
   - `services/output_service.py` — report output upload (via StorageProvider) → `store_and_register`
6. ALL existing delete code paths SHALL be refactored to call `Asset_Service.delete_asset()` which enforces the reference guard (Req 10)
7. EACH migrated code path SHALL attach a reference at the point where the asset is associated with an application entity, using the appropriate entity_type and entity_id for that domain:
   - Invoice upload → attach with entity_type=`invoice`, entity_id=`{mutaties_id}`
   - Logo/branding upload → attach with entity_type=`branding`, entity_id=`{tenant}:{asset_name}`
   - Landing page image/video → attach with entity_type=`landing_page`, entity_id=`{landing_page_id}`
   - Landing page HTML/JSON publish → attach with entity_type=`landing_page`, entity_id=`{landing_page_id}`, media_type=`web_content`
   - Report output → attach with entity_type=`report`, entity_id=`{report_type}:{timestamp}`
   - ZZP invoice → attach with entity_type=`zzp_invoice`, entity_id=`{invoice_id}`
8. THE `services/storage_resolver.py` folder marker creation (`.folder` files) SHALL continue to use the Asset_Service's `_upload_raw` method for S3 writes but SHALL NOT be registered in `s3_assets` — folder markers are infrastructure metadata excluded from asset tracking (see Out of Scope)

##### Phase 3: Verification and Enforcement

9. AFTER all code paths are migrated, AN architectural integration test SHALL be added that scans all Python source files (excluding the Asset_Service module itself and test files) for direct usage of `put_object`, `delete_object`, `copy_object` on S3 clients, and SHALL fail the test suite if any are found
10. THE migration SHALL include a post-migration reconciliation run (Req 6) that verifies: zero unregistered S3 objects exist, zero missing S3 objects exist, and all application data references have corresponding `s3_asset_references` rows
11. IF the post-migration reconciliation detects inconsistencies, THE Asset_Service SHALL produce a detailed discrepancy report and THE migration SHALL NOT be considered complete until all discrepancies are resolved
12. THE migration process SHALL be idempotent — running it multiple times SHALL NOT create duplicate `s3_assets` records or duplicate `s3_asset_references` rows, enforced by the existing unique constraints and s3_key matching logic

### Requirement 12: Role Gates and Tenant Admin Asset Workflow

**User Story:** As a tenant administrator, I want a dedicated workflow to scan my tenant's S3 assets, review analytics on orphaned and unregistered objects, and approve or reject deletions, so that I maintain full control over storage cleanup without needing system-level access.

#### Role Assignment

1. THE system SHALL define three authorization levels for asset operations:
   - **Regular user** (any tenant user with module-specific permissions): May upload, view, and use assets through normal feature workflows (invoices, landing pages, branding). No direct access to the Asset Administration UI.
   - **Tenant administrator** (`tenant_admin` or `storage_manage` permission): May access the Asset Administration UI for their own tenant, trigger scans, review analytics, and approve/reject deletions within their tenant scope.
   - **System administrator** (`admin_manage` permission): May execute cross-tenant operations including full migration (Req 11), force_delete (Req 10 AC 7), reconciliation configuration, and system-wide reports.

#### Tenant Admin Workflow: Scan

2. WHEN a tenant administrator navigates to the Asset Administration page, THE system SHALL display a dashboard showing: total registered assets, active assets, orphaned assets, storage usage by category, and the timestamp of the last scan
3. WHEN a tenant administrator clicks "Start Scan", THE Asset_Service SHALL execute a tenant-scoped reconciliation (Req 8) for the authenticated tenant only, comparing S3 bucket contents against the Asset_Registry and application references
4. THE scan operation SHALL run asynchronously and provide real-time progress updates via Server-Sent Events (SSE), showing: current phase (scanning S3 / checking registry / verifying references), objects processed, and estimated time remaining
5. WHEN the scan completes, THE Asset_Service SHALL present the results in the Asset Administration UI grouped into actionable categories:
   - **Healthy assets**: status ACTIVE, referenced, S3 object exists (no action needed)
   - **Orphaned assets**: status ORPHAN, retention period not yet elapsed (waiting)
   - **Deletion eligible**: status DELETION_ELIGIBLE, retention period elapsed, awaiting tenant admin approval
   - **Unregistered S3 objects**: exist in S3 but not in registry (candidates for import or deletion)
   - **Missing S3 objects**: registered in registry but S3 object not found (broken records to clean up)
   - **Stale references**: reference points to non-existent application entity (auto-cleanable)

#### Tenant Admin Workflow: Review and Approve Deletions

6. THE Asset Administration UI SHALL display deletion-eligible assets in a table with columns: asset_id, original_filename, category, media_type, file_size, orphaned_at, days orphaned, retention status (elapsed/remaining), and a preview thumbnail (for images) or file icon (for documents/videos)
7. THE tenant administrator SHALL be able to select one or more assets and choose from the following actions:
   - **Approve deletion**: permanently deletes the S3 object and removes the registry record (only for DELETION_ELIGIBLE assets)
   - **Extend retention**: resets the orphaned_at timestamp, moving the asset back to ORPHAN status with a fresh retention countdown
   - **Re-attach**: opens a dialog to manually link the asset to an existing entity (entity_type + entity_id), restoring it to ACTIVE status
8. WHEN the tenant administrator approves deletion, THE Asset_Service SHALL verify each asset still has zero references (Req 10 reference guard), then permanently delete the S3 object and remove the registry record
9. IF any selected asset has regained a reference between the scan and the approval action, THE Asset_Service SHALL skip that asset, report it as "re-activated" in the result summary, and proceed with the remaining approved deletions
10. THE Asset Administration UI SHALL display unregistered S3 objects with columns: s3_key, bucket, file_size, last_modified, detected media_type, and allow the tenant administrator to:
    - **Import to registry**: register the object in `s3_assets` (equivalent to Req 8 import for individual objects)
    - **Delete from S3**: permanently remove the unregistered object after confirmation
11. WHEN a tenant administrator requests deletion of an unregistered S3 object, THE Asset_Service SHALL require explicit confirmation (the object is not in the registry so it has no reference guard) and log the deletion with operator identity, s3_key, and timestamp

#### Tenant Admin Workflow: Analytics

12. THE Asset Administration UI SHALL provide a storage summary view showing:
    - Tabular breakdown: asset count and total storage per category (invoices, branding, templates, landing-pages)
    - Orphan summary: count of orphaned assets, total orphan storage, oldest orphan age
    - Top 10 largest orphaned assets (quick wins for space reclamation)
    - Timestamp of last scan and last automated cleanup
13. THE summary data SHALL be computed from the Asset_Registry tables and cached for performance, refreshed on each scan completion
14. FUTURE PHASE: Visual analytics (pie charts, histograms, growth trends) SHALL be added in a subsequent iteration once the core workflow proves useful in practice. This phase is explicitly deferred to reduce initial implementation cost.

#### System Administrator Operations

15. THE system administrator (`admin_manage`) SHALL have access to a cross-tenant view that shows aggregated asset statistics per tenant, with the ability to drill down into any tenant's Asset Administration view
16. THE system administrator SHALL be the only role permitted to:
    - Execute the full migration process (Req 11) across all tenants
    - Use `force_delete` to bypass the reference guard (Req 10 AC 7) — intended solely for emergency recovery of stuck/corrupted records
    - Configure the reconciliation schedule (Req 6 AC 5)
    - Configure system-level default retention periods (tenant administrators configure their own tenant's retention)
17. ALL system administrator actions that modify or delete data SHALL be logged in the audit trail with operator identity, affected tenant, action performed, and timestamp
18. THE system administrator SHALL NOT have authority to approve or execute deletion of a tenant's assets — this is exclusively the tenant administrator's responsibility. The only exception is `force_delete` for emergency recovery.

#### Access Control Enforcement

18. THE Asset Administration API endpoints SHALL enforce role-based access:
    - `GET /api/assets/dashboard` — requires `storage_manage` or `admin_manage`
    - `POST /api/assets/scan` — requires `storage_manage` or `admin_manage`
    - `GET /api/assets/scan/{scan_id}/status` — requires `storage_manage` or `admin_manage`
    - `POST /api/assets/approve-delete` — requires `storage_manage` or `admin_manage`
    - `POST /api/assets/import` — requires `storage_manage` or `admin_manage`
    - `POST /api/assets/force-delete` — requires `admin_manage` only
    - `POST /api/assets/migrate` — requires `admin_manage` only
    - `GET /api/assets/admin/tenants` — requires `admin_manage` only
19. IF a user without sufficient permissions attempts to access a protected Asset Administration endpoint, THE system SHALL return a 403 Forbidden error without revealing the existence of the endpoint's functionality

### Requirement 13: Asset Picker (Browse and Reuse Existing Assets)

**User Story:** As a tenant user, I want to browse and search existing assets in my tenant's registry when adding an image or document to content, so that I can reuse assets already uploaded rather than uploading duplicates.

#### Acceptance Criteria

##### Asset Picker UI Component

1. WHEREVER the application presents a file upload control (landing page editor, branding settings, invoice attachment, template editor), THE system SHALL offer two options side-by-side: "Upload new" and "Choose existing"
2. WHEN a user clicks "Choose existing", THE system SHALL open an Asset Picker modal displaying the tenant's registered assets filtered to the media types applicable to the current context (e.g., only images for a logo field, only PDFs for an invoice attachment)
3. THE Asset Picker modal SHALL display assets as a grid of thumbnail previews (for images) or file-type icons with filenames (for documents/videos), with each tile showing: thumbnail/icon, original_filename, file_size, category, and number of existing references
4. THE Asset Picker SHALL support the following filtering and search capabilities:
   - **Text search**: filter by original_filename (substring match, case-insensitive)
   - **Category filter**: dropdown to filter by asset category (invoices, branding, templates, landing-pages, or all)
   - **Media type filter**: filter by image, video, or document
   - **Sort options**: most recent first (default), filename A-Z, file size, most referenced
5. THE Asset Picker SHALL paginate results (default 20 per page) and support infinite scroll or explicit page navigation
6. WHEN a user selects an asset from the picker, THE system SHALL close the modal and populate the upload field with a reference to the selected asset (showing the thumbnail/filename as confirmation), without re-uploading or copying the S3 object

##### Backend: Asset Search API

7. THE Asset_Service SHALL expose a search endpoint `GET /api/assets/search` that accepts query parameters: `q` (filename search), `category`, `media_type`, `mime_type`, `sort` (created_at|filename|file_size|reference_count), `order` (asc|desc), `page`, `page_size`
8. THE search endpoint SHALL return results scoped to the authenticated tenant and SHALL only return assets with status ACTIVE (not orphaned assets)
9. EACH result item SHALL include: asset_id, original_filename, mime_type, file_size, category, media_type, created_at, reference_count, and a presigned thumbnail URL (for images) or null (for non-image types)
10. THE search endpoint SHALL require any authenticated tenant user permission (no special admin role needed) — asset browsing is a normal user operation

##### Reuse Mechanics (Attach Additional Reference)

11. WHEN a user selects an existing asset from the picker and saves the content, THE system SHALL call `Asset_Service.attach(asset_id, entity_type, entity_id)` to create an additional reference from the new entity to the existing asset — no S3 copy or duplication occurs
12. THE same S3 object MAY have multiple references from different entities (e.g., the same logo used on 3 landing pages), and THE Asset_Service SHALL track each reference independently in `s3_asset_references`
13. WHEN an entity that reuses a shared asset is later deleted or the asset is removed from that entity, THE system SHALL call `Asset_Service.detach` for that specific reference only — other references remain intact and the S3 object is NOT deleted unless zero references remain (standard orphan flow)

##### Duplicate Detection on Upload

14. WHEN a user uploads a new file via "Upload new", THE Asset_Service SHALL compute a SHA-256 hash of the file content and check it against the `content_hash` column in `s3_assets` for the authenticated tenant
15. IF a matching hash is found (identical file content already exists in the registry), THE Asset_Service SHALL complete the upload normally but return a `duplicate_of` field in the response containing the existing asset_id and original_filename
16. THE frontend SHALL display a non-blocking notification: "This file matches an existing asset '{original_filename}'. You can merge them in the Asset Administration." The upload flow SHALL NOT be interrupted or require a modal decision.
17. THE Asset Administration UI (Req 12) SHALL provide a "Duplicates" tab showing assets with identical content_hash values, allowing the tenant administrator to merge duplicates (keep one, re-attach references from the other, delete the duplicate)
18. THE `s3_assets` table SHALL include an additional column `content_hash` (VARCHAR(64), nullable, indexed per tenant) to support duplicate detection. Existing assets SHALL have NULL until re-scanned or re-uploaded.

##### Context-Aware Filtering

19. WHEN the Asset Picker is opened from a branding/logo context, IT SHALL default to filtering by category=`branding` and media_type=`image`
20. WHEN the Asset Picker is opened from an invoice attachment context, IT SHALL default to filtering by category=`invoices` and media_type=`document`
21. WHEN the Asset Picker is opened from a landing page editor, IT SHALL default to filtering by category=`landing-pages` with no media_type restriction (images and videos allowed)
22. THE user SHALL be able to override these default filters to browse all categories if desired (e.g., reuse a branding logo on a landing page)
