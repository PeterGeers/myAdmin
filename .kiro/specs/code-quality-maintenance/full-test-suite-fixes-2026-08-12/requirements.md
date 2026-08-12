# Full Test Suite Fixes — 2026-08-12

## Summary

Full test suite run (GitHub Actions run #31617730915) on 2026-08-12.

| Category               | Count              | Δ vs 2026-08-03      |
| ---------------------- | ------------------ | -------------------- |
| Backend test failures  | 65 (of 5773 tests) | ↑ 59 (was 6/4923)    |
| Frontend test failures | 0 (of 2370 tests)  | — (unchanged, green) |
| Ruff lint errors       | 78                 | New measurement      |
| Ruff format violations | 14 files           | New measurement      |
| Vulture (dead code)    | ✅ Pass            | Improvement          |

---

## Test Failures — Backend (65 failures, 5708 passed, 10 skipped)

### Regression: 6 → 65 failures

Major regression driven by new media asset and landing page features added since last run.

### Failures Grouped by Root Cause

#### 1. Missing Environment Variable — `S3_SHARED_BUCKET` (21 failures)

**File**: `tests/unit/test_media_asset_service.py`

All 21 failures in TestStoreAndRegister, TestLifecycle, TestImportLegacyAssets, and TestImportIntegration raise:

> `ValueError: Environment variable 'S3_SHARED_BUCKET' is not set (required for category 'invoices')`

**Root cause**: Test fixtures don't mock or set the `S3_SHARED_BUCKET` environment variable. The service now validates bucket env vars eagerly.

#### 2. Missing Method — `S3SharedStorage._make_key` (5 failures)

**File**: `tests/unit/test_s3_shared_storage_categories.py`

All 5 tests in TestMakeKeyCategory raise:

> `AttributeError: 'S3SharedStorage' object has no attribute '_make_key'`

**Root cause**: The method was renamed or removed during a refactor. Tests reference a stale API.

#### 3. Landing Page Publish Service — Mock/Assertion Drift (13 failures)

**File**: `tests/unit/test_landing_page_publish_service.py`

- 7 tests in TestLandingPagePublishService: `AssertionError` / `IndexError` — publish flow changed, S3 calls restructured (now uses asset service instead of direct S3)
- 6 tests in TestPublishWithAssetService: `botocore.exceptions.NoCredentialsError` — AWS calls not mocked

**Root cause**: The publish service was refactored to use `MediaAssetService.store_and_register()` instead of direct S3 `put_object`. Old tests mock the wrong layer; new tests don't mock boto3 at all.

#### 4. Landing Page Renderers — Section Settings Not Applied (11 failures)

**File**: `tests/unit/test_landing_page_renderers.py`

Tests expect inline styles (`background-color`, `background-image`, `background: linear-gradient`, `style=""`), video embed URLs (`youtube.com/embed/...`), and full-width layout (`<div class="">`) but rendered HTML lacks all of these.

**Root cause**: Section-level `settings` (background, full-width, gradient) are not being applied to the rendered HTML output. The renderer methods likely need to consume and apply `settings` from the section data.

#### 5. Hypothesis Flaky Tests (4 failures)

| Test File                           | Test Name                                  | Cause                         |
| ----------------------------------- | ------------------------------------------ | ----------------------------- |
| `test_parameter_service_props.py`   | `test_delete_tenant_falls_back_to_system`  | Flaky — falsified then passed |
| `test_pivot_query_builder.py`       | `test_pivot_values_in_params`              | Flaky — falsified then passed |
| `test_security_middleware_props.py` | `test_suspicious_patterns_always_detected` | Flaky — falsified then passed |
| `test_allowed_columns_registry.py`  | `test_with_tenant_restriction`             | Flaky — falsified then passed |

**Root cause**: Missing `@settings(derandomize=True, deadline=None)`. Recurring issue from previous cycles.

#### 6. Function Guard Hypothesis Flaky (1 failure)

**File**: `tests/unit/test_function_guard_props.py`
**Test**: `test_guard_returns_module_error_when_module_inactive`

Same root cause as group 5 — Hypothesis non-determinism.

---

## Test Failures — Frontend (0 failures ✅)

All 2370 tests pass. 167 test files, 12 skipped. Duration: 135.89s.

---

## Lint & Static Analysis

### Ruff Lint — 78 errors (8 auto-fixable, 15 unsafe-fixable)

| Rule    | Count | Description                          | Auto-fixable |
| ------- | ----- | ------------------------------------ | ------------ |
| BLE001  | 38    | Blind `except Exception`             | No           |
| RUF012  | 11    | Mutable default for class attribute  | No           |
| RUF059  | 9     | Unpacked variable never used         | No           |
| PLW1510 | 4     | `subprocess.run` without `check`     | No           |
| UP045   | 3     | Use `X \| None` for annotations      | Yes          |
| RUF013  | 3     | Implicit `Optional`                  | No           |
| I001    | 3     | Unsorted imports                     | Yes          |
| S110    | 2     | `try-except-pass`                    | No           |
| RUF010  | 2     | Use explicit conversion flag         | Yes          |
| ISC004  | 2     | Implicit string concat in collection | No           |
| F841    | 1     | Unused local variable                | No           |

**Files affected**:

- `media_asset_routes.py` (21 errors — mostly BLE001)
- `media_asset_service.py` (20 errors — RUF012, RUF059, BLE001, ISC004, I001, UP045)
- `landing_page_styles.py` (8 errors — RUF012)
- `landing_page_publish_service.py` (6 errors — BLE001, S110)
- `cloudfront_domain_service.py` (7 errors — BLE001, PLW1510, RUF010)
- `domain_verification_job.py` (1 error — BLE001)

### Ruff Format — 14 files need reformatting

### Vulture — ✅ Pass (no dead code detected)

---

## Comparison with 2026-08-03

| Metric              | 2026-08-03 | 2026-08-12 | Trend                                         |
| ------------------- | ---------- | ---------- | --------------------------------------------- |
| Backend failures    | 6          | 65         | ↑ Bad — new features introduced untested code |
| Frontend failures   | 0          | 0          | — Stable                                      |
| Total backend tests | 4923       | 5773       | ↑ +850 tests added                            |
| Vulture             | 479 items  | Pass       | ↑ Fixed                                       |

### Recurring Issues

- **Hypothesis flaky tests**: 4 tests still fail with same pattern as previous cycles. `derandomize=True` + `deadline=None` has not been applied globally.
- **Environment variable drift**: Tests break when services start requiring env vars that fixtures don't provide. Same pattern as the `S3_DEFAULT_STORAGE` issue from 2026-06-29.

### New Issues (Regression from New Features)

- **Media asset service tests** (26 failures): New bucket validation logic added without updating test fixtures
- **Landing page publish tests** (13 failures): Service refactored to use asset service layer, old mocks stale
- **Landing page renderer tests** (11 failures): New settings/styling feature not propagated to renderer output
- **S3 shared storage tests** (5 failures): `_make_key` method removed/renamed without test update

---

## Lessons / Recurring Issues

1. **Env var validation breaks tests** — When adding eager env var validation to services, always update the test conftest/fixtures in the same PR. This is the third time this pattern has caused mass failures.
2. **Hypothesis needs global settings** — Consider adding a `conftest.py` at `tests/` root with `settings.register_profile("ci", derandomize=True, deadline=None)` and `settings.load_profile("ci")`.
3. **Refactoring without test updates** — Landing page publish was refactored but test mocks were left pointing at the old layer. Rule 2 (run affected tests after refactoring) was not followed.
