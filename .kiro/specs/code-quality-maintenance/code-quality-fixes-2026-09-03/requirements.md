# Code Quality Fixes — 2026-09-03

## Summary

Full Test Suite run (GitHub Actions run #33764293561) on `main`, 2026-09-03.

| Category                    | Count               | Δ vs 2026-08-18            |
| --------------------------- | ------------------- | -------------------------- |
| Backend test failures       | 37 (of 5954 tests)  | ↓ 9 (was 46/5918)          |
| Frontend test failures      | 0 (of 2382 tests)   | — (unchanged, green)       |
| Ruff lint errors            | 869                 | ↑ 491 (was 378)            |
| Ruff format violations      | 5 files             | ↓ 6 (was 11 files)         |
| Vulture (dead code)         | ✅ Pass             | — (unchanged, green)       |
| File length > 500 lines     | 89 files            | (not tracked prior)        |
| File length > 1000 lines    | 4 files             | (not tracked prior)        |
| Mobile compliance           | ~6 unwrapped tables | (first tracked this cycle) |
| TypeScript `any` (prod code)| ~30 (service layer) | (first tracked this cycle) |

**CI job result**: Backend Full Test Suite ✅ pass · Frontend Full Test Suite ✅ pass · **Backend Lint & Static Analysis ❌ fail** (this is what turned the run red).

> ⚠️ **Ruff version mismatch**: CI ran **ruff 0.16.5**; local is **ruff 0.16.1**. The 869-error count is CI's. Align local ruff before attempting fixes (Rule 8) or counts will not match.

---

## Test Failures — Backend (37 failures, 5907 passed, 10 skipped)

### Progress: 46 → 37 failures (↓ 9)

Frontend remains fully green. The STR-module failures from 2026-08-18 (booking multi-import, processor, stripe enrichment — 11 failures) appear resolved. But the **S3_SHARED_BUCKET** media-asset failures got worse (15 → 32), and the Hypothesis flaky tests persist.

### Failures Grouped by Root Cause

#### 1. Missing Environment Variable — `S3_SHARED_BUCKET` / credentials (32 failures) ⚠️ RECURRING — 4th cycle

**File**: `tests/unit/test_media_asset_service.py`

- 31 failures raise `ValueError: Environment variable 'S3_SHARED_BUCKET' is not set (required for category 'invoices'|'branding')`
- 1 failure (`TestReconcileReferences::test_handles_multiple_entity_types`) raises `botocore.exceptions.NoCredentialsError: Unable to locate credentials`

**Affected test classes**: `TestStoreAndRegister` (11), `TestLifecycle` (5), `TestReconcileReferences` (1), `TestImportLegacyAssets` (12), `TestImportIntegration` (3).

**Root cause**: The env-var mock / storage-resolver mock is still not applied at the whole-module level. This is now the **4th consecutive cycle** this pattern recurs (2026-06-29 `S3_DEFAULT_STORAGE`, then `S3_SHARED_BUCKET` in 08-12, 08-18, now 09-03). Worse this cycle: the store/lifecycle classes that were "fixed" on 08-18 are failing again (15 → 32), indicating a regression — likely a shared fixture/conftest change that removed the env var, or the resolver now validates eagerly for more categories.

#### 2. Hypothesis Flaky Tests (4 failures) ⚠️ RECURRING — 5th cycle

| Test File                            | Test Name                              | Cause                                       |
| ------------------------------------ | -------------------------------------- | ------------------------------------------- |
| `test_allowed_columns_registry.py`   | `test_with_tenant_restriction`         | Flaky — falsified on first call then passed |
| `test_csv_rule_engine_properties.py` | `test_total_amount_equals_sum_of_nettobedag` | Flaky — unreliable timings           |
| `test_parameter_service_props.py`    | `test_delete_user_falls_back_to_role`  | Flaky — 392ms > 200ms deadline, then 0.5ms  |
| `test_security_middleware_props.py`  | `test_health_checks_whitelisted`       | Flaky — 452ms > 200ms deadline, then 5.6ms  |

**Root cause**: Missing `@settings(derandomize=True, deadline=None)`. CI runner timing variability trips the 200ms deadline. `test_security_middleware_props.py` recurs from prior cycles — the CI Hypothesis profile still isn't covering these. Per Rule 11, apply BOTH `derandomize=True` AND `deadline=None` directly on the tests.

#### 3. Parameter Schema — New `secret` type not allowed (1 failure) 🆕

**File**: `tests/unit/test_parameter_schema.py`
**Test**: `TestSchemaStructureValidity::test_all_params_have_type_field`
**Error**: `AssertionError: assert 'secret' in ('string', 'number', 'json')`

**Root cause**: A parameter with `type: 'secret'` was added to the schema, but the test's allowed-types tuple was not updated to include `'secret'`. Classic "changed a default/enum without updating the test" (Rule 4). Confirm whether `secret` is an intended new type (update the test) or a mistake (fix the schema).

---

## Test Failures — Frontend (0 failures ✅)

All 2370 tests pass (167 files, 12 skipped). Duration ~141s.

---

## Lint & Static Analysis (Backend Lint job — ❌ FAIL, CI-blocking)

### Ruff Lint — 869 errors

| Rule    | Count | Description                                                  | Auto-fixable |
| ------- | ----- | ------------------------------------------------------------ | ------------ |
| BLE001  | 477   | Do not catch blind exception `Exception`                     | No           |
| DTZ005  | 215   | `datetime.now()` without `tz` argument                       | No           |
| DTZ007  | 34    | Naive datetime from `strptime()` without `%z`                | No           |
| TRY002  | 32    | Create your own exception (avoid raising bare `Exception`)   | No           |
| DTZ003  | 22    | `datetime.utcnow()` used                                     | No           |
| SIM102  | 19    | Nested `if` → single `if`                                    | No           |
| RUF012  | 15    | Mutable class default needs `ClassVar`                       | No           |
| S110    | 14    | `try-except-pass`                                            | No           |
| DTZ011  | 12    | `date.today()` used                                          | No           |
| LOG015  | 7     | `error()`/`warning()` call on root logger                    | No           |
| PLW0602 | 6     | `global` used but no assignment                              | No           |
| TRY004  | 5     | Prefer `TypeError` for wrong type                            | No           |
| G201    | 5     | Use `logging.exception` instead of `error(..., exc_info=True)`| No          |
| F401    | 3     | Imported but unused                                          | Yes ✅       |
| SIM115  | 1     | Use context manager for opening files                        | No           |
| N999    | 1     | Invalid module name (`gunicorn.conf`)                        | No           |
| I001    | 1     | Unsorted imports                                             | Yes ✅       |

Only **3 auto-fixable** with `--fix`. The dominant categories are `BLE001` (blind `except Exception`) and the `DTZ*` family (timezone-naive datetimes) — together ~795 of 869. These are pervasive across the codebase and mostly represent intentional patterns (broad error handling in route handlers, local-time reporting). Decision needed: bulk-suppress via config (disable `BLE001`/`DTZ*` in `ruff.toml`) vs. mechanical fixes vs. `--add-noqa`.

> The 378 → 869 jump is driven by the ruff version bump (0.16.1 → 0.16.5 in CI) enabling/expanding these rule families. On 08-18 most errors were RUF100 unused-noqa cleanup; that has flipped entirely — RUF100 is gone and BLE001/DTZ now dominate. This is the "version upgrade introduces hundreds of new rules" scenario from Rule 8.

### Ruff Format — 5 files need reformatting (down from 11)

`ruff format src/` will fix. (File names not surfaced by CI report — run locally to identify.)

### Vulture — ✅ Pass (no dead code at confidence ≥ 80; local re-run confirmed 0 findings)

---

## Local Code Quality Scan

### File Length (89 files > 500 lines; 4 > 1000 lines)

**Critical (> 1000 lines):**

| File                                        | Lines |
| ------------------------------------------- | ----- |
| `backend/src/services/media_asset_service.py` | 2984  |
| `backend/src/routes/landing_page_routes.py`   | 1611  |
| `backend/src/services/landing_page_renderers.py` | 1118 |
| `backend/src/routes/media_asset_routes.py`    | 1023  |

**Notable 500–1000 line files** (35+ total): `backend/src/app.py` (745), `frontend/src/App.tsx` (789), `frontend/src/components/TenantAdmin/StorageTab.tsx` (625), plus many route/service modules. Full list obtainable via the file-length scan command in prompt.md Step 4.

### Dead Code — Vulture ✅ 0 findings (confidence ≥ 80).

### Type Safety — TypeScript `any` (~30 in production code)

Concentrated in the **service layer** returning `Promise<any>`:

- `frontend/src/services/productService.ts` (6 functions)
- `frontend/src/services/contactService.ts` (6 functions)
- `frontend/src/services/taxRateService.ts` (3 functions)
- `frontend/src/services/fieldConfigService.ts` (getFieldConfig)

Plus scattered `catch (err: any)` clauses and `as any` casts in `BudgetNewVersionModal.tsx`, `ZZPTimeTracking.tsx`, `ViolinChartExample.tsx`. Backend Python type-hint gaps not separately enumerated this cycle (ruff `ANN` rules not enabled).

### Mobile Compliance (~6 tables without responsive wrapper)

Overall the frontend is **broadly mobile-ready**: `index.html` has the correct `<meta name="viewport" ...>`, and Chakra responsive patterns (`{ base, md }` props, `display={{ base, md }}` mobile/desktop toggles, `useBreakpointValue`, mobile card fallbacks) are used widely across pages.

**Violations** — production tables rendered without an `overflowX`/`TableContainer` wrapper or mobile card fallback (horizontal-overflow risk on small screens):

| File                                             | Note                                             | Severity |
| ------------------------------------------------ | ------------------------------------------------ | -------- |
| `frontend/src/pages/MediaAssetAdminPage.tsx`     | 2 tables (Storage by Category, Top Orphans)      | Low (admin, narrow cols) |
| `frontend/src/components/zzp/InvoiceVatTotals.tsx` | VAT summary table, no wrapper                   | Low      |
| `frontend/src/components/STRInvoice.tsx`         | line-items table, no wrapper                     | Medium   |
| `frontend/src/pages/BudgetNewVersionModal.tsx`   | proposed-lines table in modal                    | Low      |
| `frontend/src/pages/CheckAccountsPage.tsx`       | nested tables (lines 271, 410) lack wrapper      | Medium   |
| `frontend/src/components/zzp/ContactModal.tsx`   | table inside modal, no wrapper                   | Low      |

No `mobile-exempt` markers found in the codebase, so none of the above are exempt. One hover-only style (`GenericFilter.tsx`) uses a Chakra `_hover` token, which is cosmetic and has a normal tap/focus state — not a violation.

---

## Comparison with 2026-08-18

| Metric              | 2026-08-18 | 2026-09-03 | Trend                                   |
| ------------------- | ---------- | ---------- | --------------------------------------- |
| Backend failures    | 46         | 37         | ↓ Good — 9 fewer                        |
| Frontend failures   | 0          | 0          | — Stable                                |
| Total backend tests | 5918       | 5954       | ↑ +36 tests                             |
| Ruff lint errors    | 378        | 869        | ↑ Bad — ruff 0.16.5 expanded BLE/DTZ    |
| Ruff format files   | 11         | 5          | ↓ Good — 6 fewer                        |
| Vulture             | Pass       | Pass       | — Stable                                |

### Recurring Issues

1. **S3_SHARED_BUCKET env var (4th cycle, now REGRESSED)** — Not only unfixed, it went from 15 → 32 failures. The store/lifecycle classes marked fixed on 08-18 are broken again. This needs a module-level `conftest`/fixture fix (autouse) rather than per-class patches, which keep slipping.
2. **Hypothesis flaky tests (5th cycle)** — `test_security_middleware_props.py` recurs yet again. The shared CI profile approach has repeatedly failed to cover these. Apply `@settings(derandomize=True, deadline=None)` directly on each of the 4 tests.

### Fixed from Previous Run

- ✅ STR booking multi-import tuple mismatch (3 → 0)
- ✅ STR processor missing test file (3 → 0)
- ✅ STR stripe enrichment mock config (5 → 0)
- ✅ Invoice test tool props assertion (1 → 0)
- ✅ Ruff format: 11 → 5 files

### New / Regressed

- 🔺 S3_SHARED_BUCKET media-asset failures regressed 15 → 32
- 🆕 Parameter schema `secret` type not in allowed tuple (1)
- 🔺 Ruff lint 378 → 869 (ruff version bump enabling BLE001/DTZ families)

---

## Lessons / Recurring Issues

1. **Stop patching S3 env vars per-class — fix it once, module-wide.** Four cycles of the same failure. The correct fix is an `autouse` fixture (or `conftest.py`) that sets `S3_SHARED_BUCKET` (and mocks credentials) for the entire `test_media_asset_service.py` module, so newly-added test classes inherit it automatically. Per-class `monkeypatch.setenv` keeps regressing.
2. **A ruff version bump is a breaking event.** CI upgraded 0.16.1 → 0.16.5 and lint errors more than doubled. Pin ruff to a fixed version in both CI and `requirements-test.txt` so upgrades are deliberate. Before fixing, align local ruff to CI's version (Rule 8) or the 869 count won't reproduce locally.
3. **BLE001/DTZ are policy decisions, not bugs.** 795 of 869 errors are blind-except and naive-datetime patterns that are largely intentional. Decide policy once (config-level disable, or targeted `noqa`) rather than mechanically rewriting hundreds of call sites.
4. **The lint job — not tests — is what fails CI now.** Backend and frontend tests both pass; the red X is entirely the Backend Lint & Static Analysis job. Getting CI green primarily means resolving the ruff lint/format failures.
5. **Mobile-first is the default (new this cycle).** Six tables ship without responsive wrappers. New table-rendering components must be wrapped in `<Box overflowX="auto">`/`<TableContainer>` or given a mobile card fallback, unless explicitly marked `mobile-exempt`.
