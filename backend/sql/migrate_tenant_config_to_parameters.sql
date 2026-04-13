-- Migration: tenant_config → parameters table
-- Run on Railway production database
-- Safe to run multiple times (INSERT ... ON DUPLICATE KEY UPDATE)
--
-- Maps tenant_config keys to parameters namespaces:
--   google_drive_*  → storage namespace
--   storage_*       → storage namespace (strip prefix)
--   company_logo_*  → branding namespace
--   all others      → config namespace
-- Google Drive keys → storage namespace
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
SELECT 'tenant' AS scope,
    tc.administration AS scope_id,
    'storage' AS namespace,
    tc.config_key AS `key`,
    CONCAT('"', REPLACE(tc.config_value, '"', '\\"'), '"') AS value,
    'string' AS value_type,
    tc.is_secret,
    'migration_r17' AS created_by
FROM tenant_config tc
WHERE tc.config_key LIKE 'google\_drive\_%' ON DUPLICATE KEY
UPDATE value =
VALUES(value),
    value_type =
VALUES(value_type),
    is_secret =
VALUES(is_secret),
    created_by =
VALUES(created_by);
-- storage_* keys → storage namespace (strip storage_ prefix)
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
SELECT 'tenant' AS scope,
    tc.administration AS scope_id,
    'storage' AS namespace,
    SUBSTRING(tc.config_key, 9) AS `key`,
    CONCAT('"', REPLACE(tc.config_value, '"', '\\"'), '"') AS value,
    'string' AS value_type,
    tc.is_secret,
    'migration_r17' AS created_by
FROM tenant_config tc
WHERE tc.config_key LIKE 'storage\_%' ON DUPLICATE KEY
UPDATE value =
VALUES(value),
    value_type =
VALUES(value_type),
    is_secret =
VALUES(is_secret),
    created_by =
VALUES(created_by);
-- company_logo_* keys → branding namespace
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
SELECT 'tenant' AS scope,
    tc.administration AS scope_id,
    'branding' AS namespace,
    tc.config_key AS `key`,
    CONCAT('"', REPLACE(tc.config_value, '"', '\\"'), '"') AS value,
    'string' AS value_type,
    tc.is_secret,
    'migration_r17' AS created_by
FROM tenant_config tc
WHERE tc.config_key LIKE 'company\_logo%' ON DUPLICATE KEY
UPDATE value =
VALUES(value),
    value_type =
VALUES(value_type),
    is_secret =
VALUES(is_secret),
    created_by =
VALUES(created_by);
-- All remaining keys → config namespace
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
SELECT 'tenant' AS scope,
    tc.administration AS scope_id,
    'config' AS namespace,
    tc.config_key AS `key`,
    CONCAT('"', REPLACE(tc.config_value, '"', '\\"'), '"') AS value,
    'string' AS value_type,
    tc.is_secret,
    'migration_r17' AS created_by
FROM tenant_config tc
WHERE tc.config_key NOT LIKE 'google\_drive\_%'
    AND tc.config_key NOT LIKE 'storage\_%'
    AND tc.config_key NOT LIKE 'company\_logo%' ON DUPLICATE KEY
UPDATE value =
VALUES(value),
    value_type =
VALUES(value_type),
    is_secret =
VALUES(is_secret),
    created_by =
VALUES(created_by);
-- Verify migration
SELECT 'tenant_config rows' AS source,
    COUNT(*) AS count
FROM tenant_config
UNION ALL
SELECT 'parameters (migrated)' AS source,
    COUNT(*) AS count
FROM parameters
WHERE created_by = 'migration_r17';