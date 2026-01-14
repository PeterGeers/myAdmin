-- Safe approach to remove duplicate reservation codes from bnb table
-- Execute these queries one by one and verify results before proceeding
-- STEP 1: Create a temporary table with IDs to delete (keeping the lowest ID for each reservationCode)
CREATE TEMPORARY TABLE duplicates_to_delete AS
SELECT b.ID,
    b.reservationCode,
    b.checkinDate,
    b.guestName
FROM bnb b
    INNER JOIN (
        SELECT reservationCode,
            MIN(ID) as keep_id
        FROM bnb
        WHERE reservationCode IS NOT NULL
            AND reservationCode != ''
        GROUP BY reservationCode
        HAVING COUNT(*) > 1
    ) keeper ON b.reservationCode = keeper.reservationCode
WHERE b.ID != keeper.keep_id;
-- STEP 2: Verify what will be deleted (RUN THIS FIRST!)
SELECT COUNT(*) as records_to_delete,
    COUNT(DISTINCT reservationCode) as unique_codes_affected
FROM duplicates_to_delete;
-- STEP 3: Show sample of records that will be deleted
SELECT *
FROM duplicates_to_delete
ORDER BY reservationCode,
    ID
LIMIT 10;
-- STEP 4: Show what will be kept (for verification)
SELECT b.ID,
    b.reservationCode,
    b.checkinDate,
    b.guestName,
    'WILL BE KEPT' as status
FROM bnb b
    INNER JOIN (
        SELECT reservationCode,
            MIN(ID) as keep_id
        FROM bnb
        WHERE reservationCode IS NOT NULL
            AND reservationCode != ''
        GROUP BY reservationCode
        HAVING COUNT(*) > 1
    ) keeper ON b.reservationCode = keeper.reservationCode
    AND b.ID = keeper.keep_id
ORDER BY reservationCode
LIMIT 10;
-- STEP 5: Only run this DELETE after verifying steps 2-4 look correct!
-- DELETE FROM bnb WHERE ID IN (SELECT ID FROM duplicates_to_delete);
-- STEP 6: Verify deletion worked
-- SELECT 
--     reservationCode,
--     COUNT(*) as remaining_count
-- FROM bnb 
-- WHERE reservationCode IS NOT NULL AND reservationCode != ''
-- GROUP BY reservationCode 
-- HAVING COUNT(*) > 1;