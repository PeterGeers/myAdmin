# Design Document

## Overview

This design closes the connection-lifecycle gap left open by the completed `database-abstraction-layer` spec. It has three movements:

1. **Enforce** — activate the existing dormant import-guard in the nightly Full Test Suite, and extend it with a second AST check that flags the raw `get_connection()` assignment pattern (with a strictly-decreasing allow-list so it can land before the migration finishes).
2. **Migrate** — convert all 56 raw call sites across 21 `backend/src` files to the context-managed API (`get_cursor()` / `transaction()`), grouped by the five shapes and ordered lowest-risk first.
3. **Seal** — once the allow-list is empty, privatize `get_connection()` (rename to `_get_connection`) so the escape hatch cannot be reopened.

Scope is strictly `backend/src` production call sites plus the guard tooling. `backend/scripts/` and `backend/tests/` raw sites, dialect-helper work, and any PostgreSQL-readiness effort are explicitly out of scope (owned by the parent spec). No schema, data, or view changes.

## Architecture

### Enforcement components

```
backend/scripts/check_db_imports.py        # existing — import guard (Req 1)
backend/scripts/check_raw_connection.py     # new — raw get_connection() guard (Req 2)
backend/tests/unit/test_check_raw_connection.py  # new — tests for the raw guard
.github/workflows/full-test-suite.yml       # modified — add a guard step to backend-lint job
```

The existing `check_db_imports.py` already exposes reusable, parameterized helpers (`check_file(filepath, allowed_files)`, `scan_directory(root, allowed_files, excluded_dirs)`, `_iter_py_files`). The new raw-connection check reuses the same scaffolding conventions (AST walk, `EXCLUDED_DIRS`, POSIX-normalized relative paths, exit 0/1) rather than inventing a new structure.

### Why a sibling script, not an extension of check_db_imports.py

`check_db_imports.py` has a single, well-tested responsibility (import statements) and its own allow-list semantics (files always allowed). The raw-connection check needs a different allow-list semantics: a shrinking list of `file:line` or `file`-scoped pending sites, not permanently-allowed files. Keeping it a sibling avoids conflating two allow-lists with opposite lifecycles (one permanent, one temporary) in one module.

## Components and Interfaces

### check_raw_connection.py (new, Req 2)

AST-based detector for the Raw_Connection_Pattern.

- **Detection:** walk each `backend/src` `.py` file; flag any `ast.Assign` (or `ast.AnnAssign`) whose `.value` is an `ast.Call` whose func resolves to `get_connection` — matching attribute chains `db.get_connection`, `self.db.get_connection`, `self.get_connection`, and the bare name `get_connection`. Match on the attribute/name `get_connection` regardless of receiver, to catch aliased managers.
- **Legitimate-use exclusion (Req 2.4):** `backend/src/database.py` is never scanned for this pattern (its `get_cursor()` fallback calls `self.get_connection()` by design). Implemented via an always-allowed file set, mirroring `check_db_imports.ALLOWED_FILES`.
- **Allow-list (Req 2.2, 2.5):** a module-level `PENDING_SITES` set of `"path"` entries (file-granular is sufficient and less brittle than line numbers). A file on the list is skipped. The migration removes each file from `PENDING_SITES` as its task completes; the final privatization task asserts the set is empty.
- **Output:** on an un-allow-listed hit, print `path:lineno: raw get_connection() assignment — replace with 'with db.get_cursor() as (cursor, conn):' (reads) or 'with db.transaction() as (cursor, conn):' (writes)` and exit 1.
- **Interface:** `check_file(path, allowed, pending) -> list[str]`, `scan(root, allowed, pending, excluded) -> list[str]`, `main()`.

The initial `PENDING_SITES` is seeded with exactly the 21 files from the verified inventory, so the check passes green on day one and becomes a strictly-decreasing counter.

### Full Test Suite wiring (Req 1)

Add a step to the existing `backend-lint` job (`.github/workflows/full-test-suite.yml`), guarded by the same `if: ${{ github.event_name == 'schedule' || inputs.scope == 'all' || inputs.scope == 'backend' }}` condition and `working-directory: backend` context used by the ruff/vulture steps:

```yaml
      - name: DB abstraction guards
        working-directory: .
        run: |
          python backend/scripts/check_db_imports.py
          python backend/scripts/check_raw_connection.py
```

Both run from repo root (the scripts resolve paths relative to `.`). The step fails the job on any violation (Req 1.2). It is added once; it covers both guards.

### Local fast-feedback layers (Req 1.5-1.7)

Both guards run locally before code reaches the nightly suite. Neither is authoritative — the Full Test Suite step is (Req 1.6).

**Single-file capability (Req 1.7).** Both guard scripts gain a CLI that accepts optional file path args: `python backend/scripts/check_db_imports.py [path ...]` and likewise for `check_raw_connection.py`. With no args they scan `SCAN_DIRS` (CI behavior, unchanged); with paths they check only those files. The existing `check_file(path, ...)` helper already supports this; `main()` is extended to read `sys.argv[1:]`.

**(a) Agent file-save hook.** A `.kiro/hooks` hook triggered on save of `backend/**/*.py` runs both guards against the saved file and surfaces any violation in-editor. Because it passes the single saved path, it is instant and does not scan the tree. It is advisory (does not block the save).

**(b) Git pre-commit hook.** A pre-commit hook collects staged `backend/**/*.py` paths (`git diff --cached --name-only --diff-filter=ACM`) and runs both guards against just those paths, exiting non-zero (blocking the commit) on any violation. It follows the repo's existing hook conventions (there is already a pre-push hook). It is bypassable with `--no-verify` by design (Req 1.6). To keep it fast and offline, it performs no DB connection — it is pure AST static analysis.

Both layers call the SAME guard scripts as CI, so there is one source of truth for the rules and the allow-list; a site allow-listed in `PENDING_SITES` is treated identically everywhere.

## Migration recipes by shape

### Shape 1 — plain read/write with cursor (Req 3)

Read:
```python
# before
conn = db.get_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute(q, params); rows = cursor.fetchall()
cursor.close(); conn.close()
# after
with db.get_cursor() as (cursor, conn):   # dictionary=True is the default
    cursor.execute(q, params); rows = cursor.fetchall()
```

Write (HIGHEST RISK — `get_cursor()` does NOT commit, `transaction()` does):
```python
# before
conn = db.get_connection(); cursor = conn.cursor()
cursor.execute(ins, params); conn.commit()
cursor.close(); conn.close()
# after
with db.transaction() as (cursor, conn):   # auto-commits on success, rollbacks on error
    cursor.execute(ins, params)
```

Rules: preserve the exact `dictionary=` flavor (pass `dictionary=False` to `get_cursor` where the original used a plain cursor); drop redundant `close()` calls. `transaction()` is the preferred Write_Site form (Req 3.2); an explicit `conn.commit()` under `get_cursor()` is used ONLY for DDL (`execute_ddl()`) or intentionally-incremental commits (Req 3.3). **Preserve the original commit granularity** — same number and timing of commits; do NOT collapse a per-iteration commit loop into one transaction or vice versa (Req 3.4). A per-write test asserts the row is actually committed (Req 3.6).

### Shape 2 — pandas read_sql (Req 4)

```python
# before
conn = db.get_connection()
df = pd.read_sql(q, conn, params=[...])
conn.close()
# after
with db.get_cursor() as (_cursor, conn):
    df = pd.read_sql(q, conn, params=[...])
```

Target mirrors the already-migrated `bnb_cache.py`. Where a site already uses the `_read_sql_safe` warning-suppression wrapper (`mutaties_cache_loader.py`), preserve it (Req 4.2).

### Shape 3 — class-wrapped get_cursor (Req 5.1)

`reporting_routes.py` defines its own `@contextmanager get_cursor(self)` that calls `self.db.get_connection()` and `yield cursor` (a single value, not a tuple). Delegate to the manager while preserving the single-value yield its callers expect:
```python
@contextmanager
def get_cursor(self):
    with self.db.get_cursor() as (cursor, _conn):
        yield cursor
```
This fixes all of the class's internal callers at once without touching them.

### Shape 4 — connectivity probe (Req 5.2)

`pdf_decision_helpers.py`: `test_connection = db.get_connection(); if test_connection: test_connection.close()`. Replace with a context-managed probe that opens and releases without leaking:
```python
with db.get_cursor() as (cursor, _conn):
    cursor.execute("SELECT 1")
```
(or a dedicated `DatabaseManager.healthcheck()` if preferred — but reusing `get_cursor` avoids adding API surface).

### Shape 5 — generator holding the connection across yield 

**Validates: Requirements 5.3**

`pdf_validation.py::validate_pdf_urls_with_progress` opens a connection then `yield`s progress dicts across a loop. The `with` block must wrap the ENTIRE generator body so the connection lives for every yield and is released when iteration finishes, the consumer stops early (GeneratorExit), or an error propagates:
```python
def validate_pdf_urls_with_progress(self, ...):
    with self.db.get_cursor() as (cursor, _conn):
        ...
        for i, record in enumerate(records):
            ...
            yield {...}
```
`get_cursor`'s `finally` closes the connection on normal completion, early close, and exception alike — which is exactly the lifetime guarantee needed.

### Stray-import cleanup (Req 1.3)

- `backend/src/migrations/apply_tenant_isolation.py` — standalone `mysql.connector.connect()` running `INFORMATION_SCHEMA` checks + `ALTER TABLE`. Convert to `DatabaseManager` + `execute_ddl` / `execute_query`.
- `backend/scripts/database/migrate_budget_railway.py` — standalone connect with hardcoded Railway host defaults running `CREATE TABLE` DDL. Convert to `DatabaseManager`; drop the hardcoded host/credential fallbacks (config comes from env per steering).

(These two are needed so `check_db_imports.py` passes green when first activated. The budget script lives under `scripts/`, so it is in scope only for the import-guard cleanup, not the 56-site count.)

### Privatization (Req 6)

Once `PENDING_SITES` is empty: rename `DatabaseManager.get_connection` -> `_get_connection`; update the one internal caller in `get_cursor()`'s fallback; update `check_raw_connection.py` to treat ANY external `get_connection`/`_get_connection` assignment as a hard failure (no allow-list). The public `get_cursor`, `transaction`, `execute_query`, `execute_batch_queries`, `execute_ddl` surface is untouched (Req 6.4).

## Data Models

No database schema, data, or view changes. The only new "data" is the `PENDING_SITES` allow-list in `check_raw_connection.py`, which shrinks to empty over the migration.

## Error Handling

- `get_cursor()` / `transaction()` already wrap `mysql.connector` errors into the agnostic hierarchy (`DatabaseError`, `IntegrityError`, `ConnectionError`, `OperationalError`) and roll back on exception. Migrated sites therefore inherit consistent error wrapping; any site that previously caught `mysql.connector.Error` directly is updated to catch the agnostic type (Behavior_Preserving on observable errors, Req 7.5).
- `transaction()` rolls back on exception; sites that previously had partial-commit bugs will become correct — flag any such behavior change in review rather than silently "preserving" a bug.

## Testing Strategy

- **Guard unit tests** (`test_check_raw_connection.py`): detects each receiver form (`db.`, `self.db.`, `self.`, bare); ignores `database.py`'s internal use; respects and shrinks the allow-list; non-assignment calls (already inside a `with`) are NOT flagged.
- **Per-file migration verification:** run the full backend suite after each file/group; for Write_Sites, a test that asserts committed state (query the row back), not just a 200 response (Req 3.4).
- **Behavior-preservation:** for representative read endpoints, assert identical response shape/content before and after; for pandas sites, assert identical DataFrame for fixed inputs.
- **Checkpoints** after each shape group, and a final checkpoint asserting `PENDING_SITES == set()` and the full suite green.
- Backend CI being disabled, the authoritative gate is the nightly Full Test Suite; local runs use `backend/.venv` + pytest against `testfinance` with `test_mode=True`.

## Rollout / Incremental Deployability (Req 7)

Order (lowest-risk first): activate guards + stray-import cleanup -> Shape 3 -> Shape 4 -> Shape 1 reads -> Shape 2 -> Shape 1 writes (each Write_Site its own reviewable unit) -> Shape 5 -> privatize. Each file is independently deployable; the allow-list keeps the guard green throughout and strictly decreasing.

## Correctness Properties

These properties frame the migration as behavior-preserving and the guard as monotonic. They drive the test strategy above.

### Property 1: Behavior preservation (universal)

For all migrated call sites and all valid inputs, the migrated code produces the same observable result as the original: identical API response shape/content for reads, identical committed rows for writes, and the same agnostic exception type on failure. 

**Validates: Requirements 3.5, 4.3, 5.4, 7.5**

### Property 2: Write durability

For every Write_Site, after the operation completes successfully the written row is present on a fresh read; after an operation that raises, no partial row remains (transaction rollback). This specifically catches the `get_cursor()`-does-not-commit hazard. 

**Validates: Requirements 3.2, 3.4**

### Property 3: Connection-lifetime safety for the generator (Shape 5)

For all consumption patterns (full iteration, early close/break, exception mid-iteration), exactly one connection is acquired and it is released exactly once when iteration ends. 

**Validates: Requirements 5.3**

### Property 4: Guard soundness and completeness

For all `backend/src` files, the raw-connection check flags a file if and only if it contains a Raw_Connection_Pattern assignment AND the file is not on `PENDING_SITES` and is not the internal `database.py`. No false positive on calls already inside a `with` block or passed directly as an argument. 

**Validates: Requirements 2.1, 2.3, 2.4**

### Property 5: Allow-list monotonicity

`PENDING_SITES` only ever shrinks across the migration and is empty at completion; the guard never needs a file re-added. 

**Validates: Requirements 2.5, 6.3**
