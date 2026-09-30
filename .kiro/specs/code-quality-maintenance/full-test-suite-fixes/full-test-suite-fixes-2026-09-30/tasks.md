# Full Test Suite Fixes — 2026-09-30 — Tasks

CI run #36676588374 (2026-09-30, ❌ failure — Ruff Format only). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h.

> 🔴 **One job is red: Backend Lint & Static Analysis → Ruff Format (5 files).** All three test planes (backend, SAM, frontend), ruff lint, and vulture are green. The single High task (H1) is a mechanical `ruff format` that turns CI green; M1 prevents the recurrence; L1 is the standing reproducibility guard.
> Before any lint/format check, align local ruff to CI's **0.16.5** or counts will not reproduce (this cycle they already match).
> Verification commands assume: `cd backend && source .venv/bin/activate` (backend/lint) and `cd frontend` (frontend).

---

## Critical — collection / import errors (nothing else runs until these pass)

_None._ Backend (6622 tests) and SAM collect and pass cleanly; no import/collection blockers.

---

## High — running tests that fail + CI-blocking lint

- [x] **H1. Reformat the 5 backend files flagged by `ruff format` (the sole cause of the red run).** [S] — auto-fix, no logic change.
  - **File(s)**:
    - `backend/src/auth/admin_pool_resolver.py` (line 365 — list-comprehension wrapping)
    - `backend/src/routes/auth_routes.py` (lines 111, 130, 347, 354 — `jsonify(...)` / call args collapse to one line)
    - `backend/src/routes/sysadmin_health.py` (line 50 — remove one extra blank line)
    - `backend/src/routes/sysadmin_roles.py` (line 63 — remove one extra blank line)
    - `backend/src/services/cognito_service.py` (lines 124, 159, 171, 252, 264, 277, 289, 316, 341, 365, 473, 535, 586 — `resolve_pool_id(...)` / `admin_*` call args and method signatures collapse to one line)
  - **Why**: These are pure formatter drift introduced by commit `c829580` (2026-09-29, *"fix(auth): resolve Cognito admin ops to the registry pool"*) landed without running `ruff format`. `ruff check` and all tests already pass; only `ruff format --check` fails.
  - **Action**: Run the formatter over the backend source — it rewrites all 5 files automatically. Do **not** hand-edit; let the formatter own the layout.
    ```bash
    cd backend && source .venv/bin/activate && ruff format src/
    ```
  - **Verification**:
    ```bash
    cd backend && ruff format --check src/    # -> "308 files already formatted", 0 would-reformat
    ruff check src/                            # -> All checks passed!
    ```
    Then confirm nothing behavioural changed: `cd backend && pytest -q` (still 6612 passed / 10 skipped, 0 failed).

---

## Medium — recurrence prevention

- [x] **M1. Add a local pre-commit / pre-push guard that runs `ruff format --check` (and `ruff check`) so unformatted code cannot reach CI.** [M] — prevention; run **after** H1.
  - **File(s)**: `.pre-commit-config.yaml` (add/confirm a `ruff-format` hook) **or** the existing pre-push hook under `.git/hooks/` / the repo's hook installer; keep the `ruff==0.16.5` pin consistent with `backend/requirements-test.txt`.
  - **Why**: This is the **third** time in five cycles that format/lint debt entered `main` via a commit landed after the daily suite (09-26 format ×6, 09-28 lint ×2, 09-30 format ×5), and the auth plane is the repeat offender (requirements Lessons 1–2). The CI gate is honest but only catches it a cycle late. A local `ruff format --check` + `ruff check` gate blocks the commit (`c829580`-style) before it ever reaches CI.
  - **Action**: Wire a pre-commit (or pre-push) hook that runs both `ruff check backend/src/` and `ruff format --check backend/src/`, failing the commit/push on any diff. Pin the hook's ruff to 0.16.5. Document the one-line install in the repo README / SETUP.
  - **Verification**:
    ```bash
    # with an intentionally mis-formatted line staged, the hook must block:
    cd backend && ruff format --check src/    # exit non-zero on drift
    # after `ruff format src/` the same command exits 0 and the commit proceeds
    ```

---

## Low — hygiene / prevention

- [x] **L1. Confirm ruff stays pinned to 0.16.5 (reproducibility guard).** [S]
  - **File(s)**: `backend/requirements-test.txt` (canonical pin), CI workflows `full-test-suite.yml` / `backend-code-quality.yml`.
  - **Why**: This cycle local ruff (0.16.5) matched CI (0.16.5), so the 5-file format result is directly reproducible. Keep the pin in force so counts stay trustworthy. No change expected — standing guard carried forward.
  - **Action**: Verify the `ruff==0.16.5` pin is unchanged in all copies.
  - **Verification**:
    ```bash
    ruff --version                                   # -> ruff 0.16.5
    grep -rn "ruff==0.16.5" backend/requirements-test.txt .github/workflows/
    ```

---

## Execution order (see dependency-graph.json)

1. **H1** — `ruff format src/` on the 5 files → turns CI green. (independent, do first)
2. **M1** — add the pre-commit/pre-push `ruff format --check` + `ruff check` guard. (recommended after H1: land the fix, then prevent the recurrence)
3. **L1** — confirm the 0.16.5 pin, any time.

## Full-suite verification (re-confirm after H1)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `pytest sam/tests -q`
- Frontend: `cd frontend && npx vitest run`
- Lint + Format: `cd backend && ruff check src/ && ruff format --check src/`
- Or confirm the next `full-test-suite.yml` run is green after H1 lands.
