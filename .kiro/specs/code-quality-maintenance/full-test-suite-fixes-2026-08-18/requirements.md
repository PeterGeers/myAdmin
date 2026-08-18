# Full Test Suite Fixes — 2026-08-18

## Summary

Full test suite run (GitHub Actions run #32113429079) on 2026-08-18.

| Category               | Count              | Δ vs 2026-08-12      |
| ---------------------- | ------------------ | -------------------- |
| Backend test failures  | 46 (of 5918 tests) | ↓ 19 (was 65/5773)   |
| Frontend test failures | 0 (of 2370 tests)  | — (unchanged, green) |
| Ruff lint errors       | 378                | ↑ 300 (was 78)       |
| Ruff format violations | 11 files           | ↓ 3 (was 14 files)   |
| Vulture (dead code)    | ✅ Pass            | — (unchanged, green) |

---

## Test Failures — Backend (46 failures, 5872 passed, 10 skipped)

### Progress: 65 → 46 failures

19 fewer failures than last run. Media asset lifecycle/store tests and landing page tests were fixed. However, new failures appeared in STR modules and some old issues persist.

### Failures Grouped by Root Cause

#### 1. Missing Environment Variable — `S3_SHARED_BUCKET` (15 failures) ⚠️ RECURRING

**File**: `tests/unit/test_media_asset_service.py`

All 15 failures in TestImportLegacyAssets (12) and TestImportIntegration (3) raise:

> `ValueError: Environment variable 'S3_SHARED_BUCKET' is not set (required for category 'invoices')`

**Root cause**: The import-related test classes still don't have the `S3_SHARED_BUCKET` env var mocked. The previous fix (task 1 from 2026-08-12) fixed the store/lifecycle tests but missed the import tests.

**Tests affected**:

- `TestImportLegacyAssets::test_import_registers_new_objects`
- `TestImportLegacyAssets::test_import_skips_existing_keys`
- `TestImportLegacyAssets::test_import_all_already_registered`
- `TestImportLegacyAssets::test_import_skips_unclassifiable_objects`
- `TestImportLegacyAssets::test_import_empty_prefix`
- `TestImportLegacyAssets::test_import_returns_complete_summary`
- `TestImportLegacyAssets::test_import_generates_ast_ulid_ids`
- `TestImportLegacyAssets::test_import_detects_image_media_type`
- `TestImportLegacyAssets::test_import_detects_document_media_type`
- `TestImportLegacyAssets::test_import_detects_video_media_type`
- `TestImportLegacyAssets::test_import_detects_web_content_media_type`
- `TestImportLegacyAssets::test_import_extracts_filename_from_key`
- `TestImportIntegration::test_full_import_workflow`
- `TestImportIntegration::test_import_workflow_no_orphans_when_all_referenced`
- `TestImportIntegration::test_import_workflow_all_orphaned_when_none_referenced`

#### 2. STR Booking Multi-Import — Tuple Shape Mismatch (3 failures) 🆕

**File**: `tests/unit/test_str_booking_multi_import.py`

| Test                                                                                        | Error                                                                                                                                             |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TestProperty6ScopedOverwriteInvariant::test_delete_only_imported_pairs`                    | `AssertionError: Expected DELETE for ('booking.com', 'Green Studio') but it was not called. Deleted pairs: {('booking.com', 'Green Studio', '')}` |
| `TestExampleBasedMultiFileImport::test_scoped_delete_leaves_child_friendly_untouched`       | `AssertionError: assert ('booking.com', 'Green Studio') in {('booking.com', 'Green Studio', ''), ...}`                                            |
| `TestExampleBasedMultiFileImport::test_single_file_uses_delete_by_channel_listing_strategy` | `AssertionError: assert ('booking.com'...n Studio', '') == ('booking.com'...Green Studio')`                                                       |

**Root cause**: The delete scope strategy now returns 3-tuples `(channel, listing, subcategory)` instead of 2-tuples `(channel, listing)`. Tests assert the old 2-tuple format. The service was extended to support sub-categories but tests were not updated.

#### 3. STR Processor — Missing Test File (3 failures) 🆕

**File**: `tests/unit/test_str_processor.py`

| Test                                                         | Error                                                                               |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| `TestSTRProcessor::test_process_direct_success`              | `ValueError: Failed to parse CSV: [Errno 2] No such file or directory: 'test.xlsx'` |
| `TestSTRProcessor::test_process_direct_vrbo_channel`         | Same                                                                                |
| `TestSTRProcessor::test_process_direct_skip_non_reservation` | Same                                                                                |

**Root cause**: Tests reference a `test.xlsx` fixture file that doesn't exist in the CI environment. Either the file needs to be committed, or the test needs to mock the file read.

#### 4. STR Stripe Enrichment — Mock Configuration Error (5 failures) 🆕

**File**: `tests/unit/test_str_stripe_enrichment.py`

| Test                                                         | Error                                                              |
| ------------------------------------------------------------ | ------------------------------------------------------------------ |
| `TestExtractCustomerData::test_extract_all_data_available`   | `assert <MagicMock name='mock.shipping.phone'> == '+31687654321'`  |
| `TestExtractCustomerData::test_extract_no_customer`          | `assert <MagicMock name='mock.shipping.phone'> is None`            |
| `TestExtractCustomerData::test_extract_country_from_billing` | `assert <MagicMock name='mock.shipping.address.country'> == 'DE'`  |
| `TestExtractCustomerData::test_extract_stripe_fee`           | `assert <MagicMock name='mock.shipping.phone'> is None`            |
| `TestExtractCustomerData::test_extract_no_data`              | dict comparison shows MagicMock objects instead of expected values |

**Root cause**: The mock `PaymentIntent` object auto-creates nested attributes (MagicMock default behavior). The code accesses `payment_intent.shipping.phone` which returns a MagicMock instead of the expected value. Tests need to explicitly set `mock.shipping.phone = '+31...'` or use `spec=` to prevent auto-attribute creation.

#### 5. Hypothesis Flaky Tests (2 failures) ⚠️ RECURRING

| Test File                              | Test Name                                                        | Cause                         |
| -------------------------------------- | ---------------------------------------------------------------- | ----------------------------- |
| `test_security_middleware_props.py`    | `test_suspicious_patterns_always_detected`                       | Flaky — falsified then passed |
| `test_tenant_function_routes_props.py` | `test_get_returns_exactly_registry_functions_with_correct_state` | Flaky — falsified then passed |

**Root cause**: Still missing `derandomize=True` + `deadline=None` on these tests. The CI Hypothesis profile (task 8 from 2026-08-12) was added but these specific tests may not be using it, or the profile isn't being loaded.

#### 6. Invoice Test Tool Props — Assertion Error (1 failure) 🆕

**File**: `tests/unit/test_invoice_test_tool_props.py`
**Test**: `TestAIMetricsConditionalOnParser::test_csv_rule_parser_has_null_ai_metrics`

**Root cause**: Likely a property-based test where the CSV rule parser path is not correctly returning null AI metrics. Needs investigation of the test assertion vs actual parser behavior.

---

## Test Failures — Frontend (0 failures ✅)

All 2370 tests pass. 167 test files, 12 skipped. Duration: 135.97s.

---

## Lint & Static Analysis

### Ruff Lint — 378 errors (367 auto-fixable)

| Rule    | Count | Description                           | Auto-fixable |
| ------- | ----- | ------------------------------------- | ------------ |
| RUF100  | 365   | Unused `noqa` directive (non-enabled) | Yes ✅       |
| S110    | 4     | `try-except-pass` detected            | No           |
| SIM102  | 3     | Nested `if` → single `if`             | No           |
| RUF059  | 1     | Unpacked variable never used          | No           |
| RUF010  | 1     | Use explicit conversion flag          | Yes ✅       |
| PERF102 | 1     | Use `.values()` for dict iteration    | No           |
| I001    | 1     | Unsorted imports                      | Yes ✅       |

**Key insight**: The massive jump from 78 → 378 errors is almost entirely **365 RUF100 "unused noqa"** directives. This happened because the previous fix sprint (2026-08-12, task 6) likely enabled/changed ruff rules such that `BLE001` is no longer enabled in CI, making all the `# noqa: BLE001` comments unnecessary. This is a bulk auto-fix.

### Ruff Format — 11 files need reformatting (down from 14)

### Vulture — ✅ Pass (no dead code detected)

---

## Comparison with 2026-08-12

| Metric              | 2026-08-12 | 2026-08-18 | Trend                              |
| ------------------- | ---------- | ---------- | ---------------------------------- |
| Backend failures    | 65         | 46         | ↓ Good — 19 fewer                  |
| Frontend failures   | 0          | 0          | — Stable                           |
| Total backend tests | 5773       | 5918       | ↑ +145 tests added                 |
| Ruff lint errors    | 78         | 378        | ↑ Bad — mostly noqa cleanup needed |
| Ruff format files   | 14         | 11         | ↓ Good — 3 fewer                   |
| Vulture             | Pass       | Pass       | — Stable                           |

### Recurring Issues (from previous cycles)

1. **S3_SHARED_BUCKET env var** (3rd cycle): Was partially fixed in 2026-08-12 but only for store/lifecycle test classes. Import test classes still missing the mock. Same pattern as 2026-06-29 `S3_DEFAULT_STORAGE`.
2. **Hypothesis flaky tests** (4th cycle): `test_suspicious_patterns_always_detected` keeps recurring. The CI profile approach from 2026-08-12 hasn't fully resolved this.

### Fixed from Previous Run

- ✅ Landing page publish service (13 failures → 0)
- ✅ Landing page renderers (11 failures → 0)
- ✅ S3 shared storage `_make_key` (5 failures → 0)
- ✅ Media asset store/lifecycle tests (partially: 21 → 15, import classes remain)
- ✅ 3 of 5 Hypothesis flaky tests fixed

### New Failures (not in previous run)

- 🆕 STR booking multi-import tuple mismatch (3 failures)
- 🆕 STR processor missing test file (3 failures)
- 🆕 STR stripe enrichment mock config (5 failures)
- 🆕 Invoice test tool props assertion (1 failure)

---

## Lessons / Recurring Issues

1. **Env var validation continues to break tests** — For the THIRD time, eagerly-validated env vars cause test failures. When adding `S3_SHARED_BUCKET` to the mock fixture, ALL test classes in the file should have been covered — not just the ones that were already failing. Partial fixes create recurring failures.
2. **Hypothesis CI profile not fully effective** — The profile added in 2026-08-12 (task 8) doesn't prevent all flaky failures. Consider applying `@settings(derandomize=True, deadline=None)` directly on the 2 remaining problem tests as a targeted fix.
3. **noqa comment rot** — 365 unused `# noqa: BLE001` directives accumulated because ruff rule configuration changed without cleaning up the suppression comments. Auto-fixable with `ruff check --fix`.
4. **STR module tests lag behind implementation** — 3 separate STR test files broke simultaneously, suggesting new STR features (sub-categories, direct parse, Stripe enrichment) were merged without test alignment.
