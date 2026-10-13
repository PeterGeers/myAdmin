# Implementation Plan

## Overview

Fix the two issues that make the 2026-10-13 Full Test Suite CI run red (run #64, id `38368671026`, branch `main` @ `660ad3a8`, `schedule`, ❌ failure). Two jobs are red — **Backend Lint & Static Analysis** (1 ruff `RUF100`) and **Frontend** (0 assertion failures, 1 vitest worker **JS-heap OOM** crash). Backend Full Test Suite ✅, SAM Module-Plane ✅. This is the cleanest run of the recent arc: every backend/SAM test and all 3642 frontend tests that ran passed.

Tasks are organized by priority: **Critical** (tests can't run), **High** (assertion failures + CI-blocking lint), **Medium** (flaky / non-deterministic), and **Low** (prevention / hygiene). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h. Verification commands assume `cd backend && source .venv/bin/activate` (backend) / `cd frontend` (frontend). No collection errors and no assertion failures this cycle → **no Critical tasks**, and the only test-plane item is the Medium flaky-worker mitigation.

## Tasks

### Critical — collection / import errors (nothing else runs until these pass)

_None._ No collection or import errors this cycle — backend collects and passes 7166, SAM collects and passes, and the frontend suite collected and ran (the single error is a worker crash, not a collection failure).

### High — running tests that fail + CI-blocking lint (CI-blocking)

- [x] 1. **H1. Clear the 1 CI-blocking ruff `RUF100` in `members_analytics_audit.py` (unused `# noqa: BLE001`).** [S] — auto-fixable; keep the human rationale comment, drop only the dead `# noqa:` token.
  - **Why**: Backend Lint is red on a single ruff error (CI-blocking, same priority as a test failure): `src/routes/members_analytics_audit.py:106:29` — `RUF100` unused `# noqa` directive for the **non-enabled** rule `BLE001`. The line is the route-boundary guard `except Exception as e:  # noqa: BLE001 — route boundary: never leak a 500 stack`. Because `BLE001` (blind-except) is not enabled in `backend/ruff.toml`, the `# noqa: BLE001` suppresses nothing, so ruff flags the directive itself as dead.
  - **File(s)**: `backend/src/routes/members_analytics_audit.py` (line ~105–106, the `except Exception as e:` boundary).
  - **Action**: Remove **only** the `# noqa: BLE001` token, preserving the explanatory comment (the rationale is worth keeping). Prefer the surgical edit over a blind `ruff check --fix`, which could strip the whole directive and the comment with it. Result should read e.g. `except Exception as e:  # route boundary: never leak a 500 stack`.
    ```bash
    cd /home/peter/projects/myAdmin/backend && source .venv/bin/activate
    sed -n '103,110p' src/routes/members_analytics_audit.py          # inspect the boundary first
    # Edit the line to drop the "# noqa: BLE001" token, keep the human comment.
    # (ruff check --fix also clears it, but may remove more than intended — verify after.)
    ```
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    ruff check src/routes/members_analytics_audit.py   # -> All checks passed!
    ruff check src/                                     # -> All checks passed! (whole tree clean)
    ```

### Medium — flaky / non-deterministic (frontend worker OOM)

- [ ] 2. **M1. Stop the frontend vitest forks worker from OOM-crashing the run (E1).** [M] — ⛔ OPEN / NEEDS HEAP PROFILE. Four fixes attempted, all falsified by CI. Mechanism still unidentified; do NOT attempt a 5th speculative config change without a `--heap-prof` of the failing parallel config.
  - **Attempt log (all ❌ on CI)**: (1) `poolOptions.forks.maxForks:4` + `NODE_OPTIONS=4096` — **silently ignored**: vitest 4 removed `test.poolOptions` (prints a DEPRECATED warning). (2) `poolOptions.forks.execArgv=['--max-old-space-size=6144']` — no-op: vitest does not forward `execArgv` to workers. (3) `NODE_OPTIONS=6144` + the ignored poolOptions — still OOM (run 38390996157). (4) **vitest-4 top-level `maxWorkers:2`/`minWorkers:1`** (correctly applied, no deprecation) + `NODE_OPTIONS=6144` — **still OOM** (run 38394111510), and ~90s slower. All four reverted from `vite.config.ts`; only the CI `NODE_OPTIONS=6144` headroom bump remains.
  - **Hard evidence (run 38394111510 GC log)**: a **single** worker climbed to **~6050 MB against the 6182 MB ceiling** before OOM. This proves `NODE_OPTIONS=6144` *is* inherited by the worker and `maxWorkers:2` *was* applied — and still one worker accumulates ~6 GB. That **falsifies both** the "aggregate concurrency" and "simple per-file leak" theories: a sequential `--logHeapUsage` probe of the *same* suite showed heap oscillating only 60-380 MB and GC-ing down (no OOM). So the leak only manifests under **parallelism**, in a way `isolate:true` does not reclaim.
  - **Signature is always identical & flaky**: `263 passed (264)`, `1 error`, `Timeout terminating forks worker … ZZPTrips.test.tsx`. Run history: 10-11 pass, 10-12 & 10-13 fail — intermittent. `ZZPTrips.test.tsx` (256 LOC, 8 tests, no heavy alloc) is only *named* as the dying worker's current file at teardown, not the cause. The crash sits in the worker **teardown/shutdown** phase (`tests 129s` but total `509s`; the error is "Worker exited unexpectedly" / "Timeout terminating forks worker").
  - **Next step (requires expert direction / dedicated session)**: run the failing *parallel* config locally with `--logHeapUsage` and/or `node --heap-prof` to capture the retained-object graph of the worker that climbs to 6 GB. Only then choose a fix (candidate suspects to profile: the chained `console.error` monkey-patch in `setupTests.ts` re-wrapping per isolated file; un-cleared global `vi.mock('aws-amplify/auth')` / MSW `BroadcastChannel` handles keeping the worker alive at teardown; or a vitest-4 forks-pool teardown bug). Interim option: treat as flaky-infra and add a **CI job-level retry** for the frontend suite.
  - **Fix**: `frontend/vite.config.ts` — `pool: 'forks'` + `isolate: true` (reset module registry between files) + `poolOptions.forks.maxForks: 4` (bound aggregate heap); `.github/workflows/full-test-suite.yml` frontend step — `NODE_OPTIONS=--max-old-space-size=6144` (workers inherit this; it is the supported way to raise worker heap).
  - **Two failed attempts, then root cause (per the "diagnose, don't patch" rule)**: (a) bounded pool + `NODE_OPTIONS=4096` still OOM'd (budget too low for the accumulation); (b) `poolOptions.forks.execArgv=['--max-old-space-size=6144']` was a **no-op** — vitest does **not** forward a custom `execArgv` to pool workers (confirmed: the worker launched with no such flag in its argv, and it OOM'd worse). Root cause: cross-file memory accumulation in a reused forks worker; the heap ceiling must be raised via `NODE_OPTIONS` (inherited by workers), and `isolate:true` curbs the growth rate.
  - **Verification evidence (local, WSL)**: with the broken config a worker ballooned to **~4.35 GB RSS → `FATAL ERROR: … JavaScript heap out of memory` → `Worker exited unexpectedly` → `1 failed`**. With the fix, across multiple full-suite runs the worker RSS stayed **bounded (~105 MB–500 MB) through the entire test execution with `OOM=0`** and all tests passing (dots + `✓` lines). The OOM that defines E1 **no longer reproduces**.
  - **Caveat (honest)**: the local WSL environment wedges vitest's post-run teardown/summary flush (observed identically on 3 runs, incl. a non-OOM one), so the final green `Test Files … Tests … Duration` summary line could not be captured locally — this is a terminal/WSL artifact, not a test result. The clean green summary will be confirmed by the next `full-test-suite.yml` run on a GitHub runner.
  - **If it ever recurs**: next structural lever is `fileParallelism: false` (serialise files so the worker recycles) or the `vmForks` pool (`vmMemoryLimit` recycles the worker on exceed) — deferred for their speed/sandbox tradeoffs.
  - **Why**: The run shows `FATAL ERROR: … JavaScript heap out of memory` → `[vitest-pool]: Worker forks emitted error` → `Worker exited unexpectedly`, then `Timeout terminating forks worker for test files …/src/__tests__/ZZPTrips.test.tsx`. All 3642 tests that ran passed (`263 passed (264)`); the crash lost one file's result and reddened the job. `ZZPTrips.test.tsx` is just the file assigned to the dead worker — **not** a logic bug. The frontend suite grew 2756 → 3660 across the arc with no bump to the worker memory budget, so the forks pool is near its ceiling. Non-deterministic — may not reproduce locally.
  - **File(s)**: `frontend/vitest.config.ts` (pool / `poolOptions.forks`), `frontend/package.json` (the `test` / CI script and any `NODE_OPTIONS`), and/or `.github/workflows/full-test-suite.yml` (frontend job env).
  - **Action** (pick the lightest that holds; combine if needed):
    - Raise the worker heap: set `NODE_OPTIONS=--max-old-space-size=4096` (or higher) for the frontend test step in CI, or via the `test` script.
    - Bound the pool: in `vitest.config.ts` set `pool: 'forks'` with `poolOptions.forks.maxForks` capped (e.g. 2–4) and `singleFork: false`, so fewer workers each hold less heap; or switch heavy files to `isolate: true` only where needed.
    - If memory stays tight, **shard** the frontend run (`vitest run --shard=1/2` + `2/2`) across two CI steps/jobs.
    - After changing config, run the full frontend suite twice to confirm the OOM doesn't recur.
    ```bash
    cd /home/peter/projects/myAdmin/frontend
    cat vitest.config.ts | sed -n '1,80p'                       # inspect current pool config
    NODE_OPTIONS=--max-old-space-size=4096 npx vitest run 2>&1 | tail -20
    ```
  - **Verification**:
    ```bash
    cd frontend
    NODE_OPTIONS=--max-old-space-size=4096 npx vitest run 2>&1 | tail -8
    # -> "Test Files 264 passed (264)" and NO "heap out of memory" / "Worker exited unexpectedly".
    # Re-run once more to confirm the OOM is gone (non-deterministic).
    ```

### Low — prevention / hygiene

- [x] 3. **L1. Broaden the pre-push guard from `--collect-only` to also run `ruff check` + `ruff format --check` + a changed-path test subset.** [M] — already implemented (broadened in the 10-03/10-04 cycles) and **verified this run**: with H1 stashed, `bash scripts/hooks/pre-push </dev/null` caught the RUF100 at Gate 2 and failed the push (exit 1); with H1 applied it passes. The hook + installer match the task spec (SAM collect + whole-tree `ruff check src/` + `ruff format --check src/` + changed-path pytest subset, `SKIP_PREPUSH` escape hatch). — carried forward from 10-03 / 10-04 / 10-05 / 10-10 L1 (**still open**); it would have blocked H1 before it landed on `main`.
  - **Why**: This is the **fifth consecutive cycle** this guard would have prevented the red Backend Lint job. The single `RUF100` is exactly the mechanical finding a pre-push `ruff check src/` catches in seconds. A hook that runs `cd backend && ruff check src/ && ruff format --check src/` plus a changed-path `pytest` subset would have blocked H1 pre-push. (requirements Lessons 3 & 4.)
  - **File(s)**: `scripts/hooks/pre-push`, `scripts/hooks/install-hooks.sh`.
  - **Action**: Add `cd backend && ruff check src/ && ruff format --check src/` and a changed-path `pytest` subset (map edited `src/**` → paired tests, e.g. `python -m backend.scripts.test_maintenance.scoped_runner --git-diff`) to the hook; keep the `SKIP_PREPUSH_*` escape hatch; fail on non-zero.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin
    bash scripts/hooks/pre-push </dev/null; echo "rc=$?"
    # -> exits non-zero while the RUF100 is unfixed on the branch; 0 after H1 lands.
    ```

- [x] 4. **L2. Add a memory/scale guard for the frontend test run so a growing suite can't silently OOM a worker.** [S] — durable prevention for the E1 class.
  - **Why**: E1 happened because the frontend suite grew to 3660 tests with a fixed worker memory budget. Nothing warned before the worker crashed. Make the memory budget explicit and visible so suite growth is a conscious decision, not a surprise OOM.
  - **File(s)**: `frontend/vitest.config.ts`, `.github/workflows/full-test-suite.yml` (frontend job).
  - **Action**: Pin an explicit `NODE_OPTIONS=--max-old-space-size=<N>` for the frontend test step (so the budget is version-controlled, not inherited), and document the forks-pool sizing in a comment next to it. Optionally emit the peak RSS / worker count in the frontend `SUMMARY.md` so the artifact shows headroom each run.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin
    grep -rn "max-old-space-size\|maxForks\|NODE_OPTIONS" frontend/vitest.config.ts frontend/package.json .github/workflows/full-test-suite.yml
    # -> an explicit, committed memory budget for the frontend test step.
    ```

- [x] 5. **L3. Confirm ruff stays pinned to 0.16.5 (reproducibility guard).** [S] — standing guard carried forward from 10-03 / 10-04 / 10-05 / 10-10.
  - **Why**: CI ran ruff 0.16.5; the single `RUF100` is real new debt (not a version drift). Keep local 0.16.5 == CI 0.16.5 so results stay reproducible and a silent version bump can't reintroduce a wall of findings.
  - **File(s)**: `backend/requirements-test.txt`, `.github/workflows/full-test-suite.yml`, `.github/workflows/backend-code-quality.yml`.
  - **Action / Verification**:
    ```bash
    ruff --version                                   # -> ruff 0.16.5
    grep -rn "ruff==0.16.5" backend/requirements-test.txt .github/workflows/
    ```

## Notes

### Execution order (see dependency-graph.json)

1. **H1** — strip the dead `# noqa: BLE001` token in `members_analytics_audit.py` (fastest path to a green Backend Lint job; keep the rationale comment).
2. **M1** — give the frontend vitest forks pool more heap / shard it so the worker stops OOM-crashing (clears the only remaining Frontend red).
3. **L1 / L2** — broaden the pre-push guard (ruff + changed-path tests) and pin an explicit frontend test memory budget (prevention; directly target the H1 and E1 classes).
4. **L3** — confirm the ruff pin (standing guard).

### Full-suite verification (re-confirm after H1 + M1)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `cd /home/peter/projects/myAdmin && PYTHONPATH=. python -m pytest sam/tests -q`
- Frontend: `cd frontend && NODE_OPTIONS=--max-old-space-size=4096 npx vitest run` (expect `264 passed (264)`, no OOM)
- Lint + Format: `cd backend && ruff check src/ && ruff format --check src/`
- Or confirm the next `full-test-suite.yml` run is green after H1 + M1 land.

### Context

- CI run #64 (id `38368671026`, 2026-10-13 08:21 UTC @ `660ad3a8` on `main`, `schedule`, ❌ failure). Two red jobs: Backend Lint & Static Analysis (1 ruff `RUF100`) and Frontend (0 assertion failures, 1 worker OOM crash). Backend Full Test Suite ✅ · SAM Module-Plane ✅.
- The 10-10 failures (backend F1 expected-set, frontend F2/F3/F4 Members-UI cluster, the 3 ruff + 2 format findings) did **not** recur — all 10-10 H-fixes held. No Critical tasks (no collection/import errors) and no High test tasks (no assertion failures) this cycle; the single High item is the CI-blocking lint error.
- `members_analytics_audit.py` is a **recurring ruff-finding file** (RUF100/format at 10-10, RUF100 again at 10-13) — see requirements Lessons 3.
