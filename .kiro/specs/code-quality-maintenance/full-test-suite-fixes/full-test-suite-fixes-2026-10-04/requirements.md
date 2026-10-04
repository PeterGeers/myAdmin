# Full Test Suite Fixes — 2026-10-04

## Summary

Full Test Suite run (GitHub Actions run #52 / id `37226495303`) on `spec/code-quality-fixes-2026-10-04` @ `bd529bb`, 2026-10-04 18:58 UTC. **CI conclusion: ❌ failure.** Analysis is CI-artifact-based only (no local scans), from the downloaded `backend-test-reports`, `sam-test-reports`, `frontend-test-reports`, and `backend-lint-reports` artifacts.

| Category                     | Count                                       | Δ vs 2026-10-03                                |
| ---------------------------- | ------------------------------------------- | ---------------------------------------------- |
| Backend test failures        | **17** (of 6938; 6909 passed, 12 skip)      | 🟢 **improving** 46 → 17                         |
| SAM module-plane tests       | ✅ pass (1247 tests, 0 fail)                 | ✅ held green                                    |
| Frontend test failures       | 0 (of 2928; 2916 passed, 12 skip)           | ✅ held green                                    |
| Ruff lint errors (backend)   | **39** (F401 ×27, UP045 ×5, …)              | 🔴 **regression** 0 → 39 (new rule mix)          |
| Ruff format violations (be)  | **17 files** would be reformatted            | 🔴 **regression** 1 → 17                         |
| Vulture (dead code)          | ✅ Pass                                      | — stable green                                  |

**CI job result**: **Backend Full Test Suite ❌ (17 failed)** · SAM Module-Plane ✅ · Frontend ✅ · **Backend Lint & Static Analysis ❌ (ruff lint + ruff format)**. **Two jobs are red** — backend tests and backend lint — the same two-job shape as 10-03, but with **different, now-decoupled** root causes.

> 🟢 **Backend tests are recovering (46 → 17)** — the 10-03 `database.py` `(cursor, conn)` refactor fallout has mostly cleared. But **4 of the modules "fixed" on 10-03 are red again with a *new* signature** (see Lessons 1): the 10-03 shared-mock fix got them to unpack `(cursor, conn)`, but the mocks now return bare `MagicMock`s where concrete row values are needed, so comparisons and save-paths fail. This cycle's failures split into **four independent clusters**, not one root cause.

> 🔴 **Lint regressed on a different axis**: 10-03 was 40 × `RUF059` from the DB refactor; this cycle `RUF059` is **gone** but **27 × F401 unused imports** (mostly a stray `import os` left across ~22 `routes/` and `services/` files) plus a scatter of modernization rules (`UP045`, `UP035`, `UP006`) and import-order (`I001`) appeared, and **ruff format jumped 1 → 17 files**.

> ⚠️ **Ruff version**: CI ran **ruff 0.16.5** (pinned, matches local per 10-02/10-03 L3). The lint failures are real code issues, **not** a version-mismatch artifact.

> ℹ️ **Lint count note**: the `ruff-lint.md` artifact header says "Found 41 errors", but the per-rule breakdown and the ruff footer both say **39** (27+5+2+2+1+1+1 = 39, "Found 39 errors"). This spec uses **39** (the authoritative detailed/footer count); the "41" header looks like a stale/off-by-two summary line in the report generator.

---

## Test Results — Backend (6909 passed, 12 skipped, **17 failed**, 0 collection errors — 756.52s ≈ 12m36s)

🔴 **Red — primary cause of the failed run**, but much reduced (46 → 17). 6938 tests collected; 17 fail at runtime (not collection). The failures form **four independent clusters** (no longer a single root cause). Most are Hypothesis property-based tests reporting **reproducible falsifying examples** (deterministic bugs Hypothesis minimised, **not** `deadline`/flaky non-determinism — Hypothesis 6.92.1).

### Cluster G1 — `MagicMock` leaks into comparisons (5 failures)

The cursor/connection mock yields a `MagicMock` where the code expects concrete row data, so arithmetic/`isinstance`/`dict` access operate on a mock.

| Test | Error | Note |
| ---- | ----- | ---- |
| `test_banking_service.py::TestGetMutaties::test_returns_mutaties_for_tenant` | `assert False is True` (stdout: `'<' not supported between instances of 'int' and 'MagicMock'`) | mock row count compared with `<` |
| `test_banking_service.py::TestGetMutaties::test_pagination_metadata` | same `'<' not supported … int vs MagicMock` | pagination math on a mock |
| `test_banking_service.py::TestGetMutaties::test_converts_dates_to_iso_format` | `KeyError: 'mutaties'` (service returned error dict because of the `<` failure) | downstream of the same cause |
| `test_bug_condition_hardcoded_accounts.py::TestTransactionLogicGammaFallback::test_zero_results_returns_error_not_gamma` | `AssertionError … returned a list (Gamma fallback) … Got: <MagicMock …fetchall()>` | `fetchall()` returns a `MagicMock`, not `[]` |
| `test_bug_condition_hardcoded_accounts.py::TestTransactionLogicSingleResultVAT::test_single_result_vat_from_service_not_hardcoded` | `AssertionError: Expected list, got <class 'unittest.mock.MagicMock'>` | same `fetchall()` mock-shape gap |

**Root cause**: the mock cursor's `fetchall()`/`fetchone()` return the default `MagicMock` instead of a concrete list/row. (This is the *next layer* of the 10-03 shared-mock fix — see Lessons 1.) Fix is in the test mocks, not production.

### Cluster G2 — env-isolation fixture contract drift (4 failures)

Tests assert the **old** `TEST_MODE` / `TEST_DB_NAME` / `testfinance` environment model; the app has migrated to the **`APP_ENV` + resolved-DB-target** model (DB name is `finance` on both targets — local Docker vs Railway — per the `#database` convention).

| Test | Error |
| ---- | ----- |
| `test_infrastructure.py::TestInfrastructure::test_test_environment_fixture` | `KeyError: 'TEST_DB_NAME'` |
| `test_infrastructure.py::TestInfrastructure::test_production_environment_fixture` | `AssertionError: assert None == 'false'` (`os.getenv('TEST_MODE')` is `None`) |
| `test_maintenance/test_isolation_layer.py::TestMockEnv::test_sets_db_name` | `AssertionError: assert 'finance' == 'testfinance'` |
| `test_maintenance/test_isolation_layer.py::TestMockEnv::test_all_expected_keys_present` | `AssertionError` — fixture now has `APP_ENV`, expected-set still has `TEST_MODE` |

**Root cause**: stale tests encoding the pre-`APP_ENV` isolation contract. Fix the test expectations (and the `mock_env` helper's expected-keys set) to the `APP_ENV`/`finance` model, not production.

### Cluster G3 — account-scoped save / preservation: duplicate-check mock always matches (5 failures)

Every save is skipped as a duplicate — stdout is flooded with `Skipping duplicate (Ref2 match): …` — so genuinely-new rows save 0.

| Test | Error |
| ---- | ----- |
| `test_preservation_account_scoped_save.py::TestSameAccountDuplicatePreserved::test_non_existing_row_is_saved` | `Expected 1 saved for a genuinely new Ref2=1, got 0` |
| `test_preservation_account_scoped_save.py::TestZeroAmountSkippedPreserved::test_mixed_zero_and_nonzero_only_nonzero_saved` | `Expected only the non-zero row saved, got 0` |
| `test_preservation_account_scoped_save.py::TestClosedPeriodBlockingPreserved::test_open_year_not_blocked_when_other_year_closed` | `Expected the open-year row to save …, got 0` |
| `test_preservation_account_scoped_save.py::TestWrongTenantRejectionPreserved::test_valid_tenant_row_saved_against_same_guard` | `Expected a valid-tenant row to save, got 0` |
| `test_preservation_closed_period.py::TestBankingProcessorPreservation::test_duplicate_detection_queries_existing_for_open_year` | `Expected at least 1 SELECT call for duplicate check, got 0` |

**Root cause**: the duplicate-check query mock returns a truthy/`MagicMock` "existing row" for every lookup (so every candidate reads as a Ref2 duplicate), and the SELECT-call assertion sees 0 because the mock short-circuits before the real query path. Same mock-shape family as G1; fix in test mocks.

### Cluster G4 — projection / provider-aware logic (3 failures)

| Test | Error | Note |
| ---- | ----- | ---- |
| `test_closure_aware_bug_condition.py::TestMakeLedgersDoubleCount::test_make_ledgers_beginning_balance_equals_single_count` | `AssertionError: No beginning balance records found in make_ledgers output` (`0 > 0`) | `make_ledgers` produced no beginning-balance rows |
| `test_duplicate_checker.py::TestDuplicateCheckerProperties::test_property_user_decision_processing_consistency` | `AssertionError: Decision handling should succeed for continue` | the `continue` decision path returns non-success (same failing assertion as 10-03) |
| `test_provider_aware_preservation.py::TestFlagModePreservation::test_flag_true_returns_local_folders_regardless_of_provider` | `AssertionError: assert set() == {'KPN', 'Supplier1', 'Ziggo'}` | flag-mode returned an empty set |

**Root cause**: mixed — likely the same mock-row-shape gap (G1/G3 family) feeding projection/provider code paths, plus one carried-over property assertion (`test_duplicate_checker` continue-decision) that was also red on 10-03. Needs per-test triage: confirm whether each is a stale mock or a genuine behaviour change to assert against.

**Grouped by root cause:** 17 failures → **~2 effective causes** (test-mock row-shape gap feeding G1/G3/most of G4, and a stale env-contract in G2), plus 1–2 property-assertion stragglers in G4. All fixes are in **tests**, not production (SAM + Frontend + the app run fine).

---

## Test Results — SAM module-plane (✅ PASS)

✅ **Green.** 1247 tests, 0 failures, 0 errors, 0 skipped (16.95s). Collection healthy; the 10-02 collection break and 10-03 recovery both held.

---

## Test Results — Frontend (2916 passed, 12 skipped, 0 failed, 221 files — 143.47s)

✅ **Green.** 2928 tests across 221 files, 0 failures. Count up vs 10-03 (2756 → 2928, +172). No regressions.

---

## Lint & Static Analysis (Backend Lint job — ❌ FAIL)

| Check | Result |
|-------|--------|
| Ruff Lint | ❌ Fail — **39 errors** (7 distinct rules) |
| Ruff Format | ❌ Fail — **17 files** would be reformatted |
| Vulture | ✅ Pass (no dead code) |

### Ruff Lint — 39 errors by rule

| Rule | Count | What | Auto-fixable? |
| ---- | ----- | ---- | ------------- |
| `F401` | 27 | Unused import — **mostly a stray `import os`** left in ~22 `src/routes/*.py` and a few `src/services/*.py` files; plus 4 unused imports in `src/environment/resolver.py` (`dataclasses.field`, `CognitoDef`, `MysqlDef`, `SamDef`). | ✅ yes (`--fix`), except 2 (`landing_page_routes/__init__.py`, `pivot_service.py:209`) flagged without the `[*]` safe-fix marker |
| `UP045` | 5 | Use `X | None` instead of `Optional[X]` — `bootstrap.py` (1), `environment_definition.py` (2), `resolver.py` (2). | ✅ yes (`--fix`) |
| `I001` | 2 | Import block un-sorted/un-formatted — `environment/__init__.py:15`, `resolver.py:32`. | ✅ yes (`--fix`) |
| `F841` | 2 | Local assigned but never used — `resolver.py:186` (`url`), `:187` (`branch`). | ⚠️ manual (no `[*]`) — review (may be a missing use, like a dropped log/return) |
| `UP035` | 1 | `typing.Dict` deprecated, use `dict` — `health_report.py:40`. | ⚠️ paired with UP006; no `[*]` on this one |
| `UP006` | 1 | Use `dict` instead of `Dict` for annotation — `health_report.py:45`. | ✅ yes (`--fix`) |
| `RUF022` | 1 | `__all__` not sorted — `environment/__init__.py:45`. | ✅ yes (`--fix`) |

**Totals**: 39 errors; ruff reports **35 fixable with `--fix`** (2 hidden/unsafe-only). The dominant cluster (27 × `F401`, ~22 of them a stray `import os`) is a single mechanical sweep. The `environment/` module (`__init__.py`, `bootstrap.py`, `environment_definition.py`, `resolver.py`, `health_report.py`) accounts for all of the non-`os` lint (I001, UP045, UP035, UP006, RUF022, F841) — it reads like a newly-added/edited module that hasn't been run through `ruff --fix` + `ruff format` yet.

> ⚠️ **`F841` is not a safe auto-fix here** — `resolver.py` assigns `url` and `branch` then never uses them. Blindly deleting them could hide a dropped assignment (e.g. a value meant to be logged/returned). Review before removing.

### Ruff Format — 17 files

"17 files would be reformatted, 307 files already formatted." The artifact only reports the count (one `unformatted: File would be reformatted` line per file), not the file names. Auto-fixable via `ruff format src/`. Given the `environment/` module dominates the lint findings, it is likely a large share of the 17 — confirm the file list locally with `ruff format --check src/`.

### Vulture — ✅ Pass

No dead code found. (Held green across the whole arc.)

### Non-blocking report-only signals

The CI artifacts for this run do **not** include SAM-ruff / frontend-ESLint / frontend-tsc report-only sections (only the four core artifact groups were produced). Nothing report-only is recorded for this cycle; if those planes matter, confirm the workflow still emits them.

- **Total by category**: CI-blocking = 39 ruff lint + 17 ruff format = **56 backend lint issues**; report-only = none captured this run.
- **Auto-fixable vs manual (CI-blocking)**: 35 of 39 ruff-lint errors are `--fix`-able and all 17 format files are `ruff format`-able; the manual residue is **2 × F841** (review) + the 2 non-`[*]` F401 + the UP035 line — call it ~5 that want a human glance.
- **Version mismatch**: none (local 0.16.5 == CI 0.16.5).

---

## Comparison with recent runs (the 09-29 → 10-04 arc)

| Metric               | 09-29 | 09-30 | 10-02 | 10-03 | 10-04 | Trend                                                  |
| -------------------- | ----- | ----- | ----- | ----- | ----- | ------------------------------------------------------ |
| CI conclusion        | ✅     | ❌     | ❌     | ❌     | ❌     | 🔴 Red 4 cycles running — different cause each time      |
| Backend failures     | 0     | 0     | 0     | 46    | **17**| 🟢 Improving (46 → 17) but **4 modules recurred**       |
| SAM plane            | 0     | 0     | ❌ collect | ✅ | ✅     | ✅ Held green 2 cycles                                   |
| Frontend failures    | 0     | 0     | 0     | 0     | 0     | ✅ Held green                                            |
| Ruff lint errors     | 0     | 0     | 0     | 40 (RUF059) | **39** (F401×27 …) | 🔴 Still red, **different rule mix** (RUF059 cleared)   |
| Ruff format files    | 0     | 5     | 0     | 1     | **17**| 🔴 Worst in the arc                                      |
| Vulture              | Pass  | Pass  | Pass  | Pass  | Pass  | — Stable                                                 |
| Total backend tests  | 6564  | 6622  | 6645  | 6684  | 6938  | ↑ +254 since 10-03                                       |
| Total frontend tests | 2734  | 2734  | 2756  | 2756  | 2928  | ↑ +172 since 10-03                                       |

### Held / fixed (stayed green)

- ✅ **SAM** held green (1247 tests) — the 10-02 collection break stays resolved.
- ✅ **Frontend** held green (2916 passed), now +172 tests.
- ✅ **Vulture** green.
- 🟢 **10-03 `RUF059` (×40) cleared** — the DB-refactor `(cursor, conn)` unused-`conn` lint is gone this cycle (either the H2 `_conn`/cursor-only convention landed, or those sites changed).
- 🟢 **Backend failures down 46 → 17** — the bulk of the 10-03 `(cursor, conn)` test-mock fallout is fixed.

### Regression this cycle

- 🔴 **Ruff lint 0 → 39** on a **new axis**: 27 × `F401` (a stray `import os` sweep across `routes/`/`services/`, + unused imports in the new `environment/` module) and the `environment/` module's un-`--fix`'d modernization/import-order findings. Decoupled from the DB refactor.
- 🔴 **Ruff format 1 → 17 files** — the worst in the arc; concentrated around the `environment/` module landing without `ruff format`.

### Recurring failures that were "fixed" last time but reappear

- 🔴 **`test_preservation_account_scoped_save.py`, `test_preservation_closed_period.py`, `test_closure_aware_bug_condition.py`, `test_duplicate_checker.py`** were all in the 10-03 backend-test cluster (as `ValueError: not enough values to unpack (expected 2, got 0)`), landed under 10-03 **H1** and marked **fixed**. They are **red again on 10-04** — but with a **different signature** (`0 saved` / `MagicMock` leakage / `assert False` / "No beginning balance"), not the unpack error. The 10-03 fix made the mock *yield a 2-tuple* so the unpack passes, but the mock's `fetchall()`/`fetchone()` / duplicate-check lookup still return a bare `MagicMock`, which fails one layer deeper. **This is a partial-fix recurrence, not a fresh break.** (See Lessons 1.)
- 🔴 **`test_duplicate_checker.py::…::test_property_user_decision_processing_consistency`** fails with the *same* assertion as 10-03 (`Decision handling should succeed for continue`) — the 10-03 H1 note flagged it as possibly a real behaviour change, not just a mock; it was never actually resolved.

### New failures introduced by the previous fix sprint

- The 10-03 **H1** shared-cursor-mock fixture is the proximate cause of the G1/G3 recurrence: fixing the unpack shape without also giving the mock concrete `fetchall()`/`fetchone()` return values moved the failure from collection/unpack time to assertion time.
- **G2 (env-isolation drift)** is **new** this cycle — it did not appear on 10-03. It is unrelated to the DB refactor; it tracks the `APP_ENV`/`finance` env-model migration finally reaching (or being tested against stale expectations in) `test_infrastructure.py` and `test_isolation_layer.py`.

---

## Lessons / Recurring Issues

1. **A shared-mock fix that only repairs the *outer* shape re-breaks one layer deeper.** The 10-03 H1 fix made the cursor mock yield `(cursor, conn)` so the unpack stopped failing — but the mock's `fetchall()`/`fetchone()` (and the duplicate-check lookup) still return a default `MagicMock`. So the four preservation/closure modules "fixed" on 10-03 are red again on 10-04, now with `MagicMock`-in-comparison / `0 saved` errors instead of unpack errors. **Fix the mock end-to-end**: the shared cursor fixture must return concrete, test-controlled row data (lists/tuples/`None`) from `fetchall()`/`fetchone()`, not bare mocks — otherwise this cluster will recur a third time with yet another signature.

2. **Hypothesis "falsifying example" ≠ flaky.** 10+ of the 17 failures print `Falsifying example: …` and `@reproduce_failure('6.92.1', …)`. These are **deterministic, minimised** failures Hypothesis found and can reproduce — they are **not** `deadline`/non-determinism flakes, so the standard `derandomize=True` + `deadline=None` remedy (CI Lesson Rule 2) does **not** apply here. Treat them as ordinary assertion failures to debug via the reproduce decorator, not as flakes to suppress.

3. **A stray `import os` is sweeping across the codebase (27 × F401).** The dominant lint cluster is an unused `import os` left in ~22 `routes/`/`services/` files — almost certainly a copy-paste/boilerplate header or a half-finished refactor that removed the `os` usage but not the import. One `ruff check --fix src/` clears 35 of 39, but the *pattern* (boilerplate imports landing unused) will recur unless a pre-push `ruff check` gate stops it (see the still-open 10-03 L1).

4. **New modules must pass `ruff --fix` + `ruff format` before landing.** The entire non-`os` lint load (I001, UP045, UP035, UP006, RUF022, F841) and a large share of the 17 format files are concentrated in one freshly-added/edited module (`src/environment/`). It reads as code that never had `ruff format`/`ruff check --fix` run on it. This is the same meta-pattern as prior cycles: a change lands on a branch and only surfaces at the next scheduled suite.

5. **RECURRING META-PATTERN (continued): breakage keeps entering via branch commits that only surface at the next scheduled run.** 4+ consecutive red cycles (09-30 format, 10-02 collection, 10-03 DB refactor, 10-04 env-drift + import sweep). The 10-03 **L1** proposal to broaden the pre-push guard from `--collect-only` to also run `ruff check` + `ruff format --check` + a changed-path test subset **would have caught this cycle's entire lint failure and most of the test failures before push**. It is still the highest-leverage prevention item and is carried forward.

6. **"Fixed" is not durable without an enforcing gate.** `test_duplicate_checker` `continue`-decision has now failed on both 10-03 and 10-04. Items marked fixed in a report that nothing re-runs will drift back. Either the pre-push/pre-merge gate must run the affected tests, or recurring offenders need a dedicated regression check.

7. **Count-reporting hygiene: the lint artifact header disagrees with its own body.** `ruff-lint.md` says "Found 41 errors" in the header but "Found 39 errors" in the footer and the per-rule table sums to 39. Minor, but the report generator's summary line is off — worth a one-line fix so future counts are trustworthy at a glance.
