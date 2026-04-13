# Requirements Document

## Introduction

The myAdmin system currently has configuration values hardcoded throughout the codebase: tenant names, file paths, Google Drive folder IDs, vendor folder mappings, tax rates with date-based branching, and tourist tax calculations. This feature introduces a parameter-driven configuration architecture with three distinct parameter shapes — flat key-value parameters with scope inheritance, time-versioned tax rates, and calculated rates with municipality-specific methods — backed by dedicated database tables and resolution services. The goal is to eliminate hardcoded values, enable per-tenant configuration without code changes, and support future rate changes and new tenants through data-only updates.

## Glossary

- **Parameter_Service**: Python service that resolves flat key-value parameters by walking the scope inheritance chain (user → role → tenant → system) and returning the first match, with in-process caching and write-through invalidation.
- **Tax_Rate_Service**: Python service that looks up time-versioned tax rates from the `tax_rates` table, filtering by effective date range and falling back from tenant-specific rates to system defaults.
- **Tourist_Tax_Calculator**: Python service that dispatches tourist tax computation to the correct formula based on the `calc_method` field (percentage, fixed_per_guest_night, fixed_per_night, percentage_of_room_price) stored in the `tax_rates` table.
- **Module_Registry**: In-code Python dictionary that defines, for each module (FIN, STR, TENADMIN), the required parameters with defaults, required tax rate types, and required roles. It is a developer artifact — not stored in the database.
- **Storage_Provider**: Abstract base class (Strategy pattern) defining the interface for invoice storage operations (upload, download, delete, list_files), with concrete implementations for Google Drive, S3 shared, and S3 tenant storage.
- **Parameters_Table**: New MySQL table storing flat key-value parameters with columns for scope (system/tenant/role/user), scope_id, namespace, key, value (JSON), value_type, and is_secret flag.
- **Tax_Rates_Table**: New MySQL table storing time-versioned tax rates with columns for administration, tax_type, tax_code, rate, ledger_account, effective_from, effective_to, country_code, calc_method, and calc_params (JSON).
- **Scope_Inheritance**: Resolution strategy where parameter lookup walks from most specific scope (user) to least specific (system), returning the first match found.
- **Effective_Date_Range**: The period defined by `effective_from` and `effective_to` columns in the Tax_Rates_Table during which a specific tax rate applies.
- **Calc_Method**: Field in the Tax_Rates_Table that specifies the tourist tax calculation formula to use: `percentage`, `fixed_per_guest_night`, `fixed_per_night`, or `percentage_of_room_price`.

## Requirements

### Requirement 1: Flat Parameter Storage and Resolution

**User Story:** As a system administrator, I want a unified parameter store with scope-based inheritance, so that configuration values can be managed at system, tenant, role, or user level without code changes.

#### Acceptance Criteria

1. THE Parameters_Table SHALL store parameters with the columns: scope (system/tenant/role/user), scope_id, namespace, key, value (JSON), value_type (string/number/boolean/json), and is_secret (boolean).
2. WHEN a parameter is requested, THE Parameter_Service SHALL resolve the value by checking scopes in order: user, role, tenant, system, and return the value from the first scope that has a match.
3. WHEN no value exists at any scope level for a requested parameter, THE Parameter_Service SHALL return None.
4. WHEN a parameter with is_secret set to true is stored, THE Parameter_Service SHALL encrypt the value using the existing CredentialService encryption mechanism before writing to the database.
5. WHEN a parameter with is_secret set to true is read, THE Parameter_Service SHALL decrypt the value before returning it to the caller.
6. THE Parameter_Service SHALL cache resolved parameter values in an in-process dictionary keyed by (scope, scope_id, namespace, key).
7. WHEN a parameter value is written or updated, THE Parameter_Service SHALL invalidate the corresponding cache entries immediately (write-through invalidation).
8. WHEN a parameter is requested with only a tenant scope (no role or user provided), THE Parameter_Service SHALL check tenant first, then fall back to system defaults.

### Requirement 2: Time-Versioned Tax Rate Storage and Lookup

**User Story:** As a financial administrator, I want tax rates stored with effective date ranges and tenant-specific overrides, so that the system automatically applies the correct rate for any transaction date without hardcoded date branching in code.

#### Acceptance Criteria

1. THE Tax_Rates_Table SHALL store tax rates with the columns: administration, tax_type, tax_code, rate (DECIMAL 6,3), ledger_account, effective_from (DATE), effective_to (DATE defaulting to 9999-12-31), country_code (defaulting to NL), description, calc_method (defaulting to percentage), and calc_params (JSON).
2. THE Tax_Rates_Table SHALL enforce a unique constraint on (administration, tax_type, tax_code, effective_from) to prevent duplicate rate entries for the same period.
3. WHEN a tax rate is requested for a specific date, THE Tax_Rate_Service SHALL return the rate where effective_from is less than or equal to the reference date and effective_to is greater than or equal to the reference date.
4. WHEN a tenant-specific tax rate exists for the requested tax_type, tax_code, and date range, THE Tax_Rate_Service SHALL return the tenant-specific rate.
5. WHEN no tenant-specific tax rate exists, THE Tax*Rate_Service SHALL fall back to the system default rate (administration = '\_system*').
6. WHEN no rate exists at either tenant or system level for the requested parameters, THE Tax_Rate_Service SHALL return None.
7. WHEN all active VAT codes are requested for a tenant and date, THE Tax_Rate_Service SHALL return a list of all matching tax_code entries with their rates and ledger accounts.
8. THE Tax_Rates_Table SHALL be seeded with NL system default BTW rates: zero (0%, account 2010), low (9%, account 2021), and high (21%, account 2020), with effective_from set to 2000-01-01.
9. THE Tax_Rates_Table SHALL NOT be seeded with BTW accommodation rates. STR accommodation VAT rate changes (e.g. from BTW low to BTW high on a specific date) SHALL be configured per tenant through the Tax Rate Administration API, since the applicable rate and change date depend on the tenant's STR operations.

### Requirement 3: Tourist Tax Calculation with Municipality-Specific Methods

**User Story:** As an STR operator, I want tourist tax calculated using the correct municipality-specific method (percentage, fixed per guest per night, fixed per night, or percentage of room price), so that tax amounts are accurate regardless of which municipality the property is located in.

#### Acceptance Criteria

1. WHEN a tourist tax calculation is requested with calc_method set to percentage, THE Tourist_Tax_Calculator SHALL compute the tax as: (base_amount_excl_vat / (100 + rate)) \* rate.
2. WHEN a tourist tax calculation is requested with calc*method set to fixed_per_guest_night, THE Tourist_Tax_Calculator SHALL compute the tax as: rate * number*of_guests * number_of_nights.
3. WHEN a tourist tax calculation is requested with calc_method set to fixed_per_night, THE Tourist_Tax_Calculator SHALL compute the tax as: rate \* number_of_nights.
4. WHEN a tourist tax calculation is requested with calc_method set to percentage_of_room_price, THE Tourist_Tax_Calculator SHALL compute the tax as: room_price \* (rate / 100).
5. WHEN an unknown calc_method is encountered, THE Tourist_Tax_Calculator SHALL return a tax amount of zero and log a warning.
6. THE Tourist_Tax_Calculator SHALL return a result containing: amount (rounded to 2 decimal places), method, rate, and description.
7. WHEN no tourist tax rate is configured for the tenant and reference date, THE Tourist_Tax_Calculator SHALL return a tax amount of zero with method set to none.
8. THE Tourist_Tax_Calculator SHALL read the calc_method and calc_params from the Tax_Rates_Table for the tenant's tourist_tax entry matching the reference date.

### Requirement 4: Module Registry and Parameter Seeding

**User Story:** As a developer, I want a code-based module registry that defines required parameters and defaults per module, so that enabling a module for a tenant automatically seeds the correct configuration without manual setup.

#### Acceptance Criteria

1. THE Module_Registry SHALL define for each module (FIN, STR, TENADMIN): a description, a dictionary of required parameters with their types and default values, a list of required roles, and optionally a list of required tax rate types.
2. WHEN a module is enabled for a tenant, THE Parameter_Service SHALL seed the module's required parameters with system default values from the Module_Registry for any parameters that do not already have a tenant-level value.
3. WHEN a module is disabled for a tenant, THE Parameter_Service SHALL preserve the tenant's parameter values (parameters are not deleted on module deactivation).
4. THE Module_Registry SHALL provide a unified module_required decorator that checks whether the current tenant has the specified module enabled and returns HTTP 403 with an error message if the module is not active.
5. THE Module_Registry SHALL replace the existing duplicated has_fin_module function with a generic has_module(tenant, module_name) function.
6. WHEN a new module is added to the Module_Registry, THE system SHALL require no changes to validation logic, provisioning logic, or role mapping logic beyond the registry entry itself and the module's own routes and services.

### Requirement 5: Eliminate Hardcoded Values

**User Story:** As a system administrator, I want all hardcoded tenant names, file paths, folder IDs, and vendor mappings replaced with parameter lookups, so that the system works correctly for any tenant without code modifications.

#### Acceptance Criteria

1. WHEN a default administration name is needed, THE system SHALL resolve it via Parameter_Service with namespace general and key default_administration, instead of using the hardcoded string GoodwinSolutions.
2. WHEN a download folder path is needed, THE system SHALL resolve it via Parameter_Service with namespace storage and key download_folder, instead of using the hardcoded path C:\Users\peter\Downloads.
3. WHEN a report output path is needed, THE system SHALL resolve it via Parameter_Service with namespace storage and key report_output_path, instead of using the hardcoded path C:\Users\peter\OneDrive\Admin\reports.
4. WHEN a Google Drive folder ID is needed, THE system SHALL resolve it via Parameter_Service with namespace storage and key google_drive_folder_id at the tenant scope, instead of using a hardcoded fallback folder ID in code.
5. WHEN a vendor-to-folder mapping is needed, THE system SHALL resolve it via Parameter_Service with namespace storage and key vendor_folder_mappings as a JSON object, instead of using the hardcoded dictionary in config.py.
6. WHEN VAT rates are needed for STR processing, THE system SHALL call Tax_Rate_Service with the appropriate tax_type and reference date, instead of using hardcoded date-branching logic in str_processor.py.
7. WHEN VAT account numbers are needed for BTW processing, THE system SHALL call Tax_Rate_Service to retrieve ledger_account values, instead of using hardcoded account numbers 2010, 2020, and 2021.
8. WHEN tourist tax is calculated, THE system SHALL call Tourist_Tax_Calculator with the tenant, reference date, and booking details, instead of using inline percentage formulas in str_processor.py and toeristenbelasting_generator.py.

### Requirement 6: Storage Provider Abstraction

**User Story:** As a system administrator, I want invoice storage abstracted behind a provider interface, so that tenants can use Google Drive, shared S3, or tenant-specific S3 storage without changing application code.

#### Acceptance Criteria

1. THE Storage_Provider SHALL define an abstract interface with methods: upload(file_data, path, metadata) returning a reference string, download(reference) returning bytes, delete(reference) returning a boolean, and list_files(path) returning a list of file metadata dictionaries.
2. WHEN a storage operation is requested, THE system SHALL resolve the tenant's configured storage provider from Parameter_Service with namespace storage and key invoice_provider.
3. WHEN invoice_provider is set to google_drive, THE system SHALL use the GoogleDriveStorage implementation that wraps the existing GoogleDriveService.
4. WHEN invoice*provider is set to s3_shared, THE system SHALL use the S3SharedStorage implementation that stores files in a shared bucket with tenant-prefixed keys following the pattern {tenant}/{referenceNumber}/{uuid}*{filename}, where the path is human-readable without the database (tenant for isolation, referenceNumber for context, uuid for uniqueness, original filename preserved).
5. WHEN invoice_provider is set to s3_tenant, THE system SHALL use the S3TenantStorage implementation that stores files in the tenant's own S3 bucket using cross-account credentials stored in tenant_credentials.
6. IF a configured storage provider is unavailable or misconfigured, THEN THE system SHALL return a descriptive error message indicating the provider type and the nature of the configuration problem.

### Requirement 7: Parameter Administration API

**User Story:** As a tenant administrator, I want API endpoints to view and manage parameters for my tenant, so that I can configure the system through the admin UI without developer intervention.

#### Acceptance Criteria

1. WHEN a GET request is made to the parameters endpoint, THE system SHALL return all parameters visible to the requesting tenant, grouped by namespace, with an indicator showing which scope level each value originates from (system default, tenant override, role override, or user preference).
2. WHEN a POST request is made to create a parameter, THE system SHALL validate the value against the declared value_type and reject the request with a descriptive error if validation fails.
3. WHEN a PUT request is made to update a parameter, THE system SHALL update the value at the specified scope level and invalidate the cache for that parameter.
4. WHEN a DELETE request is made to remove a parameter override, THE system SHALL delete only the override at the specified scope level, causing resolution to fall back to the next scope in the inheritance chain.
5. THE parameter administration endpoints SHALL require the Tenant_Admin role for tenant-scope operations and the SysAdmin role for system-scope operations.
6. WHEN a parameter has is_secret set to true, THE system SHALL mask the value in GET responses (returning a placeholder instead of the actual value) unless the requesting user has the SysAdmin role.

### Requirement 8: Tax Rate Administration API

**User Story:** As a tenant administrator, I want API endpoints to view and manage tax rates with effective dates, so that I can configure rate changes in advance without code deployments.

#### Acceptance Criteria

1. WHEN a GET request is made to the tax rates endpoint, THE system SHALL return all tax rates for the tenant, including system defaults that apply where no tenant override exists, sorted by tax_type, tax_code, and effective_from.
2. WHEN a POST request is made to create a new tax rate, THE system SHALL validate that the effective_from date does not conflict with an existing rate for the same administration, tax_type, and tax_code.
3. WHEN a new tax rate is created with an effective_from date that falls within an existing rate's date range, THE system SHALL automatically close the existing rate by setting its effective_to to the day before the new rate's effective_from.
4. WHEN a DELETE request is made to remove a tenant-specific tax rate override, THE system SHALL delete the override, causing the system default to apply for that period.
5. THE tax rate administration endpoints SHALL require the Tenant_Admin role for tenant-specific rates and the SysAdmin role for system default rates.

### Requirement 9: Backward Compatibility

**User Story:** As a developer, I want the new parameter system to coexist with existing configuration mechanisms, so that the migration can happen incrementally without breaking existing functionality.

#### Acceptance Criteria

1. THE system SHALL keep the existing tenant_config table operational and accessible through its current CRUD API endpoints during the migration period.
2. THE system SHALL keep the existing rekeningschema.parameters JSON column for account-level parameters, as it serves a different purpose (account-level configuration) from the new Parameters_Table (system/tenant/role/user configuration).
3. THE system SHALL keep the existing tenant_credentials table and CredentialService for credential storage, with the Parameter_Service delegating secret encryption to CredentialService.
4. THE system SHALL keep the existing tenant_modules table for module on/off state, with the Module_Registry providing the metadata layer on top of it.
5. WHEN a parameter exists in both tenant_config and the new Parameters_Table, THE Parameter_Service SHALL use the value from the Parameters_Table (new system takes precedence).

### Requirement 10: Incremental Deployment

**User Story:** As a developer, I want to deploy the parameter-driven configuration incrementally on the main branch, so that each change is small, testable, and independently deployable without a feature branch or big-bang merge.

#### Acceptance Criteria

1. ALL new tables (parameters, tax_rates) and services (ParameterService, TaxRateService, TouristTaxCalculator, ModuleRegistry) SHALL be additive — they do not modify or remove existing tables, services, or API endpoints.
2. EACH hardcoded value replacement SHALL be an independent, deployable change that can be merged and released without depending on other replacements being complete.
3. THE system SHALL function correctly in a partially migrated state where some configuration values come from the new Parameters_Table and others still use their original hardcoded values or tenant_config lookups.
4. THE storage abstraction (StorageProvider interface) SHALL wrap the existing GoogleDriveService without changing its behavior, so that existing tenants using Google Drive are unaffected when the abstraction is introduced.
5. THE recommended deployment order SHALL be: (1) create tables and services, (2) seed system defaults, (3) replace hardcoded values one by one, (4) add storage abstraction, (5) add admin API endpoints, (6) deprecate tenant_config once all entries are migrated.
