# Implementation Plan: Parameter-Driven Configuration

## Overview

Incremental implementation following the recommended deployment order: (1) create tables and services, (2) seed system defaults, (3) replace hardcoded values one by one, (4) add storage abstraction, (5) add admin API endpoints, (6) deprecate tenant_config. Each task is independently deployable on main.

## Tasks

- [x] 1. Create database tables and migration scripts
  - [x] 1.1 Create the `parameters` table migration script
    - Create `backend/src/migrations/create_parameters_table.py`
    - SQL as specified in design: scope ENUM, scope_id, namespace, key, value JSON, value_type ENUM, is_secret, timestamps, created_by
    - Include unique key `uq_param (scope, scope_id, namespace, key)` and index `idx_tenant_ns`
    - _Requirements: 1.1_
  - [x] 1.2 Create the `tax_rates` table migration script
    - Create `backend/src/migrations/create_tax_rates_table.py`
    - SQL as specified in design: administration, tax_type, tax_code, rate DECIMAL(6,3), ledger_account, effective_from, effective_to, country_code, description, calc_method, calc_params JSON, timestamps
    - Include unique key `uq_tax_rate (administration, tax_type, tax_code, effective_from)` and index `idx_lookup`
    - _Requirements: 2.1, 2.2_
  - [x] 1.3 Create seed script for NL system default BTW rates
    - Insert `_system_` BTW rates: zero (0%, 2010), low (9%, 2021), high (21%, 2020) with effective_from 2000-01-01
    - Do NOT seed btw_accommodation or tourist_tax rates (tenant-specific per requirements)
    - _Requirements: 2.8, 2.9_

- [x] 2. Implement ParameterService with scope resolution and caching
  - [x] 2.1 Implement ParameterService core class
    - Create `backend/src/services/parameter_service.py`
    - Implement `get_param()` with scope chain: user, role, tenant, system
    - Implement `set_param()` with write-through cache invalidation
    - Implement `delete_param()` with cache invalidation
    - Implement `get_params_by_namespace()` with scope origin indicator
    - Implement `_invalidate_cache()` and `_resolve_from_db()`
    - Handle is_secret encryption/decryption via CredentialService delegation
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [x] 2.2 Write property test: Scope Resolution Order (Property 1)
    - **Property 1: Scope Resolution Order**
    - Create `backend/tests/unit/test_parameter_service_props.py`
    - Use hypothesis to generate random scope configurations with 0-4 scopes populated
    - Verify get_param returns value from most specific scope, or None when no value exists
    - **Validates: Requirements 1.2, 1.3, 1.8**
  - [x] 2.3 Write property test: Secret Parameter Round-Trip (Property 2)
    - **Property 2: Secret Parameter Round-Trip**
    - Use hypothesis to generate random string values with mocked CredentialService
    - Verify get_param(set_param(value, is_secret=True)) == value and DB value differs from plaintext
    - **Validates: Requirements 1.4, 1.5**
  - [x] 2.4 Write property test: Write-Through Cache Invalidation (Property 3)
    - **Property 3: Write-Through Cache Invalidation**
    - Use hypothesis to generate random param writes followed by reads
    - Verify set_param followed by get_param always returns the newly written value
    - **Validates: Requirements 1.7**
  - [x] 2.5 Write property test: Value Type Validation (Property 9)
    - **Property 9: Value Type Validation**
    - Use hypothesis to generate random value/type combinations (matching and mismatching)
    - Verify mismatched types are rejected, matching types succeed
    - **Validates: Requirements 7.2**
  - [x] 2.6 Write property test: Scope-Level Delete Isolation (Property 10)
    - **Property 10: Scope-Level Delete Isolation**
    - Use hypothesis to generate random multi-scope configs, delete at one scope
    - Verify other scopes unaffected and resolution falls back correctly
    - **Validates: Requirements 7.4**
  - [x] 2.7 Write property test: Parameters Table Precedence (Property 13)
    - **Property 13: Parameters Table Precedence Over tenant_config**
    - Use hypothesis to generate random params in both tenant_config and parameters tables
    - Verify ParameterService returns value from parameters table
    - **Validates: Requirements 9.5**
  - [x] 2.8 Write unit tests for ParameterService
    - Test CRUD operations, encryption delegation, cache behavior
    - Test edge cases: None returns, invalid scope, missing CredentialService for secrets
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

- [x] 3. Implement TaxRateService with date-filtered resolution
  - [x] 3.1 Implement TaxRateService core class
    - Create `backend/src/services/tax_rate_service.py`
    - Implement `get_tax_rate()` with tenant then `_system_` fallback and date range filtering
    - Implement `get_all_vat_codes()` returning all active BTW codes for a tenant and date
    - Implement `create_tax_rate()` with auto-close of overlapping existing rates
    - Implement `delete_tax_rate()` preventing deletion of system defaults by non-SysAdmin
    - Add in-process caching keyed by (administration, tax_type, tax_code, date)
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 2.7_
  - [x] 3.2 Write property test: Tax Rate Date-Filtered Resolution (Property 4)
    - **Property 4: Tax Rate Date-Filtered Resolution with Tenant Preference**
    - Create `backend/tests/unit/test_tax_rate_service_props.py`
    - Use hypothesis to generate random date ranges, tenant/system rate combinations
    - Verify tenant-specific rates preferred, system fallback works, None when no match
    - **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
  - [x] 3.3 Write property test: VAT Code Completeness (Property 5)
    - **Property 5: VAT Code Completeness for Date**
    - Use hypothesis to generate random sets of VAT codes with overlapping date ranges
    - Verify get_all_vat_codes returns exactly the matching entries, preferring tenant over system
    - **Validates: Requirements 2.7**
  - [x] 3.4 Write property test: Tax Rate Auto-Close on Overlap (Property 12)
    - **Property 12: Tax Rate Auto-Close on Overlap**
    - Use hypothesis to generate random existing rates with new overlapping rates
    - Verify existing rate's effective_to is set to new_rate.effective_from - 1 day
    - **Validates: Requirements 8.3**
  - [x] 3.5 Write unit tests for TaxRateService
    - Test seed data verification, unique constraint enforcement, date boundary cases
    - Test error cases: duplicate insert (409), invalid date range, system default deletion
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 4. Checkpoint - Tables and core services
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement TouristTaxCalculator
  - [x] 5.1 Implement TouristTaxCalculator class
    - Create `backend/src/services/tourist_tax_calculator.py`
    - Implement `calculate()` dispatching to correct formula based on calc_method
    - Implement `_calc_percentage()`: (base_amount_excl_vat / (100 + rate)) \* rate
    - Implement `_calc_fixed_per_guest_night()`: rate _ guests _ nights
    - Implement `_calc_fixed_per_night()`: rate \* nights
    - Implement `_calc_percentage_of_room_price()`: room_price \* (rate / 100)
    - Return dict with amount (rounded to 2 decimals), method, rate, description
    - Handle unknown calc_method (return amount 0, log warning) and no rate configured (amount 0, method 'none')
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_
  - [x] 5.2 Write property test: Tourist Tax Calculator Method Dispatch (Property 6)
    - **Property 6: Tourist Tax Calculator Method Dispatch**
    - Create `backend/tests/unit/test_tourist_tax_calculator_props.py`
    - Use hypothesis to generate random calc_methods, rates, amounts, nights, guests
    - Verify correct formula applied per method, 2 decimal rounding, zero for unknown methods
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**
  - [x] 5.3 Write unit tests for TouristTaxCalculator
    - Test each formula with known inputs/outputs
    - Test edge cases: zero nights/guests, negative amounts (refunds), no rate configured
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 6. Implement ModuleRegistry and module_required decorator
  - [x] 6.1 Implement ModuleRegistry and helper functions
    - Create `backend/src/services/module_registry.py`
    - Define MODULE_REGISTRY dict for FIN, STR, TENADMIN with required_params, required_tax_rates, required_roles
    - Implement `has_module(db, tenant, module_name)` replacing duplicated `has_fin_module()`
    - Implement `module_required(module_name)` decorator returning HTTP 403 if module not active
    - _Requirements: 4.1, 4.4, 4.5, 4.6_
  - [x] 6.2 Implement seed_module_params in ParameterService
    - Add `seed_module_params(tenant, module_name)` to ParameterService
    - Seed required parameters from MODULE_REGISTRY defaults for params without existing tenant-level value
    - Ensure module disable preserves parameters (no deletion)
    - _Requirements: 4.2, 4.3_
  - [x] 6.3 Write property test: Module Enable Seeds Required Parameters (Property 7)
    - **Property 7: Module Enable Seeds Required Parameters**
    - Create `backend/tests/unit/test_module_registry_props.py`
    - Use hypothesis to generate random module selections with pre-existing params
    - Verify all required params seeded without overwriting existing tenant values
    - **Validates: Requirements 4.2**
  - [x] 6.4 Write property test: Module Disable Preserves Parameters (Property 8)
    - **Property 8: Module Disable Preserves Parameters**
    - Use hypothesis to generate random param sets, disable module, verify preservation
    - Verify no parameters deleted or modified on module deactivation
    - **Validates: Requirements 4.3**
  - [x] 6.5 Write unit tests for ModuleRegistry
    - Test registry structure validation, decorator behavior, has_module function
    - Test seed_module_params with partial pre-existing params
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 7. Checkpoint - All services complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Replace hardcoded values with parameter lookups (one per sub-task)
  - [x] 8.1 Replace hardcoded default administration name
    - In `duplicate_detection_routes.py` and `toeristenbelasting_processor.py`: replace hardcoded 'GoodwinSolutions' with `parameter_service.get_param('general', 'default_administration', tenant)`
    - _Requirements: 5.1, 10.2_
  - [x] 8.2 Replace hardcoded download folder path
    - In `str_processor.py`: replace hardcoded `C:\Users\peter\Downloads` with `parameter_service.get_param('storage', 'download_folder', tenant)`
    - _Requirements: 5.2, 10.2_
  - [x] 8.3 Replace hardcoded report output path
    - In `xlsx_export.py`: replace hardcoded `C:\Users\peter\OneDrive\Admin\reports` with `parameter_service.get_param('storage', 'report_output_path', tenant)`
    - _Requirements: 5.3, 10.2_
  - [x] 8.4 Replace hardcoded Google Drive folder ID
    - In `google_drive_service.py`: replace hardcoded fallback folder ID with `parameter_service.get_param('storage', 'google_drive_folder_id', tenant)`
    - _Requirements: 5.4, 10.2_
  - [x] 8.5 Replace hardcoded vendor folder mappings
    - In `config.py`: replace hardcoded `vendor_folders` dict with `parameter_service.get_param('storage', 'vendor_folder_mappings', tenant)` (JSON type)
    - _Requirements: 5.5, 10.2_
  - [x] 8.6 Replace hardcoded VAT rates in STR processing
    - In `str_processor.py`: replace date-branching VAT logic with `tax_rate_service.get_tax_rate(tenant, 'btw_accommodation', 'standard', checkin_date)`
    - _Requirements: 5.6, 10.2_
  - [x] 8.7 Replace hardcoded VAT account numbers in BTW processing
    - In `btw_processor.py`: replace hardcoded accounts 2010/2020/2021 with `tax_rate_service.get_all_vat_codes(tenant, date)` to retrieve ledger_account values
    - _Requirements: 5.7, 10.2_
  - [x] 8.8 Replace hardcoded tourist tax calculation
    - In `str_processor.py` and `toeristenbelasting_generator.py`: replace inline percentage formulas with `tourist_tax_calculator.calculate(tenant, date, base_amount, nights, guests, room_price)`
    - _Requirements: 5.8, 10.2_

- [x] 9. Checkpoint - Hardcoded value replacements
  - Ensure all tests pass, ask the user if questions arise.
## what happens with tenant credentials, config, tenant templates 
Same answer as yesterday — nothing changes. tenant_credentials, tenant_config, tenant_template_config, and rekeningschema.parameters all stay exactly as they are. The StorageProvider abstraction doesn't touch any of those tables. It only reads from the parameters table to decide which storage backend to use (google_drive, s3_shared, or s3_ten)

- [x] 10. Implement StorageProvider abstraction
  - [x] 10.1 Create StorageProvider abstract interface and factory
    - Create `backend/src/storage/storage_provider.py`
    - Define abstract `StorageProvider` base class with upload, download, delete, list_files methods
    - Implement `get_storage_provider(tenant, parameter_service)` factory resolving provider from parameter_service
    - _Requirements: 6.1, 6.2_
  - [x] 10.2 Implement GoogleDriveStorage provider
    - Create `backend/src/storage/google_drive_storage.py`
    - Wrap existing `GoogleDriveService` behind the StorageProvider interface
    - Ensure existing Google Drive tenants are unaffected
    - _Requirements: 6.3, 10.4_
  - [x] 10.3 Implement S3SharedStorage provider
    - Create `backend/src/storage/s3_shared_storage.py`
    - Implement shared bucket with tenant-prefixed keys: `{tenant}/{referenceNumber}/{uuid}_{filename}`
    - _Requirements: 6.4_
  - [x] 10.4 Implement S3TenantStorage provider
    - Create `backend/src/storage/s3_tenant_storage.py`
    - Implement tenant's own S3 bucket using cross-account credentials from tenant_credentials
    - _Requirements: 6.5_
  - [x] 10.5 Write unit tests for StorageProvider factory and implementations
    - Test factory dispatch for each provider type
    - Test error cases: unknown provider, missing credentials, misconfigured provider
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 11. Implement Parameter Administration API
  - [x] 11.1 Create parameter admin routes blueprint
    - Create `backend/src/routes/parameter_admin_routes.py`
    - Blueprint `parameter_admin_bp`, prefix `/api/tenant-admin/parameters`
    - GET: list all parameters grouped by namespace with scope origin indicator
    - GET with `?namespace={ns}`: filter by namespace
    - POST: create parameter with value_type validation
    - PUT `/{id}`: update parameter value, invalidate cache
    - DELETE `/{id}`: delete override at specified scope
    - Require Tenant_Admin for tenant-scope, SysAdmin for system-scope operations
    - Mask secret values in GET responses for non-SysAdmin users
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_
  - [x] 11.2 Register parameter_admin_bp in app.py
    - Import and register the blueprint in the Flask app
    - _Requirements: 7.1_
  - [x] 11.3 Write property test: Secret Masking by Role (Property 11)
    - **Property 11: Secret Masking by Role**
    - Create `backend/tests/unit/test_parameter_admin_props.py`
    - Use hypothesis to generate random secret params with SysAdmin/non-SysAdmin roles
    - Verify GET masks value for non-SysAdmin, shows actual value for SysAdmin
    - **Validates: Requirements 7.6**
  - [x] 11.4 Write unit tests for Parameter Admin API
    - Test auth checks (403), validation errors (400), CRUD happy paths
    - Test namespace filtering, scope origin indicators
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 12. Implement Tax Rate Administration API
  - [x] 12.1 Create tax rate admin routes blueprint
    - Create `backend/src/routes/tax_rate_admin_routes.py`
    - Blueprint `tax_rate_admin_bp`, prefix `/api/tenant-admin/tax-rates`
    - GET: list all rates for tenant + applicable system defaults, sorted by tax_type, tax_code, effective_from
    - POST: create rate with date conflict validation and auto-close of overlapping rates
    - DELETE `/{id}`: delete tenant override (system defaults cannot be deleted without SysAdmin)
    - Require Tenant_Admin for tenant-specific, SysAdmin for system default rates
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - [x] 12.2 Register tax_rate_admin_bp in app.py
    - Import and register the blueprint in the Flask app
    - _Requirements: 8.1_
  - [x] 12.3 Write unit tests for Tax Rate Admin API
    - Test auth checks, date conflict validation, auto-close behavior, CRUD happy paths
    - Test error cases: duplicate rate (409), invalid date range, system default deletion without SysAdmin (403)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 13. Backward compatibility and tenant_config precedence
  - [x] 13.1 Implement parameters table precedence over tenant_config
    - Update ParameterService to check parameters table first; if a key exists in both tenant_config and parameters, return the parameters table value
    - Ensure existing tenant_config CRUD API endpoints remain operational
    - Ensure existing tenant_modules, tenant_credentials, rekeningschema.parameters remain unchanged
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - [x] 13.2 Write integration tests for backward compatibility
    - Test existing tenant_config CRUD still works
    - Test parameters table takes precedence when both have a value
    - Test tenant_modules, tenant_credentials unaffected
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 14. Final checkpoint - Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (13 properties total)
- Unit tests validate specific examples and edge cases
- Each hardcoded value replacement (task 8.x) is independently deployable per Requirement 10.2
- The deployment order follows Requirement 10.5: tables, seed, replace hardcoded, storage abstraction, admin APIs, deprecate tenant_config


Additionals to solve

Nothing changes with them. The design explicitly states this:

Table	What happens
tenant_config	Stays operational. Existing CRUD API endpoints keep working. The new parameters table takes precedence only when both have a value for the same key (task 13).
tenant_credentials	Untouched. ParameterService delegates secret encryption to CredentialService, which still reads/writes tenant_credentials. No schema or API changes.
tenant_modules	Untouched. ModuleRegistry's has_module() reads from tenant_modules exactly like the old has_fin_module() did.
tenant_template_config	Untouched. Templates are a separate concern — the TemplateService still works the same way.
rekeningschema.parameters	Untouched. Account-level config, completely separate from the new parameter system.
The new parameters and tax_rates tables are additive — they sit alongside the existing tables. Nothing gets migrated away or deleted. The only overlap is task 13 (backward compatibility), which says: if a key exists in both tenant_config AND parameters, the parameters table wins. But that's a read-time precedence rule, not a data migration.

Eventually you could migrate values from tenant_config into parameters and deprecate the old table, but that's a future decision — not part of this spec.