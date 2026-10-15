# Implementation Plan

## Overview

Fix the single issue that makes the 2026-10-15 Full Test Suite CI run red (run **#73**, id `38789557909`, branch **`test`** @ `0fe6264ea`, `workflow_dispatch`, ❌ failure). Exactly **one** frontend test fails — an async-settle race in `MembersPage.test.tsx` — out of 3797; **SAM is green (100%)** and the other 3784 frontend tests pass. This run was dispatched as the `test → main` promotion gate, so **the promotion must not proceed until this is green** (steering 43 — a merge to `main` is a production frontend deploy).

Tasks are organized by priority: **Critical** (tests can't run), **High** (assertion failures that gate the release), **Medium** (flaky / non-deterministic), **Low** (prevention / hygiene). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h. Verification commands assume `cd frontend`. No collection/import errors and no OOM this cycle → **no Critical, no Medium tasks**.

## Tasks

### Critical — collection / import errors (nothing else runs until these pass)

_None._ Everything collected and ran — SAM passed 100%, and the frontend suite collected and executed 3797 tests. The single red is an assertion/async-settle error, not a collection failure.

### High — running tests that fail (gates the test → main promotion)

- [ ] 1. **H1. Fix the `MembersPage` stats-strip test asserting before the data-loading hook resolves.** [S]
  - **Why**: Frontend is red on exactly one test: `src/__tests__/MembersPage.test.tsx:447` → `MembersPage (Leden Overzicht) > global all-fields search (Option 1) > drives the stats strip (total stays full, filtered follows the search)`. It does `expect(screen.getByTestId('stat-total')).toHaveTextContent('3')`, but the rendered DOM is still the **loading state** (`<p>table.loading</p>` + `role="status"` spinner) — `stat-total` does not exist yet because the extracted data-loading hook had not resolved. Async-settle race, surfaced one cycle behind the 2026-10-15 `MembersPage.tsx` split (`code-quality-fixes-2026-10-15` task 6 extracted the data-loading hooks). NOT a PR #115 regression (PR #115 did not touch MembersPage).
  - **File(s)**: `frontend/src/__tests__/MembersPage.test.tsx` (the `global all-fields search (Option 1)` block, ~lines 430–448); if the race is in product code, `frontend/src/pages/MembersPage.tsx` + its extracted data-loading hook.
  - **Action** (prefer the test-side await — the product behavior is correct, the test just queries too early):
    - Make the case `async` and `await` the rows/stats to settle before querying `stat-total` — reuse the file's existing `waitForRows()` helper (sibling tests already gate on it), or wrap the first stats assertion in `await screen.findByTestId('stat-total')` / `await waitFor(() => expect(screen.getByTestId('stat-total')).toHaveTextContent('3'))`.
    - Confirm the sibling cases in the same `describe` already await; align this one to the same pattern (do not weaken the assertion — it must still assert total `3` / filtered following the search).
    - If a deterministic settle still can't be reached, verify the extracted data-loading hook flushes its initial fetch under the test's mocked data (no un-awaited microtask); fix the hook rather than add an arbitrary timeout.
    ```bash
    cd /home/peter/projects/myAdmin/frontend
    sed -n '420,460p' src/__tests__/MembersPage.test.tsx          # inspect the failing block + the waitForRows() helper
    grep -n "waitForRows\|findByTestId\|getByTestId('stat-total')" src/__tests__/MembersPage.test.tsx
    ```
  - **Verification**:
    ```bash
    cd frontend && npx vitest run src/__tests__/MembersPage.test.tsx 2>&1 | tail -8
    # -> the "drives the stats strip" test PASSES; file fully green.
    # Re-run the whole Members group (the historical red zone) before merging:
    npx vitest run src/__tests__/MembersPage.test.tsx 'src/pages/__tests__/MembersPage*' 2>&1 | tail -8
    ```

### Medium — flaky / non-deterministic

_None._ No worker OOM / infra flake this cycle (the 10-13 M1 `ZZPTrips` forks-pool OOM did not recur). H1 is flake-class but is a deterministic missing-`await`, fixed under High because it gates the release.

### Low — prevention / hygiene

- [ ] 2. **L1. Clear the benign ESLint warnings PR #115 added to the new property-test files.** [S] — report-only (non-blocking); clear while fresh.
  - **Why**: Frontend ESLint is report-only, so these did not fail CI, but the member-analytics-pivot-filter-operators arc introduced auto-fixable warnings worth clearing: `import-x/order` "no empty line between import groups" in 11 `analyticsConfig.*.property.test.ts` files, and an unused `expect` import in 3 of them (`contains`, `notContains`, `regexTotality`).
  - **File(s)**: `frontend/src/__tests__/analyticsConfig.{andAcrossClauses,blankValue,contains,emptyNotEmpty,legacyScalarEquivalence,notContains,operators,purityOrder,regexTotality,typedOrdering,unknownOperator}.property.test.ts`.
  - **Action**: Remove the blank line between the import groups (`import fc from 'fast-check'` and the local `../components/...` imports), and drop the unused `expect` named import from the three files that import it without using it. `npx eslint --fix` on those paths resolves both.
  - **Verification**:
    ```bash
    cd frontend && npx eslint src/__tests__/analyticsConfig.*.property.test.ts 2>&1 | tail -5
    # -> no import-x/order or no-unused-vars warnings for these files.
    ```

- [ ] 3. **L2. Do not promote `test → main` until the Full Test Suite is green on `test`.** [S] — release-gate verification (steering 43).
  - **Why**: The user's sequence is feature → `test` (done, PR #115) → confirm Full Test Suite green → promote `test → main`. The `test → main` merge **is a production frontend deploy** (`deploy-frontend.yml`), so TEST must be verified-green first. This run is red on H1 only.
  - **File(s)**: n/a (process gate).
  - **Action**: After H1 lands on `test`, re-dispatch the suite and confirm green, then open ONE `test → main` PR and merge it with a **merge commit** (steering 43 promote runbook).
    ```bash
    export GH_PAGER=""
    gh workflow run full-test-suite.yml --ref test
    gh run list --workflow full-test-suite.yml --branch test --limit 1 --json databaseId,status,conclusion
    # -> wait for conclusion "success" before opening the test->main PR.
    ```
  - **Verification**: the latest `full-test-suite.yml` run on `test` is `success`; then CodeQL + GitGuardian green on the `test → main` PR before the merge-commit.

## Task Dependency Graph

The authoritative machine-readable graph is `dependency-graph.json` (nodes H1, L1, L2; edge H1→L2 `blocks`). Wave schedule:

```json
{
  "waves": [
    { "id": 0, "tasks": ["H1", "L1"] },
    { "id": 1, "tasks": ["L2"] }
  ]
}
```

- **Wave 0** — **H1** (the only CI-red item; start here) and **L1** (independent hygiene) can run in parallel.
- **Wave 1** — **L2** is blocked by **H1**: the `test → main` promotion gate cannot pass until H1 makes the suite green on `test`.

Recommended order: **H1 → L1 → L2**.

## Notes

### Execution order (see dependency-graph.json)

1. **H1** — add the missing `await`/`waitFor` so the stats-strip test settles before querying `stat-total` (clears the only red; unblocks the promotion).
2. **L1** — `eslint --fix` the import-group/unused-`expect` warnings in the new property-test files (hygiene, non-blocking).
3. **L2** — re-run the Full Test Suite on `test`, confirm green, then promote `test → main` with a merge commit.

### Full-suite verification (re-confirm after H1)

- Frontend: `cd frontend && npx vitest run src/__tests__/MembersPage.test.tsx 'src/pages/__tests__/MembersPage*'` (the historical red zone) + the full suite.
- SAM: already green this run; re-confirm via the re-dispatched `full-test-suite.yml` on `test`.
- Or simply confirm the re-dispatched `full-test-suite.yml` run on `test` is green.

### Context

- CI run **#73** (id `38789557909`, 2026-10-15 18:54 UTC @ `0fe6264ea` on `test`, `workflow_dispatch`, ❌ failure). SAM ✅ (100%); Frontend ❌ 1 failed / 3784 passed / 12 skipped (3797).
- The one failure is an **async-settle race in `MembersPage`** — the standing historical red zone, trailing the 2026-10-15 `MembersPage.tsx` split by one cycle (see requirements Lessons 1 & 2).
- **Not** a regression from PR #115 (member-analytics-pivot-filter-operators); that feature's own tests are all green.
