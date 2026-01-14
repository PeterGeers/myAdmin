-- Investigation queries for duplicate reservation codes in bnb table
-- 1. First, let's see a sample of the duplicates with all their details
SELECT ID,
    reservationCode,
    checkinDate,
    guestName,
    createdAt,
    updatedAt
FROM bnb
WHERE reservationCode IN (
        SELECT reservationCode
        FROM bnb
        WHERE reservationCode IS NOT NULL
            AND reservationCode != ''
        GROUP BY reservationCode
        HAVING COUNT(*) > 1
    )
ORDER BY reservationCode,
    ID
LIMIT 20;
-- 2. Check if there are any NULL or empty values causing issues
SELECT reservationCode,
    COUNT(*) as count,
    SUM(
        CASE
            WHEN reservationCode IS NULL THEN 1
            ELSE 0
        END
    ) as null_count,
    SUM(
        CASE
            WHEN reservationCode = '' THEN 1
            ELSE 0
        END
    ) as empty_count
FROM bnb
GROUP BY reservationCode
HAVING COUNT(*) > 1
ORDER BY count DESC
LIMIT 10;
-- 3. Test the join condition that failed in the delete query
SELECT b1.ID as id1,
    b1.reservationCode as code1,
    b2.ID as id2,
    b2.reservationCode as code2,
    (b1.ID > b2.ID) as id_comparison
FROM bnb b1
    INNER JOIN bnb b2 ON b1.reservationCode = b2.reservationCode
WHERE b1.reservationCode IS NOT NULL
    AND b1.reservationCode != ''
    AND b1.ID != b2.ID -- Different records
LIMIT 10;
-- 4. Alternative approach using ROW_NUMBER() to identify duplicates to remove
SELECT ID,
    reservationCode,
    checkinDate,
    guestName,
    ROW_NUMBER() OVER (
        PARTITION BY reservationCode
        ORDER BY ID
    ) as row_num
FROM bnb
WHERE reservationCode IS NOT NULL
    AND reservationCode != ''
    AND reservationCode IN (
        SELECT reservationCode
        FROM bnb
        WHERE reservationCode IS NOT NULL
            AND reservationCode != ''
        GROUP BY reservationCode
        HAVING COUNT(*) > 1
    )
ORDER BY reservationCode,
    ID
LIMIT 20;