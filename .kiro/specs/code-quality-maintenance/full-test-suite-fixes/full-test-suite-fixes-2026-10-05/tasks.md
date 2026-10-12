# Full Test Suite Fixes — 2026-10-05 — Tasks

CI run #53 (id `37278831648`, 2026-10-05 @ `6301234f` on `main`, `schedule`, ❌ failure — backend tests only). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h.

> 🟢 **One job is red (Backend Full Test Suite: 2 failed).** Backend Lint ✅, SAM ✅, Frontend ✅. The two failures are **independent**: F1 is a stale `@patch` target left behind by the 10-04 `import os` lint sweep (fix in test), F2 is a numeric-coercion bug on a string confirmation code surfaced by Hypothesis (fix in the parser). Clearing both (H1, H2) turns CI green.
> Verification commands assume: `cd backend && source .venv/bin/activate`. No collection errors this cycle → **no Critical tasks**.
> ℹ️ Backend lint is fully green this cycle (39 ruff + 17 format → 0 + 0); no lint tasks. Report-only FE ESLint / FE tsc / SAM ruff are non-blocking → **Low** only.

---

## Critical — collection / import errors (nothing else runs until these pass)

_None._ No collection or import errors this cycle — both backend failures are runtime failures (tests collected and ran); SAM collects and passes.

---

## High — running tests that fail (CI-blocking)

- [x] **H1. Fix the stale `os` patch target in `test_landing_page_contact.py` left behind by the 10-04 `import os` lint sweep (F1, 1 failing test).** [S] — the test patches a symbol the production module no longer imports; a direct side-effect of 10-04 H2. Fix is in the **test**, not production.
  - **Why**: `test_no_email_configured_skips_send` decorates with `@patch("routes.landing_page_routes.os.getenv", return_value="false")` (`test_landing_page_contact.py:425`), but `backend/src/routes/landing_page_routes.py` **no longer imports `os`** (confirmed: `grep "import os|os\." src/routes/landing_page_routes.py` → no matches). The 10-04 F401 autofix removed the then-unused `import os`, so the patch target resolves to a missing attribute → `AttributeError: module 'routes.landing_page_routes' has no attribute 'os'`.
  - **File(s)**: `backend/tests/unit/test_landing_page_contact.py` (the `TestSendContactNotificationHelper` class, ~line 424-426). Confirm first how `_send_contact_notification` actually reads the "email configured" flag now (it may read a passed-in value, a config object, or `os.getenv` imported elsewhere).
  - **Action**: Do **not** re-add `import os` to production just to satisfy the patch. Instead, repoint the test at the **real seam** the handler uses:
    ```bash
    cd /home/peter/projects/myAdmin/backend && source .venv/bin/activate
    # Find how the handler reads config now (what replaced os.getenv):
    grep -n "getenv\|environ\|_send_contact_notification\|SES\|SENDER\|EMAIL" src/routes/landing_page_routes.py | head -30
    ```
    Then either (a) patch `os.getenv` at the module that still imports `os` and that the handler delegates to, (b) use the `mock_env` fixture (per backend testing standards) to set the env var the handler reads, or (c) if the handler now takes the value as a parameter/config, drive it through that. Prefer `mock_env` over an ad-hoc `@patch` where it fits.
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    pytest tests/unit/test_landing_page_contact.py -q   # -> 0 failed
    ```

- [x] **H2. Treat the Airbnb `Bevestigingscode` as an opaque string in grouping so numeric-looking codes (`0000E0`) aren't coerced (F2, 1 failing test).** [M] — Hypothesis found a deterministic, reproducible falsifying example; fix is in the **parser** (keep the raw string key), not a weakened assertion.
  - **Why**: `test_one_booking_per_code_payout_excluded` fails `AssertionError: assert {'0.0'} == {'0000E0'}`. The minimised example uses confirmation code `'0000E0'` (looks like scientific notation → `0.0`). `process_airbnb_multi` groups by `Bevestigingscode`; somewhere the key is passed through numeric coercion (a `float`/`Decimal` round-trip or dtype inference), turning `'0000E0'` into `'0.0'`, so the produced group key no longer matches the original string. This is **deterministic** (reproducible via `@reproduce_failure('6.92.1', b'AAEBAAEAAQABAAEOAQAAAAAB')`), **not** a flake — the `derandomize`/`deadline` remedy does **not** apply.
  - **File(s)**: `backend/src/str_airbnb_parser.py` (the `process_airbnb_multi` grouping path — find where `Bevestigingscode` becomes the group key); test is `backend/tests/unit/test_str_airbnb_parser_grouping_property.py` (keep its assertion as-is — the design intends codes to stay verbatim strings).
  - **Action**: Reproduce, then ensure the confirmation code is read and used as a **stripped string** end-to-end — never `float()`/`int()`/`Decimal()`'d and never fed to a numeric-inferring reader (e.g. if pandas is involved, force `dtype=str` for that column). Confirm against the design: airbnb-export-format-update Property 3 treats the code as an identifier string.
    ```bash
    cd /home/peter/projects/myAdmin/backend && source .venv/bin/activate
    grep -n "Bevestigingscode\|group\|float\|Decimal\|read_csv\|dtype" src/str_airbnb_parser.py | head -40
    # Reproduce the exact failing case before fixing:
    pytest tests/unit/test_str_airbnb_parser_grouping_property.py::TestAirbnbGroupingProperty::test_one_booking_per_code_payout_excluded -q
    ```
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    pytest tests/unit/test_str_airbnb_parser_grouping_property.py -q   # -> 0 failed (and re-run a few times; it's deterministic once pinned)
    ```

---

## Medium — carried-over property assertion (recurrence)

_None._ The 10-04 M1 (`test_duplicate_checker` continue-decision) is green this cycle; no carried-over property failures remain.

---

## Low — prevention / hygiene + report-only debt

- [x] **L1. Broaden the pre-push guard from `--collect-only` to also run `ruff check` + `ruff format --check` + a changed-path test subset.** [M] — carried forward from 10-03 L1 / 10-04 L1; **the changed-path test subset would have caught F1 (the `import os`-sweep regression) before push**.
  - **Why**: 5 consecutive red cycles entered via branch commits that only surface at the next scheduled run. This cycle's F1 is the textbook case: a `ruff --fix` removed an import and the test that patched it was never re-run. A pre-push hook that runs the tests touching the changed symbols would have blocked it. (requirements Lesson 1 & 3.)
  - **File(s)**: `scripts/hooks/pre-push`, `scripts/hooks/install-hooks.sh`.
  - **Action**: Add `cd backend && ruff check src/ && ruff format --check src/` and a changed-path `pytest` subset (map edited `src/**` files → their paired tests, e.g. via the test-maintenance scoped runner `python -m backend.scripts.test_maintenance.scoped_runner --git-diff`) to the existing hook; keep the `SKIP_PREPUSH_*` escape hatch; fail on non-zero.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin
    git stash -a >/dev/null 2>&1; bash scripts/hooks/pre-push </dev/null; echo "rc=$?"; git stash pop >/dev/null 2>&1
    # -> exits non-zero while H1/H2 are unfixed on the branch; 0 after they land.
    ```

- [x] **L2. Add a changed-symbol test-reference check so a lint autofix that removes an imported name can't silently orphan a `@patch` target.** [S] — durable prevention for the F1 class (fix-induced test regression).
  - **Why**: F1 happened because `ruff --fix` deleted `import os` from a module while a test still did `@patch("…landing_page_routes.os…")`. Nothing flagged the now-dangling patch target. (requirements Lesson 1.)
  - **File(s)**: the test-maintenance drift detector (`backend/scripts/test_maintenance/` — the drift detector already finds source↔test signature/key mismatches); extend it to flag `@patch("<module>.<name>")` targets where `<name>` is no longer importable from `<module>`.
  - **Action**: Add a check that resolves each `@patch(...)`/`patch.object(...)` target string against the current module and reports any that no longer exist. Wire it into the scanner so it shows up in the maintenance session list.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin
    python -m backend.scripts.test_maintenance.scanner --maintenance-session 2>&1 | grep -i "patch\|target\|drift" | head
    # -> flags the stale landing_page_routes.os patch (until H1 fixes it)
    ```

- [x] **L3. (Report-only, non-blocking) Sweep the cheap report-only lint debt before it becomes a cliff.** [M] — none of this blocks CI today; clear the mechanical bulk so the report-only planes stay readable.
  - **Why**: Report-only signals are drifting up unnoticed (requirements Lesson 4): SAM ruff **329** (291 × F401), FE ESLint **1117** (6 errors + 1111 warnings; 1 err + 196 warn auto-fixable), FE tsc **8** type errors. The F401 bulk and the FE 6 errors are quick wins.
  - **File(s) / Action** (do these as independent, low-risk sweeps — not required for green CI):
    - **SAM F401 (291)**: `cd sam && ruff check . --fix` (then re-run `sam/pytest.ini` suite to confirm no import was load-bearing). Then triage the residual 38 (I001/RUF022/SIM102/UP037/RUF100/B017/TRY004/PYI034/PLW1510/PIE810/PIE804).
    - **FE ESLint 6 errors** (manual, surgical): `MembersTypedField.tsx:424` `prefer-const` (`let base` → `const base`); `BankingFileUpload.account-scoped-dedupe-preservation.test.tsx:306` `no-constant-binary-expression` (fix the constant-truthy LHS of `||`); `zzp/ContactModal.tsx:69` + `pages/public/blocks/ContactBlock.tsx:79` `no-useless-escape` (remove the needless `\-` escapes in the regex char classes). Then `cd frontend && npx eslint --fix` for the 196 auto-fixable warnings.
    - **FE tsc 8 errors** (manual): `AppRoutes.tsx:90` (`mode` prop not on `UserMenuProps` — add to props or drop it); `useBankingPatterns.test.ts:134` / `useBankingUpload.test.ts:198` (type the mocked setter so `.mockClear`/`.mock` exist); `routePresetService.test.ts:53/62` + `vehicleService.test.ts:75` (`label` not in `Partial<RoutePreset>`/`Partial<Vehicle>` — fix the test object or the type); `BankingFileUpload…dedupe-preservation.test.tsx:306` always-truthy (same site as the ESLint error).
  - **Verification**:
    ```bash
    cd sam && ruff check . 2>&1 | tail -3           # SAM F401 bulk cleared
    cd frontend && npx eslint . 2>&1 | tail -3      # FE error count down (0 errors ideal)
    cd frontend && npx tsc --noEmit 2>&1 | tail -5  # FE tsc errors reduced
    ```

- [x] **L4. Confirm ruff stays pinned to 0.16.5 (reproducibility guard).** [S] — standing guard carried forward from 10-03 L3 / 10-04 L4; no change expected.
  - **Why**: Lint is green this cycle; keep local 0.16.5 == CI 0.16.5 so results stay reproducible and a silent version bump can't reintroduce a wall of findings.
  - **File(s)**: `backend/requirements-test.txt`, `.github/workflows/full-test-suite.yml`, `.github/workflows/backend-code-quality.yml`.
  - **Action / Verification**:
    ```bash
    ruff --version                                   # -> ruff 0.16.5
    grep -rn "ruff==0.16.5" backend/requirements-test.txt .github/workflows/
    ```

---

## Execution order (see dependency-graph.json)

1. **H1** — repoint the stale `os` patch in `test_landing_page_contact.py` to the real config seam. (fastest; clears F1)
2. **H2** — keep `Bevestigingscode` an opaque string in `str_airbnb_parser` grouping. (clears F2; independent of H1 — can run in parallel)
3. **L1 / L2** — broaden the pre-push guard (changed-path tests) and add the stale-`@patch`-target drift check. (prevention; directly target the F1 class)
4. **L3 / L4** — sweep the report-only lint debt (SAM F401, FE ESLint/tsc) and confirm the ruff pin. (hygiene; non-blocking)

## Full-suite verification (re-confirm after H1–H2)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `cd /home/peter/projects/myAdmin && PYTHONPATH=. python -m pytest sam/tests -q`
- Frontend: `cd frontend && npx vitest run`
- Lint + Format: `cd backend && ruff check src/ && ruff format --check src/`  (already green)
- Or confirm the next `full-test-suite.yml` run is green after H1–H2 land.
