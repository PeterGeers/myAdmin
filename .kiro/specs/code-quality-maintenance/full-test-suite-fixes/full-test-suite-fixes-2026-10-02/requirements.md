# Full Test Suite Fixes — 2026-10-02

## Summary

Full Test Suite run (GitHub Actions run #36978727343) on `main`, 2026-10-02 07:28 UTC. **CI conclusion: ❌ failure.** Analysis is CI-artifact-based only (no local scans), from the downloaded `backend-test-reports`, `sam-test-reports`, `frontend-test-reports`, and `backend-lint-reports` artifacts.

| Category                     | Count                                 | Δ vs 2026-09-30                              |
| ---------------------------- | ------------------------------------- | -------------------------------------------- |
| Backend test failures        | 0 (of 6645; 6633 passed, 12 skip)     | — stable green (+21 tests collected)         |
| SAM module-plane tests       | **collection ERROR** (2 modules)      | 🔴 **regression** — plane cannot collect     |
| Frontend test failures       | 0 (of 2756; 2744 passed, 12 skip)     | — stable green (+22 tests collected)         |
| Ruff lint errors (backend)   | 0 (Pass)                              | — stable green                               |
| Ruff format violations (be)  | 0 (Pass)                              | ✅ −5 (was 5) — **09-30 regression resolved** |
| Vulture (dead code)          | ✅ Pass                               | — stable green                               |

**CI job result**: Backend tests ✅ · **SAM module-plane ❌ (collection interrupted)** · Frontend tests ✅ · Backend Lint & Static Analysis ✅. **The one and only reason the run is red is the SAM plane failing to collect** — 2 test modules raise `ModuleNotFoundError` at import time, so pytest interrupts before running any SAM test. All three other planes (backend, frontend, backend lint/format/vulture) are green.

> 🔴 **This is a Critical collection failure, not a test assertion failure.** No SAM test actually ran — collection was interrupted by 2 import errors sharing a single root cause. The 09-30 `ruff format` regression (5 files) is **resolved** this cycle (format ✅).

> ⚠️ **Ruff version**: CI ran **ruff 0.16.5** (pinned, matches local). Backend lint/format/vulture all green — no version-mismatch concern this cycle.

---

## Test Results — Backend (6633 passed, 12 skipped, 0 failed, 0 errors — 875.78s)

✅ **Green.** 6645 tests collected, 0 failures, 0 errors, 12 skipped (875.78s ≈ 14m36s). Count grew +21 vs 09-30 (6612 → 6633 passed). The projection property-test and STR/Airbnb parsing areas (red through 2026-09-26) **stayed green** for a seventh consecutive cycle.

---

## Test Results — SAM module-plane (❌ COLLECTION INTERRUPTED — 2 errors, 0 tests run)

🔴 **Red — the sole cause of the failed run.** pytest aborted during collection with:

```
ERROR tests/test_hdcn_backfill.py
ERROR tests/test_onboarding_lib_resolver.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
```

Both errors share **one root cause**:

```
ModuleNotFoundError: No module named 'scripts.onboarding._lib.secrets'
```

- `tests/test_hdcn_backfill.py:936` loads `scripts/onboarding/members/h-dcn/backfill-hdcn-members.py`, which imports `scripts.onboarding._lib.paths`; importing that package runs `scripts/onboarding/_lib/__init__.py:20`, which does `from .secrets import (...)` → fails.
- `tests/test_onboarding_lib_resolver.py:34` directly `importlib.import_module("scripts.onboarding._lib.secrets")` → fails.

### Root cause — `_lib/secrets.py` is git-ignored and was never committed

The module `scripts/onboarding/_lib/secrets.py` **exists in the working tree locally** (6,445 bytes, modified 2026-10-01) but is **not tracked by git**:

- `git ls-files scripts/onboarding/_lib/` lists only `__init__.py` and `paths.py` — **not** `secrets.py`.
- `git check-ignore -v scripts/onboarding/_lib/secrets.py` →
  `.gitignore:38:**/*secret*` — the broad `**/*secret*` pattern (intended for real secret files) matches the **filename** `secrets.py`, a false positive on legitimate resolver source code.
- `scripts/onboarding/_lib/__init__.py` (line 20) unconditionally re-exports from `.secrets`
  (`MissingSecretError`, `SecretsFileNotFoundError`, `credential_file`, `load_tenant_secrets`, `require`, `tenant_dir`, `tenant_secrets_path`).

Because CI checks out only tracked files, the fresh runner has `__init__.py` + `paths.py` but **no `secrets.py`**, so the package import explodes and both dependent test modules fail to collect. The author's local suite is green (the file is present on disk) — this failure is only visible in a clean checkout / CI.

**Grouped by root cause:** 2 collection errors → 1 cause (untracked `secrets.py` masked by `.gitignore` `**/*secret*`).

---

## Test Results — Frontend (2744 passed, 12 skipped, 0 failed, 0 errors, 203 files — 175.79s)

✅ **Green.** 2756 tests across 203 files, 0 failures. Count grew +22 vs 09-30 (2722 → 2744). The Members-modal `LazySelect` suites (regressed 09-28, fixed 09-29) **held green** for a fourth consecutive cycle.

---

## Lint & Static Analysis (Backend Lint job — ✅ PASS)

| Check | Result |
|-------|--------|
| Ruff Lint | ✅ Pass (0 errors) |
| Ruff Format | ✅ Pass (all files formatted) |
| Vulture | ✅ Pass (no dead code) |

The 09-30 `ruff format` regression (5 files from commit `c829580`) is **resolved** — format is clean this cycle. Backend lint/format/vulture are the CI-blocking gates and all pass. **No backend lint work is required.**

### Non-blocking report-only signals (not CI-blocking, recorded for context)

These planes are explicitly marked **REPORT-ONLY — non-blocking** in the artifacts and did **not** contribute to the red run. They are tracked here as Medium/Low hygiene, not as failures:

- **SAM ruff lint (report-only): 41 findings.** By rule: `RUF100`=7, `PIE804`=6, `SIM102`=4, `RUF022`=4, `F401`=4, `UP037`=3, `I001`=3, `B017`=3, `TRY004`=2, `PYI034`=1, `PLW1510`=1, `PIE810`=1. Majority are `[*]` auto-fixable (`I001`, `PIE804`, `UP037`, `RUF100`, `F401`, `RUF022`). Concentrated in `sam/members/domain/*`, `sam/members/migration/hdcn_backfill.py`, `sam/shared/auth_utils.py`, and `sam/tests/*`. Plus a `sam/README.md` doc-block that `ruff format` would reflow.
- **Frontend ESLint (report-only): 1,114 warnings.** Dominated by `@typescript-eslint/no-explicit-any`, `@typescript-eslint/no-unused-vars`, and `import-x/order`; heavily concentrated in `frontend/src/__mocks__/chakra-ui-react.tsx` and test files.
- **Frontend tsc (report-only): 2 type errors.**
  - `frontend/src/components/banking/__tests__/BankingFileUpload.account-scoped-dedupe-preservation.test.tsx:306:40` — `TS2872` expression is always truthy.
  - `frontend/src/components/members/MembersFieldFormBody.tsx:187:15` — `TS2322` `EnumOptionConfig[]` not assignable to `LazyOption<string>[]` (`label: LocalizedLabel` vs `string | Record<string, string>`). This one is **product code**, not a test, so it is the most worth addressing of the report-only signals.

- **Total by category**: CI-blocking = 0 lint/format errors; report-only = 41 SAM ruff + 1,114 FE ESLint + 2 FE tsc.
- **Auto-fixable vs manual (report-only SAM ruff)**: ~27 auto-fixable (`[*]`), ~14 manual (`SIM102`, `B017`, `TRY004`, `PYI034`, `PLW1510`, `PIE810`, some `RUF022`).
- **Version mismatch**: none (local 0.16.5 == CI 0.16.5).

---

## Comparison with recent runs (the 09-26 → 10-02 arc)

| Metric               | 09-26      | 09-27 | 09-28 | 09-29 | 09-30 | 10-01 | 10-02 | Trend                                      |
| -------------------- | ---------- | ----- | ----- | ----- | ----- | ----- | ----- | ------------------------------------------ |
| CI conclusion        | ❌ failure | ✅     | ❌     | ✅     | ❌     | ✅     | ❌     | Alternating red/green — **red this cycle**  |
| Backend failures     | 15 (+7 err)| 0     | 0     | 0     | 0     | 0     | 0     | ✅ Held green (7 cycles)                     |
| SAM plane            | ❌ collapse | 0     | 0     | 0     | 0     | 0     | ❌ **collect** | 🔴 **New SAM break (import, not flask)**    |
| Frontend failures    | 7          | 0     | 10    | 0     | 0     | 0     | 0     | ✅ Held green                                |
| Ruff lint errors     | 14         | 0     | 2     | 0     | 0     | 0     | 0     | ✅ Held green                                |
| Ruff format files    | 6          | 0     | 0     | 0     | 5     | 0     | 0     | ✅ 09-30 regression resolved                 |
| Vulture              | Pass       | Pass  | Pass  | Pass  | Pass  | Pass  | Pass  | — Stable                                    |
| Total backend tests  | —          | —     | 6564  | 6564  | 6622  | —     | 6645  | ↑ +23 since 09-30                           |
| Total frontend tests | 2656       | 2716  | 2716  | 2734  | 2734  | —     | 2756  | ↑ +22 since 09-30                           |

### Held / fixed (stayed green)

- ✅ Backend (7 cycles green) and frontend (Members-modal `LazySelect` stable) planes held.
- ✅ **09-30 `ruff format` regression resolved** — the 5 drifted backend files are clean again; backend lint/format/vulture all pass.
- ✅ Backend ruff lint + vulture — green.

### Regression this cycle

- 🔴 **SAM plane: 0 → collection failure.** This is a **new failure mode** for the SAM plane, distinct from the 09-26 `flask` import-coupling collapse. The cause is a **source file that git ignores and that was never committed** (`scripts/onboarding/_lib/secrets.py`, matched by `.gitignore` `**/*secret*`). The import-boundary guard that fixed 09-26 is unrelated and still holds; this is a packaging / version-control gap, not an architectural coupling issue.

### New failures introduced by the previous cycle's changes

- The 09-30 spec was a backend `ruff format` fix and a prevention task; it did **not** touch the SAM onboarding `_lib` package. The `secrets.py` module is dated 2026-10-01 (added by onboarding-tooling work on main after the 09-30 run), so the SAM break is **new debt from a separate feature commit**, not a regression from the 09-30 fix sprint. It is, however, the **same meta-pattern** as 09-30: a change landed on `main` whose breakage only surfaces on the next scheduled run.

---

## Lessons / Recurring Issues

1. **NEW ROOT-CAUSE CLASS: a required source module can be silently excluded from git by an over-broad secret-ignore pattern.** `.gitignore` line 38 `**/*secret*` is meant to keep real credentials out of the repo, but it also swallows legitimate code whose *filename* contains "secret" — here `scripts/onboarding/_lib/secrets.py` (a secrets *resolver*, not a secrets *file*). Local suites pass because the file is on disk; CI is the first clean checkout that exposes the gap. This is a different failure mode from every prior cycle (test assertion, format drift, import coupling) and the most important lesson of this run.

2. **RECURRING META-PATTERN: breakage keeps entering `main` via commits that land after the daily suite and only surface on the next scheduled run.** 09-26 (format ×6), 09-28 (lint ×2), 09-30 (format ×5), and now 10-02 (untracked module) all follow this shape. The specific gate differs each time (formatter, linter, now the collector), but the delivery vector is identical: no clean-checkout / pre-push verification caught it locally. A **clean-checkout CI-parity check before push** (e.g. verify tracked-file set imports in a fresh clone, or run `git stash -a` + collect) would have caught `secrets.py` the same way a pre-push `ruff format --check` would have caught `c829580`.

3. **Prefer renaming out of the ignore pattern over poking a hole in it.** The cleanest fix is to rename the module so its filename no longer contains "secret" (`secrets.py` → `tenant_resolver.py`): the `**/*secret*` glob stops matching, the file `git add`s normally, and there is no `.gitignore` exception to maintain. The new name also matches the repo's `*_resolver.py` convention and is more accurate (the module is a tenant-scoped resolver, not a secret). Note that `git add` on a still-ignored path is a silent no-op, so the alternative — keeping the name — would require a `.gitignore` negation (`!scripts/onboarding/_lib/secrets.py`, mirroring the existing `!**/credential_service.py`) or a one-off `git add -f`; the rename avoids both.

4. **Tracking this module does NOT weaken secret-prevention — the filename glob is the weakest of three layers, and the rename steps out of it entirely.** The file holds no credential (it is a *resolver*; real secrets stay in the fail-closed `scripts/tenants/*/*` fence, and the tenant `secrets.local.json` / `secrets.example.json` material files keep their names — only the resolver module is renamed). Secrets are kept out of GitHub by: (a) the **`ggshield` content scan** that runs first in the committed `scripts/hooks/pre-commit` hook (`.gitguardian.yaml` `exit_zero: false`) and inspects actual bytes regardless of filename; (b) the tenant fail-closed `.gitignore` fence (untouched by C1); and (c) the coarse `**/*secret*` filename glob, which cannot distinguish resolver code from a secret file. The glob was never the thing stopping real secrets — layers (a) and (b) are — so renaming out of it loses no protection.

5. **A collection error is strictly worse than an assertion failure — it zeroes the whole plane.** Because pytest interrupts on import errors, **no** SAM test ran this cycle, so we have no signal on the ~981 SAM tests that were green on 09-29. The Critical fix (C1) is a prerequisite for getting *any* SAM coverage back, not just for turning the one job green.

6. **Report-only lint is drifting upward and should not be ignored forever.** SAM ruff (41) and frontend ESLint (1,114) are non-blocking by policy, but the frontend `tsc` `TS2322` in `MembersFieldFormBody.tsx` is **product code** and a latent type bug. Report-only gates exist to avoid blocking delivery, not to make the debt invisible — see M2/L2.

7. **The 09-30 prevention task (M1, pre-push `ruff format --check`) would NOT have caught this one.** That guard checks formatting, not the tracked-file set. This cycle demonstrates the prevention needs to be broader than "run ruff before push": it must include a **clean-checkout import/collect smoke test** so an untracked-but-required file is caught (Lesson 2, task M1 here).
