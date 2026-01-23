# Country Detection for Guest Bookings

## Overview

Detect guest country of origin from booking data across different channels (AirBNB, Booking.com, and others).

## Data Sources

### 1. AirBNB - Phone-based Detection

- **Source**: `phone` column in bookings
- **Format**: International format like `+971 58 260 0953`
- **Method**: Extract country code prefix (e.g., `+971` = UAE)
- **Reliability**: High (when phone number is provided)

### 2. Booking.com - Direct Country Code

- **Source**: `addInfo` field (pipe-separated values)
- **Format**: `Booking.com|6438303279|Ruda, Luis|2025-06-26 11:19:30|NA|ok|91.3212 EUR|12|10.958544 EUR|Paid online|NA|NA|NA|es|Leisure|Mobile|Rode huis|1|NA`
- **Country Position**: Field 13 (zero-indexed) - e.g., `es` for Spain
- **Method**: Parse pipe-separated string and extract country code
- **Reliability**: Very High (explicitly provided by Booking.com)

### 3. Other Channels (Direct, VRBO, etc.)

- **Source**: None available
- **Method**: Set to `NULL` or `Unknown`
- **Fallback**: Could use IP geolocation if captured

## Implementation Plan

### Phase 1: Database Schema Changes

1. Add `country` column to `bnb` table (VARCHAR(2) for ISO country codes)
2. Add `country` column to `bnbplanned` table
3. Update `vw_bnb_total` view to include country field

### Phase 2: Country Detection Logic

Create utility functions in `backend/src/country_detector.py`:

- `extract_country_from_phone(phone: str) -> Optional[str]`
- `extract_country_from_booking_addinfo(addinfo: str) -> Optional[str]`
- `detect_country(channel: str, phone: str, addinfo: str) -> Optional[str]`

### Phase 3: Integration

Update `backend/src/str_processor.py`:

- Integrate country detection in `_process_airbnb()`
- Integrate country detection in `_process_booking()`
- Integrate country detection in `_process_direct()`

### Phase 4: Database Updates

Update `backend/src/str_database.py`:

- Modify INSERT queries to include country field
- Add country to booking dictionaries

## Technical Details

### Phone Country Code Mapping

Use `phonenumbers` library (Python) for robust phone number parsing:

```python
import phonenumbers

def extract_country_from_phone(phone: str) -> Optional[str]:
    try:
        parsed = phonenumbers.parse(phone, None)
        country_code = phonenumbers.region_code_for_number(parsed)
        return country_code  # Returns ISO 3166-1 alpha-2 code (e.g., 'AE', 'ES')
    except:
        return None
```

### Booking.com addInfo Parsing

```python
def extract_country_from_booking_addinfo(addinfo: str) -> Optional[str]:
    try:
        fields = addinfo.split('|')
        if len(fields) > 13:
            country = fields[13].strip()
            return country if country and country != 'NA' else None
        return None
    except:
        return None
```

### Channel-Specific Detection

```python
def detect_country(channel: str, phone: str, addinfo: str) -> Optional[str]:
    if channel == 'airbnb' and phone:
        return extract_country_from_phone(phone)
    elif channel == 'booking.com' and addinfo:
        return extract_country_from_booking_addinfo(addinfo)
    else:
        return None
```

## Database Schema

### SQL Migration

```sql
-- Add country column to bnb table
ALTER TABLE bnb ADD COLUMN country VARCHAR(2) DEFAULT NULL COMMENT 'ISO 3166-1 alpha-2 country code';

-- Add country column to bnbplanned table
ALTER TABLE bnbplanned ADD COLUMN country VARCHAR(2) DEFAULT NULL COMMENT 'ISO 3166-1 alpha-2 country code';

-- Update view to include country
CREATE OR REPLACE VIEW vw_bnb_total AS
SELECT
    ID, sourceFile, channel, listing, checkinDate, checkoutDate, nights, guests,
    amountGross, amountNett, amountChannelFee, amountTouristTax, amountVat,
    guestName, phone, reservationCode, reservationDate, status, pricePerNight,
    daysBeforeReservation, addInfo, year, q, m, country,
    'realised' as bookingType
FROM bnb
UNION ALL
SELECT
    ID, sourceFile, channel, listing, checkinDate, checkoutDate, nights, guests,
    amountGross, amountNett, amountChannelFee, amountTouristTax, amountVat,
    guestName, phone, reservationCode, reservationDate, status, pricePerNight,
    daysBeforeReservation, addInfo, year, q, m, country,
    'planned' as bookingType
FROM bnbplanned;
```

## Benefits

- **Analytics**: Track guest origin patterns by country
- **Marketing**: Target specific countries with better conversion rates
- **Compliance**: Meet tourism reporting requirements
- **Insights**: Understand international vs domestic guest ratios

## Next Steps

1. Install `phonenumbers` library: `pip install phonenumbers`
2. Create `country_detector.py` utility module
3. Update database schema (run migration SQL)
4. Integrate detection logic into STR processor
5. Test with sample data from each channel
6. Backfill existing records (optional)

