# BTW Export Bug Fix Summary

## Issue

BTW transaction saved successfully, but report upload to Google Drive failed with error:

```
GoogleDriveService.__init__() missing 1 required positional argument: 'administration'
```

## Root Cause

Multiple locations in the codebase were instantiating `GoogleDriveService()` without the required `administration` parameter. The `GoogleDriveService` class was updated to require tenant/administration context for multi-tenant support, but several call sites were not updated.

## Files Fixed

### 1. `backend/src/routes/tax_routes.py`

- **Function**: `btw_upload_report`
- **Change**: Added `get_current_tenant(request)` to extract administration from request context
- **Change**: Pass `administration` parameter to `btw_processor.upload_report_to_drive()`

### 2. `backend/src/btw_processor.py`

- **Function**: `upload_report_to_drive`
- **Change**: Added `administration` parameter to method signature
- **Change**: Pass `administration` to `GoogleDriveService(administration)`

### 3. `backend/src/str_invoice_routes.py`

- **Function**: `upload_template_to_drive`
- **Change**: Pass `tenant` parameter to `GoogleDriveService(tenant)`
- **Note**: This function already had tenant context from `@tenant_required()` decorator

### 4. `backend/src/routes/missing_invoices_routes.py`

- **Function**: `upload_receipt`
- **Change**: Added `get_current_tenant(request)` to extract administration
- **Change**: Pass `administration` to `GoogleDriveService(administration)`

### 5. `backend/src/xlsx_export.py`

- **Function**: `_get_drive_service`
- **Change**: Added `administration` parameter to method signature
- **Change**: Pass `administration` to `GoogleDriveService(administration)`
- **Updated callers**:
  - `export_files()` - line ~201
  - `export_files_with_progress_generator()` - line ~629
  - `export_files_with_progress()` - line ~745

### 6. `backend/src/pdf_validation.py`

- **Class**: `PDFValidator`
- **Change**: Removed immediate GoogleDriveService initialization from `__init__`
- **Change**: Added `_ensure_drive_service(administration)` method for lazy initialization
- **Change**: Call `_ensure_drive_service()` in `validate_pdf_urls_with_progress()` when administration is provided

## Testing Recommendations

1. Test BTW report generation and upload with a valid tenant
2. Test STR invoice template upload
3. Test receipt upload for missing invoices
4. Test XLSX export with Google Drive file downloads
5. Test PDF validation with Google Drive URLs

## Impact

- All Google Drive operations now properly use tenant-specific credentials
- Multi-tenant isolation is maintained across all Google Drive interactions
- No breaking changes to API contracts (administration is extracted from request context)
