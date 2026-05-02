---
inclusion: fileMatch
fileMatchPattern: "backend/**/*.py"
---

# Database Patterns

## Abstraction Layer

All database access goes through `DatabaseManager`, `dialect_helpers`, and `db_exceptions`. No file outside `database.py` and `scalability_manager.py` may import `mysql.connector`.

```python
from database import DatabaseManager
from dialect_helpers import dialect
from db_exceptions import DatabaseError, IntegrityError, ConnectionError, OperationalError
```

## DatabaseManager

```python
db.execute_query(query, params, fetch=True)                          # read
db.execute_query(query, params, fetch=False, commit=True)            # write
db.execute_batch_queries([(q1, p1), (q2, p2)], commit=True)         # batch
db.execute_ddl("ALTER TABLE ...")                                     # DDL
with db.transaction() as (cursor, conn):                              # multi-statement
    cursor.execute(...)
with db.get_cursor() as (cursor, conn):                               # raw cursor
    cursor.executemany(...)
    conn.commit()
```

## Dialect Helpers

Use `dialect` instead of raw MySQL syntax. Key methods: `json_extract`, `json_unquote_extract`, `json_set`, `json_contains`, `year`, `month`, `quarter`, `current_date`, `current_timestamp`, `date_subtract`, `date_add`, `date_diff`, `date_format`, `str_to_date`, `ifnull`, `quote_identifier`, `describe_table`, `get_view_definition`, `list_tables`.

## Exceptions

Catch `DatabaseError` (base), `IntegrityError`, `ConnectionError`, `OperationalError` — never `mysql.connector.Error`. All carry `error_code`, `original_error`, `__cause__`.

## Reference

Full spec: #[[file:.kiro/specs/database-abstraction-layer/design.md]]

## Core Rules

- Parameterized queries: always `%s` placeholders, never f-string interpolation
- Tables: `snake_case`, views: `vw_` prefix, FKs: `{table}_id`
- Environments: local Docker (dev), Railway (production) — database config comes from env vars, never hardcode

## Tenant Isolation (REQ13 — Defense in Depth)

Every tenant-scoped table and view must support direct tenant filtering without JOINs.

### Table Creation Checklist

When creating a new table that holds tenant data:

1. **Add `administration VARCHAR(50) NOT NULL`** — no exceptions, even for child tables
2. **Add `INDEX idx_administration (administration)`** — enables standalone tenant queries
3. **Add a composite index** for the primary query pattern (e.g., `idx_admin_parent (administration, parent_id)`)
4. **Do NOT rely on parent FKs for tenant scope** — a child table like `invoice_lines` must have its own `administration` column, not inherit it via JOIN to `invoices`

### Query Rules

- Every SELECT, UPDATE, DELETE on a tenant-scoped table must include `WHERE ... administration = %s`
- The `administration` value comes from `@tenant_required()` — passed as `tenant` parameter through the service layer
- INSERT statements must include the `administration` value explicitly

### View Rules

- Views over tenant-scoped tables must include `administration` in the SELECT list and GROUP BY clause
- This allows consumers to filter by `WHERE administration = %s` directly on the view

### Why Child Tables Need Their Own Column

Relying on JOINs to parent tables for tenant filtering creates two risks:

- **Performance**: every child query requires a JOIN just for access control
- **Security**: if a developer forgets the JOIN, the query returns cross-tenant data

The `administration` column on child tables is intentional denormalization for defense-in-depth. The application layer must ensure the child's `administration` matches the parent's.

### Exceptions

These table types do NOT need `administration`:

- Generic/reference tables (e.g., `countries`, `database_migrations`)
- System tables only accessible to SysAdmin
- Tables explicitly documented as tenant-agnostic
