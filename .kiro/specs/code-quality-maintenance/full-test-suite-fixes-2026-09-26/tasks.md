# Full Test Suite Fixes — 2026-09-26 — Tasks

CI run #36221515479 (2026-09-26). Fix tasks grouped by priority. Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h.

> Before starting any lint task, align local ruff to CI's **0.16.5** or counts will not reproduce.
> Verification commands assume: `cd backend && source .venv/bin/activate` (backend) and `cd frontend` (frontend).

---

## Critical — collection / import errors (nothing else runs until these pass)

- [x] **C1. Decouple Flask from the `auth` import path so the SAM plane can collect.** [M] ✅ DONE 2026-09-26
  - **File(s)**: `backend/src/auth/__init__.py` (line 17 re-exports `.tenant_context`), `backend/src/auth/tenant_context.py` (line 15 `from flask import jsonify, request`), consumed via `sam/pretokengen/handler.py:85` → `auth.cognito_utils`.
  - **Action**: Break the eager Flask import on the `auth.cognito_utils` path. Preferred: lazy-import Flask *inside* the functions of `tenant_context.py` that need `jsonify`/`request` (module import must not require Flask). Alternative: stop re-exporting `tenant_context` from `auth/__init__.py`, or move `cognito_utils` into a Flask-free submodule. Do **not** add Flask to the SAM environment.
  - **Verification**: `cd sam && source ../backend/.venv/bin/activate && python -c "from sam.pretokengen import handler"` imports cleanly, then `pytest sam/tests -q` collects and runs.
  - **RESOLUTION**: Removed the module-level `from flask import jsonify, request` in `tenant_context.py` and moved it to a lazy import *inside* the `tenant_required` decorator's `decorated_function` (the only request-time consumer). Updated `backend/tests/test_tenant_context.py::test_tenant_required_decorator_valid`, which patched the now-removed module-level `auth.tenant_context.request`, to use the real Flask request context. Verified in a **Flask-free** CI-like venv (`sam/shared/requirements.txt` + `pytest` + `boto3`): SAM suite went from total collection failure → **957 passed**. Flask-plane `test_tenant_context.py`: **24 passed**.
  - **CI SETUP FOLLOW-UP ✅ APPLIED 2026-09-26**: with Flask fixed, the same Flask-free repro then surfaced `ModuleNotFoundError: No module named 'boto3'` via `services.dynamodb_client`. `boto3` is a legitimate SAM runtime dep (present in the Lambda runtime by default, hence omitted from `sam/shared/requirements.txt`) but was **absent in the SAM CI job**. Added `pip install boto3==1.42.30` (matching `backend/requirements.txt`) to the `sam-tests` job in `.github/workflows/full-test-suite.yml`, with an inline comment explaining why. This is NOT a source-coupling bug; boto3 is intentionally NOT added to the Lambda layer manifest. **Verified**: a venv mirroring the exact updated CI install list (Flask absent, boto3 1.42.30 present) runs the full SAM suite → **957 passed, RC=0**.

- [x] **C2. Fix the Airbnb sample fixture / header detection so `test_str_airbnb_parser.py` can set up.** [M] ✅ DONE 2026-09-26
  - **File(s)**: `backend/tests/unit/test_str_airbnb_parser.py` (`TestAnchoredExamples`), the `airbnb_pending.csv` sample fixture, and the Airbnb parser header-anchor logic (see C3 for the shared helper).
  - **Action**: Reproduce `ValueError: All files failed to parse: airbnb_pending.csv`. Determine whether the sample CSV drifted from the current Airbnb export layout (preamble rows / BOM / renamed columns) or the parser's header anchor is too strict. Re-commit an accurate sample and/or make header detection tolerant. Shares root cause with C3 — fix header handling once.
  - **Verification**: `pytest tests/unit/test_str_airbnb_parser.py -q` → 0 errors.
  - **ROOT CAUSE**: Not a parser bug. Both `test_str_airbnb_parser.py` and `test_str_processor_airbnb_scan.py` read their sample CSVs from the repo-root **`.agent-output/`** dir, which is **git-ignored** (`.gitignore: .agent-output/`). So the files exist on a dev machine but are absent in CI's checkout → header detection reads nothing → parser raises "All files failed to parse". This is the recurring "STR fixture files not committed" pattern (same class as the 2026-08-18 missing `test.xlsx`).
  - **RESOLUTION**: Created a **committed** fixtures dir `backend/tests/fixtures/str/` holding `airbnb_pending.csv` + `airbnb_08_2026-09_2026.csv` (verified NOT git-ignored). Guest names anonymised to `Guest NN` placeholders (no real PII in git) via a **byte-preserving** substitution that only rewrites the `Gast` column and leaves BOM, spacing, amounts, and the quoted European `"42,59"`/`"13,25"` Servicekosten cells untouched — a first attempt via a `csv` round-trip corrupted those quoted cells and shifted columns (dropped the anchor sums), so that was discarded. Repointed both test files' `_SAMPLES_DIR` from `../../../.agent-output` to `../fixtures/str`. Anchored sums reproduce exactly: `HMXDT8WAFF → gross 351.47 / fee 42.59` (274.80+76.67, "42,59"+0.00) and `HMTFCHFWTP → gross 109.36 / fee 13.25` (85.50+23.86, "13,25"+0.00).
  - **VERIFIED**: `test_str_airbnb_parser.py` + `test_str_processor_airbnb_scan.py` = **37 passed** (was 7 errors + 7 failures). Broader regression `pytest tests/unit -k "str_ or airbnb"` = **334 passed, 0 failed**.

---

## High — running tests that fail + CI-blocking lint

- [x] **H1. Make projection property tests use `mock_db` instead of real DB connections (8 failures).** [M] ✅ DONE 2026-09-26 — fixed by dependency injection into the tests; guardrail NOT relaxed.
  - **File(s)**: `backend/tests/unit/test_projection_convergence_props.py`, `test_projection_reader_isolation_props.py`, `test_projection_sync_idempotence_props.py`, `test_projection_sync_props.py`; plus the projection code under test (`backend/src/services/projection_sync.py`, projection reader/builder) that acquires the connection.
  - **Action**: `RuntimeError: Unit tests must not create real database connections`. Ensure each property test requests the `mock_db` fixture from `conftest.py`, and that the projection code accepts an injected connection rather than self-constructing one the fixture cannot intercept.
  - **Verification**: `pytest tests/unit/test_projection_sync_props.py tests/unit/test_projection_sync_idempotence_props.py tests/unit/test_projection_convergence_props.py tests/unit/test_projection_reader_isolation_props.py -q` → all pass.
  - **ROOT CAUSE (two layers, both in the test fakes — no production change needed)**: (1) The 4 files injected `source` and `table=` into `ProjectionSync` but omitted the third seam `parameter_service=`. For a *projecting* tenant (an active SAM module — present in every falsifying example), `sync_administration` builds C2 config rows and lazily constructs `ParameterService(DatabaseManager(test_mode=False))`, whose eager pool init calls `mysql.connector.connect` → tripped by the `tests/unit/conftest.py` autouse connection guard. The already-green example tests in `test_projection_sync.py` inject `parameter_service=FakeParameterService()`; the property files did not. (2) After injecting that, a second latent gap surfaced: `sync_administration` → `_reconcile_scopegrants` → `_list_scopegrant_sort_keys` calls `self.table.query("#pk = :pk AND begins_with(#sk, :sk_prefix)", ...)`, but the inline `FakeTable`s either lacked `query` entirely (`sync_props`, `idempotence_props`) or only accepted a boto3 `Key().eq()` condition object (`convergence`, `reader_isolation`) — so a projecting tenant hit `AttributeError: 'FakeTable' object has no attribute 'query'` / an unexpected-kwarg mismatch.
  - **RESOLUTION**: (1) Added a local `FakeParameterService` (read-only `get_param` → `None`, empty-is-valid) to each of the 4 files and injected it at all 9 `ProjectionSync(...)` construction sites, matching the established pattern in `test_projection_sync.py`. (2) Added / upgraded each `FakeTable.query` to handle BOTH call styles — the reader's boto3 `Key('tenant_id').eq(...)` condition object AND the sync's string expression `"#pk = :pk AND begins_with(#sk, :sk_prefix)"` (partition `:pk` + SK prefix `:sk_prefix`), returning a single-page tenant-scoped `{"Items": [...]}`. The connection guard was left untouched.
  - **VERIFIED**: the 4 property files (8 tests) now pass (0 failures observed in the run; guard no longer trips, `query` resolves).

- [x] **H2. Fix Airbnb header/classification returning `None` (7 failures).** [M] ✅ DONE 2026-09-26 (shared root cause with C2)
  - **File(s)**: `backend/tests/unit/test_str_processor_airbnb_scan.py`; Airbnb header-column / `is_airbnb` / `is_realised` detection helper in the STR processor.
  - **Action**: Header detection returns `None` for the pending/realised samples (BOM/whitespace strip, realised markers), so classification hits `assert None is not None` / `assert False is True` / `TypeError: argument of type 'NoneType' is not iterable`. Make the header extractor return the real header row for the committed samples; guard `in`-checks against `None`.
  - **Verification**: `pytest tests/unit/test_str_processor_airbnb_scan.py -q` → all pass.
  - **RESOLUTION**: Same root cause and fix as C2 — the `None` header was simply the git-ignored sample being absent, not a detection bug in `_airbnb_header_columns`/`_is_airbnb_file`/`_airbnb_is_realised`. Repointing to the committed `backend/tests/fixtures/str/` fixtures resolved all 7. `test_str_processor_airbnb_scan.py` = **14 passed** (part of the 37 above). No production code change was needed.

- [x] **H3. Fix MembersPage empty-rows + region badge regression (4 failures).** [M] ✅ DONE 2026-09-26 — fix was in the STALE TESTS, not the product (see deviation note).
  - **File(s)**: `frontend/src/__tests__/MembersPage.test.tsx`, `frontend/src/pages/MembersPage.tsx` (+ its members service / row + region-badge rendering).
  - **Action**: `nameColumnOrder()` returns `[]` (no rows) and no region `<span>` for "Noord". Determine whether the mocked `GET /members` envelope changed, the region badge stopped rendering as a `<span>`, or a data-load regression empties the table. Restore row rendering + region badge; keep default sort `Jan, Marie, Piet`.
  - **Verification**: `cd frontend && npx vitest run src/__tests__/MembersPage.test.tsx` → all pass.
  - **ROOT CAUSE (test drift from INTENTIONAL product changes — rows were NOT empty)**: git commit `ea6e4ab` deliberately changed the region cell from a purple Chakra `<Badge>` (renders `<span>`) to plain `<Td>` text; git commit `3dde030` deliberately prepended `member_number` (Lidnummer) as the first compact column. The tests were stale: `regionBadge()` searched for a `<span>` (now none), and `nameColumnOrder()` read `cell[0]` (now member_number, not the name). The rows render fine — `waitForRows()` passed throughout.
  - **⚠️ DEVIATION from task wording**: the task said "restore row rendering + region badge", but that premise was based on the CI symptom, not the cause. The `<Badge>` removal and the Lidnummer column are intentional product decisions (committed), so reverting them would undo shipped UI. Instead I updated the STALE TESTS to match current product: `regionBadge()` now finds the region value in its `<td>` cell (disambiguating from the filter `<option>`), and `nameColumnOrder()` now finds the name cell by matching known names rather than a fixed column index. No product code changed.
  - **VERIFIED**: `MembersPage.test.tsx` + `MembersPage.viewContexts.test.tsx` pass (vitest exit 0).

- [x] **H4. Fix BankingFileUpload zero-Revolut abort path (2 failures).** [M] ✅ DONE 2026-09-26 — fix was in the STALE TEST; the spec's "invariant" was itself the retired behavior (see deviation note).
  - **File(s)**: `frontend/src/components/banking/__tests__/BankingFileUpload.account-resolution-preservation.test.tsx`, `frontend/src/components/banking/BankingFileUpload.tsx` (account-resolution logic).
  - **Action**: With zero Revolut accounts configured, a Revolut-file upload must show the "no configured account" error and **not** open the account-selection dialog. Component currently renders the dialog with non-Revolut accounts. Restore the invariant: no Revolut accounts ⇒ no dialog + error (also satisfies the property test, seed 125779012).
  - **Verification**: `cd frontend && npx vitest run src/components/banking/__tests__/BankingFileUpload.account-resolution-preservation.test.tsx` → all pass.
  - **ROOT CAUSE (contradictory tests; the spec's invariant is the OLD behavior)**: `BankingFileUpload.tsx` `resolution.status === 'none'` branch now splits on the known-accounts list: `knownAccounts.length === 0` → error `noAccountConfigured` + abort; `knownAccounts.length > 0` → **open the account popup populated with ALL known accounts, no error**. The sibling `BankingFileUpload.no-match-popup-bug.test.tsx` (4 tests, currently PASSING) explicitly documents this popup fallback as the fixed-away behavior and calls the old "abort + error" path the bug. The failing preservation test fed 2 non-Revolut accounts (non-empty list) yet asserted the old abort path — directly contradicting the ratified behavior.
  - **⚠️ DEVIATION from task wording**: the task said "restore the invariant: no Revolut accounts ⇒ no dialog + error". That invariant was intentionally retired (the popup fallback is the shipped behavior, ratified by the passing no-match-popup-bug test). Reverting the component would re-introduce the documented bug. Instead I updated the STALE preservation test to the current behavior: a Revolut upload with no REVO match but a NON-EMPTY known list opens the popup and shows no error; the `noAccountConfigured` error is reserved for the truly-empty list (covered elsewhere). No product code changed.
  - **VERIFIED**: `BankingFileUpload.account-resolution-preservation.test.tsx` = 10 passed.

- [x] **H5. Clear the 13 auto-fixable ruff lint errors (CI-blocking).** [S] ✅ DONE 2026-09-26
  - **File(s)**: `src/services/members_config_validation.py` (UP035, RUF022, 7×UP045), `src/routes/tenant_admin_scope.py` (RUF100), `src/services/user_tenant_scope_service.py` (RUF100), `src/services/projection_builder.py` (I001), `src/services/scope_canon.py` (RUF022).
  - **Action**: `ruff check --fix src/` (ruff 0.16.5). Review the diff — UP045 rewrites `Optional[X]`→`X | None`, RUF100 drops stale `# noqa: BLE001`, RUF022 sorts `__all__`, UP035 moves `Iterable`/`Mapping` to `collections.abc`, I001 sorts imports.
  - **Verification**: `ruff check src/` → only the single SIM102 remains (see H6), then 0 after H6.
  - **RESOLUTION**: Local ruff confirmed 0.16.5 (matches CI). `ruff check --fix` fixed **15** (the 13 auto-fixable + 2 more that became fixable once imports were sorted), leaving exactly the 1 SIM102 for H6.

- [x] **H6. Manually resolve the one non-fixable lint error (SIM102).** [S] ✅ DONE 2026-09-26
  - **File(s)**: `backend/src/services/members_config_validation.py:223`.
  - **Action**: Collapse the nested `if` into a single `if a and b:` (SIM102), preserving behaviour.
  - **Verification**: `ruff check src/services/members_config_validation.py` → 0 errors.
  - **RESOLUTION**: Folded the nested `if not spec.get("choices") and not spec.get("options")` into the enclosing `elif isinstance(spec, Mapping) and spec.get("type") == "enum"` as one combined condition. Behaviour preserved (short-circuits identically).

- [x] **H7. Fix ruff format on 6 files (CI-blocking).** [S] ✅ DONE 2026-09-26
  - **File(s)**: `src/routes/str_routes.py`, `src/routes/tenant_admin_scope.py`, `src/services/members_config_validation.py`, `src/services/projection_sync.py`, `src/services/scope_canon.py`, `src/services/user_tenant_scope_service.py`.
  - **Action**: `ruff format src/`. Pure line-wrap reflows, no semantic change. Run after H5/H6 to avoid re-reflow churn.
  - **Verification**: `ruff format --check src/` → `301+ files already formatted`, 0 would-reformat.
  - **RESOLUTION**: `ruff format` reformatted exactly the 6 listed files. Final gate green: `ruff check` → "All checks passed!"; `ruff format --check` → "307 files already formatted". Behaviour unchanged — 88 tests across the touched modules (members_config / scope_canon / projection_builder / tenant_admin_scope / user_tenant_scope) pass.

---

## Medium — related / follow-on

- [x] **M1. Fix MembersPage view-context default/empty-columns assertion (1 failure).** [S] ✅ DONE 2026-09-26 (same root cause as H3)
  - **File(s)**: `frontend/src/pages/__tests__/MembersPage.viewContexts.test.tsx:382`, `MembersPage.tsx` view-context/column derivation.
  - **Action**: `expected false to be true` — default/empty context must synthesize the fixed column set (compact/full switch). Likely resolved alongside H3; verify independently.
  - **RESOLUTION**: Same stale-`<span>`-Badge assumption as H3 — the line-382 assertion required a `<span>` carrying "Noord" (the removed Badge). Updated it to assert the region value is present as a `<td>` cell instead. Verified green in the same `MembersPage.viewContexts.test.tsx` run.
  - **Verification**: `cd frontend && npx vitest run src/pages/__tests__/MembersPage.viewContexts.test.tsx` → pass.

- [x] **M2. Add an import-boundary guard test for the SAM/Lambda plane.** [S] ✅ DONE 2026-09-26 (prevents C1 from recurring)
  - **File(s)**: `sam/tests/` (new test), or a CI import-smoke step.
  - **Action**: Add a test asserting `import sam.pretokengen.handler` (and key `auth.cognito_utils` usage) succeeds without Flask installed, so re-coupling Flask into the Lambda import path fails fast in future runs.
  - **Verification**: `pytest sam/tests -q` includes and passes the new guard.
  - **RESOLUTION**: Added `sam/tests/test_import_boundary_no_flask.py`. It runs each Flask-free Lambda import (`auth.cognito_utils`, `auth.entitlement_claim_codec`, `auth.entitlement_resolver`, `sam.pretokengen.handler`) in a **child process with a `meta_path` finder that blocks `flask`**, so the guard reproduces the CI/Lambda Flask-free condition deterministically regardless of what the local venv has installed. Includes a sanity test proving the block itself works (guards against vacuous passes). **2 passed** locally.

---

## Low — hygiene / prevention

- [x] **L1. Keep ruff pinned to 0.16.5 in CI and `requirements-test.txt`.** [S] ✅ DONE 2026-09-26
  - **File(s)**: `backend/requirements-test.txt` (or equivalent), CI workflow `full-test-suite.yml`.
  - **Action**: Pin `ruff==0.16.5` so lint counts stay reproducible and rule expansions are deliberate (repeat of Lessons Rule 8 / L4 from 09-03).
  - **Verification**: `ruff --version` → `ruff 0.16.5` locally and in CI.
  - **RESOLUTION**: The `ruff==0.16.5` pin was already present in `requirements-test.txt` AND in both workflows (`backend-code-quality.yml`, `full-test-suite.yml`). The real risk was drift across the 3 hardcoded copies. Marked `requirements-test.txt` as the CANONICAL pin with a comment, and added a "keep in exact sync — bump deliberately" comment beside the `pip install ruff==0.16.5` line in both workflows. Local ruff confirmed 0.16.5 (matches CI). Left the workflows installing ruff explicitly rather than via `-r requirements-test.txt` (that would pull pytest/hypothesis into the lint-only job unnecessarily).

- [x] **L2. Commit a canonical, format-accurate Airbnb sample set + a fixture-freshness note.** [S] ✅ DONE 2026-09-26 (prevents C2/H2 recurrence)
  - **File(s)**: Airbnb sample fixtures used by `test_str_airbnb_parser.py` / `test_str_processor_airbnb_scan.py`.
  - **Action**: Store known-good `airbnb_pending.csv` / realised samples matching the current export layout, and document where they come from so a format shift is a deliberate fixture update, not a silent break.
  - **Verification**: `pytest tests/unit/test_str_airbnb_parser.py tests/unit/test_str_processor_airbnb_scan.py -q` → green.
  - **RESOLUTION**: The canonical samples were already committed under `backend/tests/fixtures/str/` in C2 (anonymized, format-accurate, verified NOT git-ignored). Added `backend/tests/fixtures/str/README.md` documenting provenance, file shapes, the anchored gross/fee expectations table (HMXDT8WAFF→351.47/42.59, HMTFCHFWTP→109.36/13.25), the PII anonymization rule (Gast column only, byte-preserving — never a csv round-trip), and a step-by-step refresh procedure tied to the Change-With-Tests Contract. The 37 Airbnb tests already pass against these fixtures (verified in C2/H2).

---

## Execution order (see dependency-graph.json)

1. **C1, C2** first — SAM cannot collect and the Airbnb parser errors block setup.
2. **H1–H7** — the running failures + lint (H5→H6→H7 in that order for lint).
3. **M1, M2** — MembersPage view-context (verify after H3), SAM import guard (after C1).
4. **L1, L2** — prevention, any time after the corresponding fixes.

## Full-suite verification (after all tasks)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `pytest sam/tests -q`
- Frontend: `cd frontend && npx vitest run`
- Lint: `cd backend && ruff check src/ && ruff format --check src/`
- Or push and confirm the `full-test-suite.yml` run goes green.
