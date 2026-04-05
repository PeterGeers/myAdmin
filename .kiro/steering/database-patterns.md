---
inclusion: fileMatch
fileMatchPattern: "backend/src/**/*.py"
---

# Database Patterns

## Tenant Isolation

Every query that touches tenant data MUST include tenant filtering:

```python
query = "SELECT * FROM mutaties WHERE tenant_id = %s AND ..."
params = (tenant_id, ...)
result = db.execute_query(query, params)
```

Never trust client-provided tenant IDs — always use the tenant from `@tenant_required()` decorator context.

## Parameterized Queries

Always use `%s` placeholders, never string interpolation:

```python
# CORRECT
query = "SELECT * FROM mutaties WHERE ref1 = %s AND amount = %s"
db.execute_query(query, (ref1, amount))

# WRONG — SQL injection risk
query = f"SELECT * FROM mutaties WHERE ref1 = '{ref1}'"
```

## DatabaseManager Usage

```python
# Single query
result = db.execute_query(query, params, fetch=True)

# Write operation
db.execute_query(insert_query, params, fetch=False, commit=True)

# Batch operations
db.execute_batch_queries([(query1, params1), (query2, params2)], commit=True)
```

## Naming Conventions

- Tables: `snake_case`, descriptive (e.g., `mutaties`, `bnb`, `pricing_recommendations`)
- Columns: `snake_case` (e.g., `created_at`, `tenant_id`, `transaction_date`)
- Foreign keys: `{table_singular}_id` (e.g., `tenant_id`, `listing_id`)
- Views: `vw_` prefix (e.g., `vw_mutaties`)

## Key Tables

- `mutaties` — financial transactions
- `bnb` — realized BNB bookings
- `bnbplanned` — planned bookings
- `bnbfuture` — future revenue
- `listings` — property listings
- `tenants` — tenant configuration
- `audit_log` — audit trail

## Test Mode

The project uses `test_mode` flag to switch databases:

- Production: `DB_NAME` from env
- Test: `TEST_DB_NAME` from env

Services receive `test_mode` via `set_test_mode()` — never hardcode database names.
