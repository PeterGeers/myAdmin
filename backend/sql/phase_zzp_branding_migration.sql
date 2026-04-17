-- Phase ZZP: Branding Parameter Migration
-- Migrates existing 'branding' namespace parameters to module-specific namespaces:
--   - 'zzp_branding' for tenants with ZZP module active
--   - 'str_branding' for tenants with STR module active
--
-- Requirements: 20.1, 20.2
-- Design: §14.11
--
-- The parameters table uses (scope, scope_id, namespace, key) as the logical key.
-- Tenant-level parameters have scope='tenant' and scope_id=<administration>.
-- This migration copies rows, preserving scope, scope_id, value, value_type, and is_secret.
--
-- Run AFTER the code changes that rename branding → str_branding / zzp_branding
-- in parameter_schema.py, pdf_generator_service.py, and str_invoice_generator.py.
--
-- Safe to run multiple times: uses INSERT IGNORE to skip already-migrated rows.
-- ============================================================================
-- Step 1: Copy branding.* → zzp_branding.* for tenants with active ZZP module
-- ============================================================================
INSERT IGNORE INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT p.scope,
    p.scope_id,
    'zzp_branding' AS namespace,
    p.`key`,
    p.value,
    p.value_type,
    p.is_secret,
    'branding_migration' AS created_by
FROM parameters p
    INNER JOIN tenant_modules tm ON p.scope_id = tm.administration
    AND tm.module_name = 'ZZP'
    AND tm.is_active = TRUE
WHERE p.namespace = 'branding'
    AND p.scope = 'tenant';
-- ============================================================================
-- Step 2: Copy branding.* → str_branding.* for tenants with active STR module
-- ============================================================================
INSERT IGNORE INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT p.scope,
    p.scope_id,
    'str_branding' AS namespace,
    p.`key`,
    p.value,
    p.value_type,
    p.is_secret,
    'branding_migration' AS created_by
FROM parameters p
    INNER JOIN tenant_modules tm ON p.scope_id = tm.administration
    AND tm.module_name = 'STR'
    AND tm.is_active = TRUE
WHERE p.namespace = 'branding'
    AND p.scope = 'tenant';
-- ============================================================================
-- Step 3: Also copy system-scope branding params (if any) to both namespaces
-- System-scope params have scope='system' and scope_id='system'.
-- These serve as defaults for all tenants.
-- ============================================================================
INSERT IGNORE INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT p.scope,
    p.scope_id,
    'zzp_branding' AS namespace,
    p.`key`,
    p.value,
    p.value_type,
    p.is_secret,
    'branding_migration' AS created_by
FROM parameters p
WHERE p.namespace = 'branding'
    AND p.scope = 'system';
INSERT IGNORE INTO parameters (
        scope,
        scope_id,
        namespace,
        `key`,
        value,
        value_type,
        is_secret,
        created_by
    )
SELECT p.scope,
    p.scope_id,
    'str_branding' AS namespace,
    p.`key`,
    p.value,
    p.value_type,
    p.is_secret,
    'branding_migration' AS created_by
FROM parameters p
WHERE p.namespace = 'branding'
    AND p.scope = 'system';
-- ============================================================================
-- Verification: Check migrated rows before deleting old ones
-- ============================================================================
-- Run these queries to verify the migration was successful:
--
-- SELECT namespace, scope_id, COUNT(*) AS param_count
-- FROM parameters
-- WHERE namespace IN ('branding', 'zzp_branding', 'str_branding')
-- GROUP BY namespace, scope_id
-- ORDER BY scope_id, namespace;
-- ============================================================================
-- Step 4: Remove old branding namespace parameters
-- ONLY run after verifying Steps 1-3 completed successfully.
-- ============================================================================
-- DELETE FROM parameters WHERE namespace = 'branding';