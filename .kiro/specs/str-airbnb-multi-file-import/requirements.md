# Requirements Document

## Introduction

Enhance the Airbnb import workflow to support uploading multiple CSV files simultaneously. Currently, each Airbnb listing export must be uploaded one file at a time, and sequential uploads for the same listing overwrite each other's planned bookings. This feature allows the user to select all Airbnb export files at once, concatenates them into a unified dataset, deduplicates by reservation code (`Bevestigingscode`), processes through the existing Airbnb algorithm, and correctly overwrites the planned bookings for the `airbnb` channel across all listings found in the combined data.

Airbnb exports are CSV-only files with Dutch column headers (e.g., `Begindatum`, `Einddatum`, `Inkomsten`, `Bevestigingscode`). The financial calculation derives gross amount from the paid-out amount (`Inkomsten`) using a 15% channel fee factor, then applies VAT and tourist tax via the shared `calculate_str_taxes()` pipeline. This is fundamentally different from Booking.com's uplift-factor-based calculation, requiring a dedicated `_process_airbnb_multi()` method.

## Glossary

- **Multi_File_Upload_Component**: The frontend file input element that accepts multiple Airbnb CSV files in a single selection when the `airbnb` platform is chosen.
- **File_Concatenator**: The backend logic within `STR_Processor` that reads multiple Airbnb CSV files, parses each into a pandas DataFrame, and concatenates them into a single unified DataFrame before processing.
- **STR_Processor**: The backend service (`str_processor.py`) responsible for parsing STR platform files and calculating financial amounts (gross, VAT, tourist tax, channel fee, net).
- **STR_Database**: The backend service (`str_database.py`) responsible for persisting booking records to the `bnb` and `bnbplanned` tables.
- **Upload_Endpoint**: The `POST /api/str/upload` Flask route that receives uploaded files, delegates to STR_Processor, and returns processed booking data.
- **Planned_Bookings_Store**: The `bnbplanned` MySQL table that holds future/planned booking records, keyed by channel and listing.
- **Listing_Normalizer**: The `_normalize_listing_name()` method that maps Airbnb listing name variations (e.g., "Advertentie" column values) to canonical listing names ("Green Studio", "Red Studio", "Child Friendly").
- **Airbnb_Algorithm**: The calculation pipeline that derives `amountGross`, `amountChannelFee`, `amountVat`, `amountTouristTax`, `amountNett`, and `pricePerNight` from the Airbnb paid-out amount (`Inkomsten`) using a 15% channel fee factor (`amountChannelFee = paidOut × 0.15`, `amountGross = paidOut + amountChannelFee`).
- **Channel_Listing_Pair**: A unique combination of `channel` (e.g., "airbnb") and `listing` (e.g., "Green Studio") used to scope delete-and-replace operations on the Planned_Bookings_Store.
- **Reservation_Code**: The `Bevestigingscode` column in Airbnb CSV exports, serving as the unique identifier for deduplication when the same reservation appears in multiple files.

## Requirements

### Requirement 1: Multi-File Selection for Airbnb

**User Story:** As an STR operator, I want to select multiple Airbnb export files at once, so that I do not have to repeat the upload process for each listing separately.

#### Acceptance Criteria

1. WHEN the user selects the `airbnb` platform, THE Multi_File_Upload_Component SHALL accept multiple file selections in a single file dialog.
2. WHEN multiple files are selected, THE Multi_File_Upload_Component SHALL display all selected filenames to the user.
3. THE Multi_File_Upload_Component SHALL accept files with extension `.csv` for the `airbnb` platform.
4. WHEN no files are selected, THE Multi_File_Upload_Component SHALL disable the process button.

### Requirement 2: File Concatenation

**User Story:** As an STR operator, I want the system to merge all uploaded Airbnb files into one dataset, so that all listings and date ranges are processed together.

#### Acceptance Criteria

1. WHEN multiple Airbnb files are uploaded, THE File_Concatenator SHALL read each CSV file into a DataFrame and concatenate them into a single unified DataFrame.
2. WHEN a file cannot be parsed due to an invalid format, THE File_Concatenator SHALL skip the invalid file, continue processing remaining files, and include the filename in an error list returned to the user.
3. WHEN duplicate booking records exist across files (same `Bevestigingscode`), THE File_Concatenator SHALL retain only one record per unique Reservation_Code, keeping the last occurrence.
4. IF all uploaded files fail to parse, THEN THE Upload_Endpoint SHALL return an error response with the list of failed filenames.

### Requirement 3: Combined Processing Through Existing Algorithm

**User Story:** As an STR operator, I want the concatenated data to be processed using the existing Airbnb algorithm, so that financial calculations remain accurate and consistent.

#### Acceptance Criteria

1. THE STR_Processor SHALL process the concatenated DataFrame using the same Airbnb_Algorithm as single-file imports (15% channel fee factor, `amountGross = paidOut + amountChannelFee`, tax rate determination by check-in date via `calculate_str_taxes()`).
2. THE Listing_Normalizer SHALL normalize all listing name values in the concatenated DataFrame to canonical listing names.
3. WHEN the concatenated data contains bookings for multiple listings, THE STR_Processor SHALL produce booking records for each listing found in the data.
4. THE STR_Processor SHALL set the `sourceFile` field to include the current date and a combined reference indicating multi-file import (e.g., "2025-07-15 multi-import (3 files)").
5. THE STR_Processor SHALL parse the Airbnb earnings field (`Inkomsten`) using European currency format (e.g., "€ 1.841,18") for all rows in the concatenated DataFrame.
6. WHEN a row has status `Geannuleerd` and zero earnings, THE STR_Processor SHALL skip that row during processing.

### Requirement 4: Correct Planned Bookings Overwrite Strategy

**User Story:** As an STR operator, I want the planned bookings for the `airbnb` channel to be fully replaced based on the combined import data, so that partial imports no longer cause data loss.

#### Acceptance Criteria

1. WHEN planned bookings from a multi-file import are saved, THE STR_Database SHALL delete existing `bnbplanned` records for each Channel_Listing_Pair found in the combined import data before inserting new records.
2. THE STR_Database SHALL preserve `bnbplanned` records for Channel_Listing_Pairs that are not present in the current import (e.g., `booking.com` listings or `airbnb` listings not included in the uploaded files).
3. WHEN the combined data contains bookings for listings "Green Studio" and "Red Studio", THE STR_Database SHALL delete and replace planned records for both `(airbnb, Green Studio)` and `(airbnb, Red Studio)`, while leaving `(airbnb, Child Friendly)` untouched if it is not in the import.

### Requirement 5: Upload Endpoint Multi-File Support

**User Story:** As a frontend developer, I want the upload API to handle multiple Airbnb files in a single request, so that the frontend can send all files at once.

#### Acceptance Criteria

1. WHEN multiple files are submitted to the Upload_Endpoint with platform `airbnb`, THE Upload_Endpoint SHALL pass all file paths to the STR_Processor for concatenated processing.
2. THE Upload_Endpoint SHALL return the same response structure as single-file uploads: `realised`, `planned`, `already_loaded` arrays and a `summary` object.
3. IF an error occurs during multi-file processing, THEN THE Upload_Endpoint SHALL return a JSON error response with HTTP status 500 and a descriptive error message.
4. THE Upload_Endpoint SHALL clean up all temporary files after processing completes, regardless of success or failure.

### Requirement 6: User Feedback for Multi-File Import

**User Story:** As an STR operator, I want clear feedback about the multi-file import results, so that I can verify all files and listings were processed correctly.

#### Acceptance Criteria

1. WHEN a multi-file Airbnb import completes successfully, THE Multi_File_Upload_Component SHALL display the total number of files processed.
2. WHEN a multi-file import completes, THE Multi_File_Upload_Component SHALL display the number of realised, planned, and already-loaded bookings found across all files.
3. WHEN one or more files fail to parse during a multi-file import, THE Multi_File_Upload_Component SHALL display a warning listing the failed filenames alongside the successful results.
4. WHEN the `airbnb` platform is selected, THE Multi_File_Upload_Component SHALL display an informational hint explaining that multiple files can be selected.
