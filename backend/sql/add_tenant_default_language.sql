-- Add default_language column to tenants table for i18n support
-- This allows Tenant Admins to set a default language for their tenant
-- New users will inherit this language preference
-- ============================================================================
-- Add default_language column
ALTER TABLE tenants
ADD COLUMN default_language VARCHAR(5) DEFAULT 'nl'
AFTER display_name;
-- Add index for performance
CREATE INDEX idx_tenants_default_language ON tenants(default_language);
-- Update existing tenants to Dutch (current default)
UPDATE tenants
SET default_language = 'nl'
WHERE default_language IS NULL;
-- Verify the change
SELECT administration,
    display_name,
    default_language,
    status
FROM tenants
ORDER BY administration;