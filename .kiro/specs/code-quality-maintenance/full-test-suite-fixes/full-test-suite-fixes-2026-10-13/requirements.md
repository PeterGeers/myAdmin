# Full Test Suite Fixes — 2026-10-13

## Summary

Full Test Suite run (GitHub Actions run #64 / id `38368671026`) on branch `main` @ `660ad3a8`, 2026-10-13 08:21 UTC, triggered by `schedule`. **CI conclusion: ❌ failure.** Analysis is CI-artifact-based only (no local scans), from the downloaded `backend-test-reports`, `sam-test-reports`, `frontend-test-reports`, and `backend-lint-reports` artifacts.

| Category                     | Count                                            | Δ vs 2026-10-10                               |
| ---------------------------- | ------------------------------------------------ | --------------------------------------------- |
| Backend test failures        | **0** (of 7166; 7152 passed, 14 skip)            | 🟢 **recovered** 1 → 0                          |
| SAM module-plane tests       | ✅ pass (0 fail)                                  | ✅ held green                                   |
| Frontend test failures       | **0 assertion** · **1 error** (worker OOM crash) | 🟢 assertions 3 → 0; 🟠 1 infra error (new)     |
| Ruff lint errors (backend)   | **1** (RUF100 ×1)                                | 🟢 **improving** 3 → 1                          |
| Ruff format violations (be)  | **0 files**                                      | 🟢 **recovered** 2 → 0                          |
| Vulture (dead code)          | ✅ Pass                                           | — stable green                                 |

**CI job result**: Backend Full Test Suite ✅ (0 failed) · SAM Module-Plane ✅ · **Frontend ❌ (0 assertion failures, 1 unhandled worker error)** · **Backend Lint & Static Analysis ❌ (1 ruff error)**. Only **two** things make this run red, and both are small: a single auto-fixable ruff `RUF100` and a frontend vitest **worker that crashed with a JavaScript heap OOM**. Every backend test, every SAM test, and all 3642 frontend tests that ran **passed** — this is the cleanest run of the recent arc.

> ⚠️ **The frontend "failure" is not an assertion failure.** 3642 tests passed, 12 skipped, and **1 error** — a vitest forks **worker exited unexpectedly after a `FATAL ERROR: … JavaScript heap out of memory`**. Vitest then reported `Timeout terminating forks worker for test files … ZZPTrips.test.tsx` — that filename is simply the file whose worker could not be reaped, **not** a failing test in it. 263 of 264 test files passed; the 264th file's result was lost to the worker crash. This is a **memory/infra flake**, not a product regression. Treat as **Medium** (flaky/non-deterministic), per Lesson 2 of the runbook.

> ⚠️ **Ruff version**: CI ran **ruff 0.16.5** (pinned, matches local). The single `RUF100` is real new debt, not a version-mismatch artifact.

> 🔁 **Recurring file**: the `RUF100` sits in `members_analytics_audit.py` — the **same file** that carried an `RUF100` + a format finding at 10-10 (H4/H5). The directive type differs (10-10 cleared a `# noqa` on a now-removed line; this run flags a `# noqa: BLE001` on the current `except Exception` boundary), but the file keeps re-attracting ruff findings. See Lessons.

---

## Test Results — Backend (7152 passed, 14 skipped, **0 failed**, 0 collection errors — 973.49s ≈ 16m13s)

✅ **Green.** 7166 tests collected; **zero failures, zero errors**. The single 10-10 backend failure (F1, the stale Members `mail_*` expected-set in `test_parameter_admin_routes.py`) did **not** recur — the 10-10 H1 fix held. Backend has now recovered to a clean run (46 → 17 → 2 → 1 → **0** across the 10-03 → 10-13 arc).

---

## Test Results — SAM module-plane (✅ PASS)

✅ **Green.** 0 failures, 0 errors (100% dots in the summary tail). Collection healthy; held green for a **fifth** consecutive cycle.

---

## Test Results — Frontend (3642 passed, 12 skipped, **0 assertion failures**, **1 unhandled error** — 263/264 files passed, 417.02s)

🟠 **Red job, but no failing test.** Every test that ran passed. The job is red because of **one unhandled worker error**:

### E1 — vitest forks worker JS-heap OOM crash (1 error, not an assertion)

| Symptom | Detail |
| ------- | ------ |
| Fatal error | `FATAL ERROR: Ineffective mark-compacts near heap limit — Allocation failed - JavaScript heap out of memory` (node 22.23.3) |
| Vitest surface | `Vitest caught 1 unhandled error during the test run` → `[vitest-pool]: Worker forks emitted error` → `Error: Worker exited unexpectedly` |
| Trailing line | `[vitest-pool]: Timeout terminating forks worker for test files …/src/__tests__/ZZPTrips.test.tsx` |
| File tally | `Test Files 263 passed (264)` — one file's result lost to the crash |

**Root cause:** a vitest **forks** worker ran out of V8 heap and was killed by node; vitest could not terminate the (already dead) worker and raised an unhandled error, which fails the job even though no assertion failed. `ZZPTrips.test.tsx` is named only because it was the file assigned to the crashed worker when the timeout fired — the OOM is a **process-memory ceiling / worker-pool** problem (large suite, forks pool, accumulated heap), not a defect in that test's assertions. The frontend suite has grown steadily (2756 → 3660 total across the arc), so the pool is closer to its memory ceiling. This is **non-deterministic / flaky** and belongs in **Medium**: it may not reproduce locally and may pass on a re-run.

**Grouped by root cause:** 0 assertion clusters. 1 infra cluster — frontend worker OOM (E1).

---

## Lint & Static Analysis (Backend Lint job — ❌ FAIL)

| Check | Result |
|-------|--------|
| Ruff Lint | ❌ Fail — **1 error** (`RUF100` ×1), ruff 0.16.5 |
| Ruff Format | ✅ Pass (325 files already formatted) |
| Vulture | ✅ Pass (no dead code) |

### Ruff Lint — 1 error (CI-blocking)

| Rule | Count | Auto-fixable | File:line |
| ---- | ----- | ------------ | --------- |
| `RUF100` | 1 | ✅ `--fix` | `src/routes/members_analytics_audit.py:106:29` — unused `# noqa` directive (non-enabled: `BLE001`) |

The flagged line is the `except Exception as e:  # noqa: BLE001 — route boundary …` guard. `BLE001` (blind-except) is **not enabled** in `backend/ruff.toml`, so the `# noqa: BLE001` suppresses nothing and ruff reports it as a dead directive. Ruff reports **1 of 1 fixable** with `--fix` (it strips the unused directive while leaving the explanatory comment logic to the author). Because the comment carries a real rationale ("route boundary: never leak a 500 stack"), the clean fix is to **drop just the `# noqa: BLE001` token** and keep the human comment, rather than let `--fix` remove the whole directive blindly — see tasks.md H1.

### Ruff Format — 0 files

✅ All 325 source files already formatted. The two 10-10 format targets (`members_analytics_audit.py`, `members_config_validation.py`) stayed formatted — the 10-10 H5 fix held.

### Totals by category

- **CI-blocking** this cycle: **1 ruff-lint error** (plus the frontend worker-OOM error that reds the Frontend job). Backend tests, SAM, format, and vulture are all green.
- **Auto-fixable vs manual (lint)**: the single `RUF100` is `--fix`-able (prefer the surgical token removal in H1 to preserve the rationale comment).
- **Test fixes**: no assertion fixes needed. E1 is a flaky-infra mitigation (Medium), not a test correction.
- **Version mismatch**: none (CI ruff 0.16.5 == local 0.16.5).

---

## Comparison with recent runs (the 10-03 → 10-13 arc)

| Metric               | 10-03 | 10-04 | 10-05 | 10-10 | 10-13 | Trend                                                   |
| -------------------- | ----- | ----- | ----- | ----- | ----- | ------------------------------------------------------- |
| CI conclusion        | ❌     | ❌     | ❌     | ❌     | ❌     | 🟠 Still red — but only on 1 lint error + 1 infra crash   |
| Backend failures     | 46    | 17    | 2     | 1     | **0** | 🟢 Recovered 1 → 0 (clean)                                |
| SAM plane            | ✅     | ✅     | ✅     | ✅     | ✅     | ✅ Held green 5 cycles                                     |
| Frontend failures    | 0     | 0     | 0     | 3     | **0*** | 🟢 Assertions 3 → 0 (*1 infra worker-OOM error remains)   |
| Ruff lint errors     | 40    | 39    | 0     | 3     | **1** | 🟢 Improving 3 → 1                                         |
| Ruff format files    | 1     | 17    | 0     | 2     | **0** | 🟢 Recovered 2 → 0                                         |
| Vulture              | Pass  | Pass  | Pass  | Pass  | Pass  | — Stable                                                  |
| Total backend tests  | 6684  | 6938  | 6938  | 7068  | 7166  | ↑ +98 since 10-10                                         |
| Total frontend tests | 2756  | 2928  | 3602  | 3660  | 3660  | ↑ large growth; pool nearing memory ceiling (see E1)     |

### Held / fixed (stayed green)

- 🟢 **Backend recovered 1 → 0**: the 10-10 F1 (stale Members `mail_*` expected-set) did **not** reappear — the 10-10 H1 fix held.
- 🟢 **Frontend assertions 3 → 0**: the 10-10 Members-UI cluster (F2 tenant-switch role re-resolution, F3/F4 session-column filter composition) did **not** reappear — the 10-10 H2/H3 fixes held. The only remaining frontend red is the new infra OOM (E1), not those tests.
- 🟢 **Ruff format recovered 2 → 0** and **lint 3 → 1**: the 10-10 H4/H5 clean-ups held; only one new `RUF100` remains.
- ✅ **SAM** held green for a fifth consecutive cycle. **Vulture** green across the whole arc.

### Recurring failures that were "fixed" last time but reappear

- **No test recurred.** But `members_analytics_audit.py` is a **recurring ruff-finding file**: it carried an `RUF100` + a format finding at 10-10 (H4/H5) and now carries a different `RUF100` (`# noqa: BLE001`) at 10-13. The specific lines differ, but the file keeps attracting dead-`noqa` findings — a sign its exception-boundary `# noqa` comments are being written against rules the project does not enable. Flagged in Lessons.

### New failures introduced since the previous fix sprint

- **E1 (frontend worker OOM)** is new and is an **infrastructure/memory** regression, not a product one — the frontend suite's steady growth (now 3660 tests) is pushing the vitest forks pool toward its heap ceiling. No new assertion failures.
- **The single `RUF100`** is new debt on the current `except Exception` boundary in `members_analytics_audit.py`.

---

## Lessons / Recurring Issues

1. **A red CI run does not always mean a failing test — read the error kind.** This cycle every assertion passed; the Frontend job is red purely because a worker **crashed with a JS-heap OOM** and vitest surfaced it as an unhandled error. Don't chase `ZZPTrips.test.tsx` as a logic bug — the fix is memory/pool configuration (raise `NODE_OPTIONS=--max-old-space-size`, cap `poolOptions.forks.maxForks`, or shard the run), per runbook Lesson 2 (flaky/non-deterministic → Medium).

2. **The frontend suite is approaching its memory ceiling.** Total frontend tests grew 2756 → 3660 across the arc with no change to the worker-pool memory budget. A one-off OOM today becomes a recurring flake tomorrow unless the pool is given more headroom or the run is sharded. Treat E1 as the early warning, not a one-time blip.

3. **`members_analytics_audit.py` keeps re-attracting dead-`noqa` findings.** It cleared an `RUF100` + format finding at 10-10 and is back with another `RUF100` (`# noqa: BLE001`) at 10-13. Writing `# noqa: <rule>` for a rule the project does not enable is self-defeating — ruff flags the suppression as dead. When adding an exception-boundary `# noqa`, confirm the rule is actually enabled in `backend/ruff.toml`; otherwise keep the explanatory comment **without** the `# noqa:` token. A pre-push `ruff check` (the still-open **L1** from the 10-03 → 10-10 arc) would have caught this before it landed on `main`.

4. **The pre-push ruff gate (carried L1) would have blocked this run.** This is now the **fifth consecutive cycle** where a pre-push `ruff check src/ && ruff format --check src/` would have prevented the red Backend Lint job — the one `RUF100` is exactly the kind of mechanical finding that gate catches in seconds. It remains the highest-leverage prevention item and is carried forward again as L1. (Encouragingly, this run also shows the trend it is meant to protect: backend 0, format 0, lint down to 1.)
