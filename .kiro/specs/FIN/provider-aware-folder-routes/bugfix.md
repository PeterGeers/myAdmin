# Bugfix Requirements Document

## Introduction

Six code paths in the backend unconditionally use `GoogleDriveService` for file storage operations, making them non-functional for tenants configured with `invoice_provider=s3_shared` or `invoice_provider=s3_tenant`. When an S3 tenant hits any of these paths, the operation either fails (no Google Drive credentials), returns empty/wrong results, or silently stores files in an inaccessible location. This completely blocks invoice import, report generation, template management, missing invoice detection, and storage administration for all S3-based tenants.

The principle: every code path that touches file storage must check `storage.invoice_provider` and route to the appropriate backend. S3 tenants must NEVER hit `GoogleDriveService`.

## Affected Code Paths

| File                                 | What it does                                          | Fix needed                                                                    |
| ------------------------------------ | ----------------------------------------------------- | ----------------------------------------------------------------------------- |
| `routes/folder_routes.py`            | List/create folders                                   | ✅ Yes — route to S3 prefix listing/marker creation                           |
| `services/invoice_service.py`        | `upload_to_drive` — uploads invoices                  | ✅ Yes — route to `S3SharedStorage.upload()`                                  |
| `services/output_service.py`         | Uploads reports/exports to Google Drive               | ✅ Yes — route to `{tenant}/reports/` in S3                                   |
| `routes/missing_invoices_routes.py`  | Lists Drive folders for missing invoice detection     | ✅ Yes — route to S3 prefix listing                                           |
| `routes/tenant_admin_storage.py`     | Storage config, folder validation, usage stats        | ✅ Yes — S3 bucket/prefix validation and size calculation                     |
| `str_invoice_routes.py`              | Template upload to Drive                              | ✅ Yes — route to `{tenant}/templates/` in S3                                 |
| `services/email_template_service.py` | Downloads tenant-specific email templates from Drive  | ✅ Yes — download from S3 via stored key (generic/system templates unchanged) |
| `tenant_admin_routes.py`             | Downloads tenant-specific template content from Drive | ✅ Yes — download from S3 via stored key (generic/system templates unchanged) |
| `xlsx_export.py`                     | Downloads invoice files from Drive for export         | ✅ Yes — download from S3 instead of Drive, local output unchanged            |
| `scripts/*`                          | Deployment/admin scripts                              | ❌ No — manual/one-off tools, Google Drive only                               |

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a tenant with `invoice_provider=s3_shared` calls `GET /api/folders` THEN the system calls `GoogleDriveService.list_subfolders()` which fails or returns empty results because the tenant has no Google Drive credentials configured

1.2 WHEN a tenant with `invoice_provider=s3_shared` calls `POST /api/create-folder` THEN the system attempts to create a Google Drive folder via `GoogleDriveService.create_folder()` which either fails silently or creates an inaccessible folder instead of persisting an S3 reference prefix

1.3 WHEN a tenant with `invoice_provider=s3_shared` uploads an invoice via `POST /api/upload` THEN the system calls `InvoiceService.upload_to_drive()` which uses `GoogleDriveService` unconditionally, ignoring the tenant's configured storage provider

1.4 WHEN a tenant with `invoice_provider=s3_shared` triggers missing invoice detection via `POST /api/upload-receipt` THEN the system calls `GoogleDriveService.list_subfolders()` and `GoogleDriveService.upload_file()` to find/create supplier folders and upload receipts, which fails for S3 tenants

1.5 WHEN a tenant with `invoice_provider=s3_shared` generates a report with `output_destination='gdrive'` THEN `OutputService._handle_gdrive_upload()` calls `GoogleDriveService` to upload the report, which fails because the tenant has no Google Drive folder structure

1.6 WHEN a tenant with `invoice_provider=s3_shared` calls `POST /generate-invoice` with `output_destination='gdrive'` THEN the STR invoice output is routed to Google Drive via `OutputService`, which fails for S3 tenants

1.7 WHEN a tenant with `invoice_provider=s3_shared` calls `POST /upload-template` THEN the system unconditionally uses `GoogleDriveService` to upload templates to a Google Drive folder, which fails for S3 tenants

1.8 WHEN a tenant with `invoice_provider=s3_shared` uses `EmailTemplateService._load_from_google_drive()` to fetch a custom template THEN the system calls `GoogleDriveService.download_file_content()` which fails because the template is stored in S3, not Google Drive

1.9 WHEN a tenant with `invoice_provider=s3_shared` calls `GET /api/tenant-admin/storage/folders` THEN the system calls `GoogleDriveService(tenant).list_subfolders()` which fails or returns empty results

1.10 WHEN a tenant with `invoice_provider=s3_shared` calls `POST /api/tenant-admin/storage/test` THEN the system calls `GoogleDriveService` to test folder accessibility, which is meaningless for S3 tenants

1.11 WHEN a tenant with `invoice_provider=s3_shared` calls `GET /api/tenant-admin/storage/usage` THEN the system calls `GoogleDriveService` to calculate folder sizes via the Drive API, which fails for S3 tenants

1.12 WHEN a tenant with `invoice_provider=s3_shared` calls `PUT /api/tenant-admin/storage/config` with `validate=True` THEN the system validates folder IDs against Google Drive, which is irrelevant for S3 tenants

### Expected Behavior (Correct)

2.1 WHEN a tenant with `invoice_provider=s3_shared` calls `GET /api/folders` THEN the system SHALL list existing reference number prefixes from S3 by extracting unique `{reference}` values from keys matching `{tenant}/invoices/{reference}/`

2.2 WHEN a tenant with `invoice_provider=s3_shared` calls `POST /api/create-folder` THEN the system SHALL persist the reference name via a zero-byte marker object at `{tenant}/invoices/{reference}/.folder` so it appears in the folder dropdown before any files are uploaded

2.3 WHEN a tenant with `invoice_provider=s3_shared` uploads an invoice via `POST /api/upload` with a selected folder name THEN the system SHALL upload the file using `S3SharedStorage.upload()` with `metadata={'reference_number': folder_name}` so the file is stored at `{tenant}/invoices/{folder_name}/{uuid}_{filename}`

2.4 WHEN a tenant with `invoice_provider=s3_shared` triggers missing invoice detection via `POST /api/upload-receipt` THEN the system SHALL list S3 prefixes under `{tenant}/invoices/` to find supplier folders, create new prefixes via marker objects if needed, and upload the receipt via `S3SharedStorage.upload()` with appropriate metadata

2.5 WHEN a tenant with `invoice_provider=s3_shared` generates a report with any output destination THEN `OutputService` SHALL upload the report to S3 at `{tenant}/reports/{filename}` via `S3SharedStorage.upload(category='reports')` instead of calling `GoogleDriveService`

2.6 WHEN a tenant with `invoice_provider=s3_shared` calls `POST /generate-invoice` with output destination THEN the STR invoice output SHALL be routed to S3 via `OutputService` using the S3 path, not Google Drive

2.7 WHEN a tenant with `invoice_provider=s3_shared` calls `POST /upload-template` THEN the system SHALL upload templates to S3 at `{tenant}/templates/{uuid}_{filename}` via `S3SharedStorage.upload(category='templates')` and store the S3 key in the database

2.8 WHEN a tenant with `invoice_provider=s3_shared` uses `EmailTemplateService` to fetch a custom template THEN the system SHALL download the template from S3 using the stored S3 key via `S3SharedStorage.download()` instead of calling `GoogleDriveService.download_file_content()`

2.9 WHEN a tenant with `invoice_provider=s3_shared` calls `GET /api/tenant-admin/storage/folders` THEN the system SHALL list S3 prefixes under `{tenant}/` using `list_objects_v2` with delimiter to show the folder structure

2.10 WHEN a tenant with `invoice_provider=s3_shared` calls `POST /api/tenant-admin/storage/test` THEN the system SHALL validate S3 access by performing a `head_bucket` call and a test `put_object`/`delete_object` cycle on the shared bucket

2.11 WHEN a tenant with `invoice_provider=s3_shared` calls `GET /api/tenant-admin/storage/usage` THEN the system SHALL calculate storage usage by calling `list_objects_v2` on the tenant's S3 prefix and summing object sizes

2.12 WHEN a tenant with `invoice_provider=s3_shared` calls `PUT /api/tenant-admin/storage/config` with `validate=True` THEN the system SHALL validate S3 configuration (bucket exists, prefix is writable) instead of validating Google Drive folder IDs

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a tenant with `invoice_provider=google_drive` calls `GET /api/folders` THEN the system SHALL CONTINUE TO list subfolders from Google Drive using `GoogleDriveService.list_subfolders()`

3.2 WHEN a tenant with `invoice_provider=google_drive` calls `POST /api/create-folder` THEN the system SHALL CONTINUE TO create a folder in Google Drive using `GoogleDriveService.create_folder()`

3.3 WHEN a tenant with `invoice_provider=google_drive` uploads an invoice via `POST /api/upload` THEN the system SHALL CONTINUE TO upload the file to Google Drive using `GoogleDriveService.upload_file()`

3.4 WHEN a tenant with `invoice_provider=google_drive` triggers missing invoice detection via `POST /api/upload-receipt` THEN the system SHALL CONTINUE TO use `GoogleDriveService` for folder listing, creation, and file upload

3.5 WHEN a tenant with `invoice_provider=google_drive` generates a report with `output_destination='gdrive'` THEN `OutputService` SHALL CONTINUE TO upload to Google Drive using `GoogleDriveService`

3.6 WHEN a tenant with `invoice_provider=google_drive` calls `POST /upload-template` THEN the system SHALL CONTINUE TO upload templates to Google Drive folders

3.7 WHEN a tenant with `invoice_provider=google_drive` uses `EmailTemplateService` to fetch a custom template THEN the system SHALL CONTINUE TO download from Google Drive using `GoogleDriveService.download_file_content()`

3.8 WHEN a tenant with `invoice_provider=google_drive` uses any `GET/POST/PUT` endpoint under `/api/tenant-admin/storage/` THEN the system SHALL CONTINUE TO use `GoogleDriveService` for folder listing, validation, and usage statistics

3.9 WHEN the system is in test mode (`flag=True`) THEN the folder listing SHALL CONTINUE TO return local config-based folders regardless of the tenant's `invoice_provider` setting

3.10 WHEN a regex filter is provided to `GET /api/folders` THEN the system SHALL CONTINUE TO apply the regex filter to the folder list regardless of the storage provider

3.11 WHEN a tenant with any `invoice_provider` generates a report with `output_destination='download'` THEN `OutputService` SHALL CONTINUE TO return content directly to the frontend without any storage backend interaction

---

## Bug Condition (Formal)

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type StorageRequest (tenant, endpoint, operation)
  OUTPUT: boolean

  // Returns true when the tenant uses S3 storage but the code path uses Google Drive
  provider ← ParameterService.get_param('storage', 'invoice_provider', tenant=X.tenant)
  RETURN provider IN ('s3_shared', 's3_tenant')
END FUNCTION
```

### Fix Checking Property

```pascal
// Property: S3 tenants get provider-appropriate storage operations across ALL paths
FOR ALL X WHERE isBugCondition(X) DO

  // Path 1: Folder listing/creation
  IF X.endpoint = 'GET /api/folders' THEN
    result ← get_folders'(X)
    ASSERT result contains S3 reference prefixes from {X.tenant}/invoices/
    ASSERT GoogleDriveService is NOT instantiated
  END IF

  IF X.endpoint = 'POST /api/create-folder' THEN
    result ← create_folder'(X)
    ASSERT marker object exists at {X.tenant}/invoices/{folder_name}/.folder
    ASSERT subsequent GET /api/folders includes the new reference
    ASSERT GoogleDriveService is NOT instantiated
  END IF

  // Path 2: Invoice upload
  IF X.endpoint = 'POST /api/upload' THEN
    result ← upload'(X)
    ASSERT file is stored via S3SharedStorage.upload()
    ASSERT metadata contains reference_number = X.folder_name
    ASSERT S3 key matches {X.tenant}/invoices/{folder_name}/{uuid}_{filename}
    ASSERT GoogleDriveService is NOT instantiated
  END IF

  // Path 3: Missing invoices / receipt upload
  IF X.endpoint = 'POST /api/upload-receipt' THEN
    result ← upload_receipt'(X)
    ASSERT supplier folder lookup uses S3 prefix listing
    ASSERT file is stored via S3SharedStorage.upload()
    ASSERT GoogleDriveService is NOT instantiated
  END IF

  // Path 4: Report/export output
  IF X.endpoint IN report_generation_endpoints AND X.destination != 'download' THEN
    result ← handle_output'(X)
    ASSERT file is stored at {X.tenant}/reports/{filename} via S3SharedStorage
    ASSERT GoogleDriveService is NOT instantiated
  END IF

  // Path 5: Template upload/download
  IF X.endpoint = 'POST /upload-template' THEN
    result ← upload_template'(X)
    ASSERT templates stored at {X.tenant}/templates/{uuid}_{filename} via S3SharedStorage
    ASSERT S3 key is persisted in database
    ASSERT GoogleDriveService is NOT instantiated
  END IF

  IF X.operation = 'fetch_template' THEN
    result ← load_template'(X)
    ASSERT template downloaded via S3SharedStorage.download(s3_key)
    ASSERT GoogleDriveService is NOT instantiated
  END IF

  // Path 6: Storage admin functions
  IF X.endpoint = 'GET /api/tenant-admin/storage/folders' THEN
    result ← list_admin_folders'(X)
    ASSERT result contains S3 prefixes from list_objects_v2
    ASSERT GoogleDriveService is NOT instantiated
  END IF

  IF X.endpoint = 'POST /api/tenant-admin/storage/test' THEN
    result ← test_access'(X)
    ASSERT validation uses S3 head_bucket and put/delete cycle
    ASSERT GoogleDriveService is NOT instantiated
  END IF

  IF X.endpoint = 'GET /api/tenant-admin/storage/usage' THEN
    result ← get_usage'(X)
    ASSERT usage calculated from S3 list_objects_v2 size summation
    ASSERT GoogleDriveService is NOT instantiated
  END IF

  IF X.endpoint = 'PUT /api/tenant-admin/storage/config' AND X.validate = True THEN
    result ← validate_config'(X)
    ASSERT validation checks S3 bucket/prefix accessibility
    ASSERT GoogleDriveService is NOT instantiated
  END IF

END FOR
```

### Preservation Checking Property

```pascal
// Property: Google Drive tenants are completely unaffected
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
  // Google Drive tenants continue to use GoogleDriveService for all storage operations
  // Test mode continues to use local folders for folder listing
  // Download-only operations remain unchanged regardless of provider
END FOR
```
