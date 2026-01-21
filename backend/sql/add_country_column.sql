-- Migration: Add country column to bnb and bnbplanned tables
-- Purpose: Store ISO 3166-1 alpha-2 country codes for guest origin tracking
-- Date: 2026-01-21
-- Step 1: Add country column to bnb table (actual bookings)
ALTER TABLE bnb
ADD COLUMN country VARCHAR(2) DEFAULT NULL COMMENT 'ISO 3166-1 alpha-2 country code (e.g., AE, ES, US)';
-- Step 2: Add country column to bnbplanned table (planned bookings)
ALTER TABLE bnbplanned
ADD COLUMN country VARCHAR(2) DEFAULT NULL COMMENT 'ISO 3166-1 alpha-2 country code (e.g., AE, ES, US)';
-- Step 3: Update the view to include country column
DROP VIEW IF EXISTS vw_bnb_total;
CREATE VIEW vw_bnb_total AS
SELECT id,
    sourceFile,
    channel,
    listing,
    checkinDate,
    checkoutDate,
    nights,
    guests,
    amountGross,
    amountNett,
    amountChannelFee,
    amountTouristTax,
    amountVat,
    guestName,
    phone,
    reservationCode,
    reservationDate,
    status,
    pricePerNight,
    daysBeforeReservation,
    addInfo,
    year,
    q,
    m,
    country,
    -- NEW: Country column
    'actual' AS source_type
FROM bnb
UNION ALL
SELECT id,
    sourceFile,
    channel,
    listing,
    checkinDate,
    checkoutDate,
    nights,
    guests,
    amountGross,
    amountNett,
    amountChannelFee,
    amountTouristTax,
    amountVat,
    guestName,
    phone,
    reservationCode,
    reservationDate,
    status,
    pricePerNight,
    daysBeforeReservation,
    addInfo,
    year,
    q,
    m,
    country,
    -- NEW: Country column
    'planned' AS source_type
FROM bnbplanned;
-- Verification queries (optional - run these to verify the changes)
-- SHOW COLUMNS FROM bnb LIKE 'country';
-- SHOW COLUMNS FROM bnbplanned LIKE 'country';
-- DESCRIBE vw_bnb_total;