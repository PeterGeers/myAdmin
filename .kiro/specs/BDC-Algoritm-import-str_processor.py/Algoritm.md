# Booking.com (BDC) Import Algorithm Specification

## Source File Format

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
