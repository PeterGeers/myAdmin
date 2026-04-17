-- ============================================================================
-- ZZP Module: Add revenue_account column to invoices table
-- Allows per-invoice revenue ledger selection (Req 18, Design §14.3)
-- ============================================================================
-- Add revenue_account column after exchange_rate
-- Stores the selected revenue ledger account code (e.g., '8001', '8010')
-- NULL means use the tenant's default zzp.revenue_account parameter
ALTER TABLE invoices
ADD COLUMN revenue_account VARCHAR(10) DEFAULT NULL
AFTER exchange_rate;
-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT 'revenue_account column added to invoices' AS status;
SELECT COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'invoices'
    AND COLUMN_NAME = 'revenue_account';