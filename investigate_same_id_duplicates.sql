-- Investigate why duplicate reservationCodes appear to have same IDs
-- This shouldn't be possible in a properly configured database
-- STEP 1: Check if ID is actually the primary key
SHOW CREATE TABLE bnb;
-- STEP 2: Check for actual duplicate IDs (this should be impossible)
SELECT ID,
    COUNT(*) as count_same_id
FROM bnb
GROUP BY ID
HAVING COUNT(*) > 1
ORDER BY count_same_id DESC
LIMIT 10;
-- STEP 3: Check the original duplicate query more carefully
SELECT ID,
    reservationCode,
    checkinDate,
    guestName,
    COUNT(*) OVER (PARTITION BY reservationCode) as dup_count
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
-- STEP 4: Check if there are hidden characters or encoding issues
SELECT reservationCode,
    HEX(reservationCode) as hex_value,
    LENGTH(reservationCode) as length_chars,
    CHAR_LENGTH(reservationCode) as length_unicode,
    COUNT(*) as count
FROM bnb
WHERE reservationCode IS NOT NULL
    AND reservationCode != ''
GROUP BY reservationCode,
    HEX(reservationCode)
HAVING COUNT(*) > 1
ORDER BY count DESC
LIMIT 10;
-- STEP 5: Alternative view - maybe the issue is in the GROUP BY query itself
SELECT reservationCode,
    COUNT(*) as duplicate_count,
    GROUP_CONCAT(
        DISTINCT ID
        ORDER BY ID
    ) as all_ids,
    GROUP_CONCAT(
        DISTINCT checkinDate
        ORDER BY checkinDate
    ) as all_dates,
    GROUP_CONCAT(
        DISTINCT guestName
        ORDER BY guestName SEPARATOR ' | '
    ) as all_guests
FROM bnb
WHERE reservationCode IS NOT NULL
    AND reservationCode != ''
GROUP BY reservationCode
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC
LIMIT 10;