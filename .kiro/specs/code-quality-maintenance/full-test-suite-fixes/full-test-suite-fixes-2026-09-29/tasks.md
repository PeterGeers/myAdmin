# Full Test Suite Fixes — 2026-09-29 — Tasks

CI run #36530772053 (2026-09-29, ✅ success). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h.

> ✅ **This cycle is fully green — there is nothing to repair.** Backend, SAM, and frontend all pass; ruff lint, ruff format, and vulture all pass. The tasks below are lightweight **verification / recurrence-watch** items only. None of them change failing code, because there is none.
> Before any lint check, align local ruff to CI's **0.16.5** or counts will not reproduce.
> Verification commands assume: `cd backend && source .venv/bin/activate` (backend/lint) and `cd frontend` (frontend).

---

## Critical — collection / import errors (nothing else runs until these pass)

_None._ Backend (6564 tests) and SAM (981 tests) collect and pass cleanly; no import/collection blockers.

---

## High — running tests that fail + CI-blocking lint

_None._ Zero test failures across all three planes; zero CI-blocking ruff lint errors. Both 2026-09-28 High-band items (H1 Members-modal `LazySelect` migration, H2 SIM103, H3 S110) are resolved and did not recur.

---

## Medium — recurrence watch (verification only)

- [ ] **M1. Confirm the Members frontend area held green and keep the recurrence guard visible.** [S] — **watch only; no code change.**
  - **File(s)** (read-only verification): `frontend/src/__tests__/MembersAddModal.test.tsx`, `frontend/src/__tests__/MembersEditDelete.test.tsx`, `frontend/src/__tests__/MembersModals.apiError.test.tsx`, `frontend/src/components/common/__tests__/LazySelect.test.tsx`, and the `MembersPage*` suites.
  - **Why**: This area regressed on 2026-09-26 (`MembersPage`) and 2026-09-28 (Members modals), each one cycle behind an intentional UI refactor. It is green on 09-29; the point of this task is to confirm the 09-28 test migration is stable and to re-affirm the pre-merge habit (run the *whole* Members group before merging any Members UI refactor, per requirements Lesson 2), not to change anything.
  - **Action**: Run the full Members frontend group and confirm 0 failures. If a shared `LazySelect` test helper was introduced (09-28 M1 follow-on), confirm the 3 modal suites still use it so the next control refactor is a one-line helper change.
  - **Verification**: `cd frontend && npx vitest run src/__tests__/MembersAddModal.test.tsx src/__tests__/MembersEditDelete.test.tsx src/__tests__/MembersModals.apiError.test.tsx src/components/common/__tests__/LazySelect.test.tsx` → all pass, 0 failures.

- [ ] **M2. Confirm the `auth/` package is still lint-clean and the gate is intact.** [S] — **watch only; no code change.**
  - **File(s)** (read-only verification): `backend/src/auth/cognito_utils.py`, `backend/src/auth/tenant_context.py`, `backend/ruff.toml`.
  - **Why**: The 09-28 debt (SIM103 in `cognito_utils.py:158`, S110 in `tenant_context.py:246`) entered via security-remediation commit `e808368` and is now fixed. Confirm no new SIM/S debt re-entered this package and that SIM103/S110 remain enabled (not ignored) in `ruff.toml`.
  - **Action**: Run ruff over `src/auth/` and confirm 0 errors; confirm `SIM103`/`S110` are not in the `ignore` list of `backend/ruff.toml`.
  - **Verification**: `cd backend && ruff check src/auth/` → 0 errors; `grep -nE "SIM103|S110" backend/ruff.toml` shows they are not ignored.

---

## Low — hygiene / prevention

- [ ] **L1. Confirm ruff stays pinned to 0.16.5 (reproducibility guard).** [S]
  - **File(s)**: `backend/requirements-test.txt` (canonical pin), CI workflows `full-test-suite.yml` / `backend-code-quality.yml`.
  - **Action**: Verify the `ruff==0.16.5` pin is still in force in all copies so lint counts stay reproducible. No change expected — this is a standing guard carried forward from prior cycles.
  - **Verification**: `ruff --version` → `ruff 0.16.5` locally; grep the workflows/requirements confirm the pin unchanged.

---

## Execution order (see dependency-graph.json)

All remaining tasks are independent, read-only verification items and may run in any order (or in parallel):

1. **M1** — confirm Members frontend area held green.
2. **M2** — confirm `auth/` still lint-clean and gate intact.
3. **L1** — confirm ruff pin, any time.

## Full-suite verification (optional re-confirm; CI already green)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `pytest sam/tests -q`
- Frontend: `cd frontend && npx vitest run`
- Lint: `cd backend && ruff check src/ && ruff format --check src/`
- Or simply confirm the latest `full-test-suite.yml` run (#36530772053) is green — it is.
