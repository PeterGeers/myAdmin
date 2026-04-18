# Implementation Plan: Template Management Defaults

## Overview

Add two new API endpoints (download default template, delete tenant template) and their corresponding frontend buttons to the existing Template Management module. Fix the `valid_types` list to include `zzp_invoice`. All changes reuse existing patterns and stay within existing files.

## Tasks

- [x] VALID_TEMPLATE_TYPES
  - 1 Add shared VALID_TEMPLATE_TYPES constant and fix valid_types
  - 1.1 Define `VALID_TEMPLATE_TYPES` constant at module level in `backend/src/tenant_admin_routes.py`
    - List all 7 types: `str_invoice_nl`, `str_invoice_en`, `btw_aangifte`, `aangifte_ib`, `toeristenbelasting`, `financial_report`, `zzp_invoice`
    - _Requirements: 3.1, 3.2_
  - 1.2 Replace the inline `valid_types` list in `get_current_template_endpoint` with `VALID_TEMPLATE_TYPES`
    - Also replace any other inline `valid_types` lists in existing template endpoints
    - _Requirements: 3.1, 3.2, 3.3_
  - 1.3 Write unit tests for VALID_TEMPLATE_TYPES
    - Test constant contains all 7 types including `zzp_invoice`
    - Test GET `/api/tenant-admin/templates/zzp_invoice` no longer returns 400
    - _Requirements: 3.1, 3.3_

- [x] 2. Implement download default template endpoint
  - 2.1 Add `GET /api/tenant-admin/templates/<template_type>/default` endpoint in `backend/src/tenant_admin_routes.py`
  - Use `@cognito_required(required_permissions=[])` decorator
  - Validate tenant admin access using existing `is_tenant_admin()` pattern
  - Validate `template_type` against `VALID_TEMPLATE_TYPES`
  - Use `TemplateService._get_local_default_metadata()` and `_LOCAL_DEFAULTS` to locate the default file
  - Read file content from disk and return JSON with `template_content`, `filename` (`{type}_default.html`), and `field_mappings`
  - Return 404 if no default template file exists for the type
  - Return 403 if user is not tenant admin
  - Return 400 if template type is invalid
  - _Requirements: 1.3, 1.5, 1.6, 4.1, 4.3_
  - 2.2 Write unit tests for download default endpoint
  - Test valid type returns 200 with correct content and filename
  - Test invalid type returns 400
  - Test type with no `_LOCAL_DEFAULTS` entry returns 404
  - Test non-tenant-admin returns 403
  - _Requirements: 1.3, 1.5, 1.6_

- [x] 3. Implement delete tenant template endpoint
  - 3.1 Add `DELETE /api/tenant-admin/templates/<template_type>` endpoint in `backend/src/tenant_admin_routes.py`
    - Use `@cognito_required(required_permissions=[])` decorator
    - Validate tenant admin access using existing `is_tenant_admin()` pattern
    - Validate `template_type` against `VALID_TEMPLATE_TYPES`
    - Execute parameterised UPDATE query: `SET is_active = FALSE, status = 'archived', updated_at = NOW()` on `tenant_template_config`
    - Return 200 with success message and `deactivated_file_id`
    - Return 404 if no active tenant template exists
    - Return 403 if user is not tenant admin
    - Log audit entry with user email, tenant, template type, and deactivated file ID
    - _Requirements: 2.4, 2.5, 2.7, 2.8, 2.9, 2.10, 4.2, 4.3_
  - 3.2 Write unit tests for delete tenant template endpoint
    - Test successful deactivation returns 200, verify `is_active=FALSE` and `status='archived'` in DB
    - Test delete when no active template returns 404
    - Test non-tenant-admin returns 403
    - Test audit log entry is written
    - _Requirements: 2.4, 2.5, 2.7, 2.8, 2.9, 2.10_

- [x] 4. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Add frontend API functions
  - 5.1 Add `DefaultTemplateResponse` and `DeleteTemplateResponse` interfaces to `frontend/src/services/templateApi.ts`
    - _Requirements: 5.1, 5.2_
  - 5.2 Add `downloadDefaultTemplate()` function to `frontend/src/services/templateApi.ts`
    - Call `GET /api/tenant-admin/templates/{type}/default` via `authenticatedRequest`
    - Throw Error with server message on non-OK response
    - _Requirements: 5.1, 5.3_
  - 5.3 Add `deleteTenantTemplate()` function to `frontend/src/services/templateApi.ts`
    - Call `DELETE /api/tenant-admin/templates/{type}` via `authenticatedRequest`
    - Throw Error with server message on non-OK response
    - _Requirements: 5.2, 5.4_

- [x] 6. Add UI buttons to TemplateUpload component
  - 6.1 Add "Download Default Template" button in `frontend/src/components/TenantAdmin/TemplateManagement/TemplateUpload.tsx`
    - Show in the warning alert block when no tenant template exists
    - On click: call `downloadDefaultTemplate()`, create Blob, trigger browser download with `{type}_default.html` filename
    - Hide when a tenant template exists
    - _Requirements: 1.1, 1.2, 1.4, 1.7_
  - 6.2 Add "Delete Template" button with confirmation dialog in `TemplateUpload.tsx`
    - Show alongside existing template info when a tenant template exists
    - Use Chakra `AlertDialog` for confirmation before deletion
    - On confirm: call `deleteTenantTemplate()`, show success toast, reset `currentTemplate` to `null` to refresh status
    - On cancel: close dialog without API call
    - Use red/destructive color scheme for the button
    - _Requirements: 2.1, 2.2, 2.3, 2.6, 4.4_
  - 6.3 Write frontend unit tests for new API functions and UI buttons
    - Test `downloadDefaultTemplate()` calls correct endpoint and returns response
    - Test `deleteTenantTemplate()` calls correct endpoint and returns response
    - Test both functions throw Error on non-OK responses
    - Test "Download Default Template" button appears when no tenant template exists
    - Test "Delete Template" button appears when tenant template exists
    - Test confirmation dialog flow
    - _Requirements: 1.1, 1.7, 2.1, 2.2, 5.1, 5.2, 5.3, 5.4_

- [x] 6.4 Update user documentation
- Update/review all user documentaion in mkdocs related to template management in NL and UK
- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - merge with main on github

## Notes

- All tasks including tests are required
- Each task references specific requirements for traceability
- All backend changes are in `backend/src/tenant_admin_routes.py` — no new files needed
- All frontend changes are in `templateApi.ts` and `TemplateUpload.tsx` — no new components
- The delete operation is a soft-delete (`is_active = FALSE`) preserving template history
- No new dependencies or architectural patterns are introduced (Requirement 4.5)
