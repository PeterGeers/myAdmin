# Implementation Plan

## Overview

Fix all failing tests, lint errors, and flaky test issues identified in the 2026-08-18 full test suite run. Tasks are organized by priority: critical (tests can't run), high (assertion failures + blocking lint), medium (flaky/non-deterministic), and low (format-only).

## Tasks

- [x] 1. Fix S3_SHARED_BUCKET env var for import test classes
  - **File**: `backend/tests/unit/test_media_asset_service.py`
  - **Action**: Add `@patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-bucket'})` to `TestImportLegacyAssets` and `TestImportIntegration` classes (or their setUp methods). Check if a shared conftest fixture already sets this for other classes in the same file and apply it consistently to ALL classes.
  - **Effort**: S
  - **Priority**: Critical
  - **Verify**: `cd backend && source .venv/bin/activate && pytest tests/unit/test_media_asset_service.py::TestImportLegacyAssets tests/unit/test_media_asset_service.py::TestImportIntegration -v 2>&1 | tail -5`
  - **Fixes**: 15 failures

- [x] 2. Fix STR booking multi-import tuple shape (2-tuple → 3-tuple)
  - **File**: `backend/tests/unit/test_str_booking_multi_import.py`
  - **Action**: The delete scope strategy now returns 3-tuples `(channel, listing, subcategory)`. Update test assertions to expect 3-tuples. Check `TestProperty6ScopedOverwriteInvariant::test_delete_only_imported_pairs` — it checks `('booking.com', 'Green Studio')` but service returns `('booking.com', 'Green Studio', '')`. Update assertions and the helper that builds expected pairs.
  - **Effort**: S
  - **Priority**: High
  - **Verify**: `cd backend && source .venv/bin/activate && pytest tests/unit/test_str_booking_multi_import.py -v 2>&1 | tail -5`
  - **Fixes**: 3 failures

- [x] 3. Fix STR processor missing test fixture file
  - **File**: `backend/tests/unit/test_str_processor.py`
  - **Action**: Tests try to open `test.xlsx` from the filesystem. Either: (a) create a minimal test fixture at the expected path and commit it, or (b) mock the file read with `unittest.mock.patch('builtins.open', ...)` or mock the pandas read function. Check how other STR processor tests handle file fixtures.
  - **Effort**: S
  - **Priority**: High
  - **Verify**: `cd backend && source .venv/bin/activate && pytest tests/unit/test_str_processor.py::TestSTRProcessor::test_process_direct_success tests/unit/test_str_processor.py::TestSTRProcessor::test_process_direct_vrbo_channel tests/unit/test_str_processor.py::TestSTRProcessor::test_process_direct_skip_non_reservation -v 2>&1 | tail -5`
  - **Fixes**: 3 failures

- [x] 4. Fix STR Stripe enrichment mock configuration
  - **File**: `backend/tests/unit/test_str_stripe_enrichment.py`
  - **Action**: The `PaymentIntent` mock auto-creates nested attributes. Fix by either: (a) using `spec=True` on the MagicMock to prevent auto-creation, or (b) explicitly setting `mock_pi.shipping.phone = '+31687654321'` and `mock_pi.shipping.address.country = 'DE'` etc., or (c) setting `mock_pi.shipping = None` for no-data tests. Check what attributes the `extract_customer_data()` function accesses and ensure mocks return the correct values (not nested MagicMocks).
  - **Effort**: M
  - **Priority**: High
  - **Verify**: `cd backend && source .venv/bin/activate && pytest tests/unit/test_str_stripe_enrichment.py::TestExtractCustomerData -v 2>&1 | tail -5`
  - **Fixes**: 5 failures

- [x] 5. Fix Hypothesis flaky tests — targeted settings
  - **Files**: `backend/tests/unit/test_security_middleware_props.py`, `backend/tests/unit/test_tenant_function_routes_props.py`
  - **Action**: Add `@settings(derandomize=True, deadline=None)` directly to `test_suspicious_patterns_always_detected` and `test_get_returns_exactly_registry_functions_with_correct_state`. Also verify the CI Hypothesis profile from task 8 (2026-08-12) is being loaded — check if `conftest.py` at the test root has `settings.load_profile("ci")`.
  - **Effort**: S
  - **Priority**: Medium
  - **Verify**: `cd backend && source .venv/bin/activate && pytest tests/unit/test_security_middleware_props.py::TestSecurityMiddlewareEnvironmentIndependence::test_suspicious_patterns_always_detected tests/unit/test_tenant_function_routes_props.py::TestGetCompleteness::test_get_returns_exactly_registry_functions_with_correct_state -v 2>&1 | tail -5`
  - **Fixes**: 2 failures

- [x] 6. Fix invoice test tool props assertion
  - **File**: `backend/tests/unit/test_invoice_test_tool_props.py`
  - **Action**: Investigate `TestAIMetricsConditionalOnParser::test_csv_rule_parser_has_null_ai_metrics`. Check if the CSV rule parser path correctly returns null AI metrics fields. May be a property-based test that generates edge cases — add `derandomize=True` if flaky, or fix the assertion if the service behavior changed.
  - **Effort**: S
  - **Priority**: Medium
  - **Verify**: `cd backend && source .venv/bin/activate && pytest tests/unit/test_invoice_test_tool_props.py::TestAIMetricsConditionalOnParser::test_csv_rule_parser_has_null_ai_metrics -v 2>&1 | tail -5`
  - **Fixes**: 1 failure

- [x] 7. Fix ruff lint — bulk auto-fix unused noqa directives (365 RUF100)
  - **Action**: Run `ruff check src/ --fix --select RUF100` from the backend directory. This removes all 365 unused `# noqa: BLE001` comments that are no longer needed because the BLE001 rule is not enabled in the current ruff config.
  - **Effort**: S
  - **Priority**: High (CI-blocking)
  - **Verify**: `cd backend && source .venv/bin/activate && ruff check src/ --select RUF100 2>&1 | tail -3`
  - **Fixes**: 365 lint errors

- [x] 8. Fix ruff lint — remaining manual fixes (13 errors)
  - **Files**: `src/routes/zzp_debtor_routes.py` (S110), `src/pattern_analyzer.py` (SIM102, I001), `src/pattern_scoring.py` (PERF102), `src/str_database.py` (RUF059), `src/str_stripe_enrichment.py` (RUF010, SIM102), `src/str_direct_parser.py` (RUF100 unused: BLE001)
  - **Action**:
    - S110 (4): Replace bare `except: pass` with `except Exception: logger.debug(...)` or similar
    - SIM102 (3): Collapse nested `if` into single `if x and y:`
    - PERF102 (1): Change `for k, v in dict.items()` → `for v in dict.values()` when key unused
    - RUF059 (1): Remove or use the unpacked `conn` variable
    - RUF010 (1): Use explicit `str()` conversion instead of f-string conversion flag
    - I001 (1): Sort imports (auto-fixable with `ruff check --fix --select I001`)
  - **Effort**: S
  - **Priority**: High (CI-blocking)
  - **Verify**: `cd backend && source .venv/bin/activate && ruff check src/ 2>&1 | tail -3`
  - **Fixes**: 13 lint errors

- [x] 9. Fix ruff format — 11 files
  - **Action**: Run `ruff format src/` from backend directory to auto-format all 11 files.
  - **Effort**: S
  - **Priority**: Low
  - **Verify**: `cd backend && source .venv/bin/activate && ruff format --check src/ 2>&1 | tail -3`
  - **Fixes**: 11 format violations

## Dependency Graph

```json
{
  "nodes": [
    {
      "id": "1",
      "title": "Fix S3_SHARED_BUCKET for import tests",
      "priority": "critical"
    },
    { "id": "2", "title": "Fix STR booking tuple shape", "priority": "high" },
    {
      "id": "3",
      "title": "Fix STR processor test fixture",
      "priority": "high"
    },
    {
      "id": "4",
      "title": "Fix STR Stripe enrichment mocks",
      "priority": "high"
    },
    { "id": "5", "title": "Fix Hypothesis flaky tests", "priority": "medium" },
    { "id": "6", "title": "Fix invoice test tool props", "priority": "medium" },
    {
      "id": "7",
      "title": "Bulk auto-fix RUF100 noqa directives",
      "priority": "high"
    },
    { "id": "8", "title": "Manual lint fixes (13 errors)", "priority": "high" },
    { "id": "9", "title": "Ruff format (11 files)", "priority": "low" }
  ],
  "edges": [
    {
      "from": "7",
      "to": "8",
      "reason": "Auto-fix first, then manual fixes for remaining"
    },
    { "from": "8", "to": "9", "reason": "Lint fixes may change formatting" }
  ]
}
```

## Summary

| Priority  | Tasks    | Failures Fixed                       | Lint Fixed          |
| --------- | -------- | ------------------------------------ | ------------------- |
| Critical  | 1        | 15                                   | —                   |
| High      | 2–4, 7–8 | 11                                   | 378                 |
| Medium    | 5–6      | 3                                    | —                   |
| Low       | 9        | —                                    | 11 files            |
| **Total** | 9        | **29 test + 17 flaky/investigation** | **378 + 11 format** |
