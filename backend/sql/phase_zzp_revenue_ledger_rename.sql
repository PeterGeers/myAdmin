-- Migration: Rename zzp_invoice_ledger to zzp_revenue_ledger in rekeningschema.parameters
-- 
-- Context: zzp_invoice_ledger was incorrectly used for revenue account selection.
-- It is now repurposed as the ZZP invoice bank account (IBAN for client payment).
-- A new zzp_revenue_ledger flag is introduced for revenue booking accounts.
--
-- This migration moves the existing zzp_invoice_ledger flags on revenue accounts
-- (8xxx range) to zzp_revenue_ledger, and removes zzp_invoice_ledger from those accounts.
-- Bank accounts that had zzp_invoice_ledger set incorrectly are also cleaned up.
-- Step 1: Copy zzp_invoice_ledger to zzp_revenue_ledger on revenue accounts (8xxx)
UPDATE rekeningschema
SET parameters = JSON_SET(parameters, '$.zzp_revenue_ledger', true)
WHERE JSON_EXTRACT(parameters, '$.zzp_invoice_ledger') = true
    AND Account LIKE '8%';
-- Step 2: Remove zzp_invoice_ledger from revenue accounts (8xxx) — it's not a bank account flag
UPDATE rekeningschema
SET parameters = JSON_REMOVE(parameters, '$.zzp_invoice_ledger')
WHERE JSON_EXTRACT(parameters, '$.zzp_invoice_ledger') = true
    AND Account LIKE '8%';
-- Step 3: Remove zzp_invoice_ledger from non-bank accounts that were incorrectly flagged
-- (accounts that have zzp_invoice_ledger but NOT bank_account)
UPDATE rekeningschema
SET parameters = JSON_REMOVE(parameters, '$.zzp_invoice_ledger')
WHERE JSON_EXTRACT(parameters, '$.zzp_invoice_ledger') = true
    AND (
        JSON_EXTRACT(parameters, '$.bank_account') IS NULL
        OR JSON_EXTRACT(parameters, '$.bank_account') = false
    );
-- Verification queries (run manually):
-- SELECT Account, AccountName, parameters FROM rekeningschema WHERE JSON_EXTRACT(parameters, '$.zzp_revenue_ledger') = true;
-- SELECT Account, AccountName, parameters FROM rekeningschema WHERE JSON_EXTRACT(parameters, '$.zzp_invoice_ledger') = true;