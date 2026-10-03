# Full Test Suite Fixes — 2026-10-03 — Tasks

CI run #37104991318 (2026-10-03 @ `c8eb675`, ❌ failure — backend tests + backend lint, one root cause). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h.

> 🔴 **Two jobs are red (Backend Full Test Suite, Backend Lint & Static Analysis) with ONE root cause**: the `backend/src/database.py` connection/cursor refactor (`get_connection` → `_get_connection`; cursor CM now yields `(cursor, conn)`). SAM ✅ (10-02 fix held) and Frontend ✅. The High tasks (H1 test mocks, H2 ruff lint) turn CI green; everything else is minor/hygiene.
> Verification commands assume: `cd backend && source .venv/bin/activate` (backend/lint). No collection errors this cycle, so there are **no Critical tasks**.

---

## Critical — collection / import errors (nothing else runs until these pass)

_None._ No collection or import errors this cycle — all 46 backend failures are runtime failures (tests collected and ran). SAM collection is restored (10-02 C1 held).

---

## High — running tests that fail + CI-blocking lint

- [x] **H1. Update backend test mocks to the new `database.py` cursor/connection contract (46 failing tests).** [L] — the primary cause of the red backend job; fix is in test mocks, not production.
  - **Why**: `backend/src/database.py` was refactored — `get_connection` → private `_get_connection` (line 196), and the cursor context manager now yields a 2-tuple `(cursor, conn)` (`yield cursor, conn` at lines 249/270/326; consumed as `with self.get_cursor(...) as (cursor, conn):`). 46 unit tests still encode the old contract and fail at runtime. Production + SAM run fine on the new contract — only the tests are stale.
  - **Failures grouped by signature** (fix the shared mock once, then the stragglers):
    - **19 × `TypeError: 'Mock' object does not support the context manager protocol`** — `test_zzp_invoice_service.py`, `test_zzp_edge_cases.py`. The mock must implement `__enter__`/`__exit__` (use `MagicMock` or a context-manager helper) and `__enter__` must return `(cursor, conn)`.
    - **13 × `ValueError: not enough values to unpack (expected 2, got 0)`** — `test_preservation_account_scoped_save.py`, `test_preservation_closed_period.py`, `test_closure_aware_bug_condition.py`. The mock CM's `__enter__` must return a 2-tuple `(cursor_mock, conn_mock)`, not nothing.
    - **11 × `AttributeError: <DatabaseManager> does not have the attribute 'get_connection'`** — `test_banking_balance_closure.py`, `test_duplicate_performance.py`. Repoint `patch.object(db, "get_connection", ...)` → `"_get_connection"` (or patch `get_cursor`).
    - **2 × `AssertionError: Regex pattern did not match.`** — `test_zzp_edge_cases.py::test_generate_invoice_number_rollback_on_error`, `test_zzp_invoice_service.py::test_generate_invoice_number_rollback_on_error`. Update the `pytest.raises(..., match=...)` pattern to the message/type the refactored transaction path now raises.
    - **1 × `AssertionError: Decision handling should succeed for continue`** — `test_duplicate_checker.py::TestDuplicateCheckerProperties::test_property_user_decision_processing_consistency`. Property-based; confirm the `continue` decision path still returns success under the new DB flow (may be a real behaviour change to assert against, not just a mock).
  - **File(s) to change** (all under `backend/tests/unit/`): `test_zzp_invoice_service.py`, `test_zzp_edge_cases.py`, `test_preservation_account_scoped_save.py`, `test_preservation_closed_period.py`, `test_closure_aware_bug_condition.py`, `test_banking_balance_closure.py`, `test_duplicate_performance.py`, `test_duplicate_checker.py`. **Prefer a shared fixture/helper** (e.g. a `mock_cursor_cm` that yields `(cursor, conn)` via `MagicMock`) so the 43 context-manager/unpack/attribute cases are fixed in one place.
  - **Action**: Locate the common cursor/connection mock pattern (grep below), replace plain `Mock()` CMs with a `MagicMock` whose `__enter__` returns `(cursor, conn)`, repoint `get_connection` patches to `_get_connection`, then handle the 2 regex + 1 property cases individually. Do **not** change `database.py`.
    ```bash
    cd /home/peter/projects/myAdmin/backend
    grep -rn "get_connection\|get_cursor\|__enter__\|context manager" tests/unit/test_zzp_invoice_service.py tests/unit/test_preservation_closed_period.py tests/unit/test_banking_balance_closure.py | head -40
    ```
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    pytest tests/unit/test_zzp_invoice_service.py tests/unit/test_zzp_edge_cases.py \
           tests/unit/test_preservation_account_scoped_save.py tests/unit/test_preservation_closed_period.py \
           tests/unit/test_closure_aware_bug_condition.py tests/unit/test_banking_balance_closure.py \
           tests/unit/test_duplicate_performance.py tests/unit/test_duplicate_checker.py -q
    # -> 46 previously-failing tests pass, 0 failed. Then full backend: pytest -q
    ```

- [x] **H2. Clear the 40 `RUF059` "unpacked variable `conn` is never used" backend lint errors.** [M] — CI-blocking (Backend Lint job red); same refactor as H1. **Not** safely auto-fixable (ruff reports 40 *hidden/unsafe* fixes only).
  - **Why**: The production side of the `database.py` refactor — 40 call sites do `with get_cursor() as (cursor, conn):` but never use `conn`. `RUF059` flags each. Blocking the Backend Lint job.
  - **File(s)** (24 files, with per-file counts): `src/bnb_routes.py` (8), `src/routes/str_routes.py` (5), `src/services/signup_service.py` (4), `src/str_channel_routes.py` (3), `src/hybrid_pricing_optimizer.py` (3), `src/banking_checks.py` (2), `src/services/banking_mutatie_service.py` (2), `src/services/tenant_language_service.py` (2), `src/services/year_end_service.py` (2), `src/str_invoice_routes.py` (2), and 1 each in: `src/banking_processor.py`, `src/report_generators/financial_report_generator.py`, `src/routes/aangifte_ib_routes.py`, `src/routes/banking_routes.py`, `src/services/country_report_service.py`, `src/services/zzp_invoice_numbering.py`, `src/xlsx_export.py`. (Full line list in the CI `ruff-lint.md` artifact / dependency-graph notes.)
  - **Action**: For each site, decide whether the connection is genuinely unused:
    - If unused → rename the binding to `_conn` / `_` (`with get_cursor() as (cursor, _conn):`) to silence `RUF059` while documenting intent.
    - If it *should* be used (e.g. a missing `conn.commit()`) → that is a latent bug; use it. Review each; do **not** run `ruff check --fix --unsafe-fixes` blindly (Lesson 6 — unsafe fixes can mask a forgotten `conn` use).
    - Strategically, consider adding a cursor-only context manager so sites that never need `conn` stop unpacking it (prevents `RUF059` recurrence — see H3-adjacent Lesson 3).
  - **Verification**:
    ```bash
    cd backend && ruff check src/ 2>&1 | tail -5     # -> 0 errors (no RUF059)
    ```

- [x] **H3. Reformat `src/str_invoice_routes.py` (1 ruff-format violation).** [S] — CI-blocking (Ruff format check red); auto-fixable.
  - **Why**: `src/str_invoice_routes.py:63` has a `logger.info(f"...")` manually split over 3 lines that fits on one; `ruff format` collapses it. "1 file would be reformatted, 308 already formatted."
  - **File(s)**: `backend/src/str_invoice_routes.py`.
  - **Action**:
    ```bash
    cd backend && ruff format src/str_invoice_routes.py
    ```
  - **Verification**:
    ```bash
    cd backend && ruff format --check src/     # -> "309 files already formatted"
    ```

---

## Medium — report-only product-code type error (recurrence)

- [x] **M1. Re-fix the frontend `tsc` `TS2322` type error in `MembersFieldFormBody.tsx` — it regressed since 10-02.** [M] — report-only (non-blocking), but it was marked fixed on 10-02 and is back.
  - **Why**: `frontend/src/components/members/MembersFieldFormBody.tsx:188:15` — `EnumOptionConfig[]` passed where `LazyOption<string>[]` is expected; `label: LocalizedLabel` is wider than `string | Record<string, string>`. The 10-02 M2 fix (map via `enumOptionToLazyOption` + `normalizeLocalizedLabel` in `fieldForm.ts`) either was reverted, incompletely landed, or masked by a stale `.tsbuildinfo` (the 10-02 note itself flagged that cache). tsc is report-only so nothing enforced it.
  - **File(s)**: `frontend/src/components/members/MembersFieldFormBody.tsx`, `frontend/src/components/members/fieldForm.ts`.
  - **Action**: Re-apply the explicit `EnumOptionConfig[] → LazyOption<string>[]` mapping at the boundary (don't cast). Then delete any stale incremental cache before re-checking so the result is real.
    ```bash
    cd frontend && rm -f tsconfig.tsbuildinfo && npx tsc --noEmit 2>&1 | grep MembersFieldFormBody
    ```
  - **Verification**:
    ```bash
    cd frontend && rm -f tsconfig.tsbuildinfo && npx tsc --noEmit    # -> no MembersFieldFormBody TS2322
    ```
  - **Follow-up (prevent re-regression)**: either promote tsc to a blocking gate for product (non-test) files, or add a type-level regression test, so a "fixed" report-only item cannot silently drift back (Lesson 5).

---

## Low — prevention / hygiene (report-only, non-blocking)

- [x] **L1. Broaden the 10-02 pre-push guard from collect-only to also run affected tests + ruff.** [M] — prevention; this cycle's regression (runtime test + lint) is invisible to a `--collect-only` guard.
  - **Why**: The 10-02 M1 pre-push hook runs `pytest sam/tests --collect-only` — it catches import/collection breaks but **not** runtime test failures or `RUF059`/format lint. 4+ consecutive cycles broke via post-suite commits (Lesson 4). A pre-push that also runs `ruff check src/ && ruff format --check src/` and the changed-file test subset would have caught both symptoms of this cycle's DB refactor before push.
  - **File(s)**: `scripts/hooks/pre-push` (extend), `scripts/hooks/install-hooks.sh`.
  - **Action**: Add `ruff check src/` + `ruff format --check src/` (backend) and a changed-path `pytest` subset to the existing pre-push hook; keep the `SKIP_PREPUSH_*` escape hatch. Fail on non-zero.
  - **Verification**:
    ```bash
    cd /home/peter/projects/myAdmin
    git stash -a >/dev/null 2>&1; bash scripts/hooks/pre-push </dev/null; echo "rc=$?"; git stash pop >/dev/null 2>&1
    # -> with H1/H2/H3 unfixed the hook exits non-zero; after fixes it exits 0.
    ```

- [x] **L2. Adopt a cursor-only context manager / `_conn` convention to stop `RUF059` recurring (3rd appearance: 08-12, 08-18, 10-03).** [M] — durable prevention for the recurring rule.
  - **Why**: `RUF059` on unpacked-unused `conn` has recurred across cycles whenever the `(cursor, conn)` idiom spreads to sites that don't need the connection (Lesson 3). A `get_cursor_only()` helper (or a documented `as (cursor, _conn):` convention) removes the unpack at sites that never touch `conn`, so the rule can't fire there again.
  - **File(s)**: `backend/src/database.py` (add/document a cursor-only helper), plus the H2 call sites adopting it where `conn` is unused.
  - **Action**: Add a thin `get_cursor_only()` (yields just `cursor`) alongside `get_cursor()`, or codify the `_conn`/`_` convention in the DB-abstraction docs/steering; migrate the H2 unused-`conn` sites to it opportunistically.
  - **Verification**:
    ```bash
    cd backend && ruff check src/ 2>&1 | tail -3     # -> stays 0 RUF059; new sites don't reintroduce it
    ```

- [x] **L3. Confirm ruff stays pinned to 0.16.5 (reproducibility guard).** [S] — standing guard, no change expected. Carried forward from 10-02 L2.
  - **Why**: Backend lint reproduces cleanly only if local ruff (0.16.5) matches CI (0.16.5). The 40 `RUF059` are real code issues, not a version artifact — keep the pin so counts stay trustworthy.
  - **File(s)**: `backend/requirements-test.txt` (canonical pin), `.github/workflows/full-test-suite.yml`, `.github/workflows/backend-code-quality.yml`.
  - **Action / Verification**:
    ```bash
    ruff --version                                   # -> ruff 0.16.5
    grep -rn "ruff==0.16.5" backend/requirements-test.txt .github/workflows/
    ```

---

## Execution order (see dependency-graph.json)

1. **H1** — update backend test mocks to the `(cursor, conn)` / `_get_connection` contract → backend test job green. (largest effort; the primary red)
2. **H2** — clear the 40 `RUF059` production call sites → backend lint job (lint) green.
3. **H3** — `ruff format src/str_invoice_routes.py` → backend lint job (format) green. (trivial; can land with H2)
4. **M1** — re-fix the `MembersFieldFormBody.tsx` `TS2322` (report-only regression).
5. **L1 / L2 / L3** — broaden pre-push guard, adopt cursor-only convention, confirm ruff pin. (prevention; after the greens)

## Full-suite verification (re-confirm after H1–H3)

- Backend: `cd backend && source .venv/bin/activate && pytest -q`
- SAM: `cd /home/peter/projects/myAdmin && PYTHONPATH=. python -m pytest sam/tests -q`
- Frontend: `cd frontend && npx vitest run`
- Lint + Format: `cd backend && ruff check src/ && ruff format --check src/`
- Or confirm the next `full-test-suite.yml` run is green after H1–H3 land.
