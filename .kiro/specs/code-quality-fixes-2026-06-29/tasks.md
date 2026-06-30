# Implementation Plan

## Overview

Code quality maintenance sprint based on CI test results (2026-06-29) and local static analysis. Addresses 103 backend + 23 frontend test failures, file length violations, and accumulated technical debt. Incorporates lessons learned from the 2026-06-27 cycle where tasks were marked done without verification.

## Execution Rules (Lessons Learned)

1. **Delete, don't workaround**: When a source module is gone, delete the test file outright.
2. **Verify after each task**: Run the listed verification command. Task is not done until it passes.
3. **Grep all tests when changing defaults**: `grep -r "old_value" backend/tests/ frontend/src/` before marking done.
4. **Update fixtures when adding guards**: Find all tests for affected routes in the same commit.
5. **CI gate between phases**: Run Full Test Suite after each wave. Do not proceed until 0 failures.

## Tasks

### Phase 1: Critical — Tests That Cannot Collect (~2 hours)

- [x] 1. Delete `backend/tests/unit/test_backfill_rekeningschema_flags.py` — module `migrations.backfill_rekeningschema_flags` removed (34 import failures). This was identified on 2026-06-27 but never resolved. Verify: `pytest backend/tests/unit/ --collect-only 2>&1 | grep -c "ERROR"` returns 0.
- [x] 2. Fix `backend/tests/unit/test_template_rendering.py` — find current method name in `template_preview_service.py` replacing `_render_template` and update 19 tests. If method is gone entirely, delete the test file. Verify: `pytest backend/tests/unit/test_template_rendering.py -v` (19 pass or file deleted).
- [x] 3. Fix `backend/tests/unit/test_bug_condition_bank_lookup.py` — `BankingProcessor._checks` moved to `banking_checks.py` during 2026-06-27 split. Update 2 tests to use new location. Verify: `pytest backend/tests/unit/test_bug_condition_bank_lookup.py -v` (2 pass).
- [x] 4. Fix `backend/tests/unit/test_preservation_bank_lookup.py` — same `_checks` issue as task 3. Verify: `pytest backend/tests/unit/test_preservation_bank_lookup.py -v` (2 pass).

### Phase 2: Route/URL Fixes (~2 hours)

- [x] 5. Fix `backend/tests/unit/test_delete_tenant_template.py` — 6 tests get 404. Check route registration in `tenant_admin_templates.py` and `app.py`. Also run: `grep -rn "tenant-admin/templates" backend/tests/`. Verify: `pytest backend/tests/unit/test_delete_tenant_template.py -v` (6 pass).
- [x] 6. Fix `backend/tests/unit/test_download_default_template.py` — 5 tests get 404. Same root cause as task 5. Verify: `pytest backend/tests/unit/test_download_default_template.py -v` (5 pass).
- [x] 7. Fix `backend/tests/unit/test_tenant_admin_per_tenant_roles.py` — 2 tests get 404. Check `tenant_admin_roles.py` registration. Verify: `pytest backend/tests/unit/test_tenant_admin_per_tenant_roles.py -v` (2 pass).
- [x] 8. Fix `backend/tests/unit/test_tenant_admin_users_routes.py` — 3 tests fail, role endpoints not registered. Verify blueprint includes role routes. Verify: `pytest backend/tests/unit/test_tenant_admin_users_routes.py -v` (3 pass).
- [x] 9. Fix `backend/tests/unit/test_valid_template_types.py` — 1 test gets 404. Verify: `pytest backend/tests/unit/test_valid_template_types.py -v` (1 pass).

### Phase 3: Storage Default & Auth Fixes (~3 hours)

- [x] 10. Fix `backend/tests/unit/test_storage_resolver.py` — default changed to `s3_shared`. Update 4 assertions. First run: `grep -rn "google_drive\|gdrive" backend/tests/ --include="*.py"` to find ALL affected tests. Verify: `pytest backend/tests/unit/test_storage_resolver.py -v` (all pass).
- [x] 11. Fix `backend/tests/unit/test_zzp_invoice_service.py` — `check_health` called with `'s3'` not `'gdrive'`. Verify: `pytest backend/tests/unit/test_zzp_invoice_service.py::test_send_invoice_draft_success_returns_invoice_number -v` (pass).
- [x] 12. Fix `backend/tests/unit/test_output_service.py` — 4 tests need S3 mocks instead of Google Drive. Also check: `grep -rn "GoogleDriveService" backend/tests/`. Verify: `pytest backend/tests/unit/test_output_service.py -v` (4 pass).
- [x] 13. Fix `backend/tests/unit/test_xlsx_export.py` — 2 tests with broken Drive mocks. Update to S3 pattern. Verify: `pytest backend/tests/unit/test_xlsx_export.py -v` (2 pass).
- [ ] 14. Fix `backend/tests/unit/test_str_channel_routes_fix.py` — 8 tests get 403. Inspect route decorators (`@module_required('STR')` or `@function_guard`). Add tenant context with STR module enabled + correct roles to fixtures. Verify: `pytest backend/tests/unit/test_str_channel_routes_fix.py -v` (8 pass).

### Phase 4: Logic & Mock Drift Fixes (~3 hours)

- [ ] 15. Fix `backend/tests/unit/test_banking_balance_closure.py` — 3 tests assert old SQL patterns. Read current query in `banking_checks.py` and update assertions. Verify: `pytest backend/tests/unit/test_banking_balance_closure.py -v` (3 pass).
- [ ] 16. Fix `backend/tests/unit/test_vrbo_processor.py` — 2 tests expect `'planned'` but get `'realised'`. First check `str_booking_parser.py` to confirm if intentional. If yes, update assertions. If bug, fix source. Verify: `pytest backend/tests/unit/test_vrbo_processor.py -v` (2 pass).
- [ ] 17. Fix `backend/tests/unit/test_function_guard_props.py` — flaky Hypothesis test. Add `@settings(derandomize=True)` or fix shared state. Verify: `pytest backend/tests/unit/test_function_guard_props.py -v --count=3` (pass 3x).
- [ ] 18. Fix `backend/tests/unit/test_invoice_service_properties.py` — flaky. Same approach as task 17. Verify: `pytest backend/tests/unit/test_invoice_service_properties.py -v --count=3` (pass 3x).
- [ ] 19. Fix `backend/tests/unit/test_parameter_admin_routes.py` — flaky. Verify: `pytest backend/tests/unit/test_parameter_admin_routes.py -v --count=3` (pass 3x).
- [ ] 20. Fix `backend/tests/unit/test_security_middleware_props.py` — flaky. Verify: `pytest backend/tests/unit/test_security_middleware_props.py -v --count=3` (pass 3x).

### Phase 5: Frontend Test Fixes (~4 hours)

- [ ] 21. Fix `frontend/src/components/TenantAdmin/ChartOfAccounts.test.tsx` — 8 tests with outdated selectors. Read current `ChartOfAccounts.tsx` for correct text/roles. Verify: `npx vitest run src/components/TenantAdmin/ChartOfAccounts.test.tsx` (8 pass).
- [ ] 22. Fix `frontend/src/components/TenantAdmin/StorageTab.test.tsx` — 8 tests where mock functions not called. Component initialization flow changed. Verify: `npx vitest run src/components/TenantAdmin/StorageTab.test.tsx` (8 pass).
- [ ] 23. Fix `frontend/src/components/SysAdmin/TenantManagement.test.tsx` — 3 tests with duplicate button selectors. Use `within()` or more specific queries. Verify: `npx vitest run src/components/SysAdmin/TenantManagement.test.tsx` (3 pass).
- [ ] 24. Fix `frontend/src/components/SysAdmin/__tests__/InvoiceTestTool.test.tsx` — 3 tests with changed validation messages and placeholder text. Read current component. Verify: `npx vitest run src/components/SysAdmin/__tests__/InvoiceTestTool.test.tsx` (all pass).
- [ ] 25. Fix `frontend/src/aws-exports.test.ts` — 1 test with overly strict regex. Relax to accept test environment client IDs. Verify: `npx vitest run src/aws-exports.test.ts` (pass).

### Phase 6: File Length Refactoring — Backend (~5 days)

- [ ] 26. Split `backend/src/routes/zzp_routes.py` (961 lines) — extract time-tracking into `zzp_time_routes.py`. Verify: `pytest backend/tests/unit/test_zzp_* -v` (all pass).
- [ ] 27. Split `backend/src/services/invoice_test_service.py` (859 lines) — extract test data generators/fixtures into separate module. Verify: `pytest backend/tests/unit/test_invoice_test_service.py -v` (pass).
- [ ] 28. Split `backend/src/routes/chart_of_accounts_routes.py` (850 lines) — extract import/export into `chart_of_accounts_io_routes.py`. Verify: `pytest backend/tests/ -k "chart_of_accounts" -v` (all pass).
- [ ] 29. Split `backend/src/routes/tenant_admin_credentials.py` (788 lines) — extract OAuth flow into `credential_service.py`. Verify: `pytest backend/tests/unit/test_tenant_admin_credentials* -v` (pass).
- [ ] 30. Split `backend/src/routes/tenant_admin_templates.py` (777 lines) — move template logic to service layer. Verify: `pytest backend/tests/unit/test_tenant_admin_templates* -v` (pass).
- [ ] 31. Split `backend/src/services/banking_service.py` (764 lines) — separate query vs mutation operations. Verify: `pytest backend/tests/unit/test_banking_service.py -v` (pass).

### Phase 7: File Length Refactoring — Frontend (~3 days)

- [ ] 32. Split `frontend/src/components/SysAdmin/PipelineResultsPanel.tsx` (656 lines) — extract log viewer and status display into child components. Verify: `npm run build` (no errors).
- [ ] 33. Split `frontend/src/components/TenantAdmin/TemplateManagement/TemplateManagement.tsx` (645 lines) — extract modal forms. Verify: `npx vitest run src/components/TenantAdmin/TemplateManagement/` (pass).
- [ ] 34. Split `frontend/src/pages/BudgetTemplatesPage.tsx` (593 lines) — extract template form modal. Verify: `npm run build` (no errors).

### Phase 8: Missing Test Coverage (~5 days)

- [ ] 35. Write tests for `backend/src/services/budget_mutation_service.py` (762 lines). Verify: `pytest backend/tests/unit/test_budget_mutation_service.py -v` (pass).
- [ ] 36. Write tests for `backend/src/services/budget_query_service.py` (703 lines). Verify: `pytest backend/tests/unit/test_budget_query_service.py -v` (pass).
- [ ] 37. Write tests for `backend/src/banking_checks.py` (546 lines). Verify: `pytest backend/tests/unit/test_banking_checks.py -v` (pass).
- [ ] 38. Write tests for `backend/src/pdf_decision_helpers.py` (534 lines). Verify: `pytest backend/tests/unit/test_pdf_decision_helpers.py -v` (pass).
- [ ] 39. Write tests for `backend/src/services/credential_service.py`. Verify: `pytest backend/tests/unit/test_credential_service.py -v` (pass).
- [ ] 40. Write tests for `frontend/src/components/BankingTransactionModal.tsx`. Verify: `npx vitest run src/components/BankingTransactionModal.test.tsx` (pass).
- [ ] 41. Write tests for `frontend/src/components/MissingInvoices.tsx`. Verify: `npx vitest run src/components/MissingInvoices.test.tsx` (pass).

### Phase 9: Type Safety & Documentation (~3 days)

- [ ] 42. Add proper return types to `frontend/src/services/timeTrackingService.ts` (5 `any` occurrences). Verify: `npx tsc --noEmit`.
- [ ] 43. Replace `Record<string, any>` in `frontend/src/utils/pivotTreeBuilder.ts` with typed row interface (7 occurrences). Verify: `npx tsc --noEmit`.
- [ ] 44. Type Formik `Field` render props in `Budget*Modal.tsx` (3 files, 6 each). Use `FieldProps<string>`. Verify: `npx tsc --noEmit`.
- [ ] 45. Add return type annotations to `backend/src/services/budget_ai_service.py` public functions. Verify: `python3 -c "import ast; ast.parse(open('backend/src/services/budget_ai_service.py').read())"` (no syntax errors).
- [ ] 46. Review `manualsSysAdm/` for Google Drive references — storage default is now S3. Update or annotate.
- [ ] 47. Review/delete `backend/src/services/GOOGLE_DRIVE_UPDATE_SUMMARY.md` given S3 default change.
- [ ] 48. Run `vulture backend/src/ --min-confidence 80` and remove confirmed dead code. Verify: `pytest backend/tests/ -x` (pass).

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "wave-1",
      "name": "Critical — Cannot Collect (Import/Attribute Errors)",
      "tasks": [1, 2, 3, 4],
      "dependsOn": []
    },
    {
      "id": "wave-2",
      "name": "Route/URL Registration Fixes",
      "tasks": [5, 6, 7, 8, 9],
      "dependsOn": ["wave-1"]
    },
    {
      "id": "wave-3",
      "name": "Storage Default & Auth Guard Fixes",
      "tasks": [10, 11, 12, 13, 14],
      "dependsOn": ["wave-1"]
    },
    {
      "id": "wave-4",
      "name": "Logic, Mock Drift & Flaky Tests",
      "tasks": [15, 16, 17, 18, 19, 20],
      "dependsOn": ["wave-1"]
    },
    {
      "id": "wave-5",
      "name": "Frontend Test Fixes",
      "tasks": [21, 22, 23, 24, 25],
      "dependsOn": ["wave-1"]
    },
    {
      "id": "wave-6",
      "name": "File Length Refactoring — Backend",
      "tasks": [26, 27, 28, 29, 30, 31],
      "dependsOn": ["wave-2", "wave-3", "wave-4"]
    },
    {
      "id": "wave-7",
      "name": "File Length Refactoring — Frontend",
      "tasks": [32, 33, 34],
      "dependsOn": ["wave-5"]
    },
    {
      "id": "wave-8",
      "name": "Missing Test Coverage",
      "tasks": [35, 36, 37, 38, 39, 40, 41],
      "dependsOn": ["wave-6"]
    },
    {
      "id": "wave-9",
      "name": "Type Safety & Documentation",
      "tasks": [42, 43, 44, 45, 46, 47, 48],
      "dependsOn": ["wave-2", "wave-3", "wave-4", "wave-5"]
    },
    {
      "id": "wave-10",
      "name": "CI Verification Gates",
      "tasks": [49, 50, 51, 52],
      "dependsOn": ["wave-6", "wave-7", "wave-8", "wave-9"]
    }
  ]
}
```

### Phase 10: CI Verification Gates

- [ ] 49. Run `gh workflow run "Full Test Suite" --field scope=both` after waves 1–5 complete. Verify: 0 backend failures, 0 frontend failures. If failures remain, fix them before proceeding.
- [ ] 50. Run `gh workflow run "Full Test Suite" --field scope=both` after waves 6–7 complete. Verify: no regressions introduced by file splits.
- [ ] 51. Run `gh workflow run "Full Test Suite" --field scope=both` after waves 8–9 complete. Verify: new tests pass in CI, no new failures.
- [ ] 52. Final check: confirm no recurring failures from 2026-06-27 spec remain (backfill migration imports, `_render_template`, `_checks` attribute, storage default).

## Parallelization Notes

- Waves 2, 3, 4, 5 are **independent** — can run in parallel after wave 1 completes
- Within each wave, all tasks are independent and can be submitted to separate agents
- Waves 6 and 7 are independent of each other
- Wave 9 can run in parallel with waves 6, 7, 8
- Task 49 gates waves 6+; task 50 gates wave 8; task 51 closes the spec
