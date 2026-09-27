# Tasks — Make the Full Test Suite Trustworthy and Green

Ordered, each maps to requirements in `requirements.md`. Local verification commands run from
`backend/` with the venv active unless noted:
`cd backend && source .venv/bin/activate`.

## Status (updated)

**Phases 1–6 complete and individually verified (T1–T12).** Bucket C (the one real,
ours-to-fix failure) is resolved, and the 12 pre-existing failures are fixed too. Remaining:
Phase 7 (T14 full local verify / T15 commit / T16 re-run CI / T17 prove-red / T18 merge).

Verification results so far:
- **T1** ruff lint `All checks passed!` + format clean; touched files' tests pass.
- **T2** deleted `sam/pretokengen/governance_reader.py` + its test (staged for deletion).
- **T3** removed the handler's optional import; `_CONFIG_ERRORS = (DynamoDBConfigError,)`.
- **T4** SAM suite green (exit 0); no lingering refs to the deleted reader.
- **T5/T6** guard is now AST-aware; **positive control** (fake `FROM tenant_modules`) correctly
  FAILS it, clean state PASSES (10 passed), ruff clean on the test file.
- **T7–T9** security-audit fixture authenticates as verified SysAdmin → **113 passed** (was 9
  failing 401s); endpoints' real auth untouched.
- **T10/T11** `deadline=None` on the 3 flaky property tests → **42 passed**, stable.
- **T12** removed `|| true` + added `set -o pipefail` on both CI test steps; YAML valid; the 8
  `if: always()` summary/upload steps intact (artifacts still publish on failure).

## Phase 1 — Lint & format (R1)

- [x] **T1. Confirm ruff clean.** (Already applied locally: `ruff check --fix` + `ruff format`
      on the new S3/S4 files, and one hand-fix `SIM103` in `projection_validator.py`.)
  - Verify: `ruff check src/ --exclude src/validate_pattern/` → `All checks passed!`
  - Verify: `ruff format --check src/ --exclude src/validate_pattern/` → all formatted
  - Re-run the touched files' tests to confirm no behavior change (R1.3):
    `python -m pytest tests/unit/test_projection_validator.py tests/unit/test_projection_validator_props.py -q`

## Phase 2 — Remove the dead MySQL reader from the module plane (R2)

- [x] **T2. Delete the obsolete MySQL reader and its test.**
  - `git rm sam/pretokengen/governance_reader.py`
  - `git rm sam/tests/test_pretokengen_governance_reader.py`
  - Rationale: superseded by `projection_governance_reader.py` (Design Amendment A — read the
    DynamoDB projection, not MySQL). It is the only real S1/S3 contract violation among the
    guard hits.
- [x] **T3. Remove the handler's optional import of the deleted reader.**
  - In `sam/pretokengen/handler.py`, delete the `try/except` block that imports
    `GovernanceConfigError` from `governance_reader` and adds it to `_CONFIG_ERRORS`.
  - Keep `_CONFIG_ERRORS = (DynamoDBConfigError,)` (the projection reader's config error) — that
    is the fail-fast type that matters now.
  - If any `handler.py` docstring names `user_tenant_roles` as *prose*, that's fine (T5 makes
    the guard prose-tolerant); do NOT strip meaningful docs.
- [x] **T4. Confirm the SAM suite still passes** (handler now uses only the projection reader):
  - `cd sam && python -m pytest -q` (uses `sam/pytest.ini`)
  - Expect: PreTokenGen handler + projection-reader tests pass; the deleted reader's test is gone.

## Phase 3 — Make the system-of-record guard precise (R3)

- [x] **T5. Tighten `test_no_sam_source_reads_governance_tables_directly`.**
  - File: `backend/tests/unit/test_s3_system_of_record_scope.py`.
  - Change the check from a blunt substring scan to one that flags a **real SQL access** to a
    governance table and ignores mentions in comments/docstrings. Concretely, before scanning:
    strip Python comments and docstrings (e.g. tokenize and drop `COMMENT`/`STRING` tokens, or
    parse the AST and inspect only string literals that look like SQL), then flag a governance
    table name only when it appears adjacent to a SQL verb (`FROM|JOIN|INTO|UPDATE|TABLE`) or
    inside an `execute_query(...)` call.
  - Intent (R3.2): a genuine `SELECT ... FROM user_tenant_roles` fails the test; a docstring
    that explains "reads the projection of `tenant_modules`" does not.
  - Keep the companion checks (`test_no_sam_source_imports_a_mysql_client`,
    `test_sam_requirements_declare_no_mysql_client`) unchanged.
- [x] **T6. Verify the guard.**
  - `python -m pytest tests/unit/test_s3_system_of_record_scope.py -q` → all pass.
  - Sanity (optional): temporarily add a fake `SELECT ... FROM tenant_modules` string in a
    throwaway `sam/` file and confirm the guard fails, then remove it — proves R3.2.

## Phase 4 — Fix the security-audit endpoint tests (R4)

- [x] **T7. Diagnose the 401.** Read `backend/tests/unit/test_security_audit.py`
      (`TestSecurityEndpointsIntegration` + its `app_with_endpoints` fixture) and the endpoint
      definitions they hit (`/api/security/*`). Determine why the endpoints now require auth
      (verified-JWT/`@cognito_required`) that the fixture doesn't supply. NOTE: these fail on
      `main` too (verified) — it is a stale test harness, not a regression.
- [x] **T8. Fix at the test layer (do NOT weaken endpoint auth — R4.3).** Preferred order:
  1. If the endpoints legitimately require auth, make the fixture authenticate (mock
     `@cognito_required` / inject a verified-claims context / provide a test token), so the
     tests exercise the real authenticated path and assert 200/400 as intended.
  2. If an endpoint is meant to be public, assert the *actual* contract.
  - Use the standard test fixtures (`mock_env`, cognito/claims mocks) per
    `34-backend-testing.md`; no `load_dotenv`, no real connections.
- [x] **T9. Verify:** `python -m pytest tests/unit/test_security_audit.py -q` → all pass.

## Phase 5 — De-flake the property tests (R5)

- [x] **T10. Set a per-test/per-class Hypothesis deadline** on the three flaky tests so first-run
      timing jitter on CI no longer trips `DeadlineExceeded` (R5.2, R5.3). Apply
      `@settings(deadline=None)` (or a generous per-test deadline) to exactly:
  - `tests/unit/test_pdf_processor_properties.py::TestValidAIResultPassthrough::test_output_contains_amount_from_ai_result`
  - `tests/unit/test_pivot_query_builder.py::TestColumnPivotConditionalAggregation::test_pivot_values_in_params`
  - `tests/unit/test_str_booking_multi_import.py::TestProperty3DeduplicationKeepsOnePerBookNumber::test_dedup_produces_unique_book_numbers`
  - Do NOT change a global deadline; leave other property tests' timing guard intact.
  - Do NOT change the strategies or assertions — only the deadline.
- [x] **T11. Verify (run a few times to confirm stability):**
  - `python -m pytest tests/unit/test_pdf_processor_properties.py tests/unit/test_pivot_query_builder.py tests/unit/test_str_booking_multi_import.py -q`

## Phase 6 — Make CI fail on failure (R6) — the key fix

- [x] **T12. Remove the exit-code mask in `.github/workflows/full-test-suite.yml`.**
  - Backend "Run all unit tests" step: the `pytest ... 2>&1 | tee reports/test-output.txt || true`
    swallows failures. Change so the real pytest exit code propagates while still writing the
    log — e.g. use `set -o pipefail` and drop `|| true`, or capture `${PIPESTATUS[0]}` and
    `exit` with it after the summary. The job must go red when pytest fails.
  - Frontend "Run all tests" step: same treatment for the `vitest ... | tee ... || true`.
  - Keep `if: always()` on the "Generate summary" and "Upload ... reports" steps so artifacts
    still publish on failure (R6.2).
- [ ] **T13. (Optional) Consider a PR trigger.** `full-test-suite.yml` is `workflow_dispatch`
      only. Leave as-is for now (manual dispatch), but note in the PR that the suite must be
      dispatched (and now truly gates) before merge. Do not change triggers unless requested.

## Phase 7 — Verify green end-to-end (R7) + ship

- [x] **T14. Full local verification (mirror CI scope):**
  - `cd backend && ruff check src/ --exclude src/validate_pattern/`  → clean
  - `ruff format --check src/ --exclude src/validate_pattern/`         → clean
  - `python -m pytest tests/unit/ -q`                                   → 0 failed
  - `cd ../sam && python -m pytest -q`                                  → pass
  - `cd ../frontend && npx vitest run`                                  → pass
- [x] **T15. Commit the fixes** on `feature/s2-jwt-verification` with a clear message
      (lint/format, remove dead MySQL reader, precise guard, security-audit fixture,
      property-test deadlines, CI exit-code fix). Stage specific files; no logs/scratch.
- [x] **T16. Push and re-run the Full Test Suite** (`gh workflow run full-test-suite.yml --ref
      feature/s2-jwt-verification -f scope=both`). Download artifacts; confirm backend =
      0 failed, frontend = 0 failed, lint = pass, and the job conclusion is now a *true* success.
- [x] **T17. Prove R6 works** (deliberate check): confirm that with the CI fix, a failing test
      would fail the job — either by reasoning from the diff, or a one-off scratch test on a
      throwaway commit that is then reverted. (Optional but recommended.)
- [ ] **T18. Merge PR #14 to `main`** once T14–T16 are green. (Merge commit to preserve the
      steering rename history unless you prefer squash.)

## Decisions (settled)

- **T5 — guard fix: AST/token-aware (DECIDED).** The guard ignores comments/docstrings and only
  flags a governance table name used in real SQL. The explanatory docstrings in
  `projection_governance_reader.py` and `handler.py` stay.
- **T8 — security-audit fix: authenticate the fixture (DECIDED, not a real choice).** Confirmed
  from `backend/src/security_audit.py`: every `/api/security/*` endpoint is intentionally
  `@cognito_required(required_roles=["SysAdmin"])` — the file's own docstring states "every
  security endpoint is SysAdmin-only and verified-JWT protected... None of these may be reachable
  anonymously." The 401s are therefore CORRECT endpoint behavior; the bug is the test fixture
  `app_with_endpoints`, which registers the endpoints without providing auth. Fix = make the
  fixture authenticate as a verified SysAdmin (mock `@cognito_required` / inject verified claims).
  Do NOT make the endpoints public — that would be a security regression contradicting S2 R1.1.
- **T13/T17:** optional hardening; skip for the minimal path to green + merge unless you want them.


## Final result

Run `35231015911` on `feature/s2-jwt-verification` (commit `8967c52`): **all green**.
- Backend: **6291 passed, 10 skipped, 0 failed**
- Frontend: **2386 passed, 12 skipped, 0 failed**
- Ruff Lint ✅ / Ruff Format ✅ / Vulture ✅

Failure chain resolved: 13 → 4 → 0. CI now reports honestly (the `|| true` removal
made the prior run correctly go red, this run correctly green). R1–R7 satisfied.
**T18 (merge PR #14 to main) pending user go-ahead.**
