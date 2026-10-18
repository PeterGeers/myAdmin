# Implementation Plan

## Overview

Make the 2026-10-17 Full Test Suite CI run green (run **#74**, id `39072218600`, branch **`test`** @ `c07927f44`, `workflow_dispatch`, FAILURE). Reds: **1 backend** Hypothesis convergence property, **2 frontend** stale `view_contexts` status-banner tests, and a **CI-blocking backend ruff-format** fail (2 files). SAM green (100%); backend 7330 pass / frontend 3859 pass otherwise. **Every red traces to the two just-merged PRs (#121 projection content-gate + view_contexts retirement, #122 catalog UI).** Dispatched as the `test -> main` promotion gate, so the promotion must not proceed until green (steering 43 — a merge to `main` is a production deploy).

Priority: **Critical** (tests can't run), **High** (assertion failures + CI-blocking lint that gate the release), **Medium** (flaky/non-deterministic), **Low** (prevention/hygiene). Effort: **S** <= 30 min · **M** <= 2 h · **L** > 2 h. No collection/import errors -> no Critical.

## Tasks

### Critical — collection / import errors

_None._ Everything collected and ran (backend 7344, frontend 3873, SAM 100%). The reds are assertion + format failures, not collection errors.

### High — running failures + CI-blocking lint (gates the test -> main promotion)

- [x] 1. **H1. Align the projection convergence property test to the content-driven write gate (or fix a real convergence defect).** [M]
  - **Why**: `backend/tests/unit/test_projection_convergence_props.py::test_projection_converges_after_a_source_change` fails with a Hypothesis ExceptionGroup of 2: `assert item[VERSION_ATTR] == new_version` (`0 == 1`, line 440) and `assert item["is_active"] is expectation["value"]` (`True is False`, line 439). PR #121 made the write decision content-driven and dropped the strictly-greater version datastore gate (design A3 (a), last-writer-wins); the property still encodes the OLD version-monotonic expectation. A change-with-tests miss on a property test.
  - **File(s)**: `backend/tests/unit/test_projection_convergence_props.py` (the generator + the post-sync assertions ~lines 360-445); `backend/src/services/projection_sync.py` only if the counterexample reveals a genuine convergence gap in the content gate.
  - **Action**: Read the Falsifying example; determine whether the property's `version`/`is_active` post-conditions are stale vs the content-gate semantics (version is bookkeeping, content drives the write) or whether the gate genuinely fails to converge for that example. If stale -> realign the property to the intended behaviour (content converges; version no longer strictly-monotonic by write) WITHOUT weakening it. If a real defect -> fix `projection_sync` and keep the property. Use `derandomize=True` + `deadline=None` if any Hypothesis flakiness surfaces (prompt Rule 2). Do NOT weaken to green.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin && source backend/.venv/bin/activate
    python -m pytest backend/tests/unit/test_projection_convergence_props.py backend/tests/unit/test_projection_sync.py backend/tests/unit/test_projection_content_gate.py -q 2>&1 | tail -15
    ```

- [x] 2. **H2. Update the two `MembersConfig` status-banner tests for the retired `view_contexts`.** [S]
  - **Why**: `MembersConfigEditor.test.tsx > status banner > renders the delivered/loaded status...` and `MembersConfigStatus.test.tsx > shows Not yet delivered for a null version` both assert a retired `views` element (`members-config-status-views-badge` / `members-config-status-views`). PR #121 retired `view_contexts`/`config#views`, so the banner no longer renders a `views` row. A change-with-tests miss (service test + key decl were updated; these two were not).
  - **File(s)**: `frontend/src/components/TenantAdmin/MembersConfig/__tests__/MembersConfigEditor.test.tsx`, `frontend/src/components/TenantAdmin/MembersConfig/__tests__/MembersConfigStatus.test.tsx` (+ confirm the component `MembersConfigStatus.tsx` intentionally no longer emits a `views` row).
  - **Action**: Remove/replace the `views` expectations to match the retired reality (status banner now shows `fields`/`scope`/`mail` only). Keep the surviving assertions intact (do not weaken). Grep both files for `views` / `config#views` / `members-config-status-views` and realign every occurrence.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin/frontend
    npx vitest run src/components/TenantAdmin/MembersConfig/__tests__/MembersConfigEditor.test.tsx src/components/TenantAdmin/MembersConfig/__tests__/MembersConfigStatus.test.tsx 2>&1 | tail -8
    ```

- [x] 3. **H3. `ruff format` the two PR #121 files (CI-blocking).** [S]
  - **Why**: Backend Ruff Format FAILED (CI-blocking) — 2 files would be reformatted: `backend/src/migrations/retire_members_view_contexts.py:125` (a `logger.info(...)` wrap) and `backend/src/services/parameter_service.py:673` (an `if` comprehension clause split). Both from PR #121; the pre-commit hook does not run `ruff format`, so the drift reached CI.
  - **File(s)**: `backend/src/migrations/retire_members_view_contexts.py`, `backend/src/services/parameter_service.py`.
  - **Action**: `ruff format` the two files; confirm no behaviour change (format-only). Re-run the paired tests to confirm the reformat did not alter logic.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin && source backend/.venv/bin/activate
    ruff format backend/src/migrations/retire_members_view_contexts.py backend/src/services/parameter_service.py
    ruff format --check backend/ 2>&1 | tail -3   # -> "N files already formatted", no "would be reformatted"
    python -m pytest backend/tests/unit/test_retire_members_view_contexts.py backend/tests/unit/test_parameter_service.py -q 2>&1 | tail -5
    ```

### Medium — flaky / non-deterministic

_None._ No worker OOM / infra flake this cycle. (H1 is a property test but it is a deterministic stale-expectation / possible-defect, classified High because it gates the release.)

### Low — prevention / hygiene

- [x] 4. **L1. Add `ruff format --check` to the backend pre-commit hook (prevent recurrence of H3).** [S] — optional hardening.
  - **Why**: H3 reached CI because the pre-commit hook runs the DB-access guard but not `ruff format --check`. A format-only drift should be caught locally, not at the CI gate.
  - **File(s)**: the backend pre-commit hook (`.githooks/` or the configured pre-commit config — locate it first).
  - **Action**: Add a `ruff format --check backend/ sam/` step to the pre-commit hook (fail fast with the fix command in the message). Confirm it does not slow the hook unreasonably.
  - **Verification**: `git commit` on a deliberately mis-formatted scratch file is rejected with the ruff-format hint (then revert the scratch).

- [x] 5. **L2. Do not promote `test -> main` until the Full Test Suite is green on `test`.** [S] — release gate (steering 43).
  - **Why**: The `test -> main` merge is a production deploy (`deploy-frontend.yml` on `frontend/**`; SAM deploys on `sam/**`). TEST must be verified-green first. This run is red on H1/H2/H3.
  - **File(s)**: n/a (process gate).
  - **Action**: After H1-H3 land on `test`, re-dispatch the suite, confirm `success`, then open ONE `test -> main` PR; CodeQL + GitGuardian green; merge with a **merge commit** (steering 43 promote runbook).
    ```bash
    export GH_PAGER=""
    gh workflow run full-test-suite.yml --ref test
    gh run list --workflow full-test-suite.yml --branch test --limit 1 --json databaseId,status,conclusion
    ```
  - **Verification**: latest `full-test-suite.yml` run on `test` is `success` before opening the promotion PR.

## Task Dependency Graph

The authoritative machine-readable graph is `dependency-graph.json` (nodes H1, H2, H3, L1, L2; edges H1->L2, H2->L2, H3->L2 `blocks`). Wave schedule:

```json
{
  "waves": [
    { "id": 0, "tasks": ["H1", "H2", "H3", "L1"] },
    { "id": 1, "tasks": ["L2"] }
  ]
}
```

- **Wave 0** — **H1** (backend convergence), **H2** (frontend status tests), **H3** (ruff format), **L1** (hook hardening) are mutually independent and can run in parallel.
- **Wave 1** — **L2** (promotion) is blocked by H1 + H2 + H3: TEST is not verified-green until all three reds are fixed.

Recommended order: **H3 (fastest, unblocks the format gate) -> H2 -> H1 -> L1 -> L2**.

## Notes

- CI run **#74** (id `39072218600`, 2026-10-17 21:44 UTC @ `c07927f44` on `test`, `workflow_dispatch`, FAILURE). SAM GREEN; Backend 1 failed / 7330 passed; Frontend 2 failed / 3859 passed; Backend Ruff Format FAIL (CI-blocking).
- **All four reds are change-with-tests / format misses from PR #121 (+ batched with #122)** — not pre-existing debt. See requirements Lessons 1-4.
- The 2 frontend tsc errors are PRE-EXISTING + report-only (deferred in the Members specs); NOT in scope here.
