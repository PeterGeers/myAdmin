# Implementation Plan

## Overview

Make the 2026-10-28 Full Test Suite CI run green (run **#113**, id `40649179164`, branch
**`main`** @ `73ef52e92`, **nightly `schedule`**, FAILURE). The ONLY red is **2 frontend
tests in one file** — `AnalyticsStateNotice.test.tsx` — both throwing
`useTenant must be used within a TenantProvider`. Backend (7422 pass), SAM (100%), and all
backend lint (ruff lint + format + vulture) are GREEN. The red traces to **PR #172**
(pivot CSV filename): `MemberPivotViews` gained a `useTenant()` call, its own paired test was
updated to mock it, but this SIBLING test that mounts the same component was not — a
change-with-tests miss.

Priority: **Critical** (tests can't run), **High** (assertion/throw failures + CI-blocking
lint), **Medium** (flaky/non-deterministic), **Low** (prevention/hygiene). Effort: **S** <= 30 min
· **M** <= 2 h · **L** > 2 h. No collection/import errors -> no Critical. No lint reds -> none at
High for lint.

## Tasks

### Critical — collection / import errors

_None._ Everything collected and ran (frontend 4231 collected; backend 7436; SAM 100%). The
reds are a runtime throw at mount (missing context provider), not a collection error.

### High — running failures (the only reds)

- [x] 1. **H1. Provide the TenantProvider/`useTenant` mock in `AnalyticsStateNotice.test.tsx` so the two PivotViewsArea tests mount again.** [S]
  - **Why**: Both failing tests throw `useTenant must be used within a TenantProvider`
    (`TenantContext.tsx:128`) from `MemberPivotViews.tsx:176`. PR #172 added `useTenant()` to
    `MemberPivotViews` to name the CSV export `{Tenant}-{Pivot}.csv`; the paired
    `MemberPivotViews.test.tsx` was updated to mock `useTenant`, but
    `AnalyticsStateNotice.test.tsx` renders the same component (via PivotViewsArea) and
    neither mocks the hook nor wraps in a `TenantProvider`. Change-with-tests miss on a
    sibling test.
  - **File(s)**: `frontend/src/components/members/analytics/areas/AnalyticsStateNotice.test.tsx`
    (the fix); reference `frontend/src/components/members/analytics/MemberPivotViews.test.tsx`
    for the exact mock shape already in use.
  - **Action**: Mirror the paired test's approach — add
    `vi.mock('../../../../context/TenantContext', () => ({ useTenant: () => ({ currentTenant: 'h-dcn' }) }))`
    at the top of `AnalyticsStateNotice.test.tsx` (adjust the relative path to that file's
    depth), OR wrap the render in a real `<TenantProvider>`. Prefer the mock for parity with
    the sibling test and to avoid pulling in auth/provider setup. Do NOT weaken or delete the
    two assertions — they must still assert "no degradation notice" and "empty-state hint",
    just with the component able to mount. Confirm the relative import depth is correct
    (`areas/` is one level deeper than `MemberPivotViews.test.tsx`).
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin/frontend
    npx vitest run src/components/members/analytics/areas/AnalyticsStateNotice.test.tsx 2>&1 | tail -8
    # then the whole analytics dir to confirm no sibling regressed:
    npx vitest run src/components/members/analytics 2>&1 | tail -8
    ```

### Medium — flaky / non-deterministic

_None._ No worker OOM / infra flake / Hypothesis deadline this cycle.

### Low — prevention / hygiene

- [x] 2. **L1. Grep for OTHER tests that mount `MemberPivotViews` (or PivotViewsArea) without the tenant context, to close the whole class — not just the one red file.** [S] — recurrence guard for Lesson 1.
  - **Why**: The red was a sibling test the paired-test update missed. Other tests may mount
    the same component through yet another entry point and be latently broken (or pass only by
    accident). Close the class, not just the instance.
  - **File(s)**: the frontend test tree under `frontend/src/components/members/analytics/**`.
  - **Action**:
    ```bash
    cd /home/peter/projects/myAdmin/frontend
    grep -rln "MemberPivotViews\|PivotViewsArea" src --include=*.test.tsx
    ```
    For each hit, confirm it either mocks `useTenant` or wraps in `TenantProvider`. Fix any
    that don't (same pattern as H1). If none remain, record that the class is closed.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin/frontend
    npx vitest run src/components/members/analytics 2>&1 | tail -8
    ```

- [ ] 3. **L2. Re-dispatch the Full Test Suite on `main` (and verify `test`) after the fix lands.** [S] — confirm the nightly is green again.
  - **Why**: #113 is the nightly on `main`; a red here means the regression is already on the
    production branch. After H1 lands, confirm the suite is green rather than waiting for the
    next nightly. The fix itself ships through the normal branch -> PR -> `test` -> `main` flow
    (frontend-only change; no SAM/infra).
  - **File(s)**: n/a (process).
  - **Action**: Land H1 on a branch -> PR into `test` (CodeQL + GitGuardian green) -> merge;
    re-dispatch `full-test-suite.yml` on `test`, confirm `success`; then promote `test -> main`
    with a merge commit (steering 43). Optionally dispatch on `main` to clear the nightly red
    immediately.
    ```bash
    export GH_PAGER=""
    gh workflow run full-test-suite.yml --ref test
    gh run list --workflow full-test-suite.yml --branch test --limit 1 --json databaseId,status,conclusion
    ```
  - **Verification**: latest `full-test-suite.yml` run is `success` (frontend 1 file no longer failing).

## Task Dependency Graph

The authoritative machine-readable graph is `dependency-graph.json` (nodes H1, L1, L2; edges
H1->L2, L1->L2 `blocks`). Wave schedule:

```json
{
  "waves": [
    { "id": 0, "tasks": ["H1", "L1"] },
    { "id": 1, "tasks": ["L2"] }
  ]
}
```

- **Wave 0** — **H1** (fix the sibling test) and **L1** (sweep for other unguarded mounts) are
  independent and can run together; L1 may surface more files H1-style.
- **Wave 1** — **L2** (re-dispatch + verify green) is blocked by H1 + L1: the suite is not
  verified-green until the sibling test(s) mount again.

Recommended order: **H1 -> L1 -> L2**.

## Notes

- CI run **#113** (id `40649179164`, 2026-10-28 07:18 UTC @ `73ef52e92` on `main`,
  `schedule`, FAILURE). SAM GREEN (100%); Backend GREEN (7422 passed / 14 skipped); all backend
  lint GREEN. Frontend 2 failed / 4217 passed / 12 skipped — 1 failed file.
- **Both reds are one change-with-tests miss from PR #172** (pivot CSV filename): a sibling
  test mounting `MemberPivotViews` was not given the `useTenant` mock its paired test got. Not
  pre-existing debt.
- The head SHA `73ef52e92` is the PR #173 `test -> main` promotion merge commit, so the
  regression is already on `main`; L2 re-verifies green. See requirements Lessons 1-4.
