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

- Tenant isolation: every tenant query filters by tenant from `@tenant_required()`
- Parameterized queries: always `%s` placeholders, never f-string interpolation
- Tables: `snake_case`, views: `vw_` prefix, FKs: `{table}_id`
- Environments: local Docker (dev), Railway (production) — database config comes from env vars, never hardcode
