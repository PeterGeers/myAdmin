# Implementation Plan

## Overview

Seal the raw `get_connection()` escape hatch left open by the completed `database-abstraction-layer` spec. Three movements: (1) activate + extend the guards (CI step in the Full Test Suite, plus a local on-save agent hook and a git pre-commit hook) with a strictly-decreasing `PENDING_SITES` allow-list; (2) migrate all 56 raw call sites across 21 `backend/src` files to the context-managed API, lowest-risk shape first; (3) privatize `get_connection()` -> `_get_connection` once the allow-list is empty.

**Language:** Python (Flask backend, pytest + Hypothesis). Scope: `backend/src` production call sites + guard tooling only. No schema/data/view changes.

**Classification (verified by scan):** reads use `with db.get_cursor() as (cursor, conn):`; writes use `with db.transaction() as (cursor, conn):` and MUST preserve the original commit granularity (same count/timing); explicit `conn.commit()` only for DDL (`execute_ddl()`) or intentionally-incremental commits. Each write-site task adds a commit-durability test.

## Tasks

### Wave 0: Enforcement foundation

- [x] 1. Build and wire the database-access guards
  - [x] 1.1 Add single-file CLI to `check_db_imports.py`
    - Extend `main()` to accept optional path args (`sys.argv[1:]`); with paths, check only those files; with none, scan `SCAN_DIRS` (unchanged CI behavior)
    - _Requirements: 1.7_
  - [x] 1.2 Create `backend/scripts/check_raw_connection.py` (new raw-pattern guard)
    - AST detector flagging `Assign`/`AnnAssign` whose value is a `get_connection(...)` call (receivers: `db.`, `self.db.`, `self.`, bare); reuse `check_db_imports` scaffolding conventions
    - `PENDING_SITES` file-granular allow-list seeded with the 21 inventory files; always-exclude `backend/src/database.py`; single-file CLI like 1.1
    - Violation message includes file, line, and the recommended `get_cursor()` / `transaction()` replacement; exit 0/1
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 1.7_
  - [x] 1.3 Write unit tests `backend/tests/unit/test_check_raw_connection.py`
    - Detect each receiver form; ignore `database.py` internal use; respect + shrink allow-list; no false positive on calls already inside a `with` / passed as an argument
    - **Validates: Requirements 2.1, 2.3, 2.4**
  - [x] 1.4 Refactor the two stray `mysql.connector` imports (clean import-guard baseline)
    - `backend/src/migrations/apply_tenant_isolation.py`: standalone connect + INFORMATION_SCHEMA checks + ALTER -> `DatabaseManager` + `execute_ddl`/`execute_query`
    - `backend/scripts/database/migrate_budget_railway.py`: standalone connect + CREATE TABLE DDL -> `DatabaseManager`; drop hardcoded Railway host/credential fallbacks (env-only per steering)
    - _Requirements: 1.3_
  - [x] 1.5 Wire both guards into the Full Test Suite
    - Add a "DB abstraction guards" step to the `backend-lint` job in `.github/workflows/full-test-suite.yml`, same `if:` scope gate, running `check_db_imports.py` then `check_raw_connection.py` from repo root; step fails job on violation
    - _Requirements: 1.1, 1.2_
  - [x] 1.6 Add the local on-save agent hook
    - A `.kiro/hooks` hook on save of `backend/**/*.py` that runs both guards against the saved path (single-file CLI) and surfaces violations in-editor; advisory (non-blocking)
    - _Requirements: 1.5, 1.6, 1.7_
  - [x] 1.7 Add the git pre-commit hook
    - Collects staged `backend/**/*.py` (`git diff --cached --name-only --diff-filter=ACM`), runs both guards against those paths, blocks commit on violation; pure AST (no DB connection); bypassable with `--no-verify` by design
    - _Requirements: 1.5, 1.6_

- [x] 2. Checkpoint - Guards live, baseline green
  - Run both guards locally; confirm import-guard passes (stray imports fixed) and raw-guard passes with the 21-file allow-list; full backend suite green. Ask the user if questions arise.

### Wave 1: Shape 3 + Shape 4 (lowest risk)

- [x] 3. Migrate `reporting_routes.py` (Shape 3 - class-wrapped get_cursor)
  - Delegate the class's internal `@contextmanager get_cursor` to `self.db.get_cursor()`, preserving its single-value `yield cursor` for existing callers; remove the file from `PENDING_SITES`
  - _Requirements: 5.1, 5.4, 7.1, 7.2_
- [x] 4. Migrate `pdf_decision_helpers.py` (Shape 4 - connectivity probe)
  - Replace `test_connection = db.get_connection(); ... .close()` with a context-managed probe (`with db.get_cursor() as (cursor, _conn): cursor.execute("SELECT 1")`); remove from `PENDING_SITES`
  - _Requirements: 5.2, 5.4, 7.1, 7.2_

### Wave 2: Shape 1 reads (pure SELECT)

- [x] 5. Migrate Shape 1 read-only files to `get_cursor()`
  - Each file: convert its raw read site(s) to `with db.get_cursor() as (cursor, conn):`, preserve `dictionary=` flavor, drop redundant `close()`; remove each from `PENDING_SITES`; Behavior_Preserving
  - [x] 5.1 `bnb_routes.py` (8 sites)
  - [x] 5.2 `banking_checks.py` (2 sites)
  - [x] 5.3 `routes/aangifte_ib_routes.py` (1)
  - [x] 5.4 `routes/financial_reporting_routes.py` (1)
  - [x] 5.5 `report_generators/financial_report_generator.py` (1)
  - [x] 5.6 `services/country_report_service.py` (1)
  - [x] 5.7 `xlsx_export.py` (1)
  - [x] 5.8 `banking_processor.py` (1)
  - _Requirements: 3.1, 3.5, 3.7, 7.1, 7.2_

- [x] 6. Checkpoint - Shapes 3/4 and reads migrated
  - Full backend suite green; `PENDING_SITES` reduced accordingly. Ask the user if questions arise.

### Wave 3: Shape 2 pandas (read-only)

- [x] 7. Migrate `business_pricing_model.py` (Shape 2 - pandas read_sql, 5 sites)
  - Convert each `conn = db.get_connection(); pd.read_sql(q, conn, ...)` to `with db.get_cursor() as (_cursor, conn): pd.read_sql(q, conn, ...)` (mirror `bnb_cache.py`); DataFrames identical; remove from `PENDING_SITES`
  - _Requirements: 4.1, 4.2, 4.3, 7.1, 7.2_

### Wave 4: Shape 1 writes + mixed (highest risk - transaction() + commit-granularity, durability tests)

- [x] 8. Migrate Shape 1 write files to `transaction()` preserving commit granularity
  - Each file: reads -> `get_cursor()`; writes -> `with db.transaction()`; explicit `commit()` only for DDL/intentional incremental commits; preserve original commit count/timing; add a commit-durability test (read the row back); remove each from `PENDING_SITES`; Behavior_Preserving
  - [x] 8.1 `btw_processor.py` (2 sites)
  - [x] 8.2 `routes/str_routes.py` (5 sites; writes present)
  - [x] 8.3 `str_channel_routes.py` (3 sites)
  - [x] 8.4 `str_invoice_routes.py` (2 sites)
  - [x] 8.5 `routes/banking_routes.py` (1 site)
  - [x] 8.6 `services/zzp_invoice_numbering.py` (1 site; sequence numbering - verify no double-commit / race change)
  - [x] 8.7 `services/year_end_service.py` (2 sites)
  - [x] 8.8 `services/banking_mutatie_service.py` (2 sites)
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 7.1, 7.2_
- [x] 9. Migrate `hybrid_pricing_optimizer.py` (mixed: Shape 2 pandas reads + Shape 1 writes, 9 sites)
  - pandas reads -> `with db.get_cursor() as (_cursor, conn): pd.read_sql(...)`; the DELETE-then-INSERT save methods -> single `with db.transaction()` (atomic replace preserves the one-commit granularity); commit-durability test; remove from `PENDING_SITES`
  - _Requirements: 3.1, 3.2, 3.4, 3.6, 4.1, 4.3, 7.1, 7.2_

- [x] 10. Checkpoint - All writes migrated
  - Full backend suite green incl. new commit-durability tests; `PENDING_SITES` down to the generator file only. Ask the user if questions arise.

### Wave 5: Shape 5 generator (+ its write methods)

- [x] 11. Migrate `pdf_validation.py` (Shape 5 generator + 2 Shape 1 writes, 5 sites)
  - `validate_pdf_urls_with_progress`: wrap the ENTIRE generator body in `with self.db.get_cursor() as (cursor, _conn):` so the connection lives across all `yield`s and releases on completion / early close / error
  - `_update_ref3` and the bulk Ref3 update: `with db.transaction()`; add commit-durability tests; tenant-scope (`administration`) unchanged
  - Remove from `PENDING_SITES`
  - _Requirements: 5.3, 5.4, 3.1, 3.2, 3.4, 3.6, 7.1, 7.2_

### Wave 6: Seal

- [x] 12. Privatize `get_connection()` and flip the guard to zero-tolerance
  - [x] 12.1 Rename `DatabaseManager.get_connection` -> `_get_connection`; update the internal `get_cursor()` fallback caller; public `get_cursor`/`transaction`/`execute_query`/`execute_batch_queries`/`execute_ddl` unchanged
    - _Requirements: 6.1, 6.2, 6.4_
  - [x] 12.2 Update `check_raw_connection.py` to treat ANY external `get_connection`/`_get_connection` assignment as a hard failure; assert `PENDING_SITES` is empty
    - _Requirements: 6.3, 2.5_
- [x] 13. Final checkpoint - Hatch sealed
  - `PENDING_SITES == set()`; both guards green in CI, on-save, and pre-commit; full backend suite green with zero regressions; no schema/data/view change. Ask the user if questions arise.
  - **Validates: Requirements 6.1, 6.2, 6.3, 7.1, 7.3, 7.5**

## Task Dependency Graph

```json
{ what b
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "2"] },
    { "id": 1, "tasks": ["3", "4"] },
    { "id": 2, "tasks": ["5.1","5.2","5.3","5.4","5.5","5.6","5.7","5.8","6"] },
    { "id": 3, "tasks": ["7"] },
    { "id": 4, "tasks": ["8.1","8.2","8.3","8.4","8.5","8.6","8.7","8.8","9","10"] },
    { "id": 5, "tasks": ["11"] },
    { "id": 6, "tasks": ["12.1","12.2","13"] }
  ]
}
```

- Wave 0 builds the guards + allow-list and cleans the import baseline before any migration; task 2 is its checkpoint.
- Waves 1-5 migrate shapes lowest-risk first (3/4 -> reads -> pandas -> writes/mixed -> generator); each file is independently deployable and removes itself from `PENDING_SITES`.
- Wave 6 privatizes `get_connection()` only after the allow-list is empty, then the final checkpoint.

## Notes

- `get_cursor()` does NOT auto-commit; `transaction()` does. Writes migrated to `get_cursor()` without a commit silently lose data - this is the single highest risk and why writes are their own wave with durability tests.
- Preserve commit granularity: do not collapse per-iteration commits into one transaction or vice versa (Req 3.4).
- The allow-list is strictly decreasing: a file is removed only when fully migrated; it is never re-added.
- Mixed files (`hybrid_pricing_optimizer.py`, `pdf_validation.py`) carry more than one shape and are scheduled in the higher-risk of their shapes' waves.
- Authoritative gate is the nightly Full Test Suite (Backend CI is disabled); local hooks are fast feedback only and may be bypassed.
- Explicitly out of scope: `backend/scripts/` and `backend/tests/` raw sites (except the one stray import cleanup in 1.4), dialect-helper work, and any PostgreSQL-readiness effort - all owned by the parent `database-abstraction-layer` spec.
