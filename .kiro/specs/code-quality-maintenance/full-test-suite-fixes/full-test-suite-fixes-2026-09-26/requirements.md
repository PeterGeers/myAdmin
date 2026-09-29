# Full Test Suite Fixes — 2026-09-26

## Summary

Full Test Suite run (GitHub Actions run #36221515479) on `main`, 2026-09-26 05:40 UTC. **CI conclusion: ❌ failure.** Analysis is CI-artifact-based only (no local scans), from the downloaded `backend-test-reports`, `sam-test-reports`, `frontend-test-reports`, and `backend-lint-reports` artifacts.

| Category                     | Count                              | Δ vs 2026-09-03                     |
| ---------------------------- | ---------------------------------- | ----------------------------------- |
| Backend test failures        | 15 failed + 7 errors (of 6555)     | ↓ 15 (was 37/5954)                  |
| SAM module-plane tests       | ❌ Total collection failure        | 🆕 first tracked / newly red        |
| Frontend test failures       | 7 (of 2656, in 3 files)            | 🔺 +7 (was 0/2382) — **regression** |
| Ruff lint errors             | 14 (13 auto-fixable)               | ↓ 855 (was 869)                     |
| Ruff format violations       | 6 files                            | 🔺 +1 (was 5 files)                 |
| Vulture (dead code)          | ✅ Pass                            | — (unchanged, green)                |

**CI job result**: Backend tests ❌ · **SAM module-plane ❌ (import error)** · Frontend tests ❌ · **Backend Lint & Static Analysis ❌**. Every plane except vulture is red this cycle.

> ⚠️ **Ruff version**: CI ran **ruff 0.16.5**. Align local ruff to 0.16.5 before reproducing/fixing lint or counts will not match (Lessons Rule 8 from prior cycles).

> ⚠️ **Count note**: the ruff lint report header summarizes 16 rule-hits by code but the tail reports `Found 14 errors` (13 fixable). The 14 figure is authoritative; the per-rule breakdown below sums to 14.

---

## Test Failures — Backend (15 failed, 6523 passed, 10 skipped, 7 errors — 770.85s)

### Progress: 37 → 15 failures (+7 errors) — net improvement, but the failure *area* shifted from media-asset/env-var to projection + STR/Airbnb.

### Grouped by root cause

#### RC-B1 — Projection property tests open real DB connections (8 failures) ⚠️ RECURRING (Hypothesis area, 6th cycle)

**Error**: `RuntimeError: Unit tests must not create real database connections. Use the 'mock_db' fixture from conftest.py instead.`

| File | Tests |
| ---- | ----- |
| `backend/tests/unit/test_projection_convergence_props.py` | `test_projection_converges_after_a_source_change` |
| `backend/tests/unit/test_projection_reader_isolation_props.py` | `test_projection_reader_isolates_tenants` |
| `backend/tests/unit/test_projection_sync_idempotence_props.py` | `test_sync_twice_unchanged_source_is_a_noop`, `test_repeated_syncs_are_stable_across_identical_reruns`, `test_source_change_bumps_version_and_read_side_sees_it`, `test_stale_lower_version_never_clobbers_newer_stored_value` |
| `backend/tests/unit/test_projection_sync_props.py` | `test_sync_is_write_only_to_projection_and_zero_mysql_writes`, `test_sync_via_fake_source_writes_only_projection_table` |

**Root cause**: These Hypothesis property tests drive `projection_sync` / projection reader code paths that instantiate a real DB connection instead of the `mock_db` fixture. A conftest guardrail (`RuntimeError` on real connections) catches them. Either the tests do not request `mock_db`, or the projection code creates its own connection that the fixture does not intercept. This is the same *projection-property-test* family that has recurred each cycle; the failure mode changed from Hypothesis deadline flakiness (prior cycles) to a hard real-DB guardrail trip.

#### RC-B2 — Airbnb header/classification scan returns `None` (7 failures) ⚠️ RECURRING (STR area)

**File**: `backend/tests/unit/test_str_processor_airbnb_scan.py`

| Test | Error |
| ---- | ----- |
| `TestAirbnbHeaderColumns::test_header_columns_pending_sample_strips_bom_and_whitespace` | `assert None is not None` |
| `TestAirbnbHeaderColumns::test_header_columns_realised_sample_includes_realised_markers` | `assert None is not None` |
| `TestIsAirbnbFile::test_header_content_classifies_even_without_airbnb_in_name` | `assert False is True` |
| `TestAirbnbIsRealised::test_realised_sample_header_classifies_as_realised` | `TypeError: argument of type 'NoneType' is not iterable` |
| `TestAirbnbIsRealised::test_pending_sample_header_classifies_as_pending` | `TypeError: argument of type 'NoneType' is not iterable` |
| `TestSampleFileEndToEndClassification::test_pending_sample_is_airbnb_and_pending` | `TypeError: argument of type 'NoneType' is not iterable` |
| `TestSampleFileEndToEndClassification::test_realised_sample_is_airbnb_and_realised` | `TypeError: argument of type 'NoneType' is not iterable` |

**Root cause**: The Airbnb header-detection helper returns `None` (no header row extracted) for the pending/realised sample CSVs. Downstream classification (`is_airbnb` / `is_realised`) then receives `None` and either fails the `is not None` assertion or throws `TypeError` on `in`-membership over `None`. Strongly correlated with RC-B3 (same sample fixture `airbnb_pending.csv`). Likely a changed Airbnb export layout (extra preamble rows / BOM / renamed columns) or a fixture file that no longer matches the parser's header anchor.

#### RC-B3 — Airbnb parser: all files fail to parse (7 errors) ⚠️ RECURRING (STR fixture)

**File**: `backend/tests/unit/test_str_airbnb_parser.py`, class `TestAnchoredExamples`

**Error (collection/setup)**: `ValueError: All files failed to parse: airbnb_pending.csv`

Tests: `test_hmxdt8waff_gross_and_channel_fee`, `test_hmtfchfwtp_gross_and_channel_fee`, `test_both_anchor_codes_present`, `test_anchor_dict_status_channel_and_defaults[HMXDT8WAFF]`, `test_anchor_dict_status_channel_and_defaults[HMTFCHFWTP]`, `test_exactly_one_dict_per_code`, `test_no_blank_reservation_code_payout_dropped`.

**Root cause**: The parser rejects `airbnb_pending.csv` outright (raises during a class/module fixture, hence *errors* not *failures* — the tests cannot even set up). Same underlying sample/format defect as RC-B2. Fixing the header/format handling once should clear both RC-B2 and RC-B3.

---

## Test Failures — SAM module-plane (❌ total collection failure) 🆕 CRITICAL

**Error** (conftest import chain):

```
ImportError while loading conftest 'sam/tests/conftest.py'.
tests/conftest.py:21: from sam.pretokengen import handler as handler_mod
pretokengen/handler.py:85: from auth.cognito_utils import _normalize_tenants_claim  # noqa: E402
../backend/src/auth/__init__.py:17: from .tenant_context import ( ... )
../backend/src/auth/tenant_context.py:15: from flask import jsonify, request
E   ModuleNotFoundError: No module named 'flask'
```

**Root cause**: The SAM (Lambda) test plane imports `sam.pretokengen.handler`, which imports `auth.cognito_utils`. Importing anything from the `auth` package executes `backend/src/auth/__init__.py`, which eagerly imports `.tenant_context`, which does a top-level `from flask import jsonify, request`. The SAM environment has no Flask (Lambda handlers are not Flask apps), so **the entire SAM suite fails to collect** — zero SAM tests run.

This is an **import-coupling defect**: a Flask-only web concern (`tenant_context`) is pulled into the import graph of a Flask-agnostic Lambda utility (`cognito_utils`) via the `auth` package `__init__`. The fix is to decouple the import (lazy import of Flask inside `tenant_context`, or stop re-exporting `tenant_context` from `auth/__init__.py`, or split `cognito_utils` out of the Flask-bearing package), not to add Flask to the SAM environment.

---

## Test Failures — Frontend (7 failed, 2637 passed, 12 skipped, 3 files — 166.34s) 🔺 REGRESSION

Frontend was green for three consecutive prior cycles (08-18, 09-03: 0 failures). It is red again.

#### RC-F1 — `MembersPage` renders no rows / region badge missing (4 failures)

**File**: `frontend/src/__tests__/MembersPage.test.tsx`

| Test | Error |
| ---- | ----- |
| `… > renders each member name returned by GET /members` | `Error: No region badge <span> for "Noord"` (helper `regionBadge`, line 114) |
| `… > renders exactly the rows the module returns — invents no extra rows (R8.7)` | `expected [] to have a length of 3 but got +0` |
| `… > surfaces each region as a read-only scope Badge (R5.3/R5.4)` | `Error: No region badge <span> for "Noord"` |
| `… > reverses the row order when the name header is clicked (R7.6)` | `expected [] to deeply equal [ 'Jan', 'Marie', 'Piet' ]` |

**Root cause**: `nameColumnOrder()` returns `[]` — the members table renders no rows at all, and the region `<span>` badge is absent. Either the mocked `GET /members` response shape changed (component reads a different field / envelope), the region badge markup was refactored away from a `<span>`, or a data-loading regression leaves the table empty. All four failures share the "table body is empty" symptom.

#### RC-F2 — `MembersPage` view-context assertion (1 failure)

**File**: `frontend/src/pages/__tests__/MembersPage.viewContexts.test.tsx:382`
**Test**: `… (d) default/empty context shows all visible fields > synthesizes a single default context (empty columns) → compact/full switch + fixed columns`
**Error**: `expected false to be true`

**Root cause**: The default/empty-columns view context no longer synthesizes the expected fixed-column set (compact/full toggle). Likely the same MembersPage change behind RC-F1 (column/context derivation), so treat as related.

#### RC-F3 — Banking upload shows account-selection dialog when it must abort (2 failures)

**File**: `frontend/src/components/banking/__tests__/BankingFileUpload.account-resolution-preservation.test.tsx`

| Test | Error |
| ---- | ----- |
| `… Zero Revolut accounts > should show error when no Revolut account is configured` | `expected <div role="dialog">…</div> to be null` (line 325) |
| `… Zero Revolut accounts > PROPERTY: for any set of non-Revolut accounts … shows error (seed=125779012)` | `Property failed after 1 tests` |

**Root cause**: When **zero Revolut accounts** are configured, uploading a Revolut file must abort with an error and **not** open the account-selection dialog. The component now renders the dialog (populated with non-Revolut accounts 1100/1200) instead of the "no configured account" error path. A preservation/property invariant ("no Revolut accounts ⇒ no dialog, show error") is broken.

---

## Lint & Static Analysis (Backend Lint job — ❌ FAIL, CI-blocking)

### Ruff Lint — 14 errors (13 auto-fixable), ruff 0.16.5

| Rule    | Count | Description                                       | Auto-fixable |
| ------- | ----- | ------------------------------------------------- | ------------ |
| UP045   | 7     | Use `X \| None` instead of `Optional[X]`          | Yes ✅       |
| RUF100  | 2     | Unused `noqa` directive (non-enabled `BLE001`)    | Yes ✅       |
| RUF022  | 2     | `__all__` is not sorted                           | Yes ✅       |
| UP035   | 1     | Import from `collections.abc` (`Iterable`,`Mapping`) | Yes ✅     |
| I001    | 1     | Import block un-sorted / un-formatted             | Yes ✅       |
| SIM102  | 1     | Nested `if` → single `if`                         | No (manual)  |

**Errors by file**:

- `src/routes/tenant_admin_scope.py:396` — RUF100
- `src/services/user_tenant_scope_service.py:350` — RUF100
- `src/services/members_config_validation.py` — UP035 (43), RUF022 (45), UP045 (191, 237, 238, 274, 275, 334, 335), SIM102 (223)
- `src/services/projection_builder.py:49` — I001
- `src/services/scope_canon.py:41` — RUF022

**Note**: 13 of 14 are `ruff check --fix`-able. Only the single **SIM102** (nested `if` at `members_config_validation.py:223`) needs a manual rewrite. This is the near-inverse of 09-03, where 866 of 869 needed manual/policy work — the BLE001/DTZ policy decision from last cycle clearly landed.

### Ruff Format — 6 files need reformatting (301 already formatted)

- `src/routes/str_routes.py`
- `src/routes/tenant_admin_scope.py`
- `src/services/members_config_validation.py`
- `src/services/projection_sync.py`
- `src/services/scope_canon.py`
- `src/services/user_tenant_scope_service.py`

All fixable with `ruff format src/`. These are pure line-wrap / call-argument-collapse reflows (no semantic change).

### Vulture — ✅ Pass (no dead code found)

---

## Comparison with 2026-09-03

| Metric               | 2026-09-03 | 2026-09-26 | Trend                                          |
| -------------------- | ---------- | ---------- | ---------------------------------------------- |
| Backend failures     | 37         | 15 (+7 err)| ↓ Good — but new projection + STR area         |
| SAM plane            | (untracked)| ❌ collapse | 🆕 Bad — total import failure                   |
| Frontend failures    | 0          | 7          | 🔺 Bad — **regression** (3 files)              |
| Total backend tests  | 5954       | 6555       | ↑ +601 tests                                   |
| Ruff lint errors     | 869        | 14         | ↓ Great — BLE001/DTZ policy applied            |
| Ruff format files    | 5          | 6          | 🔺 +1                                          |
| Vulture              | Pass       | Pass       | — Stable                                       |

### Fixed from previous run

- ✅ Ruff lint 869 → 14 (the BLE001/DTZ policy decision from 09-03 Lessons #3 was applied — the biggest win this cycle).
- ✅ S3_SHARED_BUCKET media-asset failures (32 → 0) — the recurring 4-cycle env-var failure appears resolved (no longer in the failing set).
- ✅ Parameter schema `secret` type assertion (1 → 0).

### New / regressed

- 🆕 **SAM module-plane total collection failure** (`flask` import via `auth/__init__.py` → `tenant_context`). New and CRITICAL.
- 🔺 **Frontend regressed 0 → 7** across MembersPage (5) and BankingFileUpload (2).
- 🔺 **Projection property tests** now trip the real-DB guardrail (8) — a new failure mode for the long-recurring property-test area.
- 🔺 **Airbnb STR parsing** broke again (RC-B2/B3, 14 tests) — recurrence of the "STR fixture/format" pattern.
- 🔺 Ruff format 5 → 6 files.

---

## Lessons / Recurring Issues

1. **The property-test suite keeps finding a new way to be red.** For six cycles the Hypothesis property tests have been the flakiest area — previously deadline timeouts, now a hard real-DB-connection guardrail trip in the projection tests. The durable fix is to make the projection code paths honour the `mock_db` fixture (inject the DB, don't self-construct a connection), not to relax the guardrail. Verify with the `mock_db` fixture actually intercepting `projection_sync`'s connection acquisition.

2. **STR/Airbnb tests recur whenever the export format shifts (repeat of 08-18).** On 08-18 it was a missing `test.xlsx` fixture; now `airbnb_pending.csv` fails to parse and header detection returns `None`. When Airbnb changes its CSV layout (preamble rows, BOM, renamed columns), commit the updated sample AND make header-anchor detection tolerant. RC-B2 and RC-B3 share one root cause — fix the header/format handling once.

3. **Import-coupling across the web/Lambda boundary is a landmine (new).** `auth/__init__.py` eagerly importing Flask-bearing `tenant_context` means every SAM/Lambda consumer of `auth.cognito_utils` now needs Flask. Keep Flask imports out of package `__init__` re-exports, or lazy-import Flask inside `tenant_context`. Do **not** "fix" this by installing Flask into the Lambda/SAM environment.

4. **Frontend green is not a ratchet.** Three green cycles lulled us; a MembersPage refactor (empty rows, missing region `<span>`, view-context columns) and a BankingFileUpload account-resolution change (dialog shown for zero-Revolut) reintroduced 7 failures. Re-run the affected component suites locally before merging UI refactors.

5. **The lint work from last cycle paid off — protect it.** 869 → 14 confirms the BLE001/DTZ policy call was right. Keep ruff pinned to 0.16.5 in CI and `requirements-test.txt` so the count stays reproducible, and clear the 13 auto-fixable items with `ruff check --fix` + `ruff format` so lint stops being the CI-blocker.
