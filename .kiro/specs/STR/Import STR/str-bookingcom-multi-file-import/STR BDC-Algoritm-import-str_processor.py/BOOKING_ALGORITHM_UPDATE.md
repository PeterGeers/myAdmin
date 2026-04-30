# Booking.com Algorithm Update

## Date: January 14, 2026

## Summary

Updated the Booking.com import algorithm in `str_processor.py` to correctly calculate financial amounts based on actual Booking.com data structure.

## Problem

The previous algorithm incorrectly added tourist tax to the base price from Booking.com, which didn't reflect the actual business logic.

## Solution

Implemented the correct algorithm that:

1. Uses both **Base Price** and **Commission Amount** from Booking.com export
2. Applies an uplift factor (1.03357) to calculate gross amount
3. Correctly calculates channel fee, VAT, and tourist tax
4. Produces accurate net amounts and price per night

## Changes Made

### 1. Updated `backend/src/str_processor.py`

**Lines 401-449:** Modified the `_process_booking()` function

**Key Changes:**

- Extract both `Price` and `Commission amount` from Booking.com file
- Calculate `amountGross = (basePrice + commissionAmount) × 1.03357`
- Calculate `amountChannelFee = amountGross - basePrice`
- Use existing `calculate_str_taxes()` function for VAT and tourist tax
- Removed incorrect tourist tax addition to base price

### 2. Created Specification Document

**File:** `specs/BDC-Algoritm-import-str_processor.py/Algoritm.md`

Professional specification document including:

- Source file format description
- Input value definitions
- Complete calculation algorithm
- Tax rate determination logic
- Example calculations with verification

### 3. Created Test Script

**File:** `test_booking_algorithm.py`

Comprehensive test script that validates:

- 2026 tax rates (21% VAT, 6.9% tourist tax)
- 2025 tax rates (9% VAT, 6.02% tourist tax)
- All calculation steps
- Verification of results

## Algorithm Details

### Input Values (from Booking.com Excel)

- **Base Price:** From "Price" column (e.g., "126.6314 EUR")
- **Commission Amount:** From "Commission amount" column (e.g., "15.195768 EUR")

### Calculation Steps

```
1. amountGross = round((basePrice + commissionAmount) × 1.03357, 2)
2. amountChannelFee = amountGross - basePrice
3. amountVat = round((amountGross / 121) × 21, 2)  [for 2026]
4. amountTouristTax = round(((amountGross - amountVat) / 106.9) × 6.9, 2)  [for 2026]
5. amountNett = amountGross - amountVat - amountTouristTax - amountChannelFee
6. pricePerNight = round(amountNett / nights, 2)
```

### Tax Rates by Date

**Check-in >= 2026-01-01:**

- VAT: 21% (base 121)
- Tourist Tax: 6.9% (base 106.9)

**Check-in < 2026-01-01:**

- VAT: 9% (base 109)
- Tourist Tax: 6.02% (base 106.02)

## Example Calculation (2026 Rates)

**Input:**

- Base Price: €126.63
- Commission: €15.20
- Nights: 2

**Output:**

- amountGross: €146.59
- amountChannelFee: €19.96
- amountVat: €25.44
- amountTouristTax: €7.82
- amountNett: €93.37
- pricePerNight: €46.69

**Verification:** ✅ All amounts balance correctly

## Testing

Run the test script to verify the algorithm:

```bash
python test_booking_algorithm.py
```

Expected output: All tests pass with verification showing correct calculations.

## Impact

### Positive Changes

- ✅ Accurate financial calculations matching Booking.com data
- ✅ Correct channel fee calculation
- ✅ Proper tax calculations based on check-in date
- ✅ Consistent with actual business operations

### Data Integrity

- Existing data in database may need recalculation if imported with old algorithm
- New imports will use correct algorithm
- Consider running a data migration script for historical Booking.com records

## Files Modified

1. `backend/src/str_processor.py` - Updated `_process_booking()` function
2. `specs/BDC-Algoritm-import-str_processor.py/Algoritm.md` - Created specification
3. `test_booking_algorithm.py` - Created test script
4. `BOOKING_ALGORITHM_UPDATE.md` - This summary document

## Next Steps

1. ✅ Algorithm implemented and tested
2. ⚠️ Consider recalculating existing Booking.com records in database
3. ⚠️ Update any reports or dashboards that depend on these calculations
4. ⚠️ Verify with actual Booking.com data to ensure accuracy

## Notes

- The uplift factor (1.03357) is constant and accounts for the tax structure
- Tourist tax is always calculated on VAT-exclusive amount
- All monetary values are rounded to 2 decimal places
- Commission amount from Booking.com is included in gross calculation
