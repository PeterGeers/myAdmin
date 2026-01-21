-- Migration: Add countryName column to bnb and bnbplanned tables
-- Purpose: Store full country names alongside ISO codes for better readability
-- Date: 2026-01-21
-- Step 1: Add countryName column to bnb table
ALTER TABLE bnb
ADD COLUMN countryName VARCHAR(100) DEFAULT NULL COMMENT 'Full country name (e.g., Netherlands, Spain, United States)';
-- Step 2: Add countryName column to bnbplanned table
ALTER TABLE bnbplanned
ADD COLUMN countryName VARCHAR(100) DEFAULT NULL COMMENT 'Full country name (e.g., Netherlands, Spain, United States)';
-- Step 3: Update the view to include countryName column
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
    countryName,
    -- NEW: Country name column
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
    countryName,
    -- NEW: Country name column
    'planned' AS source_type
FROM bnbplanned;