# Code Quality Fixes — 2026-06-29

## Summary

Full test suite run (GitHub Actions) + local code quality scan performed on 2026-06-29.

| Category                                           | Count                    |
| -------------------------------------------------- | ------------------------ |
| Backend test failures                              | 103 (of 4479 tests)      |
| Frontend test failures                             | 23 (of 2332 tests)       |
| Backend files > 500 lines                          | 50                       |
| Backend files > 1000 lines                         | 0                        |
| Frontend source files > 500 lines (excl. tests)    | 17                       |
| Frontend source files > 1000 lines (excl. tests)   | 0                        |
| Backend modules without tests                      | 34                       |
| Frontend components/pages without tests            | 21                       |
| TypeScript `any` usage (files with 4+ occurrences) | 30 files                 |
| Python functions missing return type hints         | ~60+ (services + routes) |

---

## Test Failures — Backend (103 failures, 0 errors, 10 skipped)

### Grouped by Root Cause

#### 1. Import Error — Missing module (34 failures)

- **File**: `test_backfill_rekeningschema_flags.py` (34 tests)
- **Cause**: `ModuleNotFoundError: No module named 'migrations.backfill_rekeningschema_flags'`
- **Root cause**: Migration module removed or renamed without updating/removing corresponding tests

#### 2. API/Attribute Error — `_render_template` removed (19 failures)

- **File**: `test_template_rendering.py` (17 tests), `test_template_rendering.TestFieldMappings` (2 tests)
- **Cause**: `AttributeError: 'TemplatePreviewService' object has no attribute '_render_template'`
- **Root cause**: Internal method renamed/refactored, tests not updated

#### 3. Route Not Found — 404 instead of expected response (17 failures)

- **Files**: `test_delete_tenant_template.py` (6), `test_download_default_template.py` (5), `test_tenant_admin_per_tenant_roles.py` (2), `test_tenant_admin_users_routes.py` (3), `test_valid_template_types.py` (1)
- **Cause**: Routes returning 404 — endpoints removed or URL patterns changed
- **Root cause**: Route registration changed, tests reference stale URL paths

#### 4. Storage Provider Default Changed (5 failures)

- **Files**: `test_storage_resolver.py` (4), `test_zzp_invoice_service.py` (1)
- **Cause**: Default storage changed from `google_drive` to `s3_shared`
- **Root cause**: Intentional default change, tests not updated

#### 5. STR Channel Auth/Guard Issue (8 failures)

- **File**: `test_str_channel_routes_fix.py` (8 tests)
- **Cause**: Getting 403 Forbidden instead of expected responses
- **Root cause**: Auth guard or module guard added to STR routes, test fixtures don't satisfy new requirements

#### 6. Banking Processor Refactored (4 failures)

- **Files**: `test_bug_condition_bank_lookup.py` (2), `test_preservation_bank_lookup.py` (2)
- **Cause**: `AttributeError: 'BankingProcessor' object has no attribute '_checks'`
- **Root cause**: Internal `_checks` attribute renamed or restructured

#### 7. Output Service / S3 Refactored (4 failures)

- **File**: `test_output_service.py` (4 tests)
- **Cause**: `'Mock' object is not subscriptable` and assertion on S3 bucket name
- **Root cause**: Google Drive upload path replaced with S3, mocks not updated

#### 8. Banking Balance Closure Logic (3 failures)

- **File**: `test_banking_balance_closure.py` (3 tests)
- **Cause**: SQL assertions fail — date bounds not applied as expected
- **Root cause**: Query logic changed, tests assert old SQL patterns

#### 9. VRBO Processor Status Logic (2 failures)

- **File**: `test_vrbo_processor.py` (2 tests)
- **Cause**: `'realised' != 'planned'` — future bookings classified as realised
- **Root cause**: Booking status classification logic changed

#### 10. XLSX Export / Google Drive (2 failures)

- **File**: `test_xlsx_export.py` (2 tests)
- **Cause**: Drive service returns None; download returns False
- **Root cause**: Google Drive integration changed/removed

#### 11. Flaky Hypothesis Tests (5 failures)

- **Files**: `test_function_guard_props.py` (1), `test_invoice_service_properties.py` (1), `test_parameter_admin_routes.py` (1), `test_security_middleware_props.py` (1), `test_output_service.py` (overlap)
- **Cause**: `hypothesis.errors.Flaky`
- **Root cause**: Non-deterministic test behavior, possible shared state

---

## Test Failures — Frontend (23 failures)

### Grouped by Root Cause

#### 1. ChartOfAccounts Component Rewrite (8 failures)

- **File**: `ChartOfAccounts.test.tsx`
- **Cause**: Unable to find elements by text — component rendering changed
- **Root cause**: Component UI refactored, test selectors outdated

#### 2. StorageTab Component Changed (8 failures)

- **File**: `StorageTab.test.tsx`
- **Cause**: Mock function not called — component initialization flow changed
- **Root cause**: Component no longer calls expected service functions on mount

#### 3. TenantManagement Multiple Buttons (3 failures)

- **File**: `TenantManagement.test.tsx`
- **Cause**: "Found multiple elements with the role button"
- **Root cause**: UI added duplicate action buttons, test selectors too broad

#### 4. InvoiceTestTool Validation Changed (3 failures)

- **File**: `InvoiceTestTool.test.tsx` + `InvoiceTestTool.prop.test.tsx`
- **Cause**: Validation regex/messages changed, placeholder text changed
- **Root cause**: Vendor name validation rules updated, tests not aligned

#### 5. AWS Exports Config Test (1 failure)

- **File**: `aws-exports.test.ts`
- **Cause**: Client ID format doesn't match expected regex
- **Root cause**: Test assumes production format, CI uses test values

---

## File Length Violations (> 500 lines)

### Backend (50 files over 500 lines, 0 over 1000)

| Lines | File                                                            |
| ----- | --------------------------------------------------------------- |
| 961   | `backend/src/routes/zzp_routes.py`                              |
| 859   | `backend/src/services/invoice_test_service.py`                  |
| 850   | `backend/src/routes/chart_of_accounts_routes.py`                |
| 788   | `backend/src/routes/tenant_admin_credentials.py`                |
| 777   | `backend/src/routes/tenant_admin_templates.py`                  |
| 764   | `backend/src/services/banking_service.py`                       |
| 762   | `backend/src/services/budget_mutation_service.py`               |
| 731   | `backend/src/routes/tenant_admin_users.py`                      |
| 717   | `backend/src/services/cognito_service.py`                       |
| 715   | `backend/src/services/zzp_invoice_service.py`                   |
| 714   | `backend/src/services/template_service.py`                      |
| 712   | `backend/src/services/pivot_service.py`                         |
| 704   | `backend/src/services/tenant_provisioning_service.py`           |
| 703   | `backend/src/services/budget_query_service.py`                  |
| 695   | `backend/src/scalability_routes.py`                             |
| 693   | `backend/src/hybrid_pricing_optimizer.py`                       |
| 689   | `backend/src/routes/budget_routes.py`                           |
| 675   | `backend/src/services/invoice_email_service.py`                 |
| 640   | `backend/src/routes/sysadmin_tenants.py`                        |
| 630   | `backend/src/app.py`                                            |
| 605   | `backend/src/services/asset_service.py`                         |
| 604   | `backend/src/routes/str_routes.py`                              |
| 602   | `backend/src/routes/tenant_admin_storage.py`                    |
| 591   | `backend/src/pattern_detection.py`                              |
| 588   | `backend/src/audit_logger.py`                                   |
| 587   | `backend/src/xlsx_report_generators.py`                         |
| 581   | `backend/src/mutaties_cache.py`                                 |
| 579   | `backend/src/pattern_analyzer.py`                               |
| 578   | `backend/src/btw_processor.py`                                  |
| 570   | `backend/src/services/template_preview_service.py`              |
| 565   | `backend/src/report_generators/toeristenbelasting_generator.py` |
| 564   | `backend/src/str_invoice_routes.py`                             |
| 564   | `backend/src/auth/cognito_utils.py`                             |
| 563   | `backend/src/duplicate_checker.py`                              |
| 557   | `backend/src/services/template_pdf_renderer.py`                 |
| 557   | `backend/src/database.py`                                       |
| 553   | `backend/src/services/ai_template_assistant.py`                 |
| 546   | `backend/src/banking_checks.py`                                 |
| 534   | `backend/src/pdf_decision_helpers.py`                           |
| 528   | `backend/src/services/email_verification_service.py`            |
| 514   | `backend/src/services/parameter_service.py`                     |
| 514   | `backend/src/pattern_cache.py`                                  |
| 512   | `backend/src/routes/banking_routes.py`                          |
| 509   | `backend/src/security_audit.py`                                 |
| 506   | `backend/src/report_generators/btw_aangifte_generator.py`       |
| 504   | `backend/src/pattern_scoring.py`                                |
| 504   | `backend/src/bnb_routes.py`                                     |
| 503   | `backend/src/routes/aangifte_ib_routes.py`                      |
| 502   | `backend/src/duplicate_performance_monitor.py`                  |

### Frontend Source (excl. test files, 17 files over 500 lines)

| Lines | File                                                                            |
| ----- | ------------------------------------------------------------------------------- |
| 656   | `frontend/src/components/SysAdmin/PipelineResultsPanel.tsx`                     |
| 645   | `frontend/src/components/TenantAdmin/TemplateManagement/TemplateManagement.tsx` |
| 593   | `frontend/src/pages/BudgetTemplatesPage.tsx`                                    |
| 581   | `frontend/src/components/reports/BnbActualsReport.tsx`                          |
| 578   | `frontend/src/components/pivot/PivotResultTable.tsx`                            |
| 573   | `frontend/src/components/reports/ProfitLossReport.tsx`                          |
| 569   | `frontend/src/components/BankingProcessor.tsx`                                  |
| 564   | `frontend/src/components/TenantAdmin/AccountModal.tsx`                          |
| 564   | `frontend/src/App.tsx`                                                          |
| 563   | `frontend/src/components/TenantAdmin/StorageTab.tsx`                            |
| 542   | `frontend/src/pages/ZZPInvoiceDetail.tsx`                                       |
| 539   | `frontend/src/components/YearEndClosureSection.tsx`                             |
| 538   | `frontend/src/hooks/useBankingUpload.ts`                                        |
| 533   | `frontend/src/components/STRPricing.tsx`                                        |
| 524   | `frontend/src/components/TenantAdmin/ParameterManagement.tsx`                   |
| 519   | `frontend/src/components/TenantAdmin/CredentialsManagement.tsx`                 |
| 519   | `frontend/src/components/PDFUploadForm.tsx`                                     |

---

## Missing Test Coverage

### Backend — 34 modules without tests

**`backend/src/` root (23 modules)**:
banking_checks, database_banking_queries, duplicate_performance_monitor, duplicate_query_optimizer, file_cleanup_actions, pattern_scoring, pattern_storage_routes, pdf_decision_handler, pdf_decision_helpers, pdf_parsing_strategies, scalability_manager, scalability_workers, security_validators, session_manager, shared_limiter, str_airbnb_parser, str_booking_parser, str_database, str_utils, tenant_admin_routes, xlsx_download_helpers, xlsx_report_generators, xlsx_styles

**`backend/src/services/` (8 modules)**:
budget_mutation_service, budget_query_service, chart_of_accounts_io_service, credential_service, template_html_processor, template_pdf_renderer, year_end_journal_entries, zzp_invoice_delivery

**`backend/src/routes/` (3 modules)**:
sysadmin_tenant_actions, tenant_admin_roles, zzp_time_routes

### Frontend — 21 components/pages without tests

**Components (12)**:
BankingFileUpload, BankingPatternPanel, BankingTransactionModal, FilterErrorBoundary, MissingInvoices, PlotlyChart, ProfitLossChartPanel, ProfitLossFilterPanel, STRBookingTable, STRPricingTable, STRSummaryPanel, ViolinChartExample

**Pages (9)**:
BudgetLineModal, BudgetNewVersionModal, Callback, CopyBudgetModal, GenerateDraftModal, NotFound, ServerError, ServiceUnavailable, Unauthorized

---

## Type Safety Issues

### TypeScript `any` Usage (30 files with 4+ occurrences)

Top offenders (excluding test/mock files):

- `pivotTreeBuilder.ts` — 7 occurrences (generic data structures)
- `PivotBuilderFilters.tsx` — 7 occurrences
- `timeTrackingService.ts` — 5 occurrences (all return types)
- `BudgetNewVersionModal.tsx` — 6 occurrences (Formik field render props)
- `BudgetTemplatesPage.tsx` — 5 occurrences (Formik field render props)
- `csvExport.ts` — 4 occurrences (generic utility)

### Python Missing Return Type Hints

~60+ functions across services and routes lack `-> ReturnType` annotations. Most are `__init__` methods (acceptable) but many service/route functions also lack them.

---

## Stale Documentation

Not fully scanned (requires manual review), but known concerns:

- `manualsSysAdm/` references Google Drive workflows that may be partially replaced by S3
- Test failures confirm storage default changed from `google_drive` to `s3_shared`
