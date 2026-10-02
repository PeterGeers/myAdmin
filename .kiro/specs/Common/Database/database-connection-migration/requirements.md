# Requirements Document

## Introduction

The completed `database-abstraction-layer` spec centralized MySQL driver imports, introduced dialect helpers and agnostic exceptions, and built an AST import-guard (`backend/scripts/check_db_imports.py`). It deliberately kept `DatabaseManager.get_connection()` public (Req 9.1, backward compatibility). As a result, a leaky escape hatch remains: **56 call sites across 21 production files** obtain a raw, caller-owned connection via `conn = db.get_connection(); cursor = conn.cursor(); ...; conn.close()` instead of the context-managed `get_cursor()` / `transaction()` / `execute_query()` API.

Two gaps keep the "local, non-generic DB function" pattern alive:

1. **The guard is dormant.** `check_db_imports.py` exists but is wired into no CI workflow, and it only detects `import mysql.connector` — not the raw `get_connection()` assignment pattern. Two stray imports have already slipped back in (`backend/src/migrations/apply_tenant_isolation.py`, `backend/scripts/database/migrate_budget_railway.py`).
2. **`get_connection()` is still public.** Nothing prevents new raw-pattern call sites from being added.

This spec closes both gaps. It (a) activates and extends enforcement so the pattern cannot regress, (b) migrates all 56 raw call sites to the context-managed API, and (c) privatizes `get_connection()` so the escape hatch is sealed. It is a continuation of the abstraction-layer effort, scoped to the connection-lifecycle slice only. It is **not** a database migration and changes no schema or data.

### Verified inventory (ground truth)

Raw `get_connection()` assignment sites in `backend/src` (excluding the one legitimate internal use inside `database.py`'s own `get_cursor` fallback): **56 sites, 21 files**.

Per-file counts: `hybrid_pricing_optimizer.py` (9), `bnb_routes.py` (8), `routes/str_routes.py` (5), `pdf_validation.py` (5), `business_pricing_model.py` (5), `str_channel_routes.py` (3), `str_invoice_routes.py` (2), `services/year_end_service.py` (2), `services/banking_mutatie_service.py` (2), `reporting_routes.py` (2), `btw_processor.py` (2), `banking_checks.py` (2), `xlsx_export.py` (1), `services/zzp_invoice_numbering.py` (1), `services/country_report_service.py` (1), `routes/financial_reporting_routes.py` (1), `routes/banking_routes.py` (1), `routes/aangifte_ib_routes.py` (1), `report_generators/financial_report_generator.py` (1), `pdf_decision_helpers.py` (1), `banking_processor.py` (1).

### Call-site shapes (each needs a different, careful transform)

- **Shape 1 — plain read/write with cursor** (the majority): `conn = db.get_connection(); cursor = conn.cursor(dictionary=?); cursor.execute(...); ...; cursor.close(); conn.close()`. Reads -> `with db.get_cursor() as (cursor, conn):`. **Writes -> `with db.transaction() as (cursor, conn):`** (or keep an explicit `conn.commit()`), because `get_cursor()` does NOT auto-commit while `transaction()` does. This is the highest-risk transform.
- **Shape 2 — pandas `pd.read_sql(query, conn, ...)`** (`business_pricing_model.py`, `hybrid_pricing_optimizer.py`): passes the raw connection to pandas, not a cursor. Target is the pattern already used elsewhere in the codebase: `with db.get_cursor() as (_cursor, conn): pd.read_sql(query, conn, ...)` (see `bnb_cache.py`; `mutaties_cache_loader.py` wraps it as `_read_sql_safe` to suppress the SQLAlchemy warning).
- **Shape 3 — class-wrapped `@contextmanager get_cursor`** (`reporting_routes.py`): a class exposes its own `get_cursor` that internally calls `get_connection()`. Delegating that one internal method to `self.db.get_cursor()` fixes all its callers at once.
- **Shape 4 — connectivity probe** (`pdf_decision_helpers.py`): `test_connection = db.get_connection(); if test_connection: test_connection.close()`. Replace with a context-managed health check.
- **Shape 5 — generator holding the connection across `yield`** (`pdf_validation.py::validate_pdf_urls_with_progress`): the connection stays open across progress yields; wrapping in `with` must preserve that the connection lives for the whole generator body.

## Glossary

- **DatabaseManager**: central DB access class in `backend/src/database.py` (`execute_query`, `execute_batch_queries`, `get_connection`, `get_cursor`, `transaction`, `execute_ddl`).
- **Raw_Connection_Pattern**: a call site that assigns the result of `get_connection()` to a variable and manually manages the cursor/connection lifecycle (`conn = db.get_connection(); ...; conn.close()`).
- **Context_Managed_API**: `get_cursor()`, `transaction()`, `execute_query()`, `execute_batch_queries()` — the APIs that own connection lifecycle via `with`.
- **Import_Guard**: `backend/scripts/check_db_imports.py`, the AST lint from the abstraction-layer spec.
- **Write_Site**: a Raw_Connection_Pattern site that performs INSERT/UPDATE/DELETE/DDL and relies on a commit.
- **Local_Fast_Feedback**: developer-side checks that run the guards before code reaches CI — an agent file-save hook and a git pre-commit hook — intended for speed, not authoritative enforcement.
- **Behavior_Preserving**: the migrated site returns identical API responses, writes the same data (and still commits), and raises the same observable errors.

## Requirements

### Requirement 1: Activate the Guards (CI + Local Fast Feedback)

**User Story:** As a developer, I want the database-access guards to run automatically in CI and locally, so that stray `mysql.connector` imports and new raw-connection patterns are blocked early instead of silently accumulating.

#### Acceptance Criteria

1. THE Import_Guard SHALL be invoked as a step in the `backend-lint` job of the nightly Full Test Suite (`full-test-suite.yml`) — the authoritative, non-bypassable gate — running on every scheduled run and on every `workflow_dispatch` run whose scope includes the backend.
2. WHEN the Import_Guard detects a disallowed `import mysql.connector` outside the allowed files, THEN the workflow SHALL fail with the file, line, and the correct import path in the message.
3. THE existing stray imports in `backend/src/migrations/apply_tenant_isolation.py` and `backend/scripts/database/migrate_budget_railway.py` SHALL be refactored to the Abstraction_Layer so the guard passes on a clean baseline.
4. THE Import_Guard's allowed-files list SHALL remain configurable without code changes to the scan logic.
5. THE guards SHALL additionally run as a local fast-feedback layer, independent of CI: (a) an agent file-save hook that runs the guard(s) on each saved `backend/**/*.py` file and surfaces any violation in-editor, and (b) a git pre-commit hook that runs the guard(s) against staged `backend/**/*.py` files and blocks the commit on a violation.
6. THE local layers in AC 5 are developer-facing fast feedback only; they MAY be bypassable (e.g. `git commit --no-verify`) and SHALL NOT be relied on as the authoritative gate — the Full Test Suite step in AC 1 remains authoritative.
7. THE guard scripts SHALL support single-file invocation (checking one path) so the agent file-save hook can check only the saved file.

### Requirement 2: Extend the Guard to Detect the Raw Connection Pattern

**User Story:** As a developer, I want the guard to flag new raw `get_connection()` call sites, so that the pattern cannot creep back after migration.

#### Acceptance Criteria

1. THE Import_Guard (or a sibling AST check) SHALL detect the Raw_Connection_Pattern — an assignment whose value is a call to `get_connection(...)` (as `db.get_connection`, `self.db.get_connection`, `self.get_connection`, or a bare `get_connection`) in `backend/src`.
2. THE check SHALL support an explicit allow-list of known-pending sites so it can be introduced before the migration completes without failing the build (a strictly-decreasing baseline).
3. WHEN a new Raw_Connection_Pattern site is added that is not on the allow-list, THEN the check SHALL fail with the file, line, and the recommended Context_Managed_API replacement.
4. THE check SHALL NOT flag the one legitimate internal use inside `DatabaseManager.get_cursor()`'s fallback path in `database.py`.
5. AS each file is migrated, its entries SHALL be removed from the allow-list, and WHEN the migration is complete THE allow-list SHALL be empty.

### Requirement 3: Migrate Plain Cursor Call Sites (Shape 1), Preserving Commit Semantics

**User Story:** As a developer, I want plain read/write raw sites moved to the context-managed API without changing behavior, so that connection handling is consistent and writes still persist.

#### Acceptance Criteria

1. WHEN a Shape 1 read site is migrated, THE site SHALL use `with db.get_cursor() as (cursor, conn):` preserving the original `dictionary=` cursor flavor.
2. WHEN a Shape 1 Write_Site is migrated, THE site SHALL use `with db.transaction() as (cursor, conn):` as the preferred form, so commit and rollback are structural rather than a line that can be forgotten.
3. An explicit `conn.commit()` under `with db.get_cursor()` SHALL be used ONLY where `transaction()` would change observable behavior — specifically (a) DDL statements (use `execute_ddl()`), or (b) a site that intentionally commits incrementally (e.g. once per batch/iteration), where collapsing to a single transaction would alter commit granularity.
4. THE migration SHALL preserve the original commit granularity — the same number and timing of commits as before (a site that committed once at the end still commits once; a site that committed per iteration still commits per iteration).
5. THE migration SHALL remove now-redundant manual `cursor.close()` / `conn.close()` calls that the context manager handles.
6. FOR every migrated Write_Site, a test SHALL assert the write is actually committed (not just that the endpoint returns success).
7. THE migrated sites SHALL be Behavior_Preserving.

### Requirement 4: Migrate pandas read_sql Call Sites (Shape 2)

**User Story:** As a developer, I want pandas-backed query sites to obtain their connection through the context-managed API, so that connection lifecycle is owned by `DatabaseManager`.

#### Acceptance Criteria

1. WHEN a Shape 2 site is migrated, THE site SHALL obtain the connection via `with db.get_cursor() as (_cursor, conn):` and pass that `conn` to `pd.read_sql(...)`.
2. THE migration SHALL preserve any existing SQLAlchemy-warning suppression pattern (e.g. the `_read_sql_safe` wrapper) where already used.
3. THE resulting DataFrames SHALL be identical to pre-migration output for the same inputs (Behavior_Preserving).

### Requirement 5: Migrate Class-Wrapped, Probe, and Generator Call Sites (Shapes 3-5)

**User Story:** As a developer, I want the structurally unusual sites migrated with their lifetime semantics intact, so that no connection is leaked or prematurely closed.

#### Acceptance Criteria

1. WHEN the Shape 3 class-wrapped `get_cursor` is migrated, THE class's internal method SHALL delegate to `self.db.get_cursor()` and all its callers SHALL continue to work unchanged.
2. WHEN the Shape 4 connectivity probe is migrated, THE probe SHALL use a context-managed check that opens and releases the connection without leaking it.
3. WHEN the Shape 5 generator is migrated, THE connection SHALL remain open for the full duration of the generator's iteration and be released when iteration completes or the generator is closed/errors.
4. THE migrated sites SHALL be Behavior_Preserving.

### Requirement 6: Privatize get_connection() After Migration

**User Story:** As a developer, I want the raw accessor sealed once no caller needs it, so that "one centralized way" is actually enforced.

#### Acceptance Criteria

1. AFTER all 56 sites are migrated, THE public `get_connection()` SHALL be renamed to `_get_connection` to mark it private; external modules SHALL NOT call it, and the Requirement 2 check enforces this.
2. WHEN `get_connection()` is privatized, THE internal callers (e.g. `get_cursor()`'s fallback) SHALL be updated to the private name.
3. THE Raw_Connection_Pattern check from Requirement 2 SHALL be updated so that any external use of the accessor is a hard failure with no allow-list entries remaining.
4. THE change SHALL NOT break the public `get_cursor`, `transaction`, `execute_query`, `execute_batch_queries`, `execute_ddl` API.

### Requirement 7: Zero Regressions and Incremental Deployability

**User Story:** As a developer, I want the migration landed safely in reviewable increments, so that the application stays operational throughout.

#### Acceptance Criteria

1. AFTER each file or logical group is migrated, THE full backend test suite SHALL pass with zero regressions.
2. EACH migrated file SHALL be independently deployable without requiring all files to be migrated simultaneously.
3. THE migration SHALL change no database schema, data, or views.
4. THE tasks document SHALL contain an explicit task per file (or tight logical group), grouped by shape and ordered lowest-risk first (Shape 3/4, then Shape 1 reads, Shape 2, Shape 1 writes, Shape 5), with Write_Sites called out individually.
5. THE Behavior_Preserving property SHALL hold for every migrated site: identical API responses, identical committed data, identical observable errors.
