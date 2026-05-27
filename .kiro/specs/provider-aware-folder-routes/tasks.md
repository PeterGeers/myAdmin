# Implementation Plan

## Overview

Fix six backend code paths that unconditionally use `GoogleDriveService` for file storage operations, making them non-functional for tenants configured with `invoice_provider=s3_shared`. The fix introduces a storage provider resolver pattern that checks `storage.invoice_provider` via `ParameterService` and routes each operation to either `GoogleDriveService` (unchanged) or `S3SharedStorage` (new path). Nine files are affected in total.

## Task Depenency Graph

```json
{
  "waves": [
    {
      "name": "Wave 1 - Exploration & Preservation Tests (BEFORE fix)",
      "tasks": ["1", "2"],
      "description": "Write bug condition and preservation tests on unfixed code"
    },
    {
      "name": "Wave 2 - Storage Resolver Module",
      "tasks": ["3"],
      "dependsOn": ["1", "2"],
      "description": "Create the shared helper module that all fixes depend on"
    },
    {
      "name": "Wave 3 - Fix Affected Files (parallelizable)",
      "tasks": ["4", "5", "6", "7", "8", "9", "10", "11", "12"],
      "dependsOn": ["3"],
      "description": "Add provider-aware routing to each affected code path"
    },
    {
      "name": "Wave 4 - Verification & Additional Tests",
      "tasks": ["13", "14", "15"],
      "dependsOn": ["4", "5", "6", "7", "8", "9", "10", "11", "12"],
      "description": "Verify fix passes exploration test, preservation holds, and write additional tests"
    },
    {
      "name": "Wave 5 - Checkpoint",
      "tasks": ["16"],
      "dependsOn": ["13", "14", "15"],
      "description": "Final validation that all tests pass"
    }
  ]
}
```

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - S3 Tenants Unconditionally Hit GoogleDriveService
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate GoogleDriveService is instantiated for S3 tenants
  - **Scoped PBT Approach**: Scope the property to concrete failing cases: any tenant with `invoice_provider=s3_shared` calling storage endpoints
  - Test file: `backend/tests/unit/test_provider_aware_bug_condition.py`
  - Use Hypothesis to generate random tenant names and endpoint combinations where `isBugCondition(X)` is true
  - Mock `ParameterService.get_param('storage', 'invoice_provider', tenant=X.tenant)` to return `'s3_shared'`
  - For each affected code path, assert that `GoogleDriveService` is NOT instantiated and `S3SharedStorage` IS used:
    - `folder_routes.get_folders()` — should call `list_s3_folders()` not `GoogleDriveService.list_subfolders()`
    - `folder_routes.create_folder()` — should call `create_s3_folder()` not `GoogleDriveService.create_folder()`
    - `missing_invoices_routes.upload_receipt()` — should use S3 for folder listing and upload
    - `output_service.handle_output(destination='gdrive')` — should route to `_handle_s3_upload()`
    - `tenant_admin_storage.list_folders()` — should use `list_objects_v2` not `GoogleDriveService`
    - `email_template_service._load_from_google_drive()` — should download from S3 when key contains `/`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists because GoogleDriveService is called unconditionally)
  - Document counterexamples found (e.g., "get_folders('AcmeBV') instantiates GoogleDriveService instead of listing S3 prefixes")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 1.9_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Google Drive Tenants Unaffected
  - **IMPORTANT**: Follow observation-first methodology
  - Test file: `backend/tests/unit/test_provider_aware_preservation.py`
  - Observe behavior on UNFIXED code for Google Drive tenants (cases where `isBugCondition` returns false):
    - Observe: `get_folders()` with `invoice_provider='google_drive'` calls `GoogleDriveService.list_subfolders()` and returns folder names
    - Observe: `create_folder()` with `invoice_provider='google_drive'` calls `GoogleDriveService.create_folder()`
    - Observe: `get_folders()` with `flag=True` (test mode) returns local config folders regardless of provider
    - Observe: `handle_output(destination='download')` returns content directly without any storage backend
    - Observe: regex filtering on `GET /api/folders` applies to folder list regardless of provider
  - Write property-based tests using Hypothesis:
    - Property: for all tenants where `invoice_provider='google_drive'` or unset, `GoogleDriveService` is instantiated with correct tenant
    - Property: for all requests with `flag=True`, local folders are returned regardless of `invoice_provider`
    - Property: for all requests with `destination='download'`, no storage backend is called
    - Property: for all folder lists and regex patterns, filtering produces the same subset regardless of provider
  - Mock `GoogleDriveService` to return predictable results, verify it IS called for Google Drive tenants
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

- [x] 3. Create `services/storage_resolver.py` helper module
  - [x] 3.1 Implement `resolve_storage_provider(tenant, parameter_service=None)`
    - Returns `'google_drive'` or `'s3_shared'` based on `ParameterService.get_param('storage', 'invoice_provider', tenant=tenant)`
    - If `parameter_service` is None, instantiate one from `DatabaseManager`
    - Default to `'google_drive'` when parameter is unset or None
    - _Bug_Condition: isBugCondition(input) where provider IN ('s3_shared', 's3_tenant') but code uses GoogleDriveService_
    - _Expected_Behavior: Returns correct provider string for routing decisions_
    - _Preservation: Returns 'google_drive' for unset/None/google_drive values_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 3.1_

  - [x] 3.2 Implement `get_s3_storage(tenant, parameter_service=None)`
    - Returns an initialized `S3SharedStorage(tenant, parameter_service)` instance
    - Handles parameter_service resolution if not provided
    - _Requirements: 2.3, 2.4, 2.5, 2.7, 2.8_

  - [x] 3.3 Implement `list_s3_folders(tenant, parameter_service=None, category='invoices')`
    - Uses `list_objects_v2` with `Delimiter='/'` and `Prefix='{tenant}/invoices/'` to extract unique reference names
    - Also checks for `.folder` marker objects to include empty folders
    - Returns list of folder name strings (matching the format returned by Google Drive path)
    - _Requirements: 2.1, 2.4, 2.9_

  - [x] 3.4 Implement `create_s3_folder(tenant, folder_name, parameter_service=None)`
    - Creates a zero-byte marker object at `{tenant}/invoices/{folder_name}/.folder`
    - Returns success dict matching Google Drive create_folder response shape
    - _Requirements: 2.2_

- [x] 4. Fix `routes/folder_routes.py` — Add provider-aware routing
  - [x] 4.1 Add provider check in `get_folders()`
    - After tenant resolution, call `resolve_storage_provider(tenant)`
    - If `'s3_shared'` or `'s3_tenant'`, call `list_s3_folders(tenant)` instead of `GoogleDriveService.list_subfolders()`
    - Preserve test mode path: the `if flag:` branch remains unchanged
    - Preserve regex filtering: applied after folder list is obtained from either provider
    - Preserve fallback behavior on error
    - _Bug_Condition: isBugCondition(X) where X.endpoint = 'GET /api/folders' and provider = 's3_shared'_
    - _Expected_Behavior: Returns S3 reference prefixes from {tenant}/invoices/_
    - _Preservation: Google Drive tenants and test mode unchanged_
    - _Requirements: 2.1, 3.1, 3.9, 3.10_

  - [x] 4.2 Add provider check in `create_folder()`
    - If `'s3_shared'`, call `create_s3_folder(tenant, folder_name)` instead of `GoogleDriveService.create_folder()`
    - Preserve local folder creation (always happens regardless of provider)
    - _Bug_Condition: isBugCondition(X) where X.endpoint = 'POST /api/create-folder' and provider = 's3_shared'_
    - _Expected_Behavior: Creates marker object at {tenant}/invoices/{folder_name}/.folder_
    - _Preservation: Google Drive tenants continue to use GoogleDriveService.create_folder()_
    - _Requirements: 2.2, 3.2_

- [x] 5. Fix `services/invoice_service.py` — Add provider check to `upload_to_drive()`
  - [x] 5.1 Add provider-aware routing at method start
    - Call `resolve_storage_provider(tenant)` before any storage operation
    - If `'s3_shared'`, read file bytes from `temp_path`, call `S3SharedStorage.upload(file_data, filename, metadata={'reference_number': folder_name})`
    - Return `{'id': s3_key, 'url': s3_key}` matching the Google Drive response shape
    - Preserve test mode path unchanged
    - Preserve Google Drive path as the `else` branch
    - _Bug_Condition: isBugCondition(X) where X.endpoint = 'POST /api/upload' and provider = 's3_shared'_
    - _Expected_Behavior: File stored at {tenant}/invoices/{folder_name}/{uuid}_{filename} via S3SharedStorage\_
    - _Preservation: Google Drive tenants continue to use GoogleDriveService.upload_file()_
    - _Requirements: 2.3, 3.3_

- [x] 6. Fix `services/output_service.py` — Add provider-aware routing in `handle_output()`
  - [x] 6.1 Route S3 tenants to `_handle_s3_upload()` when destination is 'gdrive'
    - In `handle_output()`, when `destination='gdrive'`, check provider via `resolve_storage_provider(administration)`
    - If `'s3_shared'` or `'s3_tenant'`, route to existing `_handle_s3_upload()` instead of `_handle_gdrive_upload()`
    - The `_handle_s3_upload()` implementation already exists and works correctly
    - Preserve download destination path (no storage backend interaction)
    - Preserve Google Drive path for Google Drive tenants
    - _Bug_Condition: isBugCondition(X) where X.destination = 'gdrive' and provider = 's3_shared'_
    - _Expected_Behavior: Report stored at {tenant}/reports/{filename} via S3SharedStorage_
    - _Preservation: Google Drive tenants and download destination unchanged_
    - _Requirements: 2.5, 2.6, 3.5, 3.11_

- [x] 7. Fix `routes/missing_invoices_routes.py` — Add provider check to `upload_receipt()`
  - [x] 7.1 Add provider-aware routing for folder listing and file upload
    - After tenant resolution, call `resolve_storage_provider(administration)`
    - If `'s3_shared'`: use `list_s3_folders(administration)` for supplier lookup, `create_s3_folder()` for new suppliers, and `S3SharedStorage.upload()` for file upload
    - Return S3 key as `driveUrl` in response (maintains API contract)
    - Preserve Google Drive path for Google Drive tenants
    - _Bug_Condition: isBugCondition(X) where X.endpoint = 'POST /api/upload-receipt' and provider = 's3_shared'_
    - _Expected_Behavior: Supplier folder lookup uses S3 prefix listing, file stored via S3SharedStorage_
    - _Preservation: Google Drive tenants continue to use GoogleDriveService for all operations_
    - _Requirements: 2.4, 3.4_

- [x] 8. Fix `routes/tenant_admin_storage.py` — Add provider checks to all four endpoints
  - [x] 8.1 Fix `list_folders()` — route to S3 prefix listing
    - If S3, use `list_objects_v2` with delimiter to show prefix structure under `{tenant}/`
    - Return same response shape (`folders` list, `count`)
    - _Requirements: 2.9, 3.8_

  - [x] 8.2 Fix `update_storage_config()` — S3 validation path
    - If S3 and `validate=True`, validate by calling `head_bucket` on shared bucket and testing `put_object`/`delete_object` cycle on `{tenant}/_test_access`
    - _Requirements: 2.12, 3.8_

  - [x] 8.3 Fix `test_folder_access()` — S3 access test
    - If S3, perform `head_bucket` + put/delete cycle instead of Google Drive file listing
    - Return same response shape (`read_access`, `write_access`, `accessible`)
    - _Requirements: 2.10, 3.8_

  - [x] 8.4 Fix `get_storage_usage()` — S3 size calculation
    - If S3, call `list_objects_v2` on `{tenant}/` prefix and sum object sizes
    - Return same response shape (`usage` dict with `file_count`, `total_size_bytes`, `total_size_mb`)
    - _Requirements: 2.11, 3.8_

- [x] 9. Fix `str_invoice_routes.py` — Add provider check to `upload_template_to_drive()`
  - [x] 9.1 Add provider-aware template upload
    - If `'s3_shared'`, upload template content via `S3SharedStorage.upload(content_bytes, template_name, category='templates')`
    - Store the returned S3 key in `tenant_template_config.template_file_id`
    - Preserve Google Drive path for Google Drive tenants
    - _Bug_Condition: isBugCondition(X) where X.endpoint = 'POST /upload-template' and provider = 's3_shared'_
    - _Expected_Behavior: Template stored at {tenant}/templates/{uuid}_{filename}, key persisted in DB\_
    - _Preservation: Google Drive tenants continue to use GoogleDriveService_
    - _Requirements: 2.7, 3.6_

- [x] 10. Fix `services/email_template_service.py` — Add provider check to `_load_from_google_drive()`
  - [x] 10.1 Add provider-aware template download
    - Before calling `GoogleDriveService`, check provider via `resolve_storage_provider(self.administration)`
    - If `'s3_shared'` and `template_file_id` looks like an S3 key (contains `/`), download via `S3SharedStorage.download(template_file_id)`
    - If provider is `'google_drive'` or key looks like a Drive file ID (no `/`), use existing `GoogleDriveService.download_file_content()`
    - Preserve local fallback: if no custom template found in either backend, fall back to local filesystem templates
    - _Bug_Condition: isBugCondition(X) where X.operation = 'fetch_template' and provider = 's3_shared'_
    - _Expected_Behavior: Template downloaded via S3SharedStorage.download(s3_key)_
    - _Preservation: Google Drive tenants and local fallback unchanged_
    - _Requirements: 2.8, 3.7_

- [x] 11. Fix `tenant_admin_routes.py` — Add provider check to template content download
  - [x] 11.1 Add provider-aware template download in `get_template_content()` endpoint
    - Before calling `GoogleDriveService.download_file_content(file_id)`, check provider via `resolve_storage_provider(tenant)`
    - If `'s3_shared'` and `file_id` looks like an S3 key (contains `/`), download via `S3SharedStorage.download(file_id)`
    - If provider is `'google_drive'` or key looks like a Drive file ID (no `/`), use existing `GoogleDriveService.download_file_content()`
    - Preserve error handling and audit logging unchanged
    - _Bug_Condition: isBugCondition(X) where X.operation = 'fetch_template_content' and provider = 's3_shared'_
    - _Expected_Behavior: Template downloaded via S3SharedStorage.download(s3_key)_
    - _Preservation: Google Drive tenants continue to use GoogleDriveService.download_file_content()_
    - _Requirements: 2.8, 3.7_

- [x] 12. Fix `xlsx_export.py` — Add provider-aware file download
  - [x] 12.1 Add provider-aware download in `export_files()`
    - When processing `DocUrl` values, check if the URL is an S3 key (no `drive.google` in it)
    - If S3 key, download via `S3SharedStorage.download(key)` instead of Google Drive API
    - Update `_get_drive_service()`: if provider is `'s3_shared'`, return `None` (skip Drive initialization)
    - Add `_download_s3_file(key, destination_folder)` method for S3 downloads
    - Preserve local file operations (temp files, workbook writing) unchanged
    - _Bug_Condition: isBugCondition(X) where DocUrl is an S3 key_
    - _Expected_Behavior: File downloaded from S3 by key and saved to destination folder_
    - _Preservation: Google Drive URLs continue to use Drive API, local operations unchanged_
    - _Requirements: 2.3, 3.3_

- [x] 13. Verify bug condition exploration test now passes
  - [x] 13.1 Re-run bug condition exploration test
    - **Property 1: Expected Behavior** - S3 Tenants Get Provider-Appropriate Storage
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (S3 tenants use S3SharedStorage, not GoogleDriveService)
    - When this test passes, it confirms the expected behavior is satisfied across all affected code paths
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — S3 tenants now route to S3SharedStorage)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12_

  - [x] 13.2 Verify preservation tests still pass
    - **Property 2: Preservation** - Google Drive Tenants Unaffected
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — Google Drive tenants still use GoogleDriveService)
    - Confirm all tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

- [x] 14. Unit tests for `storage_resolver.py`
  - [x] 14.1 Write unit tests for resolver functions
    - Test file: `backend/tests/unit/test_storage_resolver.py`
    - Test `resolve_storage_provider()` returns `'google_drive'` for `None`, empty string, `'google_drive'`
    - Test `resolve_storage_provider()` returns `'s3_shared'` for `'s3_shared'`, `'s3_tenant'`
    - Test `list_s3_folders()` correctly parses `list_objects_v2` response with CommonPrefixes
    - Test `list_s3_folders()` includes folders from `.folder` marker objects
    - Test `create_s3_folder()` creates correct marker object key `{tenant}/invoices/{name}/.folder`
    - Test edge cases: empty tenant, special characters in folder names, unicode folder names
    - _Requirements: 2.1, 2.2, 2.9_

- [x] 15. Integration tests for provider routing
  - [x] 15.1 Write integration tests for end-to-end provider routing
    - Test file: `backend/tests/integration/test_provider_aware_routing.py`
    - Test full folder listing flow for S3 tenant with mocked S3 responses
    - Test full invoice upload flow for S3 tenant (mock S3 `put_object`)
    - Test full report output flow for S3 tenant (mock S3 `put_object`)
    - Test storage admin endpoints for S3 tenant (mock `list_objects_v2`, `head_bucket`)
    - Test that switching a tenant from `google_drive` to `s3_shared` routes correctly
    - Test mixed scenario: two tenants with different providers in same request sequence
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.9, 2.10, 2.11, 2.12_

- [x] 16. Checkpoint - Ensure all tests pass
  - Run full test suite: `pytest backend/tests/unit/test_provider_aware_bug_condition.py backend/tests/unit/test_provider_aware_preservation.py backend/tests/unit/test_storage_resolver.py backend/tests/integration/test_provider_aware_routing.py -v`
  - Ensure all property-based tests pass (bug condition test passes on fixed code, preservation tests still pass)
  - Ensure unit tests for storage_resolver pass
  - Ensure integration tests pass
  - Run existing test suite to confirm no regressions: `pytest backend/tests/ -m "not e2e" --tb=short`
  - Ask the user if questions arise

## Notes

- The `output_service.py` already has a working `_handle_s3_upload()` implementation — task 6 only needs to add routing logic in `handle_output()` to check provider when destination is 'gdrive'
- The `storage/storage_provider.py` factory (`get_storage_provider()`) already resolves tenant provider from ParameterService — `storage_resolver.py` provides simpler helper functions for the routing layer
- Property-based tests use Hypothesis (Python) since the backend is Flask/Python
- All S3 operations use the existing `S3SharedStorage` class — no new storage implementation needed
- The marker object pattern (`{tenant}/invoices/{folder_name}/.folder`) ensures empty folders appear in listings before any files are uploaded
