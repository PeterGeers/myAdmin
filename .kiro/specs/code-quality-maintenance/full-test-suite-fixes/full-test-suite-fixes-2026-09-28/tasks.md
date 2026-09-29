# Full Test Suite Fixes — 2026-09-28 — Tasks

CI run #36384687261 (2026-09-28). Fix tasks grouped by priority. Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h.

> Before starting any lint task, align local ruff to CI's **0.16.5** or counts will not reproduce.
> Verification commands assume: `cd backend && source .venv/bin/activate` (backend/lint) and `cd frontend` (frontend).
> ⚠️ **Members frontend failures — decide product-vs-test FIRST.** On 2026-09-26 every Members frontend "fix" was a stale test chasing an intentional product refactor (no product code changed). Confirm whether the missing `membership_type` control is an intentional refactor (⇒ fix tests) or a real regression (⇒ fix component) before editing anything.

---

## Critical — collection / import errors (nothing else runs until these pass)

_None this cycle._ Backend and SAM both collect and pass; there are no import/collection blockers. All work is in the High/Medium/Low bands below.

---

## High — running tests that fail + CI-blocking lint

- [x] **H1. Migrate the 3 Members-modal test files to drive the `membership_type` `LazySelect` combobox (10 failures, 3 files).** [M] — **STALE TESTS from an intentional product migration; do NOT revert the component.**
  - **File(s)** (tests only — no product change expected):
    - `frontend/src/__tests__/MembersAddModal.test.tsx` (5)
    - `frontend/src/__tests__/MembersEditDelete.test.tsx` (2)
    - `frontend/src/__tests__/MembersModals.apiError.test.tsx` (3)
    - Reference (do not edit): `frontend/src/components/members/MembersFieldFormBody.tsx` (routes `membership_type` through `LazySelect`), `frontend/src/components/common/LazySelect.tsx`, `.kiro/specs/Common/Frameworks/lazy-select/LAZY_SELECT.md`, and the already-migrated `frontend/src/components/common/__tests__/LazySelect.test.tsx` (copy its query patterns).
  - **Confirmed root cause**: `membership_type` moved from a native `<select name="membership_type">`/`<option>` to the shared `LazySelect` combobox. `LazySelect` renders `role="combobox"` (testid `membership_type-lazyselect`); its `role="option"` children appear **only after the combobox is opened**, and for `membership_type` only after the **async** `listMembershipTypes(true)` source resolves (`optionsDepKey="membership_type"`). The tests still query the retired native control → `No form control with name="membership_type"` (×5), `Unable to find … option "Premium"/"Standaard"` (×2), `expected null to be truthy` (×1), `Cannot read properties of null (reading 'value')` (×1).
  - **Action** (test-side, mirroring the 2026-09-26 stale-test resolution pattern):
    1. Replace `name="membership_type"` form-control lookups with the combobox trigger (`getByTestId('membership_type-lazyselect')` or `getByRole('combobox', { name: <label> })`).
    2. For option assertions/selection, **open the combobox first** (click / `ArrowDown`), then `await findByRole('option', { name })` (async — the membership catalog resolves via `listMembershipTypes`); pick by clicking the option. Mock `listMembershipTypes(true)` in these suites to return the expected active catalog (`Standaard`, `Premium`, …).
    3. For role-restricted assertions (R4.12), keep the "renders/hides option for caller with/without role" intent but assert against the opened listbox's `role="option"` set (LazySelect applies `filterOption`).
    4. For pre-fill on edit, read the trigger's displayed value (rest state) instead of `.value` on a native control.
    5. For valid-submit tests, drive the pick through the combobox so Formik `setFieldValue('membership_type', …)` fires, then assert the create/update payload as before.
    6. Add a short DEVIATION note in the fix commit: the task title says "regression" but the missing native control is an **intentional** LazySelect migration; the resolution is test-side only.
  - **Effort note**: single shared root cause across 3 files; factor the combobox interaction into one helper (see M1) so all 10 clear together — hence M not L.
  - **Verification**: `cd frontend && npx vitest run src/__tests__/MembersAddModal.test.tsx src/__tests__/MembersEditDelete.test.tsx src/__tests__/MembersModals.apiError.test.tsx` → 10 previously-failing tests pass, 0 new failures. Confirm no product file (`MembersFieldFormBody.tsx` / `LazySelect.tsx`) was modified.

- [x] **H2. Resolve ruff SIM103 in `cognito_utils.py` (CI-blocking).** [S]
  - **File(s)**: `backend/src/auth/cognito_utils.py:158`.
  - **Action**: SIM103 — "Return the condition directly". Ruff offers only a *hidden* unsafe fix, so **rewrite by hand**: replace an `if <cond>: return True` / `return False` pattern with `return <cond>` (or `return bool(<cond>)` if a non-bool truthy value must be normalised). Do **not** run `ruff check --fix --unsafe-fixes` blindly; verify the boolean semantics are preserved (watch for `None`/truthy-vs-`True` differences).
  - **Verification**: `cd backend && ruff check src/auth/cognito_utils.py` → 0 errors; run the cognito_utils unit tests (`pytest tests -q -k cognito` or the file's suite) → green.

- [x] **H3. Resolve ruff S110 in `tenant_context.py` (CI-blocking).** [S]
  - **File(s)**: `backend/src/auth/tenant_context.py:246`.
  - **Action**: S110 — bare `try`/`except`/`pass` swallows the exception silently. Replace the `pass` with a real handler: log the exception (e.g. `logger.warning("...", exc_info=True)` or `logger.debug(...)`) and/or narrow the `except` to the specific expected exception type. A silent swallow here is high-risk — this is the package that hid the Flask import-coupling break last cycle. Avoid papering over it with `# noqa: S110`.
  - **Verification**: `cd backend && ruff check src/auth/tenant_context.py` → 0 errors; run the tenant_context suite (`pytest tests/test_tenant_context.py -q`) → green.

---

## Medium — related / follow-on

- [x] **M1. Factor the Members-modal `LazySelect` interaction into one shared test helper.** [S]
  - **File(s)**: the 3 Members modal test files + a shared helper (e.g. `frontend/src/__tests__/helpers/lazySelect.ts` or reuse an existing test-utils location).
  - **Action**: Once H1 lands, extract the combobox drive into a **single shared helper** — `openMembershipType(user)` / `pickMembershipType(user, name)` / `getMembershipTypeTrigger()` — wrapping the open-then-`findByRole('option')` flow, used by all 3 files. This makes the next LazySelect/control refactor a one-line helper change rather than 10 scattered query updates, and directly addresses Lessons #1/#2 (the Members area recurs one cycle behind a shared-building-block adoption). Optionally generalise it to any `{name}-lazyselect` trigger so other LazySelect consumers reuse it.
  - **Verification**: `cd frontend && npx vitest run src/__tests__/MembersAddModal.test.tsx src/__tests__/MembersEditDelete.test.tsx src/__tests__/MembersModals.apiError.test.tsx` → still green via the shared helper.

- [x] **M2. Confirm the `auth/` lint debt origin and prevent recurrence.** [S]
  - **File(s)**: `backend/src/auth/cognito_utils.py`, `backend/src/auth/tenant_context.py`.
  - **Action**: `git blame` lines 158 / 246 to confirm whether SIM103/S110 entered with the 2026-09-26 Flask-decoupling edit (C1). If so, note it in the fix commit so the pattern (lint debt slipping in during a red cycle, surfacing the next red cycle) is visible. No behaviour change beyond H2/H3.
  - **Verification**: `cd backend && ruff check src/auth/` → 0 errors.

---

## Low — hygiene / prevention

- [x] **L1. Confirm ruff stays pinned to 0.16.5 (reproducibility).** [S]
  - **File(s)**: `backend/requirements-test.txt` (canonical pin), CI workflows `full-test-suite.yml` / `backend-code-quality.yml`.
  - **Action**: Verify the `ruff==0.16.5` pin (set as canonical on 2026-09-26 / L1) is still in force in all copies, so the 2-error count stays reproducible. No change expected — this is a guard.
  - **Verification**: `ruff --version` → `ruff 0.16.5` locally; grep the workflows/requirements confirm the pin unchanged.

---

## Execution order (see dependency-graph.json)

1. **H1** — the 10 frontend failures (single root cause; triage product-vs-test first).
2. **H2, H3** — the 2 CI-blocking ruff lint errors (independent of H1 and of each other; can run in parallel).
3. **M1** (after H1), **M2** (after H2/H3).
4. **L1** — guard, any time.

## Full-suite verification (after all tasks)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `pytest sam/tests -q`
- Frontend: `cd frontend && npx vitest run`
- Lint: `cd backend && ruff check src/ && ruff format --check src/`
- Or push and confirm the `full-test-suite.yml` run goes green.
