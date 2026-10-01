# Bugfix Requirements Document

## Introduction

Since commit `8631168 fix(db): make scalability manager pool config connector-legal`, every data view in the myAdmin frontend renders empty and the underlying data endpoints return HTTP 500. Login succeeds and the menu renders, but for example `GET /api/banking/filter-options` fails with a 500.

The root cause has been confirmed by reproduction against the Railway `finance` database. Commit `8631168` made the scalability manager's pool config connector-legal (`db_pool_size` 50→20, dropped the invalid `pool_recycle` kwarg). Before that commit the scalability manager FAILED to initialize (its invalid pool config raised), so `DatabaseManager` silently fell back to the legacy pool, which returns a RAW `mysql.connector` connection. After `8631168` the scalability manager INITIALIZES SUCCESSFULLY, and that changes what `DatabaseManager.get_connection()` returns.

`DatabaseManager.get_connection()` (`backend/src/database.py`, line ~109) now calls `scalability_manager.get_database_connection()`, which returns `connection_pool.get_connection(pool_type)`. `AdvancedConnectionPool.get_connection` (`backend/src/scalability_manager.py`, line ~196) is decorated `@contextmanager`, so calling it WITHOUT entering the `with` block returns a `_GeneratorContextManager` object, NOT a connection.

Every caller using the raw pattern therefore breaks:

```python
conn = db.get_connection()
cursor = conn.cursor(dictionary=True)   # AttributeError: '_GeneratorContextManager' object has no attribute 'cursor'
```

The route-level `except Exception` converts this `AttributeError` into an HTTP 500, so all affected data endpoints fail and the UI data views show nothing.

**Reproduction (confirmed):** Connecting via `backend/scripts/railway-db.sh` against the Railway `finance` DB, the scalability manager logged `🚀 Scalability Manager initialized successfully`, then `conn = db.get_connection(); conn.cursor(dictionary=True)` raised `AttributeError: '_GeneratorContextManager' object has no attribute 'cursor'`.

**Blast radius:** Many call sites use the raw `conn = db.get_connection(); conn.cursor(...)` pattern and are all affected, including `backend/src/routes/banking_routes.py`, `backend/src/bnb_routes.py` (7+ sites), `backend/src/str_invoice_routes.py`, `backend/src/str_channel_routes.py`, `backend/src/reporting_routes.py`, `backend/src/services/banking_mutatie_service.py`, `year_end_service.py`, `country_report_service.py`, `zzp_invoice_numbering.py`, `backend/src/banking_checks.py`, `banking_processor.py`, `pdf_validation.py`, `btw_processor.py`, `xlsx_export.py`, `business_pricing_model.py`, `hybrid_pricing_optimizer.py`, `report_generators/financial_report_generator.py`, and `pdf_decision_helpers.py`. Routes that instead use the `with db.get_cursor()` / `with db.transaction()` context-manager API are NOT affected.

## Bug Analysis

### Current Behavior (Defect)

What currently happens when the scalability manager is active (post-commit `8631168`) and a caller uses the raw connection pattern.

1.1 WHEN the scalability manager is initialized and a caller invokes `conn = db.get_connection()` THEN the system returns a `_GeneratorContextManager` object instead of a raw database connection

1.2 WHEN a caller then invokes `conn.cursor(dictionary=True)` on that returned object THEN the system raises `AttributeError: '_GeneratorContextManager' object has no attribute 'cursor'`

1.3 WHEN a request hits an endpoint that uses the raw pattern (e.g. `GET /api/banking/filter-options` in `banking_filter_options`) THEN the route's `except Exception` catches the `AttributeError` and the system returns HTTP 500 with `{"success": false, "error": "..."}`

1.4 WHEN the frontend loads any data view backed by an affected endpoint THEN the system renders the view empty because the underlying request returned 500

### Expected Behavior (Correct)

What should happen instead, for the same conditions.

2.1 WHEN the scalability manager is initialized and a caller invokes `conn = db.get_connection()` THEN the system SHALL return a usable raw connection that supports `.cursor()` and `.close()`, regardless of which pool backs it

2.2 WHEN a caller invokes `conn.cursor(dictionary=True)` on the returned object THEN the system SHALL return a working cursor without raising `AttributeError`

2.3 WHEN a request hits an endpoint that uses the raw pattern (e.g. `GET /api/banking/filter-options`) THEN the system SHALL return HTTP 200 with the expected data payload

2.4 WHEN the frontend loads a data view backed by an affected endpoint THEN the system SHALL render the view populated with data

### Unchanged Behavior (Regression Prevention)

Existing behavior that must be preserved by the fix.

3.1 WHEN a route uses the `with db.get_cursor()` context-manager API THEN the system SHALL CONTINUE TO yield a `(cursor, conn)` pair and work as before

3.2 WHEN a route uses the `with db.transaction()` context-manager API THEN the system SHALL CONTINUE TO commit on success and roll back on exception as before

3.3 WHEN the scalability manager is unavailable and the legacy pool is used THEN the system SHALL CONTINUE TO return a raw `mysql.connector` connection from `get_connection()`

3.4 WHEN both the scalability manager and legacy pool are unavailable THEN the system SHALL CONTINUE TO return a raw connection via the direct `mysql.connector.connect(**self.config)` fallback

3.5 WHEN the scalability manager initializes THEN the system SHALL CONTINUE TO use the connector-legal pool config from commits `7862ae6` and `8631168` (no invalid `pool_recycle` kwarg; `pool_size` within the mysql-connector 32 cap) — these fixes SHALL NOT be reverted

3.6 WHEN an affected endpoint returns data THEN the system SHALL CONTINUE TO apply the same tenant/administration filtering as before the fix

## Bug Condition Derivation

**Bug Condition Function** — identifies inputs that trigger the bug:

```pascal
FUNCTION isBugCondition(X)
  INPUT: X = a call to DatabaseManager.get_connection(pool_type)
  OUTPUT: boolean

  // True when the scalability manager is active, because get_connection()
  // then returns a @contextmanager object instead of a raw connection.
  RETURN scalabilityManagerInitialized() = true
         AND callerUsesRawPattern(X)   // caller does conn.cursor()/conn.close() directly
END FUNCTION
```

**Property Specification** — correct behavior for buggy inputs:

```pascal
// Property: Fix Checking - get_connection() returns a usable raw connection
FOR ALL X WHERE isBugCondition(X) DO
  conn ← DatabaseManager.get_connection'(X.pool_type)
  ASSERT hasAttribute(conn, "cursor") AND hasAttribute(conn, "close")
  ASSERT no_AttributeError(conn.cursor(dictionary := true))
END FOR
```

**Preservation Goal** — for all non-buggy inputs, fixed behaves identically to original:

```pascal
// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)   // get_cursor/transaction context managers, legacy + direct
                        // fallbacks, and pool-config fixes all unchanged
END FOR
```

**Key Definitions:**
- **F**: `DatabaseManager.get_connection` (and the get_cursor/transaction paths) before the fix
- **F'**: The same after the fix
- **C(X)**: scalability manager active AND caller uses the raw `conn.cursor()` pattern
- **Counterexample (confirmed):** `conn = db.get_connection(); conn.cursor(dictionary=True)` raises `AttributeError: '_GeneratorContextManager' object has no attribute 'cursor'`

_Note: two candidate fix directions to explore in the design phase — (A) normalize `get_connection()` at the boundary so it always returns a raw connection (smallest blast radius, one place); (B) migrate raw-pattern callers to the `with db.get_cursor()` API (large, many files). The exact approach is left to design._
