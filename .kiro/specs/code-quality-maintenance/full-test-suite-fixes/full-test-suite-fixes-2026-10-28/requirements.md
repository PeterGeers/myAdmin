# Requirements Document

# Full Test Suite Fixes — 2026-10-28 (run #113, nightly on `main`)

## Introduction

CI-analysis spec (not a feature): captures the failures from one **Full Test Suite** run and
defines the fix tasks, per the `prompt-test-suite-results.md` runbook. The outcomes below are
what make the run green again. This run is the **nightly scheduled** run on `main` — i.e. a
post-release signal, so a red here means a regression already reached production branch.

## Glossary

- **Full_Test_Suite**: The `full-test-suite.yml` GitHub Actions workflow (backend + SAM +
  frontend suites + lint/static-analysis), the only automated lint/test gate today
  (nightly cron + dispatch).
- **Change-with-tests miss**: A behaviour change whose paired/related test(s) were not
  realigned in the same change, so the suite goes red later.
- **Paired test**: The test allocated to a product file (e.g. `MemberPivotViews.test.tsx`
  for `MemberPivotViews.tsx`).
- **Sibling test**: A different test that also exercises the changed unit through another
  entry point (here `AnalyticsStateNotice.test.tsx` mounting `MemberPivotViews` via
  PivotViewsArea).
- **Run #113**: The analyzed Full_Test_Suite run (id `40649179164`, nightly `schedule` on
  `main`).

## Source

GitHub Actions **Full Test Suite** run **#113** (id `40649179164`), event **`schedule`**
(nightly cron) on branch **`main`** @ `73ef52e927d5cc1dd419c0837e52cdb3cbe815f9`. That head
SHA is the **PR #173 promotion merge commit** (`test -> main`) that shipped PR #171
(members overview enum-label fix) and PR #172 (pivot CSV filename fix). Conclusion: FAILURE.
Analyzed purely from downloaded CI artifacts (`backend-test-reports`, `sam-test-reports`,
`frontend-test-reports`, `backend-lint-reports`) — no local scans.

## Requirements

### Requirement 1: The Full Test Suite is green again

**User Story:** As a maintainer, I want the nightly Full Test Suite on `main` to pass, so
that `main` is a trustworthy production branch.

#### Acceptance Criteria

1. WHEN `full-test-suite.yml` runs after the fix, THE frontend suite SHALL report 0 failed
   tests (the two `AnalyticsStateNotice.test.tsx` tests pass).
2. THE backend, SAM, and all backend lint checks SHALL remain green (no regression from the
   fix).
3. THE fix SHALL NOT weaken or delete the two affected assertions ("no degradation notice";
   "empty-state hint") — only enable the component to mount.

### Requirement 2: The change-with-tests class is closed, not just the instance

**User Story:** As a maintainer, I want every test that mounts the changed component to be
tenant-context-aware, so that this class of regression does not recur.

#### Acceptance Criteria

1. WHEN searching the frontend test tree for tests that mount `MemberPivotViews` or
   `PivotViewsArea`, THE spec execution SHALL confirm each either mocks `useTenant` or wraps
   in `TenantProvider`.
2. IF any other such test lacks the tenant context, THEN it SHALL be fixed the same way as
   the primary red.

### Requirement 3: Green is re-verified after landing the fix

**User Story:** As a maintainer, I want the suite re-dispatched after the fix, so that the
`main` nightly red is cleared rather than left to the next nightly.

#### Acceptance Criteria

1. WHEN the fix has merged, THE `full-test-suite.yml` workflow SHALL be re-dispatched and
   observed `success` before the spec is considered done.

## Findings summary

| Suite | Result |
| --- | --- |
| **SAM Module-Plane** | GREEN — all tests pass (dots-only, 100%) |
| **Backend** | GREEN — 7422 passed / 14 skipped (710.10s) |
| **Backend Ruff Lint** | PASS |
| **Backend Ruff Format** | PASS |
| **Vulture** | PASS |
| **Frontend** | **2 failed tests / 1 failed file**; 4217 passed, 12 skipped (4231) |

**Net: the ONLY red is 2 frontend tests in one file, both throwing the same error, and both
trace directly to PR #172 (the pivot CSV filename fix) — a change-with-tests miss on a
SIBLING test that renders the changed component.**

### Test failures

#### Frontend — 2 (both in one file, same root cause)
- **File**: `frontend/src/components/members/analytics/areas/AnalyticsStateNotice.test.tsx`
- **Suite**: `PivotViewsArea — no degradation notice (role machinery removed)`
- **Tests**:
  1. `mounts the pivot sub-panel with NO analytics-config degradation notice`
  2. `shows the empty-state hint (not a degradation) when there are no saved sets`
- **Error** (identical for both):
  ```
  Error: useTenant must be used within a TenantProvider
   ❯ useTenant src/context/TenantContext.tsx:128:11
   ❯ MemberPivotViews src/components/members/analytics/MemberPivotViews.tsx:176:29
  ```
- **Root cause**: PR #172 added a `useTenant()` call to `MemberPivotViews.tsx` (line ~176)
  to name the CSV export `{Tenant}-{Pivot}.csv`. The paired test
  `MemberPivotViews.test.tsx` was updated to mock `useTenant` and still passes. But
  `AnalyticsStateNotice.test.tsx` ALSO renders `MemberPivotViews` (via the PivotViewsArea)
  and does NOT mock `useTenant` nor wrap the render in a `TenantProvider`. So that sibling
  test now throws at mount. A **change-with-tests miss**: the paired test was updated, a
  second test exercising the same component through a different entry point was not.

### Lint failures

_None._ Backend Ruff Lint, Ruff Format, and Vulture all PASS. No CI-blocking lint this run.

#### Report-only (non-blocking)
- No lint reds. (Historically this slot has carried frontend `tsc`/ESLint and SAM ruff
  report-only findings; the downloaded `backend-lint-reports` for this run is all-green and
  the frontend report shows only the 2 test failures above.)

## Comparison with the previous run (Step 5)

Prior comparable CI spec: `full-test-suite-fixes-2026-10-17` (run #74, `test`, after PRs
#121/#122) — 1 backend convergence property + 2 frontend stale-`view_contexts` status tests
+ a CI-blocking backend ruff-format fail (4 reds, all from the two just-merged PRs).

- **Direction**: run #113 has **fewer reds than #74** (4 -> 2) and **no backend or lint reds**
  at all — backend, SAM, and all lint are green. This is a **narrower regression**, not a
  spike: a single component's sibling test.
- **Recurring pattern — change-with-tests miss (SAME class as #74)**: #74's reds were paired
  tests not realigned to a Members-config refactor; #113's reds are the same class — a
  component change (`MemberPivotViews` gained `useTenant`) whose paired test was updated but a
  SIBLING test rendering the same component was not. The recurring theme is "update the paired
  test but miss a second test that mounts the same unit." This is exactly the class the
  `30-backend-api-flask-mysql` Change-With-Tests Contract names as the top recurring CI failure.
- **NEW failure introduced by the fix sprint**: yes — the fail is net-new from **PR #172**
  (pivot-csv-filename). It did not exist before that PR.
- **Did #74's reds recur?** No. The projection convergence property, the `view_contexts`
  status-banner tests, and the ruff-format drift are all green in #113. #74's fixes held.
- **Promotion-gate note**: #113 is the NIGHTLY run on `main` (post-release). The regression
  reached `main` because the `test -> main` promotion (PR #173) was merged while this
  sibling-test red was latent — the pre-merge gates on PRs #171/#172/#173 were CodeQL +
  GitGuardian only (Backend/Frontend CI are `disabled_manually`; see steering 43), so no
  per-PR full-suite run caught it. The nightly suite is the first gate that runs the full
  frontend suite.

## Lessons / Recurring issues

1. **When a component gains a new hook/context dependency, realign EVERY test that mounts it —
   not only its own paired test.** PR #172 added `useTenant()` to `MemberPivotViews` and
   updated `MemberPivotViews.test.tsx`, but `AnalyticsStateNotice.test.tsx` mounts the same
   component through PivotViewsArea and was not updated. Before calling such a change done,
   grep the test tree for every test that renders the changed component (by import or by a
   wrapping area/panel) and ensure each either provides the new context or mocks the hook.
2. **A missing React context provider in a test throws at mount with a crisp message
   (`X must be used within a Y Provider`).** Treat that class as a change-with-tests miss, not
   a flake: the fix is to add the provider wrapper (or mock the hook) in the sibling test, the
   same way the paired test already does.
3. **Per-PR gates do not run the full frontend suite (Backend/Frontend CI are
   `disabled_manually`; only CodeQL + GitGuardian gate a PR — steering 43).** So a frontend
   change-with-tests miss is invisible until the NIGHTLY full-suite run — after it has already
   been promoted to `main`. Mitigation: run the changed component's sibling tests locally
   (`npx vitest run <component-dir>`) before promoting, and/or re-dispatch `full-test-suite.yml`
   on `test` as the promotion gate rather than relying on the nightly.
4. **The recurring class is unchanged from #74: "update the paired test, miss a second test."**
   The specific trigger differs (projection semantics then; a new context hook now) but the
   remedy is the same — sweep ALL tests exercising the changed unit, not just the obvious one.
