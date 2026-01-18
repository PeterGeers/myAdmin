# Requirements Document: Fix STR Invoice Generator Database Query

## Introduction

The STR Invoice Generator is currently not loading booking data because it queries from an incorrect table name. The code queries `bnbtotal` (which doesn't exist) instead of the correct existing view `vw_bnb_total`.

**Current Problem:** Code uses `bnbtotal` → **Solution:** Change to `vw_bnb_total`

## Glossary

- **STR Invoice Generator**: Frontend component that allows users to search for bookings and generate invoices
- **vw_bnb_total**: Database view that combines `bnb` (actual bookings) and `bnbplanned` (future bookings)
- **bnbtotal**: Non-existent table name currently being queried (incorrect)
- **str_invoice_routes**: Backend Flask blueprint that handles invoice-related API endpoints

## Requirements

### Requirement 1: Fix Database Query in Search Endpoint

**User Story:** As a user, I want to search for bookings by guest name or reservation code, so that I can generate invoices for those bookings.

#### Acceptance Criteria

1. WHEN a user searches for bookings, THE System SHALL query the `vw_bnb_total` view instead of `bnbtotal`
2. WHEN the search query is executed, THE System SHALL return matching bookings from both actual (`bnb`) and planned (`bnbplanned`) tables via the view
3. WHEN search results are returned, THE System SHALL include all required fields: reservationCode, guestName, channel, listing, checkinDate, checkoutDate, nights, guests, amountGross
4. WHEN no results are found, THE System SHALL return an empty list with success status

### Requirement 2: Fix Database Query in Invoice Generation Endpoint

**User Story:** As a user, I want to generate an invoice for a selected booking, so that I can provide documentation to guests.

#### Acceptance Criteria

1. WHEN generating an invoice, THE System SHALL query the `vw_bnb_total` view instead of `bnbtotal`
2. WHEN the booking is found, THE System SHALL retrieve all financial fields: amountGross, amountTouristTax, amountChannelFee, amountNett, amountVat
3. WHEN the booking is not found, THE System SHALL return a 404 error with appropriate message
4. WHEN invoice data is retrieved, THE System SHALL pass it to the invoice generation function

### Requirement 3: Maintain Backward Compatibility

**User Story:** As a system administrator, I want the fix to maintain existing functionality, so that no other features are broken.

#### Acceptance Criteria

1. WHEN the view name is changed, THE System SHALL maintain the same query structure and parameters
2. WHEN results are returned, THE System SHALL maintain the same response format
3. WHEN errors occur, THE System SHALL maintain the same error handling behavior
4. THE System SHALL continue to work with both test_mode=False (production) and test_mode=True (test) configurations

## Technical Notes

### Current Issue

- **Incorrect:** Code queries `SELECT * FROM bnbtotal WHERE ...`
- **Correct:** Should query `SELECT * FROM vw_bnb_total WHERE ...`
- The view `vw_bnb_total` already exists and is correctly configured

### Files to Update

- `backend/src/str_invoice_routes.py` - Two SQL queries need updating:
  1. Line ~23: Search booking query - change `bnbtotal` to `vw_bnb_total`
  2. Line ~66: Generate invoice query - change `bnbtotal` to `vw_bnb_total`

### View Structure

The existing `vw_bnb_total` view combines:

- `bnb` table (actual/realized bookings)
- `bnbplanned` table (future/planned bookings)

This ensures the invoice generator can work with both past and future bookings.
