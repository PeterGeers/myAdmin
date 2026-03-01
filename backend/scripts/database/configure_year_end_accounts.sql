-- Configure Year-End Closure Account Roles
-- This script sets up the required account roles for year-end closure feature
-- Configure interim opening balance account (2001) for all tenants
UPDATE rekeningschema
SET parameters = JSON_OBJECT('roles', JSON_ARRAY('interim_opening_balance'))
WHERE Account = '2001';
-- Configure equity result account (3080) for GoodwinSolutions
UPDATE rekeningschema
SET parameters = JSON_OBJECT('roles', JSON_ARRAY('equity_result'))
WHERE Account = '3080'
    AND administration = 'GoodwinSolutions';
-- Configure P&L closing account (8099) for all tenants
UPDATE rekeningschema
SET parameters = JSON_OBJECT('roles', JSON_ARRAY('pl_closing'))
WHERE Account = '8099';
-- Verify configuration
SELECT administration,
    Account,
    AccountName,
    parameters
FROM rekeningschema
WHERE Account IN ('2001', '3080', '8099')
ORDER BY administration,
    Account;