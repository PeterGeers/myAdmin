# Implementation Plan: Members config projection fix + `view_contexts` retirement

## Overview

Two workstreams. **A** (tasks 1–4) hardens the projection write (R1). **B** (tasks 5–7) retires `view_contexts` (R2). A and B are independent; A lands first so the ad-hoc `died` re-sync can be done. Task 8 is the final checkpoint before promoting `test` → `main`. Change-with-tests applies throughout.

## Task Dependency Graph

```
A:  1 ──▶ 2 ──▶ 3 ──▶ 4
B:  5 ──▶ 6 ──▶ 7      (independent of A)
              4, 7 ──▶ 8  (checkpoint needs A and B complete)
```
- Task 8 depends on both 4 and 7.

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "5"] },
    { "wave": 2, "tasks": ["2", "6"] },
    { "wave": 3, "tasks": ["3", "7"] },
    { "wave": 4, "tasks": ["4"] },
    { "wave": 5, "tasks": ["8"] }
  ],
  "dependencies": {
    "2": ["1"], "3": ["2"], "4": ["3"],
    "6": ["5"], "7": ["6"],
    "8": ["4", "7"]
  }
}
```

## Tasks

## A. Projection write: content-driven + validate-before-write (R1)

- [x] 1. Write the exploration + property tests for the content-gate (BEFORE the fix)
  - [x] 1.1 Reproduce the exact wedge as a failing test: stored `config#fields` = 6-value
    `membership.status` at version `V`; source overlay = 7-value (incl. `died`) at the SAME
    version `V`; assert a sync WRITES the 7-value content. EXPECTED: fails on current code
    (strict-greater gate skips) — this confirms the bug.
  - [x] 1.2 Property P2 (idempotent): for an unchanged source, a re-sync writes nothing and
    leaves the stored row byte-identical.
  - [x] 1.3 Property P4 (concrete regression): a tenant overlay authoring `membership.status`
    incl. `died` projects `overrides["membership.status"]` containing `died`, same as `gender`.
  - Use in-memory fakes (fake projection table + fake `ParameterService`); reuse existing
    projection test fakes where present.
  - _Requirements: 1.2, 1.3, 1.6, 1.8_

- [x] 2. Build from a coherent (uncached) source in the sync run
  - [x] 2.1 Ensure `ProjectionSync.sync_administration` builds rows from a non-stale param read
    (fresh `ParameterService` for the run, or invalidate the members namespace for the tenant
    before building). Do not change the builders' output shape.
  - [x] 2.2 Add/adjust a `ParameterService` cache-invalidation seam if needed (uncached read or
    `invalidate(namespace, tenant)`), with a unit test proving a post-write read is fresh.
  - _Requirements: 1.1, 1.7_

- [x] 3. Make the write decision content-driven; keep version for recording/ordering
  - [x] 3.1 Change `_conditional_put` (or its caller) to read the full stored item and compare
    CONTENT (semantic payload, excluding `version`/bookkeeping; canonicalized stable JSON or a
    content hash). Write when stored is absent OR content differs; skip when equal.
  - [x] 3.2 Decide + implement the datastore concurrency guard per design A3 (prefer: drop the
    strict-greater version condition; rely on serial in-process drain + last-writer-wins). Keep
    the benign no-op handling for a true conditional-check failure. Keep `version`/`updated_at`
    on the row for recording.
  - [x] 3.3 Confirm generality: the change is in `ProjectionSync`/shared seam so it applies to
    `config#fields`/`config#scope`/`config#mail` alike (not a status special-case).
  - [x] 3.4 Update any existing `projection_sync` tests that asserted the strict-greater gate to
    the content-gate behaviour (align to intended new behaviour; never weaken). If two tests
    contradict, STOP and surface it.
  - _Requirements: 1.2, 1.3, 1.5, 1.6, 1.7_

- [x] 4. Validate-before-write (loud, never silent-stale)
  - [x] 4.1 Confirm/extend `validate_items` so a structurally incomplete/malformed `config#*`
    row is REJECTED (raises) before any put; a failing build surfaces through the existing
    `_project_tenant_change` outcome, not a stale-leave. Add a test for the reject path.
  - [x] 4.2 Re-run task-1 tests: the wedge-reproduction now PASSES (fix validated); P2/P4 pass.
  - _Requirements: 1.4_

## B. Retire `view_contexts` (R2 — Phase-2 step d)

- [x] 5. Data + projection cleanup migration
  - [x] 5.1 Add a migration under `backend/src/migrations/` (pattern:
    `migrate_overrides_to_fixed_overrides.py`): `administration`-scoped, dry-run default,
    `--apply` to write, idempotent; deletes `scope='tenant'` / `namespace='members'` /
    `key='view_contexts'` rows. Parameterized queries. Summary `{scanned, deleted}`.
  - [x] 5.2 Remove `config#views` projection residue (delete stored `sk=config#views` rows per
    tenant, and/or confirm the removed builder + reconcile no longer emit it).
  - [x] 5.3 Migration unit test: dry-run makes no change; `--apply` deletes only targeted rows;
    idempotent re-run is a no-op.
  - _Requirements: 2.1, 2.6_

- [x] 6. Remove the Flask-plane view-context builder/modules (if any remain)
  - [x] 6.1 Delete `build_config_views_row` + any view-context domain/validation modules and
    their wiring in `projection_sync.py` / `_projection_config_builders.py`; the sync no longer
    emits `config#views`.
  - [x] 6.2 Update/remove the paired tests (change-with-tests).
  - _Requirements: 2.3, 2.6_

- [x] 7. Remove the frontend `view_contexts` reference
  - [x] 7.1 Remove `view_contexts` from `MEMBERS_PARAM_KEYS` and `MEMBERS_PARAM_TO_CONFIG_ID`
    in `frontend/src/services/membersConfigService.ts`.
  - [x] 7.2 Update `membersConfigService.test.ts` (re-point the generic save-helper test to a
    surviving key, e.g. `field_overlay`; do not weaken).
  - [x] 7.3 Repo-wide search (excluding `.aws-sam/**`, `node_modules`, `.kiro/specs`,
    `.kiro/steering`): assert NO live reader and NO authoring-key declaration of `view_contexts`
    remains. Confirm Session Columns + `default_page_size` untouched.
  - _Requirements: 2.2, 2.4, 2.5_

## Checkpoint

- [ ] 8. Full verification before `test` → `main`
  - [x] 8.1 Run backend pytest (incl. the new projection + migration tests) and the SAM suite
    (`sam/pytest.ini`) — all green.
  - [x] 8.2 Run the frontend vitest suite — green.
  - [x] 8.3 Confirm the two pre-existing unrelated frontend typecheck errors
    (`PublicApplicationForm.axe.test.tsx`, `useApplicationsInbox.test.ts`) are either fixed or
    explicitly deferred so they do not block the gate. (Decide with the user.)
    DECISION: DEFERRED (pre-existing, unrelated to this spec; does not block the gate).
  - [ ] 8.4 Ad-hoc (NOT a code task): re-sync h-dcn on `test` and confirm `died` appears in the
    member modal + TenantAdmin. (R1 makes this a one-shot, not a recurring manual bump.)
    DEFERRED - POST-DEPLOY: chicken-and-egg (the fix must be on test before it can be verified
    there). Projection writer is Flask-plane (Railway TEST backend), so this runs after
    backend/** lands on test; died read-back is observed via the unchanged SAM Members
    field-config endpoint + the local dev SPA (VITE_APP_ENV=test, no hosted TEST frontend).
    Not runnable from the workspace pre-merge.
  - _Requirements: 1.8, 2.4, 2.5_

- [ ] 9. CI/CD surface (per 43-cicd-deploys.md; required by 40-spec-workflow.md)
  - [x] 9.1 Quality gates: scoped bugfix -> changed-file paired tests are the local gate
    (change-with-tests; no full-suite dispatch required per the 43 bugfix-scope note). Per-PR
    gates on the test->main PR are CodeQL + GitGuardian (Backend/Frontend CI are
    disabled_manually); the nightly Full Test Suite is the broad gate on GitHub.
  - [x] 9.2 Deploy path: changes are backend/** (Flask/Railway plane) + frontend/**. NO
    deploy-sam-*.yml fires (no sam/members/** or sam/shared/** changed - the projection writer
    is the Railway backend, not the SAM Lambda). deploy-frontend.yml fires only on main
    (frontend/**) -> production Pages; TEST frontend is the local dev server.
  - [x] 9.3 No new/changed workflow, samconfig.toml, or IAM-OIDC wiring needed by this spec.
  - [ ] 9.4 Promote test->main: ONE reviewed MERGE-COMMIT PR, CodeQL + GitGuardian green,
    preview prod changesets (none expected - no SAM/stateful change). Merge to main IS a
    production deploy.
  - _Requirements: governance gate per 40/43_

## Notes

- Change-with-tests contract applies to every behaviour edit (update the paired test in the same change; never weaken an assertion; surface contradicting tests).
- A is correctness-sensitive (shared by every `config#*` row) — hence the property tests in task 1.
- The `died` unblock (8.4) is operational, not a code task; R1 makes it a one-shot.
- The `membership_type` catalog management UI is a SEPARATE spec, not tracked here.
- LESSON (R1 root cause): the wedge was a VERSION/CONTENT DESYNC - a config#* row held stale
  content stamped at the CURRENT source version, so a strictly-greater version gate could
  never heal it. Fix = content-driven WRITE DECISION (canonical semantic payload compare,
  version excluded) + build from a non-stale (cache-invalidated) param read.
- LESSON: a version/timestamp proxy must never be the SOLE gate for WHETHER to write a
  derived/projected row - compare the content it guards. Datastore conditional kept only as a
  concurrency backstop (dropped: serial in-process drain makes last-writer-wins safe).
- LESSON: config#* rows are UPSERT-ONLY (scopegrant reconcile does not sweep them), so
  retiring a row type (config#views) needs an EXPLICIT residue delete, not a reconcile pass.
