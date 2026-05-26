# Onboarding Storage & Visibility Bugfix Design

## Overview

Seven related bugs in the tenant provisioning flow cause newly onboarded tenants to have non-functional storage, incorrect module visibility, missing parameter seeds, and confusing Google Drive-specific labels. The root cause is that the provisioning pipeline (`sysadmin_provisioning.py` → `TenantProvisioningService`) was built as a minimal "insert records" flow without calling `seed_module_params` or seeding storage configuration, and the default module list includes STR unconditionally. Additionally, the `activate_module()` function and the branding parameter schema lack awareness of the tenant's actual storage provider.

The fix is minimal and targeted: adjust defaults, add seed calls at provisioning and module activation time, and extend the `visible_when` mechanism to branding parameters.

## Glossary

- **Bug_Condition (C)**: The set of conditions under which provisioning produces an incomplete or incorrect tenant configuration
- **Property (P)**: The desired behavior — a fully functional tenant with correct modules, seeded parameters, and provider-appropriate labels
- **Preservation**: Existing behavior for tenants provisioned with explicit STR, Google Drive tenants, idempotent re-provisioning, and dependency checks must remain unchanged
- **`TenantProvisioningService`**: The service in `backend/src/services/tenant_provisioning_service.py` that orchestrates tenant creation
- **`seed_module_params`**: Method on `ParameterService` that seeds required parameters from `MODULE_REGISTRY` defaults
- **`activate_module`**: Function in `module_registry.py` that activates a module but currently does not seed parameters
- **`PARAMETER_SCHEMA`**: The schema in `parameter_schema.py` defining UI metadata, `visible_when` rules, and module filters
- **`visible_when`**: A conditional visibility mechanism that shows/hides parameters based on another parameter's value

## Bug Details

### Bug Condition

The bugs manifest when a new tenant is provisioned (or a module is activated post-provisioning) and the system fails to: (a) restrict modules to the actual subscription, (b) seed required parameters, (c) seed storage configuration, or (d) adapt branding labels to the storage provider.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type ProvisioningRequest OR ModuleActivationRequest
  OUTPUT: boolean

  IF input.type == 'provisioning' THEN
    RETURN (input.modules NOT explicitly provided AND default includes 'STR')
           OR (input.storage_provider == 's3_shared' AND NOT storage_bucket_seeded)
           OR (NOT seed_module_params_called_for_each_module)
           OR (branding_labels_reference_google_drive AND provider != 'google_drive')
  END IF

  IF input.type == 'module_activation' THEN
    RETURN NOT seed_module_params_called_after_activation
  END IF

  RETURN FALSE
END FUNCTION
```

### Examples

- **Bug 1.1**: Tenant "KimGeers" provisioned with `s3_shared` → `storage.s3_shared_bucket` is empty → invoice upload fails with "S3 shared bucket not configured"
- **Bug 1.2**: Tenant "KimGeers" provisioned without explicit modules → system enables `['FIN', 'STR', 'TENADMIN']` → STR navigation visible despite no STR subscription
- **Bug 1.3**: Tenant without STR sees STR parameters in settings because `tenant_modules` has an active STR row
- **Bug 1.4**: After provisioning, `fin.default_currency`, `fin.fiscal_year_start_month`, `fin.locale` have no tenant-scope rows → shown as "system default" (read-only)
- **Bug 1.5**: Tenant activates ZZP via Tenant Admin UI → `zzp.invoice_prefix` etc. not seeded → module settings page is empty
- **Bug 1.6**: Required params like `storage.s3_shared_bucket` only exist as CODE_DEFAULTS → user must click "Customize" before editing
- **Bug 1.7**: Tenant with `s3_shared` sees `company_logo_file_id` labeled "Google Drive File ID" in STR/ZZP branding sections

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Tenants provisioned with STR explicitly in the modules list continue to get STR enabled (Req 3.1)
- Tenants with Google Drive as storage provider continue to see Google Drive parameters and labels (Req 3.2, 3.7)
- Idempotent re-provisioning continues to skip existing records without errors (Req 3.3)
- Module show/hide via `get_schema_for_tenant` continues to work for existing tenants (Req 3.4)
- TENADMIN auto-inclusion safety guard remains (Req 3.5)
- Module dependency checks in `activate_module` remain enforced (Req 3.6)

**Scope:**
All inputs that do NOT involve the provisioning flow's default module list, parameter seeding, or branding label rendering should be completely unaffected by this fix. This includes:

- Direct database queries for existing tenants
- Authentication and authorization flows
- Chart of accounts loading
- Cognito user management
- Email sending

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Hardcoded Default Module List (Bug 1.2, 1.3)**: `sysadmin_provisioning.py` line `modules = data.get('modules', ['FIN', 'STR', 'TENADMIN'])` unconditionally includes STR. The signup record's `property_range` field (which indicates STR interest) is not consulted.

2. **Missing `seed_module_params` Call in Provisioning (Bug 1.4, 1.6)**: `TenantProvisioningService.create_and_provision_tenant` never calls `ParameterService.seed_module_params()` after inserting modules. Required params remain as CODE_DEFAULTS only (no tenant-scope DB rows).

3. **Missing Storage Parameter Seeding (Bug 1.1, 1.6)**: The provisioning flow does not seed `storage.invoice_provider` or `storage.s3_shared_bucket` at tenant scope. The `S3_SHARED_BUCKET` env var value is never written to the parameters table.

4. **Missing `seed_module_params` in `activate_module` (Bug 1.5)**: The `activate_module()` function in `module_registry.py` only inserts the `tenant_modules` row but does not seed the module's required parameters.

5. **Google Drive-Specific Branding Labels (Bug 1.7)**: `PARAMETER_SCHEMA` defines `company_logo_file_id` with label "Google Drive File ID" and description referencing Google Drive, without a `visible_when` condition. S3 tenants see irrelevant Google Drive terminology.

## Correctness Properties

Property 1: Bug Condition - Storage Parameters Seeded at Provisioning

_For any_ provisioning request where the storage provider is `s3_shared`, the fixed provisioning flow SHALL seed `storage.invoice_provider` = 's3_shared' and `storage.s3_shared_bucket` = env(`S3_SHARED_BUCKET`) as tenant-scope parameter rows, making storage immediately functional.

**Validates: Requirements 2.1, 2.6**

Property 2: Bug Condition - Default Modules Exclude STR

_For any_ provisioning request where modules are not explicitly specified, the fixed provisioning flow SHALL default to `['FIN', 'TENADMIN']` only, excluding STR unless explicitly requested.

**Validates: Requirements 2.2, 2.3**

Property 3: Bug Condition - Module Parameters Seeded at Provisioning

_For any_ provisioning request, the fixed provisioning flow SHALL call `seed_module_params` for each enabled module, creating tenant-scope parameter rows for all required params that have defaults.

**Validates: Requirements 2.4, 2.6**

Property 4: Bug Condition - Module Parameters Seeded at Activation

_For any_ module activation via `activate_module`, the fixed function SHALL call `seed_module_params` for the newly activated module, creating tenant-scope parameter rows for all required params that have defaults.

**Validates: Requirements 2.5**

Property 5: Bug Condition - Branding Labels Adapt to Storage Provider

_For any_ tenant with `s3_shared` or `s3_tenant` as their storage provider, the fixed parameter schema SHALL hide or relabel Google Drive-specific branding fields (e.g., `company_logo_file_id`) and show S3-appropriate alternatives.

**Validates: Requirements 2.7**

Property 6: Preservation - Explicit STR and Google Drive Tenants Unchanged

_For any_ provisioning request where STR is explicitly included in the modules list, or where the storage provider is `google_drive`, the fixed code SHALL produce the same result as the original code, preserving STR enablement and Google Drive parameter visibility.

**Validates: Requirements 3.1, 3.2, 3.7**

Property 7: Preservation - Idempotent Re-provisioning and Dependencies

_For any_ re-provisioning of an existing tenant or module activation with unmet dependencies, the fixed code SHALL produce the same result as the original code, preserving idempotent skip behavior and dependency enforcement.

**Validates: Requirements 3.3, 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `backend/src/routes/sysadmin_provisioning.py`

**Function**: `provision_signup`

**Specific Changes**:

1. **Change default modules**: Replace `['FIN', 'STR', 'TENADMIN']` with `['FIN', 'TENADMIN']`
   - Line: `modules = data.get('modules', ['FIN', 'STR', 'TENADMIN'])`
   - New: `modules = data.get('modules', ['FIN', 'TENADMIN'])`

---

**File**: `backend/src/services/tenant_provisioning_service.py`

**Function**: `create_and_provision_tenant`

**Specific Changes**: 2. **Add parameter seeding step after module insertion**: After Step 2 (insert modules), add a new Step 2b that calls `seed_module_params` for each module and seeds storage parameters.

- Import `ParameterService`
- Create `ParameterService(self.db)` instance
- For each module in `modules`: call `param_service.seed_module_params(administration, module)`
- Seed storage params: set `storage.invoice_provider` = 's3_shared' and `storage.s3_shared_bucket` = `os.getenv('S3_SHARED_BUCKET', 'myadmin-shared')` at tenant scope
- Add results to the return dict: `'params_seeded': <count>`

---

**File**: `backend/src/services/module_registry.py`

**Function**: `activate_module`

**Specific Changes**: 3. **Call `seed_module_params` after activation**: After the successful INSERT/UPDATE of the `tenant_modules` row, instantiate `ParameterService` and call `seed_module_params(tenant, module_name)`.

- Import at function level to avoid circular imports
- Add after the `db.execute_query` call
- Log the number of params seeded

---

**File**: `backend/src/services/parameter_schema.py`

**Specific Changes**: 4. **Add `visible_when` to branding logo fields**: Update `company_logo_file_id` in both `str_branding` and `zzp_branding` sections:

- Add `'visible_when': {'invoice_provider': 'google_drive'}` to the existing `company_logo_file_id` param definition
- Change label from "Company Logo (Google Drive File ID)" to "Company Logo"
- Change description from "Google Drive file ID for company logo" to "File identifier for company logo"

5. **Add S3 logo upload field**: Add a new `company_logo_s3_key` parameter to both `str_branding` and `zzp_branding`:
   - `'visible_when': {'invoice_provider': ['s3_shared', 's3_tenant']}`
   - Label: "Company Logo (S3 Key)"
   - Type: string
   - Description: "S3 object key for company logo image"

---

**File**: `backend/src/services/parameter_schema.py`

**Function**: `get_schema_for_tenant`

**Specific Changes**: 6. **Extend `visible_when` resolution**: The `visible_when` mechanism is already handled by the frontend. The schema changes above (adding `visible_when` to branding fields) are sufficient — the frontend already evaluates `visible_when` conditions against current parameter values. No backend logic change needed for visibility filtering.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bugs on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bugs BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that call `provision_signup` and `activate_module` with various inputs and assert the expected parameter state. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:

1. **Default Module Test**: Provision without explicit modules → assert STR is NOT in `tenant_modules` (will fail on unfixed code — STR is included)
2. **Storage Seed Test**: Provision with default storage → assert `storage.s3_shared_bucket` has tenant-scope value (will fail on unfixed code — no row exists)
3. **Module Param Seed Test**: Provision with FIN → assert `fin.default_currency` has tenant-scope row (will fail on unfixed code — only CODE_DEFAULT)
4. **Activate Module Seed Test**: Activate ZZP → assert `zzp.invoice_prefix` has tenant-scope row (will fail on unfixed code — not seeded)
5. **Branding Label Test**: Get schema for S3 tenant → assert `company_logo_file_id` is hidden or relabeled (will fail on unfixed code — shows Google Drive label)

**Expected Counterexamples**:

- `tenant_modules` contains STR for tenants that didn't request it
- `parameters` table has no tenant-scope rows for `storage.s3_shared_bucket`
- `parameters` table has no tenant-scope rows for module required params
- Branding schema shows Google Drive labels regardless of storage provider

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed functions produce the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := provision_tenant_fixed(input)
  ASSERT storage_params_seeded(result.tenant)
  ASSERT module_params_seeded(result.tenant, result.modules)
  ASSERT default_modules_correct(result.modules)
  ASSERT branding_labels_appropriate(result.tenant, result.storage_provider)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed functions produce the same result as the original functions.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT provision_tenant_original(input).tenant == provision_tenant_fixed(input).tenant
  ASSERT provision_tenant_original(input).modules == provision_tenant_fixed(input).modules
  ASSERT provision_tenant_original(input).chart == provision_tenant_fixed(input).chart
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many combinations of module lists, storage providers, and tenant configurations
- It catches edge cases like empty module lists, duplicate modules, or unusual provider values
- It provides strong guarantees that non-buggy paths remain unchanged

**Test Plan**: Observe behavior on UNFIXED code first for explicit-STR provisioning, Google Drive tenants, and idempotent re-runs, then write property-based tests capturing that behavior.

**Test Cases**:

1. **Explicit STR Preservation**: Provision with `modules=['FIN', 'STR', 'TENADMIN']` → verify STR is still enabled after fix
2. **Google Drive Preservation**: Provision with Google Drive storage → verify Google Drive params visible, S3 params hidden
3. **Idempotent Preservation**: Provision same tenant twice → verify second run skips without errors
4. **Dependency Preservation**: Activate ZZP without FIN → verify ValueError still raised
5. **TENADMIN Auto-Include**: Provision without TENADMIN in list → verify it's still auto-added

### Unit Tests

- Test `provision_signup` with no modules specified → assert default is `['FIN', 'TENADMIN']`
- Test `create_and_provision_tenant` → assert `seed_module_params` called for each module
- Test `create_and_provision_tenant` → assert storage params seeded at tenant scope
- Test `activate_module` → assert `seed_module_params` called after activation
- Test `get_schema_for_tenant` with S3 provider → assert Google Drive logo field hidden
- Test `seed_module_params` idempotency → assert existing params not overwritten

### Property-Based Tests

- Generate random module lists (subsets of `['FIN', 'STR', 'ZZP', 'TENADMIN']`) and verify:
  - All required params for included modules are seeded
  - No params for excluded modules are seeded
  - TENADMIN is always present
- Generate random storage provider values and verify:
  - `s3_shared` → bucket param seeded
  - `google_drive` → no bucket param seeded
  - Branding labels match provider
- Generate random tenant names and verify idempotent behavior on re-provisioning

### Integration Tests

- Full provisioning flow: signup → provision → verify tenant can upload invoice to S3
- Full provisioning flow: signup → provision → verify STR nav hidden when not subscribed
- Module activation flow: activate ZZP → verify settings page shows seeded params
- Parameter editing flow: verify seeded params are immediately editable (no "Customize" step needed)
