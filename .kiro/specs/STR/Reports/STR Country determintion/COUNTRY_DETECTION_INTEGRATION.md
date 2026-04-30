# Country Detection Integration - Complete

## Overview

Automatic country detection has been fully integrated into the STR (Short-Term Rental) booking processor. New bookings will automatically have their guest country detected and stored.

## What Was Implemented

### 1. ✅ Country Detection Module (`src/country_detector.py`)

- `extract_country_from_phone()` - Extracts country from international phone numbers
- `extract_country_from_booking_addinfo()` - Extracts country from Booking.com data
- `detect_country()` - Unified detection based on channel
- Handles both old and new Booking.com data formats
- Case-insensitive channel matching

### 2. ✅ Database Schema

- Added `country VARCHAR(2)` column to `bnb` table
- Added `country VARCHAR(2)` column to `bnbplanned` table
- Created `countries` lookup table with 245 countries
- Updated `vw_bnb_total` view with LEFT JOIN to countries table
- View now includes: `country`, `countryName`, `countryNameNL`, `countryRegion`

### 3. ✅ Countries Lookup Table

Contains 245 countries with:

- `code` - ISO 3166-1 alpha-2 (e.g., NL, DE, US)
- `name` - English name (e.g., Netherlands, Germany)
- `name_nl` - Dutch name (e.g., Nederland, Duitsland)
- `region` - Geographic region (e.g., Europe, Asia, North America)

### 4. ✅ STR Processor Integration (`src/str_processor.py`)

**Added country detection to all three booking channels:**

#### AirBNB Processing

```python
# Detect country from phone number
country = detect_country('airbnb', phone=phone, addinfo=add_info)
transaction['country'] = country
```

#### Booking.com Processing

```python
# Detect country from addInfo field
country = detect_country('booking.com', phone='', addinfo=add_info)
transaction['country'] = country
```

#### Direct Bookings Processing

```python
# Detect country (usually None for direct bookings)
country = detect_country(channel, phone='', addinfo=add_info)
transaction['country'] = country
```

### 5. ✅ Database Module Integration (`src/str_database.py`)

- Updated INSERT queries for `bnb` table to include `country` field
- Updated INSERT queries for `bnbplanned` table to include `country` field
- Country field defaults to NULL if not detected

### 6. ✅ Backfill Existing Records

- Backfilled 786 existing bookings with country data
- Detection rate: 100% for Booking.com, ~60% for AirBNB (depends on phone availability)
- Fixed incorrect "12" values to proper country codes

## Detection Methods by Channel

| Channel         | Detection Method     | Data Source                              | Success Rate               |
| --------------- | -------------------- | ---------------------------------------- | -------------------------- |
| **AirBNB**      | Phone number parsing | `phone` column                           | ~60% (when phone provided) |
| **Booking.com** | Parse addInfo field  | Position 19 or 13 in pipe-separated data | ~100%                      |
| **Direct/VRBO** | Not available        | N/A                                      | 0% (no data source)        |

## Usage Examples

### Query bookings with country names

```sql
SELECT
    id,
    guestName,
    country,
    countryName,
    countryNameNL,
    countryRegion
FROM vw_bnb_total
WHERE country IS NOT NULL
ORDER BY checkinDate DESC;
```

### Top countries by booking count

```sql
SELECT
    country,
    countryName,
    COUNT(*) as bookings
FROM vw_bnb_total
WHERE country IS NOT NULL
GROUP BY country, countryName
ORDER BY bookings DESC;
```

### Bookings by region

```sql
SELECT
    countryRegion,
    COUNT(*) as bookings
FROM vw_bnb_total
WHERE countryRegion IS NOT NULL
GROUP BY countryRegion
ORDER BY bookings DESC;
```

## Testing

Run the integration test:

```bash
python scripts/test_country_integration.py
```

All 6 test cases pass:

- ✅ AirBNB with phone (NL)
- ✅ AirBNB with US phone (US)
- ✅ Booking.com new format (NL)
- ✅ Booking.com old format (ES)
- ✅ Direct booking (None)
- ✅ AirBNB without phone (None)

## Reports

Generate HTML country report:

```bash
python scripts/generate_country_report.py
```

Output: `backend/reports/country_bookings_report.html`

## Current Statistics

Based on existing data:

- **Total bookings with country**: 786
- **Countries represented**: 66
- **Geographic regions**: 10
- **Top country**: Netherlands (198 bookings)
- **Top region**: Europe (644 bookings)

## Future Enhancements

Potential improvements:

1. Add IP geolocation for direct bookings
2. Add more language translations (French, German, Spanish)
3. Create country-based analytics dashboard
4. Add country-based pricing strategies
5. Generate country-specific marketing reports

## Files Modified

1. `backend/src/str_processor.py` - Added country detection calls
2. `backend/src/str_database.py` - Updated INSERT queries
3. `backend/src/country_detector.py` - Created detection module
4. `backend/sql/add_country_column.sql` - Database migration
5. `backend/sql/create_countries_lookup.sql` - Lookup table creation

## Files Created

1. `backend/scripts/migrate_add_country.py` - Migration script
2. `backend/scripts/backfill_country.py` - Backfill script
3. `backend/scripts/populate_all_countries.py` - Populate 245 countries
4. `backend/scripts/test_country_integration.py` - Integration tests
5. `backend/scripts/generate_country_report.py` - HTML report generator
6. `backend/scripts/verify_country.py` - Verification script

## Maintenance

### Adding a new country

```sql
INSERT INTO countries (code, name, name_nl, region)
VALUES ('XX', 'Country Name', 'Nederlandse Naam', 'Region');
```

### Updating country name

```sql
UPDATE countries
SET name = 'New Name', name_nl = 'Nieuwe Naam'
WHERE code = 'XX';
```

### Re-detecting countries for specific bookings

```sql
-- Clear country for re-detection
UPDATE bnb SET country = NULL WHERE channel = 'airbnb' AND country IS NULL;

-- Then run backfill script
python scripts/backfill_country.py --execute
```

## Support

For issues or questions:

1. Check test results: `python scripts/test_country_integration.py`
2. Verify database: `python scripts/verify_country.py`
3. Review logs in STR processor output
4. Check country detector module for debugging

---

**Status**: ✅ Complete and Production Ready  
**Last Updated**: January 21, 2026  
**Version**: 1.0
