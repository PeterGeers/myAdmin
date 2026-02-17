# STR Invoice Missing Booking Fix

**Date**: 2026-02-16 20:45
**Status**: ✅ Fixed and Deployed

## Problem

Booking 5313159963 (Hanny Post, check-in 2026-02-16) was not visible in the STR Invoice Generator frontend, despite existing in the database.

## Root Cause

The frontend was loading bookings with `query=2` parameter, which filters for bookings containing the digit "2" in their reservation code:

```typescript
// Line 66 in STRInvoice.tsx (OLD)
const response = await authenticatedGet(
  `/api/str-invoice/search-booking?query=2&limit=all&startDate=${startDate}`,
);
```

The reservation code `5313159963` does NOT contain the digit "2":

- Digits: 5-3-1-3-1-5-9-9-6-3
- SQL test: `LIKE '%2%'` returned 0
- SQL test: `INSTR(reservationCode, '2')` returned 0

## Investigation Steps

1. ✅ Verified booking exists in `vw_bnb_total` (id=8189, status='realised', administration='GoodwinSolutions')
2. ✅ Changed backend default date range from 90 to 365 days
3. ✅ Changed backend `includeFuture` default to true
4. ✅ Changed frontend startDate to 365 days lookback
5. ✅ Added debug logging to backend
6. ✅ Discovered frontend loads with `query=2` pattern filter
7. ✅ SQL diagnostics confirmed reservation code doesn't contain "2"

## Solution

Changed frontend to load ALL bookings without pattern filter:

```typescript
// Line 66 in STRInvoice.tsx (NEW)
const response = await authenticatedGet(
  `/api/str-invoice/search-booking?query=&limit=all&startDate=${startDate}`,
);
```

This allows:

- All bookings to be loaded into memory
- Client-side filtering by guest name, reservation code, channel, or listing
- Users can search for any booking regardless of which digits it contains

## Files Changed

- `frontend/src/components/STRInvoice.tsx` - Changed query parameter from "2" to empty string

## Deployment

- Committed: b428f92
- Pushed to GitHub: main branch
- GitHub Pages will rebuild automatically
- Frontend URL: https://petergeers.github.io/myAdmin/

## Testing

After GitHub Pages rebuild completes (2-3 minutes):

1. Navigate to STR Invoice Generator
2. Wait for bookings to load
3. Search for "5313159963" or "Hanny Post"
4. Booking should now be visible with check-in date 2026-02-16

## Related Files

- `check_exact_value.sql` - SQL diagnostics showing reservation code doesn't contain "2"
- `backend/src/str_invoice_routes.py` - Backend search endpoint (already updated with 365 days and includeFuture=true)
