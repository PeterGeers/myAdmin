# Full Test Suite Fixes — 2026-10-03

## Summary

Full Test Suite run (GitHub Actions run #37104991318) on `main` @ `c8eb675`, 2026-10-03 07:01 UTC. **CI conclusion: ❌ failure.** Analysis is CI-artifact-based only (no local scans), from the downloaded `backend-test-reports`, `sam-test-reports`, `frontend-test-reports`, and `backend-lint-reports` artifacts.

| Category                     | Count                                   | Δ vs 2026-10-02                               |
| ---------------------------- | --------------------------------------- | --------------------------------------------- |
| Backend test failures        | **46** (of 6684; 6626 passed, 12 skip)  | 🔴 **regression** 0 → 46                        |
| SAM module-plane tests       | ✅ pass (collection restored)            | ✅ fixed — 10-02 collection error resolved      |
| Frontend test failures       | 0 (of 2756; 2744 passed, 12 skip)       | — stable green                                 |
| Ruff lint errors (backend)   | **40** (`RUF059` ×40)                    | 🔴 **regression** 0 → 40                        |
| Ruff format violations (be)  | **1 file** (`str_invoice_routes.py`)     | 🔴 **regression** 0 → 1                          |
| Vulture (dead code)          | ✅ Pass                                  | — stable green                                 |

**CI job result**: **Backend Full Test Suite ❌ (46 failed)** · SAM Module-Plane ✅ · Frontend ✅ · **Backend Lint & Static Analysis ❌ (ruff lint + ruff format)**. **Two jobs are red** — backend tests and backend lint — and they share **one underlying cause**: a refactor of the database connection/cursor abstraction in `backend/src/database.py`.

> 🔴 **This is a single-root-cause regression with two symptoms.** The DB layer now exposes `_get_connection` (renamed from `get_connection`) and its cursor context manager yields a **2-tuple `(cursor, conn)`**. (1) 46 backend tests still mock the old shape and fail at runtime; (2) 40 production call sites unpack `conn` from `(cursor, conn)` but never use it, which `RUF059` flags. The 10-02 SAM `secrets.py` collection break is **resolved** — SAM collects and passes this cycle.

> ⚠️ **Ruff version**: CI ran **ruff 0.16.5** (pinned, matches local per 10-02 L2). The lint failures are real code issues, **not** a version-mismatch artifact.

---

## Test Results — Backend (6626 passed, 12 skipped, **46 failed**, 0 collection errors — 1006.68s ≈ 16m47s)

🔴 **Red — primary cause of the failed run.** 6684 tests collected; 46 fail at runtime (not collection). All 46 trace to the same DB-abstraction refactor. Grouped by error signature:

| # | Error signature | Root cause | Test modules |
| - | --------------- | ---------- | ------------ |
| 19 | `TypeError: 'Mock' object does not support the context manager protocol` | Tests mock the cursor/connection helper with a plain `Mock`; the new code uses it as a `with ... as (cursor, conn):` context manager, which a bare `Mock` does not implement. | `test_zzp_invoice_service.py`, `test_zzp_edge_cases.py` |
| 13 | `ValueError: not enough values to unpack (expected 2, got 0)` | New code does `with get_cursor() as (cursor, conn):` (2-tuple yield). The test's mock context manager yields nothing (0 values), so the 2-target unpack fails. | `test_preservation_account_scoped_save.py`, `test_preservation_closed_period.py`, `test_closure_aware_bug_condition.py` |
| 11 | `AttributeError: <database.DatabaseManager> does not have the attribute 'get_connection'` | Tests `patch.object(db, "get_connection", ...)`, but the method was **renamed to `_get_connection`** (now private). `patch` fails because the attribute no longer exists. | `test_banking_balance_closure.py`, `test_duplicate_performance.py` |
| 2 | `AssertionError: Regex pattern did not match.` | `pytest.raises(..., match=...)` on the invoice-number rollback path — the error message/type changed with the transaction refactor, so the regex no longer matches. | `test_zzp_edge_cases.py`, `test_zzp_invoice_service.py` |
| 1 | `AssertionError: Decision handling should succeed for continue` | Property-based (`TestDuplicateCheckerProperties`) duplicate-decision test — a user-decision path no longer returns success for the `continue` branch after the refactor. | `test_duplicate_checker.py` |

**Confirmed in source** (`backend/src/database.py`):
- `def _get_connection(self, pool_type="primary")` at line 196 — the old public `get_connection` is gone (hence the 11 `AttributeError`s).
- The cursor context manager yields a 2-tuple: `yield cursor, conn` (lines 249, 270, 326), consumed everywhere as `with self.get_cursor(...) as (cursor, conn):` — hence the 13 unpack errors and the 19 context-manager errors when a mock does not implement that protocol/shape.

**Grouped by root cause:** 46 failures → **1 cause** (DB connection/cursor abstraction refactor in `database.py`). The fix is in the **tests' mocks**, not production code — production works (SAM + the app run); the tests encode the *old* DB contract.

---

## Test Results — SAM module-plane (✅ PASS — collection restored)

✅ **Green.** The 10-02 Critical collection failure (`ModuleNotFoundError: scripts.onboarding._lib.secrets`, from the untracked `secrets.py` masked by `.gitignore` `**/*secret*`) is **resolved** — the 10-02 C1 rename to `tenant_resolver.py` held. SAM collects and all tests pass (`SAM Module-Plane Test Suite` job = success).

---

## Test Results — Frontend (2744 passed, 12 skipped, 0 failed, 203 files — 183.07s)

✅ **Green.** 2756 tests across 203 files, 0 failures. Count stable vs 10-02 (2744 passed). No regressions.

---

## Lint & Static Analysis (Backend Lint job — ❌ FAIL)

| Check | Result |
|-------|--------|
| Ruff Lint | ❌ Fail — **40 errors**, all `RUF059` |
| Ruff Format | ❌ Fail — **1 file** would be reformatted |
| Vulture | ✅ Pass (no dead code) |

### Ruff Lint — 40 × `RUF059` "Unpacked variable `conn` is never used"

Every one of the 40 errors is the **same rule and same variable**: a `conn` (or `connection`) unpacked from the new `with get_cursor() as (cursor, conn):` 2-tuple that the call site never references. This is the **production-side footprint of the exact same refactor** that broke the backend tests. Spread across **24 files** (notable concentrations: `src/bnb_routes.py` ×8, `src/routes/str_routes.py` ×5, `src/services/signup_service.py` ×4, `src/str_channel_routes.py` ×3, `src/hybrid_pricing_optimizer.py` ×3). Ruff reports **"No fixes available (40 hidden fixes can be enabled with `--unsafe-fixes`)"** — so these are **not** safely auto-fixable; each needs a deliberate edit (rename to `_conn`, or `with get_cursor() as (cursor, _):`, or drop the unused binding).

### Ruff Format — 1 file

`src/str_invoice_routes.py:63` — a `logger.info(f"...")` call that was manually split across 3 lines but fits on one; `ruff format` would collapse it. Auto-fixable (`ruff format`). "1 file would be reformatted, 308 files already formatted."

### Vulture — ✅ Pass

No dead code found.

### Non-blocking report-only signals (not CI-blocking, recorded for context)

These planes are explicitly marked **REPORT-ONLY — non-blocking** in the artifacts and did **not** contribute to the red run:

- **SAM ruff lint (report-only): 18 findings.** By rule: `SIM102`=4, `RUF022`=3, `B017`=3, `TRY004`=2, `PYI034`=1, `PLW1510`=1, `PIE810`=1, `PIE804`=1. Down from 41 on 10-02 (the 10-02 L1 auto-fix sweep held; the remaining ~18 are the manual-judgment findings).
- **Frontend ESLint (report-only): ~1,100+ warnings.** Dominated by `@typescript-eslint/no-explicit-any`, `@typescript-eslint/no-unused-vars`, and `import-x/order`; heavily concentrated in `frontend/src/__mocks__/chakra-ui-react.tsx` and test files.
- **Frontend tsc (report-only): 2 type errors.**
  - `frontend/src/components/banking/__tests__/BankingFileUpload.account-scoped-dedupe-preservation.test.tsx:306:40` — `TS2872` expression is always truthy.
  - `frontend/src/components/members/MembersFieldFormBody.tsx:188:15` — `TS2322` `EnumOptionConfig[]` not assignable to `LazyOption<string>[]`. **This reappeared** — it was marked fixed as 10-02 M2 but is present again in this run's artifact (line moved 187→188). See Lessons.

- **Total by category**: CI-blocking = 40 ruff lint + 1 ruff format = 41 backend lint errors; report-only = 18 SAM ruff + ~1,100 FE ESLint + 2 FE tsc.
- **Auto-fixable vs manual (CI-blocking)**: ruff format (1 file) is auto-fixable via `ruff format`; the 40 `RUF059` are **not** safely auto-fixable (hidden/unsafe fixes only) — each is a manual edit.
- **Version mismatch**: none (local 0.16.5 == CI 0.16.5).

---

## Comparison with recent runs (the 09-27 → 10-03 arc)

| Metric               | 09-27 | 09-28 | 09-29 | 09-30 | 10-02 | 10-03 | Trend                                         |
| -------------------- | ----- | ----- | ----- | ----- | ----- | ----- | --------------------------------------------- |
| CI conclusion        | ✅     | ❌     | ✅     | ❌     | ❌     | ❌     | 🔴 Red 3 cycles running — different cause each |
| Backend failures     | 0     | 0     | 0     | 0     | 0     | **46**| 🔴 **New: DB-abstraction refactor regression** |
| SAM plane            | 0     | 0     | 0     | 0     | ❌ collect | ✅ | ✅ 10-02 collection break resolved             |
| Frontend failures    | 0     | 10    | 0     | 0     | 0     | 0     | ✅ Held green                                   |
| Ruff lint errors     | 0     | 2     | 0     | 0     | 0     | **40**| 🔴 **New: `RUF059` ×40 (same refactor)**        |
| Ruff format files    | 0     | 0     | 0     | 5     | 0     | **1** | 🔴 Minor regression (1 file)                    |
| Vulture              | Pass  | Pass  | Pass  | Pass  | Pass  | Pass  | — Stable                                        |
| Total backend tests  | —     | 6564  | 6564  | 6622  | 6645  | 6684  | ↑ +39 since 10-02                               |
| Total frontend tests | 2716  | 2716  | 2734  | 2734  | 2756  | 2756  | — stable                                        |

### Held / fixed (stayed green)

- ✅ **SAM plane fixed** — the 10-02 Critical collection error is resolved; the `secrets.py` → `tenant_resolver.py` rename held and SAM passes.
- ✅ Frontend held green (2744 passed, 4th+ consecutive cycle for the Members-modal `LazySelect` suites).
- ✅ Vulture green.

### Regression this cycle

- 🔴 **Backend tests: 0 → 46**, and **backend ruff lint: 0 → 40**, from **one** change: the `database.py` connection/cursor abstraction refactor (`get_connection` → `_get_connection`; cursor CM now yields `(cursor, conn)`). Production code was updated to the new shape (so the app and SAM run), but (a) 46 unit-test mocks still encode the old contract and (b) 40 production call sites unpack a `conn` they don't use.
- 🔴 **Backend ruff format: 0 → 1** (`str_invoice_routes.py` line-length reflow). Minor, auto-fixable.

### New failures introduced by the previous cycle's changes

- The 10-02 fix sprint (C1 SAM rename, M1 pre-push collect guard, M2 `MembersFieldFormBody` type fix, L1 SAM ruff sweep, L2 ruff-pin) did **not** touch `backend/src/database.py`. The DB refactor is **new debt from a separate feature commit** landed on `main` after 10-02 — same meta-pattern (change lands on main, breaks the next scheduled run), new subsystem.
- ⚠️ **10-02 M2 regression**: the `MembersFieldFormBody.tsx` `TS2322` type error marked fixed on 10-02 is **present again** in the 10-03 tsc artifact (now line 188). It is report-only so it did not redden CI, but the "fixed" state did not hold — see Lessons 4.

---

## Lessons / Recurring Issues

1. **A single abstraction refactor fans out into both a test-plane failure AND a lint failure — treat them as one root cause, not two.** The 46 backend test failures and the 40 `RUF059` lint errors are two symptoms of the same `database.py` change. Fixing one without the other leaves CI red; the dependency graph groups them under one cause so they land together.

2. **The fix belongs in the test mocks, not production.** Production code (and SAM) run fine on the new `(cursor, conn)` contract — the 46 failures are tests asserting the *old* contract (`get_connection` attribute, non-context-manager mocks, non-2-tuple yields). This is the inverse of a product bug: the tests are stale. Updating a shared cursor-mock fixture/helper to the new 2-tuple-yielding context-manager shape should clear most of the 43 context-manager/unpack/attribute failures in one place; the 2 `match=` regex and 1 property-test failures need individual attention.

3. **RECURRING RULE: `RUF059` has bitten before (08-12, 08-18) and is back at scale.** The "unpacked-but-unused `conn`" pattern recurs whenever the cursor-unpacking idiom spreads to new call sites. The durable fix is a **convention**: when a call site doesn't need the connection, bind `with get_cursor() as (cursor, _conn):` (or `as (cursor, _):`) from the start. Consider a cursor-only context manager (`get_cursor_only()`) so sites that never touch `conn` don't unpack it at all — that would prevent the rule from recurring a fourth time.

4. **RECURRING META-PATTERN (4th+ cycle): breakage keeps entering `main` via commits that land after the daily suite and only surface on the next scheduled run.** 09-28 (lint ×2), 09-30 (format ×5), 10-02 (untracked module), and now 10-03 (DB refactor). The 10-02 M1 pre-push *collect* guard catches collection/import breaks but **not** runtime test failures or lint regressions — it is collect-only by design. This cycle argues for broadening the pre-push gate to also run the **affected test subset + `ruff check`/`ruff format --check`** (not just `--collect-only`), or enforcing it in a required pre-merge check.

5. **"Fixed" report-only items can silently regress — 10-02 M2 is back.** The `MembersFieldFormBody.tsx` `TS2322` was marked done on 10-02 but reappears in the 10-03 tsc artifact. Because tsc is report-only (non-blocking), nothing enforced the fix, so it drifted back (the 10-02 note itself flagged a stale `.tsbuildinfo` masking the check). Report-only gates do not hold fixes in place — if `TS2322` matters, it needs either a blocking check or a regression test. Re-tracked here as M2.

6. **Ruff's "40 hidden fixes" are `--unsafe-fixes` — do not blanket-apply them.** `RUF059` auto-removal of an unpack target can change tuple arity and mask a real "forgot to use `conn`" bug. Each of the 40 should be a deliberate `_conn`/`_` rename or a switch to a cursor-only helper, reviewed against whether that site legitimately needs the connection (e.g. for an explicit `conn.commit()`).
