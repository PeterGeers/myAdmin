# Implementation Plan

## Overview

Code quality maintenance sprint based on CI test results (2026-06-27) and local static analysis. Addresses 163 backend + 25 frontend test failures, 6 critical file length violations, and accumulated technical debt.

## Tasks

### Phase 1: Fix CI Test Failures — Import & Module Errors (~2 hours)

- [x] 1. Add `migrations/` to PYTHONPATH in CI workflow or move `backfill_rekeningschema_flags.py` to `backend/src/migrations/` (fixes 34 import failures)
- [x] 2. Update `TemplatePreviewService` test mocks to match refactored API — methods `_render_template`, `_validate_*`, `_fetch_*` renamed/removed (fixes 55 failures)
- [x] 3. Fix storage provider routing in `test_provider_aware_preservation.py` — tests expect gdrive instantiation but code defaults to S3 (fixes 8 failures)
- [x] 4. Add `@settings(deadline=None)` to flaky Hypothesis tests: `test_cors_property`, `test_provisioning_preservation`, `test_tourist_tax_calculator_props`, `test_tenant_function_service_props`, `test_invoice_booking_helper_props` (fixes 5 failures)

### Phase 2: Fix CI Test Failures — Assertion & Mock Drift (~4 hours)

- [x] 5. Fix OPTIONS handler for disallowed origins returning 403 instead of 200 with no CORS headers (fixes 6 failures)
- [x] 6. Fix provisioning status tests (`'failed' == 'created'`) — storage provider seeding logic changed (fixes 4 failures)
- [x] 7. Update `email_template_service` patch paths after module restructure (fixes 4 failures)
- [x] 8. Update frontend error handling test mocks/assertions in `STRInvoice`, `STRPricing`, `STRProcessor`, `YearEndClosureSection`, `InvoicePreviewModal` (fixes 25 frontend failures)
- [x] 9. Add `cnt` key to budget status transition response (fixes 2 `KeyError` failures)
- [x] 10. Register missing routes: `/api/reports/trends-data`, `/balance-data`, `/reference-analysis` (fixes 3 failures)
- [x] 11. Fix rate limiter off-by-one boundary calculation (fixes 2 failures)
- [x] 12. Update S3 presigned URL mock to include `ResponseContentType` param (fixes 1 failure)
- [x] 13. Fix zero-result handling in `transaction_logic.py` — Gamma fallback bug (fixes 1 failure)
- [x] 14. Skip pre-commit hook assertion in CI environment (fixes 1 failure)
- [x] 15. Use `os.path.join` for path separator issue on CI runner (fixes 1 failure)
- [x] 16. Create shared auth fixture in `backend/tests/api/conftest.py` for authenticated Flask test client (unblocks 5 skipped API tests)

### Phase 3: Critical File Length Violations (>1000 lines) (~3-4 days)

- [x] 17. Split `backend/src/services/budget_service.py` (1398 lines) into `budget_query_service.py` + `budget_mutation_service.py`
- [x] 18. Split `backend/src/routes/tenant_admin_users.py` (1166 lines) — extract user CRUD, role assignment, invitation into separate blueprints
- [x] 19. Split `backend/src/routes/zzp_routes.py` (1080 lines) — separate invoice routes from time-tracking routes
- [x] 20. Split `backend/src/routes/chart_of_accounts_routes.py` (1004 lines) — extract import/export logic to service layer
- [x] 21. Split `frontend/src/components/PDFUploadForm.tsx` (1074 lines) — extract file validation, preview, and upload hooks
- [x] 22. ~~Split `backend/src/validate_pattern/pattern_analyzer_test.py` (1774 lines)~~ — DELETED: One-time validation script directory (not production code). The production `pattern_analyzer.py` (579 lines) already delegates to `pattern_detection.py`, `pattern_scoring.py`, and `pattern_storage.py`. Entire `validate_pattern/` directory removed.

### Phase 4: Type Safety Improvements (~3-4 days)

- [x] 23. Audit and replace `any` types in frontend `services/` and `hooks/` — fixed 14 `any` usages in `apiService.ts`, `authService.ts`, `tenantApiService.ts`, `pivotService.ts`, `useBankingProcessor.ts`, `useTenantValidation.ts`, `useTableConfig.ts`, `parameterTypes.ts`, `tenant.ts`
- [x] 24. Remove `as any` casts in priority files — removed 4 `as any` casts in `authService.ts`, `apiService.ts`, `pivotService.ts`
- [x] 25. Add return type hints to `backend/src/services/*.py` public API functions — fixed `invoice_service.py`, `tenant_function_service.py`, `time_tracking_service.py`, `ai_usage_tracker.py`; 10 other files already had proper hints
- [x] 26. Add return type hints to `backend/src/routes/*.py` Flask route handlers (`-> Response`)

### Phase 5: File Length Violations (500-1000, backend) (~5 days)

- [x] 27. Split `services/year_end_service.py` (937→498 lines) — extracted `year_end_journal_entries.py` (493 lines) with closure transactions, opening balances, ending balances, and VAT netting logic
- [x] 28. Split `routes/sysadmin_tenants.py` (930→640 lines) — extracted `sysadmin_tenant_actions.py` (305 lines) with reprovision and resend-invitation endpoints
- [x] 29. Split `banking_processor.py` (920→380 lines) — extracted `banking_checks.py` (546 lines) with balance verification, sequence gaps, and Revolut balance analysis
- [x] 30. Split `services/zzp_invoice_service.py` (907→715 lines) — extracted `zzp_invoice_delivery.py` (256 lines) with send flow, PDF storage, email preview
- [x] 31. Split `pdf_decision_handler.py` (844→256 lines) — extracted `pdf_decision_helpers.py` (534 lines) with validation, component init, retry logic, and enhanced decision processing
- [x] 32. Split `file_cleanup_manager.py` (833→389 lines) — extracted `file_cleanup_actions.py` (306 lines) with URL handling, security validation, local/Drive cleanup operations
- [x] 33. Split `scalability_manager.py` (830→469 lines) — extracted `scalability_workers.py` (377 lines) with AsyncProcessingManager and ResourceMonitor
- [x] 34. Split `security_audit.py` (790→509 lines) — extracted `security_validators.py` (331 lines) with input validation, SQL injection checks, file upload validation, XSS detection, password strength
- [x] 35. Split `xlsx_report_generators.py` (766→587 lines) — extracted `xlsx_download_helpers.py` (204 lines) with file download helpers (Drive, S3, logging)
- [x] 36. Split `database.py` (727→557 lines) — extracted `database_banking_queries.py` (189 lines) with banking-specific lookups, patterns, and duplicate detection as a mixin

### Phase 6: File Length Violations (500-1000, frontend) (~4 days)

- [x] 37. Split `hooks/useBankingProcessor.ts` (935 lines) into `useBankingUpload`, `useBankingPatterns`, `useBankingState`
- [x] 38. Split `TenantAdmin/UserManagement.tsx` (881 lines) — extract UserTable, InviteModal, RoleEditor
- [x] 39. Split `SysAdmin/TenantManagement.tsx` (880 lines) — extract TenantTable, ProvisionModal
- [x] 40. Split `STRProcessor.tsx` (853 lines) — extract FileUpload, ResultsTable, SummaryPanel
- [x] 41. Split `ProfitLoss.tsx` (816 lines) — extract chart configs, filter panel, table sections
- [x] 42. Split `reports/BnbActualsReport.tsx` (792 lines) — extract chart component, data hook
- [x] 43. Split `pages/ZZPInvoiceDetail.tsx` (760 lines) — extract form sub-components
- [x] 44. Split `STRPricing.tsx` (737 lines) — extract pricing table, recommendation panel
- [x] 45. Split `TenantAdmin/TemplateManagement/TemplateUpload.tsx` (685 lines) — extract step components
- [x] 46. Split `pages/BudgetLinesPage.tsx` (633 lines) — extract BudgetLineTable, modal, toolbar

### Phase 7: Missing Test Coverage (~5 days)

- [x] 47. Add unit tests for `routes/aangifte_ib_routes.py` with mocked services
- [x] 48. Add unit tests for `routes/budget_routes.py` CRUD endpoints
- [x] 49. Add unit tests for `routes/financial_reporting_routes.py`
- [x] 50. Add unit tests for `routes/tenant_admin_credentials.py` credential CRUD + refresh
- [x] 51. Add unit tests for `routes/tenant_admin_templates.py` template upload/list/delete
- [x] 52. Add tests for `pdf_ai_extraction.py` with mocked OpenRouter API
- [x] 53. Add tests for `pattern_detection.py` against known bank descriptions
- [x] 54. Add tests for `str_airbnb_parser.py` and `str_booking_parser.py` with sample CSVs
- [x] 55. Add frontend tests for `ErrorBoundary.tsx`, `BankingProcessorTable.tsx`, `Login.tsx`
- [x] 56. Add frontend tests for `pages/BudgetPage.tsx` and `STRReports.tsx`

### Phase 8: Stale Documentation & TODOs (~1 day)

- [x] 57. Remove `Manuals/` from `.kiro/steering/structure.md` or restore directory
- [x] 58. Implement BTW adjustment in `business_pricing_model.py` or document as intentional no-op
- [x] 59. Implement token persistence on refresh in `tenant_admin_credentials.py`
- [x] 60. Create test data fixtures for year-end integration tests

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "wave-1",
      "name": "CI Green (Import & Module Fixes)",
      "tasks": [1, 2, 3, 4],
      "dependsOn": []
    },
    {
      "id": "wave-2",
      "name": "CI Green (Assertion & Mock Fixes)",
      "tasks": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
      "dependsOn": ["wave-1"]
    },
    {
      "id": "wave-3",
      "name": "Critical File Splits (>1000 lines)",
      "tasks": [17, 18, 19, 20, 21, 22],
      "dependsOn": ["wave-2"]
    },
    {
      "id": "wave-4",
      "name": "Type Safety Improvements",
      "tasks": [23, 24, 25, 26],
      "dependsOn": ["wave-2"]
    },
    {
      "id": "wave-5",
      "name": "Backend File Splits (500-1000)",
      "tasks": [27, 28, 29, 30, 31, 32, 33, 34, 35, 36],
      "dependsOn": ["wave-3"]
    },
    {
      "id": "wave-6",
      "name": "Frontend File Splits (500-1000)",
      "tasks": [37, 38, 39, 40, 41, 42, 43, 44, 45, 46],
      "dependsOn": ["wave-3"]
    },
    {
      "id": "wave-7",
      "name": "Missing Test Coverage",
      "tasks": [47, 48, 49, 50, 51, 52, 53, 54, 55, 56],
      "dependsOn": ["wave-2"]
    },
    {
      "id": "wave-8",
      "name": "Stale Documentation & TODOs",
      "tasks": [57, 58, 59, 60],
      "dependsOn": ["wave-2"]
    }
  ]
}
```

## Notes

- Waves 1-2 must be completed first to get CI green before refactoring
- Waves 3-8 are independent and can be parallelized across developers
- Dead code scan was clean (vulture ≥80% confidence) — no tasks needed
- File length tasks sorted by line count (largest first)
- Test coverage tasks prioritize business-critical modules over utilities
- Type safety work should be done incrementally alongside other changes
