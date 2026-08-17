# Implementation Plan: Import dfDirect (Guesty CSV)

## Overview

Replace the legacy Excel-based dfDirect import with a new Guesty CSV parser module, add file extension validation in the route layer, implement upsert-based duplicate handling, update the frontend ImportLinksPopup, and add optional Stripe enrichment as a post-import step.

## Tasks

- [x] 1. Create `str_direct_parser.py` module with CSV parsing and validation
  - [x] 1.1 Create `str_direct_parser.py` with header validation and date parsing
    - Create `backend/src/services/str_direct_parser.py` following the pattern of `str_airbnb_parser.py`
    - Implement `_validate_headers()` — case-insensitive, whitespace-trimmed check for all 13 required columns; return list of missing column names
    - Implement `_parse_guesty_date()` — parse "YYYY-MM-DD HH:MM AM/PM" and "YYYY-MM-DD" formats, return date string or None for invalid/unparsable dates
    - Validate extracted date is a real calendar date (month ≤ 12, day ≤ days-in-month)
    - _Requirements: 2.1, 2.2, 2.4, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 1.2 Implement row filtering and financial calculation logic
    - Implement status filtering: only process rows with STATUS == "confirmed" (case-insensitive, trimmed); skip empty/whitespace-only STATUS
    - Implement `_calculate_direct_row()` — set amountGross from TOTAL PAYOUT, calculate channel fee (4% of gross, half-up rounding to 2dp)
    - Call `calculate_str_taxes()` for VAT and tourist tax, compute amountNett and pricePerNight
    - Skip rows with TOTAL PAYOUT ≤ 0, non-numeric TOTAL PAYOUT, or zero/missing NUMBER OF NIGHTS (log warnings with confirmation code)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 1.3 Implement field mapping and `process_direct_csv()` public function
    - Map Guesty CSV columns to booking fields per design column mapping table
    - Set channel to "dfDirect", derive year/q/m from checkinDate, calculate daysBeforeReservation
    - Set sourceFile as "YYYY-MM-DD filename.csv", set status "planned"/"realised" based on checkinDate vs today
    - Call `normalize_listing_name()` for listing field, set phone to "", build addInfo string
    - Implement `process_direct_csv()` orchestrating validation → filtering → calculation → mapping
    - Return `{"bookings": [...], "status_updates": [...], "summary": {...}}` structure
    - Handle non-confirmed rows that have a reservationCode → collect as status_updates list
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 2.3, 2.5, 2.6, 8.5_

  - [x] 1.4 Write unit tests for `str_direct_parser.py`
    - Test header validation with missing columns, extra columns, case variations
    - Test date parsing with valid formats, invalid dates, empty values
    - Test row filtering by status (confirmed, canceled, empty, whitespace)
    - Test financial calculations (4% fee, tax integration, rounding)
    - Test field mapping completeness
    - Use test data from `.kiro/specs/myBacklog/testdate.csv` as reference
    - _Requirements: 2.1–2.6, 3.1–3.4, 4.1–4.7, 5.1–5.7, 6.1–6.5_

- [x] 2. Route and processor changes for direct platform
  - [x] 2.1 Add file extension validation in `str_routes.py`
    - In `str_upload_authenticated` (or equivalent upload handler), add validation for platform "direct"
    - Reject `.xls`/`.xlsx` with 400 and message: "Only CSV files are supported for the direct platform. Excel files (.xls/.xlsx) are no longer accepted."
    - Reject non-`.csv` extensions with 400 and message about unsupported file type
    - Allow `.csv` files to proceed to processing
    - _Requirements: 7.2, 7.3, 7.4_

  - [x] 2.2 Update `str_processor.py` to delegate to new parser
    - Replace `_process_direct()` method body with call to `process_direct_csv()`
    - Store processing summary on instance (`self._direct_processing_summary`)
    - Remove old `_calculate_direct_row()` method
    - _Requirements: 7.1_

  - [x] 2.3 Enhance route response with summary and already_loaded array
    - For dfDirect imports, build response with `realised`, `planned`, `already_loaded` arrays
    - Include `summary` object with total_bookings, realised_count, planned_count, skipped_count, updated_count, skipped_reasons
    - Ensure response structure matches other STR platform uploads
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 2.4 Write unit tests for route validation and processor delegation
    - Test file extension validation (csv accepted, xls/xlsx rejected, other rejected)
    - Test processor delegation to `process_direct_csv()`
    - Test summary response structure
    - _Requirements: 7.1–7.4, 9.1–9.4_

- [x] 3. Checkpoint - Core backend functionality
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Duplicate handling in database layer
  - [x] 4.1 Implement `upsert_direct_bookings()` in `str_database.py`
    - Query existing reservation codes for channel "dfDirect" and current tenant
    - For matching reservationCode: UPDATE checkinDate, checkoutDate, listing, guestName, nights, guests, amountGross, amountNett, amountChannelFee, amountVat, amountTouristTax, status, pricePerNight, sourceFile
    - For new reservationCode: INSERT full record
    - Apply status_updates for non-confirmed re-imported rows (update status only)
    - Return `{"inserted": int, "updated": int}` counts
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 4.2 Wire upsert into route/save flow
    - Replace direct INSERT call with `upsert_direct_bookings()` for dfDirect platform
    - Populate `already_loaded` array in response with updated duplicate records
    - Include `updated_count` in summary
    - _Requirements: 8.4, 9.4_

  - [x] 4.3 Write unit tests for duplicate handling
    - Test insert of new booking
    - Test update of existing booking (same reservationCode + dfDirect)
    - Test status update for non-confirmed re-import
    - Test counts returned correctly
    - _Requirements: 8.1–8.5_

- [x] 5. Frontend changes
  - [x] 5.1 Update ImportLinksPopup dfDirect section in `STRProcessor.tsx`
    - Replace current dfDirect static text with Guesty link and filter prompt
    - Add clickable link to `https://app.guesty.com/reservations?viewId=6a72237ce377681f84e3746c` opening in new tab
    - Add section heading consistent with other channels (Booking, Airbnb, VRBO)
    - Add filter prompt text below link: "Checkin is between 2 months ago and 1 year into the future for Platform Manual"
    - Style with teal.600 background, borderRadius md, matching existing link styling
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 5.2 Restrict file input to `.csv` for direct platform
    - Update file input `accept` attribute: when selectedPlatform is "direct", restrict to `.csv` only
    - Other platforms keep existing accepted extensions
    - _Requirements: 7.2_

  - [x] 5.3 Add translation keys for new UI text
    - Add keys to the appropriate i18n JSON file(s) under `str` namespace:
      - `processor.importDataLinks.dfDirect`: "Guesty Direct:"
      - `processor.importDataLinks.guestyReservations`: "Guesty Reservations"
      - `processor.importDataLinks.guestyFilterPrompt`: "Checkin is between 2 months ago and 1 year into the future for Platform Manual"
    - _Requirements: 1.1, 1.2_

- [x] 6. Checkpoint - Full CSV import flow complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Optional Stripe enrichment module
  - [x] 7.1 Create `str_stripe_enrichment.py` with 3-stage lookup
    - Create `backend/src/services/str_stripe_enrichment.py`
    - Implement `enrich_direct_bookings()` — accepts reservation_codes and optional amounts dict
    - Implement `_lookup_payment()` with 3-stage strategy: metadata search → description search → amount fallback
    - Implement `_search_by_metadata()` using configurable `STRIPE_GUESTY_METADATA_KEY` env var
    - Implement `_search_by_description()` using fuzzy description search
    - Implement `_search_by_amount()` — exact cents match, single-match-only constraint
    - Implement `_extract_customer_data()` — pull email/phone/country from PaymentIntent, Customer, PaymentMethod; extract actual Stripe processing fee from Charge's BalanceTransaction (fee field in cents → convert to euros)
    - Add rate-limit sleep (0.05s between calls)
    - Return `{"enrichments": [...], "not_found": [...], "errors": [...]}` where each enrichment includes `stripe_fee` (actual Stripe processing fee) when available
    - _Requirements: (optional enrichment, extends booking data quality)_

  - [x] 7.2 Add enrichment route and database methods
    - Add `POST /api/str/enrich-direct` route in `str_routes.py` with `@cognito_required` and `@tenant_required`
    - Accept optional `{"reservation_codes": [...]}` body; if absent, fetch unenriched codes
    - Implement `get_unenriched_direct_codes()` in `str_database.py` — query dfDirect bookings with empty phone/country, limit 50
    - Implement `apply_stripe_enrichments()` in `str_database.py` — update phone, country, append email to addInfo; when `stripe_fee` is present, replace estimated 4% amountChannelFee with actual Stripe fee and recalculate amountNett and pricePerNight
    - Return `{"success": true, "enriched": N, "not_found": N, "errors": [...]}`
    - _Requirements: (optional enrichment)_

  - [x] 7.3 Add frontend enrichment trigger after dfDirect save
    - After successful save of dfDirect bookings, fire `POST /api/str/enrich-direct` with reservation codes
    - Fire-and-forget pattern — show message if enrichment succeeds, silent on failure
    - Display enrichment count in existing message area
    - _Requirements: (optional enrichment)_

  - [x] 7.4 Write unit tests for Stripe enrichment module
    - Mock Stripe API calls (PaymentIntent.search, Customer.retrieve, PaymentMethod.retrieve)
    - Test 3-stage fallback logic (metadata found, description found, amount found, not found)
    - Test rate limiting behavior
    - Test `_extract_customer_data()` with various data availability scenarios
    - _Requirements: (optional enrichment)_

- [x] 8. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- The Stripe enrichment (task 7) is fully optional and independent of the core CSV import flow
- The `str_direct_parser.py` module follows the established pattern of `str_airbnb_parser.py` and `str_booking_parser.py`
- Test data is available at `.kiro/specs/myBacklog/testdate.csv` for reference during implementation
- The `normalize_listing_name()` and `calculate_str_taxes()` utilities already exist in `str_utils.py`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "5.3"] },
    { "id": 2, "tasks": ["1.3", "5.1", "5.2"] },
    { "id": 3, "tasks": ["1.4", "2.1", "2.2"] },
    { "id": 4, "tasks": ["2.3", "2.4"] },
    { "id": 5, "tasks": ["4.1"] },
    { "id": 6, "tasks": ["4.2", "4.3"] },
    { "id": 7, "tasks": ["7.1"] },
    { "id": 8, "tasks": ["7.2", "7.4"] },
    { "id": 9, "tasks": ["7.3"] }
  ]
}
```
