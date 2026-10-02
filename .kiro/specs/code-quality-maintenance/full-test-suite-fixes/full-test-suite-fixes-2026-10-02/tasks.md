# Full Test Suite Fixes — 2026-10-02 — Tasks

CI run #36978727343 (2026-10-02, ❌ failure — SAM collection error). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h.

> 🔴 **One job is red: SAM module-plane → collection interrupted (2 import errors, 1 root cause).** Backend (6633 passed), frontend (2744 passed), and backend lint/format/vulture are all green. The single Critical task (C1) restores SAM collection and turns CI green; everything else is non-blocking hygiene or prevention.
> Verification commands assume: `cd backend && source .venv/bin/activate` (backend/lint), `pytest sam/tests` from repo root (SAM), and `cd frontend` (frontend).

---

## Critical — collection / import errors (nothing else runs until these pass)

- [x] **C1. Rename `scripts/onboarding/_lib/secrets.py` → `tenant_resolver.py` so a clean checkout (CI) can import `scripts.onboarding._lib`.** [S] — rename + import updates, no logic change. ✅ Done 2026-10-02: file moved (now not git-ignored), 4 code refs + 2 doc comments updated, stdlib `import secrets` left untouched; both former-failing modules collect (193 + 23 tests, 0 errors) and `pytest sam/tests` exits RC=0.
  - **Why**: The sole cause of the red run. `scripts/onboarding/_lib/__init__.py:20` does `from .secrets import (...)`; CI checks out only tracked files, and `secrets.py` is **untracked** because `.gitignore`'s broad `**/*secret*` rule matches its filename (`git check-ignore -v` confirms; `git ls-files` lists only `__init__.py` + `paths.py`). So the package import raises `ModuleNotFoundError: No module named 'scripts.onboarding._lib.secrets'`, interrupting collection of `tests/test_hdcn_backfill.py` and `tests/test_onboarding_lib_resolver.py` before any SAM test runs.

  - **Why rename instead of a `.gitignore` negation**: Renaming so the filename no longer contains "secret" removes the `**/*secret*` match at the source — no exception to add, no glob hole to maintain, and the file then `git add`s normally. `tenant_resolver.py` is also the more accurate name: every public function is tenant-scoped (`tenant_secrets_path(tenant)`, `tenant_dir(tenant)`, `load_tenant_secrets(tenant)`, `credential_file(..., tenant)`), and it matches the repo's established `*_resolver.py` convention (`entitlement_resolver`, `admin_pool_resolver`, `storage_resolver`, `logo_resolver`, `field_resolver`). The module carries **no** credential — it is pure resolver logic; real secrets stay in the fail-closed `scripts/tenants/*/*` fence, untouched. (If a rename is ever undesirable, the fallback is a narrow negation `!scripts/onboarding/_lib/<file>` mirroring the existing `!**/credential_service.py` precedent — but the rename is cleaner and preferred.)

  - **Secret-prevention is unaffected either way** — the filename glob is the weakest of three layers and the only one involved: (1) **`ggshield` content scan** runs first in the committed `scripts/hooks/pre-commit` hook (`.gitguardian.yaml` `exit_zero: false`) and inspects actual bytes regardless of filename; (2) the **tenant fail-closed `.gitignore` fence** keeps real `secrets.local.json` + co-located credential files ignored; (3) the coarse `**/*secret*` **filename glob**, which is what we are stepping out of. After the rename, (1) and (2) still fully apply.

  - **File(s) to change** (4 code refs + 2 doc comments; the stdlib `import secrets` in `scripts/onboarding/members/_generic/load-cognito-users.py` is the Python standard library and MUST NOT be touched):
    - `scripts/onboarding/_lib/secrets.py` → **rename to** `scripts/onboarding/_lib/tenant_resolver.py` (plain filesystem move — the file is currently untracked, so there is nothing to `git mv`).
    - `scripts/onboarding/_lib/__init__.py` — change `from .secrets import (...)` (line ~20) to `from .tenant_resolver import (...)`; update the docstring reference `:mod:\`_lib.secrets\`` → `:mod:\`_lib.tenant_resolver\``.
    - `scripts/onboarding/members/h-dcn/backfill-hdcn-members.py` (line ~142) — `from scripts.onboarding._lib.secrets import (...)` → `from scripts.onboarding._lib.tenant_resolver import (...)`.
    - `sam/tests/test_onboarding_lib_resolver.py` (line ~34) — `importlib.import_module("scripts.onboarding._lib.secrets")` → `"scripts.onboarding._lib.tenant_resolver"`; update the nearby `` ``secrets.py`` uses ... `` comment to the new name.
    - `scripts/tenants/README.md` and `scripts/tenants/h-dcn/secrets.example.json` — update the prose/`//scope` pointers that reference `scripts/onboarding/_lib/secrets.py` to `.../tenant_resolver.py` (comments only; the tenant files `secrets.local.json` / `secrets.example.json` keep their names — those are the actual secret-material files the fence protects, unrelated to the resolver module name).

  - **Action**:
    ```bash
    cd /home/peter/projects/myAdmin
    # 1) move the (untracked) module to the glob-safe name
    mv scripts/onboarding/_lib/secrets.py scripts/onboarding/_lib/tenant_resolver.py
    # 2) update the 4 code references + 2 doc comments listed above (from .secrets -> from .tenant_resolver, etc.)
    # 3) stage + verify the new name is tracked (no -f, no .gitignore edit needed):
    git check-ignore -v scripts/onboarding/_lib/tenant_resolver.py   # -> expect NO output (not ignored)
    git add scripts/onboarding/_lib/tenant_resolver.py scripts/onboarding/_lib/__init__.py \
            scripts/onboarding/members/h-dcn/backfill-hdcn-members.py \
            sam/tests/test_onboarding_lib_resolver.py \
            scripts/tenants/README.md scripts/tenants/h-dcn/secrets.example.json
    git ls-files scripts/onboarding/_lib/                            # -> must now list tenant_resolver.py
    # 4) confirm the content scanner still passes on the file being added:
    ggshield secret scan path scripts/onboarding/_lib/tenant_resolver.py   # -> No secrets found
    # 5) confirm no stale references to the old module remain:
    grep -rn "_lib\.secrets\|_lib/secrets\|from \.secrets" scripts/ sam/ --include="*.py" --include="*.md" --include="*.json"
    #    -> no matches (the stdlib `import secrets` line is NOT matched by these patterns)
    ```
  - **Verification**:
    ```bash
    # reproduce CI's clean-checkout view: the package + both test modules must collect.
    cd /home/peter/projects/myAdmin
    python -c "import importlib; importlib.import_module('scripts.onboarding._lib.tenant_resolver'); print('tenant_resolver OK')"
    PYTHONPATH=. python -m pytest sam/tests/test_onboarding_lib_resolver.py sam/tests/test_hdcn_backfill.py --collect-only -q
    # -> both collect, 0 errors. Then run the SAM plane:
    PYTHONPATH=. python -m pytest sam/tests -q    # -> ~981 tests, 0 errors
    ```
  - **Belt-and-suspenders (confirm nothing else in `_lib` is also untracked)**:
    ```bash
    git status --ignored scripts/onboarding/_lib/   # -> no other required .py under "Ignored files"
    ```

---

## High — running tests that fail + CI-blocking lint

_None._ No test ran-and-failed this cycle, and all CI-blocking lint (backend ruff lint, ruff format, vulture) is green. The only red is the C1 collection error above.

---

## Medium — recurrence prevention + report-only product-code type error

- [x] **M1. Add a clean-checkout import/collect smoke check before push so an untracked-but-required module is caught locally.** [M] — prevention; the 09-30 `ruff format --check` guard would NOT have caught this (requirements Lesson 6). ✅ Done 2026-10-02: added `scripts/hooks/pre-push` (stashes untracked+ignored to mimic a clean checkout, runs `pytest sam/tests --collect-only`, always restores via trap, `SKIP_PREPUSH_COLLECT=1` escape hatch) and wired it into `scripts/hooks/install-hooks.sh`; installed as symlink. Validated both ways against a clean clone / staged-index snapshot: pre-C1 collect fails exit 2 with the exact `ModuleNotFoundError: ...secrets` (guard catches it); C1-staged collect exits 0 (193 + 23 tests).
  - **File(s)**: `scripts/hooks/pre-push` (new), `scripts/hooks/install-hooks.sh` (installs pre-commit + pre-push).
  - **Why**: Four of the last cycles (09-26, 09-28, 09-30, 10-02) broke via a change that landed on `main` and only surfaced on the next scheduled run. The 10-02 break specifically is invisible to a formatter/linter gate because the file is present locally — only a **clean-checkout import/collect** exposes it. A pre-push step that collects the SAM plane against the tracked file set (e.g. `git stash -a` then `pytest --collect-only`, or a throwaway `git archive | tar -x` into a temp dir) blocks this class before CI.
  - **Action**: Wire a pre-push (or CI pre-flight) step that runs `pytest sam/tests --collect-only -q` against a clean/tracked view and fails on any collection error. Keep it fast (collect-only).
  - **Verification**:
    ```bash
    # with secrets.py still untracked, the check must fail:
    git stash -a && PYTHONPATH=. python -m pytest sam/tests --collect-only -q ; git stash pop
    # after C1 lands, the same clean-view collect exits 0.
    ```

- [x] **M2. Fix the frontend `tsc` `TS2322` type error in product code (`MembersFieldFormBody.tsx`).** [M] — report-only gate, but this is a latent product-code type bug (not a test). ✅ Done 2026-10-02: replaced the unsafe `rich as LazyOption[]` cast with `rich.map(enumOptionToLazyOption)`; added `enumOptionToLazyOption` + `normalizeLocalizedLabel` helpers to `fieldForm.ts` that map `EnumOptionConfig`→`LazyOption` (narrow `LocalizedLabel`'s `string|undefined` values to `Record<string,string>`, `roles: string[]|null`→`undefined`). Verified clean: IDE diagnostics 0 errors on all 3 files; a fresh `tsc --noEmit` (after clearing a stale `tsconfig.tsbuildinfo` that had been masking the fix) produced an empty log = no type errors. NOTE: an incremental `.tsbuildinfo` cache made earlier CLI runs report the stale error; delete it for a true check.
  - **File(s)**: `frontend/src/components/members/MembersFieldFormBody.tsx` (map instead of cast), `frontend/src/components/members/fieldForm.ts` (new `enumOptionToLazyOption` + `normalizeLocalizedLabel`, imports `LazyOption`).
  - **Why**: `EnumOptionConfig[]` is passed where `LazyOption<string>[]` is expected; `label: LocalizedLabel` is wider than `string | Record<string, string>`. tsc is report-only (non-blocking), so it did not redden CI, but this is real product code and a type-safety hole — the most worth-fixing of the report-only signals.
  - **Action**: Reconcile the two label types — either narrow/normalize `LocalizedLabel` to `string | Record<string, string>` at the boundary, or widen `LazyOption.label`, or map `EnumOptionConfig[] → LazyOption<string>[]` explicitly before passing. Pick the option consistent with how `LazySelect` consumes `label` elsewhere.
  - **Verification**:
    ```bash
    cd frontend && npx tsc --noEmit    # -> the MembersFieldFormBody TS2322 is gone
    ```

---

## Low — hygiene / prevention (report-only, non-blocking)

- [x] **L1. Clear the auto-fixable SAM ruff findings (report-only).** [S] — mechanical, no behaviour change. ✅ Done 2026-10-02: `ruff check --fix .` cleared **23** findings (45 → 22); `ruff format README.md` reflowed the doc code-blocks (now passes `--check`). Affected files' tests re-run green (`pytest sam/tests/test_hdcn_backfill.py` + the 3 mapping tests + `test_onboarding_lib_resolver.py` → rc 0). The **22 remaining are manual-judgment findings left in place** (not blanket-noqa'd), for a deliberate follow-up: `DTZ011`×4 (date.today w/o tz), `SIM102`×4 (collapsible-if), `B017`×3 (assert blind Exception — tests), `RUF022`×3 (unsorted `__all__` — `[-]` needs `--fix`/review), `BLE001`×2 (blind except), `TRY004`×2 (ValueError→TypeError), `PIE810`×1, `PYI034`×1 (return `Self`), `PLW1510`×1 (`subprocess.run` check=), `PIE804`×1. All report-only / non-blocking.
  - **File(s)**: `sam/README.md`, `sam/members/migration/hdcn_backfill.py`, `sam/tests/test_hdcn_backfill.py`, `sam/tests/test_members_mapping_loader_orphan_guard.py`, `sam/tests/test_members_modal_mapping_mismatch_explore.py`, `sam/tests/test_members_modal_mapping_preservation.py` (the files `--fix`/format actually touched).
  - **Why**: 41 report-only ruff findings; ~27 are `[*]` auto-fixable (`I001`, `PIE804`, `UP037`, `RUF100`, `F401`, some `RUF022`). Clearing the auto-fixable set shrinks the drift so the ~14 manual ones (`SIM102`, `B017`, `TRY004`, `PYI034`, `PLW1510`, `PIE810`) stand out for a deliberate follow-up. Non-blocking, so do after C1.
  - **Action**:
    ```bash
    cd sam && ruff check --fix . && ruff format README.md
    # then review the manual (non-[*]) findings individually; do NOT blanket-noqa.
    ```
  - **Verification**:
    ```bash
    cd sam && ruff check . 2>&1 | tail -5    # -> only the intended manual findings remain
    ```

- [x] **L2. Confirm ruff stays pinned to 0.16.5 (reproducibility guard).** [S] — standing guard, no change expected. ✅ Done 2026-10-02: pin is consistent at **0.16.5** across all copies — installed `ruff 0.16.5`; canonical `backend/requirements-test.txt:11` `ruff==0.16.5`; CI `backend-code-quality.yml:36`, `full-test-suite.yml:47` (backend lint) and `full-test-suite.yml:257` (SAM report-only lint) all `ruff==0.16.5`; pre-commit hook docs reference 0.16.5. No floating/mismatched version found. No change required.
  - **File(s)**: `backend/requirements-test.txt` (canonical pin), `.github/workflows/full-test-suite.yml`, `.github/workflows/backend-code-quality.yml`.
  - **Why**: Backend lint/format/vulture reproduced cleanly this cycle because local ruff (0.16.5) matches CI (0.16.5). Keep the pin so counts stay trustworthy. Carried forward from 09-30 L1.
  - **Action**: Verify the `ruff==0.16.5` pin is unchanged in all copies.
  - **Verification**:
    ```bash
    ruff --version                                   # -> ruff 0.16.5
    grep -rn "ruff==0.16.5" backend/requirements-test.txt .github/workflows/
    ```

---

## Execution order (see dependency-graph.json)

1. **C1** — rename `secrets.py` → `tenant_resolver.py` (+ update 4 code refs/2 docs) → SAM collects → turns CI green. (do first; everything SAM depends on it)
2. **M1** — add the clean-checkout import/collect pre-push smoke check. (recommended after C1: land the fix, then prevent the recurrence it exposed)
3. **M2** — fix the `MembersFieldFormBody.tsx` `TS2322` product-code type error. (independent)
4. **L1 / L2** — SAM ruff auto-fix and the ruff-pin check. (any time, after C1)

## Full-suite verification (re-confirm after C1)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `cd /home/peter/projects/myAdmin && PYTHONPATH=. python -m pytest sam/tests -q`
- Frontend: `cd frontend && npx vitest run`
- Lint + Format: `cd backend && ruff check src/ && ruff format --check src/`
- Or confirm the next `full-test-suite.yml` run is green after C1 lands.
