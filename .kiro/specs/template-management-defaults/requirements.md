# Requirements Document

## Introduction

The Template Management module already supports uploading, previewing, validating, approving, and AI-assisted fixing of tenant-specific HTML templates for all seven template types. Template resolution falls back from a tenant-specific template (stored in Google Drive via `tenant_template_config`) to a built-in local default (stored in `backend/templates/`).

Two capabilities are missing:

1. **Download default template** — When no tenant-specific template exists for a given type, the user cannot obtain the built-in default file to use as a starting point for customisation.
2. **Delete tenant template** — When a tenant-specific template exists, the user cannot remove it and revert to the built-in default.

Additionally, the `valid_types` list in the existing `GET /api/tenant-admin/templates/<template_type>` endpoint is missing `zzp_invoice`, which prevents that template type from being retrieved.

This feature adds the two missing operations and fixes the `valid_types` list so all seven template types are consistently supported.

## Glossary

- **Template_Management_UI**: The React frontend component (`TemplateUpload.tsx`) that lets Tenant Administrators select a template type, view current template status, upload new templates, and manage templates.
- **Template_API**: The backend Flask blueprint (`tenant_admin_routes.py`) that exposes REST endpoints under `/api/tenant-admin/templates/`.
- **Template_Service**: The backend service (`template_service.py`) that resolves templates using the tenant-specific → local-default fallback chain.
- **Default_Template**: A built-in HTML template file stored in the `backend/templates/html/` directory, used as fallback when no tenant-specific template exists.
- **Tenant_Template**: A tenant-specific template stored in tenant supported storage and tracked in the `tenant_template_config` database table.
- **Tenant_Admin**: A user with the Tenant_Admin role who manages templates for their organisation.
- **Template_Type**: One of the seven supported template identifiers: `str_invoice_nl`, `str_invoice_en`, `btw_aangifte`, `aangifte_ib`, `toeristenbelasting`, `financial_report`, `zzp_invoice`.
- **LOCAL_DEFAULTS**: The `_LOCAL_DEFAULTS` mapping in `TemplateService` that maps each Template_Type to its local default file path.

## Requirements

### Requirement 1: Download Default Template

**User Story:** As a Tenant_Admin, I want to download the built-in default template for a template type, so that I can use it as a starting point to create a customised tenant-specific template.

#### Acceptance Criteria

1. WHEN a Tenant_Admin selects a Template_Type and no Tenant_Template exists for that type, THE Template_Management_UI SHALL display a "Download Default Template" button.
2. WHEN the Tenant_Admin clicks the "Download Default Template" button, THE Template_Management_UI SHALL call the download-default API endpoint for the selected Template_Type.
3. WHEN the download-default API endpoint receives a valid Template_Type, THE Template_API SHALL read the corresponding Default_Template file from the LOCAL_DEFAULTS mapping and return its content with the correct filename.
4. WHEN the Template_API returns the Default_Template content, THE Template_Management_UI SHALL trigger a browser file download with the filename `{template_type}_default.html`.
5. IF the download-default API endpoint receives a Template_Type that has no entry in LOCAL_DEFAULTS, THEN THE Template_API SHALL return HTTP 404 with an error message indicating no default template is available.
6. IF the download-default API endpoint is called by a user who is not a Tenant_Admin, THEN THE Template_API SHALL return HTTP 403 with an access-denied error.
7. WHEN a Tenant_Template exists for the selected Template_Type, THE Template_Management_UI SHALL hide the "Download Default Template" button and continue to show the existing "Download" and "Load & Modify" buttons for the active tenant template.

### Requirement 2: Delete Tenant Template

**User Story:** As a Tenant_Admin, I want to delete the tenant-specific template for a template type, so that the system reverts to using the built-in default template.

#### Acceptance Criteria

1. WHEN a Tenant_Admin selects a Template_Type and a Tenant_Template exists for that type, THE Template_Management_UI SHALL display a "Delete Template" button alongside the existing template information.
2. WHEN the Tenant_Admin clicks the "Delete Template" button, THE Template_Management_UI SHALL display a confirmation dialog asking the user to confirm deletion.
3. WHEN the Tenant_Admin confirms the deletion, THE Template_Management_UI SHALL call the delete-template API endpoint for the selected Template_Type.
4. WHEN the delete-template API endpoint receives a valid request, THE Template_API SHALL deactivate the Tenant_Template record in the `tenant_template_config` table by setting `is_active` to FALSE.
5. WHEN the Template_API successfully deactivates the Tenant_Template, THE Template_API SHALL return HTTP 200 with a success message.
6. WHEN the Template_Management_UI receives a successful deletion response, THE Template_Management_UI SHALL refresh the template status display to show "No active template found" and display the "Download Default Template" button.
7. WHEN the delete-template API endpoint processes a deletion, THE Template_API SHALL log an audit entry containing the user email, tenant, template type, and the deactivated file ID.
8. IF the delete-template API endpoint is called for a Template_Type that has no active Tenant_Template, THEN THE Template_API SHALL return HTTP 404 with an error message indicating no active template exists to delete.
9. IF the delete-template API endpoint is called by a user who is not a Tenant_Admin, THEN THE Template_API SHALL return HTTP 403 with an access-denied error.
10. THE Template_API SHALL deactivate the Tenant_Template record rather than permanently deleting it from the database, so that the template history is preserved.

### Requirement 3: Fix valid_types List Consistency

**User Story:** As a Tenant_Admin, I want the `GET /api/tenant-admin/templates/<template_type>` endpoint to accept all seven Template_Types, so that I can retrieve any tenant-specific template including ZZP invoices.

#### Acceptance Criteria

1. THE Template_API `GET /api/tenant-admin/templates/<template_type>` endpoint SHALL accept all seven Template_Types: `str_invoice_nl`, `str_invoice_en`, `btw_aangifte`, `aangifte_ib`, `toeristenbelasting`, `financial_report`, and `zzp_invoice`.
2. THE Template_API SHALL use a single, shared list of valid template types across the get-current, download-default, and delete-template endpoints to prevent future inconsistencies.
3. WHEN the `GET /api/tenant-admin/templates/<template_type>` endpoint receives `zzp_invoice` as the template type, THE Template_API SHALL process the request identically to any other valid Template_Type.

### Requirement 4: Reuse Existing Logic

**User Story:** As a developer, I want the new download-default and delete-template features to reuse existing code paths and patterns, so that the codebase stays maintainable and no unnecessary new code is introduced.

#### Acceptance Criteria

1. THE Template_API download-default endpoint SHALL reuse the existing `_LOCAL_DEFAULTS` mapping and `_get_local_default_metadata()` method in Template_Service to locate default template files, rather than introducing a new file-lookup mechanism.
2. THE Template_API delete-template endpoint SHALL reuse the existing `DatabaseManager` and parameterised query patterns for updating the `tenant_template_config` table, rather than introducing a new data-access layer.
3. THE Template_API new endpoints SHALL follow the same authentication and authorisation pattern (Cognito JWT validation, tenant admin check) already used by the existing template endpoints, without duplicating or reimplementing that logic.
4. THE Template_Management_UI SHALL integrate the new buttons into the existing `TemplateUpload` component's template-status section, reusing the existing `useEffect` template-loading flow and Chakra UI component patterns, rather than creating separate components or pages.
5. THE implementation SHALL not introduce new dependencies, libraries, or architectural patterns beyond what the project already uses.

### Requirement 5: Frontend API Integration

**User Story:** As a developer, I want the frontend API service layer to include functions for the new download-default and delete-template endpoints, so that the UI components can call them consistently.

#### Acceptance Criteria

1. THE `templateApi.ts` service SHALL export a `downloadDefaultTemplate` function that calls `GET /api/tenant-admin/templates/<template_type>/default` and returns the template content and filename.
2. THE `templateApi.ts` service SHALL export a `deleteTenantTemplate` function that calls `DELETE /api/tenant-admin/templates/<template_type>` and returns the success response.
3. WHEN the `downloadDefaultTemplate` function receives a non-OK response, THE function SHALL throw an Error with the server-provided error message.
4. WHEN the `deleteTenantTemplate` function receives a non-OK response, THE function SHALL throw an Error with the server-provided error message.
