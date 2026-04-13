# Frontend Tasks: Parameter & Tax Rate Administration UI

## Overview

Add tabs to TenantAdminDashboard and SysAdminDashboard for managing parameters and tax rates. Follow BankingProcessor pattern: click row to open modal, no action buttons in table.

## UI Pattern (matching BankingProcessor transactions)

- Click on row opens edit modal (cursor pointer, hover gray.600)
- Modal: ModalContent bg="gray.700", Grid 2-col, Input bg="gray.600" color="white"
- Delete button inside modal footer (left-aligned, red ghost)
- AlertDialog confirmation before delete

## Prerequisites

Backend API endpoints (completed):

- `GET/POST/PUT/DELETE /api/tenant-admin/parameters`
- `GET/POST/PUT/DELETE /api/tenant-admin/tax-rates`

## Tasks

- [x] F1. ParameterManagement component — `frontend/src/components/TenantAdmin/ParameterManagement.tsx`
- [x] F2. TaxRateManagement component — `frontend/src/components/TenantAdmin/TaxRateManagement.tsx`
- [x] F3. Tabs added to TenantAdminDashboard (Parameters + Tax Rates)
- [x] F4. SysAdmin SystemTaxRates — added to SysAdminDashboard.tsx
- [x] F5. API services — parameterService.ts + taxRateService.ts
- [x] F6. TypeScript types — parameterTypes.ts + taxRateTypes.ts
- [x] F7. Translations (NL + EN) — completed, wired up with useTypedTranslation
- [x] F8. Frontend unit tests — 18 tests (9 ParameterManagement + 9 TaxRateManagement)

## F9. Structured Settings Form

### Problem

Raw parameter table shows database contents but gives no guidance about what parameters should exist, which are required, logical grouping, or conditional sub-parameters.

### Backend

- [x] F9.1 Create `backend/src/services/parameter_schema.py` with PARAMETER_SCHEMA
- [x] F9.2 Create `GET /api/tenant-admin/parameters/schema` endpoint

### Frontend

- [x] F9.3 Create `frontend/src/components/TenantAdmin/TenantSettings.tsx`
- [x] F9.4 Add "Settings" tab, rename "Parameters" to "Advanced Parameters"
- [x] F9.5 Create parameterSchemaService.ts and parameterSchemaTypes.ts
- [x] F9.6 check Translations (NL + EN)

## F10. Cleanup: Remove invalid parameters

### Problem

Three parameters were seeded that should not be tenant-configurable:

- `default_administration` — redundant, tenant name comes from request context
- `download_folder` — OS/deployment env var, not per-tenant
- `vendor_folder_mappings` — app-level local filesystem config, test mode fallback only

### Tasks

- [x] F10.1 Remove these 3 from all databases (finance, testfinance, Railway SQL)
- [x] F10.2 Remove from seed scripts
- [x] F10.3 Revert config.py vendor_folders to not use ParameterService
- [x] F10.4 Revert str_processor.py download_folder to env var / os.getcwd()
- [x] F10.5 Exclude from F9 schema
- [x] F10.6 Clean up duplicate_detection_routes.py default_administration usage
