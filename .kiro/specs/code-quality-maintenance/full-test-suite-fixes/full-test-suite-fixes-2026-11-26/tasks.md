# Implementation Plan

## Overview

Fix the one issue that makes the 2026-11-26 Full Test Suite CI run red (run #45797012593, schedule, ❌ failure). The Frontend job is red with 0 assertion failures: 365 test files passed, 4534 tests passed | 12 skipped (4546), 1 unhandled error — a Vitest `ReferenceError: window is not defined` teardown flake in `AangifteIbReport.test.tsx`. All other planes are green: Backend Full Test Suite ✅ (7736 passed, 14 skipped, 0 failed), SAM Module-Plane ✅, Backend Lint & Static Analysis ✅ (0 RUFxx), Frontend ESLint report-only 0 errors, Frontend tsc report-only non-blocking.

Tasks are organized by priority: **Critical** (tests can't run), **High** (assertion failures + CI-blocking lint), **Medium** (flaky / non-deterministic), and **Low** (prevention / hygiene). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h. Verification commands assume `cd backend && source .venv/bin/activate` (backend) / `cd frontend` (frontend). No collection errors and no assertion failures this cycle → **no Critical tasks**, and the only test-plane item is the Medium flaky-worker mitigation.

## Tasks

### Critical — collection / import errors (nothing else runs until these pass)

_None._ No collection or import errors this cycle — backend collects and passes 7736, SAM collects and passes, and the frontend suite collected and ran (the single error is a worker crash, not a collection failure).

### High — running tests that fail + CI-blocking lint (CI-blocking)

_None._ No assertion failures this cycle, and there are no CI-blocking lint errors (ruff lint, format, vulture all clean; frontend ESLint 0 errors, tsc report-only). The Frontend job is red purely due to an unhandled error, not a failure.

### Medium — flaky / non-deterministic (frontend window teardown)

- [x] **M1. Fix the frontend vitest `window is not defined` unhandled error in AangifteIbReport test.** [M] — address the root cause of the single job red.

  - **Why:** Frontend job red with 0 assertion failures: 365 test files passed, 4534 tests passed | 12 skipped (4546), 1 error. Vitest raised `'ReferenceError: window is not defined'` during teardown of `src/components/reports/AangifteIbReport.test.tsx`. Originates from `setTimeout(() => setTenantSwitching(false), 100)` in `src/components/reports/AangifteIbReport.tsx:221` — timer callback fires after test environment teardown, so react-dom's `window` reference is unavailable. Non-deterministic (timing-dependent), not an assertion failure. No product regression.

  - **File(s):** `frontend/src/components/reports/AangifteIbReport.tsx` (line ~221, the `setTimeout` call) and `frontend/src/components/reports/AangifteIbReport.test.tsx` (the test file where the error surfaces).

  - **Action (pick the lightest that holds):**
    - **Option A:** Add `vi.clearAllTimers()` in an `afterAll` hook in the test file or a nearby `setupFiles` to clear any pending timeouts before environment teardown.
    - **Option B:** Rewrite the setTimeout to avoid the `window` reference, e.g., move the `setTenantSwitching(false)` call to run synchronously or use `vi.runOnlyPendingTimers()` within a `vi.mockedSetTimeout` wrapper.
    - **Option C:** Use `vi.runWithTimers()` context or `vi.useFakeTimers()` with proper `vi.clearAllTimers()` cleanup.

    The lightest and safest fix is typically Option A: add `afterAll(() => vi.clearAllTimers())` in the test file's tear down, or add it to the frontend's Vitest config setup file so all tests benefit. This prevents any pending timer from firing after the test environment is torn down, eliminating the `ReferenceError: window is not defined`.

    ```bash
    # Inspect the current test file setup:
    cd /home/peter/projects/myAdmin/frontend
    grep -n 'afterAll\|vi.clearAllTimers\|useFakeTimers' src/components/reports/AangifteIbReport.test.tsx
    # Edit the test file to add vi.clearAllTimers() in afterAll (or in the Vitest global setup)
    # Example diff:
    # --- a/src/components/reports/AangifteIbReport.test.tsx
    # +++ b/src/components/reports/AangifteIbReport.test.tsx
    #@@ -afterEach, afterAll = ...
    #+afterAll(() => vi.clearAllTimers())
    ```

  - **Verification:** Re-run the frontend suite and confirm the job concludes success (0 unhandled errors):
    ```bash
    cd /home/peter/projects/myAdmin/frontend
    NODE_OPTIONS=--max-old-space-size=4096 npx vitest run src/components/reports/AangifteIbReport.test.tsx 2>&1 | tail -10
    # -> should show 0 unhandled errors / "Unhandled Errors" section absent or empty
    # Re-run the full frontend suite to confirm no regression:
    NODE_OPTIONS=--max-old-space-size=4096 npx vitest run 2>&1 | grep -E '(Unhandled Errors|Test Files|Tests)' | head -5
    ```

### Low — prevention / hygiene

- [x] **L1. Verify ruff stays pinned to 0.16.5 (reproducibility guard).** [S] — standing guard carried forward from prior cycles. CI ran ruff 0.16.5; the clean lint results are genuine (no version drift). Keep local 0.16.5 == CI 0.16.5 so results stay reproducible and a silent version bump can't reintroduce a wall of findings.

  - **File(s):** `backend/requirements-test.txt`, `.github/workflows/full-test-suite.yml`, `.github/workflows/backend-code-quality.yml`.

  - **Action / Verification:**
    ```bash
    ruff --version                                   # -> ruff 0.16.5
    grep -rn "ruff==0.16.5" /home/peter/projects/myAdmin/backend/requirements-test.txt .github/workflows/
    ```

- [x] **L2. Broaden pre-push guard from `--collect-only` to also run `ruff check` + `ruff format --check` + changed-path tests.** [M] — carried forward from 10-03/10-04/10-05/10-10 L1 (**verified**); FIFTH consecutive cycle this guard would have prevented the red Backend Lint job. Although the current run has 0 lint errors (clean), the guard remains the highest-leverage prevention item.

  - **File(s):** `scripts/hooks/pre-push`, `scripts/hooks/install-hooks.sh`.

  - **Action:** Ensure `cd backend && ruff check src/ && ruff format --check src/` and a changed-path `pytest` subset (map edited `src/**` → paired tests, e.g. `python -m backend.scripts.test_maintenance.scoped_runner --git-diff`) are in the hook; keep the `SKIP_PREPUSH_*` escape hatch; fail on non-zero.

  - **Verification:**
    ```bash
    cd /home/peter/projects/myAdmin
    bash scripts/hooks/pre-push </dev/null; echo "rc=$?"
    ```

- [x] **L3. Confirm ruff stays pinned to 0.16.5 (reproducibility guard).** [S] — standing guard carried forward from 10-03 L3 / 10-04 L4 / 10-05 L4 / 10-10 L3. CI ran ruff 0.16.5; the clean lint results are genuine (no version drift). Keep local 0.16.5 == CI 0.16.5 so results stay reproducible and a silent version bump can't reintroduce a wall of findings.

  - **File(s):** `backend/requirements-test.txt`, `.github/workflows/full-test-suite.yml`, `.github/workflows/backend-code-quality.yml`.

  - **Action / Verification:**
    ```bash
    ruff --version                                   # -> ruff 0.16.5
    grep -rn "ruff==0.16.5" /home/peter/projects/myAdmin/backend/requirements-test.txt .github/workflows/
    ```

## Notes

### Execution order (see dependency-graph.json)

1. **M1** — fix the frontend vitest unhandled `window is not defined` error (the only test-plane item; clears the Frontend red).
2. **L1 / L2 / L3** — standing guards carried forward; maintain reproducibility and prevention (pre-push gate + ruff pin + changed-path tests).

### Full-suite verification (re-confirm after M1 lands)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `cd /home/peter/projects/myAdmin && PYTHONPATH=. python -m pytest sam/tests -q`
- Frontend: `cd frontend && NODE_OPTIONS=--max-old-space-size=4096 npx vitest run` (expect `365 Test Files passed`, 0 unhandled errors)
- Lint + Format: `cd backend && ruff check src/ && ruff format --check src/`
- Or confirm the next `full-test-suite.yml` run is green after M1 land.

### Context

- CI run #45797012593 (2026-11-26 @ 10:16 UTC @ main, schedule, ❌ failure). Frontend red with 0 assertion failures; 1 unhandled `window is not defined` error — a vitest forks worker teardown flake. Backend Full Test Suite GREEN (7736 passed, 14 skipped, 0 failed). SAM Module-Plane GREEN. Backend Lint & Static Analysis GREEN (0 ruff errors). This is the cleanest arc since the 11-18 Option B fix sprint cleared all backend/SAM failures.
- No Critical tasks (backend and SAM collect and pass; frontend collected and ran). No High test tasks (no assertion failures; no CI-blocking lint). The sole test-plane item is the Medium flaky-worker teardown error M1.
- Standing Low guards carried forward: L1=ruff pin, L2=pre-push broadening, L3=ruff reproducibility guard. These are maintained as preventive items regardless of current run state.
- Comparison to 11-18: All Option B migration fixes (backend F1 test assertion failures, SAM FakeParameterService.get_item, RUF059) held green on the main-branch scheduled run — no recurring failures. The only new red is this frontend teardown error, which is distinct in nature (infra flake vs product regression).
- Ruff version consistency: CI 0.16.5 == local. The clean lint results are genuine, not a version-mismatch artifact.
- Ruff went from 1 error (11-18) to 0 errors (11-26). The pre-push gate and the L3 standing guard (ruff pinned to 0.16.5) are bearing fruit.
