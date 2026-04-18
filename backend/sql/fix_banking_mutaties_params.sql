-- Fix banking_mutaties parameter column names to match actual API field names
-- Run on Railway production database
--
-- Before: Amount, Account, CounterAccount, CounterName, Description, Reference, Category, Status, FileName, LedgerAccount
-- After:  TransactionDescription, TransactionAmount, Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4, Administration
UPDATE parameters
SET value = '["ID","TransactionNumber","TransactionDate","TransactionDescription","TransactionAmount","Debet","Credit","ReferenceNumber","Ref1","Ref2","Ref3","Ref4","Administration"]'
WHERE namespace = 'ui.tables'
    AND `key` = 'banking_mutaties.columns';
UPDATE parameters
SET value = '["ID","TransactionNumber","TransactionDate","TransactionDescription","TransactionAmount","Debet","Credit","ReferenceNumber","Ref1","Ref2","Ref3","Ref4","Administration"]'
WHERE namespace = 'ui.tables'
    AND `key` = 'banking_mutaties.filterable_columns';
-- Verify
SELECT scope_id,
    `key`,
    value
FROM parameters
WHERE namespace = 'ui.tables'
    AND `key` LIKE 'banking_mutaties%'
ORDER BY scope_id,
    `key`;