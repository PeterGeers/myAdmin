# Requirements Document

## Introduction

Airbnb changed its CSV export format. The new exports ship as two separate files that share
one column layout but differ by which columns are present, and each row now appears as a
`Boeking` / `Doorloop totaal` pair grouped by a shared `Bevestigingscode`, interleaved with
informational `Payout` rows. The previous parser was built for the old `reservation`-style
export: it read columns that no longer exist (`Inkomsten`, `Contact`, `# volwassenen`,
`Status`, `Gereserveerd`), parsed only European-formatted amounts, applied a hardcoded 15%
channel fee, and derived booking status from the check-in date relative to today.

This feature updates the Airbnb ingest path (file detection, parsing, calculation, and
persistence) to consume the new format while preserving the existing booking-dict output
contract and the existing tenant-scoped `bnb` / `bnbplanned` tables. The old `reservation`
format is replaced, not kept alongside.

### Impact Analysis (context captured for design)

The user asked what fields are available, which are new, and how re-import/refresh behaves.
This context informs the design and is recorded here so it is not lost.

**Fields available in the new exports** (shared header, in file order):
`Datum`, `Type`, `Bevestigingscode`, `Boekingsdatum`, `Begindatum`, `Einddatum`, `Nachten`,
`Gast`, `Advertentie`, `Informatie`, `Referentienummer`, `Valuta`, `Bedrag`, `Servicekosten`,
`Schoonmaakkosten`, `Bruto-inkomsten`, `Door Airbnb doorbelaste en afgedragen heffingen`,
`Inkomstenjaar`. The realised/past file additionally carries `Verwacht op`, `Uitbetaald`, and
`Kosten voor snelle uitbetaling`.

**Fields consumed** (map to the output contract): `Bevestigingscode` (grouping key +
`reservationCode`), `Boekingsdatum` (`reservationDate`, drives `daysBeforeReservation`),
`Begindatum` (`checkinDate`), `Einddatum` (`checkoutDate`), `Nachten` (`nights`), `Gast`
(`guestName`), `Advertentie` (`listing` via `normalize_listing_name`), `Bruto-inkomsten`
(summed into `amountGross`), `Servicekosten` (summed into `amountChannelFee`), `Informatie`
(feeds `addInfo` and country detection).

**New vs. old behavior**: channel fee now comes from summed `Servicekosten` instead of a
hardcoded 15%; amounts must accept both US-style (`274.80`) and quoted European (`"42,59"`,
`"1.234,56"`) formats; dates are `MM/DD/YYYY` (old format used `dd-mm-yyyy` / `yyyy-mm-dd`);
status is determined by which file the row came from, not by check-in-vs-today; guest count and
phone are no longer present, so the guest count defaults to 2 when absent.

**Re-import / refresh behavior**: re-importing the same file updates existing bookings in place
rather than duplicating them, keyed by `reservationCode` within a channel + administration,
mirroring the existing `upsert_direct_bookings` flow for realised bookings and applying the
same keyed-refresh semantics to planned bookings.

## Glossary

- **STR_System**: The short-term-rental ingest subsystem under `backend/src/str_*.py` that
  scans, parses, calculates, and persists rental bookings.
- **File_Scanner**: `str_processor.scan_str_files`, which classifies files in the download
  folder by platform.
- **Airbnb_Parser**: `str_airbnb_parser` (`process_airbnb_multi`, `calculate_airbnb_row`),
  which turns Airbnb CSV rows into booking dicts.
- **STR_Persistence**: `str_database`, which writes bookings to the `bnb` and `bnbplanned`
  tables.
- **Pending_File**: An Airbnb export that lacks the `Verwacht op`, `Uitbetaald`, and
  `Kosten voor snelle uitbetaling` columns. Its bookings are future/unpaid.
- **Realised_File**: An Airbnb export that contains the `Verwacht op`, `Uitbetaald`, and
  `Kosten voor snelle uitbetaling` columns. Its bookings are past/paid.
- **Booking_Group**: The set of rows sharing one non-blank `Bevestigingscode` value, normally a
  `Boeking` row and a `Doorloop totaal` row.
- **Payout_Row**: A row whose `Type` is `Payout` and whose `Bevestigingscode` is blank;
  informational only.
- **Booking_Dict**: The output record produced per booking, with the field shape defined in
  Requirement 8.
- **Channel_Fee**: The Airbnb service fee for a booking, computed as the sum of `Servicekosten`
  across the Booking_Group.
- **Gross_Amount**: The gross income for a booking, computed as the sum of `Bruto-inkomsten`
  across the Booking_Group.
- **Reservation_Code**: The `Bevestigingscode` value, used as the per-channel upsert key.

## Requirements

### Requirement 1: File detection and classification

**User Story:** As an operator, I want the new Airbnb exports recognized automatically, so that
I no longer have to rename files to the old `reservation` convention.

#### Acceptance Criteria

1. WHERE a CSV file header contains both a `Type` column and a `Bruto-inkomsten` column, THE File_Scanner SHALL classify that file as an Airbnb file.
2. WHERE a CSV file name contains the token `airbnb`, THE File_Scanner SHALL classify that file as an Airbnb file.
3. THE File_Scanner SHALL classify an Airbnb file as a Realised_File WHEN the header contains the `Uitbetaald` column and the `Verwacht op` column.
4. THE File_Scanner SHALL classify an Airbnb file as a Pending_File WHEN the header lacks the `Uitbetaald` column and lacks the `Verwacht op` column.
5. THE File_Scanner SHALL cease using the `reservation` file-name token as the Airbnb classification rule.

### Requirement 2: Row grouping by confirmation code

**User Story:** As an operator, I want each Airbnb booking assembled from its paired rows, so
that gross income and fees are complete per booking.

#### Acceptance Criteria

1. THE Airbnb_Parser SHALL group input rows into a Booking_Group by their non-blank `Bevestigingscode` value.
2. THE Airbnb_Parser SHALL produce exactly one Booking_Dict per Booking_Group.
3. WHERE a row is a Payout_Row, THE Airbnb_Parser SHALL exclude that row from Booking_Group creation.
4. THE Airbnb_Parser SHALL read booking attributes (dates, guest name, listing, nights, reservation date) from the rows within the Booking_Group.

### Requirement 3: Financial calculation

**User Story:** As a finance user, I want gross, fee, VAT, tourist tax, and net computed from
the summed rows, so that the recorded totals match the Airbnb payout.

#### Acceptance Criteria

1. THE Airbnb_Parser SHALL compute Gross_Amount as the sum of `Bruto-inkomsten` across all rows in the Booking_Group.
2. THE Airbnb_Parser SHALL compute Channel_Fee as the sum of `Servicekosten` across all rows in the Booking_Group.
3. THE Airbnb_Parser SHALL compute VAT, tourist tax, and net by calling `calculate_str_taxes` with Gross_Amount, the check-in date, Channel_Fee, the tax rate service, and the tenant.
4. THE Airbnb_Parser SHALL cease applying the hardcoded 15% channel-fee factor.
5. WHEN parsing the confirmation code `HMXDT8WAFF`, THE Airbnb_Parser SHALL produce Gross_Amount `351.47` and Channel_Fee `42.59`.
6. WHEN parsing the confirmation code `HMTFCHFWTP`, THE Airbnb_Parser SHALL produce Gross_Amount `109.36` and Channel_Fee `13.25`.

### Requirement 4: Amount parsing

**User Story:** As an operator, I want amounts parsed regardless of their notation, so that both
export styles produce correct numbers.

#### Acceptance Criteria

1. WHEN an amount value uses a period as the decimal separator (for example `274.80`), THE Airbnb_Parser SHALL parse it to the corresponding numeric value.
2. WHEN an amount value uses a comma as the decimal separator with a period thousands separator (for example `"1.234,56"`), THE Airbnb_Parser SHALL parse it to the corresponding numeric value.
3. WHEN an amount value uses a comma as the decimal separator without a thousands separator (for example `"42,59"`), THE Airbnb_Parser SHALL parse it to the corresponding numeric value.
4. IF an amount value is blank or non-numeric, THEN THE Airbnb_Parser SHALL treat that value as zero.

### Requirement 5: Date parsing and derived periods

**User Story:** As a finance user, I want dates read in the export's format, so that periods and
lead time are correct.

#### Acceptance Criteria

1. THE Airbnb_Parser SHALL parse `Begindatum`, `Einddatum`, and `Boekingsdatum` as `MM/DD/YYYY` dates.
2. THE Airbnb_Parser SHALL set `checkinDate` from `Begindatum`, `checkoutDate` from `Einddatum`, and `reservationDate` from `Boekingsdatum`.
3. THE Airbnb_Parser SHALL compute `daysBeforeReservation` as the number of days between the reservation date and the check-in date.
4. THE Airbnb_Parser SHALL derive `year`, `q`, and `m` from the check-in date.

### Requirement 6: Status and table routing by file

**User Story:** As a finance user, I want realised and planned bookings routed to the correct
table, so that reporting separates past from future stays.

#### Acceptance Criteria

1. WHERE a Booking_Group originates from a Pending_File, THE STR_System SHALL set its status to `planned`.
2. WHERE a Booking_Group originates from a Pending_File, THE STR_Persistence SHALL write the Booking_Dict to the `bnbplanned` table.
3. WHERE a Booking_Group originates from a Realised_File, THE STR_System SHALL set its status to `realised`.
4. WHERE a Booking_Group originates from a Realised_File, THE STR_Persistence SHALL write the Booking_Dict to the `bnb` table.
5. THE STR_System SHALL determine status from the source file classification rather than from the check-in date relative to the current date.

### Requirement 7: Guest, phone, and country handling

**User Story:** As an operator, I want absent guest/contact fields handled with sensible defaults
(guest count defaults to 2, phone empty) rather than invented values, so that reports stay
consistent without showing fabricated contact data.

#### Acceptance Criteria

1. WHERE the export provides no guest-count column, THE Airbnb_Parser SHALL set `guests` to `2`.
2. WHERE the export provides no contact or phone column, THE Airbnb_Parser SHALL set `phone` to an empty value.
3. THE Airbnb_Parser SHALL detect `country` from the additional-information text by calling `detect_country`.

### Requirement 8: Output contract

**User Story:** As a downstream consumer, I want the booking dict shape unchanged, so that
persistence and reporting continue to work without modification.

#### Acceptance Criteria

1. THE Airbnb_Parser SHALL emit each Booking_Dict with the fields `sourceFile`, `channel`, `listing`, `checkinDate`, `checkoutDate`, `nights`, `guests`, `amountGross`, `amountChannelFee`, `guestName`, `phone`, `reservationCode`, `reservationDate`, `status`, `addInfo`, `amountVat`, `amountTouristTax`, `amountNett`, `pricePerNight`, `year`, `q`, `m`, `daysBeforeReservation`, and `country`.
2. THE Airbnb_Parser SHALL set `channel` to `airbnb`.
3. THE Airbnb_Parser SHALL set `listing` to the result of `normalize_listing_name` applied to the `Advertentie` value.
4. THE Airbnb_Parser SHALL set `reservationCode` to the Booking_Group `Bevestigingscode` value.

### Requirement 9: Ignored columns

**User Story:** As an operator, I want irrelevant columns left uncaptured, so that empty or
zero-valued data does not pollute records.

#### Acceptance Criteria

1. THE Airbnb_Parser SHALL exclude `Schoonmaakkosten`, `Door Airbnb doorbelaste en afgedragen heffingen`, `Kosten voor snelle uitbetaling`, `Verwacht op`, `Uitbetaald`, `Datum`, `Referentienummer`, and `Inkomstenjaar` from calculation and output fields.
2. THE Airbnb_Parser SHALL treat currency as EUR without reading the `Valuta` column into an output field.
3. THE Airbnb_Parser SHALL use the `Boekingsdatum` column as the reservation date.

### Requirement 10: Re-import and refresh

**User Story:** As an operator, I want re-importing the same export to refresh existing
bookings, so that repeated imports do not create duplicates.

#### Acceptance Criteria

1. THE STR_Persistence SHALL use Reservation_Code as the upsert key within a given channel and administration.
2. WHEN a Booking_Dict has a Reservation_Code that is absent for the channel and administration, THE STR_Persistence SHALL insert a new record.
3. WHEN a Booking_Dict has a Reservation_Code that already exists for the channel and administration, THE STR_Persistence SHALL update the existing record.
4. THE STR_Persistence SHALL apply the keyed upsert to realised bookings in the `bnb` table and to planned bookings in the `bnbplanned` table.
