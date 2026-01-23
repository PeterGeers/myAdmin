# Booking.com (BDC) Import Algorithm Specification

## Overview

This document describes two import methods for Booking.com data:

1. **Primary Import:** Excel file with booking details (available immediately after booking)
2. **Payout Import:** CSV file with final financial figures (available monthly after month closure)

The Payout import is used to **overwrite** the calculated financial values with the actual figures from Booking.com's final settlement.

---

## 1. Primary Import: Booking Details (Excel)

### Source File Format

**Import File Example:** `Check-in 2025-12-13 to 2027-01-13.xls`

### Excel File Structure

**Header Row:**

```
Book number | Booked by | Guest name(s) | Check-in | Check-out | Booked on | Status | Rooms | Persons | Adults | Children | Children's age(s) | Price | Commission % | Commission amount | Payment status | Payment method (Payment Provider) | Remarks | Booker group | Booker country | Travel purpose | Device | Unit type | Duration (nights) | Cancellation date | Address | Phone number
```

**Example Data Row:**

```
6547074679 | Hauck, Lukas | Lukas Hauck | 2025-12-15 | 2025-12-17 | 2025-12-09 00:26:33 | ok | 1 | 1 | 1 | 0 | | 126.6314 EUR | 12 | 15.195768 EUR | Payment via Booking.com | | | | de | Leisure | Mobile | One-Bedroom Apartment | 2 | | |
```

## Input Values

Two primary values are extracted from the Booking.com export:

1. **Base Price:** `Price` field (e.g., "126.6314 EUR")
   - Field mapping: `Price` → `Total price` → `Amount`
   - This is the amount paid by the guest to Booking.com
2. **Commission Amount (from BDC):** `Commission amount` field (e.g., "15.195768 EUR")
   - Field mapping: `Commission amount` → `Commission`
   - This is Booking.com's commission as reported in their export
   - **Important:** This value is used in the gross calculation but is NOT directly stored
   - The actual `amountChannelFee` stored in the database is calculated as: **amountGross - basePrice**

## Calculation Algorithm

### Tax Rate Determination

**Effective Date:** January 1, 2026

**For check-in dates >= 2026-01-01:**

- VAT Rate: 21%
- VAT Base: 121 (100 + 21)
- Tourist Tax Rate: 6.9%
- Tourist Tax Base: 106.9 (100 + 6.9)

**For check-in dates < 2026-01-01:**

- VAT Rate: 9%
- VAT Base: 109 (100 + 9)
- Tourist Tax Rate: 6.02%
- Tourist Tax Base: 106.02 (100 + 6.02)

### Calculation Steps (2026 Rates)

#### Step 1: Calculate Gross Amount

```
amountGross = round((basePrice + commissionAmount) × 1.047826, 2)
```

**Note:** The factor 1.047826 (or 4.7826% uplift) represents the additional fees on top of the base price and commission from BDC. This factor was derived from actual Booking.com data analysis.

#### Step 2: Calculate Channel Fee

```
amountChannelFee = amountGross - basePrice
```

**Important:** The `amountChannelFee` is the CALCULATED difference between gross and base price, NOT the commission amount from Booking.com. The commission from BDC is only used in Step 1 to calculate the gross amount.

#### Step 3: Calculate VAT

```
amountVat = round((amountGross / 121) × 21, 2)
```

**Formula:** `(gross_amount / vat_base) × vat_rate`

#### Step 4: Calculate Tourist Tax

```
vatExclusiveAmount = amountGross - amountVat
amountTouristTax = round((vatExclusiveAmount / 106.9) × 6.9, 2)
```

**Formula:** `((gross_amount - vat) / tourist_base) × tourist_rate`

#### Step 5: Calculate Net Amount

```
amountNett = amountGross - amountVat - amountTouristTax - amountChannelFee
```

#### Step 6: Calculate Price Per Night

```
pricePerNight = round(amountNett / nights, 2)
```

## Example Calculation (2026 Rates)

**Given:**

- Base Price: €126.6314
- Commission Amount: €15.195768
- Nights: 2

**Calculations:**

```
Step 1: Calculate Gross Amount
amountGross = round((126.6314 + 15.195768) × 1.033750, 2)
            = round(141.827168 × 1.033750, 2)
            = round(146.614, 2)
            = €146.61

Step 2: Calculate Channel Fee (NOT the same as BDC commission!)
amountChannelFee = 146.61 - 126.6314
                 = €19.98
Note: BDC Commission was €15.20, but our channel fee is €19.98

Step 3: Calculate VAT
amountVat = round((146.59 / 121) × 21, 2)
          = round(1.2115 × 21, 2)
          = round(25.44, 2)
          = €25.44

Step 4: Calculate Tourist Tax
vatExclusiveAmount = 146.59 - 25.44
                   = €121.15

amountTouristTax = round((121.15 / 106.9) × 6.9, 2)
                 = round(1.1333 × 6.9, 2)
                 = round(7.82, 2)
                 = €7.82

Step 5: Calculate Net Amount
amountNett = 146.59 - 25.44 - 7.82 - 19.96
           = €93.37

Step 6: Calculate Price Per Night
pricePerNight = round(93.37 / 2, 2)
              = €46.69
```

## Implementation Notes

1. All monetary amounts must be rounded to 2 decimal places
2. Tax rates are determined by the check-in date, not the booking date
3. The uplift factor (1.047826 or 4.7826%) is constant and derived from actual BDC data
4. Tourist tax is always calculated on the VAT-exclusive amount
5. **Commission amount from Booking.com** is used in Step 1 to calculate gross amount
6. **Channel fee stored in database** is calculated as: amountGross - basePrice (different from BDC commission)
7. The Excel file contains precise decimal values that differ from the web interface display
8. Always use the precise values from the Excel file, not the rounded display values

---

## 2. Payout Import: Final Financial Figures (CSV)

### Overview

The Payout CSV file is provided by Booking.com **monthly after month closure** and contains the **final, accurate financial figures** for all reservations. This file should be imported **after** the primary Excel import to overwrite the calculated values with actual settlement data.

### Source File Format

**Import File Example:** `Payout_from_2025-01-01_until_2025-12-31.csv`

### CSV File Structure

**Header Row:**

```
Type/Transaction type, Statement Descriptor, Reference number, Check-in date, Check-out date, Issue date, Reservation status, Rooms, Room nights, Property ID, Property name, Legal ID, Legal name, Country, Payout type, Gross amount, Commission, Commission %, Payments Service Fee, Payments Service Fee %, Tax/VAT, Transaction amount, Transaction currency, Exchange rate, Payable amount, Payout amount, Payout currency, Payout date, Payout frequency, Bank account
```

**Example Data Rows:**

```
(Payout)             , y55PeMz92KfbsTyD    , -               , -            , -             , -         , -                 , -    , -          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , -           , -         , -           , -                   , -                     , -      , -                 , -                   , -            ,          95.26, 95.26        , EUR            , 2025-03-10 , Daily           , *6917
Reservation          , y55PeMz92KfbsTyD    , 4649972566      , 2025-03-08   , 2025-03-09    , 2025-03-09, Okay              , 1    , 1          ,     5620035, "JaBaKi Green Studio",  8411095, "Goodwin Solutions BV", Netherlands, Net        , 112.50      , -12.79    , 11.37%      , -1.46               , 1.30%                 , -2.99  , 95.26             , EUR                 , 1.00         ,          95.26, -            , EUR            , 2025-03-10 , Daily           , *6917
```

### Important Notes

1. **File Availability:** This file is only available **after month closure** (typically early in the following month)
2. **Import Order:** Always import the Excel file first, then overwrite with Payout CSV data
3. **Data Completeness:** The Payout file only contains reservations that have been settled/paid out
4. **Row Types:** The CSV contains two types of rows:
   - `(Payout)` rows: Summary payout information (can be ignored for our purposes)
   - `Reservation` rows: Individual reservation financial details (use these)

### Field Mapping

The Payout CSV provides **actual financial figures** that should replace the calculated values:

| CSV Column             | Database Field             | Description                                        |
| ---------------------- | -------------------------- | -------------------------------------------------- |
| `Reference number`     | `reservationCode`          | Booking.com reservation number (unique identifier) |
| `Check-in date`        | `checkinDate`              | Check-in date                                      |
| `Check-out date`       | `checkoutDate`             | Check-out date                                     |
| `Room nights`          | `nights`                   | Number of nights                                   |
| `Gross amount`         | `amountGross`              | **Actual gross amount from BDC**                   |
| `Commission`           | Part of `amountChannelFee` | BDC commission (negative value)                    |
| `Payments Service Fee` | Part of `amountChannelFee` | Payment processing fee (negative value)            |
| `Tax/VAT`              | N/A                        | **VAT on BDC services (not used)**                 |
| `Transaction amount`   | N/A                        | Net amount after all deductions (not used)         |

**Important Note**: The `Tax/VAT` column in the Payout CSV is the VAT on Booking.com's services (channel fee), which you can reclaim from tax authorities. This is **NOT** the accommodation VAT that you must pay. The accommodation VAT must be calculated on `amountGross` using the standard rates (9% until 2026-01-01, then 21%).

### Calculation for Payout Import

When importing from the Payout CSV, use the **actual gross amount** from Booking.com and **calculate** the accommodation VAT:

```
amountGross = Gross amount (from CSV)
amountChannelFee = abs(Commission) + abs(Payments Service Fee)
amountVat = Calculate on amountGross (9% or 21% based on check-in date)
amountTouristTax = Calculate using existing algorithm (not in CSV)
amountNett = amountGross - amountVat - amountTouristTax - amountChannelFee
```

**Important**: The `Tax/VAT` column in the CSV is the VAT on BDC's services (which you can reclaim). This is **NOT** used in our calculations. We calculate the accommodation VAT on the gross amount.

### Tourist Tax Calculation

The Payout CSV does **not** include tourist tax separately. Calculate it using the existing algorithm:

**For check-in dates >= 2026-01-01:**

```
vatExclusiveAmount = amountGross - amountVat
amountTouristTax = round((vatExclusiveAmount / 106.9) × 6.9, 2)
```

**For check-in dates < 2026-01-01:**

```
vatExclusiveAmount = amountGross - amountVat
amountTouristTax = round((vatExclusiveAmount / 106.02) × 6.02, 2)
```

### VAT Calculation

The accommodation VAT must be calculated on the gross amount (not taken from CSV):

**For check-in dates >= 2026-01-01:**

```
amountVat = round((amountGross / 121) × 21, 2)
```

**For check-in dates < 2026-01-01:**

```
amountVat = round((amountGross / 109) × 9, 2)
```

### Example Payout Import Calculation

**Given (from CSV):**

- Reference number: 4649972566
- Check-in date: 2025-03-08
- Check-out date: 2025-03-09
- Room nights: 1
- Gross amount: €112.50
- Commission: -€12.79
- Payments Service Fee: -€1.46
- Tax/VAT: -€2.99 (VAT on BDC services - not used)

**Calculations:**

```
Step 1: Use actual gross amount from CSV
amountGross = €112.50

Step 2: Calculate channel fee from CSV values
amountChannelFee = abs(-12.79) + abs(-1.46)
                 = 12.79 + 1.46
                 = €14.25

Step 3: Calculate accommodation VAT on gross amount
Check-in date 2025-03-08 is before 2026-01-01, so use 9% rate
amountVat = round((112.50 / 109) × 9, 2)
          = round(1.0321 × 9, 2)
          = round(9.29, 2)
          = €9.29

Step 4: Calculate tourist tax (not in CSV, use algorithm)
vatExclusiveAmount = 112.50 - 9.29
                   = €103.21

amountTouristTax = round((103.21 / 106.02) × 6.02, 2)
                 = round(0.9735 × 6.02, 2)
                 = round(5.86, 2)
                 = €5.86

Step 5: Calculate net amount
amountNett = 112.50 - 9.29 - 5.86 - 14.25
           = €83.10

Step 6: Calculate price per night
pricePerNight = round(83.10 / 1, 2)
              = €83.10
```

**Note**: The Tax/VAT value of -€2.99 from the CSV is the VAT on Booking.com's services (commission and fees). This can be reclaimed from tax authorities but is not used in our accommodation calculations.

### Import Process

1. **Match by Reservation Code:** Use the `Reference number` field to find existing records in the database
2. **Update Financial Fields:** Overwrite the following calculated fields with actual values:
   - `amountGross` ← from CSV
   - `amountChannelFee` ← calculated from Commission + Payments Service Fee
   - `amountVat` ← from CSV
   - `amountTouristTax` ← calculated using algorithm
   - `amountNett` ← calculated: gross - vat - tourist tax - channel fee
   - `pricePerNight` ← calculated: nett / nights
3. **Preserve Other Fields:** Keep all other fields (guest name, dates, etc.) from the original Excel import
4. **Log Updates:** Track which records were updated from Payout data for audit purposes

### Implementation Requirements

1. **File Detection:** Automatically detect Payout CSV files by filename pattern: `Payout_from_*.csv`
2. **Import Timing:** Import Payout files after the primary Excel import is complete
3. **Validation:** Verify that the reservation code exists before updating
4. **Error Handling:** Log any mismatches or missing reservations
5. **Audit Trail:** Record when financial values were updated from Payout data
6. **Reporting:** Provide summary of how many records were updated and any discrepancies

### Data Quality Notes

1. **More Accurate Gross Amount:** Payout data contains the **final gross amount** from Booking.com's settlement
2. **VAT Calculation:** The accommodation VAT must be calculated on the gross amount (9% or 21% based on check-in date)
3. **BDC Service VAT:** The `Tax/VAT` column in the CSV is VAT on BDC's services (reclaimable) and is not used in calculations
4. **Timing Difference:** There may be a delay between booking and payout, so not all reservations will have payout data immediately
5. **Currency:** All amounts in the Payout CSV are in EUR (or the property's settlement currency)
6. **Negative Values:** Commission and fees are negative in the CSV (deductions from gross)

---

## 3. API Endpoint for Payout Import

### Endpoint Details

**URL:** `POST /api/str/import-payout`

**Content-Type:** `multipart/form-data`

**Authentication:** None (internal use)

### Request

**Form Data:**

- `file`: The Payout CSV file (required)
  - Filename must match pattern: `Payout_from_*.csv`
  - Example: `Payout_from_2025-01-01_until_2025-12-31.csv`

### Response

**Success Response (200 OK):**

```json
{
  "success": true,
  "message": "Payout CSV processed successfully",
  "processing": {
    "total_rows": 204,
    "reservation_rows": 202,
    "updates_prepared": 202,
    "processing_errors": 0
  },
  "database": {
    "updated": 195,
    "not_found": ["1234567890", "9876543210"],
    "errors": []
  },
  "summary": {
    "total_updated": 195,
    "total_not_found": 7,
    "total_errors": 0
  }
}
```

**Error Responses:**

**400 Bad Request - No file provided:**

```json
{
  "success": false,
  "error": "No file provided"
}
```

**400 Bad Request - Invalid filename:**

```json
{
  "success": false,
  "error": "Invalid file format. Expected: Payout_from_YYYY-MM-DD_until_YYYY-MM-DD.csv"
}
```

**500 Internal Server Error:**

```json
{
  "success": false,
  "error": "Error message details"
}
```

### Usage Example (Python)

```python
import requests

# Upload Payout CSV file
url = "http://localhost:5000/api/str/import-payout"
file_path = "Payout_from_2025-01-01_until_2025-12-31.csv"

with open(file_path, 'rb') as f:
    files = {'file': (file_path, f, 'text/csv')}
    response = requests.post(url, files=files)

    if response.status_code == 200:
        result = response.json()
        print(f"✅ Success! Updated {result['summary']['total_updated']} bookings")

        if result['database']['not_found']:
            print(f"⚠️  {len(result['database']['not_found'])} reservations not found in database")
    else:
        print(f"❌ Error: {response.json()['error']}")
```

### Usage Example (cURL)

```bash
curl -X POST http://localhost:5000/api/str/import-payout \
  -F "file=@Payout_from_2025-01-01_until_2025-12-31.csv"
```

### Processing Flow

1. **File Validation:**
   - Check if file is provided
   - Validate filename pattern (`Payout_from_*.csv`)

2. **CSV Processing:**
   - Read CSV file
   - Filter for `Reservation` type rows (ignore `Payout` summary rows)
   - Extract financial data for each reservation
   - Calculate VAT and tourist tax based on check-in date
   - Prepare update records

3. **Database Update:**
   - Match reservations by `reservationCode` and `channel = 'booking.com'`
   - Update financial fields: `amountGross`, `amountChannelFee`, `amountVat`, `amountTouristTax`, `amountNett`, `pricePerNight`
   - Update `sourceFile` to indicate Payout import
   - Track which reservations were updated vs. not found

4. **Response:**
   - Return processing statistics
   - List reservation codes not found in database
   - Report any errors encountered

### Important Notes

1. **Import Order:** Always import the Excel file first to create the initial bookings, then use the Payout CSV to update with actual figures

2. **Not Found Reservations:** Reservations in the Payout CSV that don't exist in the database will be listed in the `not_found` array. This is normal for:
   - Cancelled bookings that were never imported
   - Bookings from properties not in your database
   - Test bookings

3. **Idempotency:** The endpoint can be called multiple times with the same file - it will simply update the same records again

4. **Performance:** Processing 200+ reservations typically takes 1-2 seconds

5. **Error Handling:** If individual rows fail to process, they are logged in the `errors` array but don't stop the entire import

### Testing

A manual test script is available at `backend/test_payout_upload_manual.py`:

```bash
cd backend
python test_payout_upload_manual.py
```

This script will:

- Upload the real Payout CSV file
- Display processing results
- Show which reservations were updated
- List any reservations not found in the database

### Integration with Frontend

The frontend can integrate this endpoint by:

1. Adding a file upload button for Payout CSV files
2. Validating the filename pattern before upload
3. Displaying processing results to the user
4. Showing which bookings were updated
5. Warning about reservations not found in the database

Example frontend code:

```javascript
async function uploadPayoutCSV(file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("/api/str/import-payout", {
      method: "POST",
      body: formData,
    });

    const result = await response.json();

    if (result.success) {
      alert(`✅ Success! Updated ${result.summary.total_updated} bookings`);

      if (result.database.not_found.length > 0) {
        console.warn("Reservations not found:", result.database.not_found);
      }
    } else {
      alert(`❌ Error: ${result.error}`);
    }
  } catch (error) {
    alert(`❌ Upload failed: ${error.message}`);
  }
}
```

---

## 4. Summary

### Import Workflow

1. **Monthly Excel Import:**
   - Import Booking.com Excel file with all bookings
   - Calculate financial values using the algorithm
   - Store in database

2. **Monthly Payout Import (after month closure):**
   - Import Payout CSV file
   - Update existing bookings with actual financial figures
   - Overwrite calculated values with BDC's final settlement data

### Key Differences

| Aspect              | Excel Import                   | Payout Import                     |
| ------------------- | ------------------------------ | --------------------------------- |
| **Timing**          | Immediately after booking      | After month closure               |
| **Purpose**         | Create initial booking records | Update with actual financial data |
| **Data Source**     | Calculated from base price     | Actual from BDC settlement        |
| **Completeness**    | All bookings                   | Only settled/paid out bookings    |
| **Financial Data**  | Calculated estimates           | Final actual amounts              |
| **VAT Calculation** | On calculated gross            | On actual gross from BDC          |
| **Tourist Tax**     | Calculated                     | Calculated (not in CSV)           |

### Best Practices

1. Always import Excel files first to establish baseline data
2. Import Payout CSV monthly after receiving it from Booking.com
3. Monitor the `not_found` list to identify missing bookings
4. Keep both import files for audit purposes
5. Verify that updated amounts are reasonable (not drastically different from calculated values)
