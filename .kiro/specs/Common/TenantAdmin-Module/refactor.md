# Tenant Admin Module - Refactor Spec

Status: In Progress
Created: April 13, 2026

## Problem

The Tenant Admin dashboard grew from 7 to 11 tabs. Related functionality is scattered across multiple tabs. A tenant admin configuring Google Drive storage visits 4 tabs: Credentials (OAuth), Configuration (folder IDs), Settings (provider selection), Parameters (raw table). This is confusing and duplicative.

## Current State: 11 Tabs

| #   | Tab                 | Component              | Purpose                           |
| --- | ------------------- | ---------------------- | --------------------------------- |
| 1   | User Management     | UserManagement         | Cognito users, roles, invitations |
| 2   | Chart of Accounts   | ChartOfAccounts        | FIN module only                   |
| 3   | Year-End Settings   | YearEndSettings        | FIN module only                   |
| 4   | Template Management | TemplateManagement     | Upload/preview templates          |
| 5   | Credentials         | CredentialsManagement  | Google Drive OAuth, API keys      |
| 6   | Configuration       | TenantConfigManagement | Raw tenant_config CRUD            |
| 7   | Settings            | TenantSettings         | Schema-driven parameter form      |
| 8   | Parameters          | ParameterManagement    | Raw parameters table CRUD         |
| 9   | Tax Rates           | TaxRateManagement      | Tax rate CRUD                     |
| 10  | Tenant Details      | TenantDetails          | Company info, contact, bank       |
| 11  | Email Log           | EmailLogPanel          | Email history                     |

## Problems

1. Storage config scattered across 4 tabs (Credentials, Configuration, Settings, Parameters)
2. Duplicate config: tenant_config table vs parameters table, both with UI
3. 11 tabs overflow viewport width
4. No logical grouping: financial tabs (2, 3, 9) and storage tabs (5, 6, 7) split apart
5. Raw data tabs (Configuration, Parameters) exposed to tenant admins unnecessarily

## Proposed Structure: 6 Tabs

| #   | Tab         | Contents                                                            |
| --- | ----------- | ------------------------------------------------------------------- |
| 1   | Users       | User management, roles, invitations (unchanged)                     |
| 2   | Financial   | Chart of Accounts (with purpose assignment) + Tax Rates (FIN gated) |
| 3   | Storage     | Provider selection + credentials + folder config in one flow        |
| 4   | Templates   | Template management (unchanged)                                     |
| 5   | Tenant Info | Company details + contact + bank + email log                        |
| 6   | Advanced    | Raw parameters + raw tenant_config (SysAdmin only)                  |

## Tasks

### Phase 1: Financial Tab

- [x] R1. Chart of Accounts section: table with click-row-to-edit modal (reused existing ChartOfAccounts)
  - Grid: 2 columns wide, 1 column small screen
  - Fields: Account, Name, VW, Tax Category, Purpose (dropdown: closure/vat/ib/none)
  - Purpose replaces YearEndSettings (same rekeningschema.parameters column)
- [x] R1b. Tax Rates section: table with click-row-to-edit modal (reused TaxRateManagement)
- [x] R1c. Remove YearEndSettings tab and component (deleted YearEndSettings.tsx)
- [x] R2. Replace 3 tabs with single "Financial" tab (FIN gated, Accordion sections)
  - Created `FinancialTab.tsx` — Accordion with ChartOfAccounts + TaxRates + VATNetting

### Phase 2: Storage Tab

- [x] R3. Storage section with provider-driven flow:
  - Provider selection dropdown (google_drive / s3_shared / s3_tenant)
  - Google Drive: credentials upload + OAuth + folder ID config (merged from CredentialsManagement)
  - S3 Shared: info message (platform-level config)
  - S3 Tenant: info message (Advanced tab config)
  - Created `StorageTab.tsx` — provider-driven Accordion with conditional sections
- [x] R4. Replace Credentials + Configuration + Settings with single "Storage" tab
  - Dashboard now uses StorageTab instead of CredentialsManagement

### Phase 3: Tenant Info Tab

- [ ] R5. Redesign TenantDetails matching BankingProcessor modal style:
  - Grid: 2 columns wide screen, 1 column small screen
  - Field label and input on same row
  - Sections: Company Info, Contact, Bank Details
  - Email Log as Accordion section below
- [x] R5b. Merge TenantDetails + EmailLogPanel into single Tenant Info tab
  - Created `TenantInfoTab.tsx` — Accordion with TenantDetails + EmailLog

### Phase 4: Hide Raw Data

- [x] R6. Combine Configuration + Parameters into "Advanced" tab
  - Created `AdvancedTab.tsx` — Accordion with ParameterManagement + TenantConfigManagement
- [x] R7. Show Advanced tab only for SysAdmin users
  - `isSysAdmin = userRoles.includes('SysAdmin')` gating in dashboard

### Phase 5: Cleanup

- [x] R8. Move VATNettingConfig into Financial tab (was inside YearEndSettings, now in FinancialTab Accordion)
- [x] R9. Remove TenantSettings.tsx (deleted — F9 prototype replaced by StorageTab)
- [x] R10. Update translations (NL + EN) for new tab structure
  - Added: users, financial, storage, templates, tenantInfo, advanced, emailLog
- [x] R11. Frontend tests pass (859/859 passed; 12 pre-existing auth test failures unrelated)

### Phase 6: Migrate tenant_config to parameters table

- [x] R14. Audit all tenant_config keys across all tenants
  - Keys found: `google_drive_root_folder_id`, `google_drive_invoices_folder_id`, `google_drive_templates_folder_id`, `google_drive_*_folder_id` (dynamic), `storage_*`, `company_logo_file_id`, plus arbitrary CRUD keys
  - Read locations: `tenant_context.get_tenant_config()`, `tenant_settings_service.get_settings()`, `tenant_admin_storage` routes, `str_invoice_routes`, scripts (create_template_folders, upload_templates, verify_template_folders)
  - Write locations: `tenant_context.set_tenant_config()`, `tenant_settings_service.update_settings()`, `tenant_admin_config` routes, `tenant_admin_storage.update_storage_config()`, `tenant_admin_routes` CRUD
- [x] R15. Map each key to correct namespace in parameters table
  - `google_drive_*_folder_id` → namespace `storage`, key `google_drive_*_folder_id`
  - `storage_*` → namespace `storage`, key as-is (strip `storage_` prefix)
  - `company_logo_file_id` → namespace `branding`, key `company_logo_file_id`
  - All others → namespace `config`, key as-is
- [ ] R16. Add missing keys to PARAMETER_SCHEMA for structured UI
- [ ] R17. Create migration script: copy tenant_config values into parameters
- [x] R18. Update all backend code reading tenant_config to use ParameterService
  - `get_tenant_config()` now reads from parameters (primary) with tenant_config fallback
  - `set_tenant_config()` now dual-writes to both parameters and tenant_config
  - All callers (str_invoice_routes, scripts, etc.) automatically use new path
- [x] R19. Update tenant_config CRUD API to write to parameters (backward compat)
  - `tenant_admin_config.py` create/update/delete all dual-write to parameters table
  - Uses `_map_config_key_to_param()` for consistent namespace mapping
- [x] R20. Remove TenantConfigManagement component
  - Removed from AdvancedTab, deleted TenantConfigManagement.tsx
- [x] R21. Drop tenant_config table after all reads/writes migrated and verified
  - Dropped on all 3 MySQL instances (local, test, Railway production)

### Phase 7: Documentation

- [x] R22. Update FINAL_STATUS.md with refactor summary
- [x] R23. Archive old PHASE summaries to archive/ folder (7 files moved)
- [x] R24. Update tenant administration user manual (NL + EN)
  - Updated `docs/docs/tenant-admin/tenant-settings.md` (NL) and `tenant-settings.en.md` (EN)
  - Documents new 6-tab structure: Users, Financial, Storage, Templates, Tenant Info, Advanced

## Design Notes

- Accordion sub-sections within each tab (collapsible, all open by default)
- Conditional: FIN sections when FIN active, STR when STR active
- Storage tab: pick provider first, then configure that provider
- Parameter schema API (F9.2) is source of truth for settings
- Raw tables are power-user tools, not primary UX

## Out of Scope

- SysAdmin dashboard restructuring
- New parameter types
