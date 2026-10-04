# Full Test Suite Fixes — 2026-10-04 — Tasks

CI run #52 (id `37226495303`, 2026-10-04 @ `bd529bb` on `spec/code-quality-fixes-2026-10-04`, ❌ failure — backend tests + backend lint, two independent causes). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h.

> 🔴 **Two jobs are red (Backend Full Test Suite: 17 failed, Backend Lint & Static Analysis: ruff lint + format).** SAM ✅ and Frontend ✅. Unlike 10-03 this is **not** one root cause: the 17 test failures are stale/under-specified test mocks + a stale env contract, and the 56 lint issues are a stray-`import os` sweep + an un-formatted new `environment/` module. The High tasks (H1 test mocks, H2 ruff lint, H3 ruff format) turn CI green.
> Verification commands assume: `cd backend && source .venv/bin/activate`. No collection errors this cycle → **no Critical tasks**.
> ℹ️ Lint count: use **39** ruff-lint errors (per-rule table + ruff footer); the artifact's "41" header line is a stale summary (see requirements Lesson 7).

---

## Critical — collection / import errors (nothing else runs until these pass)

_None._ No collection or import errors this cycle — all 17 backend failures are runtime failures (tests collected and ran); SAM collects and passes.

---

## High — running tests that fail + CI-blocking lint

- [x] **H1. Give the shared cursor mock concrete `fetchall()`/`fetchone()` return values so the preservation / banking-service clusters stop leaking `MagicMock` (13 failing tests: G1 + G3 + most of G4).** [L] — the primary cause of the red backend job; a **recurrence** of the 10-03 H1 cluster one layer deeper (see requirements Lesson 1). Fix is in test mocks, not production.
  - **Why**: The 10-03 fix made the cursor context manager mock yield `(cursor, conn)` (fixing the unpack), but the mock's `fetchall()`/`fetchone()` still return a default `MagicMock`. So row counts compare as `'<' not supported between int and MagicMock`, `isinstance(result, list/dict)` is False, and the duplicate-check lookup reads every candidate as an existing Ref2 duplicate → `0 saved`.
  - **Failures grouped by signature** (fix the shared fixture once, then the stragglers):
    - **G1 — 5 × `MagicMock` in comparison/`isinstance`**: `test_banking_service.py::TestGetMutaties::{test_returns_mutaties_for_tenant, test_pagination_metadata, test_converts_dates_to_iso_format}`, `test_bug_condition_hardcoded_accounts.py::{TestTransactionLogicGammaFallback::test_zero_results_returns_error_not_gamma, TestTransactionLogicSingleResultVAT::test_single_result_vat_from_service_not_hardcoded}`. Make `fetchall()` return a concrete `list` (e.g. `[]` or seeded rows) and `fetchone()` a concrete tuple/`None`.
    - **G3 — 5 × duplicate-check always matches → `0 saved`**: `test_preservation_account_scoped_save.py::{TestSameAccountDuplicatePreserved::test_non_existing_row_is_saved, TestZeroAmountSkippedPreserved::test_mixed_zero_and_nonzero_only_nonzero_saved, TestClosedPeriodBlockingPreserved::test_open_year_not_blocked_when_other_year_closed, TestWrongTenantRejectionPreserved::test_valid_tenant_row_saved_against_same_guard}`, `test_preservation_closed_period.py::TestBankingProcessorPreservation::test_duplicate_detection_queries_existing_for_open_year`. The duplicate-check SELECT mock must return **no existing row** (`None`/`[]`) for genuinely-new Ref2, and the test must still see the SELECT call fire.
    - **G4 (partial) — 3 × projection/provider**: `test_closure_aware_bug_condition.py::TestMakeLedgersDoubleCount::test_make_ledgers_beginning_balance_equals_single_count` (no beginning-balance rows), `test_provider_aware_preservation.py::TestFlagModePreservation::test_flag_true_returns_local_folders_regardless_of_provider` (empty set). Likely the same row-shape gap feeding projection/provider code — triage each: stale mock vs genuine behaviour change.
  - **File(s) to change** (all under `backend/tests/unit/`): `test_banking_service.py`, `test_bug_condition_hardcoded_accounts.py`, `test_preservation_account_scoped_save.py`, `test_preservation_closed_period.py`, `test_closure_aware_bug_condition.py`, `test_provider_aware_preservation.py`, plus the **shared cursor-mock fixture/helper** they rely on (locate via grep below — likely in a `conftest.py` or a shared test util). Fix the fixture once; it should return concrete, test-controlled data from `fetchall()`/`fetchone()`, not bare mocks.
  - **Action**: Do **not** change production. Find the shared mock and give its cursor concrete returns:
    ```bash
    cd /home/peter/projects/myAdmin/backend && source .venv/bin/activate
    grep -rn "fetchall\|fetchone\|mock_cursor\|get_cursor\|__enter__" tests/unit/test_banking_service.py tests/unit/test_preservation_account_scoped_save.py tests/unit/conftest.py 2>/dev/null | head -40
    ```
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    pytest tests/unit/test_banking_service.py tests/unit/test_bug_condition_hardcoded_accounts.py \
           tests/unit/test_preservation_account_scoped_save.py tests/unit/test_preservation_closed_period.py \
           tests/unit/test_closure_aware_bug_condition.py tests/unit/test_provider_aware_preservation.py -q
    # -> 0 failed
    ```

- [x] **H2. Clear the 39 ruff-lint errors — dominated by 27 × `F401` (a stray `import os` sweep) + the un-cleaned `environment/` module.** [M] — CI-blocking (Backend Lint job red). 35 of 39 are safe-auto-fixable; ~4 need a human glance.
  - **Why**: 27 × `F401` (mostly an unused `import os` left across ~22 `src/routes/*.py` and a few `src/services/*.py`; plus 4 unused imports in `src/environment/resolver.py`), 5 × `UP045` (`Optional[X]` → `X | None`), 2 × `I001` (import sort), 2 × `F841` (`url`, `branch` in `resolver.py`), 1 × `UP035`, 1 × `UP006` (`Dict` → `dict` in `health_report.py`), 1 × `RUF022` (`__all__` unsorted). All but the F841 pair + two F401 + the UP035 line carry ruff's `[*]` safe-fix marker.
  - **File(s)**: ~22 `src/routes/*.py` + `src/services/{domain_verification_job,function_guard,pivot_service}.py` (the `os` F401s); and the `src/environment/` module (`__init__.py`, `bootstrap.py`, `environment_definition.py`, `resolver.py`, `health_report.py`) for everything else. Full line list is in the CI `backend-lint-reports/ruff-lint.md` artifact / the dependency-graph notes.
  - **Action**: Run the safe autofix first, then hand-review the residue:
    ```bash
    cd backend && ruff check src/ --fix      # clears the 35 [*] fixes (os F401s, UP045, I001, UP006, RUF022)
    ```
    Then manually review the non-safe residue — **do not** `--unsafe-fixes` blindly:
    - **2 × `F841`** `resolver.py:186` (`url`), `:187` (`branch`) — assigned-but-unused. Check whether a use was dropped (a log line, a return, a dict field) before deleting; a bare delete could hide a real omission.
    - **`UP035`** `health_report.py:40` (`typing.Dict` import) — remove once `UP006` rewrites the annotations to `dict`.
    - The 2 non-`[*]` F401 (`landing_page_routes/__init__.py:47`, `pivot_service.py:209`) — confirm `os` is truly unused there, then remove.
  - **Verification**:
    ```bash
    cd backend && ruff check src/ 2>&1 | tail -5     # -> "All checks passed!" (0 errors)
    ```

- [x] **H3. Reformat the 17 files flagged by `ruff format` (concentrated in the new `src/environment/` module).** [S] — CI-blocking (Ruff format check red); auto-fixable.
  - **Why**: "17 files would be reformatted, 307 files already formatted." The artifact reports only the count, not names; the `environment/` module (the lint hotspot) is the likely bulk. Run after H2 so lint `--fix` and format converge.
  - **File(s)**: whichever `ruff format --check src/` lists (run it to see names — the artifact omitted them).
  - **Action**:
    ```bash
    cd backend && ruff format --check src/   # list the 17 files first
    cd backend && ruff format src/           # reformat them
    ```
  - **Verification**:
    ```bash
    cd backend && ruff format --check src/    # -> "324 files already formatted" (0 would be reformatted)
    ```

---

## High — stale test contract (CI-blocking, independent of H1)

- [x] **H4. Migrate the env-isolation tests off the dead `TEST_MODE`/`TEST_DB_NAME`/`testfinance` contract to the `APP_ENV`/`finance` model (4 failing tests: G2).** [M] — CI-blocking (part of the 17 backend failures); **new** this cycle, unrelated to the DB-mock cluster.
  - **Why**: The app migrated to the `APP_ENV` + resolved-DB-target model (DB name is `finance` on both local-Docker and Railway targets per the `#database` convention). These tests still assert the old `TEST_MODE`/`TEST_DB_NAME`/`testfinance` shape:
    - `test_infrastructure.py::TestInfrastructure::test_test_environment_fixture` — `KeyError: 'TEST_DB_NAME'`.
    - `test_infrastructure.py::TestInfrastructure::test_production_environment_fixture` — `os.getenv('TEST_MODE')` is `None`, assert `== 'false'` fails.
    - `test_maintenance/test_isolation_layer.py::TestMockEnv::test_sets_db_name` — expects `'testfinance'`, gets `'finance'`.
    - `test_maintenance/test_isolation_layer.py::TestMockEnv::test_all_expected_keys_present` — expected-keys set still lists `TEST_MODE`; fixture now has `APP_ENV`.
  - **File(s)**: `backend/tests/unit/test_infrastructure.py`, `backend/tests/unit/test_maintenance/test_isolation_layer.py` (and the `mock_env` helper / `test_environment` fixture they consume — update the expected-keys set to `{… , 'APP_ENV'}` minus `'TEST_MODE'`, and the DB-name expectation to `'finance'`).
  - **Action**: Update the test expectations to the `APP_ENV`/`finance` model — **do not** reintroduce `TEST_MODE`/`testfinance` in production env resolution (that is the legacy escape hatch, not the model; see the `#database` skill). Confirm against the actual keys the current env resolver sets.
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    pytest tests/unit/test_infrastructure.py tests/unit/test_maintenance/test_isolation_layer.py -q   # -> 0 failed
    ```

---

## Medium — carried-over property assertion (recurrence)

- [x] **M1. Resolve `test_duplicate_checker` `continue`-decision property failure — same assertion failed on 10-03.** [M] — one of the 17 backend failures; flagged on 10-03 H1 as "may be a real behaviour change", never actually fixed.
  - **Why**: `test_duplicate_checker.py::TestDuplicateCheckerProperties::test_property_user_decision_processing_consistency` fails `AssertionError: Decision handling should succeed for continue` on both 10-03 and 10-04. This is a Hypothesis property test with a reproducible falsifying example (`continue` branch), **not** a flake. Decide: is the `continue` decision path *supposed* to return success, or has behaviour legitimately changed and the assertion should?
  - **File(s)**: `backend/tests/unit/test_duplicate_checker.py`, plus the duplicate-decision handler it exercises (`src/duplicate_checker.py` or equivalent — confirm by import).
  - **Action**: Reproduce with the Hypothesis decorator, trace the `continue` path, then either fix the mock/handler so `continue` returns success or update the assertion to the correct post-change contract. If it shares the H1 mock-row-shape gap, it may fall out with H1 — re-run after H1 before deep-diving.
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    pytest tests/unit/test_duplicate_checker.py::TestDuplicateCheckerProperties::test_property_user_decision_processing_consistency -q   # -> passed
    ```

---

## Low — prevention / hygiene

- [x] **L1. Broaden the pre-push guard from `--collect-only` to also run `ruff check` + `ruff format --check` + a changed-path test subset.** [M] — carried forward from 10-03 L1; **it would have caught this entire cycle's lint failure and most of the test failures before push**.
  - **Why**: 4+ consecutive red cycles entered via branch commits that only surface at the next scheduled run (09-30 format, 10-02 collection, 10-03 DB refactor, 10-04 import-sweep + env-drift). The current `pytest … --collect-only` guard catches collection breaks but not runtime failures or `F401`/format lint — exactly this cycle's shape (requirements Lesson 5).
  - **File(s)**: `scripts/hooks/pre-push`, `scripts/hooks/install-hooks.sh`.
  - **Action**: Add `cd backend && ruff check src/ && ruff format --check src/` and a changed-path `pytest` subset to the existing hook; keep the `SKIP_PREPUSH_*` escape hatch; fail on non-zero.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin
    git stash -a >/dev/null 2>&1; bash scripts/hooks/pre-push </dev/null; echo "rc=$?"; git stash pop >/dev/null 2>&1
    # -> with H2/H3 unfixed the hook exits non-zero; after fixes it exits 0.
    ```

- [x] **L2. Harden the shared cursor-mock fixture so `fetchall()`/`fetchone()` must be given explicit returns (stop the G1/G3 recurrence).** [M] — durable prevention for the twice-recurred preservation/banking cluster.
  - **Why**: The preservation/closure cluster has now broken on 10-03 (unpack) and 10-04 (`MagicMock` leak) off the *same* under-specified mock. A fixture that returns a bare `MagicMock` cursor will keep producing a new failure signature each refactor (requirements Lesson 1).
  - **File(s)**: the shared test fixture/helper from H1 (likely `backend/tests/unit/conftest.py` or a shared mock util).
  - **Action**: Make the fixture default `fetchall()` → `[]` and `fetchone()` → `None` (never a bare mock), and require tests to opt into seeded rows explicitly. Optionally add a tiny assertion/typed helper so a test that forgets to seed rows fails loudly rather than silently comparing against a mock.
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate && pytest tests/unit -q -k "preservation or banking_service or bug_condition"   # -> stays green; mock returns concrete data
    ```

- [x] **L3. Run `ruff --fix` + `ruff format` on new modules before they land (and fix the `ruff-lint.md` header count).** [S] — prevention; the `environment/` module landed un-linted/un-formatted and is nearly the whole lint load.
  - **Why**: The non-`os` lint (I001, UP045, UP035, UP006, RUF022, F841) and a large share of the 17 format files all sit in one freshly-added `src/environment/` module (requirements Lesson 4). Separately, the lint report header says "41" while the body/footer say "39" (Lesson 7).
  - **File(s)**: contributor docs / steering for the ruff pre-landing step; the CI lint-report generator for the header count.
  - **Action**: Document (and ideally gate via L1) that new/edited modules pass `ruff check --fix src/` + `ruff format src/` before push; fix the report generator's summary line to match the footer count.
  - **Verification**:
    ```bash
    cd backend && ruff check src/ && ruff format --check src/   # -> clean on current tree after H2/H3
    ```

- [x] **L4. Confirm ruff stays pinned to 0.16.5 (reproducibility guard).** [S] — standing guard carried forward from 10-03 L3; no change expected.
  - **Why**: The 39 lint errors are real code, not a version artifact — keep local 0.16.5 == CI 0.16.5 so counts stay trustworthy.
  - **File(s)**: `backend/requirements-test.txt`, `.github/workflows/full-test-suite.yml`, `.github/workflows/backend-code-quality.yml`.
  - **Action / Verification**:
    ```bash
    ruff --version                                   # -> ruff 0.16.5
    grep -rn "ruff==0.16.5" backend/requirements-test.txt .github/workflows/
    ```

---

## Execution order (see dependency-graph.json)

1. **H1** — give the shared cursor mock concrete `fetchall()`/`fetchone()` returns → clears the G1/G3 (+most G4) cluster, the bulk of the red backend job. (largest effort)
2. **H4** — migrate the 4 env-isolation tests to the `APP_ENV`/`finance` contract. (independent of H1; can run in parallel)
3. **H2** — `ruff check src/ --fix` + hand-review the ~4 residue → backend lint (lint) green.
4. **H3** — `ruff format src/` the 17 files → backend lint (format) green. (land with H2)
5. **M1** — resolve the `test_duplicate_checker` `continue`-decision property failure (re-check after H1 — may fall out with it).
6. **L1 / L2 / L3 / L4** — broaden pre-push guard, harden the cursor-mock fixture, lint/format new modules + fix the report header, confirm ruff pin. (prevention; after the greens)

## Full-suite verification (re-confirm after H1–H4)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `cd /home/peter/projects/myAdmin && PYTHONPATH=. python -m pytest sam/tests -q`
- Frontend: `cd frontend && npx vitest run`
- Lint + Format: `cd backend && ruff check src/ && ruff format --check src/`
- Or confirm the next `full-test-suite.yml` run is green after H1–H4 land.
