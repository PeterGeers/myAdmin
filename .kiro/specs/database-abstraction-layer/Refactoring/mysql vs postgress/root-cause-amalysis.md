# MySQL → PostgreSQL Migration Analysis for myAdmin

**Date:** 2026-04-29
**Status:** Analysis / Decision Pending
**Author:** Kiro (AI-assisted analysis)

---

## 1. Current State Summary

| Aspect             | Detail                                                                           |
| ------------------ | -------------------------------------------------------------------------------- |
| Database           | MySQL 8.0 (Docker container, `mysql:8.0` image)                                  |
| Connector          | `mysql-connector-python 8.1.0`                                                   |
| ORM                | **None** — raw SQL with parameterized queries (`%s` placeholders)                |
| Connection pooling | Custom `ScalabilityManager` (50 connections) + legacy `MySQLConnectionPool` (20) |
| Tables             | ~40+ tables with foreign keys and indexes                                        |
| Views              | 15+ views with complex joins and JSON operations                                 |
| Migration scripts  | 50+ SQL/Python scripts in `backend/scripts/database/`                            |
| Test database      | Separate `testfinance` database, same MySQL instance                             |
| Infrastructure     | Docker Compose (local), Railway (production)                                     |
| Terraform          | AWS Cognito + SNS only — **no database in Terraform**                            |
| Backup             | MySQL dump in `scripts/CICD/backups/`                                            |

### Direct MySQL imports across the codebase

**~45 Python files** import `mysql.connector` directly — not just `database.py` but also scripts, tests, services, and route files. There is **no abstraction layer or ORM** between application code and MySQL.

---

## 2. MySQL-Specific Features in Use

These are the MySQL-specific constructs that would require conversion:

### 2.1 DDL / Schema

| MySQL Feature                       | Occurrences                                                        | PostgreSQL Equivalent                              |
| ----------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------- |
| `AUTO_INCREMENT`                    | Every table                                                        | `SERIAL` / `GENERATED ALWAYS AS IDENTITY`          |
| `ENGINE=InnoDB`                     | Every `CREATE TABLE`                                               | Not needed (PG has one engine)                     |
| `DEFAULT CHARSET=utf8mb4`           | Every table                                                        | `SET client_encoding = 'UTF8'` (default)           |
| `COLLATE utf8mb4_unicode_ci`        | Tables + WHERE clauses                                             | `COLLATE "und-x-icu"` or column-level collation    |
| `ON UPDATE CURRENT_TIMESTAMP`       | ~10 tables (`updated_at` columns)                                  | Requires trigger function                          |
| `ENUM(...)` column type             | `invoices.status`, `parameters.scope`, `contact_emails.email_type` | `CREATE TYPE ... AS ENUM(...)` or CHECK constraint |
| `UNIQUE KEY name (...)`             | Many tables                                                        | `UNIQUE (...)` or `CREATE UNIQUE INDEX`            |
| `INDEX idx_name (col)`              | Many tables                                                        | `CREATE INDEX idx_name ON table(col)`              |
| Backtick `` ` `` identifier quoting | Views, reserved words (`key`)                                      | Double-quote `"` identifier quoting                |

### 2.2 SQL Functions

| MySQL Function                         | Usage                                               | PostgreSQL Equivalent                 |
| -------------------------------------- | --------------------------------------------------- | ------------------------------------- |
| `IFNULL(a, b)`                         | `chart_of_accounts_routes.py` (3+ places)           | `COALESCE(a, b)`                      |
| `JSON_EXTRACT(col, '$.key')`           | Extensive — chart of accounts, migrations, backfill | `col->>'key'` or `col->'key'`         |
| `JSON_UNQUOTE(JSON_EXTRACT(...))`      | Chart of accounts routes                            | `col->>'key'` (returns text directly) |
| `JSON_SET(col, '$.key', val)`          | Backfill migrations                                 | `jsonb_set(col, '{key}', val)`        |
| `JSON_CONTAINS(...)`                   | Opening balance migrator                            | `col @> '...'::jsonb`                 |
| `YEAR(date_col)`                       | Financial queries, grouping                         | `EXTRACT(YEAR FROM date_col)`         |
| `DATE_SUB(CURDATE(), INTERVAL n YEAR)` | Transaction lookups                                 | `CURRENT_DATE - INTERVAL 'n years'`   |
| `CURDATE()`                            | Multiple queries                                    | `CURRENT_DATE`                        |
| `NOW()`                                | Inserts                                             | `NOW()` (same)                        |
| `DATE_FORMAT(...)`                     | Report generation                                   | `TO_CHAR(date, 'format')`             |
| `STR_TO_DATE(...)`                     | Data imports                                        | `TO_DATE(str, 'format')`              |
| `GROUP_CONCAT(...)`                    | (in backup dump, potential use)                     | `STRING_AGG(col, ',')`                |

### 2.3 Administrative / Introspection

| MySQL Feature                                                | Usage                                   | PostgreSQL Equivalent                                       |
| ------------------------------------------------------------ | --------------------------------------- | ----------------------------------------------------------- |
| `SHOW CREATE VIEW name`                                      | 6+ scripts (view inspection, migration) | `pg_get_viewdef('name')`                                    |
| `SHOW CREATE TABLE name`                                     | STR database (schema check)             | `pg_catalog` queries                                        |
| `SHOW FULL TABLES`                                           | Sysadmin pivot routes                   | `information_schema.tables`                                 |
| `DESCRIBE table`                                             | Pivot service column introspection      | `information_schema.columns`                                |
| `INFORMATION_SCHEMA` with `TABLE_SCHEMA = DATABASE()`        | Multi-tenant migration scripts          | `information_schema` with `table_schema = current_schema()` |
| `SET @variable = ...` / `PREPARE` / `EXECUTE` / `DEALLOCATE` | Phase 1 migration scripts               | PL/pgSQL `DO $$ ... $$` blocks                              |

### 2.4 Connection & Driver

| MySQL                                         | PostgreSQL                                   |
| --------------------------------------------- | -------------------------------------------- |
| `mysql-connector-python`                      | `psycopg2` or `psycopg3`                     |
| `mysql.connector.pooling.MySQLConnectionPool` | `psycopg_pool.ConnectionPool` or `pgbouncer` |
| `mysql.connector.Error`                       | `psycopg2.Error`                             |
| `%s` parameter placeholders                   | `%s` (same with psycopg2) ✅                 |
| `cursor(dictionary=True)`                     | `psycopg2.extras.RealDictCursor`             |

---

## 3. Advantages of Migrating to PostgreSQL

### 3.1 Superior JSON Support

PostgreSQL's `jsonb` type is significantly more powerful than MySQL's JSON:

- Native operators (`->`, `->>`, `@>`, `?`, `#>`) are more concise than `JSON_EXTRACT`/`JSON_UNQUOTE`
- GIN indexes on JSONB columns for fast lookups — myAdmin's `rekeningschema.parameters` column would benefit greatly
- `jsonb_set`, `jsonb_build_object`, `jsonb_agg` are more composable
- **Impact for myAdmin:** The chart of accounts and parameter system rely heavily on JSON queries. PostgreSQL would make these faster and cleaner.

### 3.2 Better Analytical Query Performance

- Window functions are more mature and performant
- CTEs (WITH queries) are better optimized
- Partial indexes (e.g., `CREATE INDEX ... WHERE status = 'active'`) reduce index size
- **Impact for myAdmin:** P&L reports, balance sheets, and pivot queries would benefit from better query planning.

### 3.3 Advanced Data Types

- `NUMERIC` with arbitrary precision (better for financial data than `DECIMAL(10,2)`)
- Native `UUID` type
- `ARRAY` types (could simplify multi-value columns)
- `DATERANGE`, `TSRANGE` for booking date ranges in STR module
- **Impact for myAdmin:** Financial calculations get better precision; STR bookings could use range types for overlap detection.

### 3.4 Stronger Data Integrity

- Deferred constraints (check FK at commit, not at statement)
- Exclusion constraints (prevent overlapping date ranges — perfect for STR bookings)
- Transactional DDL (schema changes can be rolled back)
- **Impact for myAdmin:** Safer migrations, better booking conflict detection.

### 3.5 Better Concurrency (MVCC)

- PostgreSQL's MVCC is more mature — readers never block writers
- No table-level locking issues that MySQL/InnoDB can exhibit under high contention
- **Impact for myAdmin:** The `ScalabilityManager` with 50+ connections would see fewer lock contention issues.

### 3.6 Ecosystem & Hosting

- First-class support on Railway (already used for production), AWS RDS, Supabase, Neon, Render
- Better tooling ecosystem (pgAdmin, DBeaver, psql)
- More active open-source community and faster feature development
- **Impact for myAdmin:** More hosting options, potentially lower cost.

### 3.7 Full-Text Search

- Built-in `tsvector`/`tsquery` for full-text search without external tools
- **Impact for myAdmin:** Could enable searching across invoice descriptions, transaction notes without LIKE queries.

---

## 4. Disadvantages / Risks of Migrating

### 4.1 Massive Code Change Surface (HIGH RISK)

This is the single biggest concern:

- **~45 Python files** import `mysql.connector` directly
- **No ORM or abstraction layer** — every SQL query is hand-written
- **50+ migration/setup scripts** contain MySQL-specific SQL
- **15+ views** with MySQL-specific syntax (backticks, functions)
- **All DDL scripts** use MySQL syntax (`ENGINE=InnoDB`, `AUTO_INCREMENT`, etc.)

**Estimated files requiring changes:** 80–100+ files across backend source, scripts, tests, and SQL files.

### 4.2 JSON Syntax Rewrite (MEDIUM-HIGH RISK)

The `rekeningschema.parameters` JSON column is queried extensively:

- `JSON_EXTRACT(parameters, '$.bank_account')` → `parameters->>'bank_account'`
- `JSON_SET(COALESCE(parameters, '{}'), '$.flag', value)` → `jsonb_set(COALESCE(parameters, '{}'), '{flag}', value)`
- `JSON_UNQUOTE(JSON_EXTRACT(...))` → `parameters->>'key'`

These patterns appear in **chart_of_accounts_routes.py**, **backfill_rekeningschema_flags.py**, **database.py**, and tests. Each must be rewritten and tested.

### 4.3 ON UPDATE CURRENT_TIMESTAMP (MEDIUM RISK)

MySQL's `ON UPDATE CURRENT_TIMESTAMP` is used on ~10 tables for `updated_at` columns. PostgreSQL requires a trigger function:

```sql
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Per table:
CREATE TRIGGER set_updated_at BEFORE UPDATE ON table_name
FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

This adds maintenance overhead for every table with `updated_at`.

### 4.4 ENUM Type Differences (LOW-MEDIUM RISK)

MySQL `ENUM` is inline in column definition. PostgreSQL requires separate type creation:

```sql
CREATE TYPE invoice_status AS ENUM ('draft', 'sent', 'paid', 'overdue', 'cancelled', 'credited');
```

Adding values to PostgreSQL ENUMs requires `ALTER TYPE ... ADD VALUE` (cannot remove values without recreating).

### 4.5 View Migration Complexity (MEDIUM RISK)

- 15+ views use backtick quoting, MySQL functions (`YEAR()`, `IFNULL()`)
- Scripts that inspect views via `SHOW CREATE VIEW` need rewriting
- The `flatten_view_chain.py` script parses MySQL view definitions — needs complete rewrite

### 4.6 Data Migration Risk (HIGH RISK)

- Production data in MySQL needs to be migrated with zero data loss
- Date formats, character encoding, JSON data must transfer correctly
- The `mutaties` table has 250K+ rows of financial data — any corruption is unacceptable
- Need parallel-run period to validate data integrity

### 4.7 Test Suite Disruption (MEDIUM RISK)

- Tests mock `mysql.connector.Error`, `mysql.connector.connect`
- Test fixtures create MySQL-specific schemas
- `setup_test_database.py` uses `SHOW CREATE VIEW` to copy views
- All test infrastructure needs updating

### 4.8 No Immediate Business Value (STRATEGIC RISK)

- MySQL 8.0 is working correctly for current needs
- No reported performance issues that PostgreSQL would solve
- Migration effort doesn't deliver new features to users
- Development time diverted from feature work

### 4.9 Backup & Operations Changes

- Current backup uses `mysqldump` — needs to switch to `pg_dump`
- Docker image changes from `mysql:8.0` to `postgres:16`
- `my.cnf` configuration doesn't apply — need `postgresql.conf` tuning
- Monitoring queries and health checks need updating

---

## 5. Effort Estimation

| Phase                            | Scope                                                                    | Estimated Effort            |
| -------------------------------- | ------------------------------------------------------------------------ | --------------------------- |
| **Phase 0: Abstraction layer**   | Introduce DB abstraction in `database.py` to isolate MySQL-specific code | 3–5 days                    |
| **Phase 1: Schema conversion**   | Convert all DDL (tables, views, indexes, triggers)                       | 3–4 days                    |
| **Phase 2: Query conversion**    | Rewrite MySQL-specific SQL in Python files (~45 files)                   | 5–8 days                    |
| **Phase 3: Script conversion**   | Update migration/setup/analysis scripts (~50 files)                      | 3–5 days                    |
| **Phase 4: Test conversion**     | Update test fixtures, mocks, and assertions                              | 2–3 days                    |
| **Phase 5: Infrastructure**      | Docker Compose, Railway config, backup scripts                           | 1–2 days                    |
| **Phase 6: Data migration**      | ETL pipeline, validation, parallel-run                                   | 3–5 days                    |
| **Phase 7: Integration testing** | End-to-end validation of all modules                                     | 3–5 days                    |
| **Total**                        |                                                                          | **23–37 days** (~5–8 weeks) |

---

## 6. Alternative: Introduce an Abstraction Layer First

Instead of a full migration, a phased approach reduces risk:

### Step 1 — Database Abstraction Layer (regardless of migration decision)

Refactor `database.py` to provide a dialect-agnostic interface:

- Centralize all `mysql.connector` imports into `database.py`
- Remove direct `mysql.connector` imports from the ~45 other files
- Abstract connection pooling behind a common interface
- Create SQL dialect helpers for JSON, date functions, identifier quoting

**Benefit:** Even without migrating, this improves code quality and makes a future migration 60–70% easier.

### Step 2 — Evaluate After Abstraction

Once the abstraction layer is in place, the actual database swap becomes a configuration change + schema conversion, rather than a codebase-wide rewrite.

---

## 7. Recommendation

### Short-term: Do NOT migrate now

The current MySQL 8.0 setup is functional, and the migration carries significant risk for a codebase with no ORM and 45+ files with direct MySQL imports. The effort (5–8 weeks) would halt feature development with no immediate user-facing benefit.

### Medium-term: Introduce abstraction layer (Phase 0)

This is valuable regardless of the migration decision:

1. Centralize all database access through `DatabaseManager`
2. Eliminate direct `mysql.connector` imports outside `database.py`
3. Create SQL dialect helpers for JSON operations, date functions
4. This is a ~1 week investment that pays off in maintainability

### Long-term: Migrate when there's a forcing function

Good triggers for migration:

- Moving to a managed database service that favors PostgreSQL (e.g., Supabase, Neon)
- Hitting MySQL limitations with JSON queries or analytical workloads
- Need for PostgreSQL-specific features (range types for STR bookings, exclusion constraints)
- Railway pricing/support changes favoring PostgreSQL

---

## 8. Decision Matrix

| Factor                    | Stay MySQL                      | Migrate PostgreSQL       |
| ------------------------- | ------------------------------- | ------------------------ |
| Development effort        | ✅ Zero                         | ❌ 5–8 weeks             |
| Risk to production data   | ✅ None                         | ❌ High (financial data) |
| JSON query performance    | ⚠️ Adequate                     | ✅ Superior              |
| Analytical queries        | ⚠️ Good                         | ✅ Better                |
| Financial precision       | ⚠️ DECIMAL(10,2)                | ✅ NUMERIC arbitrary     |
| Hosting flexibility       | ⚠️ Good                         | ✅ Excellent             |
| Feature development pace  | ✅ Uninterrupted                | ❌ Blocked 5–8 weeks     |
| Long-term maintainability | ⚠️ OK with abstraction          | ✅ Better ecosystem      |
| STR booking conflicts     | ⚠️ Application-level            | ✅ Exclusion constraints |
| Code quality improvement  | ⚠️ Needs abstraction either way | ✅ Forces cleanup        |

**Bottom line:** The abstraction layer (Phase 0) is the right next step. It delivers value now and keeps the PostgreSQL door open for when there's a genuine business need.

---

## 9. Database Call Distribution Analysis

Measured on 2026-04-29 by scanning all `.py` files across the project.

### 9.1 Through the Abstraction Layer (`db.execute_query()` / `db.execute_batch_queries()`)

| Location                                   | Calls    |
| ------------------------------------------ | -------- |
| `backend/src/` (core application code)     | **415**  |
| `backend/scripts/` (migrations, utilities) | ~300     |
| `backend/tests/`                           | ~100     |
| Root `scripts/`                            | 38       |
| `execute_batch_queries()` calls            | 2        |
| **Total abstraction layer calls**          | **~857** |

### 9.2 Bypassing the Abstraction (`cursor.execute()` directly)

| Location                                   | Calls    |
| ------------------------------------------ | -------- |
| `backend/src/` (core application code)     | **134**  |
| `backend/scripts/` (migrations, utilities) | 145      |
| `backend/tests/`                           | 21       |
| Root `scripts/`                            | ~67      |
| **Total direct cursor calls**              | **~367** |

### 9.3 Completely Outside DatabaseManager (`mysql.connector.connect()` directly)

| Location                       | Calls   |
| ------------------------------ | ------- |
| `backend/src/`                 | 7       |
| `backend/scripts/`             | ~25     |
| `backend/tests/`               | ~5      |
| Root `scripts/`                | ~7      |
| **Total direct connect calls** | **~44** |

### 9.4 Summary

| Access Pattern                             | Call Count | % of Total |
| ------------------------------------------ | ---------- | ---------- |
| `db.execute_query()` — through abstraction | **857**    | **70%**    |
| `cursor.execute()` — bypasses abstraction  | **367**    | **30%**    |
| **Total database calls**                   | **~1,224** | 100%       |

### 9.5 Key Observations

1. **70% of database calls** already go through the `DatabaseManager.execute_query()` abstraction — this is the good news.
2. **30% (367 calls)** bypass the abstraction by getting a raw connection via `db.get_connection()` or `mysql.connector.connect()` and using `cursor.execute()` directly.
3. **Worst offenders for bypassing the abstraction:**
   - `backend/scripts/` — 145 direct cursor calls (migration and utility scripts)
   - `backend/src/` — 134 direct cursor calls in core app code (`transaction_logic.py`, `str_database.py`, `xlsx_export.py`, `missing_invoices_routes.py`)
   - 44 places create their own `mysql.connector.connect()` entirely outside `DatabaseManager`
4. **The 134 direct cursor calls in `backend/src/`** are the most critical to consolidate — these are production code paths that would all break on a database switch.
5. **Scripts and tests** (233 direct calls) are lower priority but still need conversion for a full migration.

### 9.6 Implication for Migration Strategy

The 70/30 split reinforces the Phase 0 recommendation: consolidating the remaining 367 direct calls through `DatabaseManager` is a prerequisite for any database migration. Without this, a PostgreSQL switch would require touching every one of those 367 call sites individually, plus the 857 that already go through the abstraction (for SQL dialect changes). With the abstraction layer complete, only `database.py` and the SQL dialect helpers need to change for the actual database swap.
