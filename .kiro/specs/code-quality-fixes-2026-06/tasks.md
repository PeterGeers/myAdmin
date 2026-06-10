# Implementation Plan

## Overview

This plan addresses code quality issues found by automated scanning: file length violations, dead code, missing tests, type safety gaps, and stale documentation. Tasks are grouped into 5 phases (waves) prioritized by severity.

## Tasks

- [x] 1. Split `frontend/src/components/BankingProcessor.tsx` (2160 lines)
  - [x] 1.1 Extract table/grid rendering into `BankingProcessorTable.tsx`
  - [x] 1.2 Extract file upload logic into `BankingFileUpload.tsx`
  - [x] 1.3 Extract pattern matching UI into `BankingPatternPanel.tsx`
  - [x] 1.4 Extract transaction editing modal into `BankingTransactionModal.tsx`
  - [x] 1.5 Move shared state logic into `useBankingProcessor.ts` hook
  - [x] 1.6 Verify each sub-component renders correctly and all functionality preserved

- [ ] 2. Split `backend/src/pattern_analyzer.py` (1797 lines)
  - [x] 2.1 Extract pattern detection logic into `pattern_detection.py`
  - [x] 2.2 Extract pattern scoring/ranking into `pattern_scoring.py`
  - [x] 2.3 Extract cache management into existing `pattern_cache.py` or new helper
  - [x] 2.4 Keep `pattern_analyzer.py` as orchestrator (<500 lines)
  - [x] 2.5 Update all imports across the codebase

- [x] 3. Split `backend/src/tenant_admin_routes.py` (1589 lines)
  - [x] 3.1 Extract template-related endpoints into `routes/tenant_admin_templates.py` blueprint
  - [x] 3.2 Extract user management endpoints into existing `routes/tenant_admin_users.py`
  - [x] 3.3 Extract config endpoints into existing `routes/tenant_admin_config.py`
  - [x] 3.4 Keep only shared middleware/helpers in `tenant_admin_routes.py`
  - [x] 3.5 Register new blueprints in `app.py`

- [ ] 4. Split `backend/src/pdf_processor.py` (1467 lines)
  - [x] 4.1 Extract PDF parsing strategies into `pdf_parsing_strategies.py`
  - [x] 4.2 Extract AI extraction logic into `pdf_ai_extraction.py`
  - [x] 4.3 Extract decision-handling logic (`_handle_continue_decision`, `_handle_cancel_decision`) into `pdf_decision_handler.py`
  - [x] 4.4 Keep `pdf_processor.py` as the main entry point (<500 lines)
  - [x] 4.5 Update imports in routes and tests

- [x] 5. Split `backend/src/str_processor.py` (1383 lines)
  - [x] 5.1 Extract Airbnb-specific parsing into `str_airbnb_parser.py`
  - [x] 5.2 Extract Booking.com-specific parsing into `str_booking_parser.py`
  - [x] 5.3 Extract common STR utilities into `str_utils.py`
  - [x] 5.4 Keep `str_processor.py` as dispatcher (<500 lines)
  - [x] 5.5 Update all imports

- [x] 6. Split `backend/src/services/template_preview_service.py` (1362 lines)
  - [x] 6.1 Extract HTML parsing/sanitization into `template_html_processor.py`
  - [x] 6.2 Extract PDF rendering logic into `template_pdf_renderer.py`
  - [x] 6.3 Keep preview orchestration in `template_preview_service.py` (<500 lines)
  - [x] 6.4 Update imports

- [x] 7. Split `backend/src/reporting_routes.py` (1140 lines)
  - [x] 7.1 Extract aangifte IB endpoints into `routes/aangifte_ib_routes.py`
  - [x] 7.2 Extract balance/trends endpoints into `routes/financial_reporting_routes.py`
  - [x] 7.3 Keep general reporting endpoints in `reporting_routes.py` (<500 lines)
  - [x] 7.4 Register new blueprints in `app.py`

- [ ] 8. Split `backend/src/xlsx_export.py` (1070 lines)
  - [x] 8.1 Extract cell styling/formatting into `xlsx_styles.py`
  - [x] 8.2 Extract report-specific generators into `xlsx_report_generators.py`
  - [x] 8.3 Keep common export infrastructure in `xlsx_export.py` (<500 lines)
  - [x] 8.4 Update imports

- [ ] 9. Remove 100% confidence dead code
  - [x] 9.1 Remove unused `sender_company` variable at `backend/src/services/invoice_email_service.py:298`
  - [x] 9.2 Remove unused `sender_company` variable at `backend/src/services/invoice_email_service.py:310`
  - [x] 9.3 Fix unreachable code after `try` at `backend/src/str_processor.py:149`

- [ ] 10. Remove dead code in `performance_optimizer.py`
  - [x] 10.1 Remove unused class `BatchProcessor` and its methods
  - [x] 10.2 Remove unused functions: `start_performance_monitoring`, `log_performance`, `performance_status`, `analyze_performance`, `memory_check`, `optimize_performance`
  - [x] 10.3 Remove unused methods: `profile_function`, `take_memory_snapshot`, `detect_memory_leaks`, `force_garbage_collection`
  - [x] 10.4 Verify no runtime usage via grep for imports of removed symbols

- [ ] 11. Remove dead code in `duplicate_performance_monitor.py`
  - [x] 11.1 Remove unused methods: `monitor_file_cleanup`, `monitor_decision_log`, `monitor_database_query`
  - [x] 11.2 Remove unused functions: `get_metrics_collector`, `get_performance_summary`, `export_performance_metrics`, `reset_performance_metrics`
  - [x] 11.3 Verify no runtime usage

- [ ] 12. Remove dead code in `duplicate_query_optimizer.py`
  - [x] 12.1 Remove unused methods: `check_duplicates_optimized`, `analyze_query_performance`, `get_optimization_recommendations`, `get_query_statistics`, `invalidate_cache_for_transaction`, `cleanup_cache`, `reset_statistics`
  - [x] 12.2 Remove unused function: `reset_query_optimizer`
  - [x] 12.3 Verify no runtime usage

- [ ] 13. Remove dead code in `session_manager.py`
  - [x] 13.1 Remove unused methods: `create_session`, `extend_session`, `invalidate_session`, `get_session_info`, `get_active_session_count`, `get_session_statistics`
  - [x] 13.2 If entire module is unused, remove the file and imports

- [ ] 14. Remove dead code in `scalability_manager.py`
  - [x] 14.1 Remove unused variables: `cache_levels`, `cache_ttl_seconds`, `cache_max_memory_mb`, `pool`
  - [x] 14.2 Remove unused function: `initialize_scalability`
  - [x] 14.3 Verify no runtime usage

- [ ] 15. Remove dead code in `error_handlers.py`
  - [x] 15.1 Remove unused variables: `BUSINESS_LOGIC`, `EXTERNAL_SERVICE`
  - [x] 15.2 Remove unused functions: `user_friendly_error`, `bad_request`, `unauthorized`, `forbidden`, `not_found`, `internal_error`
  - [x] 15.3 Remove unused attribute: `error_mappings`
  - [x] 15.4 Verify no runtime usage

- [x] 16. Remove dead code in `hybrid_pricing_optimizer.py`
  - [x] 16.1 Remove unused variables: `events_data`, `historical_rates`
  - [x] 16.2 Remove unused methods: `_calculate_monthly_multipliers`, `_calculate_seasonal_multipliers`, `_get_season`
  - [x] 16.3 Verify no runtime usage

- [x] 17. Remove frontend unused exports
  - [x] 17.1 Remove `decodeJWTPayload` from `services/authService.ts`
  - [x] 17.2 Remove `getAccount` from `services/chartOfAccountsService.ts`
  - [x] 17.3 Remove `toBackendConfig` and `fromBackendConfig` from `services/pivotService.ts`
  - [x] 17.4 Remove `tenantAwarePut`, `tenantAwareDelete`, `createTenantParams` from `services/tenantApiService.ts`
  - [x] 17.5 Remove `getAvailableYears` from `services/yearEndClosureService.ts`
  - [x] 17.6 Remove `validateConfiguration`, `getConfiguredPurposes`, `setAccountPurpose`, `getAvailableAccounts` from `services/yearEndConfigService.ts`
  - [x] 17.7 Remove `getLocaleGreeting` from `utils/emailVerificationUtils.ts`
  - [x] 17.8 Remove `getErrorMessageByStatus`, `getErrorMessage` from `utils/errorHandling.ts`
  - [x] 17.9 Remove `filterByVW` from `utils/financialReportUtils.ts`
  - [x] 17.10 Remove `formatNumber` from `utils/formatting.ts`
  - [x] 17.11 Remove `isValidUrl`, `isValidPhone`, `isValidIBAN` from `utils/validationHelpers.ts`
  - [x] 17.12 Run `npx tsc --noEmit` to confirm no compile errors after removal

- [x] 18. Create vulture whitelist for Flask route handlers
  - [x] 18.1 Create `backend/vulture_whitelist.py` with all Flask blueprint route handler function names to suppress false positives
  - [x] 18.2 Document usage in project README or contributing guide

- [ ] 19. Backend service tests (highest priority — business logic)
  - [~] 19.1 Create `backend/tests/unit/test_banking_service.py` — test account lookup, transaction categorization
  - [~] 19.2 Create `backend/tests/unit/test_email_log_service.py` — test log retrieval, filtering
  - [~] 19.3 Create `backend/tests/unit/test_email_template_service.py` — test template rendering
  - [~] 19.4 Create `backend/tests/unit/test_tenant_language_service.py` — test language preference CRUD
  - [~] 19.5 Create `backend/tests/unit/test_tenant_settings_service.py` — test settings retrieval/update
  - [~] 19.6 Create `backend/tests/unit/test_user_language_service.py` — test user language preference
  - [~] 19.7 Create `backend/tests/unit/test_country_report_service.py` — test report generation
  - [~] 19.8 Create `backend/tests/unit/test_parameter_schema.py` — test schema validation
  - [~] 19.9 Create `backend/tests/unit/test_invoice_test_service.py` — test invoice tool functionality

- [ ] 20. Backend route tests (API coverage)
  - [~] 20.1 Create `backend/tests/api/test_banking_routes.py` — test all banking endpoints
  - [~] 20.2 Create `backend/tests/api/test_cache_routes.py` — test cache warmup/refresh/invalidation
  - [~] 20.3 Create `backend/tests/api/test_contact_routes.py` — test CRUD operations
  - [~] 20.4 Create `backend/tests/api/test_product_routes.py` — test product CRUD
  - [~] 20.5 Create `backend/tests/api/test_storage.py` — test presigned URL, logo upload
  - [~] 20.6 Create `backend/tests/api/test_str_routes.py` — test STR upload/save/pricing
  - [~] 20.7 Create `backend/tests/api/test_sysadmin_tenants.py` — test tenant CRUD
  - [~] 20.8 Create `backend/tests/api/test_tenant_admin_users.py` — test user management
  - [~] 20.9 Create `backend/tests/api/test_zzp_routes.py` — test ZZP invoice endpoints

- [ ] 21. Backend core module tests
  - [~] 21.1 Create `backend/tests/unit/test_mutaties_cache.py` — test cache invalidation logic
  - [~] 21.2 Create `backend/tests/unit/test_csv_rules.py` — test CSV rule matching
  - [~] 21.3 Create `backend/tests/unit/test_error_handlers.py` — test error response formatting
  - [~] 21.4 Create `backend/tests/unit/test_aws_notifications.py` — test SNS notification sending (mocked)
  - [~] 21.5 Create `backend/tests/unit/test_pattern_analyzer.py` — test pattern detection/scoring

- [ ] 22. Frontend service tests
  - [~] 22.1 Create `frontend/src/services/assetService.test.ts` — test API calls
  - [~] 22.2 Create `frontend/src/services/chartOfAccountsService.test.ts` — test CRUD calls
  - [~] 22.3 Create `frontend/src/services/contactService.test.ts` — test contact API
  - [~] 22.4 Create `frontend/src/services/debtorService.test.ts` — test debtor operations
  - [~] 22.5 Create `frontend/src/services/parameterService.test.ts` — test parameter fetching
  - [~] 22.6 Create `frontend/src/services/taxRateService.test.ts` — test tax rate API
  - [~] 22.7 Create `frontend/src/services/timeTrackingService.test.ts` — test time entry CRUD
  - [~] 22.8 Create `frontend/src/services/zzpInvoiceService.test.ts` — test invoice operations
  - [~] 22.9 Create `frontend/src/services/yearEndClosureService.test.ts` — test year-end API
  - [~] 22.10 Create `frontend/src/services/sysadminService.test.ts` — test admin API calls

- [ ] 23. Frontend component tests (most critical)
  - [~] 23.1 Create `frontend/src/components/STRPricing.test.tsx` — test pricing display/interaction
  - [~] 23.2 Create `frontend/src/components/STRInvoice.test.tsx` — test invoice rendering
  - [~] 23.3 Create `frontend/src/components/YearEndClosureSection.test.tsx` — test year-end workflow
  - [~] 23.4 Create `frontend/src/components/UserMenu.test.tsx` — test menu rendering/navigation
  - [~] 23.5 Create `frontend/src/components/InvoiceGenerator.test.tsx` — test invoice form
  - [~] 23.6 Create `frontend/src/components/Assets/AssetList.test.tsx` — test asset table
  - [~] 23.7 Create `frontend/src/components/SysAdmin/TenantManagement.test.tsx` — test tenant admin UI
  - [~] 23.8 Create `frontend/src/components/TenantAdmin/ChartOfAccounts.test.tsx` — test account management
  - [~] 23.9 Create `frontend/src/components/TenantAdmin/StorageTab.test.tsx` — test storage config

- [ ] 24. Add Python type hints to top-offender files
  - [~] 24.1 Add type hints to all functions in `backend/src/routes/zzp_routes.py` (30 missing returns, 28 missing params)
  - [~] 24.2 Add type hints to all functions in `backend/src/services/pivot_service.py` (18 returns, 21 params)
  - [~] 24.3 Add type hints to all functions in `backend/src/routes/banking_routes.py` (17 returns, 17 params)
  - [~] 24.4 Add type hints to all functions in `backend/src/services/year_end_service.py` (17 returns, 17 params)
  - [~] 24.5 Add type hints to all functions in `backend/src/routes/str_routes.py` (16 returns, 14 params)
  - [~] 24.6 Add type hints to all functions in `backend/src/services/banking_service.py` (12 returns, 12 params)
  - [~] 24.7 Add type hints to all functions in `backend/src/services/year_end_config.py` (12 returns, 12 params)
  - [~] 24.8 Add type hints to all functions in `backend/src/routes/tenant_admin_users.py` (11 returns, 11 params)
  - [~] 24.9 Add type hints to all functions in `backend/src/routes/pivot_routes.py` (12 returns, 10 params)
  - [~] 24.10 Add type hints to all functions in `backend/src/services/template_preview_service.py` (11 returns, 9 params)

- [ ] 25. Fix TypeScript `any` in top-offender files
  - [~] 25.1 Replace `any` types in `components/TenantAdmin/ParameterManagement.tsx` (17 occurrences) — define proper interfaces
  - [~] 25.2 Replace `any` types in `services/tenantAdminApi.ts` (16 occurrences) — add request/response types
  - [~] 25.3 Replace `any` types in `components/reports/BnbActualsReport.tsx` (12 occurrences) — type chart data
  - [~] 25.4 Replace `any` types in `components/BankingProcessor.tsx` (10 occurrences) — type transaction/pattern data
  - [~] 25.5 Replace `any` types in `components/PDFUploadForm.tsx` (9 occurrences) — type form/upload data
  - [~] 25.6 Replace `any` types in `services/zzpInvoiceService.ts` (9 occurrences) — add invoice types
  - [~] 25.7 Replace `any` types in `components/TenantAdmin/StorageTab.tsx` (8 occurrences) — type storage config
  - [~] 25.8 Replace `any` types in `services/debtorService.ts` (7 occurrences) — add debtor types
  - [~] 25.9 Replace `any` types in `pages/ZZPInvoiceDetail.tsx` (7 occurrences) — type invoice detail data
  - [~] 25.10 Replace `any` types in `components/reports/ProfitLossReport.tsx` (7 occurrences) — type financial data

- [ ] 26. Update `manualsSysAdm/` documentation
  - [~] 26.1 Review and update `DUPLICATE_DETECTION_INDEXES.md` — verify index names/structure match current `duplicate_checker.py`
  - [~] 26.2 Review and update `DUPLICATE_DETECTION_MONITORING.md` — verify monitoring code references match refactored code
  - [~] 26.3 Review and update `DUPLICATE_DETECTION_PERFORMANCE.md` — verify performance tips still apply
  - [~] 26.4 Review and update `DUPLICATE_DETECTION_TROUBLESHOOTING.md` — verify troubleshooting steps match current behavior
  - [~] 26.5 Review and update `PERFORMANCE_IMPLEMENTATION_SUMMARY.md` — verify `scalability_manager.py` references

- [ ] 27. Update `backend/src/services/` documentation
  - [~] 27.1 Review `TEMPLATE_PREVIEW_SERVICE_IMPLEMENTATION.md` against current `template_preview_service.py`
  - [~] 27.2 Review `TEMPLATE_SERVICE_DOCUMENTATION.md` against current `template_service.py`
  - [~] 27.3 Review `AI_TEMPLATE_ASSISTANT_IMPLEMENTATION.md` against current `ai_template_assistant.py`
  - [~] 27.4 Review `GOOGLE_DRIVE_UPDATE_SUMMARY.md` — check if referenced patterns still exist
  - [~] 27.5 Remove or archive any documentation for features/code that no longer exists

- [ ] 28. Add vulture to CI/pre-commit
  - [~] 28.1 Add vulture check to CI pipeline (with whitelist) to prevent new dead code accumulation
  - [~] 28.2 Document the code quality scan process for future scheduled runs

## Notes

- Flask route handlers flagged by vulture (60% confidence) are **false positives** — they are registered via `@blueprint.route()` decorators. A whitelist file will suppress these.
- `gunicorn.conf.py` variables are intentionally "unused" in the Python sense — they are read by the gunicorn server process. Excluded from findings.
- `validate_pattern/` directory contains test/validation copies and is excluded from dead code analysis.
- `chakraMock.tsx` uses `any` extensively as a test mock — this is acceptable and excluded from type safety tasks (Task 25).
- File length warnings (501–1000 lines) are documented in requirements but NOT assigned individual tasks — they should be addressed opportunistically during regular feature work.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": 0,
      "tasks": [
        "1.1",
        "1.2",
        "1.3",
        "1.4",
        "1.5",
        "1.6",
        "2.1",
        "2.2",
        "2.3",
        "2.4",
        "2.5",
        "3.1",
        "3.2",
        "3.3",
        "3.4",
        "3.5",
        "4.1",
        "4.2",
        "4.3",
        "4.4",
        "4.5",
        "5.1",
        "5.2",
        "5.3",
        "5.4",
        "5.5",
        "6.1",
        "6.2",
        "6.3",
        "6.4",
        "7.1",
        "7.2",
        "7.3",
        "7.4",
        "8.1",
        "8.2",
        "8.3",
        "8.4"
      ]
    },
    {
      "id": 1,
      "tasks": [
        "9.1",
        "9.2",
        "9.3",
        "10.1",
        "10.2",
        "10.3",
        "10.4",
        "11.1",
        "11.2",
        "11.3",
        "12.1",
        "12.2",
        "12.3",
        "13.1",
        "13.2",
        "14.1",
        "14.2",
        "14.3",
        "15.1",
        "15.2",
        "15.3",
        "15.4",
        "16.1",
        "16.2",
        "16.3",
        "17.1",
        "17.2",
        "17.3",
        "17.4",
        "17.5",
        "17.6",
        "17.7",
        "17.8",
        "17.9",
        "17.10",
        "17.11",
        "17.12",
        "18.1",
        "18.2"
      ]
    },
    {
      "id": 2,
      "tasks": [
        "19.1",
        "19.2",
        "19.3",
        "19.4",
        "19.5",
        "19.6",
        "19.7",
        "19.8",
        "19.9",
        "20.1",
        "20.2",
        "20.3",
        "20.4",
        "20.5",
        "20.6",
        "20.7",
        "20.8",
        "20.9",
        "21.1",
        "21.2",
        "21.3",
        "21.4",
        "21.5",
        "22.1",
        "22.2",
        "22.3",
        "22.4",
        "22.5",
        "22.6",
        "22.7",
        "22.8",
        "22.9",
        "22.10",
        "23.1",
        "23.2",
        "23.3",
        "23.4",
        "23.5",
        "23.6",
        "23.7",
        "23.8",
        "23.9"
      ]
    },
    {
      "id": 3,
      "tasks": [
        "24.1",
        "24.2",
        "24.3",
        "24.4",
        "24.5",
        "24.6",
        "24.7",
        "24.8",
        "24.9",
        "24.10",
        "25.1",
        "25.2",
        "25.3",
        "25.4",
        "25.5",
        "25.6",
        "25.7",
        "25.8",
        "25.9",
        "25.10"
      ]
    },
    {
      "id": 4,
      "tasks": [
        "26.1",
        "26.2",
        "26.3",
        "26.4",
        "26.5",
        "27.1",
        "27.2",
        "27.3",
        "27.4",
        "27.5",
        "28.1",
        "28.2"
      ]
    }
  ]
}
```
