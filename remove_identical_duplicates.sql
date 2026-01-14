-- Remove identical duplicate records from bnb table
-- Since duplicates are exactly the same, we keep the one with the lowest ID
-- STEP 1: First, let's verify the current duplicate count
SELECT 'Before deletion' as status,
    COUNT(*) as total_duplicates
FROM bnb b1
WHERE EXISTS (
        SELECT 1
        FROM bnb b2
        WHERE b2.reservationCode = b1.reservationCode
            AND b2.ID < b1.ID
            AND b1.reservationCode IS NOT NULL
            AND b1.reservationCode != ''
    );
-- STEP 2: Show sample of what will be deleted (records with higher IDs)
SELECT ID,
    reservationCode,
    checkinDate,
    guestName,
    'WILL BE DELETED' as action
FROM bnb b1
WHERE EXISTS (
        SELECT 1
        FROM bnb b2
        WHERE b2.reservationCode = b1.reservationCode
            AND b2.ID < b1.ID
            AND b1.reservationCode IS NOT NULL
            AND b1.reservationCode != ''
    )
ORDER BY reservationCode,
    ID
LIMIT 10;
-- STEP 3: Execute the deletion (keeps record with lowest ID for each reservationCode)
DELETE b1
FROM bnb b1
WHERE EXISTS (
        SELECT 1
        FROM bnb b2
        WHERE b2.reservationCode = b1.reservationCode
            AND b2.ID < b1.ID
            AND b1.reservationCode IS NOT NULL
            AND b1.reservationCode != ''
    );
-- STEP 4: Verify deletion worked - should return 0 duplicates
SELECT 'After deletion' as status,
    COUNT(*) as remaining_duplicates
FROM bnb
WHERE reservationCode IS NOT NULL
    AND reservationCode != ''
GROUP BY reservationCode
HAVING COUNT(*) > 1;
-- STEP 5: Final count check
SELECT COUNT(DISTINCT reservationCode) as unique_reservation_codes,
    COUNT(*) as total_records,
    COUNT(*) - COUNT(DISTINCT reservationCode) as should_be_zero
FROM bnb
WHERE reservationCode IS NOT NULL
    AND reservationCode != '';