# Code Quality Fix Tasks — 2026-09-03

Generated from Full Test Suite run #33764293561 (`main`). Do the work on `main` (per user's instruction for this cycle).

**Before starting:** align local ruff to CI's version so counts reproduce (Rule 8):

```bash
pip install ruff==0.16.5
ruff --version   # expect 0.16.5
```

Effort key: S = <30 min, M = 30 min–2 h, L = > 2 h.

---

## Critical — CI-blocking lint failures (Backend Lint & Static Analysis job is red)

- [x] **C1. Decide and apply ruff lint policy for BLE001 + DTZ family (795 of 869 errors).** [L]
  These are pervasive intentional patterns (broad `except Exception` in route handlers; timezone-naive datetimes). Choose ONE strategy per family and apply consistently:
  - Option A (recommended for BLE001): disable `BLE001` project-wide in `backend/ruff.toml` if broad handlers are the deliberate house style.
  - Option B (DTZ005/007/003/011): if the app is intentionally local-time, disable the `DTZ` family in `ruff.toml`; otherwise fix real UTC-sensitive sites (audit_logger, cognito token expiry) and suppress the rest.
  - Do NOT mechanically rewrite 477 call sites without a decision.
  File: `backend/ruff.toml`
  Verify: `ruff check src/ --exclude src/validate_pattern/` (expect 0 errors, or only the non-suppressed intentional set)

- [x] **C2. Auto-fix the 3 mechanically-fixable lint errors.** [S]
  `F401` unused imports (`banking_processor.py:17`, `gunicorn.conf.py:3`) and `I001` unsorted imports.
  ```bash
  ruff check src/ --fix --exclude src/validate_pattern/
  ```
  Verify: `ruff check src/ --select F401,I001 --exclude src/validate_pattern/` (expect 0)

- [x] **C3. Fix ruff format on 5 files.** [S]
  ```bash
  ruff format src/ --exclude src/validate_pattern/
  ```
  Verify: `ruff format --check src/ --exclude src/validate_pattern/` (expect "X files already formatted", 0 to reformat)

- [x] **C4. Resolve remaining manual lint rules after C1.** [M]
  Address whatever survives the C1 policy decision: `TRY002` (32 — raise specific exceptions), `SIM102` (19 — flatten nested ifs), `RUF012` (15 — `ClassVar` on mutable defaults), `S110` (14 — justify or fix try-except-pass), `LOG015` (7 — use module logger not root), `PLW0602` (6), `TRY004` (5), `G201` (5 — use `logging.exception`), `SIM115` (1), `N999` (1 — `gunicorn.conf` module name).
  Verify: `ruff check src/ --exclude src/validate_pattern/` (expect 0)

---

## High — Backend test failures (make the Backend test job robust)

- [x] **H1. Fix S3_SHARED_BUCKET / credentials failures module-wide (32 failures).** [M] ⚠️ 4th cycle — fix ONCE.
  Add an `autouse=True` fixture (or `conftest.py` in the test dir) that sets `S3_SHARED_BUCKET` (and any sibling bucket env vars) and mocks AWS credentials/boto client for the ENTIRE `tests/unit/test_media_asset_service.py` module — not per class. This must cover `TestStoreAndRegister`, `TestLifecycle`, `TestReconcileReferences`, `TestImportLegacyAssets`, `TestImportIntegration`. Also mock the S3 client so `TestReconcileReferences::test_handles_multiple_entity_types` doesn't hit `NoCredentialsError`.
  File: `backend/tests/unit/test_media_asset_service.py` (or new `backend/tests/unit/conftest.py`)
  Verify: `pytest tests/unit/test_media_asset_service.py -v` (expect 0 failures across all 32 previously-failing tests)

- [x] **H2. Stabilize 4 Hypothesis flaky tests.** [S] ⚠️ 5th cycle — apply directly, don't rely on shared profile.
  Add `@settings(derandomize=True, deadline=None)` to each:
  - `tests/unit/test_allowed_columns_registry.py::TestColumnResolutionIntersection::test_with_tenant_restriction`
  - `tests/unit/test_csv_rule_engine_properties.py::TestCsvAggregationCorrectness::test_total_amount_equals_sum_of_nettobedag`
  - `tests/unit/test_parameter_service_props.py::TestScopeLevelDeleteIsolation::test_delete_user_falls_back_to_role`
  - `tests/unit/test_security_middleware_props.py::TestSecurityMiddlewareEnvironmentIndependence::test_health_checks_whitelisted`
  Verify: `pytest tests/unit/test_allowed_columns_registry.py tests/unit/test_csv_rule_engine_properties.py tests/unit/test_parameter_service_props.py tests/unit/test_security_middleware_props.py -v` (expect 0 flaky failures)

- [x] **H3. Fix parameter schema `secret` type assertion (1 failure).** [S]
  Determine if `type: 'secret'` is an intended new param type. If yes, add `'secret'` to the allowed-types tuple in the test. If no, correct the schema entry.
  Files: `backend/tests/unit/test_parameter_schema.py` (and possibly the parameter schema definition)
  Verify: `pytest tests/unit/test_parameter_schema.py::TestSchemaStructureValidity::test_all_params_have_type_field -v` (expect pass)

---

## Medium — file-length refactors & mobile compliance

- [x] **M1. Split `media_asset_service.py` (2984 lines).** [L]
  Extract cohesive concerns (store/register, lifecycle, import, reconcile) into submodules under `services/media_asset/`. Update imports and run the media-asset tests after each extraction (Rule 2).
  Verify: `pytest tests/unit/test_media_asset_service.py -v` passes after each split.

- [x] **M2. Split the other 3 files > 1000 lines.** [L]
  `landing_page_routes.py` (1611), `landing_page_renderers.py` (1118), `media_asset_routes.py` (1023).
  Verify: run each module's tests after splitting.

- [x] **M3. Add responsive wrappers to Medium-severity mobile tables.** [S]
  Wrap tables in `<Box overflowX="auto">` (or `<TableContainer>`):
  - `frontend/src/components/STRInvoice.tsx` (line-items table ~L260)
  - `frontend/src/pages/CheckAccountsPage.tsx` (tables at ~L271, ~L410)
  Verify: `npx vitest run src/components/STRInvoice` and visual check at 375px width.

---

## Low — coverage, type safety, cosmetic mobile, docs

- [x] **L1. Add responsive wrappers to Low-severity mobile tables.** [S]
  `MediaAssetAdminPage.tsx` (2 tables), `InvoiceVatTotals.tsx`, `BudgetNewVersionModal.tsx`, `ContactModal.tsx`. Wrap in `<Box overflowX="auto">`. If any is intentionally desktop-only, add a `// mobile-exempt: <reason>` marker instead.

- [x] **L2. Tighten service-layer TypeScriptl types.** [M]
  Replace `Promise<any>` with typed responses in `productService.ts`, `contactService.ts`, `taxRateService.ts`, `fieldConfigService.ts`. Replace `catch (err: any)` with `catch (err: unknown)` + narrowing.
  Verify: `cd frontend && npx tsc --noEmit` (expect no new errors)

- [x] **L3. Refactor 500–1000 line files opportunistically.** [L]
  35+ files including `backend/src/app.py` (745), `frontend/src/App.tsx` (789), `StorageTab.tsx` (625). Address as touched; not urgent.

- [x] **L4. Pin ruff version to prevent surprise rule expansions.** [S]
  Pin `ruff==0.16.5` in `backend/requirements-test.txt` and the CI workflow so future bumps are deliberate (Rule 8 / Lesson 2).

---

## Final verification (Rule 5 — do not close until CI is green)

```bash
git add -A && git commit -m "code quality fixes 2026-09-03" && git push
gh workflow run "Full Test Suite" --field scope=both --ref main
# Wait for completion, then confirm:
#   Backend Full Test Suite      => success (0 failures)
#   Frontend Full Test Suite     => success (0 failures)
#   Backend Lint & Static Analysis => success (0 ruff errors, 0 format, vulture pass)
```

Only close the spec when all three jobs are green.
