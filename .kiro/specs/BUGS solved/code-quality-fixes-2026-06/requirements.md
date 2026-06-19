# Requirements Document

## Introduction

Automated code quality scan performed on 2026-06 identifying issues across 5 categories: file length violations, missing test coverage, dead code, type safety gaps, and stale documentation. This document captures all findings as actionable requirements.

## Glossary

- **Vulture**: Python dead code detection tool
- **Type hints**: Python type annotations (PEP 484)
- **`any`**: TypeScript escape hatch that disables type checking

## Requirements

---

## Category 1: File Length Violations

**Target: ≤500 lines | Maximum: ≤1000 lines**

### 1.1 Critical (>1000 lines) — 8 files

| #   | File                                               | Lines | Severity    |
| --- | -------------------------------------------------- | ----- | ----------- |
| 1   | `frontend/src/components/BankingProcessor.tsx`     | 2160  | 🔴 Critical |
| 2   | `backend/src/pattern_analyzer.py`                  | 1797  | 🔴 Critical |
| 3   | `backend/src/tenant_admin_routes.py`               | 1589  | 🔴 Critical |
| 4   | `backend/src/pdf_processor.py`                     | 1467  | 🔴 Critical |
| 5   | `backend/src/str_processor.py`                     | 1383  | 🔴 Critical |
| 6   | `backend/src/services/template_preview_service.py` | 1362  | 🔴 Critical |
| 7   | `backend/src/reporting_routes.py`                  | 1140  | 🔴 Critical |
| 8   | `backend/src/xlsx_export.py`                       | 1070  | 🔴 Critical |

### 1.2 Warning (501–1000 lines) — 57 files

**Backend (40 files):**

| #   | File                                                            | Lines |
| --- | --------------------------------------------------------------- | ----- |
| 1   | `backend/src/routes/chart_of_accounts_routes.py`                | 960   |
| 2   | `backend/src/services/year_end_service.py`                      | 925   |
| 3   | `backend/src/banking_processor.py`                              | 910   |
| 4   | `backend/src/routes/tenant_admin_users.py`                      | 910   |
| 5   | `backend/src/routes/zzp_routes.py`                              | 903   |
| 6   | `backend/src/routes/sysadmin_tenants.py`                        | 861   |
| 7   | `backend/src/scalability_manager.py`                            | 828   |
| 8   | `backend/src/file_cleanup_manager.py`                           | 825   |
| 9   | `backend/src/services/zzp_invoice_service.py`                   | 777   |
| 10  | `backend/src/services/banking_service.py`                       | 747   |
| 11  | `backend/src/hybrid_pricing_optimizer.py`                       | 739   |
| 12  | `backend/src/routes/tenant_admin_credentials.py`                | 738   |
| 13  | `backend/src/services/cognito_service.py`                       | 708   |
| 14  | `backend/src/database.py`                                       | 701   |
| 15  | `backend/src/services/template_service.py`                      | 697   |
| 16  | `backend/src/security_audit.py`                                 | 697   |
| 17  | `backend/src/scalability_routes.py`                             | 666   |
| 18  | `backend/src/services/invoice_test_service.py`                  | 653   |
| 19  | `backend/src/services/tenant_provisioning_service.py`           | 635   |
| 20  | `backend/src/duplicate_performance_monitor.py`                  | 621   |
| 21  | `backend/src/services/pivot_service.py`                         | 591   |
| 22  | `backend/src/routes/tenant_admin_storage.py`                    | 585   |
| 23  | `backend/src/audit_logger.py`                                   | 582   |
| 24  | `backend/src/btw_processor.py`                                  | 575   |
| 25  | `backend/src/routes/str_routes.py`                              | 566   |
| 26  | `backend/src/services/invoice_email_service.py`                 | 564   |
| 27  | `backend/src/mutaties_cache.py`                                 | 559   |
| 28  | `backend/src/duplicate_checker.py`                              | 553   |
| 29  | `backend/src/app.py`                                            | 550   |
| 30  | `backend/src/duplicate_query_optimizer.py`                      | 540   |
| 31  | `backend/src/services/ai_template_assistant.py`                 | 538   |
| 32  | `backend/src/report_generators/toeristenbelasting_generator.py` | 538   |
| 33  | `backend/src/services/asset_service.py`                         | 534   |
| 34  | `backend/src/str_invoice_routes.py`                             | 526   |
| 35  | `backend/src/performance_optimizer.py`                          | 525   |
| 36  | `backend/src/error_handlers.py`                                 | 518   |
| 37  | `backend/src/pattern_cache.py`                                  | 505   |
| 38  | `backend/src/validate_pattern/pattern_cache.py`                 | 505   |

**Frontend (17 files):**

| #   | File                                                                            | Lines |
| --- | ------------------------------------------------------------------------------- | ----- |
| 1   | `frontend/src/components/PDFUploadForm.tsx`                                     | 999   |
| 2   | `frontend/src/components/STRProcessor.tsx`                                      | 830   |
| 3   | `frontend/src/components/TenantAdmin/UserManagement.tsx`                        | 827   |
| 4   | `frontend/src/components/SysAdmin/TenantManagement.tsx`                         | 825   |
| 5   | `frontend/src/components/ProfitLoss.tsx`                                        | 789   |
| 6   | `frontend/src/components/reports/BnbActualsReport.tsx`                          | 742   |
| 7   | `frontend/src/components/STRPricing.tsx`                                        | 707   |
| 8   | `frontend/src/pages/ZZPInvoiceDetail.tsx`                                       | 696   |
| 9   | `frontend/src/components/TenantAdmin/TemplateManagement/TemplateUpload.tsx`     | 634   |
| 10  | `frontend/src/components/SysAdmin/PipelineResultsPanel.tsx`                     | 602   |
| 11  | `frontend/src/components/TenantAdmin/TemplateManagement/TemplateManagement.tsx` | 589   |
| 12  | `frontend/src/components/reports/ProfitLossReport.tsx`                          | 538   |
| 13  | `frontend/src/components/pivot/PivotResultTable.tsx`                            | 529   |
| 14  | `frontend/src/components/TenantAdmin/AccountModal.tsx`                          | 528   |
| 15  | `frontend/src/components/TenantAdmin/StorageTab.tsx`                            | 513   |
| 16  | `frontend/src/App.tsx`                                                          | 510   |
| 17  | `frontend/src/components/YearEndClosureSection.tsx`                             | 509   |

---

## Category 2: Dead Code

**Tool: Vulture (Python backend) + manual analysis (frontend)**

### 2.1 Backend Dead Code (vulture, ≥60% confidence)

- **Total findings: 418**
  - Unused functions: 293
  - Unused methods: 89
  - Unused variables: 21
  - Unused attributes: 12
  - Unused classes: 2
  - Unreachable code: 1

**100% confidence findings (guaranteed dead code):**

- `backend/src/services/invoice_email_service.py:298` — unused variable `sender_company`
- `backend/src/services/invoice_email_service.py:310` — unused variable `sender_company`
- `backend/src/str_processor.py:149` — unreachable code after `try`

**Key modules with most dead code (60%+ confidence):**

- `backend/src/scalability_routes.py` — 9 unused functions
- `backend/src/scalability_manager.py` — 5 unused variables + 1 unused function
- `backend/src/performance_optimizer.py` — 10+ unused functions/methods/classes
- `backend/src/duplicate_performance_monitor.py` — 6 unused functions/methods
- `backend/src/duplicate_query_optimizer.py` — 8 unused methods/functions
- `backend/src/security_audit.py` — 6 unused functions
- `backend/src/error_handlers.py` — 5 unused functions/variables
- `backend/src/reporting_routes.py` — 12 unused functions
- `backend/src/routes/banking_routes.py` — 17 unused functions (all route handlers flagged as unused by Flask blueprint registration pattern)
- `backend/src/session_manager.py` — 5 unused methods

**Note:** Flask route handlers decorated with `@blueprint.route()` appear as "unused functions" to vulture because they're registered via decorators, not called directly. These are **false positives** and should be excluded. The truly unused code is primarily in: `performance_optimizer.py`, `scalability_manager.py`, `duplicate_performance_monitor.py`, `duplicate_query_optimizer.py`, `session_manager.py`.

### 2.2 Frontend Unused Exports (20 findings)

| #   | Export                    | File                                 |
| --- | ------------------------- | ------------------------------------ |
| 1   | `decodeJWTPayload`        | `services/authService.ts`            |
| 2   | `getAccount`              | `services/chartOfAccountsService.ts` |
| 3   | `toBackendConfig`         | `services/pivotService.ts`           |
| 4   | `fromBackendConfig`       | `services/pivotService.ts`           |
| 5   | `tenantAwarePut`          | `services/tenantApiService.ts`       |
| 6   | `tenantAwareDelete`       | `services/tenantApiService.ts`       |
| 7   | `createTenantParams`      | `services/tenantApiService.ts`       |
| 8   | `getAvailableYears`       | `services/yearEndClosureService.ts`  |
| 9   | `validateConfiguration`   | `services/yearEndConfigService.ts`   |
| 10  | `getConfiguredPurposes`   | `services/yearEndConfigService.ts`   |
| 11  | `setAccountPurpose`       | `services/yearEndConfigService.ts`   |
| 12  | `getAvailableAccounts`    | `services/yearEndConfigService.ts`   |
| 13  | `getLocaleGreeting`       | `utils/emailVerificationUtils.ts`    |
| 14  | `getErrorMessageByStatus` | `utils/errorHandling.ts`             |
| 15  | `getErrorMessage`         | `utils/errorHandling.ts`             |
| 16  | `filterByVW`              | `utils/financialReportUtils.ts`      |
| 17  | `formatNumber`            | `utils/formatting.ts`                |
| 18  | `isValidUrl`              | `utils/validationHelpers.ts`         |
| 19  | `isValidPhone`            | `utils/validationHelpers.ts`         |
| 20  | `isValidIBAN`             | `utils/validationHelpers.ts`         |

---

## Category 3: Missing Tests

### 3.1 Backend — Missing Unit/API Tests (43 modules)

**Root-level `backend/src/*.py` (24 files without tests):**

1. `actuals_routes.py`
2. `app.py`
3. `aws_notifications.py`
4. `bnb_routes.py`
5. `config.py`
6. `csv_rules.py`
7. `database.py`
8. `duplicate_performance_monitor.py`
9. `duplicate_query_optimizer.py`
10. `error_handlers.py`
11. `google_drive_service.py`
12. `image_ai_processor.py`
13. `migrate_revolut_ref2.py`
14. `mutaties_cache.py`
15. `pattern_analyzer.py`
16. `pattern_cache.py`
17. `pattern_storage_routes.py`
18. `scalability_manager.py`
19. `session_manager.py`
20. `shared_limiter.py`
21. `str_channel_routes.py`
22. `str_database.py`
23. `str_invoice_routes.py`
24. `tenant_admin_routes.py`

**Routes `backend/src/routes/*.py` (10 files without tests):**

1. `banking_routes.py`
2. `cache_routes.py`
3. `contact_routes.py`
4. `product_routes.py`
5. `storage.py`
6. `str_routes.py`
7. `sysadmin_tenants.py`
8. `sysadmin_test_tool.py`
9. `tenant_admin_users.py`
10. `zzp_routes.py`

**Services `backend/src/services/*.py` (9 files without tests):**

1. `banking_service.py`
2. `country_report_service.py`
3. `email_log_service.py`
4. `email_template_service.py`
5. `invoice_test_service.py`
6. `parameter_schema.py`
7. `tenant_language_service.py`
8. `tenant_settings_service.py`
9. `user_language_service.py`

### 3.2 Frontend — Missing Tests

**Components without tests (55 files):**

- 11 root-level components (ErrorBoundary, FilterErrorBoundary, InvoiceGenerator, MissingInvoices, PlotlyChart, STRInvoice, STRPricing, STRReports, UserMenu, ViolinChartExample, YearEndClosureSection)
- 3 Assets components (AssetDetail, AssetForm, AssetList)
- 1 banking component (BankingMutatiesTab)
- 1 common component (AccountSelect)
- 3 help components (FieldHelp, HelpButton, HelpDrawer)
- 6 pivot components (PivotBuilderFilters, PivotBuilderMeasures, PivotBuilderModels, PivotBuilderWithPreview, PivotExportMenu, PivotResultTablePivoted)
- 7 reports components (BnbCountryBookingsReport, BnbFutureReport, BnbReturningGuestsReport, BnbRevenueReport, BnbViolinsReport, BnbYearMonthMatrix, ToeristenbelastingReport)
- 1 settings component (PasskeySettings)
- 1 shared component (EmailLogPanel)
- 10 SysAdmin components (CustomPromptEditor, HealthCheck, ModuleManagement, PipelineResultsPanel, ProvisioningPanel, RoleManagement, SysAdminDashboard, SysAdminPivotDataSources, SystemTaxRates, TenantManagement, VendorHistoryPanel)
- 10 TenantAdmin components (AccountModal, AdvancedTab, ChartOfAccounts, FinancialTab, StorageTab, TenantAdminDashboard, TenantDetails, TenantInfoTab, VATNettingConfig, FieldMappingEditor)
- 1 zzp component (TimeEntryModal)

**Services without tests (18 files):**

1. `assetService.ts`
2. `chartOfAccountsService.ts`
3. `contactService.ts`
4. `debtorService.ts`
5. `fieldConfigService.ts`
6. `invoiceTestToolService.ts`
7. `parameterSchemaService.ts`
8. `parameterService.ts`
9. `productService.ts`
10. `sysadminService.ts`
11. `taxRateService.ts`
12. `templateApi.ts`
13. `tenantAdminApi.ts`
14. `timeTrackingService.ts`
15. `verificationApi.ts`
16. `yearEndClosureService.ts`
17. `yearEndConfigService.ts`
18. `zzpInvoiceService.ts`

---

## Category 4: Type Safety

### 4.1 Backend — Missing Python Type Hints

- **Files with missing return type hints:** 48+ files in `services/` and `routes/`
- **Total functions missing return type hints:** ~508

**Top offenders:**
| # | File | Missing Return | Missing Params |
|---|------|----------------|----------------|
| 1 | `routes/zzp_routes.py` | 30 | 28 |
| 2 | `services/pivot_service.py` | 18 | 21 |
| 3 | `routes/banking_routes.py` | 17 | 17 |
| 4 | `services/year_end_service.py` | 17 | 17 |
| 5 | `routes/str_routes.py` | 16 | 14 |
| 6 | `services/banking_service.py` | 12 | 12 |
| 7 | `services/year_end_config.py` | 12 | 12 |
| 8 | `routes/tenant_admin_users.py` | 11 | 11 |
| 9 | `routes/pivot_routes.py` | 12 | 10 |
| 10 | `services/template_preview_service.py` | 11 | 9 |

### 4.2 Frontend — TypeScript `any` Usage

- **Total `any` usages:** 291 across non-test files
- **Files affected:** 40+

**Top offenders:**
| # | File | Count |
|---|------|-------|
| 1 | `components/TenantAdmin/TemplateManagement/chakraMock.tsx` | 48 |
| 2 | `components/TenantAdmin/ParameterManagement.tsx` | 17 |
| 3 | `services/tenantAdminApi.ts` | 16 |
| 4 | `components/reports/BnbActualsReport.tsx` | 12 |
| 5 | `components/BankingProcessor.tsx` | 10 |
| 6 | `components/PDFUploadForm.tsx` | 9 |
| 7 | `services/zzpInvoiceService.ts` | 9 |
| 8 | `components/TenantAdmin/StorageTab.tsx` | 8 |
| 9 | `services/debtorService.ts` | 7 |
| 10 | `pages/ZZPInvoiceDetail.tsx` | 7 |

---

## Category 5: Stale Documentation

### 5.1 `manualsSysAdm/` Documentation

All files last updated **2026-03-03**. Code referenced has been modified since:

- `duplicate_checker.py` — modified after docs (db-abstraction refactor)
- `duplicate_query_optimizer.py` — modified after docs (db-abstraction refactor + Booking.com import)
- `scalability_manager.py` — modified after docs (Booking.com multi-file import)

**Potentially stale files:**

- `DUPLICATE_DETECTION_INDEXES.md` — references code that has been refactored
- `DUPLICATE_DETECTION_MONITORING.md` — references code that has been refactored
- `DUPLICATE_DETECTION_PERFORMANCE.md` — references code that has been refactored
- `DUPLICATE_DETECTION_TROUBLESHOOTING.md` — references code that has been refactored
- `PERFORMANCE_IMPLEMENTATION_SUMMARY.md` — references `scalability_manager.py` which has changed

### 5.2 Backend Service Documentation (in `backend/src/services/`)

All markdown files last updated **2026-03-03**. May be stale relative to ongoing code changes:

- `AI_TEMPLATE_ASSISTANT_IMPLEMENTATION.md`
- `AI_USAGE_TRACKER_IMPLEMENTATION.md`
- `GOOGLE_DRIVE_UPDATE_SUMMARY.md`
- `IMPLEMENTATION_SUMMARY.md`
- `SAMPLE_DATA_FETCHING_IMPLEMENTATION.md`
- `TEMPLATE_PREVIEW_SERVICE_IMPLEMENTATION.md`
- `TEMPLATE_SERVICE_DOCUMENTATION.md`

---

## Summary

| Category                              | Count           | Severity  |
| ------------------------------------- | --------------- | --------- |
| File length — Critical (>1000)        | 8 files         | 🔴 High   |
| File length — Warning (501–1000)      | 57 files        | 🟡 Medium |
| Dead code — Backend (vulture 60%+)    | 418 findings    | 🟡 Medium |
| Dead code — Frontend unused exports   | 20 findings     | 🟡 Medium |
| Missing tests — Backend               | 43 modules      | 🟡 Medium |
| Missing tests — Frontend components   | 55 files        | 🟡 Medium |
| Missing tests — Frontend services     | 18 files        | 🟡 Medium |
| Type hints — Python functions missing | ~508 functions  | 🟡 Medium |
| TypeScript `any` usage                | 291 occurrences | 🟡 Medium |
| Stale documentation                   | 12 files        | 🟢 Low    |
