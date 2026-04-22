# MySQL Connection Pool Exhaustion Issue

## Problem

Frontend MySQL clients (HeidiSQL, MySQL Workbench) cannot connect to the database. MySQL is unresponsive to external connection attempts.

## Root Cause

The backend application is executing extremely slow queries that consume all 151 available MySQL connections and hold them open for 400+ seconds:

- Query: `SELECT DISTINCT administration FROM vw_mutaties WHERE administration IS NOT NULL AND ...`
- Query: `SELECT COUNT(*) as total FROM mutaties WHERE YEAR(TransactionDate) ...`

These queries are stuck in "converting HEAP to ondisk", "executing", and "Opening tables" states, preventing new connections from being established.

## Impact

- No external database connections possible (tools like HeidiSQL, MySQL Workbench timeout)
- Connection pool exhaustion after ~15 minutes of backend activity
- System becomes unresponsive to client queries

## Required Action

**Optimize the queries on `vw_mutaties` and `mutaties` tables:**

1. Add indexes on `TransactionDate` and `administration` columns
2. Review and optimize the view definition for `vw_mutaties` (likely missing proper indexes or inefficient joins)
3. Add query execution timeouts to prevent long-running queries from holding connections
4. Implement connection pooling best practices (set `pool_recycle`, adjust pool size limits, add connection timeouts)

## Database Details

- Table: `vw_mutaties` (view), `mutaties` (table)
- Affected columns: `administration`, `TransactionDate`
- Database: `finance`
- Current max_connections: 151
- Current active slow queries: 25+ running 400+ seconds each
