-- Seed tenant-scope default parameters for table configuration (ui.tables)
-- Used by useTableConfig hook for ChartOfAccounts, ParameterManagement, BankingProcessor
--
-- Reference: .kiro/specs/table-filter-framework-v2/design.md §5 (Parameter Seed Data)
-- Requirements: 6.7
--
-- Idempotent: ON DUPLICATE KEY UPDATE ensures re-running is safe.
-- Self-contained: discovers all active tenants and seeds all 12 parameters per tenant.
--
-- USAGE: Just run this script — no variables to set.
--   mysql -u <user> -p <database> < seed_table_config_params.sql
--   Or: SOURCE seed_table_config_params.sql;
-- Clean up any old system-scope rows from previous seed version
DELETE FROM parameters
WHERE scope = 'system'
    AND namespace = 'ui.tables';
-- Seed all active tenants in one pass using INSERT ... SELECT
-- Each INSERT creates 4 parameters for one table entity × all tenants
-- ============================================================================
-- ChartOfAccounts table config (4 params × all tenants)
-- ============================================================================
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'chart_of_accounts.columns',
    '["Account","AccountName","AccountLookup","SubParent","Parent","VW","Belastingaangifte","parameters"]',
    'json',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'chart_of_accounts.filterable_columns',
    '["Account","AccountName","AccountLookup","SubParent","Parent","VW","Belastingaangifte","parameters"]',
    'json',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'chart_of_accounts.default_sort',
    '{"field":"Account","direction":"asc"}',
    'json',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'chart_of_accounts.page_size',
    '1000',
    'number',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
-- ============================================================================
-- ParameterManagement table config (4 params × all tenants)
-- ============================================================================
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'parameters.columns',
    '["namespace","key","value","value_type","scope_origin"]',
    'json',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'parameters.filterable_columns',
    '["namespace","key","value","value_type","scope_origin"]',
    'json',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'parameters.default_sort',
    '{"field":"namespace","direction":"asc"}',
    'json',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'parameters.page_size',
    '100',
    'number',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
-- ============================================================================
-- BankingProcessor mutaties tab config (4 params × all tenants)
-- ============================================================================
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'banking_mutaties.columns',
    '["ID","TransactionNumber","TransactionDate","TransactionDescription","TransactionAmount","Debet","Credit","ReferenceNumber","Ref1","Ref2","Ref3","Ref4","Administration"]',
    'json',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'banking_mutaties.filterable_columns',
    '["ID","TransactionNumber","TransactionDate","TransactionDescription","TransactionAmount","Debet","Credit","ReferenceNumber","Ref1","Ref2","Ref3","Ref4","Administration"]',
    'json',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'banking_mutaties.default_sort',
    '{"field":"TransactionDate","direction":"desc"}',
    'json',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
INSERT INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT 'tenant',
    t.administration,
    'ui.tables',
    'banking_mutaties.page_size',
    '100',
    'number',
    FALSE,
    'system'
FROM tenants t
WHERE t.status = 'active' ON DUPLICATE KEY
UPDATE value =
VALUES(value);
-- ============================================================================
-- Verification: count parameters per tenant (expect 12 each)
-- ============================================================================
SELECT p.scope_id AS tenant,
    COUNT(*) AS param_count
FROM parameters p
WHERE p.scope = 'tenant'
    AND p.namespace = 'ui.tables'
GROUP BY p.scope_id
ORDER BY p.scope_id;