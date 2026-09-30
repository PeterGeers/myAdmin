# Full Test Suite Fixes — 2026-09-30

## Summary

Full Test Suite run (GitHub Actions run #36676588374) on `main`, 2026-09-30 06:07 UTC. **CI conclusion: ❌ failure.** Analysis is CI-artifact-based only (no local scans), from the downloaded `backend-test-reports`, `sam-test-reports`, `frontend-test-reports`, and `backend-lint-reports` artifacts.

| Category                     | Count                               | Δ vs 2026-09-29                          |
| ---------------------------- | ----------------------------------- | ---------------------------------------- |
| Backend test failures        | 0 (of 6622; 6612 passed, 10 skip)   | — stable green (+58 tests collected)     |
| SAM module-plane tests       | 0 (all passed)                      | — stable green                           |
| Frontend test failures       | 0 (of 2734; 2722 passed, 12 skip)   | — stable green                           |
| Ruff lint errors             | 0 (Pass)                            | — stable green                           |
| Ruff format violations       | **5 files** (Fail)                  | 🔴 +5 (was 0) — **regression**           |
| Vulture (dead code)          | ✅ Pass                             | — stable green                           |

**CI job result**: Backend tests ✅ · SAM module-plane ✅ · Frontend tests ✅ · Backend Lint & Static Analysis ❌ (Ruff Format only). **The one and only reason the run is red is `ruff format` reporting 5 backend files that would be reformatted.** Ruff lint, vulture, and all three test planes are green.

> ⚠️ **Ruff version**: CI ran **ruff 0.16.5** (pinned, matches local `ruff 0.16.5`). The 5 format violations are genuine formatting drift, **not** a version mismatch.

> ℹ️ **This is a small, mechanical failure.** The fix is a single `ruff format backend/src/` — no logic changes, no manual editing. See `tasks.md` H1.

---

## Test Results — Backend (6612 passed, 10 skipped, 0 failed, 0 errors — 604.43s)

✅ **Green.** 6622 tests collected, 0 failures, 0 errors, 10 skipped (604.43s ≈ 10m04s). Test count grew +58 vs 09-29 (6554 → 6612 passed), consistent with new coverage landing. The projection property-test and STR/Airbnb parsing areas (red for several cycles up to 2026-09-26) **stayed green** for a fifth consecutive cycle.

---

## Test Results — SAM module-plane (all passed, 0 failed, 0 errors)

✅ **Green.** The SAM plane collects and passes cleanly (SUMMARY shows 100% dots, no failures). The 2026-09-26 `flask` import-coupling collapse remains fixed; the import-boundary guard continues to hold — fourth consecutive green cycle for this plane.

---

## Test Results — Frontend (2722 passed, 12 skipped, 0 failed, 0 errors, 200 files — 112.91s)

✅ **Green.** 2734 tests across 200 files, 0 failures. The Members-modal `LazySelect` suites that regressed on 09-28 and were fixed on 09-29 **held green** for a second consecutive cycle.

---

## Lint & Static Analysis (Backend Lint job — ❌ FAIL: Ruff Format only)

| Check | Result |
|-------|--------|
| Ruff Lint | ✅ Pass (0 errors) |
| Ruff Format | ❌ **Fail — 5 files would be reformatted, 303 already formatted** |
| Vulture | ✅ Pass (no dead code) |

### Ruff Format — ❌ Fail (5 files, all auto-fixable)

Every violation is pure whitespace / line-wrapping drift. There are **no** rule-code lint errors — this is `ruff format` (the formatter), not `ruff check` (the linter). All 5 are fixed by a single `ruff format backend/src/`:

| # | File | Location(s) | Nature of drift | Auto-fixable |
| - | ---- | ----------- | --------------- | ------------ |
| 1 | `backend/src/auth/admin_pool_resolver.py` | line 365 | list-comprehension should be wrapped across multiple lines | ✅ `ruff format` |
| 2 | `backend/src/routes/auth_routes.py` | lines 111, 130, 347, 354 | multi-line call args / `jsonify(...)` should collapse onto one line | ✅ `ruff format` |
| 3 | `backend/src/routes/sysadmin_health.py` | line 50 | one extra blank line before `# Create blueprint` | ✅ `ruff format` |
| 4 | `backend/src/routes/sysadmin_roles.py` | line 63 | one extra blank line before comment | ✅ `ruff format` |
| 5 | `backend/src/services/cognito_service.py` | lines 124, 159, 171, 252, 264, 277, 289, 316, 341, 365, 473, 535, 586 (many) | `resolve_pool_id(...)` / `admin_*` call args and several method signatures should collapse onto one line | ✅ `ruff format` |

**Grouped by root cause:** all 5 stem from a **single commit** — `c829580` (2026-09-29 12:22 +0200, *"fix(auth): resolve Cognito admin ops to the registry pool, not the legacy var"*) — which was the last commit to touch every one of these files. The edits were made by hand and committed **without running `ruff format`**, landing **after** the 09-29 green suite and surfacing on the next scheduled run (09-30). This is the same delivery vector as the 09-28 `auth/` lint regression (a post-suite commit), only the tripped gate is the formatter this time rather than the linter.

- **Total by category**: format-only = 5 files; lint rule-code errors = 0; version mismatch = none (0.16.5 == 0.16.5).
- **Auto-fixable vs manual**: 5 auto-fixable, 0 manual.

### Ruff Lint — ✅ Pass (0 errors), ruff 0.16.5

### Vulture — ✅ Pass (no dead code found)

---

## Comparison with recent runs (the 09-26 → 09-30 arc)

| Metric               | 2026-09-26 | 2026-09-27 | 2026-09-28 | 2026-09-29 | 2026-09-30 | Trend                                       |
| -------------------- | ---------- | ---------- | ---------- | ---------- | ---------- | ------------------------------------------- |
| CI conclusion        | ❌ failure | ✅ success | ❌ failure | ✅ success | ❌ failure | Alternating — **red this cycle (format)**   |
| Backend failures     | 15 (+7 err)| 0          | 0          | 0          | 0          | ✅ Held green (5 cycles)                     |
| SAM plane            | ❌ collapse | 0          | 0          | 0          | 0          | ✅ Held green (guard working)                |
| Frontend failures    | 7          | 0          | 10         | 0          | 0          | ✅ Held green (Members modals stable)        |
| Ruff lint errors     | 14         | 0          | 2          | 0          | 0          | ✅ Held green                                |
| Ruff format files    | 6          | 0          | 0          | 0          | **5**      | 🔴 **Recurrence** — format debt is back      |
| Vulture              | Pass       | Pass       | Pass       | Pass       | Pass       | — Stable                                    |
| Total backend tests  | —          | —          | 6564       | 6564       | 6622       | ↑ +58 since 09-29                           |
| Total frontend tests | 2656       | 2716       | 2716       | 2734       | 2734       | — stable                                    |

### Held / fixed (stayed green)

- ✅ Backend projection property tests + STR/Airbnb parsing — durable fixes held for a fifth cycle.
- ✅ SAM `flask` import-coupling — plane still collects; import-boundary guard doing its job.
- ✅ Frontend Members-modal `LazySelect` migration — held green a second cycle (fixed 09-29).
- ✅ Ruff lint + vulture — green this cycle.

### Regression this cycle

- 🔴 **Ruff format 0 → 5** — five backend files (3 in the `auth`/Cognito plane) drifted out of format via commit `c829580`. Not a recurrence of the *same files* fixed last time, but a **recurrence of the format-debt failure mode** last seen on 09-26 (6 files), and a recurrence of the **auth-plane-commit-after-the-suite delivery vector** last seen on 09-28.

### New failures introduced by the previous cycle's changes

- The 09-29 spec was fully green and carried only verification tasks, so this is **not** a regression from a 09-29 *fix*. It is new debt from a **feature/bugfix commit** (`c829580`) that landed the same day the 09-29 suite ran but after it — i.e., the debt was in `main` before this run but not covered by the 09-29 artifact.

---

## Lessons / Recurring Issues

1. **RECURRING: format/lint debt keeps entering `main` via commits landed *after* the daily suite — now three times in five cycles.** 09-26 (6 format files), 09-28 (2 lint errors, `auth/`), and now 09-30 (5 format files, mostly `auth/`). Each time a commit lands after that day's scheduled run and the gate trips on the next run. The gate itself is honest and CI-blocking; the miss is always **timing + no local pre-push format/lint check**. This is the single most repeated pattern in the arc and warrants a prevention task (see M1), not just another one-line fix.

2. **RECURRING: the `auth`/Cognito plane is the repeat offender.** 09-28 lint debt (`cognito_utils.py`, `tenant_context.py`) and 09-30 format debt (`admin_pool_resolver.py`, `auth_routes.py`, `cognito_service.py`) both originated in the auth package, both from security/auth-hardening commits. Reviewers of auth-plane changes should run `ruff format --check` and `ruff check` on the touched files as part of the PR, since this area churns and keeps tripping the gate.

3. **`ruff format` (formatter) is a distinct gate from `ruff check` (linter) — both are CI-blocking.** This cycle `ruff check` passed cleanly; the red came entirely from `ruff format`. A commit can be lint-clean yet format-dirty. Any local guard must run **both** `ruff check` and `ruff format --check`.

4. **The fix is mechanical; the prevention is the real work.** H1 (`ruff format backend/src/`) closes this instance in seconds. The recurring pattern (Lesson 1) will keep re-tripping until an unformatted commit is blocked *before* it reaches CI — hence M1 (pre-commit/pre-push `ruff format --check` guard). Prefer the durable prevention over repeatedly re-running the formatter each cycle.

5. **Ruff pin held (0.16.5) — counts are reproducible.** Local and CI both on 0.16.5, so `ruff format --check backend/src/` locally reproduces the 5-file result exactly. The pin is doing its job (see L1).

6. **Every cycle still deserves a spec, red or green.** This red cycle, following a green one, is exactly the alternating pattern the arc history was built to surface — and it directly exposes the "post-suite commit" recurrence (Lesson 1) that a single green snapshot would have hidden.
