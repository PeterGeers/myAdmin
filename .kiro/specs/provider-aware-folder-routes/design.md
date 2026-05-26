# Provider-Aware Folder Routes Bugfix Design

## Overview

Six backend code paths unconditionally use `GoogleDriveService` for file storage operations, making them non-functional for tenants configured with `invoice_provider=s3_shared`. The fix introduces a storage provider resolver pattern that checks `storage.invoice_provider` via `ParameterService` and routes each operation to either `GoogleDriveService` (unchanged) or `S3SharedStorage` (new path). The fix is scoped to the routing layer — no changes to the underlying storage implementations.

## Glossary

- **Bug_Condition (C)**: The tenant's `invoice_provider` parameter is `s3_shared` or `s3_tenant`, but the code path unconditionally calls `GoogleDriveService`
- **Property (P)**: S3 tenants get provider-appropriate storage operations; files are stored/retrieved from S3 with correct key structure
- **Preservation**: Google Drive tenants continue to use `GoogleDriveService` for all operations without any behavioral change
- **Storage Provider Resolver**: A shared helper function `resolve_storage_provider(tenant)` that returns `'google_drive'` or `'s3_shared'` based on `ParameterService.get_param('storage', 'invoice_provider', tenant=tenant)`
- **S3SharedStorage**: Existing class in `storage/s3_shared_storage.py` with `upload()`, `download()`, `list_files()`, `delete()` methods; keys follow `{tenant}/{category}/{reference}/{uuid}_{filename}`
- **ParameterService**: Service in `services/parameter_service.py` that resolves parameters by walking scope chain (user → role → tenant → system)
- **Marker Object**: A zero-byte S3 object at `{tenant}/invoices/{reference}/.folder` that makes a reference appear in folder listings before any files are uploaded

## Bug Details

### Bug Condition

The bug manifests when any S3-configured tenant hits a storage-related endpoint. All six code paths (`folder_routes.py`, `invoice_service.py`, `output_service.py`, `missing_invoices_routes.py`, `tenant_admin_storage.py`, `str_invoice_routes.py`, `email_template_service.py`, `xlsx_export.py`) unconditionally instantiate `GoogleDriveService(tenant)` without checking the tenant's configured storage provider.

**Formal Specification:**

```
FUNCTION isBugCondition(X)
  INPUT: X of type StorageRequest (tenant, endpoint, operation)
  OUTPUT: boolean

  provider ← ParameterService.get_param('storage', 'invoice_provider', tenant=X.tenant)
  RETURN provider IN ('s3_shared', 's3_tenant')
END FUNCTION
```

### Examples

- `GET /api/folders` for tenant "AcmeBV" with `invoice_provider=s3_shared` → calls `GoogleDriveService("AcmeBV").list_subfolders()` → fails with missing credentials or returns empty list. Expected: returns S3 prefixes from `AcmeBV/invoices/`.
- `POST /api/upload` for tenant "AcmeBV" with file "invoice.pdf" and folder "Supplier1" → calls `GoogleDriveService("AcmeBV").upload_file()` → fails. Expected: stores at `AcmeBV/invoices/Supplier1/{uuid}_invoice.pdf` via `S3SharedStorage.upload()`.
- `POST /api/create-folder` for tenant "AcmeBV" with folderName "NewSupplier" → calls `GoogleDriveService.create_folder()` → fails. Expected: creates marker at `AcmeBV/invoices/NewSupplier/.folder`.
- `GET /api/tenant-admin/storage/usage` for tenant "AcmeBV" → calls Google Drive API for folder sizes → fails. Expected: sums object sizes from `list_objects_v2` on prefix `AcmeBV/`.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Google Drive tenants (`invoice_provider=google_drive`) continue to use `GoogleDriveService` for all storage operations across all endpoints
- Test mode (`flag=True`) continues to return local config-based folders for `GET /api/folders`
- Regex filtering on `GET /api/folders` continues to apply regardless of storage provider
- `output_destination='download'` continues to return content directly without any storage backend interaction
- Generic/system templates (bundled with the app in `backend/templates/`) remain unchanged regardless of provider
- Local file operations (temp files, workbook writing) in `xlsx_export.py` remain unchanged
- Database operations (duplicate checks, transaction queries) remain unchanged

**Scope:**
All inputs where `ParameterService.get_param('storage', 'invoice_provider', tenant=tenant)` returns `'google_drive'` or `None` (default) should be completely unaffected by this fix. This includes:

- All Google Drive tenant API calls
- Test mode folder listing
- Download-only output destinations
- System template loading (local filesystem)
- Database queries and transaction processing

## Hypothesized Root Cause

Based on the code analysis, the root cause is straightforward: **no provider dispatch logic exists**. Each affected file was written when Google Drive was the only storage backend. The `S3SharedStorage` class was added later (for the s3-shared-bucket-infrastructure spec) but the routing layer was never updated to use it.

Specific issues per file:

1. **`folder_routes.py`** (lines 47-56): Directly instantiates `GoogleDriveService(administration=tenant)` in production mode without checking provider. No S3 alternative path exists.

2. **`invoice_service.py`** (lines 155-160): `upload_to_drive()` method name itself reveals the assumption. Instantiates `GoogleDriveService(administration=tenant)` unconditionally.

3. **`output_service.py`** (lines 145-155): `_handle_gdrive_upload()` is the only non-download output handler. No `_handle_s3_upload()` implementation exists (method stub raises `NotImplementedError`).

4. **`missing_invoices_routes.py`** (lines 48-55): `upload_receipt` endpoint directly uses `GoogleDriveService(administration)` for folder listing and file upload.

5. **`tenant_admin_storage.py`** (lines 50-53, 145-155, 210-215, 270-280): All four endpoints (`/folders`, `/config PUT`, `/test`, `/usage`) unconditionally use `GoogleDriveService(tenant)`.

6. **`str_invoice_routes.py`** (lines 362-365): `upload_template_to_drive()` instantiates `GoogleDriveService(tenant)` without provider check.

7. **`email_template_service.py`** (lines 55-80): `_load_from_google_drive()` uses `GoogleDriveService` to download tenant-specific templates by file ID.

8. **`xlsx_export.py`** (lines 871-880): `_get_drive_service()` unconditionally creates `GoogleDriveService(administration)`.

## Correctness Properties

Property 1: Bug Condition - S3 Tenants Get Provider-Appropriate Storage

_For any_ storage request where the tenant's `invoice_provider` is `s3_shared` or `s3_tenant` (isBugCondition returns true), the fixed code SHALL route the operation to `S3SharedStorage` with correct key structure (`{tenant}/{category}/{reference}/{uuid}_{filename}`) and SHALL NOT instantiate `GoogleDriveService`.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12**

Property 2: Preservation - Google Drive Tenants Unaffected

_For any_ storage request where the tenant's `invoice_provider` is `google_drive` or unset (isBugCondition returns false), the fixed code SHALL produce exactly the same behavior as the original code, preserving all Google Drive operations, test mode behavior, regex filtering, and download-only output handling.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `backend/src/services/storage_resolver.py` (NEW)

**Purpose**: Shared helper that resolves the storage provider for a tenant

**Specific Changes**:

1. **Create `resolve_storage_provider(tenant, parameter_service=None)`**: Returns `'google_drive'` or `'s3_shared'` by calling `ParameterService.get_param('storage', 'invoice_provider', tenant=tenant)`. Defaults to `'google_drive'` when parameter is unset.
2. **Create `get_s3_storage(tenant, parameter_service=None)`**: Returns an initialized `S3SharedStorage(tenant, parameter_service)` instance.
3. **Create `list_s3_folders(tenant, parameter_service=None)`**: Uses `list_objects_v2` with `Delimiter='/'` and `Prefix='{tenant}/invoices/'` to extract unique reference names. Also checks for `.folder` marker objects.
4. **Create `create_s3_folder(tenant, folder_name, parameter_service=None)`**: Creates a zero-byte marker object at `{tenant}/invoices/{folder_name}/.folder`.

---

**File**: `backend/src/routes/folder_routes.py`

**Function**: `get_folders()`, `create_folder()`

**Specific Changes**:

1. **Add provider check in `get_folders()`**: After tenant resolution, call `resolve_storage_provider(tenant)`. If `'s3_shared'`, call `list_s3_folders(tenant)` instead of `GoogleDriveService.list_subfolders()`.
2. **Add provider check in `create_folder()`**: If `'s3_shared'`, call `create_s3_folder(tenant, folder_name)` instead of `GoogleDriveService.create_folder()`.
3. **Preserve test mode path**: The `if flag:` branch remains unchanged (returns local folders regardless of provider).
4. **Preserve regex filtering**: Applied after folder list is obtained from either provider.

---

**File**: `backend/src/services/invoice_service.py`

**Function**: `upload_to_drive()`

**Specific Changes**:

1. **Add provider check at method start**: Call `resolve_storage_provider(tenant)`. If `'s3_shared'`, read file bytes from `temp_path`, call `S3SharedStorage.upload(file_data, filename, metadata={'reference_number': folder_name})`, return `{'id': s3_key, 'url': s3_key}`.
2. **Preserve test mode path**: The `if self.test_mode:` branch remains unchanged.
3. **Preserve Google Drive path**: The existing Google Drive logic remains as the `else` branch.

---

**File**: `backend/src/services/output_service.py`

**Function**: `handle_output()`, `_handle_s3_upload()` (implement existing stub)

**Specific Changes**:

1. **Add provider-aware routing in `handle_output()`**: When `destination='gdrive'`, check provider. If `'s3_shared'`, route to `_handle_s3_upload()` instead of `_handle_gdrive_upload()`.
2. **Implement `_handle_s3_upload()`**: Upload content to `{tenant}/reports/{filename}` via `S3SharedStorage.upload(content_bytes, filename, category='reports')`. Return `{'success': True, 'destination': 's3', 'key': s3_key}`.

---

**File**: `backend/src/routes/missing_invoices_routes.py`

**Function**: `upload_receipt()`

**Specific Changes**:

1. **Add provider check**: After tenant resolution, call `resolve_storage_provider(tenant)`. If `'s3_shared'`, use `list_s3_folders(tenant)` for supplier lookup, `create_s3_folder()` for new suppliers, and `S3SharedStorage.upload()` for file upload.
2. **Preserve Google Drive path**: Existing logic remains for Google Drive tenants.

---

**File**: `backend/src/routes/tenant_admin_storage.py`

**Functions**: `list_folders()`, `update_storage_config()`, `test_folder_access()`, `get_storage_usage()`

**Specific Changes**:

1. **`list_folders()`**: If S3, use `list_objects_v2` with delimiter to show prefix structure under `{tenant}/`.
2. **`update_storage_config()` with `validate=True`**: If S3, validate by calling `head_bucket` on the shared bucket and testing a `put_object`/`delete_object` cycle on `{tenant}/_test_access`.
3. **`test_folder_access()`**: If S3, perform `head_bucket` + put/delete cycle instead of Google Drive file listing.
4. **`get_storage_usage()`**: If S3, call `list_objects_v2` on `{tenant}/` prefix and sum object sizes.

---

**File**: `backend/src/str_invoice_routes.py`

**Function**: `upload_template_to_drive()`

**Specific Changes**:

1. **Add provider check**: If `'s3_shared'`, upload template content via `S3SharedStorage.upload(content_bytes, template_name, category='templates')`. Store the returned S3 key in `tenant_template_config.template_file_id`.
2. **Preserve Google Drive path**: Existing logic remains for Google Drive tenants.

---

**File**: `backend/src/services/email_template_service.py`

**Function**: `_load_from_google_drive()`

**Specific Changes**:

1. **Add provider check**: Before calling `GoogleDriveService`, check provider. If `'s3_shared'` and `template_file_id` looks like an S3 key (contains `/`), download via `S3SharedStorage.download(template_file_id)`.
2. **Preserve Google Drive path**: If provider is `'google_drive'` or key looks like a Drive file ID, use existing `GoogleDriveService.download_file_content()`.
3. **Preserve local fallback**: If no custom template found in either backend, fall back to local filesystem templates (unchanged).

---

**File**: `backend/src/xlsx_export.py`

**Function**: `_get_drive_service()`, `export_files()`, `_download_drive_file()`

**Specific Changes**:

1. **Add provider-aware download in `export_files()`**: When processing `DocUrl` values, check if the URL is an S3 key (no `drive.google` in it). If so, download via `S3SharedStorage.download(key)` instead of Google Drive API.
2. **Update `_get_drive_service()`**: If provider is `'s3_shared'`, return `None` (skip Drive initialization). The caller already handles `None` gracefully.
3. **Add `_download_s3_file()` method**: Downloads file from S3 by key and saves to destination folder.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that mock `ParameterService.get_param('storage', 'invoice_provider', tenant=tenant)` to return `'s3_shared'`, then call each affected endpoint. Observe that `GoogleDriveService` is still instantiated (confirming the bug). Run these tests on the UNFIXED code to observe failures.

**Test Cases**:

1. **Folder Listing Test**: Mock provider as `s3_shared`, call `GET /api/folders` → observe `GoogleDriveService` is called (will fail on unfixed code)
2. **Folder Creation Test**: Mock provider as `s3_shared`, call `POST /api/create-folder` → observe `GoogleDriveService.create_folder()` is called (will fail on unfixed code)
3. **Invoice Upload Test**: Mock provider as `s3_shared`, call `upload_to_drive()` → observe `GoogleDriveService` is instantiated (will fail on unfixed code)
4. **Output Service Test**: Mock provider as `s3_shared`, call `handle_output(destination='gdrive')` → observe `GoogleDriveService` is called (will fail on unfixed code)
5. **Storage Admin Test**: Mock provider as `s3_shared`, call `GET /api/tenant-admin/storage/folders` → observe `GoogleDriveService` is called (will fail on unfixed code)
6. **Template Upload Test**: Mock provider as `s3_shared`, call `POST /upload-template` → observe `GoogleDriveService` is called (will fail on unfixed code)

**Expected Counterexamples**:

- `GoogleDriveService` is instantiated for S3 tenants in every code path
- Operations fail with missing credentials or return incorrect results
- Possible causes confirmed: no provider dispatch logic exists anywhere

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL X WHERE isBugCondition(X) DO
  result := fixed_endpoint(X)
  ASSERT GoogleDriveService NOT instantiated
  ASSERT S3SharedStorage used with correct tenant prefix
  ASSERT result contains valid S3 keys or prefix listings
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT original_endpoint(X) = fixed_endpoint(X)
  // Google Drive tenants use GoogleDriveService unchanged
  // Test mode returns local folders unchanged
  // Download destinations return content unchanged
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many tenant/endpoint/parameter combinations automatically
- It catches edge cases where provider resolution might incorrectly route Google Drive tenants to S3
- It provides strong guarantees that the Google Drive path is truly unchanged

**Test Plan**: Observe behavior on UNFIXED code first for Google Drive tenants (mock `GoogleDriveService` responses), then write property-based tests capturing that behavior continues after the fix.

**Test Cases**:

1. **Google Drive Folder Listing Preservation**: Verify `GET /api/folders` for Google Drive tenants continues to call `GoogleDriveService.list_subfolders()` and return the same results
2. **Google Drive Upload Preservation**: Verify `upload_to_drive()` for Google Drive tenants continues to use `GoogleDriveService.upload_file()`
3. **Test Mode Preservation**: Verify `GET /api/folders` with `flag=True` returns local folders regardless of provider setting
4. **Regex Filter Preservation**: Verify regex filtering applies identically to both provider paths
5. **Download Destination Preservation**: Verify `handle_output(destination='download')` never touches any storage backend

### Unit Tests

- Test `resolve_storage_provider()` returns correct provider for various parameter values (s3_shared, google_drive, None, empty string)
- Test `list_s3_folders()` correctly parses `list_objects_v2` response with CommonPrefixes and marker objects
- Test `create_s3_folder()` creates correct marker object key
- Test each route handler dispatches to correct backend based on provider
- Test edge cases: provider parameter missing (defaults to google_drive), empty tenant, invalid provider value

### Property-Based Tests

- Generate random tenant names and provider settings, verify `resolve_storage_provider()` always returns a valid provider string
- Generate random folder names (with special characters, unicode, long names) and verify S3 key construction is valid
- Generate random combinations of (tenant, provider, endpoint) and verify the correct backend is called
- Generate random Google Drive tenant requests and verify behavior matches unfixed code exactly

### Integration Tests

- Test full folder listing flow for S3 tenant with mocked S3 responses
- Test full invoice upload flow for S3 tenant end-to-end (mock S3 `put_object`)
- Test full report output flow for S3 tenant (mock S3 `put_object`)
- Test storage admin endpoints for S3 tenant (mock `list_objects_v2`, `head_bucket`)
- Test that switching a tenant from google_drive to s3_shared mid-session routes correctly
