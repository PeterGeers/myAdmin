# Requirements Document

# Full Test Suite Fixes — 2026-10-15 (run #73, dispatched on `test`)

## Introduction

This is a CI-analysis spec (not a feature): it captures the failures from a single **Full Test Suite** run and defines the fix tasks. It is generated per the `prompt-test-suite-results.md` runbook. The requirements below are the concrete, verifiable outcomes that make the run green and safe to promote `test → main`.

## Glossary

- **async-settle race** — a test asserting on post-load DOM before the component's data-loading promise has resolved (element not yet rendered).
- **report-only lint** — a CI lint/typecheck step that annotates but does not fail the build.
- **promotion gate** — the steering-43 rule that `test` must be verified-green before a `test → main` merge (a production frontend deploy).


## Source

GitHub Actions **Full Test Suite** run **#73** (id `38789557909`), `workflow_dispatch` on branch **`test`** @ `0fe6264ea` (the merge commit of PR #115, member-analytics-pivot-filter-operators + the ZZP spec move). Conclusion: ❌ **failure**. Analyzed purely from the downloaded CI artifacts (`sam-test-reports`, `frontend-test-reports`) — no local scans.

This run was dispatched as the promotion gate before a `test → main` release.

## Requirements

- **R1 (H1).** The frontend suite MUST be green on `test`: `MembersPage.test.tsx > global all-fields search (Option 1) > drives the stats strip` passes by awaiting the data-loading settle before querying `stat-total` (assertion not weakened).
- **R2 (L1).** The new `analyticsConfig.*.property.test.ts` files MUST carry no ESLint `import-x/order` or unused-`expect` warnings (auto-fixable).
- **R3 (L2).** The `test → main` promotion MUST NOT proceed until a re-dispatched Full Test Suite run on `test` concludes `success` (steering 43 production-deploy gate).

## Findings summary

| Suite | Result |
| --- | --- |
| **SAM Module-Plane** | ✅ GREEN — all tests pass (dots-only, 100%) |
| **Frontend** | ❌ **1 failed test** / 1 failed file; **3784 passed**, 12 skipped (3797 total) |
| Backend Full Test Suite | not in this dispatch's artifact set (no `backend-test-reports`) |
| Frontend ESLint / tsc | REPORT-ONLY (non-blocking) — tsc clean; ESLint all `warning`, no `error` |
| SAM ruff lint | REPORT-ONLY (non-blocking) — 60 findings, SAM job green |

**Net: a single frontend assertion failure** is the entire reason the run is red.

### Test failures — 1 frontend (1 root cause)

#### H1 — `MembersPage` stats-strip test asserts while the page is still loading

- **File / test**: `frontend/src/__tests__/MembersPage.test.tsx:447` → `MembersPage (Leden Overzicht) > global all-fields search (Option 1) > drives the stats strip (total stays full, filtered follows the search)`
- **Error**: `TestingLibraryElementError: Unable to find an element by: [data-testid="stat-total"]`
- **Rendered DOM at failure**: the page is still in its **loading state** — `<p>table.loading</p>` + `<span role="status">` spinner; the stats strip and table body have not rendered yet.
- **Root cause**: the test does `expect(screen.getByTestId('stat-total')).toHaveTextContent('3')` **before the data-loading hook has resolved** (rows/stats not yet painted). Sibling tests in the same file gate on a `waitForRows()` helper before asserting; this case asserts without that settle. An **async-settle race**, not a product-logic bug.
- **Attribution**: surfaced one cycle behind the **2026-10-15 code-quality arc** (`code-quality-fixes-2026-10-15` task 6 split `MembersPage.tsx` (1161 LOC) and **extracted its data-loading hooks**). The extracted hook's initial-fetch timing is slightly different under test, so a non-awaited assertion now loses the race.
- **NOT a PR #115 regression**: the member-analytics-pivot-filter-operators change touched analytics files (`types/pivot.ts`, `analyticsConfig.ts`, `GroupedFieldSelect`, `MemberFieldPicker`, `memberFieldPicker.helpers`, locales) + a SAM test — **not** `MembersPage.tsx`. The feature's own ~95 new/updated tests are all green. The flake merely rides on the same branch.

### Lint failures — none CI-blocking

- **Frontend `tsc`**: clean (empty report).
- **Frontend ESLint** (report-only): all `warning`, zero `error`. PR #115 added benign, auto-fixable warnings in the new property-test files → captured as **L1**:
  - `import-x/order` "no empty line between import groups" in 11 files: `analyticsConfig.andAcrossClauses / blankValue / contains / emptyNotEmpty / legacyScalarEquivalence / notContains / operators / purityOrder / regexTotality / typedOrdering / unknownOperator.property.test.ts`.
  - unused `expect` import in `contains / notContains / regexTotality.property.test.ts`.
- **SAM ruff lint** (report-only): 60 findings by rule (`12 I001, 9 RUF022, 7 RUF100, 4 UP037, 4 SIM102, 4 B017, …`); none CI-blocking (SAM job green). Pre-existing SAM debt, out of scope for this promotion gate.

## Comparison with the previous run (Step 5)

The directly comparable prior CI spec is `full-test-suite-fixes-2026-10-15` (run #72, `schedule` on `main`, SHA `e600d5e2`). This run (#73) is a **later, `test`-branch `workflow_dispatch`** that includes PR #115.

- **Direction**: #72 had Critical + a broader failure set; #73 is down to **one frontend async-settle flake** — strong convergence. SAM remained green.
- **Backend Lint `RUF100` (10-13 H1 / recurring in `members_analytics_audit.py`)**: not present in this dispatch's artifacts (no backend-lint artifact in scope); not re-flagged here.
- **Frontend worker OOM (10-13 M1 / `ZZPTrips.test.tsx` forks-pool heap)**: did **NOT** recur in #73 — no `JavaScript heap out of memory` / `Worker exited unexpectedly`; the single failure is a clean assertion error.

## Lessons / Recurring issues

1. **`MembersPage` is the standing red zone — it regresses one cycle behind every Members UI refactor.** Recorded at **2026-09-26** (RC-F1/RC-F2: empty rows / view-context), **2026-10-10** (F3/F4: session-column filter composition), and the **2026-09-29** lesson already warns to "re-run the whole Members test group before merging a Members UI refactor." This failure trails the **2026-10-15 MembersPage split** — exactly the predicted pattern. **Action for next time**: after any `MembersPage.tsx` / its hooks refactor, run `cd frontend && npx vitest run src/__tests__/MembersPage.test.tsx src/pages/__tests__/MembersPage*` before merging.

2. **Extracting a data-loading hook changes test timing — audit synchronous `getByTestId` queries for a missing `await`.** When a page's fetch moves into an extracted hook, tests that queried post-load DOM synchronously can now lose the settle race. Prefer `await waitForRows()` / `findByTestId` over a bare `getByTestId` for any element that only exists after data loads.

3. **A single async-settle flake on `test` must not auto-promote to `main`.** Per steering 43 the `test → main` merge is a production frontend deploy; TEST must be verified-green first. Fix H1 (or confirm-flaky + re-run green) before opening the promotion PR.
