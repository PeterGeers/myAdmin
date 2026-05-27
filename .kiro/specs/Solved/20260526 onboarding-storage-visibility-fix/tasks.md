# Implementation Plan

## Overview

Fix six related bugs in the tenant provisioning flow: S3 storage not configured, STR module visible without subscription, missing `seed_module_params` calls during provisioning and module activation, Google Drive-specific branding labels shown to S3 tenants, and required params only existing as CODE_DEFAULTS. Uses the bug condition methodology with exploratory testing before fix, preservation testing, then implementation and validation.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Provisioning Fails to Seed Storage, Restricts Modules, and Seeds Parameters
  - **IMPORTANT**: Write this property-based test BEFORE implementing the fix
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bugs exist
  - **Scoped PBT Approach**: Scope the property to concrete failing cases:
    - Provision with no explicit modules → assert STR is NOT in tenant_modules (Bug 1.2)
    - Provision with s3_shared storage → assert `storage.s3_shared_bucket` has tenant-scope value (Bug 1.1)
    - Provision with FIN module → assert `fin.default_currency` has tenant-scope row (Bug 1.4)
    - Activate ZZP module → assert `zzp.invoice_prefix` has tenant-scope row (Bug 1.5)
    - Get schema for S3 tenant → assert `company_logo_file_id` is hidden or has visible_when condition (Bug 1.7)
  - **Bug Condition from design**: `isBugCondition(input)` returns true when:
    - `input.modules` NOT explicitly provided AND default includes 'STR'
    - `input.storage_provider == 's3_shared'` AND NOT `storage_bucket_seeded`
    - NOT `seed_module_params_called_for_each_module`
    - `branding_labels_reference_google_drive` AND `provider != 'google_drive'`
    - For module activation: NOT `seed_module_params_called_after_activation`
  - **Expected Behavior (assertions)**: For all inputs satisfying the bug condition:
    - Default modules == `['FIN', 'TENADMIN']` (no STR)
    - `storage.s3_shared_bucket` == env(`S3_SHARED_BUCKET`) at tenant scope
    - All required module params have tenant-scope rows
    - `activate_module` seeds params after activation
    - Branding fields have `visible_when` based on `invoice_provider`
  - Run test on UNFIXED code - expect FAILURE (this confirms the bugs exist)
  - Document counterexamples found (e.g., "provision without modules → STR in tenant_modules", "s3_shared_bucket has no tenant-scope row")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Explicit STR, Google Drive, Idempotent Re-provisioning, and Dependencies Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **Observe on UNFIXED code** (non-buggy inputs where isBugCondition returns false):
    - Provision with `modules=['FIN', 'STR', 'TENADMIN']` explicitly → observe STR is enabled
    - Provision with `google_drive` storage → observe Google Drive params visible, no S3 bucket seeded
    - Provision same tenant twice → observe second run skips without errors (idempotent)
    - Activate ZZP without FIN dependency → observe ValueError raised
    - Provision without TENADMIN in list → observe TENADMIN auto-added
    - Get schema for Google Drive tenant → observe `company_logo_file_id` visible with Google Drive label
  - **Write property-based tests capturing observed behavior**:
    - For all module lists that explicitly include STR: STR remains enabled after provisioning
    - For all tenants with `google_drive` provider: Google Drive params visible, S3 fields hidden
    - For all re-provisioning of existing tenants: no errors, no duplicates, same result
    - For all module activations with unmet dependencies: ValueError raised
    - For all module lists missing TENADMIN: TENADMIN auto-included
  - **Property-based testing generates many test cases for stronger guarantees**
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3. Fix for onboarding storage and visibility bugs
  - [x] 3.1 Change default modules in sysadmin_provisioning.py
    - In `backend/src/routes/sysadmin_provisioning.py`, function `provision_signup`
    - Change `modules = data.get('modules', ['FIN', 'STR', 'TENADMIN'])` to `modules = data.get('modules', ['FIN', 'TENADMIN'])`
    - This removes STR from the default module list so only explicitly subscribed tenants get STR
    - _Bug_Condition: isBugCondition(input) where input.modules NOT explicitly provided AND default includes 'STR'_
    - _Expected_Behavior: default_modules == ['FIN', 'TENADMIN'] only_
    - _Preservation: Tenants provisioned with STR explicitly continue to get STR (Req 3.1)_
    - _Requirements: 2.2, 2.3_

  - [x] 3.2 Add parameter seeding step in tenant_provisioning_service.py
    - In `backend/src/services/tenant_provisioning_service.py`, function `create_and_provision_tenant`
    - Import `ParameterService` from `services.parameter_service`
    - After module insertion (Step 2), add Step 2b:
      - Create `param_service = ParameterService(self.db)` instance
      - For each module in `modules`: call `param_service.seed_module_params(administration, module)`
      - Seed storage params: set `storage.invoice_provider` = 's3_shared' and `storage.s3_shared_bucket` = `os.getenv('S3_SHARED_BUCKET', 'myadmin-shared')` at tenant scope
    - Add `'params_seeded': <count>` to the return dict
    - _Bug_Condition: isBugCondition(input) where NOT seed_module_params_called AND storage_provider == 's3_shared' AND NOT storage_bucket_seeded_
    - _Expected_Behavior: All required module params have tenant-scope rows; storage.s3_shared_bucket == env(S3_SHARED_BUCKET)_
    - _Preservation: Idempotent re-provisioning skips existing records (Req 3.3); TENADMIN auto-inclusion preserved (Req 3.5)_
    - _Requirements: 2.1, 2.4, 2.6_

  - [x] 3.3 Add seed_module_params call in module_registry.py activate_module
    - In `backend/src/services/module_registry.py`, function `activate_module`
    - After the successful INSERT/UPDATE of the `tenant_modules` row:
      - Import `ParameterService` at function level to avoid circular imports
      - Instantiate `ParameterService(db)` and call `seed_module_params(tenant, module_name)`
      - Log the number of params seeded
    - _Bug_Condition: isBugCondition(input) where input.type == 'module_activation' AND NOT seed_module_params_called_after_activation_
    - _Expected_Behavior: activate_module seeds params for newly activated module_
    - _Preservation: Module dependency checks remain enforced (Req 3.6)_
    - _Requirements: 2.5_

  - [x] 3.4 Add visible_when to branding fields and add S3 logo field in parameter_schema.py
    - In `backend/src/services/parameter_schema.py`:
    - Update `company_logo_file_id` in both `str_branding` and `zzp_branding` sections:
      - Add `'visible_when': {'invoice_provider': 'google_drive'}`
      - Change label from "Company Logo (Google Drive File ID)" to "Company Logo"
      - Change description from "Google Drive file ID for company logo" to "File identifier for company logo"
    - Add new `company_logo_s3_key` parameter to both `str_branding` and `zzp_branding`:
      - `'visible_when': {'invoice_provider': ['s3_shared', 's3_tenant']}`
      - Label: "Company Logo (S3 Key)"
      - Type: string
      - Description: "S3 object key for company logo image"
    - _Bug_Condition: isBugCondition(input) where branding_labels_reference_google_drive AND provider != 'google_drive'_
    - _Expected_Behavior: Google Drive fields hidden for S3 tenants; S3 fields shown for S3 tenants_
    - _Preservation: Google Drive tenants continue to see Google Drive-specific parameters (Req 3.2, 3.7)_
    - _Requirements: 2.7_

  - [x] 3.5 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Provisioning Seeds Storage, Restricts Modules, and Seeds Parameters
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied:
      - Default modules == `['FIN', 'TENADMIN']` (no STR)
      - `storage.s3_shared_bucket` seeded at tenant scope
      - All required module params have tenant-scope rows
      - `activate_module` seeds params after activation
      - Branding fields have appropriate `visible_when` conditions
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bugs are fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** - Explicit STR, Google Drive, Idempotent Re-provisioning, and Dependencies Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all preservation tests still pass after fix:
      - Explicit STR provisioning still works
      - Google Drive tenants unchanged
      - Idempotent re-provisioning still skips
      - Dependency checks still enforced
      - TENADMIN auto-inclusion still works
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite to confirm no regressions
  - Verify bug condition exploration test passes (Property 1)
  - Verify preservation property tests pass (Property 2)
  - Run existing unit tests for affected modules (provisioning, parameter service, module registry)
  - Ensure all tests pass, ask the user if questions arise

## Task Dependency Graph

```json
{ "waves": [["1"], ["2"], ["3.1", "3.2", "3.3", "3.4"], ["3.5", "3.6"], ["4"]] }
```

## Notes

- This fix uses the **bug condition methodology**: write tests first on unfixed code to confirm bugs exist, then implement the fix, then verify tests pass.
- Property-based testing (pytest + Hypothesis) is used for both exploration and preservation to generate many input combinations automatically.
- The exploration test (Property 1) is expected to FAIL on unfixed code — this is correct behavior that confirms the bugs exist.
- The preservation test (Property 2) is expected to PASS on unfixed code — this captures baseline behavior that must not regress.
- After the fix, Property 1 should PASS (bugs fixed) and Property 2 should still PASS (no regressions).
- Files affected: `sysadmin_provisioning.py`, `tenant_provisioning_service.py`, `module_registry.py`, `parameter_schema.py`
- Test files: `backend/tests/unit/test_provisioning_bug_condition.py`, `backend/tests/unit/test_provisioning_preservation.py`
