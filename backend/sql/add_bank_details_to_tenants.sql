-- Add bank details columns to tenants table
-- For Tenant Admin to manage their own banking information
-- ============================================================================
ALTER TABLE tenants
ADD COLUMN bank_account_number VARCHAR(50)
AFTER country,
    ADD COLUMN bank_name VARCHAR(255)
AFTER bank_account_number;
-- Verify
DESCRIBE tenants;