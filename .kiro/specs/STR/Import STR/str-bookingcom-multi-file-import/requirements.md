# Requirements Document

## Introduction

Enhance the Booking.com import workflow to support uploading multiple CSV/Excel files simultaneously. Currently, each Booking.com listing must be downloaded and imported one file at a time, which is slow and error-prone. When multiple files are imported sequentially for the same listing, the `bnbplanned` data gets overwritten per file instead of being combined. This feature allows the user to select all Booking.com export files at once, concatenates them into a unified dataset, identifies the listings involved, and correctly overwrites the planned bookings for the `booking.com` channel across all listings found in the combined data.

## Glossary

- **Multi_File_Upload_Component**: The frontend file input element that accepts multiple Booking.com CSV/Excel files in a single selection when the `booking` platform is chosen.
- **File_Concatenator**: The backend logic within `STRProcessor` that reads multiple Booking.com files, parses each into a pandas DataFrame, and concatenates them into a single unified DataFrame before processing.
- **STR_Processor**: The backend service (`str_processor.py`) responsible for parsing STR platform files and calculating financial amounts (gross, VAT, tourist tax, channel fee, net).
- **STR_Database**: The backend service (`str_database.py`) responsible for persisting booking records to the `bnb` and `bnbplanned` tables.
- **Upload_Endpoint**: The `POST /api/str/upload` Flask route that receives uploaded files, delegates to STR_Processor, and returns processed booking data.
- **Planned_Bookings_Store**: The `bnbplanned` MySQL table that holds future/planned booking records, keyed by channel and listing.
- **Listing_Normalizer**: The `_normalize_listing_name()` method that maps Booking.com unit type variations (e.g., "One-Bedroom Apartment", "Rode Studio") to canonical listing names ("Green Studio", "Red Studio", "Child Friendly").
- **Booking_Algorithm**: The calculation pipeline that derives `amountGross`, `amountChannelFee`, `amountVat`, `amountTouristTax`, `amountNett`, and `pricePerNight` from Booking.com base price and commission amount using the uplift factor (1.047826).
- **Channel_Listing_Pair**: A unique combination of `channel` (e.g., "booking.com") and `listing` (e.g., "Green Studio") used to scope delete-and-replace operations on the Planned_Bookings_Store.

## Requirements

### Requirement 1: Multi-File Selection for Booking.com

**User Story:** As an STR operator, I want to select multiple Booking.com export files at once, so that I do not have to repeat the upload process for each listing separately.

#### Acceptance Criteria

1. WHEN the user selects the `booking` platform, THE Multi_File_Upload_Component SHALL accept multiple file selections in a single file dialog.
2. WHEN multiple files are selected, THE Multi_File_Upload_Component SHALL display all selected filenames to the user.
3. THE Multi_File_Upload_Component SHALL accept files with extensions `.csv`, `.tsv`, `.xls`, and `.xlsx` for the `booking` platform.
4. WHEN no files are selected, THE Multi_File_Upload_Component SHALL disable the process button.

### Requirement 2: File Concatenation

**User Story:** As an STR operator, I want the system to merge all uploaded Booking.com files into one dataset, so that all listings and date ranges are processed together.

#### Acceptance Criteria

1. WHEN multiple Booking.com files are uploaded, THE File_Concatenator SHALL read each file into a DataFrame and concatenate them into a single unified DataFrame.
2. WHEN a file cannot be parsed due to an invalid format, THE File_Concatenator SHALL skip the invalid file, continue processing remaining files, and include the filename in an error list returned to the user.
3. WHEN duplicate booking records exist across files (same `Book number`), THE File_Concatenator SHALL retain only one record per unique `Book number`, keeping the last occurrence.
4. THE File_Concatenator SHALL support a mix of `.csv`, `.tsv`, `.xls`, and `.xlsx` files in a single upload batch.
5. IF all uploaded files fail to parse, THEN THE Upload_Endpoint SHALL return an error response with the list of failed filenames.

### Requirement 3: Combined Processing Through Existing Algorithm

**User Story:** As an STR operator, I want the concatenated data to be processed using the existing Booking.com algorithm, so that financial calculations remain accurate and consistent.

#### Acceptance Criteria

1. THE STR_Processor SHALL process the concatenated DataFrame using the same Booking_Algorithm as single-file imports (uplift factor 1.047826, tax rate determination by check-in date, channel fee calculation).
2. THE Listing_Normalizer SHALL normalize all unit type values in the concatenated DataFrame to canonical listing names.
3. WHEN the concatenated data contains bookings for multiple listings, THE STR_Processor SHALL produce booking records for each listing found in the data.
4. THE STR_Processor SHALL set the `sourceFile` field to include the current date and a combined reference indicating multi-file import (e.g., "2025-07-15 multi-import (3 files)").

### Requirement 4: Correct Planned Bookings Overwrite Strategy

**User Story:** As an STR operator, I want the planned bookings for the `booking.com` channel to be fully replaced based on the combined import data, so that partial imports no longer cause data loss.

#### Acceptance Criteria

1. WHEN planned bookings from a multi-file import are saved, THE STR_Database SHALL delete existing `bnbplanned` records for each Channel_Listing_Pair found in the combined import data before inserting new records.
2. THE STR_Database SHALL preserve `bnbplanned` records for Channel_Listing_Pairs that are not present in the current import (e.g., `airbnb` listings or `booking.com` listings not included in the uploaded files).
3. WHEN the combined data contains bookings for listings "Green Studio" and "Red Studio", THE STR_Database SHALL delete and replace planned records for both `(booking.com, Green Studio)` and `(booking.com, Red Studio)`, while leaving `(booking.com, Child Friendly)` untouched if it is not in the import.

### Requirement 5: Upload Endpoint Multi-File Support

**User Story:** As a frontend developer, I want the upload API to handle multiple Booking.com files in a single request, so that the frontend can send all files at once.

#### Acceptance Criteria

1. WHEN multiple files are submitted to the Upload_Endpoint with platform `booking`, THE Upload_Endpoint SHALL pass all file paths to the STR_Processor for concatenated processing.
2. THE Upload_Endpoint SHALL return the same response structure as single-file uploads: `realised`, `planned`, `already_loaded` arrays and a `summary` object.
3. IF an error occurs during multi-file processing, THEN THE Upload_Endpoint SHALL return a JSON error response with HTTP status 500 and a descriptive error message.
4. THE Upload_Endpoint SHALL clean up all temporary files after processing completes, regardless of success or failure.

### Requirement 6: User Feedback for Multi-File Import

**User Story:** As an STR operator, I want clear feedback about the multi-file import results, so that I can verify all files and listings were processed correctly.

#### Acceptance Criteria

1. WHEN a multi-file Booking.com import completes successfully, THE Multi_File_Upload_Component SHALL display the total number of files processed.
2. WHEN a multi-file import completes, THE Multi_File_Upload_Component SHALL display the number of realised, planned, and already-loaded bookings found across all files.
3. WHEN one or more files fail to parse during a multi-file import, THE Multi_File_Upload_Component SHALL display a warning listing the failed filenames alongside the successful results.
4. WHEN the `booking` platform is selected, THE Multi_File_Upload_Component SHALL display an informational hint explaining that multiple files can be selected.

### Requirement 7: Backward Compatibility

**User Story:** As an STR operator, I want single-file Booking.com imports to continue working as before, so that existing workflows are not disrupted.

#### Acceptance Criteria

1. WHEN a single Booking.com file is uploaded, THE STR_Processor SHALL process the file using the same logic as before this feature was introduced.
2. THE Upload_Endpoint SHALL maintain backward compatibility with single-file uploads for all platforms (airbnb, booking, vrbo, direct, payout).
3. WHEN a single file is uploaded for the `booking` platform, THE STR_Database SHALL apply the same delete-by-Channel_Listing_Pair strategy as multi-file imports.
