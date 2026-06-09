# Bugfix Requirements Document

## Introduction

After onboarding a new tenant (Kim Geers), two issues are observed:

1. **S3 shared storage not configured** — The tenant's storage provider defaults to `s3_shared` but no bucket name is seeded during provisioning, making invoice storage non-functional.
2. **STR module visible without subscription** — The provisioning flow defaults to enabling `['FIN', 'STR', 'TENADMIN']` modules for all new tenants, regardless of what the tenant actually subscribed to. Tenants without an STR subscription see STR-related parameters and navigation items.

Both bugs originate in the provisioning flow (`sysadmin_provisioning.py` and `TenantProvisioningService`).

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a new tenant is provisioned with `s3_shared` as the default storage provider THEN the system does not seed the `storage.s3_shared_bucket` parameter, causing storage operations to fail with "S3 shared bucket not configured"

1.2 WHEN a new tenant is provisioned without explicitly specifying modules THEN the system defaults to `['FIN', 'STR', 'TENADMIN']`, enabling the STR module even when the tenant did not subscribe to STR

1.3 WHEN a tenant without STR subscription views the application THEN the system shows STR navigation items and STR-related parameters because the `tenant_modules` table contains an active STR row

1.4 WHEN a new tenant is provisioned THEN the system does not call `seed_module_params` to seed required parameters for the enabled modules, leaving module-specific configuration incomplete

1.5 WHEN an existing tenant activates a new module (e.g. ZZP or STR) via the Tenant Admin UI THEN the system does not seed the module's required parameters, leaving the newly activated module's configuration incomplete

1.6 WHEN a new tenant views parameters that have only a system default (no tenant-scope row) THEN the parameter appears read-only with a "system default" badge, requiring the user to first "Customize" (save without changes) before the field becomes editable — this is confusing for required configuration like `s3_shared_bucket` that must be set per-tenant

1.7 WHEN a tenant has `s3_shared` as their storage provider THEN the system still shows branding parameters labeled "Google Drive File ID" (e.g. `company_logo_file_id` in `str_branding` and `zzp_branding`), which is confusing because the tenant is not using Google Drive — the parameter description and storage mechanism should adapt to the configured provider

### Expected Behavior (Correct)

2.1 WHEN a new tenant is provisioned with `s3_shared` as the storage provider THEN the system SHALL seed the `storage.s3_shared_bucket` parameter with the shared bucket name (from `S3_SHARED_BUCKET` environment variable) so that storage is immediately functional

2.2 WHEN a new tenant is provisioned without explicitly specifying modules THEN the system SHALL default to only `['FIN', 'TENADMIN']` (the base subscription), not include STR unless explicitly requested

2.3 WHEN a tenant without STR in their `tenant_modules` views the application THEN the system SHALL hide STR navigation items and STR-related parameters, showing only features relevant to the tenant's active modules

2.4 WHEN a new tenant is provisioned THEN the system SHALL call `seed_module_params` for each enabled module to seed required parameters with their defaults, ensuring the tenant's configuration is complete from the start

2.5 WHEN an existing tenant activates a new module via the Tenant Admin UI THEN the system SHALL seed the module's required parameters with their defaults so the module is immediately usable

2.6 WHEN a new tenant is provisioned THEN the system SHALL create tenant-scope parameter rows (not just rely on system defaults) for required storage configuration, so that parameters are immediately editable without requiring the "Customize" step first

2.7 WHEN a tenant has `s3_shared` or `s3_tenant` as their storage provider THEN the system SHALL hide or adapt Google Drive-specific parameters (like `company_logo_file_id` labeled as "Google Drive File ID") and instead show S3-appropriate fields for logo/branding assets — the `visible_when` mechanism should be extended to branding parameters based on the storage provider

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a tenant is provisioned with STR explicitly included in the modules list THEN the system SHALL CONTINUE TO enable the STR module and show STR navigation items and parameters

3.2 WHEN a tenant has Google Drive configured as storage provider THEN the system SHALL CONTINUE TO use Google Drive without requiring S3 bucket configuration

3.3 WHEN a tenant already exists and is re-provisioned (idempotent run) THEN the system SHALL CONTINUE TO skip already-existing records without errors or duplicates

3.4 WHEN a tenant's modules are later changed via the Tenant Admin UI THEN the system SHALL CONTINUE TO correctly show/hide features based on the updated module configuration

3.5 WHEN the `TENADMIN` module is not explicitly included in the provisioning request THEN the system SHALL CONTINUE TO automatically add it (existing safety guard)

3.6 WHEN an existing tenant activates a module that has dependencies (e.g. ZZP depends on FIN) THEN the system SHALL CONTINUE TO enforce dependency checks before activation

3.7 WHEN a tenant has Google Drive as their storage provider THEN the system SHALL CONTINUE TO show Google Drive-specific parameters (folder IDs, credentials) as before
