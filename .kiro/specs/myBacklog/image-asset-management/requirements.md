# Requirements Document

## Introduction

The Media Asset Management Service treats all S3-stored assets as first-class domain objects with explicit lifecycle management. Instead of storing S3 keys directly in application data, assets are registered in a central MySQL Asset Registry (tables `s3_assets` and `s3_asset_references`) with tracked references. This enables safe cleanup of orphaned assets, consistency reconciliation between S3 and application data, and a clear upload-to-deletion lifecycle across all tenant contexts.

The service manages assets across multiple media types (images, videos, documents) stored in the project's S3 buckets, organized by asset category (invoices, branding, templates, landing-pages).

### Scope

- This service manages ONLY S3 buckets defined within the myAdmin project: `myadmin-shared-{env}` and `myadmin-public-pages-{env}`
- Other projects or services that may access the shared bucket are out of scope
- Future cross-project integration is acknowledged but not addressed in this version

### Safety Model

The service uses a three-layer safety model:

1. **S3 Lifecycle** — automatically expires forgotten temporary uploads
2. **Asset Registry with references** — manages normal asset lifecycle (active/orphan/deleted)
3. **Periodic Reconciliation** — catches bugs and data inconsistencies between S3, registry, and application data

## Glossary

- **Asset_Service**: The backend service module responsible for media asset lifecycle operations (create, attach, detach, replace, get, delete, reconcile, import)
- **Asset_Registry**: The MySQL tables (`s3_assets` and `s3_asset_references`) storing asset metadata, status, and reference information
- **Temporary_Upload**: An asset uploaded to S3 under the `/tmp/` prefix, subject to automatic expiry via S3 Lifecycle rules
- **Permanent_Asset**: An asset moved from `/tmp/` to its category-specific path and registered in the Asset_Registry
- **Reference**: An explicit link between an asset and a consuming entity (landing page, invoice, member avatar, etc.), stored as a row in the `s3_asset_references` table
- **Orphan_Asset**: A registered asset with zero references, marked with status ORPHAN and an orphaned_at timestamp
- **Grace_Period**: The configurable duration (default 7 days) an Orphan_Asset must remain unreferenced before deletion is permitted
- **Reconciliation_Job**: A periodic process that verifies consistency between S3 objects, Asset_Registry records, and application references
- **Tenant**: An isolated organizational unit in the multi-tenant system, identified by the `administration` value from AWS Cognito JWT
- **Bucket_Configuration**: The service-level configuration defining the S3 buckets managed by this project. The two buckets are `myadmin-shared-{env}` (for invoices, branding, templates) and `myadmin-public-pages-{env}` (for landing page assets served via CloudFront). The Asset_Service resolves which bucket to use based on asset category.
- **Asset_Consumer**: Any application entity that can reference an asset (landing page, invoice record, member profile, template, etc.)
- **Asset_Category**: A classification that determines the storage bucket and path prefix for an asset. Categories are: `invoices` (PDF documents in shared bucket under `{tenant}/invoices/`), `branding` (logos and letterheads in shared bucket under `{tenant}/branding/`), `templates` (invoice and report templates in shared bucket under `{tenant}/templates/`), and `landing-pages` (HTML, images, and videos in public-pages bucket)
- **Media_Type**: The broad classification of a file by content: `image` (JPEG, PNG, WebP, GIF — max 10 MB), `video` (MP4, WebM — max 100 MB), or `document` (PDF — max 25 MB)

## Requirements

### Requirement 1: Temporary Asset Upload

**User Story:** As a tenant user, I want to upload media assets to a temporary location, so that I can preview them before committing to use them in my content.

#### Acceptance Criteria

1. WHEN a tenant user uploads an asset, THE Asset_Service SHALL resolve the target bucket from the Bucket_Configuration based on the specified asset category and store the asset in that bucket under the path `/tmp/{tenantId}/{uploadId}.{extension}` where uploadId is a system-generated unique identifier
2. WHEN a tenant user uploads an asset, THE Asset_Service SHALL return a temporary asset identifier, the resolved bucket name, and a pre-signed preview URL valid for 24 hours
3. THE Asset_Service SHALL validate that the uploaded file belongs to an allowed Media_Type by verifying both the file extension and the file content headers (magic bytes), where allowed types are: images (JPEG, PNG, WebP, GIF), videos (MP4, WebM), and documents (PDF)
4. THE Asset_Service SHALL validate that the uploaded file does not exceed the size limit for its Media_Type: 10 MB for images, 100 MB for videos, and 25 MB for documents
5. IF a file with an unsupported type is uploaded, THEN THE Asset_Service SHALL reject the upload with an error message indicating the detected file type and listing the allowed types grouped by Media_Type category
6. IF a file exceeding the maximum size for its Media_Type is uploaded, THEN THE Asset_Service SHALL reject the upload with an error message indicating the file size, the detected Media_Type, and the applicable size limit
7. IF the upload request contains no file or an empty file body, THEN THE Asset_Service SHALL reject the request with an error message indicating that a file is required

### Requirement 2: S3 Lifecycle for Temporary Uploads

**User Story:** As a system operator, I want temporary uploads to be automatically deleted after 24 hours, so that abandoned uploads do not accumulate storage costs.

#### Acceptance Criteria

1. THE S3_Lifecycle_Rule SHALL be configured on each bucket defined in the Bucket_Configuration to automatically delete objects under the `/tmp/` prefix that are older than 24 hours based on object creation time
2. WHEN a temporary upload expires via S3 Lifecycle, THE Asset_Service SHALL require no registry cleanup because Temporary_Uploads are not registered in the Asset_Registry until promotion to Permanent_Asset
3. THE S3_Lifecycle_Rule SHALL apply exclusively to objects under the `/tmp/` prefix without affecting objects under category-specific paths on each configured bucket
4. IF a tenant user attempts to promote a temporary upload that has already been deleted by the S3_Lifecycle_Rule, THEN THE Asset_Service SHALL return an error indicating the upload has expired

### Requirement 3: Asset Registration (Promote to Permanent)

**User Story:** As a tenant user, I want to commit an uploaded asset for use in my content, so that the asset is permanently stored and tracked in the system.

#### Acceptance Criteria

1. WHEN a user saves content referencing a temporary upload, THE Asset_Service SHALL resolve the target permanent path from the Bucket_Configuration based on the specified asset category, and copy the asset from `/tmp/{tenantId}/{uploadId}.{extension}` to the category-specific path in the resolved bucket (e.g., `{tenantId}/branding/{assetId}.{extension}` for the shared bucket, or `{slug}/assets/{assetId}.{extension}` for the public-pages bucket)
2. WHEN a temporary asset is promoted to permanent, THE Asset_Service SHALL insert a record in the `s3_assets` table with status ACTIVE, the administration, bucket, s3_key, mime_type, file_size, category, media_type, original_filename, and created_at timestamp
3. WHEN a temporary asset is promoted to permanent, THE Asset*Service SHALL generate a unique asset id using the format `ast*` followed by a ULID
4. IF the temporary upload does not exist in S3 at promotion time or the provided uploadId does not match a valid temporary upload for the authenticated tenant, THEN THE Asset_Service SHALL return an error indicating the upload has expired or is invalid
5. WHEN a temporary asset is promoted, THE Asset_Service SHALL delete the original object from `/tmp/` after successful copy to the permanent path
6. IF the S3 copy operation to the permanent path fails, THEN THE Asset_Service SHALL return an error indicating the promotion failed and SHALL NOT insert an `s3_assets` record nor delete the temporary upload
7. IF a promotion request is made for a temporary upload that has already been promoted, THEN THE Asset_Service SHALL return an error indicating the upload has already been registered

### Requirement 4: Attach Asset Reference

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

### Requirement 5: Detach Asset Reference

**User Story:** As a tenant user, I want assets to be unlinked when I remove them from content, so that unused assets can be identified and cleaned up.

#### Acceptance Criteria

1. WHEN a detach request is received specifying an asset_id, entity_type, and entity_id, THE Asset_Service SHALL delete the matching row from the `s3_asset_references` table and return the updated asset record including the current reference count and status
2. WHEN the last reference to an asset is removed, THE Asset_Service SHALL change the asset status to ORPHAN and record the current timestamp as orphaned_at
3. WHILE an asset still has remaining references after a detach, THE Asset_Service SHALL keep the asset status as ACTIVE
4. THE Asset_Service SHALL enforce that all detach operations are scoped to the authenticated tenant
5. IF a detach operation references a non-existent asset_id or a reference entry that does not match any stored row in `s3_asset_references` for that asset, THEN THE Asset_Service SHALL return an error indicating the resource does not exist

### Requirement 6: Retrieve Asset

**User Story:** As a tenant user, I want to retrieve asset metadata and access URLs, so that I can display or download assets in my content.

#### Acceptance Criteria

1. WHEN a tenant user requests an asset by asset_id, THE Asset_Service SHALL return the asset metadata including id, s3_key, mime_type, file_size, category, media_type, original_filename, status, created_at, and associated references from the `s3_asset_references` table
2. WHEN a tenant user requests an asset by asset_id, THE Asset_Service SHALL include a presigned S3 URL valid for 60 minutes in the response
3. THE Asset_Service SHALL enforce that asset retrieval is scoped to the authenticated tenant
4. IF a tenant user requests an asset belonging to a different tenant, THEN THE Asset_Service SHALL return a not-found error without revealing the asset exists
5. IF a tenant user requests an asset_id that does not exist in the `s3_assets` table, THEN THE Asset_Service SHALL return a not-found error
6. WHILE an asset has status ORPHAN, THE Asset_Service SHALL still permit retrieval of its metadata and presigned URL until the asset is permanently deleted

### Requirement 7: Delete Asset

**User Story:** As a system operator, I want orphaned assets to be permanently deleted after the grace period, so that storage is reclaimed without risking deletion of actively used assets.

#### Acceptance Criteria

1. WHEN an Orphan_Asset has exceeded the Grace_Period, THE Asset_Service SHALL delete the S3 object, remove any remaining rows from `s3_asset_references`, and delete the row from `s3_assets` as part of an automated deletion process
2. WHEN THE Asset_Service attempts to delete an asset, THE Asset_Service SHALL verify within the same transaction that the asset still has status ORPHAN and zero references in `s3_asset_references` before performing the S3 deletion and registry removal
3. IF an asset regains a reference during the Grace_Period, THEN THE Asset_Service SHALL cancel the pending deletion by reverting status to ACTIVE and clearing the orphaned_at timestamp
4. WHEN an asset is successfully deleted, THE Asset_Service SHALL log the deletion with the asset_id, administration, bucket, category, and deletion timestamp for audit purposes
5. WHEN a tenant user requests manual deletion of an asset that has zero references, THE Asset_Service SHALL delete the S3 object, remove any remaining rows from `s3_asset_references`, and delete the row from `s3_assets`
6. IF a tenant user requests manual deletion of an asset that has one or more active references, THEN THE Asset_Service SHALL reject the request with an error message indicating the asset is still in use and listing the number of active references
7. IF the S3 object deletion fails during an asset deletion operation, THEN THE Asset_Service SHALL retain the `s3_assets` record and report the failure without leaving the system in an inconsistent state

### Requirement 8: Reconciliation

**User Story:** As a system operator, I want periodic consistency checks between S3, the Asset Registry, and application data, so that bugs and data inconsistencies are detected and reported.

#### Acceptance Criteria

1. WHEN the Reconciliation_Job executes, THE Asset_Service SHALL scan all buckets defined in the Bucket_Configuration and identify S3 objects under category-specific paths that have no corresponding row in the `s3_assets` table (unregistered S3 objects)
2. WHEN the Reconciliation_Job executes, THE Asset_Service SHALL identify `s3_assets` records where the referenced S3 object does not exist in the bucket stored on the record (missing S3 objects)
3. WHEN the Reconciliation_Job executes, THE Asset_Service SHALL identify rows in `s3_asset_references` pointing to application entities that no longer exist (stale references)
4. WHEN the Reconciliation_Job completes, THE Asset_Service SHALL produce a reconciliation report containing the administration, execution timestamp, and counts of total assets, consistent assets, unregistered S3 objects, missing S3 objects, and stale references
5. THE Reconciliation_Job SHALL execute on a configurable schedule (default: once daily)
6. THE Reconciliation_Job SHALL process assets scoped per tenant (administration) to maintain isolation
7. IF stale references are detected, THEN THE Asset_Service SHALL automatically remove the stale reference rows from `s3_asset_references` and update asset status to ORPHAN with orphaned_at set when zero references remain, or keep status as ACTIVE when references still exist
8. IF the Reconciliation_Job fails mid-execution, THEN THE Asset_Service SHALL log the failure with administration, timestamp, and error details, and SHALL NOT leave partially-processed records in an inconsistent state
9. WHEN unregistered S3 objects or missing S3 objects are detected, THE Reconciliation_Job SHALL report them in the reconciliation report but SHALL NOT automatically delete or create records without explicit operator action

### Requirement 9: Multi-Tenant Isolation

**User Story:** As a tenant administrator, I want all asset operations to be isolated to my tenant, so that no tenant can access or modify another tenant's assets.

#### Acceptance Criteria

1. WHEN a request is received, THE Asset_Service SHALL extract the administration value from the authenticated AWS Cognito JWT token before processing any operation
2. IF the JWT token is missing, expired, or does not contain a valid administration claim, THEN THE Asset_Service SHALL reject the request with an authentication error and SHALL NOT process the operation
3. THE Asset_Service SHALL include the administration value as a WHERE clause filter for all queries against the `s3_assets` and `s3_asset_references` tables
4. THE Asset_Service SHALL scope all S3 operations to the tenant-specific prefix for the relevant asset category across all buckets defined in the Bucket_Configuration for the authenticated tenant
5. IF a request contains an asset identifier or S3 key that resolves to a path outside the authenticated tenant's prefix, THEN THE Asset_Service SHALL reject the request with an authorization error indicating access denied, and SHALL NOT read, write, or delete the referenced object
6. IF a request attempts to access an asset whose `s3_assets` record belongs to a different administration than the authenticated tenant, THEN THE Asset_Service SHALL reject the request with an authorization error indicating access denied and SHALL NOT return asset data or metadata
7. THE Reconciliation_Job SHALL query and process assets scoped to a single administration value per execution cycle, without reading or modifying records belonging to any other tenant

### Requirement 10: Asset Registry Data Model

**User Story:** As a developer, I want a well-defined MySQL schema for the Asset Registry, so that asset data is efficiently queryable and supports all lifecycle operations.

#### Acceptance Criteria

1. THE Asset*Registry SHALL use a table named `s3_assets` with columns: `id` (VARCHAR primary key storing `ast*`+ ULID),`administration`(VARCHAR NOT NULL for tenant isolation),`bucket`(VARCHAR NOT NULL),`s3_key`(VARCHAR NOT NULL),`mime_type`(VARCHAR NOT NULL),`file_size`(BIGINT NOT NULL),`category`(ENUM of`invoices`, `branding`, `templates`, `landing-pages`), `media_type`(ENUM of`image`, `video`, `document`), `original_filename`(VARCHAR NOT NULL),`status`(ENUM of`ACTIVE`, `ORPHAN`with default`ACTIVE`), `created_at`(DATETIME NOT NULL),`updated_at`(DATETIME),`orphaned_at`(DATETIME), and`migrated_at` (DATETIME)
2. THE Asset_Registry SHALL use a separate table named `s3_asset_references` with columns: `id` (BIGINT AUTO_INCREMENT primary key), `asset_id` (VARCHAR NOT NULL referencing `s3_assets.id`), `entity_type` (VARCHAR NOT NULL), `entity_id` (VARCHAR NOT NULL), and `created_at` (DATETIME NOT NULL)
3. THE `s3_asset_references` table SHALL define a foreign key from `asset_id` to `s3_assets.id` with ON DELETE CASCADE
4. THE `s3_asset_references` table SHALL define a unique constraint on the combination of (asset_id, entity_type, entity_id) to prevent duplicate references
5. THE `s3_assets` table SHALL include indexes on (administration, status), (administration, category), and (status, orphaned_at) to support efficient tenant-scoped queries and orphan cleanup
6. THE `s3_asset_references` table SHALL include an index on (entity_type, entity_id) to support efficient lookup of all assets referenced by a given entity

### Requirement 11: Legacy Asset Import

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
