-- Update ReferenceNumber for existing year-end closure transactions
-- Run this script to add ReferenceNumber to historical closure records
-- Update OpeningBalance records
UPDATE mutaties
SET ReferenceNumber = 'Opening Balance'
WHERE TransactionNumber LIKE 'OpeningBalance%'
    AND (
        ReferenceNumber IS NULL
        OR ReferenceNumber = ''
    );
-- Update YearClose records
UPDATE mutaties
SET ReferenceNumber = 'Year Closure'
WHERE TransactionNumber LIKE 'YearClose%'
    AND (
        ReferenceNumber IS NULL
        OR ReferenceNumber = ''
    );
-- Verify the updates
SELECT 'OpeningBalance' as RecordType,
    COUNT(*) as TotalRecords,
    SUM(
        CASE
            WHEN ReferenceNumber = 'Opening Balance' THEN 1
            ELSE 0
        END
    ) as WithReferenceNumber,
    SUM(
        CASE
            WHEN ReferenceNumber IS NULL
            OR ReferenceNumber = '' THEN 1
            ELSE 0
        END
    ) as WithoutReferenceNumber
FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance%'
UNION ALL
SELECT 'YearClose' as RecordType,
    COUNT(*) as TotalRecords,
    SUM(
        CASE
            WHEN ReferenceNumber = 'Year Closure' THEN 1
            ELSE 0
        END
    ) as WithReferenceNumber,
    SUM(
        CASE
            WHEN ReferenceNumber IS NULL
            OR ReferenceNumber = '' THEN 1
            ELSE 0
        END
    ) as WithoutReferenceNumber
FROM mutaties
WHERE TransactionNumber LIKE 'YearClose%';
-- Show sample records
SELECT TransactionNumber,
    TransactionDate,
    ReferenceNumber,
    administration
FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance%'
    OR TransactionNumber LIKE 'YearClose%'
ORDER BY administration,
    TransactionDate
LIMIT 20;