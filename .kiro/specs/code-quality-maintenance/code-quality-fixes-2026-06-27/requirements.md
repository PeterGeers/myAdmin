# Code Quality Fixes — 2026-06-27

## Summary

Local code quality scan performed on 2026-06-27. CI test results pending (workflow run #28287140559).

## Findings

### 1. Test Failures (CI)

**Backend: 163 failures / 4297 tests (3.8% failure rate)**

| Root Cause                                                                                  | Count | Type          |
| ------------------------------------------------------------------------------------------- | ----- | ------------- |
| `ModuleNotFoundError: No module named 'migrations.backfill_rekeningschema_flags'`           | 34    | Import error  |
| `TemplatePreviewService` missing attributes (`_render_template`, `_validate_*`, `_fetch_*`) | 55    | API drift     |
| Hypothesis flaky (deadline exceeded on CI)                                                  | 5     | Flaky         |
| CORS preflight 403 vs expected 200                                                          | 6     | Assertion     |
| Storage provider routing (`s3_shared` vs `google_drive`)                                    | 8     | Assertion     |
| Provisioning status (`'failed' == 'created'`)                                               | 4     | Assertion     |
| `email_template_service` mock target mismatch                                               | 4     | Mock drift    |
| Budget `KeyError: 'cnt'` in status transitions                                              | 2     | Logic         |
| Missing routes (`/api/reports/trends-data`, `/balance-data`, `/reference-analysis`)         | 3     | Missing route |
| Rate limiter off-by-one (800 vs 801, 700 vs 701)                                            | 2     | Assertion     |
| S3 presigned URL now includes `ResponseContentType`                                         | 1     | API change    |
| `get_last_transactions` Gamma fallback bug                                                  | 1     | Known bug     |
| Path separator `\` vs `/` on CI runner                                                      | 1     | Platform      |
| Pre-commit hook assertion (CI has no hooks)                                                 | 1     | CI env        |
| Other mixed assertion / property failures                                                   | ~36   | Various       |

**Frontend: 25 failures / 2289 tests (1.1% failure rate)**

All 25 failures are in error-handling UI tests (mock-based) expecting specific fallback UI behavior. Files affected:

- `InvoicePreviewModal.test.tsx` (1)
- `STRInvoice.test.tsx` (2)
- `STRPricing.test.tsx` (2)
- `STRProcessor.test.tsx` (2)
- `YearEndClosureSection.test.tsx` (8+)
- Other components (~10)

### 2. File Length Violations

**Critical (>1000 lines): 6 files**

| File                                                    | Lines | Module           |
| ------------------------------------------------------- | ----- | ---------------- |
| `backend/src/validate_pattern/pattern_analyzer_test.py` | 1774  | validate_pattern |
| `backend/src/services/budget_service.py`                | 1398  | services         |
| `backend/src/routes/tenant_admin_users.py`              | 1166  | routes           |
| `backend/src/routes/zzp_routes.py`                      | 1080  | routes           |
| `backend/src/routes/chart_of_accounts_routes.py`        | 1004  | routes           |
| `frontend/src/components/PDFUploadForm.tsx`             | 1074  | components       |

**Warning (500–1000 lines): ~48 files**

Backend (top offenders):

- `services/year_end_service.py` (937), `routes/sysadmin_tenants.py` (930), `banking_processor.py` (920)
- `services/zzp_invoice_service.py` (907), `services/invoice_test_service.py` (859)
- `pdf_decision_handler.py` (844), `file_cleanup_manager.py` (833), `scalability_manager.py` (830)
- `security_audit.py` (790), `routes/tenant_admin_templates.py` (776)
- `xlsx_report_generators.py` (766), `routes/tenant_admin_credentials.py` (765)
- `database.py` (727), `services/cognito_service.py` (717), `services/template_service.py` (714)
- `services/pivot_service.py` (712), `services/tenant_provisioning_service.py` (704)
- `scalability_routes.py` (695), `hybrid_pricing_optimizer.py` (693), `routes/budget_routes.py` (689)
- `services/invoice_email_service.py` (675), `app.py` (626), `services/asset_service.py` (605)
- `routes/str_routes.py` (604), `routes/tenant_admin_storage.py` (601)

Frontend (top offenders):

- `hooks/useBankingProcessor.ts` (935), `TenantAdmin/UserManagement.tsx` (881)
- `SysAdmin/TenantManagement.tsx` (880), `STRProcessor.tsx` (853)
- `ProfitLoss.tsx` (816), `reports/BnbActualsReport.tsx` (792)
- `pages/ZZPInvoiceDetail.tsx` (760), `STRPricing.tsx` (737)
- `TenantAdmin/TemplateManagement/TemplateUpload.tsx` (685)
- `SysAdmin/PipelineResultsPanel.tsx` (656)
- `TenantAdmin/TemplateManagement/TemplateManagement.tsx` (645)
- `pages/BudgetLinesPage.tsx` (633), `pivot/PivotResultTable.tsx` (578)
- `reports/ProfitLossReport.tsx` (573), `BankingProcessor.tsx` (569)
- `App.tsx` (564), `TenantAdmin/AccountModal.tsx` (564)
- `TenantAdmin/StorageTab.tsx` (563), `YearEndClosureSection.tsx` (539)
- `TenantAdmin/ParameterManagement.tsx` (524), `TenantAdmin/CredentialsManagement.tsx` (519)
- `types/budget.ts` (517), `pages/ZZPTimeTracking.tsx` (514)
- `reports/AangifteIbReport.tsx` (508)

### 3. Dead Code

Vulture scan (≥80% confidence): **0 items detected**. Codebase is clean of obvious dead code.

### 4. Missing Test Coverage

**Backend routes without tests (5):**

- `routes/aangifte_ib_routes.py`
- `routes/budget_routes.py`
- `routes/financial_reporting_routes.py`
- `routes/tenant_admin_credentials.py`
- `routes/tenant_admin_templates.py`

**Backend src modules without tests (21):**

- `app.py`, `duplicate_performance_monitor.py`, `duplicate_query_optimizer.py`
- `gunicorn.conf.py`, `pattern_detection.py`, `pattern_scoring.py`
- `pattern_storage_routes.py`, `pdf_ai_extraction.py`, `pdf_decision_handler.py`
- `pdf_parsing_strategies.py`, `scalability_manager.py`, `session_manager.py`
- `shared_limiter.py`, `str_airbnb_parser.py`, `str_booking_parser.py`
- `str_database.py`, `str_utils.py`, `tenant_admin_routes.py`
- `wsgi.py`, `xlsx_report_generators.py`, `xlsx_styles.py`

**Backend services without tests (3):**

- `services/credential_service.py`
- `services/template_html_processor.py`
- `services/template_pdf_renderer.py`

**Frontend pages without tests (11):**

- `BudgetLineModal.tsx`, `BudgetNewVersionModal.tsx`, `BudgetPage.tsx`
- `Callback.tsx`, `CopyBudgetModal.tsx`, `GenerateDraftModal.tsx`
- `Login.tsx`, `NotFound.tsx`, `ServerError.tsx`
- `ServiceUnavailable.tsx`, `Unauthorized.tsx`

**Frontend components without tests (10):**

- `BankingFileUpload.tsx`, `BankingPatternPanel.tsx`, `BankingProcessorTable.tsx`
- `BankingTransactionModal.tsx`, `ErrorBoundary.tsx`, `FilterErrorBoundary.tsx`
- `MissingInvoices.tsx`, `PlotlyChart.tsx`, `STRReports.tsx`
- `ViolinChartExample.tsx`

**Total: 50 modules/components without test coverage**

### 5. Type Safety

**Python (backend services + routes):**

- Total functions: 822
- With return type hints (`->`): 410 (50%)
- Missing return type hints: 412 (50%)

**TypeScript (frontend src, excluding tests):**

- Files with `any` usage: 49
- Total `: any` occurrences: 279
- Explicit `as any` casts: 28

### 6. Stale Documentation

- `Manuals/` directory referenced in project structure but **not found in repository** — likely removed or relocated
- 5 API test files permanently skipped with `TODO: add auth fixtures`
- 1 TODO in `business_pricing_model.py` for BTW rate change logic
- 1 TODO in `tenant_admin_credentials.py` for saving refreshed tokens
- 1 TODO in `test_year_end_integration.py` for test data setup

## Totals

| Category                       | Count                             |
| ------------------------------ | --------------------------------- |
| Test failures: backend (CI)    | 163 of 4297 (3.8%)                |
| Test failures: frontend (CI)   | 25 of 2289 (1.1%)                 |
| File length >1000 (critical)   | 6                                 |
| File length 500–1000 (warning) | ~48                               |
| Dead code                      | 0                                 |
| Missing test coverage          | 50 modules                        |
| Type safety issues             | 691 (412 Python + 279 TypeScript) |
| Stale docs / TODOs             | 8                                 |
