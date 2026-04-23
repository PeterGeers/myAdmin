# Implementation Plan

## Bug: All 3 tenant provisioning entry points create tenant infrastructure but never create an initial admin user

---

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** — No Initial Admin User Created During Provisioning
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists in all 3 entry points
  - **Scoped PBT Approach**: Scope the property to concrete failing cases — call `create_and_provision_tenant()` with a valid `initial_admin_email` and assert that `results['initial_admin']` exists and `user_tenant_roles` has a `Tenant_Admin` row
  - Create test file `backend/tests/unit/test_initial_admin_bug_condition.py`
  - Use `hypothesis` with `@given(st.emails(), st.from_regex(r'[A-Z][a-zA-Z0-9]{2,20}', fullmatch=True))` to generate email and administration name combinations
  - Test 1: Call `TenantProvisioningService.create_and_provision_tenant()` with `initial_admin_email` parameter — assert `results` dict contains `initial_admin` key with status `created` or `existing_user` (will FAIL because method doesn't accept this parameter yet)
  - Test 2: After provisioning, assert `user_tenant_roles` has a row with `(email, administration, 'Tenant_Admin')` (will FAIL because no row is ever inserted)
  - Test 3: After provisioning, assert `user_invitations` has a record for the admin email (will FAIL because no invitation is created)
  - Mock `DatabaseManager`, `CognitoService`, `InvitationService`, `SESEmailService`, `EmailTemplateService` to isolate the service logic
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct — it proves the bug exists: `create_and_provision_tenant()` has no `initial_admin_email` parameter and no user creation step)
  - Document counterexamples found (e.g., "create_and_provision_tenant() returns results with no 'initial_admin' key, user_tenant_roles has 0 rows for the tenant")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** — Existing Provisioning Infrastructure Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Create test file `backend/tests/unit/test_initial_admin_preservation.py`
  - Observe on UNFIXED code: `create_and_provision_tenant('TestCorp', 'Test Corp', 'test@example.com', ['FIN', 'STR'], 'admin@sys.com', 'nl')` returns `{'tenant': 'created', 'modules': [...], 'chart': 'created', 'chart_rows': N, 'warnings': []}`
  - Observe on UNFIXED code: calling with same administration twice returns `{'tenant': 'skipped', 'modules': [skipped...], 'chart': 'skipped', ...}` (idempotent)
  - Observe on UNFIXED code: `create_and_provision_tenant()` without `initial_admin_email` (current signature) succeeds and returns results with keys `tenant`, `modules`, `chart`, `chart_rows`, `warnings`
  - Write property-based test with `hypothesis`: for all valid `(administration, display_name, contact_email, modules, locale)` tuples, `create_and_provision_tenant()` returns a dict with keys `tenant`, `modules`, `chart`, `chart_rows`, `warnings`
  - Write property-based test: for all valid inputs, `results['tenant']` is either `'created'` or `'skipped'`
  - Write property-based test: for all valid inputs, `results['modules']` is a list where each entry has `name` and `status` keys, and `TENADMIN` is always present
  - Write property-based test: for all valid inputs, `results['chart']` is one of `'created'`, `'skipped'`, `'failed'`
  - Write property-based test: idempotent rerun — calling twice with same administration produces `'skipped'` for tenant and modules on second call
  - Mock `DatabaseManager` to simulate both fresh and existing tenant scenarios
  - Verify all tests PASS on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.7, 3.8_

- [ ] 3. Implement the fix — Add `create_initial_admin_user()` to `TenantProvisioningService`
  - [x] 3.1 Add `create_initial_admin_user()` method to `TenantProvisioningService`
    - Add new method to `backend/src/services/tenant_provisioning_service.py`
    - Method signature: `create_initial_admin_user(self, administration, email, created_by, locale='nl')` returning `dict`
    - Check if `user_tenant_roles` row already exists for `(email, administration, 'Tenant_Admin')` — if yes, return `{'status': 'skipped'}`
    - Check if Cognito user exists via `CognitoService.get_user(email)`
    - For NEW users: create Cognito user via `CognitoService.create_user()`, call `admin_set_user_password(Password=temp_password, Permanent=True)` to set status to `CONFIRMED`, create invitation via `InvitationService.create_invitation()`, insert `user_tenant_roles` with `Tenant_Admin`, send invitation email via `SESEmailService`
    - For EXISTING users: update Cognito `custom:tenants` via `CognitoService.add_tenant_to_user()`, insert `user_tenant_roles` with `Tenant_Admin`, send tenant-added notification via `SESEmailService`
    - Wrap in try/except — failures are warnings, not hard errors (matches chart of accounts pattern)
    - Return result dict: `{'status': 'created'|'existing_user'|'skipped'|'failed', 'warning': optional_str}`
    - _Bug_Condition: isBugCondition(input) where input has initial_admin_email and no user_tenant_roles row exists_
    - _Expected_Behavior: After method completes, user_tenant_roles has Tenant_Admin row, user_invitations has record, email was sent_
    - _Preservation: Method only runs when initial_admin_email is provided; existing 3 steps unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.2 Add optional `initial_admin_email` parameter to `create_and_provision_tenant()`
    - Add `initial_admin_email: Optional[str] = None` parameter to method signature
    - After Step 3 (chart of accounts), add Step 4: if `initial_admin_email` is provided and not empty, call `self.create_initial_admin_user(administration, initial_admin_email, created_by, locale)`
    - Add result to `results` dict under key `initial_admin`
    - If `initial_admin_email` is None or empty, skip Step 4 entirely (no `initial_admin` key in results)
    - Update logger.info to include initial_admin status
    - _Bug_Condition: create_and_provision_tenant() currently has no initial_admin_email parameter_
    - _Expected_Behavior: When initial_admin_email is provided, results dict includes initial_admin key_
    - _Preservation: When initial_admin_email is None, behavior is identical to original_
    - _Requirements: 2.1, 2.2, 2.3, 3.8_

  - [x] 3.3 Update `sysadmin_tenants.py` — extract `initial_admin_email` and pass to service
    - In `create_tenant()` function in `backend/src/routes/sysadmin_tenants.py`
    - Extract `initial_admin_email = data.get('initial_admin_email', '').strip() or None` from request data
    - Pass `initial_admin_email=initial_admin_email` to `service.create_and_provision_tenant()`
    - Include `initial_admin` result in the response if present in `results`
    - _Requirements: 2.1_

  - [x] 3.4 Update `provision_tenant.py` — pass signup email as `initial_admin_email`
    - In `provision()` function in `backend/scripts/provision_tenant.py`
    - Pass `initial_admin_email=email` to `service.create_and_provision_tenant()`
    - Log the initial_admin result alongside other provisioning results
    - _Requirements: 2.2_

  - [x] 3.5 Update `sysadmin_provisioning.py` — pass signup email as `initial_admin_email`
    - In `provision_signup()` function in `backend/src/routes/sysadmin_provisioning.py`
    - Pass `initial_admin_email=email` to `service.create_and_provision_tenant()`
    - Include `initial_admin` result in the response if present in `prov_results`
    - _Requirements: 2.3_

  - [x] 3.6 Add SysAdmin resend invitation endpoint
    - Add `POST /api/sysadmin/tenants/<administration>/resend-invitation` to `backend/src/routes/sysadmin_tenants.py`
    - Authorization: `@cognito_required(required_roles=['SysAdmin'])`
    - Request body: `{ "email": "admin@example.com" }`
    - Look up existing invitation in `user_invitations` for email + administration
    - If no invitation exists, create one via `InvitationService.create_invitation()`
    - Generate new temporary password via `InvitationService`
    - Update Cognito user password via `admin_set_user_password(Password=new_temp_password, Permanent=True)` to keep status `CONFIRMED`
    - If user has no `user_tenant_roles` row, create one with `Tenant_Admin` (handles pre-fix tenants)
    - Send invitation email via `SESEmailService` using `EmailTemplateService` for locale-aware templates
    - Return `{ "success": true, "message": "Invitation resent", "email": email }`
    - _Requirements: 2.5, 2.6_

  - [x] 3.7 Add resend invitation API call to `sysadminService.ts`
    - Add `resendInvitation(administration: string, email: string)` function to `frontend/src/services/sysadminService.ts`
    - Call `POST /api/sysadmin/tenants/${administration}/resend-invitation` with `{ email }`
    - Return `{ success: boolean; message: string }`
    - _Requirements: 2.5_

  - [x] 3.8 Add "Resend Invitation" button to SysAdmin Tenant Management modal
    - In `frontend/src/components/SysAdmin/TenantManagement.tsx`
    - Add button in the edit modal footer, next to the existing action buttons
    - Button visible only in `modalMode === 'edit'`
    - On click: call `resendInvitation(selectedTenant.administration, formData.contact_email)`
    - Show success/error toast with result
    - Disable button while request is in progress (use `actionLoading` state)
    - Add translation keys for button label and toast messages in both `nl` and `en` locale files
    - _Requirements: 2.5_

  - [x] 3.9 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** — Initial Admin User Created During Provisioning
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1: `pytest backend/tests/unit/test_initial_admin_bug_condition.py -v`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — `create_and_provision_tenant()` now accepts `initial_admin_email` and creates the admin user)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.10 Verify preservation tests still pass
    - **Property 2: Preservation** — Existing Provisioning Infrastructure Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2: `pytest backend/tests/unit/test_initial_admin_preservation.py -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — tenant, modules, chart behavior unchanged)
    - Confirm all tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.7, 3.8_

- [x] 4. Write unit tests for `create_initial_admin_user()` and resend endpoint
  - Create test file `backend/tests/unit/test_create_initial_admin_user.py`
  - Test new Cognito user path: verify `CognitoService.create_user()` called, `admin_set_user_password(Permanent=True)` called, `user_tenant_roles` INSERT executed, `InvitationService.create_invitation()` called, `SESEmailService.send_invitation()` called
  - Test existing Cognito user path: verify `CognitoService.add_tenant_to_user()` called, `user_tenant_roles` INSERT executed, tenant-added notification sent, NO `admin_set_user_password` call
  - Test idempotent skip: when `user_tenant_roles` row already exists, method returns `{'status': 'skipped'}` and no Cognito/email calls made
  - Test `create_and_provision_tenant()` with `initial_admin_email=None`: verify no user creation step attempted, results dict has no `initial_admin` key
  - Test `create_and_provision_tenant()` with `initial_admin_email` provided: verify `create_initial_admin_user()` called, results dict has `initial_admin` key
  - Test error handling: when `create_initial_admin_user()` raises exception, overall provisioning still succeeds with warning
  - Test Cognito user status: verify `admin_set_user_password(Permanent=True)` is called for new users to set status to `CONFIRMED`
  - Test resend invitation endpoint: mock services, verify new password generated, Cognito password updated, email sent
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.8_

- [x] 5. Checkpoint — Ensure all tests pass
  - Run full test suite: `pytest backend/tests/unit/test_initial_admin_bug_condition.py backend/tests/unit/test_initial_admin_preservation.py backend/tests/unit/test_create_initial_admin_user.py backend/tests/unit/test_tenant_provisioning_service.py -v`
  - Verify all exploration tests (Property 1) now PASS
  - Verify all preservation tests (Property 2) still PASS
  - Verify all unit tests for new functionality PASS
  - Verify existing `test_tenant_provisioning_service.py` tests still PASS (no regressions)
  - Ensure all tests pass, ask the user if questions arise.
