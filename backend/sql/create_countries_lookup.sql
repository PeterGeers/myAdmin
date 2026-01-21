-- Create countries lookup table
-- Purpose: Provide country code to name mapping for efficient lookups
-- Date: 2026-01-21
-- Create the countries lookup table
CREATE TABLE IF NOT EXISTS countries (
    code VARCHAR(2) PRIMARY KEY COMMENT 'ISO 3166-1 alpha-2 country code',
    name VARCHAR(100) NOT NULL COMMENT 'English country name',
    name_nl VARCHAR(100) DEFAULT NULL COMMENT 'Dutch country name (optional)',
    region VARCHAR(50) DEFAULT NULL COMMENT 'Geographic region (e.g., Europe, Asia)',
    UNIQUE KEY idx_name (name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = 'Country code to name lookup table';
-- Insert common countries (based on your booking data)
INSERT INTO countries (code, name, name_nl, region)
VALUES -- Europe
    ('NL', 'Netherlands', 'Nederland', 'Europe'),
    ('DE', 'Germany', 'Duitsland', 'Europe'),
    (
        'GB',
        'United Kingdom',
        'Verenigd Koninkrijk',
        'Europe'
    ),
    ('FR', 'France', 'Frankrijk', 'Europe'),
    ('BE', 'Belgium', 'België', 'Europe'),
    ('ES', 'Spain', 'Spanje', 'Europe'),
    ('IT', 'Italy', 'Italië', 'Europe'),
    ('CH', 'Switzerland', 'Zwitserland', 'Europe'),
    ('AT', 'Austria', 'Oostenrijk', 'Europe'),
    ('PT', 'Portugal', 'Portugal', 'Europe'),
    ('SE', 'Sweden', 'Zweden', 'Europe'),
    ('NO', 'Norway', 'Noorwegen', 'Europe'),
    ('DK', 'Denmark', 'Denemarken', 'Europe'),
    ('FI', 'Finland', 'Finland', 'Europe'),
    ('PL', 'Poland', 'Polen', 'Europe'),
    ('CZ', 'Czech Republic', 'Tsjechië', 'Europe'),
    ('HU', 'Hungary', 'Hongarije', 'Europe'),
    ('RO', 'Romania', 'Roemenië', 'Europe'),
    ('BG', 'Bulgaria', 'Bulgarije', 'Europe'),
    ('GR', 'Greece', 'Griekenland', 'Europe'),
    ('IE', 'Ireland', 'Ierland', 'Europe'),
    ('HR', 'Croatia', 'Kroatië', 'Europe'),
    ('SK', 'Slovakia', 'Slowakije', 'Europe'),
    ('LV', 'Latvia', 'Letland', 'Europe'),
    ('LT', 'Lithuania', 'Litouwen', 'Europe'),
    ('EE', 'Estonia', 'Estland', 'Europe'),
    ('LU', 'Luxembourg', 'Luxemburg', 'Europe'),
    ('CY', 'Cyprus', 'Cyprus', 'Europe'),
    ('MT', 'Malta', 'Malta', 'Europe'),
    ('IS', 'Iceland', 'IJsland', 'Europe'),
    ('UA', 'Ukraine', 'Oekraïne', 'Europe'),
    ('RS', 'Serbia', 'Servië', 'Europe'),
    ('AL', 'Albania', 'Albanië', 'Europe'),
    (
        'MK',
        'North Macedonia',
        'Noord-Macedonië',
        'Europe'
    ),
    ('MD', 'Moldova', 'Moldavië', 'Europe'),
    ('GE', 'Georgia', 'Georgië', 'Europe/Asia'),
    -- Americas
    (
        'US',
        'United States',
        'Verenigde Staten',
        'North America'
    ),
    ('CA', 'Canada', 'Canada', 'North America'),
    ('MX', 'Mexico', 'Mexico', 'North America'),
    ('BR', 'Brazil', 'Brazilië', 'South America'),
    ('AR', 'Argentina', 'Argentinië', 'South America'),
    ('CO', 'Colombia', 'Colombia', 'South America'),
    ('PE', 'Peru', 'Peru', 'South America'),
    ('UY', 'Uruguay', 'Uruguay', 'South America'),
    ('PA', 'Panama', 'Panama', 'Central America'),
    ('EC', 'Ecuador', 'Ecuador', 'South America'),
    -- Asia
    ('CN', 'China', 'China', 'Asia'),
    ('JP', 'Japan', 'Japan', 'Asia'),
    ('IN', 'India', 'India', 'Asia'),
    ('KR', 'South Korea', 'Zuid-Korea', 'Asia'),
    ('TR', 'Turkey', 'Turkije', 'Asia/Europe'),
    ('SG', 'Singapore', 'Singapore', 'Asia'),
    ('MY', 'Malaysia', 'Maleisië', 'Asia'),
    ('TH', 'Thailand', 'Thailand', 'Asia'),
    ('PH', 'Philippines', 'Filipijnen', 'Asia'),
    ('HK', 'Hong Kong', 'Hong Kong', 'Asia'),
    (
        'AE',
        'United Arab Emirates',
        'Verenigde Arabische Emiraten',
        'Middle East'
    ),
    (
        'SA',
        'Saudi Arabia',
        'Saoedi-Arabië',
        'Middle East'
    ),
    ('IL', 'Israel', 'Israël', 'Middle East'),
    ('AZ', 'Azerbaijan', 'Azerbeidzjan', 'Asia'),
    ('KZ', 'Kazakhstan', 'Kazachstan', 'Asia'),
    ('UZ', 'Uzbekistan', 'Oezbekistan', 'Asia'),
    ('PK', 'Pakistan', 'Pakistan', 'Asia'),
    -- Oceania
    ('AU', 'Australia', 'Australië', 'Oceania'),
    ('NZ', 'New Zealand', 'Nieuw-Zeeland', 'Oceania'),
    -- Africa
    ('ZA', 'South Africa', 'Zuid-Afrika', 'Africa'),
    ('EG', 'Egypt', 'Egypte', 'Africa'),
    ('MA', 'Morocco', 'Marokko', 'Africa'),
    ('NG', 'Nigeria', 'Nigeria', 'Africa'),
    -- Russia
    ('RU', 'Russia', 'Rusland', 'Europe/Asia') ON DUPLICATE KEY
UPDATE name =
VALUES(name),
    name_nl =
VALUES(name_nl),
    region =
VALUES(region);
-- Create an updated view that includes country name via JOIN
DROP VIEW IF EXISTS vw_bnb_total;
CREATE VIEW vw_bnb_total AS
SELECT b.id,
    b.sourceFile,
    b.channel,
    b.listing,
    b.checkinDate,
    b.checkoutDate,
    b.nights,
    b.guests,
    b.amountGross,
    b.amountNett,
    b.amountChannelFee,
    b.amountTouristTax,
    b.amountVat,
    b.guestName,
    b.phone,
    b.reservationCode,
    b.reservationDate,
    b.status,
    b.pricePerNight,
    b.daysBeforeReservation,
    b.addInfo,
    b.year,
    b.q,
    b.m,
    b.country,
    c.name AS countryName,
    c.name_nl AS countryNameNL,
    c.region AS countryRegion,
    'actual' AS source_type
FROM bnb b
    LEFT JOIN countries c ON b.country = c.code
UNION ALL
SELECT b.id,
    b.sourceFile,
    b.channel,
    b.listing,
    b.checkinDate,
    b.checkoutDate,
    b.nights,
    b.guests,
    b.amountGross,
    b.amountNett,
    b.amountChannelFee,
    b.amountTouristTax,
    b.amountVat,
    b.guestName,
    b.phone,
    b.reservationCode,
    b.reservationDate,
    b.status,
    b.pricePerNight,
    b.daysBeforeReservation,
    b.addInfo,
    b.year,
    b.q,
    b.m,
    b.country,
    c.name AS countryName,
    c.name_nl AS countryNameNL,
    c.region AS countryRegion,
    'planned' AS source_type
FROM bnbplanned b
    LEFT JOIN countries c ON b.country = c.code;
-- Verification queries
-- SELECT * FROM countries ORDER BY name;
-- SELECT country, countryName, COUNT(*) FROM vw_bnb_total WHERE country IS NOT NULL GROUP BY country, countryName ORDER BY COUNT(*) DESC;