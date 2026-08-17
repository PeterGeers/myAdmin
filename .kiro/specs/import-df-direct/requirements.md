# Requirements Document

## Introduction

Replace the existing "Import Links Jabaki Direct" flow for the `dfDirect` channel with a new CSV-based import from Guesty. The current `_process_direct` method processes an Excel file with columns like `startDate`, `guestName`, `typeTrade`, etc. The new flow imports a Guesty CSV export with different column names and a simpler financial model: gross amount equals `TOTAL PAYOUT`, and channel fee is a fixed 4% of gross. Only rows with status "confirmed" are processed; all other statuses are skipped.

The import link changes from a local file reference to a Guesty reservation view URL, and the user receives a prompt describing the correct filter criteria to apply before exporting from Guesty.

## Glossary

- **STR_Processor**: The backend service (`str_processor.py`) responsible for parsing STR platform CSV files and calculating financial amounts (gross, VAT, tourist tax, channel fee, net).
- **Import_Links_Popup**: The frontend popup component within `STRProcessor.tsx` that displays external links and instructions for downloading import files per channel.
- **Guesty_CSV**: A CSV file exported from the Guesty platform containing reservation data with columns: CHECK-IN, CHECK-OUT, CONFIRMATION CODE, LISTING, GUEST, CREATION DATE, NUMBER OF NIGHTS, NUMBER OF GUESTS, STATUS, BALANCE DUE, TOTAL PAID, TOTAL PAYOUT, PLATFORM.
- **DfDirect_Channel**: The `dfDirect` channel identifier used in the STR booking database tables (`bnb` and `bnbplanned`) representing direct bookings managed via Guesty.
- **Upload_Endpoint**: The `POST /api/str/upload` Flask route that receives uploaded files and delegates to STR_Processor for processing.
- **Tax_Calculator**: The shared `calculate_str_taxes()` function that computes VAT and tourist tax from a gross amount and check-in date using date-dependent tax rates.
- **Listing_Normalizer**: The `normalize_listing_name()` function that maps listing name variations to canonical names (e.g., "Garden House / JaBaKi Garden House" → "Child Friendly").

## Requirements

### Requirement 1: Import Link Configuration

**User Story:** As an STR operator, I want the import link for dfDirect to point to the Guesty reservations view, so that I can quickly navigate to the correct page to export the CSV.

#### Acceptance Criteria

1. WHEN the Import_Links_Popup is displayed, THE Import_Links_Popup SHALL render the dfDirect import link as a clickable hyperlink with the URL `https://app.guesty.com/reservations?viewId=6a72237ce377681f84e3746c`.
2. WHEN the Import_Links_Popup is displayed, THE Import_Links_Popup SHALL display a visible prompt text adjacent to the dfDirect link: "Checkin is between 2 months ago and 1 year into the future for Platform Manual".
3. WHEN the user clicks the dfDirect import link, THE Import_Links_Popup SHALL open the link in a new browser tab.
4. WHEN the Import_Links_Popup is displayed, THE Import_Links_Popup SHALL display a section heading identifying the dfDirect channel, consistent with the heading style used for other channel sections (Booking, Airbnb, VRBO).

### Requirement 2: CSV File Parsing

**User Story:** As an STR operator, I want to upload a Guesty CSV export for dfDirect, so that the system processes my direct bookings from the new source format.

#### Acceptance Criteria

1. WHEN a CSV file is uploaded with platform `direct`, THE STR_Processor SHALL parse the Guesty_CSV expecting all 13 columns present: CHECK-IN, CHECK-OUT, CONFIRMATION CODE, LISTING, GUEST, CREATION DATE, NUMBER OF NIGHTS, NUMBER OF GUESTS, STATUS, BALANCE DUE, TOTAL PAID, TOTAL PAYOUT, PLATFORM. Column header matching SHALL be case-insensitive and SHALL ignore leading/trailing whitespace in header names.
2. WHEN parsing date columns (CHECK-IN, CHECK-OUT, CREATION DATE), THE STR_Processor SHALL interpret the format "YYYY-MM-DD HH:MM AM/PM" (e.g., "2026-06-12 02:00 PM") and extract only the date portion (YYYY-MM-DD), discarding the time component.
3. IF a CSV file cannot be parsed due to one or more of the 13 required columns being absent from the header row, THEN THE Upload_Endpoint SHALL return an error response with HTTP status 400 and a message listing the names of all missing columns.
4. THE STR_Processor SHALL trim leading and trailing whitespace from all parsed string values in the Guesty_CSV, including quoted values that contain padding spaces.
5. WHEN parsing numeric columns (NUMBER OF NIGHTS, NUMBER OF GUESTS, BALANCE DUE, TOTAL PAID, TOTAL PAYOUT), THE STR_Processor SHALL interpret values as decimal numbers, handling quoted numeric strings (e.g., "-360", "464") and treating empty or non-numeric values as zero.
6. IF the uploaded CSV file contains additional columns beyond the 13 required columns, THEN THE STR_Processor SHALL ignore the extra columns and process the file without error.

### Requirement 3: Row Filtering by Status

**User Story:** As an STR operator, I want only confirmed reservations to be imported, so that canceled or other non-active bookings do not pollute my booking data.

#### Acceptance Criteria

1. WHEN a row in the Guesty_CSV has STATUS equal to "confirmed", THE STR_Processor SHALL process that row into a booking record.
2. WHEN a row in the Guesty_CSV has STATUS not equal to "confirmed" (e.g., "canceled", "inquiry", "closed"), THE STR_Processor SHALL skip that row without producing a booking record.
3. THE STR_Processor SHALL trim leading and trailing whitespace from the STATUS field value and perform case-insensitive comparison when evaluating the status filter.
4. IF a row in the Guesty_CSV has a missing, empty, or whitespace-only STATUS field, THEN THE STR_Processor SHALL skip that row without producing a booking record.

### Requirement 4: Financial Calculation

**User Story:** As an STR operator, I want the gross amount and channel fee to be calculated correctly from the Guesty CSV data, so that my financial records are accurate.

#### Acceptance Criteria

1. THE STR_Processor SHALL set the gross amount (`amountGross`) to the numeric value in the TOTAL PAYOUT column for each processed row, parsed as a decimal number with 2 decimal places precision.
2. THE STR_Processor SHALL calculate the channel fee (`amountChannelFee`) as 4% of the gross amount (amountGross × 0.04), rounded to 2 decimal places using half-up rounding.
3. THE Tax_Calculator SHALL compute `amountVat` and `amountTouristTax` from the gross amount using the check-in date to determine the applicable tax rates.
4. THE STR_Processor SHALL calculate `amountNett` as: amountGross − amountChannelFee − amountVat − amountTouristTax, rounded to 2 decimal places.
5. THE STR_Processor SHALL calculate `pricePerNight` as amountNett divided by NUMBER OF NIGHTS, rounded to 2 decimal places.
6. IF the TOTAL PAYOUT value is zero or negative for a confirmed row, THEN THE STR_Processor SHALL skip that row without producing output for it.
7. IF the TOTAL PAYOUT value is non-numeric or the NUMBER OF NIGHTS value is zero or missing for a confirmed row, THEN THE STR_Processor SHALL skip that row and log a warning indicating the confirmation code and the reason for skipping.

### Requirement 5: Booking Record Mapping

**User Story:** As an STR operator, I want the CSV data to be correctly mapped to booking database fields, so that all booking details are stored consistently.

#### Acceptance Criteria

1. THE STR_Processor SHALL map Guesty_CSV columns to booking fields as follows: CHECK-IN → `checkinDate` (date only, YYYY-MM-DD), CHECK-OUT → `checkoutDate` (date only, YYYY-MM-DD), CONFIRMATION CODE → `reservationCode`, GUEST → `guestName`, CREATION DATE → `reservationDate` (date only, YYYY-MM-DD), NUMBER OF NIGHTS → `nights` (integer), NUMBER OF GUESTS → `guests` (integer).
2. THE STR_Processor SHALL set the `channel` field to "dfDirect" for all processed rows.
3. THE Listing_Normalizer SHALL normalize the LISTING column value to a canonical listing name ("Green Studio", "Child Friendly", or "Red Studio") based on keyword matching, and SHALL preserve the original LISTING value unchanged if no known pattern matches.
4. THE STR_Processor SHALL derive the `year` (4-digit integer), `q` (integer 1–4), and `m` (integer 1–12) fields from the `checkinDate`.
5. THE STR_Processor SHALL calculate `daysBeforeReservation` as `checkinDate` minus `reservationDate` in whole days, yielding zero when both dates are equal and a negative value when the reservation date is after the check-in date.
6. THE STR_Processor SHALL set the `sourceFile` field to the current server date followed by the uploaded filename (format: "YYYY-MM-DD filename.csv").
7. THE STR_Processor SHALL set the booking `status` to "planned" when the `checkinDate` is after the server's current date at time of processing, and "realised" when the `checkinDate` is equal to or before the server's current date.

### Requirement 6: CSV Date Format Parsing

**User Story:** As an STR operator, I want the system to correctly parse the Guesty date format, so that check-in, check-out, and creation dates are stored accurately.

#### Acceptance Criteria

1. WHEN parsing a date value in the format "YYYY-MM-DD HH:MM AM/PM" (e.g., "2026-06-12 02:00 PM"), THE STR_Processor SHALL extract and store only the date part (YYYY-MM-DD) for `checkinDate` and `checkoutDate`.
2. WHEN parsing the CREATION DATE column, THE STR_Processor SHALL extract and store the date part (YYYY-MM-DD) as `reservationDate`.
3. WHEN a date value contains only a date part (YYYY-MM-DD) without a time component, THE STR_Processor SHALL accept and store it as-is.
4. IF a date value is empty, null, or cannot be parsed into a valid date, THEN THE STR_Processor SHALL skip the row and log a warning that includes the row number (1-based, excluding header), the CONFIRMATION CODE value, and the unparsable date value.
5. IF the extracted date part does not represent a valid calendar date (e.g., month > 12 or day > days-in-month), THEN THE STR_Processor SHALL treat it as an unparsable date value.

### Requirement 7: Replace Existing Direct Import Logic

**User Story:** As a developer, I want the old direct import processing to be replaced with the new Guesty CSV logic, so that the codebase has a single, maintained import path for dfDirect.

#### Acceptance Criteria

1. WHEN platform `direct` is selected for upload with a `.csv` file, THE STR_Processor SHALL process it using the Guesty_CSV column structure (CHECK-IN, CHECK-OUT, CONFIRMATION CODE, LISTING, GUEST, CREATION DATE, NUMBER OF NIGHTS, NUMBER OF GUESTS, STATUS, BALANCE DUE, TOTAL PAID, TOTAL PAYOUT, PLATFORM) and SHALL NOT invoke the legacy Excel-based direct processing logic.
2. THE Upload_Endpoint SHALL accept `.csv` files for the `direct` platform and process them successfully when the file content is valid.
3. IF a file with extension `.xls` or `.xlsx` is uploaded for the `direct` platform, THEN THE Upload_Endpoint SHALL reject the file with HTTP status 400 and an error message indicating that only CSV files are supported for the direct platform.
4. IF a file with an extension other than `.csv`, `.xls`, or `.xlsx` is uploaded for the `direct` platform, THEN THE Upload_Endpoint SHALL reject the file with HTTP status 400 and an error message indicating the unsupported file type.

### Requirement 8: Duplicate Handling

**User Story:** As an STR operator, I want re-importing a CSV to update existing bookings rather than create duplicates, so that my data stays clean when I import updated exports.

#### Acceptance Criteria

1. THE STR_Processor SHALL use the CONFIRMATION CODE column (mapped to `reservationCode`) combined with channel "dfDirect" as the composite key for duplicate detection.
2. WHEN a booking in the CSV has a `reservationCode` that already exists in the `bnb` table for channel "dfDirect", THE STR_Processor SHALL update the existing record's checkinDate, checkoutDate, listing, guestName, nights, guests, amountGross, amountNett, amountChannelFee, and status fields with the values from the CSV row.
3. WHEN a booking in the CSV has a `reservationCode` that does not exist in the `bnb` table for channel "dfDirect", THE STR_Processor SHALL insert it as a new record.
4. WHEN a re-import completes, THE STR_Processor SHALL return a summary indicating the number of records inserted and the number of records updated.
5. IF a previously imported booking appears in the re-imported CSV with status not equal to "confirmed", THEN THE STR_Processor SHALL update the existing record's status to the new value without deleting the record.

### Requirement 9: User Feedback

**User Story:** As an STR operator, I want clear feedback after importing a dfDirect CSV, so that I can verify the import was successful and see how many bookings were processed or skipped.

#### Acceptance Criteria

1. WHEN a dfDirect CSV import completes successfully, THE Upload_Endpoint SHALL return a `summary` object containing: `total_bookings` (number of processed bookings), `realised_count` (number of realised bookings), `planned_count` (number of planned bookings), `skipped_count` (number of rows not imported), and `updated_count` (number of existing records updated via duplicate detection).
2. WHEN rows are skipped during import, THE Upload_Endpoint SHALL include a `skipped_reasons` object in the `summary` that maps each skip reason to its count (e.g., non-confirmed status, zero or negative payout, unparsable date).
3. THE Upload_Endpoint SHALL return the same top-level response structure as other STR platform uploads: `realised` array, `planned` array, `already_loaded` array (containing updated duplicate records), and a `summary` object.
4. WHEN a dfDirect CSV import completes successfully, THE Upload_Endpoint SHALL populate the `already_loaded` array with booking records that were updated because a matching `reservationCode` already existed for channel "dfDirect".
