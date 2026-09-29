# Full Test Suite Fixes — 2026-09-28

## Summary

Full Test Suite run (GitHub Actions run #36384687261) on `main`, 2026-09-28 06:04 UTC. **CI conclusion: ❌ failure.** Analysis is CI-artifact-based only (no local scans), from the downloaded `backend-test-reports`, `sam-test-reports`, `frontend-test-reports`, and `backend-lint-reports` artifacts.

| Category                     | Count                              | Δ vs 2026-09-27                       |
| ---------------------------- | ---------------------------------- | ------------------------------------- |
| Backend test failures        | 0 (of 6564; 6554 passed, 10 skip)  | — stable green                        |
| SAM module-plane tests       | 0 (of 981; all passed)             | — stable green                        |
| Frontend test failures       | 10 (of 2716, in 3 files)           | 🔺 +10 (was 0/2716) — **regression**  |
| Ruff lint errors             | 2 (0 auto-fixable)                 | 🔺 +2 (was 0) — **regression**        |
| Ruff format violations       | 0 (Pass)                           | — stable green                        |
| Vulture (dead code)          | ✅ Pass                            | — stable green                        |

**CI job result**: Backend tests ✅ · SAM module-plane ✅ · **Frontend tests ❌** · **Backend Lint & Static Analysis ❌ (Ruff Lint)**. Two planes red this cycle; both are *regressions* from the green 2026-09-27 run.

> ⚠️ **Ruff version**: CI ran **ruff 0.16.5** (pinned, matches local). Align local ruff to 0.16.5 before reproducing/fixing lint or counts will not match.

> ⚠️ **Count note**: the ruff lint report header prints `Found 4 errors` in one section but the authoritative "All Errors" block lists exactly **2** concrete errors (`Found 2 errors.`). The 2 figure is authoritative; the per-rule breakdown below sums to 2.

---

## Test Failures — Backend (6554 passed, 10 skipped, 0 failed, 0 errors — 854.74s)

✅ **Green.** 6564 tests collected, 0 failures, 0 errors, 10 skipped. The recurring projection property-test and STR/Airbnb fixture areas (red for many prior cycles, fixed on 2026-09-26) **stayed green** this cycle.

---

## Test Failures — SAM module-plane (981 tests, 0 failed, 0 errors, 0 skipped)

✅ **Green.** The SAM plane collects and passes cleanly. The 2026-09-26 `flask` import-coupling collapse remains fixed; the import-boundary guard test (M2 from 09-26) is holding.

---

## Test Failures — Frontend (10 failed, 2694 passed, 12 skipped, 3 files — 150.80s) 🔺 REGRESSION

Frontend was green on 2026-09-27 (0 failed). It is red again — **10 failures across 3 files, all in the Members Add/Edit modal feature area**. Every failure shares a single root cause: the `membership_type` dropdown was migrated from a native `<select>` to the shared **`LazySelect`** combobox, and the 3 modal test files were not updated in lock-step — so they still query the retired native `name="membership_type"` control and its at-rest `<option>`s.

### RC-F1 — Members modals migrated `membership_type` to `LazySelect`; tests still query the old native `<select>` (10 failures) ⚠️ RECURRING AREA (Members frontend, 2nd consecutive red cycle for this feature)

Shared symptom family across all three files: `No form control with name="membership_type"`, `Unable to find an accessible element with the role "option" and name "Premium"/"Standaard"`, `expected null to be truthy`, and `Cannot read properties of null (reading 'value')`. The modal renders its section headings (`Persoonlijk`, `Lidmaatschap`) but the membership-type field/options inside are absent, so every test that queries or submits that control fails.

#### `frontend/src/__tests__/MembersAddModal.test.tsx` (5 failures)

| Test | Error |
| ---- | ----- |
| `… broadened over the resolved field set > opening + sectioned rendering (R8.3, R4.9) > opens the modal and renders the resolved fields in functional-group sections` | `expected null to be truthy` |
| `… > value-level role-restricted enum options (R4.12) > renders a role-restricted option for a caller holding the role` | `Unable to find an accessible element with the role "option" and name "Premium"` |
| `… > value-level role-restricted enum options (R4.12) > hides a role-restricted option for a caller lacking the role` | `Unable to find an accessible element with the role "option" and name "Standaard"` |
| `… > valid submit (R8.3, Property 2) > calls createMember with the storage-group-shaped nested body and NO tenant field` | `No form control with name="membership_type"` |
| `… > success closes the modal and refreshes the list > closes the modal and reloads members after a successful create` | `No form control with name="membership_type"` |

#### `frontend/src/__tests__/MembersEditDelete.test.tsx` (2 failures)

| Test | Error |
| ---- | ----- |
| `MembersEditModal — broadened over the resolved field set > opening + pre-fill (R8.2, R4.9) > opens the edit modal from the view-modal footer, pre-filled from the nested member` | `Cannot read properties of null (reading 'value')` |
| `… > valid submit (R8.2, Property 2) > calls updateMember with the storage-group-shaped nested body (NO tenant)` | `No form control with name="membership_type"` |

#### `frontend/src/__tests__/MembersModals.apiError.test.tsx` (3 failures)

| Test | Error |
| ---- | ----- |
| `MembersAddModal — 422 field errors (task 4.4) > renders a matched field error INLINE and fires a summary toast` | `No form control with name="membership_type"` |
| `… > folds an UNMATCHED field into the summary toast` | `No form control with name="membership_type"` |
| `… > shows the localized fallback toast on a network failure` | `No form control with name="membership_type"` |

**Root cause (one defect, three files) — CONFIRMED: intentional product migration, STALE TESTS.** The Members Add/Edit modals migrated every enum/reference/scope dropdown — including `membership_type` — from a native `<select name="membership_type">`/`<option>` to the shared **`LazySelect`** building block (`.kiro/specs/Common/Frameworks/lazy-select/`, reference impl `frontend/src/components/members/MembersFieldFormBody.tsx`). `LazySelect` renders a `role="combobox"` trigger (testid `membership_type-lazyselect`) whose `role="option"` children are revealed **only after the combobox is opened** — it is no longer a native form control, and its options are not in the DOM at rest. That is exactly why the tests fail:

- `No form control with name="membership_type"` — there is no native `<select>`/`<input>` named `membership_type` anymore; the control is a combobox addressed by `membership_type-lazyselect` / `role="combobox"`.
- `Unable to find … role "option" and name "Premium"/"Standaard"` — options only render once the combobox is opened (and, for `membership_type`, after its **async** `listMembershipTypes(true)` source resolves — `optionsDepKey="membership_type"`).
- `expected null to be truthy` / `Cannot read properties of null (reading 'value')` — the tests `querySelector` the old native control and get `null`.

The component code itself documents the change ("the old `data-dimension` hook on the native `<select>` is gone"; the synthetic-current-value `renderOptions` stopgap was removed). The `LazySelect` adoption checklist (step 6 / the Change-With-Tests Contract in `32-frontend-ui.md`) requires updating the paired test **in the same change** — that was done for the direct `LazySelect.test.tsx` suites but **not** for these 3 Members-modal files, so they went stale. This is the **same class of Members-frontend regression seen on 2026-09-26** (RC-F1/RC-F2 there were `MembersPage` row/column/badge test drift after intentional product refactors), confirming the feature area recurs one cycle behind a UI refactor. **Resolution direction: fix the stale tests to drive the LazySelect combobox — do NOT revert the migration.**

---

## Lint & Static Analysis (Backend Lint job — ❌ FAIL, CI-blocking)

### Ruff Lint — 2 errors (0 auto-fixable), ruff 0.16.5 🔺 REGRESSION

| Rule    | Count | Description                                                    | Auto-fixable |
| ------- | ----- | -------------------------------------------------------------- | ------------ |
| SIM103  | 1     | Return the condition directly (instead of `if x: return True`) | No — only a *hidden* unsafe fix (`--unsafe-fixes`) |
| S110    | 1     | `try`-`except`-`pass` detected — consider logging the exception | No (manual)  |

**Errors by file**:

- `backend/src/auth/cognito_utils.py:158:5` — SIM103 (return the boolean condition directly)
- `backend/src/auth/tenant_context.py:246:9` — S110 (bare `try/except/pass`; add logging or a narrow handler)

**Note**: Neither error is safely auto-fixable. Ruff reports `No fixes available (1 hidden fix can be enabled with the --unsafe-fixes option)` for the SIM103 — do **not** blanket `--unsafe-fixes`; apply the SIM103 rewrite by hand and confirm behaviour. Both errors live in `backend/src/auth/` — the **same package** that was refactored on 2026-09-26 to decouple Flask (C1: `tenant_context.py`). It is likely this lint debt was introduced by that decoupling edit (the `try/except/pass` at `tenant_context.py:246` and the boolean helper in `cognito_utils.py:158`) and simply not caught then because CI was already red for other reasons that cycle, then green on 09-27 — worth confirming against the blame.

### Ruff Format — ✅ Pass (all files already formatted)

### Vulture — ✅ Pass (no dead code found)

---

## Comparison with 2026-09-27 (and the 09-26 → 09-27 arc)

| Metric               | 2026-09-26 | 2026-09-27 | 2026-09-28 | Trend                                      |
| -------------------- | ---------- | ---------- | ---------- | ------------------------------------------ |
| Backend failures     | 15 (+7 err)| 0          | 0          | ✅ Held green                              |
| SAM plane            | ❌ collapse | 0          | 0          | ✅ Held green (guard working)              |
| Frontend failures    | 7          | 0          | 10         | 🔺 Regressed again — Members area          |
| Ruff lint errors     | 14         | 0          | 2          | 🔺 Regressed (new debt in `auth/`)         |
| Ruff format files    | 6          | 0          | 0          | ✅ Held green                              |
| Vulture              | Pass       | Pass       | Pass       | — Stable                                   |
| Total frontend tests | 2656       | 2716       | 2716       | ↑ +60 since 09-26                          |

### Held / fixed (stayed green from 2026-09-27)

- ✅ Backend projection property tests + STR/Airbnb parsing — the durable fixes (inject the seams / commit the fixtures) stuck for a second cycle.
- ✅ SAM `flask` import-coupling — plane still collects; the import-boundary guard (M2) is doing its job.
- ✅ Ruff format + Vulture.

### New / regressed this cycle

- 🔺 **Frontend regressed 0 → 10** — all in the **Members modal** area (`MembersAddModal`, `MembersEditDelete`, `MembersModals.apiError`), one shared root cause: the `membership_type` dropdown moved to the shared `LazySelect` combobox (via `MembersFieldFormBody.tsx`) and these 3 test files weren't migrated with it. Adjacent-but-different from the 09-26 Members regression (which was `MembersPage`), so the *feature area* is recurring even though the specific files rotate.
- 🔺 **Ruff lint regressed 0 → 2** — `SIM103` + `S110`, both inside `backend/src/auth/` (the package touched by the 09-26 Flask decoupling).

---

## Lessons / Recurring Issues

1. **The Members frontend suite is a recurring red zone — the *area* recurs even when the *file* changes.** 09-26 it was `MembersPage` (rows/columns/region badge); 09-28 it is the Members Add/Edit **modals** (the `membership_type` → `LazySelect` migration). Both are one cycle behind an intentional UI refactor, with tests querying the old DOM shape. Before merging any Members UI refactor, re-run the *whole* Members test group locally — `MembersAddModal`, `MembersEditDelete`, `MembersModals.*`, `MembersPage*` — not just the file you edited.

2. **The `LazySelect` adoption checklist step 6 (Change-With-Tests Contract) was skipped for the Members modals.** The migration updated the direct `LazySelect.test.tsx` suites but left the 3 consuming Members-modal tests querying the retired native `<select name="membership_type">`. When a shared building block (LazySelect, Table Filter, etc.) is adopted, migrate **every consumer's** paired tests in the same change — grep for the old query shape (`name="membership_type"`, `getByRole('option')` at rest) across the whole feature, not just the building block's own tests. The fix here is test-side (drive the combobox); do **not** revert the migration.

3. **`auth/` accrued lint debt after the Flask decoupling — keep the lint gate honest across cycles.** The 2 new ruff errors (`SIM103` in `cognito_utils.py:158`, `S110` in `tenant_context.py:246`) both sit in the package rewritten on 09-26. A `try/except/pass` that silently swallows exceptions (S110) is exactly the kind of thing that hides the *next* import/coupling break. Fix S110 with real logging (not a `# noqa`), and confirm the SIM103 rewrite by hand rather than reaching for `--unsafe-fixes`.

4. **Lint is CI-blocking — treat these 2 errors with the same urgency as the test failures.** Two errors is small, but the job is red until they clear, which blocks the whole suite's green status.

5. **Ruff pin held (0.16.5) — counts are reproducible.** The L1 pin from 09-26 is still in force locally and in CI, so the 2-error count is trustworthy and directly reproducible with `ruff check backend/src/`.

---

## M2 — `auth/` lint-debt origin & recurrence-guard confirmation (2026-09-28, read-only investigation)

**Introducing commit (both findings): `e808368` — "security: remediate security-assessment-2026-09-26 findings (H1, M1, M2, L1-L4)", 2026-09-27 13:36 +0200.**

- **S110** (`tenant_context.py:246`): the offending `try: … except Exception: pass` block was **added by `e808368`** — it lives inside the *new* `_log_sysadmin_bypass` helper that commit introduced (diff adds `+ try:` / `+ except Exception:` / `+ pass`). At `e808368^` that region had no such block. That same helper carries the "importable on the Flask-free SAM plane" lazy-import note, so this audit path is the Flask-decoupling-aware refactor.
- **SIM103** (`cognito_utils.py:158`): the `_jwt_verification_required()` predicate (`if …: return True` / `return False`) was **also added by `e808368`** — the function does not exist at `e808368^` (grep count 0).

**Hypothesis verdict — REFUTED on specifics, correct in spirit.** The tasks/requirements hypothesised the debt "arrived with the 2026-09-26 Flask-decoupling change (C1)". In fact both findings arrived one day later, in the **2026-09-27 security-remediation commit `e808368`**, not a 2026-09-26 commit. It is Flask-decoupling-*adjacent* (the new audit helper is written for the Flask-free plane), but the concrete origin is the security remediation, not the original decoupling. Only two `auth/` commits exist in the 09-25→09-29 window (`c344f77` 09-27 00:03, `e808368` 09-27 13:36); the debt is entirely in `e808368`. It surfaced in CI run #36384687261 (2026-09-28 06:04) — the first Full Suite run after `e808368` landed.

**Recurrence guard — ALREADY IN PLACE, no config change made.**
- `backend/ruff.toml` enables a broad rule set (40+ families). SIM (42 rules incl. **SIM103**) and S/flake8-bandit (6 rules incl. **S110**) are both in `linter.rules.enabled` (verified via `ruff check --show-settings`). The config declares only an `ignore` list (BLE001, DTZ*) — it does **not** weaken SIM/S.
- Empirically verified with ruff **0.16.5** (CI-pinned): a fresh probe file with both patterns is flagged `SIM103` + `S110` under the project config.
- CI runs `ruff check src/ --exclude src/validate_pattern/` on every push in **both** `backend-code-quality.yml` and `full-test-suite.yml`, and lint is CI-blocking. So this class of issue is caught locally and in CI going forward.
- **No config change required or made** (per task: do NOT weaken/invent config). The gate is honest; the 09-28 miss was timing — `e808368` merged after that day's suite, and the debt surfaced on the next scheduled run.
