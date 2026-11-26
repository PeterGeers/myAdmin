# Requirements Document

# Full Test Suite Fixes - 2026-11-26 (run #45797012593)

## Introduction

CI-analysis spec (not a feature): captures the failures from one Full Test Suite run and defines the fix tasks, per the prompt-test-suite-results.md runbook. This run is a scheduled nightly Full Test Suite execution on branch main @ 660ad3a8 (the same head as the 11-18 Option B fix merge). The run downloads CI artifacts (backend-test-reports, sam-test-reports, frontend-test-reports, backend-lint-reports) - no local scans.

## Glossary

- **Full_Test_Suite**: The full-test-suite.yml GitHub Actions workflow (backend + SAM + frontend suites + lint/static-analysis), the only automated lint/test gate today (nightly cron + dispatch).
- **Option B**: The redesign that removed the Flask members.scope_dimensions mirror, added SCOPE_CONFIG_SORT_KEY, load_scope_dimensions, and injected ProjectionSync.reader into MembersProjectionReader.get_scope_config.

## Source

GitHub Actions Full Test Suite run #45797012593 (id 45797012593), event schedule on branch main @ 660ad3a8. That head SHA is the post-11-18 Option B fix commit (merge 275439a02); the docs were added via prior commits. The run uses downloaded CI artifacts (backend-test-reports, sam-test-reports, frontend-test-reports, backend-lint-reports) - no local scans.

## Test Results Summary

| Category                     | Count                                            | Notes                                               |
| ---------------------------- | ------------------------------------------------ | ----------------------------------------------------- |
| **Backend test failures**    | **0** (of 7736; 7736 passed, 14 skipped, 1 warning) | 1 warning is FutureWarning from google.api_core, non-blocking |
| **SAM module-plane tests**   | pass (0 fail)                                   | All SAM tests passed                                 |
| **Frontend test failures**   | 0 assertion · 1 error (window teardown)           | 1 unhandled ReferenceError: window is not defined in AangifteIbReport test |
| **Ruff lint errors (backend)**| **0**                                            | All checks passed; clean lint                       |
| **Ruff format violations**   | **0 files**                                      | 346 files already formatted                         |
| **Vulture (dead code)**      | Pass                                            | No dead code found                                   |
| **Frontend ESLint**          | 0 errors, 1148 warnings                           | Report-only; 0 errors, many warnings (unused vars, etc.) |
| **Frontend tsc**             | Many errors (report-only - non-blocking)         | REPORT-ONLY: tsc --noEmit flags many TS type errors |

### CI Job Results

| Job                                | Status |
| ------------------------------------ | ------ |
| Backend Lint & Static Analysis       | Pass |
| Backend Full Test Suite              | Pass (0 failed) |
| SAM Module-Plane Test Suite          | Pass |
| **Frontend Full Test Suite**         | **Red** (1 unhandled error) |
