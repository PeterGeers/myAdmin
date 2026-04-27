# Implementation Plan: Parameter Reset to Default

## Overview

Rework the Parameter Management modal and table to replace the misleading "Delete" action with a clear "Reset to Default" workflow, remove the inconsistent inline Actions column and Add Parameter button, add read-only mode for system-scope parameters with Customize in the modal, add JSON validation/formatting, and implement a Reset Confirmation Dialog with current vs default value comparison. The backend gets one new read-only endpoint to fetch the default value for preview.

## Tasks

- [x] 1. Add backend endpoint for fetching parameter default value
  - [x] 1.1 Implement `GET /api/tenant-admin/parameters/default` endpoint in `backend/src/routes/parameter_admin_routes.py`
    - Accept `namespace` and `key` query parameters
    - Return 400 if namespace or key is missing
    - Resolve default from `CODE_DEFAULTS` first (source: `code_default`), then system-scope DB row (source: `system`)
    - Return `{ success: true, has_default: false }` when neither exists
    - Mask value with `'********'` for secret parameters when user is not SysAdmin
    - Use `@cognito_required` + `@tenant_required()` decorators consistent with other endpoints
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 1.2 Write unit tests for the default value endpoint in `backend/tests/unit/test_parameter_admin_routes.py`
    - `test_get_default_returns_code_default` — parameter exists in CODE_DEFAULTS
    - `test_get_default_returns_system_scope_db` — parameter exists as system-scope DB row but not in CODE_DEFAULTS
    - `test_get_default_returns_no_default` — parameter exists nowhere
    - `test_get_default_code_default_takes_precedence` — parameter exists in both; CODE_DEFAULTS wins
    - `test_get_default_masks_secret_for_non_sysadmin` — secret returns `********` for non-SysAdmin
    - `test_get_default_shows_secret_for_sysadmin` — secret returns actual value for SysAdmin
    - `test_get_default_requires_namespace_and_key` — returns 400 when query params missing
    - _Requirements: 1.1, 1.2, 1.3, 1.5_

  - [x] 1.3 Write property-based test for default value resolution (Hypothesis)
    - **Property 1: Default Value Resolution Completeness**
    - Generate random `(namespace, key)` pairs against a generated CODE_DEFAULTS dict and system-scope DB rows
    - Verify: CODE_DEFAULTS entry → `source: "code_default"`, system DB row only → `source: "system"`, neither → `has_default: false`
    - Verify `value_type` matches the source's declared type
    - Minimum 100 iterations
    - **Validates: Requirements 1.1, 1.2, 1.3**

- [x] 2. Checkpoint — Ensure backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Extend frontend service and types for default value fetching
  - [x] 3.1 Add `ParameterDefaultResponse` interface to `frontend/src/types/parameterTypes.ts`
    - Fields: `success: boolean`, `has_default: boolean`, `value?: any`, `value_type?: 'string' | 'number' | 'boolean' | 'json'`, `source?: 'code_default' | 'system'`
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 3.2 Add `getParameterDefault(namespace, key)` function to `frontend/src/services/parameterService.ts`
    - Build URL with `URLSearchParams` for namespace and key
    - Call `authenticatedGet` with `buildEndpoint` to `${BASE}/default`
    - Return typed `ParameterDefaultResponse`
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 4. Rework ParameterManagement component — remove Actions column, Add button, and isNew logic
  - [x] 4.1 Remove Actions column and inline buttons from `frontend/src/components/TenantAdmin/ParameterManagement.tsx`
    - Remove `<Th>Actions</Th>` header column
    - Remove the `<Td>` with inline `IconButton` components (Customize, Reset)
    - Remove `handleCustomize` and `handleResetToDefault` functions that operate outside the modal
    - Adjust empty-state `colSpan` to `tableConfig.columns.length` (no +1)
    - Remove `AddIcon`, `EditIcon`, `RepeatIcon` imports if no longer used
    - _Requirements: 4.1_

  - [x] 4.2 Remove Add Parameter button and isNew/create logic from the modal
    - Remove the "Add Parameter" `<Button>` and `handleAdd` function
    - Remove `isNew` state variable and all conditional branches that use it
    - Remove the create-new-parameter path from `handleSave` (keep only update and customize paths)
    - Remove namespace/key/value_type/is_secret form fields that were only editable for new parameters
    - _Requirements: 4.2_

- [x] 5. Implement modal read-only mode and Customize-in-modal
  - [x] 5.1 Add read-only vs edit mode to the modal in `ParameterManagement.tsx`
    - Add `isReadOnly` state variable, set based on `scope_origin` in `handleRowClick`
    - `scope_origin === 'system'` (or `id === null`) → read-only mode: all value fields disabled
    - `scope_origin === 'tenant'` → edit mode: value field enabled
    - Make all parameter rows clickable (remove the system-scope click guard)
    - Update modal header to show "View Parameter" for read-only, "Edit Parameter" for edit mode
    - _Requirements: 4.3, 4.4, 4.5_

  - [x] 5.2 Implement Customize button in read-only modal footer
    - Show "Customize" + "Cancel" buttons in modal footer when `isReadOnly === true`
    - Customize creates a tenant-scope copy via `createParameter` with `scope: 'tenant'`
    - After successful customize: show success toast, refresh list, close modal (user reopens to edit)
    - _Requirements: 4.3_

- [x] 6. Implement Reset to Default and Delete button logic in modal footer
  - [x] 6.1 Add conditional Reset to Default / Delete button in edit-mode modal footer
    - When `scope_origin === 'tenant'` AND `has_code_default === true`: show "Reset to Default" button
    - When `scope_origin === 'tenant'` AND `has_code_default === false`: show "Delete" button (existing behavior)
    - No destructive button for read-only mode (system/code_default parameters)
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 6.2 Implement Reset Confirmation Dialog with value comparison
    - Add new `useDisclosure` for reset dialog (`isResetOpen`, `onResetOpen`, `onResetClose`)
    - Add state: `defaultValue`, `defaultSource`, `loadingDefault`
    - When "Reset to Default" clicked: fetch default via `getParameterDefault`, then open dialog
    - Dialog shows: namespace.key heading, "Current value" label + value, "Default value (source)" label + value
    - For `value_type === 'json'`: display both values with `JSON.stringify(value, null, 2)` in monospace `<Code>` block
    - For `is_secret === true` (non-SysAdmin): show `********` for both values
    - Use Chakra `AlertDialog` consistent with existing delete confirmation pattern
    - _Requirements: 2.3, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 6.3 Wire confirm/cancel actions in Reset Confirmation Dialog
    - On confirm: call `deleteParameter(editing.id)`, show success toast "Parameter reset to default", refresh list, close reset dialog + edit modal
    - On cancel: close reset dialog, return to edit modal
    - On error: show error toast with message, keep dialog open
    - _Requirements: 3.6, 3.7, 7.1, 7.2, 7.3, 7.4_

- [x] 7. Implement JSON validation and Format button in modal
  - [x] 7.1 Add JSON validation on change in the edit modal
    - Add `jsonError` state variable
    - On every `formValue` change when `formType === 'json'`: try `JSON.parse`, set error message on failure, clear on success
    - Display error message as red text below the textarea when invalid
    - Disable Save button when `jsonError !== null` and `formType === 'json'`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 7.2 Add Format button for JSON textarea
    - Render "Format" button next to the value `FormLabel` when `formType === 'json'`
    - On click: parse current value, re-stringify with 2-space indent, update `formValue`
    - Disable Format button when JSON is invalid or modal is read-only
    - Use `Button size="xs" variant="ghost" colorScheme="blue"`
    - _Requirements: 5.5_

- [x] 8. Checkpoint — Ensure frontend builds and manual smoke test
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Write frontend unit tests for modal behavior
  - [x] 9.1 Write Jest + React Testing Library tests in `frontend/src/components/TenantAdmin/__tests__/ParameterManagement.test.tsx`
    - `test_actions_column_removed` — verify no Actions column header or inline buttons render
    - `test_add_button_removed` — verify no "Add Parameter" button renders
    - `test_system_param_opens_readonly_modal` — click system-scope row, verify fields disabled + Customize button
    - `test_tenant_param_opens_edit_modal` — click tenant-scope row, verify fields enabled + Save button
    - `test_reset_button_shown_when_has_code_default` — verify "Reset to Default" button for tenant params with code default
    - `test_delete_button_shown_when_no_code_default` — verify "Delete" button for tenant params without code default
    - `test_reset_confirm_calls_delete_and_refreshes` — confirm reset, verify DELETE call + list refresh
    - `test_reset_cancel_closes_dialog` — cancel reset, verify no API call + dialog closed
    - `test_customize_creates_tenant_copy` — click Customize in read-only modal, verify POST call
    - `test_json_validation_disables_save` — enter invalid JSON, verify Save disabled + error shown
    - `test_json_format_button_formats_valid_json` — click Format, verify JSON re-indented
    - `test_success_toast_on_reset` — verify success toast after reset
    - `test_error_toast_on_reset_failure` — verify error toast on failed reset
    - Mock `getParameterDefault` in the service mock
    - _Requirements: 2.1, 2.2, 2.3, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.5, 7.1, 7.2_

- [x] 10. Write frontend property-based tests with fast-check
  - [x] 10.1 Write property test for modal footer button determination
    - **Property 2: Modal Footer Button Determination**
    - Generate random `Parameter` objects with varying `scope_origin` and `has_code_default`
    - Verify: tenant + has_code_default → "Reset to Default", tenant + no code default → "Delete", system → "Customize"
    - Minimum 100 iterations
    - **Validates: Requirements 2.1, 2.2, 2.4**

  - [x] 10.2 Write property test for confirmation dialog information display
    - **Property 3: Confirmation Dialog Information Display**
    - Generate random namespace, key, current value, default value strings
    - Verify all appear in dialog: namespace.key heading, "Current value" label, "Default value" label
    - Minimum 100 iterations
    - **Validates: Requirements 3.1, 3.2, 3.3**

  - [x] 10.3 Write property test for JSON values formatted in dialog
    - **Property 4: JSON Values Formatted in Confirmation Dialog**
    - Generate random JSON objects via `fc.jsonValue()`
    - Verify dialog displays `JSON.stringify(value, null, 2)` for both current and default values
    - Minimum 100 iterations
    - **Validates: Requirements 3.4**

  - [x] 10.4 Write property test for modal mode matching parameter scope
    - **Property 5: Modal Mode Matches Parameter Scope**
    - Generate random parameters with varying `scope_origin`
    - Verify: system → read-only (fields disabled, Customize shown), tenant → edit (fields enabled, Save shown)
    - Minimum 100 iterations
    - **Validates: Requirements 4.3, 4.4**

  - [x] 10.5 Write property test for JSON validation controlling Save button
    - **Property 6: JSON Validation Controls Save Button**
    - Generate random strings via `fc.oneof(fc.json(), fc.string())`
    - Verify Save button enabled iff `JSON.parse` succeeds; error message shown when invalid
    - Minimum 100 iterations
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

  - [x] 10.6 Write property test for JSON Format button idempotence
    - **Property 7: JSON Format Button Idempotence**
    - Generate random valid JSON objects
    - Verify Format produces `JSON.stringify(JSON.parse(input), null, 2)` and is idempotent (applying twice yields same result)
    - Verify Format button disabled when JSON is invalid
    - Minimum 100 iterations
    - **Validates: Requirements 5.5**

- [x] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [-] 12. Commit and push to main
  - Stage all changed files (backend endpoint, frontend component, services, types, tests)
  - Commit with message: "feat: parameter reset-to-default — replace Delete with Reset, remove Actions column, add JSON validation"
  - Push to main branch

## Notes

- All tasks are required
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- The reset operation reuses the existing `DELETE /api/tenant-admin/parameters/{id}` endpoint — no new write endpoint needed
- `CODE_DEFAULTS`, `scope_origin`, and `has_code_default` are already available from the existing list endpoint
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend: Python + Flask, pytest + Hypothesis
- Frontend: React 19 + TypeScript + Chakra UI, Jest + React Testing Library + fast-check
