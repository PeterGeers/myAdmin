# Implementation Plan

## Overview

Fix the issues that make the 2026-10-15 Full Test Suite CI run red (run #72, id `38691915907`, branch `main` @ `e600d5e2`, `schedule`, ❌ failure). **Three** jobs are red — **SAM Module-Plane** (1 collection/import error), **Frontend** (4 assertion failures in 2 Members files), and **Backend Lint & Static Analysis** (1 ruff `RUF100` + 3 ruff-format files). **Backend Full Test Suite ✅** (7200 passed, 14 skip, 0 fail).

Tasks are organized by priority: **Critical** (tests can't even collect), **High** (assertion failures + CI-blocking lint/format), **Medium** (flaky / non-deterministic), and **Low** (prevention / hygiene). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h. Verification commands assume `cd backend && source .venv/bin/activate` (backend), `cd /home/peter/projects/myAdmin` (SAM), `cd frontend` (frontend). There is **one Critical** this cycle (the SAM collection error) and **no Medium** item — the 10-13 frontend worker-OOM (E1) did not recur.

## Tasks

### Critical — collection / import errors (nothing else in the module runs until this passes)

- [x] 1. **C1. Decouple the SAM invariance test from the MySQL migration import (`ModuleNotFoundError: No module named 'mysql'`).** [M] — a SAM/DynamoDB-plane test must not transitively import `mysql.connector`.
  - **Why**: `sam/tests/test_member_data_invariance_props.py` fails at **collection**, reddening the SAM job and breaking a 5-cycle green streak. Import chain:
    - `sam/tests/test_member_data_invariance_props.py:77` → `from migrate_overrides_to_fixed_overrides import rename_overrides_key`
    - `backend/src/migrations/migrate_overrides_to_fixed_overrides.py:48` → `from database import DatabaseManager`
    - `backend/src/database.py:6` → `import mysql.connector` → **`ModuleNotFoundError`** (the SAM env does not install `mysql-connector-python`).
    The test only needs the **pure, DB-free** transform `rename_overrides_key` (its own comment at line 76 calls it exactly that), but importing it from the migration module drags in that module's **top-level** `from database import DatabaseManager`.
  - **File(s)**: `backend/src/migrations/migrate_overrides_to_fixed_overrides.py`, `backend/src/database.py` (import site, no change expected), `sam/tests/test_member_data_invariance_props.py` (import line 77), and optionally a new DB-free helper module.
  - **Action** (pick (a) — the cleaner, structural fix; (b) is the minimal fallback):
    - **(a) Extract the pure transform.** Move `rename_overrides_key` into a DB-free module (e.g. `backend/src/migrations/overrides_key_transform.py`) with **no** `database`/`mysql` import. Have `migrate_overrides_to_fixed_overrides` import it from there, and point the SAM test at the new module. The pure function then carries no MySQL dependency.
    - **(b) Make the MySQL import lazy.** In `migrate_overrides_to_fixed_overrides.py`, remove the top-level `from database import DatabaseManager` and import it **inside** the function(s) that actually use `DatabaseManager`, so importing `rename_overrides_key` never loads `mysql.connector`.
    - Keep the paired backend migration test(s) passing (Change-With-Tests Contract) — grep the test tree for `migrate_overrides_to_fixed_overrides` / `rename_overrides_key`.
    ```bash
    cd /home/peter/projects/myAdmin
    sed -n '40,60p' backend/src/migrations/migrate_overrides_to_fixed_overrides.py   # see the top-level DB import
    grep -rn "rename_overrides_key\|migrate_overrides_to_fixed_overrides" backend/tests sam/tests
    ```
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin
    PYTHONPATH=. python -m pytest sam/tests/test_member_data_invariance_props.py -q   # collects + runs (no ModuleNotFoundError)
    PYTHONPATH=. python -m pytest sam/tests -q                                        # whole SAM plane green
    # and confirm the backend migration still works:
    cd backend && source .venv/bin/activate && python -m pytest -q -k "overrides or migrate_overrides"
    ```

### High — running tests that fail + CI-blocking lint/format (CI-blocking)

- [x] 2. **H1. Fix the `membersApiService` column-preferences response-shape drift (3 failing tests, F1).** [M] — source-ahead-of-test drift; align the contract and its paired test in the same change.
  - **Why**: 3 failures in `frontend/src/services/membersApiService.test.ts` (suite *"membersApiService — column preferences (task 2.5.5)"*). The service returns a **3-key** object where the tests assert a **2-key** `{ sub, columns }` shape:
    - `getColumnPreferences > unwraps the {data} envelope and maps { sub, columns, updated_at }` → expected `…(2)`, got `{ sub, …(3) }`
    - `getColumnPreferences > defaults columns to [] when the backend omits the field entirely` → got `{ sub:'', columns:[], …(2) }` vs expected object
    - `saveColumnPreferences > PUT /members/column-preferences with a { columns } body` → expected `…(2)`, got `{ sub, …(3) }`
    Consistent with the service now surfacing an extra field (likely `updated_at`) while the tests still encode the older shape.
  - **File(s)**: `frontend/src/services/membersApiService.ts` (`getColumnPreferences` / `saveColumnPreferences`), `frontend/src/services/membersApiService.test.ts`.
  - **Action**: Read the two service methods and decide the correct contract — does the service **rightly** surface `updated_at` (then update the tests to assert the 3-key shape), or should it **strip** it (then fix the service to return `{ sub, columns }`)? Align both sides in the same change. **Do not weaken assertions** to go green; if the test name itself says "maps `{ sub, columns, updated_at }`" the intended shape may be 3-key and the mapping/the other two tests need updating to match.
    ```bash
    cd /home/peter/projects/myAdmin/frontend
    grep -n "getColumnPreferences\|saveColumnPreferences\|updated_at" src/services/membersApiService.ts
    ```
  - **Verification**:
    ```bash
    cd frontend
    npx vitest run src/services/membersApiService.test.ts 2>&1 | tail -15   # -> all column-preferences tests pass
    ```

- [x] 3. **H2. Fix the `MembersFieldFormBody` rich-enum locale-label regression (`'Standard'` vs `'Standaard'`, F2).** [S] — single-assertion locale/label resolution fix.
  - **Why**: 1 failure in `frontend/src/components/members/MembersFieldFormBody.currentValue.test.tsx` — *"shows a rich-enum value at rest even when the caller role cannot pick that option"*: expected `[ 'Standaard' ]` (nl) but got `[ 'Standard' ]` (en). The LazySelect current-value rendering resolved the **English** label where the test expects the **Dutch** localised label.
  - **File(s)**: `frontend/src/components/members/MembersFieldFormBody.tsx` (and its rich-enum / option-label resolution helper), `frontend/src/components/members/MembersFieldFormBody.currentValue.test.tsx`.
  - **Action**: Trace how the rich-enum option label is resolved for the at-rest current value. Either (a) the component should render the **localised** label (restore nl resolution) — fix the component; or (b) the fixture/expected label legitimately changed — align the test. Determine which from the label source/fixture; keep the single assertion meaningful.
    ```bash
    cd /home/peter/projects/myAdmin/frontend
    grep -rn "Standaard\|Standard\|richEnum\|LazySelect\|label" src/components/members/MembersFieldFormBody.tsx | head -30
    ```
  - **Verification**:
    ```bash
    cd frontend
    npx vitest run src/components/members/MembersFieldFormBody.currentValue.test.tsx 2>&1 | tail -12   # -> passes
    ```

- [x] 4. **H3. Clear the 1 CI-blocking ruff `RUF100` in `parameter_admin_routes.py` (unused `# noqa: BLE001`).** [S] — auto-fixable; keep the human rationale comment, drop only the dead `# noqa:` token.
  - **Why**: Backend Lint is red on a single ruff error (CI-blocking): `src/routes/parameter_admin_routes.py:73:31` — `RUF100` unused `# noqa` directive for the **non-enabled** rule `BLE001`. The line is `except Exception as exc:  # noqa: BLE001 — surface the real projection error to the caller`. Because `BLE001` (blind-except) is not enabled in `backend/ruff.toml`, the `# noqa: BLE001` suppresses nothing, so ruff flags the directive itself as dead. **Identical pattern** to the 10-13 `members_analytics_audit.py` RUF100.
  - **File(s)**: `backend/src/routes/parameter_admin_routes.py` (line 73, the `except Exception as exc:` boundary).
  - **Action**: Remove **only** the `# noqa: BLE001` token, preserving the explanatory comment. Prefer the surgical edit over a blind `ruff check --fix` (which could strip the whole directive). Result should read e.g. `except Exception as exc:  # surface the real projection error to the caller`.
    ```bash
    cd /home/peter/projects/myAdmin/backend && source .venv/bin/activate
    sed -n '71,76p' src/routes/parameter_admin_routes.py   # inspect the boundary first
    # Edit the line to drop the "# noqa: BLE001" token, keep the human comment.
    ```
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    ruff check src/routes/parameter_admin_routes.py   # -> All checks passed!
    ruff check src/                                    # -> All checks passed! (whole tree clean)
    ```

- [x] 5. **H4. Apply `ruff format` to the 3 unformatted backend files (CI-blocking).** [S] — mechanical, fully auto-applied by `ruff format`.
  - **Why**: Backend Lint is red on ruff format: **3 of 328 files would be reformatted**:
    - `src/routes/parameter_admin_routes.py:324` — collapse a multi-line `jsonify({...})` to one line (same file as H3).
    - `src/services/_projection_config_builders.py:169` — blank-line normalisation after a docstring before a nested `def`.
    - `src/services/members_config_validation.py:174, 472` — blank-line after docstring + collapse a multi-line `raise MembersConfigError({...})` (recurring format file).
  - **File(s)**: the three files above.
  - **Action**: Run `ruff format` on the three files (or the whole `src/`). Review the diff is whitespace/line-wrap only (no logic change), then commit.
    ```bash
    cd /home/peter/projects/myAdmin/backend && source .venv/bin/activate
    ruff format src/routes/parameter_admin_routes.py src/services/_projection_config_builders.py src/services/members_config_validation.py
    git --no-pager diff --stat
    ```
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    ruff format --check src/   # -> "328 files already formatted"
    ```

### Medium — flaky / non-deterministic

_None._ The 10-13 frontend vitest worker JS-heap OOM (E1) did **not** recur this run — 0 unhandled worker errors; all 3684 frontend tests collected and ran. The 10-13 `NODE_OPTIONS=--max-old-space-size=6144` headroom bump is holding (keep watching: the suite grew +24 to 3684).

### Low — prevention / hygiene

- [x] 6. **L1. Broaden the pre-push guard: `ruff check` + `ruff format --check` + a changed-path test subset (fail on non-zero).** [M] — carried forward across the arc; it would have blocked H3 **and** H4 before they landed on `main`.
  - **Why**: Nth consecutive cycle this guard would have prevented the red Backend Lint job. A pre-push `cd backend && ruff check src/ && ruff format --check src/` catches the 1 `RUF100` + 3 format findings in seconds, and a changed-path `pytest` subset (edited `sam/**`/`frontend/**` → paired tests) could have surfaced C1/F1/F2 pre-push. (requirements Lessons 3 & 4.)
  - **File(s)**: `scripts/hooks/pre-push`, `scripts/hooks/install-hooks.sh`.
  - **Action**: Ensure the hook runs `cd backend && ruff check src/ && ruff format --check src/` plus a changed-path `pytest` subset (map edited `src/**` → paired tests, e.g. `python -m backend.scripts.test_maintenance.scoped_runner --git-diff`); keep the `SKIP_PREPUSH_*` escape hatch; fail on non-zero.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin
    bash scripts/hooks/pre-push </dev/null; echo "rc=$?"
    # -> exits non-zero while H3/H4 are unfixed on the branch; 0 after they land.
    ```

- [x] 7. **L2. Add a cross-plane import guard so a SAM test can never transitively import `mysql.connector`.** [M] — durable prevention for the C1 class.
  - **Why**: C1 happened because a SAM/DynamoDB-plane test reached into a Flask/MySQL-plane migration whose import graph needs `mysql-connector`. Make that structurally impossible to re-introduce silently.
  - **File(s)**: `sam/pytest.ini` or a `sam/tests/conftest.py` import-contract check, `.github/workflows/full-test-suite.yml` (SAM job).
  - **Action**: Add a guard that fails fast when `sam/**` imports a backend MySQL-coupled module — e.g. a lightweight import-linter contract (`sam.*` must not import `backend.src.database` or anything that imports it), or a CI step asserting no `import mysql` is reachable from `sam/tests`. Keeps the planes' dependency graphs separate.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin
    # After adding the guard, intentionally re-introduce a mysql-coupled import in a sam test on a scratch branch:
    # the guard/CI step should fail fast with a clear "SAM must not import mysql.connector" message.
    grep -rn "import mysql" sam/ || echo "no direct mysql import in sam/"
    ```

- [x] 8. **L3. Confirm ruff stays pinned to 0.16.5 (reproducibility guard).** [S] — standing guard carried forward across the arc.
  - **Why**: CI ran ruff 0.16.5; the 1 `RUF100` + 3 format findings are real new debt (not a version drift). Keep local 0.16.5 == CI 0.16.5 so results stay reproducible and a silent version bump can't reintroduce a wall of findings.
  - **File(s)**: `backend/requirements-test.txt`, `.github/workflows/full-test-suite.yml`, `.github/workflows/backend-code-quality.yml`.
  - **Action / Verification**:
    ```bash
    ruff --version                                   # -> ruff 0.16.5
    grep -rn "ruff==0.16.5" backend/requirements-test.txt .github/workflows/
    ```

## Notes

### Execution order (see dependency-graph.json)

1. **C1** — decouple the pure `rename_overrides_key` transform from the MySQL import so the SAM module collects (clears the only Critical; restores the SAM job to green).
2. **H1 / H2** — fix the 4 frontend Members assertion failures (column-preferences shape + rich-enum locale label).
3. **H3 / H4** — strip the dead `# noqa: BLE001` token and run `ruff format` on the 3 files (fastest path to a green Backend Lint job).
4. **L1 / L2** — broaden the pre-push guard (ruff + changed-path tests) and add the cross-plane import-contract guard (prevention; directly target the H3/H4 and C1 classes).
5. **L3** — confirm the ruff pin (standing guard).

### Full-suite verification (re-confirm after C1 + H1–H4)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `cd /home/peter/projects/myAdmin && PYTHONPATH=. python -m pytest sam/tests -q` (expect 0 errors, 0 failures)
- Frontend: `cd frontend && npx vitest run` (expect `270 passed (270)` files, 0 assertion failures)
- Lint + Format: `cd backend && ruff check src/ && ruff format --check src/`
- Or confirm the next `full-test-suite.yml` run is green after C1 + H1–H4 land.

### Context

- CI run #72 (id `38691915907`, 2026-10-15 06:21 UTC @ `e600d5e2` on `main`, `schedule`, ❌ failure). Three red jobs: SAM Module-Plane (1 collection/import error), Frontend (4 assertion failures in 2 Members files), Backend Lint & Static Analysis (1 ruff `RUF100` + 3 ruff-format files). Backend Full Test Suite ✅ (7200 passed, 14 skip, 0 fail).
- Regression in breadth vs the clean 10-13 run: a new Critical SAM collection error, 4 new frontend assertion failures, and 3 new format findings. Backend held green; the 10-13 frontend worker-OOM (E1) did **not** recur.
- Recurring: the dead-`# noqa: BLE001` pattern (10-13 `members_analytics_audit.py` → 10-15 `parameter_admin_routes.py`); `parameter_admin_routes.py` carries both the lint and a format finding; `members_config_validation.py` is a recurring format file; the Members surface is the arc's hotspot (10-10, 10-13, 10-15) — see requirements Lessons.
