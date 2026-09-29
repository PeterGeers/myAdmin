# Code Quality Fixes — 2026-08-03

## Summary

Full test suite run (GitHub Actions run #30856073803) + local code quality scan performed on 2026-08-03.

| Category                                        | Count                  | Δ vs 2026-06-29     |
| ----------------------------------------------- | ---------------------- | ------------------- |
| Backend test failures                           | 6 (of 4923 tests)      | ↓ 97 (was 103/4479) |
| Frontend test failures                          | 0 (of 2338 tests)      | ↓ 23 (was 23/2332)  |
| Backend files > 500 lines                       | 62                     | ↑ 12 (was 50)       |
| Backend files > 1000 lines (critical)           | 1                      | ↑ 1 (was 0)         |
| Frontend source files > 500 lines (excl. tests) | 22                     | ↑ 5 (was 17)        |
| Frontend source files > 1000 lines              | 0                      | — (unchanged)       |
| Dead code (vulture ≥60% confidence)             | 479 items              | New measurement     |
| TypeScript `any` usage (source, excl. mocks)    | ~30 occurrences        | ↓ improved          |
| Backend modules without tests                   | ~34 (estimated stable) | — (stable)          |

---

## Test Failures — Backend (6 failures, 4923 passed, 10 skipped)

### Massive improvement: 103 → 6 failures

All previous root causes (import errors, API drift, route 404s, storage defaults, auth guards) have been resolved.

### Remaining Failures — Grouped by Root Cause

#### 1. Hypothesis Flaky Tests (5 failures)

| Test File                                         | Test Name                                               | Cause                                              |
| ------------------------------------------------- | ------------------------------------------------------- | -------------------------------------------------- |
| `test_allowed_columns_registry.py`                | `test_result_is_subset_of_restriction`                  | Flaky — falsified then passed                      |
| `test_budget_properties.py`                       | `test_copy_preserves_period_mode_and_dimensions`        | Flaky — non-deterministic                          |
| `test_duplicate_performance.py`                   | `test_performance_property_response_time`               | Flaky — timing-dependent (593ms vs 200ms deadline) |
| `test_maintenance/test_flaky_quarantine_props.py` | `test_quarantine_lifecycle`                             | Flaky — falsified then passed                      |
| `test_pdf_processor_properties.py`                | `test_ai_exception_produces_fallback_with_zero_amounts` | Flaky — falsified then passed                      |

**Root cause**: CI timing variability and non-deterministic property test behavior. These need `deadline=None` or `@settings(suppress_health_check=[...])` annotations.

#### 2. Real Bug — ZZP Route Preset Service (1 failure)

| Test File                          | Test Name                               | Cause              |
| ---------------------------------- | --------------------------------------- | ------------------ |
| `test_zzp_route_preset_service.py` | `test_new_route_creates_with_count_one` | `assert None == 1` |

**Root cause**: `increment_usage` returns `None` instead of the new count when creating a new route preset. This is a genuine logic bug in the service layer.

---

## Test Failures — Frontend (0 failures!)

### All 23 previous failures resolved

The ChartOfAccounts, StorageTab, TenantManagement, InvoiceTestTool, and AWS exports issues from 2026-06-29 are all fixed. Frontend test suite is fully green.

---

## File Length Violations

### Critical (>1000 lines): 1 file

| Lines | File                                       | Status                                   |
| ----- | ------------------------------------------ | ---------------------------------------- |
| 1292  | `backend/src/services/zzp_trip_service.py` | **NEW** — grew past 1000 since last scan |

### Backend (62 files over 500 lines)

Top offenders (>750 lines):

| Lines | File                                      |
| ----- | ----------------------------------------- |
| 1292  | `services/zzp_trip_service.py`            |
| 928   | `mutaties_cache.py`                       |
| 880   | `services/zzp_invoice_service.py`         |
| 849   | `services/pivot_service.py`               |
| 804   | `routes/zzp_trip_routes.py`               |
| 802   | `routes/budget_routes.py`                 |
| 798   | `scalability_routes.py`                   |
| 794   | `routes/tenant_admin_users.py`            |
| 792   | `services/budget_mutation_service.py`     |
| 784   | `routes/chart_of_accounts_routes.py`      |
| 768   | `hybrid_pricing_optimizer.py`             |
| 765   | `services/zzp_trip_import_service.py`     |
| 760   | `services/tenant_provisioning_service.py` |

### Frontend Source (22 files over 500 lines, excl. tests)

| Lines | File                                                               |
| ----- | ------------------------------------------------------------------ |
| 648   | `App.tsx`                                                          |
| 596   | `pages/ZZPTrips.tsx`                                               |
| 583   | `components/reports/BnbActualsReport.tsx`                          |
| 578   | `components/pivot/PivotResultTable.tsx`                            |
| 573   | `components/reports/ProfitLossReport.tsx`                          |
| 571   | `components/TenantAdmin/TemplateManagement/TemplateManagement.tsx` |
| 569   | `components/BankingProcessor.tsx`                                  |
| 564   | `components/TenantAdmin/AccountModal.tsx`                          |
| 563   | `components/TenantAdmin/StorageTab.tsx`                            |
| 558   | `hooks/usePDFUpload.ts`                                            |
| 545   | `pages/ZZPInvoiceDetail.tsx`                                       |
| 539   | `components/YearEndClosureSection.tsx`                             |
| 538   | `hooks/useBankingUpload.ts`                                        |
| 533   | `components/STRPricing.tsx`                                        |
| 524   | `components/TenantAdmin/ParameterManagement.tsx`                   |
| 520   | `components/PDFUploadForm.tsx`                                     |
| 519   | `components/TenantAdmin/CredentialsManagement.tsx`                 |
| 517   | `types/budget.ts`                                                  |
| 514   | `pages/ZZPTimeTracking.tsx`                                        |
| 508   | `components/reports/AangifteIbReport.tsx`                          |
| 508   | `components/filters/types.ts`                                      |
| 502   | `services/authService.ts`                                          |

---

## Dead Code

Vulture at ≥80% confidence: **0 items** (suppressed by `backend/vulture_whitelist.py` — 595 lines of whitelisted symbols).

Vulture at ≥60% confidence: **479 items** — almost all are Flask route functions and class methods that appear unused to static analysis because they're registered via decorators or called dynamically. These are largely false positives but the whitelist should be reviewed periodically.

---

## Type Safety

### TypeScript `any` in source code (excluding tests/mocks)

~30 occurrences in real source files:

- `pages/BudgetNewVersionModal.tsx` — 6 (Formik render props)
- `pages/CopyBudgetModal.tsx` — 3 (Formik render props)
- `pages/GenerateDraftModal.tsx` — 3 (Formik render props)
- `pages/BudgetVersionsPage.tsx` — 4 (Formik render props)
- `pages/BudgetLinesPage.tsx` — 1 (catch block)
- `pages/BudgetPage.tsx` — 7 (catch blocks)
- `pages/Login.tsx` — 5 (catch blocks)
- `pages/ZZPTimeTracking.tsx` — 1 (cast)
- `types/parameterSchemaTypes.ts` — 2 (intentional generic)

**Pattern**: Most are Formik `Field` render props (`{ field, meta }: any`) and `catch (err: any)` blocks — both fixable with proper typing.

---

## Comparison with Previous Runs (Trend Analysis)

### 2026-06-27 → 2026-06-29 → 2026-08-03

| Metric               | Jun 27 | Jun 29 | Aug 3    | Trend                |
| -------------------- | ------ | ------ | -------- | -------------------- |
| Backend failures     | 163    | 103    | **6**    | 📉 Excellent         |
| Frontend failures    | 25     | 23     | **0**    | 📉 Resolved          |
| Backend tests total  | 4297   | 4479   | **4923** | 📈 +444 tests        |
| Frontend tests total | 2289   | 2332   | **2338** | 📈 +6 tests          |
| Files >1000 lines    | 6      | 0      | **1**    | ⚠️ Slight regression |
| Backend files >500   | ~48    | 50     | **62**   | 📈 Growing           |
| Frontend files >500  | ~24    | 17     | **22**   | ~ Stable             |

### Recurring Issues

1. **Hypothesis flaky tests** — Present in all 3 scans. These need systematic `deadline=None` or `@settings(derandomize=True)` treatment. They are CI timing artifacts, not real bugs.

2. **File length creep** — Despite refactoring 6 files down from >1000 lines between Jun 27–29, new growth pushed `zzp_trip_service.py` past 1000 again. The total count of >500-line files keeps growing (48→50→62 backend).

3. **Dead code whitelist** — The 595-line whitelist masks whether new dead code is introduced. Consider periodic audit of the whitelist itself.

### Resolved Issues (not recurring)

- ✅ Import errors (34 from missing migration module) — fully resolved
- ✅ `_render_template` API drift (19 failures) — fully resolved
- ✅ Route 404s (17 failures) — fully resolved
- ✅ Storage default change (5 failures) — fully resolved
- ✅ STR auth guards (8 failures) — fully resolved
- ✅ All 23 frontend failures — fully resolved

### Lessons / Recurring Issues

1. **Hypothesis flaky tests are chronic** — 5 flaky failures present in every scan. Action: add `deadline=None` globally or per-test for timing-sensitive property tests.
2. **File length grows organically** — new features add lines faster than refactoring removes them. The ZZP module is the biggest offender (trip_service at 1292 lines).
3. **Formik `any` pattern is systemic** — every Formik `Field` render prop uses `: any`. Consider creating a typed wrapper or utility type.
