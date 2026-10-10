# Implementation Plan

## Overview

Fix all failing tests and lint/format errors identified in the 2026-10-10 Full Test Suite CI run (#60, id `38056285364`, branch `test` @ `c4e30fab`, `workflow_dispatch`, ❌ failure). Three jobs are red — Backend Full Test Suite (1 failed), Frontend (3 failed / 2 files), Backend Lint & Static Analysis (3 ruff + 2 format); SAM ✅. Every failure traces to new **Members feature work** landed on the `test` branch without the full suite + lint run together: F1 is a stale expected-set test, F2–F4 are a Members-UI behaviour cluster, and the lint/format findings are un-linted new files.

Tasks are organized by priority: **Critical** (tests can't run), **High** (assertion failures + CI-blocking lint), **Medium** (flaky / carried-over), and **Low** (prevention / hygiene). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h. Verification commands assume `cd backend && source .venv/bin/activate` (backend) / `cd frontend` (frontend). No collection errors this cycle → **no Critical tasks**.

## Tasks

### Critical — collection / import errors (nothing else runs until these pass)

_None._ No collection or import errors this cycle — the backend failure is a runtime assertion, SAM collects and passes, and the frontend failures run.

### High — running tests that fail + CI-blocking lint (CI-blocking)

- [x] 1. **H1. Update the stale expected-set in `test_parameter_admin_routes.py` for the three new Members `mail_*` config keys (F1, 1 failing test).** [S] — the parameter schema now returns `mail_certified` / `mail_domain` / `mail_local_part`; the test's hard-coded expected set was not updated. Fix is in the **test**, not production.
  - **Why**: `test_schema_members_tenant_permits_members_namespace` asserts `set(params.keys()) == {…}` (`test_parameter_admin_routes.py:567`) with a frozen key set `{field_overlay, mail_enabled, scope_dimensions, view_contexts}`. The schema endpoint now also returns `mail_certified`, `mail_domain`, `mail_local_part` (the new Members mail namespace — same feature that added `members_config_validation.py`'s `mail_local_part`/`mail_certified` validators). → `AssertionError` with those three as extra items in the actual set.
  - **File(s)**: `backend/tests/unit/test_parameter_admin_routes.py` (~line 567, `TestParameterSchemaEndpointMembersGating`). Confirm against the schema source that the three keys are intentional before adding them.
  - **Action**: Add `mail_certified`, `mail_domain`, `mail_local_part` to the expected set so it matches the schema the endpoint returns. Do **not** change production. Verify the keys are the intended Members-mail namespace (cross-check the schema definition / `members_config_validation.py`).
    ```bash
    cd /home/peter/projects/myAdmin/backend && source .venv/bin/activate
    grep -rn "mail_certified\|mail_domain\|mail_local_part" src/ | head -20
    ```
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    pytest tests/unit/test_parameter_admin_routes.py::TestParameterSchemaEndpointMembersGating -q   # -> 0 failed
    ```

- [x] 2. **H2. Fix the Members tenant-switch role re-resolution so "Members Overview" surfaces after switching to `h-dcn` (F2, 1 failing test).** [M] — the accessible "Members Overview" button is not rendered after the in-app tenant switch.
  - **Why**: `tenantSwitchRoles.test.tsx > re-resolves roles on switch to h-dcn` expects, after switching to `h-dcn`, that "Tenant Administration" hides and a button named `/Members Overview/` appears (and the fetch carries `X-Tenant: h-dcn`). → `TestingLibraryElementError: Unable to find an accessible element with the role "button" and name /Members Overview/`. Either the role re-resolution didn't surface the Members Overview nav entry, the label/role changed, or the `h-dcn` nav gating changed.
  - **File(s)**: the tenant-switch role resolver + nav gating (`frontend/src/context/` TenantContext / role resolution; the Members Overview nav item component). Test: `frontend/src/context/__tests__/tenantSwitchRoles.test.tsx`.
  - **Action**: Reproduce, then determine whether the regression is in production (role re-resolution / nav gating no longer exposes Members Overview for `h-dcn`) or the test (label/role drift). Fix the real cause — prefer the production path if the switch genuinely stopped surfacing the entry; only adjust the test if the accessible name/role legitimately changed.
    ```bash
    cd /home/peter/projects/myAdmin/frontend
    npx vitest run src/context/__tests__/tenantSwitchRoles.test.tsx 2>&1 | tail -30
    ```
  - **Verification**:
    ```bash
    cd frontend && npx vitest run src/context/__tests__/tenantSwitchRoles.test.tsx   # -> 0 failed
    ```

- [x] 3. **H3. Fix Members session-column filter composition so excluded rows are filtered out (F3/F4, 2 failing tests — one cluster).** [M] — a row that should be filtered out (`Marie`) stays in the DOM when a chosen-column filter is AND-composed with the global search, and when the saved column list survives a view-context switch.
  - **Why**: both `MembersPage.sessionColumns.test.tsx` failures are `expect(element).not.toBeInTheDocument()` but `found <td>` — a row expected to be excluded is still rendered. With global search `"regulier"` the stats strip reads `total 3 / filtered 2`, yet an extra row (`Marie`) remains. The AND-composition of a chosen-column filter with the global all-fields search (R2.4) and the view-context-switch column retention (OQ-1/R3.3) are not narrowing rows as expected. Treat as **one shared cause** (filter composition).
  - **File(s)**: the Members session-column filter path (`frontend/src/pages/MembersPage.*` / the column-chooser + global-search filter composition logic). Test: `frontend/src/pages/__tests__/MembersPage.sessionColumns.test.tsx`.
  - **Action**: Reproduce both, find where the chosen-column filter composes (AND) with the global search and where the saved column list is re-applied after a view-context switch. Fix the composition so excluded rows are actually dropped. Determine production-vs-test the same way as H2 (prefer fixing the filter if the behaviour genuinely broke).
    ```bash
    cd /home/peter/projects/myAdmin/frontend
    npx vitest run src/pages/__tests__/MembersPage.sessionColumns.test.tsx 2>&1 | tail -40
    ```
  - **Verification**:
    ```bash
    cd frontend && npx vitest run src/pages/__tests__/MembersPage.sessionColumns.test.tsx   # -> 0 failed
    ```

- [x] 4. **H4. Clear the 3 CI-blocking ruff-lint errors in the new Members routes (G201 ×2, RUF100 ×1).** [S] — all in new sender-identity / analytics-audit routes; 1 auto-fixable, 2 a trivial manual idiom swap.
  - **Why**: Backend Lint is red on 3 ruff errors (CI-blocking, same priority as a test failure):
    - `members_sender_identity_routes.py:90:16` and `:156:16` — `G201`: use `logger.exception(msg)` instead of `logger.error(msg, exc_info=True)` inside the `except` block.
    - `members_analytics_audit.py:107:29` — `RUF100`: unused `# noqa` directive (for a non-enabled `BLE001`) — remove the directive (auto-fixable).
  - **File(s)**: `backend/src/routes/members_sender_identity_routes.py`, `backend/src/routes/members_analytics_audit.py`.
  - **Action**:
    ```bash
    cd /home/peter/projects/myAdmin/backend && source .venv/bin/activate
    ruff check src/routes/members_analytics_audit.py --fix        # clears RUF100
    # Manually rewrite the two G201 sites: logger.error(<msg>, exc_info=True) -> logger.exception(<msg>)
    ```
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    ruff check src/routes/members_sender_identity_routes.py src/routes/members_analytics_audit.py   # -> All checks passed!
    ```

- [x] 5. **H5. Reformat the 2 ruff-format files from the new Members mail-config feature.** [S] — purely mechanical `ruff format`.
  - **Why**: Ruff Format is red on 2 files: `members_analytics_audit.py:85` (split f-string to collapse) and `members_config_validation.py:411,433` (re-wrap `MembersConfigError({...})` calls). Both are new feature files.
  - **File(s)**: `backend/src/routes/members_analytics_audit.py`, `backend/src/services/members_config_validation.py`.
  - **Action / Verification**:
    ```bash
    cd /home/peter/projects/myAdmin/backend && source .venv/bin/activate
    ruff format src/routes/members_analytics_audit.py src/services/members_config_validation.py
    ruff format --check src/   # -> All files already formatted!
    ```

### Medium — carried-over property assertion (recurrence)

_None._ No 10-05 failure recurred; no carried-over property failures remain this cycle.

### Low — prevention / hygiene

- [x] 6. **L1. Broaden the pre-push guard from `--collect-only` to also run `ruff check` + `ruff format --check` + a changed-path test subset.** [M] — carried forward from 10-03 / 10-04 / 10-05 L1 (**still open**); it would have blocked all of H1, H4, and H5 before push.
  - **Why**: This is the **fourth consecutive cycle** this guard would have prevented the red Backend Lint job (and the stale-expected-set F1). New Members files landed un-linted / un-formatted and a schema key-set grew without its paired test. A pre-push hook that runs `ruff check src/ && ruff format --check src/` plus the tests touching the changed symbols would have caught every one pre-push. (requirements Lessons 2 & 3.)
  - **File(s)**: `scripts/hooks/pre-push`, `scripts/hooks/install-hooks.sh`.
  - **Action**: Add `cd backend && ruff check src/ && ruff format --check src/` and a changed-path `pytest` subset (map edited `src/**` → paired tests, e.g. `python -m backend.scripts.test_maintenance.scoped_runner --git-diff`) to the hook; keep the `SKIP_PREPUSH_*` escape hatch; fail on non-zero.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin
    bash scripts/hooks/pre-push </dev/null; echo "rc=$?"
    # -> exits non-zero while H4/H5 are unfixed on the branch; 0 after they land.
    ```

- [x] 7. **L2. Add a schema/enum key-set ↔ expected-set drift check so growing a key set can't silently break a frozen-set test.** [S] — durable prevention for the F1 class (feature-vs-test drift).
  - **Why**: F1 happened because the parameter schema gained three keys while `test_parameter_admin_routes.py` asserted a hard-coded set. Nothing flagged the divergence until CI. (requirements Lesson 1.)
  - **File(s)**: the test-maintenance drift detector (`backend/scripts/test_maintenance/`).
  - **Action**: Extend the drift detector to find tests asserting `set(x.keys()) == {literal set}` against a schema/config source, and flag when the source's key set no longer matches the literal. Wire into the scanner's `--maintenance-session` list.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin
    python -m backend.scripts.test_maintenance.scanner --maintenance-session 2>&1 | grep -i "key\|set\|schema\|drift" | head
    ```

- [x] 8. **L3. Confirm ruff stays pinned to 0.16.5 (reproducibility guard).** [S] — standing guard carried forward from 10-03 / 10-04 / 10-05.
  - **Why**: CI ran ruff 0.16.5; the 3 lint + 2 format findings are real new debt (not a version drift). Keep local 0.16.5 == CI 0.16.5 so results stay reproducible.
  - **File(s)**: `backend/requirements-test.txt`, `.github/workflows/full-test-suite.yml`, `.github/workflows/backend-code-quality.yml`.
  - **Action / Verification**:
    ```bash
    ruff --version                                   # -> ruff 0.16.5
    grep -rn "ruff==0.16.5" backend/requirements-test.txt .github/workflows/
    ```

## Notes

### Execution order (see dependency-graph.json)

1. **H4 / H5** — clear the 3 ruff-lint + 2 format findings (mechanical; fastest path to a green Backend Lint job).
2. **H1** — add the three `mail_*` keys to the expected set in `test_parameter_admin_routes.py` (clears F1; independent).
3. **H2** — fix tenant-switch role re-resolution so Members Overview surfaces (clears F2).
4. **H3** — fix Members session-column filter composition so excluded rows drop (clears F3/F4; shared cause).
5. **L1 / L2** — broaden the pre-push guard (ruff + changed-path tests) and add the schema-key-set drift check (prevention; directly target the H1/H4/H5 class).
6. **L3** — confirm the ruff pin (standing guard).

### Full-suite verification (re-confirm after H1–H5)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `cd /home/peter/projects/myAdmin && PYTHONPATH=. python -m pytest sam/tests -q`
- Frontend: `cd frontend && npx vitest run`
- Lint + Format: `cd backend && ruff check src/ && ruff format --check src/`
- Or confirm the next `full-test-suite.yml` run is green after H1–H5 land.

### Context

- CI run #60 (id `38056285364`, 2026-10-10 @ `c4e30fab` on `test`, `workflow_dispatch`, ❌ failure). Three red jobs: Backend Full Test Suite (1 failed), Frontend (3 failed / 2 files), Backend Lint & Static Analysis (3 ruff + 2 format). SAM ✅.
- The two backend failures from 10-05 (stale `os` patch, Airbnb `Bevestigingscode`) did **not** recur. No Critical tasks (no collection/import errors) and no Medium tasks (no carried-over property failures) this cycle.
