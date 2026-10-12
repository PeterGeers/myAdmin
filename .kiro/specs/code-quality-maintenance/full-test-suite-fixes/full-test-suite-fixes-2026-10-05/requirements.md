# Full Test Suite Fixes — 2026-10-05

## Summary

Full Test Suite run (GitHub Actions run #53 / id `37278831648`) on `main` @ `6301234f`, 2026-10-05 07:38 UTC, triggered by `schedule`. **CI conclusion: ❌ failure.** Analysis is CI-artifact-based only (no local scans), from the downloaded `backend-test-reports`, `sam-test-reports`, `frontend-test-reports`, and `backend-lint-reports` artifacts.

| Category                     | Count                                       | Δ vs 2026-10-04                                |
| ---------------------------- | ------------------------------------------- | ---------------------------------------------- |
| Backend test failures        | **2** (of 6938; 6924 passed, 12 skip)       | 🟢 **improving** 17 → 2                          |
| SAM module-plane tests       | ✅ pass (1247 tests, 0 fail)                 | ✅ held green                                    |
| Frontend test failures       | 0 (of 2928; 2916 passed, 12 skip)           | ✅ held green                                    |
| Ruff lint errors (backend)   | **0** — ✅ All checks passed                 | 🟢 **fixed** 39 → 0                              |
| Ruff format violations (be)  | **0** — ✅ All files formatted               | 🟢 **fixed** 17 → 0                              |
| Vulture (dead code)          | ✅ Pass                                      | — stable green                                  |

**CI job result**: **Backend Full Test Suite ❌ (2 failed)** · SAM Module-Plane ✅ · Frontend ✅ · **Backend Lint & Static Analysis ✅**. **Only one job is red** — the backend test suite — and it is down to **2 failures** (from 17). The 10-04 backend-lint regression (39 ruff + 17 format) is **fully cleared**; this is the cleanest run in the recent arc.

> 🟢 **Big step toward green**: backend failures 17 → 2, and the whole Backend Lint job flipped ❌ → ✅. The 10-04 cursor-mock cluster (G1/G3/G4) and the env-isolation drift (G2) are **gone** — the 10-04 H1/H4 fixes held. What remains is **two small, independent failures**, each with a clear single cause.

> ⚠️ **One of the two failures is a direct side-effect of the 10-04 lint cleanup** (see Lessons 1): the 10-04 H2 "stray `import os` sweep" removed `import os` from `routes/landing_page_routes.py`, but `test_landing_page_contact.py` still patches `routes.landing_page_routes.os.getenv`, so the patch target no longer exists → `AttributeError`. Clearing the lint created one test regression. The gap the previous spec flagged (lint and tests pushed without being run together) is exactly what let this through.

> ⚠️ **Ruff version**: CI ran **ruff 0.16.5** (pinned, matches local). Lint is fully green this cycle, so there is no version-mismatch question to resolve.

---

## Test Results — Backend (6924 passed, 12 skipped, **2 failed**, 0 collection errors — 733.03s ≈ 12m13s)

🔴 **Red — the sole cause of the failed run**, but down to just 2 failures. 6938 tests collected; both fail at runtime (not collection). The two failures are **independent** — no shared root cause.

### F1 — stale `os` patch target after the 10-04 lint sweep (1 failure)

| Test | Error |
| ---- | ----- |
| `test_landing_page_contact.py::TestSendContactNotificationHelper::test_no_email_configured_skips_send` | `AttributeError: module 'routes.landing_page_routes' has no attribute 'os'` |

**Root cause (confirmed against source):** the test decorates with `@patch("routes.landing_page_routes.os.getenv", return_value="false")` (`test_landing_page_contact.py:425`), but `backend/src/routes/landing_page_routes.py` **no longer imports `os`** (`grep "import os|os\." → no matches`). The 10-04 **H2** F401 cleanup removed the then-unused `import os`; this test was never updated in the same change, so the `@patch` target resolves to a missing attribute. This is a **test-side regression caused by the previous fix sprint**, not a production bug. Fix the test to patch the real seam the handler uses to read config (patch `os.getenv` at the module that still imports `os`, or patch the helper/`mock_env` the code actually reads), not a removed import.

### F2 — Airbnb grouping: numeric-looking confirmation code coerced (1 failure)

| Test | Error |
| ---- | ----- |
| `test_str_airbnb_parser_grouping_property.py::TestAirbnbGroupingProperty::test_one_booking_per_code_payout_excluded` | `AssertionError: assert {'0.0'} == {'0000E0'}` |

**Root cause:** a Hypothesis property-based test (airbnb-export-format-update, Property 3: one booking per confirmation code, payout rows excluded). The **minimised falsifying example** uses `Bevestigingscode = '0000E0'` — a string that looks like scientific notation (`0000E0` → `0.0`). Somewhere in `process_airbnb_multi` the grouping key is passed through a numeric coercion (e.g. CSV/`float`/`Decimal` round-trip or a pandas dtype inference), so the code is stored/compared as `'0.0'` while the test's expected set keeps the original string `'0000E0'`. This is a **deterministic, reproducible** failure Hypothesis found — reproducible via `@reproduce_failure('6.92.1', b'AAEBAAEAAQABAAEOAQAAAAAB')` — **not** a `deadline`/flaky non-determinism issue. Fix: treat `Bevestigingscode` as an **opaque string** for grouping (never coerce to a number); keep the raw stripped string as the group key.

**Grouped by root cause:** 2 failures → **2 independent causes** — F1 is a stale test seam left behind by the 10-04 lint sweep (fix in test), F2 is a numeric-coercion bug on a string key surfaced by Hypothesis (fix in parser, or in the test's shape only if the design truly intends numeric codes — it does not).

---

## Test Results — SAM module-plane (✅ PASS)

✅ **Green.** 1247 tests, 0 failures, 0 errors, 0 skipped (17.89s). Collection healthy; held green for a third consecutive cycle.

---

## Test Results — Frontend (2916 passed, 12 skipped, 0 failed, 221 files — 120.64s)

✅ **Green.** 2928 tests across 221 files, 0 failures. Count flat vs 10-04 (2928 → 2928). No regressions.

---

## Lint & Static Analysis (Backend Lint job — ✅ PASS)

| Check | Result |
|-------|--------|
| Ruff Lint | ✅ Pass — **0 errors** ("All checks passed!", ruff 0.16.5) |
| Ruff Format | ✅ Pass — **0 files** would be reformatted ("All files already formatted!") |
| Vulture | ✅ Pass (no dead code) |

🟢 **Fully recovered from 10-04.** The 39 ruff-lint errors (27 × F401 `import os` sweep + the un-cleaned `environment/` module) and the 17 ruff-format files are **all cleared** — the 10-04 **H2/H3** fixes landed and held. Vulture stayed green across the whole arc.

### Non-blocking report-only signals (NOT CI-blocking)

These planes run **report-only** in CI (the job stays green regardless), so they do **not** cause the red run — but they are captured here for debt tracking. All are **Low** priority this cycle.

| Signal | Count | Notes |
| ------ | ----- | ----- |
| Frontend **ESLint** (report-only) | **1117 problems** (6 errors, 1111 warnings) | 1 error + 196 warnings auto-fixable via `eslint --fix`. The 1111 warnings are dominated by `@typescript-eslint/no-unused-vars` and `no-explicit-any` + `import-x/order`. |
| Frontend **tsc** typecheck (report-only) | **8 type errors** | `AppRoutes.tsx` (`mode` prop not on `UserMenuProps`), `BankingFileUpload…dedupe-preservation.test.tsx` (always-truthy), `useBankingPatterns.test.ts` / `useBankingUpload.test.ts` (mock `.mockClear`/`.mock` typing), `routePresetService.test.ts` ×2 + `vehicleService.test.ts` (`label` not in `Partial<…>`). |
| SAM **ruff** (report-only) | **329 findings** | By rule: `F401` ×291 (unused imports, auto-fixable), `I001` ×11, `RUF022` ×6, `SIM102` ×4, `UP037` ×3, `RUF100` ×3, `B017` ×3, `TRY004` ×2, `PYI034` ×1, `PLW1510` ×1, `PIE810` ×1, `PIE804` ×1. The 291 F401 dominate and are a single `ruff check --fix` sweep. |

#### Frontend ESLint — the 6 errors (file:line)

| Rule | File:line |
| ---- | --------- |
| `prefer-const` | `src/components/TenantAdmin/MembersConfig/MembersTypedField.tsx:424` (`base` never reassigned) |
| `no-constant-binary-expression` | `src/components/banking/__tests__/BankingFileUpload.account-scoped-dedupe-preservation.test.tsx:306` (constant truthiness on LHS of `||`) |
| `no-useless-escape` ×2 | `src/components/zzp/ContactModal.tsx:69` (`\-` ×2 in a regex char class) |
| `no-useless-escape` ×2 | `src/pages/public/blocks/ContactBlock.tsx:79` (`\-` ×2 in a regex char class) |

### Totals by category

- **CI-blocking** this cycle: **2 backend test failures**. Backend lint = **0** (green).
- **Report-only (non-blocking)**: FE ESLint 1117 (6 err / 1111 warn), FE tsc 8, SAM ruff 329 — tracked as Low debt, not causing the red run.
- **Auto-fixable vs manual**: F1/F2 are both manual (small, surgical). Report-only: SAM 291 F401 + FE 1 err/196 warn are `--fix`-able; the FE tsc 8 and the remaining FE ESLint errors need manual edits.
- **Version mismatch**: none (CI ruff 0.16.5 == local 0.16.5); lint is green regardless.

---

## Comparison with recent runs (the 09-30 → 10-05 arc)

| Metric               | 09-30 | 10-02 | 10-03 | 10-04 | 10-05 | Trend                                                  |
| -------------------- | ----- | ----- | ----- | ----- | ----- | ------------------------------------------------------ |
| CI conclusion        | ❌     | ❌     | ❌     | ❌     | ❌     | 🟠 Red 5 cycles — but failure surface is shrinking fast |
| Backend failures     | 0     | 0     | 46    | 17    | **2** | 🟢 Improving 46 → 17 → 2                                 |
| SAM plane            | 0     | ❌ collect | ✅ | ✅ | ✅     | ✅ Held green 3 cycles                                   |
| Frontend failures    | 0     | 0     | 0     | 0     | 0     | ✅ Held green                                            |
| Ruff lint errors     | 0     | 0     | 40 (RUF059) | 39 (F401×27…) | **0** | 🟢 **Cleared** — Backend Lint job green                 |
| Ruff format files    | 5     | 0     | 1     | 17    | **0** | 🟢 **Cleared**                                          |
| Vulture              | Pass  | Pass  | Pass  | Pass  | Pass  | — Stable                                                 |
| Total backend tests  | 6622  | 6645  | 6684  | 6938  | 6938  | flat vs 10-04                                            |
| Total frontend tests | 2734  | 2756  | 2756  | 2928  | 2928  | flat vs 10-04                                            |

### Held / fixed (stayed or turned green)

- ✅ **SAM** held green (1247 tests) for a third cycle.
- ✅ **Frontend** held green (2916 passed).
- ✅ **Vulture** green across the arc.
- 🟢 **Backend Lint job fully recovered**: 10-04's 39 ruff + 17 format → **0 + 0**. The 10-04 H2/H3 landed and held.
- 🟢 **Backend failures 17 → 2**: the 10-04 cursor-mock cluster (G1/G3/G4, H1) and env-isolation drift (G2, H4) are gone — those fixes held. The twice-recurring preservation/banking cluster did **not** reappear this cycle.
- 🟢 **`test_duplicate_checker` continue-decision (10-04 M1)** is green this cycle — no longer in the failure set.

### Regression this cycle

- 🔴 **`test_landing_page_contact.py` is newly red (F1)** as a **direct side-effect of the 10-04 H2 `import os` sweep**. Removing the unused `import os` from `landing_page_routes.py` broke a test that patches `routes.landing_page_routes.os.getenv`. This is a **fix-induced test regression** — the lint cleanup and the test it affected were not run together before landing.

### Recurring failures that were "fixed" last time but reappear

- **None this cycle.** The 10-04 recurring cluster (preservation/banking mocks, G1/G3/G4) and `test_duplicate_checker` continue-decision are all green. The chronic twice-recurred cluster finally stayed fixed.

### New failures introduced by the previous fix sprint

- **F1** (`test_landing_page_contact.py`) is the one new fix-induced failure: the 10-04 H2 F401 autofix removed an import that a test still patched. This is the mirror image of the 10-04 pattern (previously a mock fix broke tests; now a lint fix broke a test) — same meta-cause: a change landed without re-running the tests that reference the touched symbol.
- **F2** (`test_str_airbnb_parser_grouping_property.py`) is **not** fix-induced — it is a pre-existing numeric-coercion edge case that Hypothesis happened to minimise to `'0000E0'` this run. It can appear/disappear between runs depending on the Hypothesis example database, but the underlying bug is deterministic once the example is pinned.

---

## Lessons / Recurring Issues

1. **A lint autofix (`ruff --fix` removing an unused import) can silently break a test that patches that symbol.** The 10-04 H2 F401 sweep deleted `import os` from `routes/landing_page_routes.py`; `test_landing_page_contact.py` still does `@patch("routes.landing_page_routes.os.getenv", …)`, which now raises `AttributeError: module has no attribute 'os'`. **`ruff check --fix` touching a module must be followed by running that module's paired tests** (the Change-With-Tests contract applies to lint-driven edits too, not just behaviour changes). This is exactly the gap the 10-04 **L1** pre-push broadening (ruff + changed-path tests) was meant to close — had the changed-path test subset run after the autofix, F1 would have been caught pre-push. **L1 is still the highest-leverage prevention item and is carried forward.**

2. **Hypothesis "falsifying example" ≠ flaky (restated).** F2 prints `Falsifying example: …` + `@reproduce_failure('6.92.1', …)`. It is a **deterministic, minimised** failure, **not** `deadline`/non-determinism — the standard `derandomize=True` + `deadline=None` remedy (CI Lesson Rule 2) does **not** apply. Debug it via the reproduce decorator as an ordinary assertion failure. The actual lesson: **identifier-like fields that happen to look numeric (`0000E0`, leading-zero codes) must be treated as opaque strings** and never round-tripped through `float`/numeric dtype inference.

3. **Prevention is working — the surface is shrinking.** 46 → 17 → 2 backend failures and a fully-recovered lint job show the 10-03/10-04 fixes held and did not re-break (no recurrence this cycle). The remaining risk is the **last-mile gap**: small, fix-induced regressions (F1) that a pre-push changed-path test run would catch. Closing 10-04 L1 would very likely have made this run green.

4. **"Report-only" planes are accumulating quiet debt.** FE ESLint (1117), FE tsc (8), and SAM ruff (329, 291 of them F401) do not block CI, so they drift upward unnoticed. None caused this red run, but the SAM 291 × F401 and the FE 6 ESLint errors are cheap to clear and worth a periodic sweep before they become a blocking cliff if these planes are ever promoted to blocking.
