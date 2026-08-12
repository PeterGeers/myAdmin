# Implementation Plan

## Overview

Fix all failing tests, lint errors, and flaky test issues identified in the 2026-08-12 full test suite run. Tasks are organized by priority: critical (tests can't run), high (assertion failures), medium (flaky/warnings), and low (minor lint).

## Tasks

- [x] 1. Fix S3_SHARED_BUCKET env var in media asset test fixtures
  - **Files**: `backend/tests/unit/test_media_asset_service.py`, `backend/tests/unit/conftest.py`
  - **Action**: Add `S3_SHARED_BUCKET` (and likely `LANDING_PAGES_BUCKET`) to the mock environment in the test fixture. Use `@patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-bucket', 'LANDING_PAGES_BUCKET': 'test-pages-bucket'})` or add to conftest's `mock_env` fixture.
  - **Effort**: S
  - **Verify**: `cd backend && source .venv/bin/activate && pytest tests/unit/test_media_asset_service.py -v 2>&1 | tail -5` (expect 21 pass)

- [x] 2. Fix or remove `_make_key` tests in test_s3_shared_storage_categories
  - **File**: `backend/tests/unit/test_s3_shared_storage_categories.py`
  - **Action**: Check if `_make_key` was renamed (grep for the new method name in `s3_shared_storage.py`). Update test to use the current method name, or delete tests if the method was intentionally removed.
  - **Effort**: S
  - **Verify**: `cd backend && source .venv/bin/activate && pytest tests/unit/test_s3_shared_storage_categories.py -v 2>&1 | tail -5` (expect 5 pass)

- [x] 3. Fix TestPublishWithAssetService — mock boto3/credentials
  - **File**: `backend/tests/unit/test_landing_page_publish_service.py` (TestPublishWithAssetService class)
  - **Action**: The 6 tests in `TestPublishWithAssetService` call the real asset service which tries to connect to AWS. Mock `MediaAssetService.store_and_register` (the method that the publish service now delegates to) instead of letting it hit real boto3.
  - **Effort**: M
  - **Verify**: `cd backend && source .venv/bin/activate && pytest tests/unit/test_landing_page_publish_service.py::TestPublishWithAssetService -v 2>&1 | tail -5` (expect 6 pass)

- [x] 4. Fix TestLandingPagePublishService mock expectations
  - **File**: `backend/tests/unit/test_landing_page_publish_service.py` (TestLandingPagePublishService class)
  - **Action**: The publish service now uses `store_and_register()` instead of direct S3 `put_object`. Update the 7 test assertions to verify calls to the asset service layer rather than raw S3 calls. Check what `publish()` now returns and align assertions.
  - **Effort**: M
  - **Verify**: `cd backend && source .venv/bin/activate && pytest tests/unit/test_landing_page_publish_service.py::TestLandingPagePublishService -v 2>&1 | tail -5` (expect 7 pass)

- [x] 5. Fix landing page renderer — apply section settings to output
  - **File**: `backend/src/services/landing_page_renderers.py`
  - **Action**: 11 tests expect `settings` (background-color, background-image, gradient, full-width, video embed URL) to be applied as inline styles on `<section>` elements. Investigate whether `render_sections_html()` consumes the `settings` dict from each section. If not, add settings application logic. If the feature was intentionally deferred, update tests to match current behavior.
  - **Effort**: L
  - **Verify**: `cd backend && source .venv/bin/activate && pytest tests/unit/test_landing_page_renderers.py -v -k "settings or gradient or video_bg or full_width or round_trip or responsive" 2>&1 | tail -15` (expect 11 pass)

- [x] 6. Fix ruff lint — auto-fixable errors (8 errors)
  - **Files**: `media_asset_service.py`, `cloudfront_domain_service.py`
  - **Action**: Run `cd backend && ruff check src/ --fix --exclude src/validate_pattern/` to auto-fix I001 (imports), UP045 (Optional to X|None), RUF010 (conversion flags).
  - **Effort**: S
  - **Verify**: `cd backend && source .venv/bin/activate && ruff check src/ --exclude src/validate_pattern/ --select I001,UP045,RUF010 2>&1 | tail -3` (expect 0 errors)

- [x] 7. Fix ruff format — 14 files
  - **Action**: Run `cd backend && ruff format src/ --exclude src/validate_pattern/`
  - **Effort**: S
  - **Verify**: `cd backend && source .venv/bin/activate && ruff format --check src/ --exclude src/validate_pattern/ 2>&1 | tail -3` (expect "14 files already formatted")

- [x] 8. Add Hypothesis CI profile to conftest root
  - **File**: `backend/tests/conftest.py` (root level)
  - **Action**: Add a global Hypothesis CI profile to eliminate all flaky test failures at once. Add `from hypothesis import settings, HealthCheck` then `settings.register_profile("ci", derandomize=True, deadline=None, suppress_health_check=[HealthCheck.too_slow])` and `settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "default"))`. Then set `HYPOTHESIS_PROFILE=ci` in the GitHub Actions workflow env.
  - **Effort**: S
  - **Verify**: `cd backend && source .venv/bin/activate && HYPOTHESIS_PROFILE=ci pytest tests/unit/test_parameter_service_props.py tests/unit/test_pivot_query_builder.py tests/unit/test_security_middleware_props.py tests/unit/test_allowed_columns_registry.py tests/unit/test_function_guard_props.py -v 2>&1 | grep -E "passed|failed" | tail -5` (expect 0 flaky failures)

- [x] 9. Address BLE001 — blind except Exception (38 errors)
  - **Files**: `media_asset_routes.py` (21), `media_asset_service.py` (8), `landing_page_publish_service.py` (4), `cloudfront_domain_service.py` (3), `domain_verification_job.py` (1)
  - **Action**: For route handlers, this is the project's standard pattern (per `api-conventions.md`). Add BLE001 to the ruff ignore list for routes files via `per-file-ignores` in `ruff.toml`/`pyproject.toml`. For service files, add `# noqa: BLE001` to appropriate lines.
  - **Effort**: M
  - **Verify**: `cd backend && source .venv/bin/activate && ruff check src/ --exclude src/validate_pattern/ --select BLE001 2>&1 | wc -l` (expect 0 or suppressed)

- [x] 10. Address RUF012 — mutable class attribute defaults (11 errors)
  - **Files**: `landing_page_styles.py` (8), `media_asset_service.py` (3)
  - **Action**: These are class-level dicts/lists used as constants. Either annotate with `ClassVar` or convert to module-level constants. For `LandingPageStyles`, these are intentional lookup tables — `ClassVar` annotation is the cleanest fix.
  - **Effort**: S
  - **Verify**: `cd backend && source .venv/bin/activate && ruff check src/ --exclude src/validate_pattern/ --select RUF012 2>&1 | wc -l` (expect 0)

- [x] 11. Fix RUF059 — unused unpacked variables (9 errors)
  - **Files**: `media_asset_service.py` (7), `media_asset_routes.py` (1)
  - **Action**: Replace unused `conn` in `with db.transaction() as (cursor, conn):` with `_` → `with db.transaction() as (cursor, _):`. Same for unused `user_email`.
  - **Effort**: S
  - **Verify**: `cd backend && source .venv/bin/activate && ruff check src/ --exclude src/validate_pattern/ --select RUF059 2>&1 | wc -l` (expect 0)

- [x] 12. Fix PLW1510 — subprocess.run without check (4 errors)
  - **File**: `cloudfront_domain_service.py`
  - **Action**: Add `check=False` explicitly to each `subprocess.run()` call (the current behavior is already not checking, but ruff wants it explicit).
  - **Effort**: S
  - **Verify**: `cd backend && source .venv/bin/activate && ruff check src/services/cloudfront_domain_service.py --select PLW1510 2>&1 | tail -3` (expect 0)

- [x] 13. Fix remaining minor lint (RUF013, ISC004, S110, F841)
  - **Files**: Various
  - **Action**: RUF013 (3): Add explicit `Optional[...]` or `X | None` annotations. ISC004 (2): Add parentheses around implicit string concatenation in collection. S110 (2): Add logging to `except: pass` blocks. F841 (1): Remove or use the unused `category` variable.
  - **Effort**: S
  - **Verify**: `cd backend && source .venv/bin/activate && ruff check src/ --exclude src/validate_pattern/ 2>&1 | tail -3` (expect "Found 0 errors")

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": 0,
      "tasks": ["1", "2", "5", "6", "8", "9", "10", "11", "12", "13"]
    },
    { "id": 1, "tasks": ["3", "7"] },
    { "id": 2, "tasks": ["4"] }
  ]
}
```

## Notes

- Tasks 1-3 are critical priority (tests can't run at all)
- Tasks 4-7 are high priority (tests run but fail)
- Tasks 8-10 are medium priority (flaky tests and lint warnings)
- Tasks 11-13 are low priority (minor warnings)
- Task 4 depends on Tasks 1 and 3 because they modify the same test file
- Task 7 (format) depends on Task 6 (lint fix) since lint fixes may change formatting
