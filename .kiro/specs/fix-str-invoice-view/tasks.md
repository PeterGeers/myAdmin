# Implementation Plan: Fix STR Invoice Generator Database Query

## Overview

Simple bugfix to correct the database view name from `bnbtotal` to `vw_bnb_total` in two SQL queries within the STR invoice routes file.

## Tasks

- [x] 1. Update search booking query to use correct view name
  - Open `backend/src/str_invoice_routes.py`
  - Locate the search_booking function (around line 10-35)
  - Change `FROM bnbtotal` to `FROM vw_bnb_total` in the SQL query
  - _Requirements: 1.1_

- [x] 2. Update invoice generation query to use correct view name
  - In the same file `backend/src/str_invoice_routes.py`
  - Locate the generate_invoice function (around line 40-80)
  - Change `FROM bnbtotal` to `FROM vw_bnb_total` in the SQL query
  - _Requirements: 2.1_

- [x] 3. Test the search functionality
  - Start the backend server
  - Navigate to STR Invoice Generator in the frontend
  - Search for a known guest name or reservation code
  - Verify that results are returned
  - _Requirements: 1.2, 1.3, 1.4_

- [x] 4. Test the invoice generation functionality
  - Select a booking from search results
  - Click "Generate Invoice"
  - Verify that the invoice is generated successfully
  - Verify all financial fields are populated correctly
  - _Requirements: 2.2, 2.4_

- [x] 5. Verify error handling
  - Search for a non-existent reservation code
  - Verify appropriate error message is shown
  - _Requirements: 2.3_

## Notes

- This is a simple find-and-replace fix
- No new functionality is being added
- The view `vw_bnb_total` already exists in the database
- Both production and test modes should work after the fix
