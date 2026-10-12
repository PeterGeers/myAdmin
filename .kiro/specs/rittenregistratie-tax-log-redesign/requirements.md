# Requirements Document

## Introduction

The ZZP Rittenregistratie (trip/mileage registration) module is being redesigned to become a pure, Belastingdienst-compliant kilometer log for Dutch tax purposes. The module was originally requested as a simple trip register. During development, a kilometer-billing model (invoice-from-trips, unbilled-trips, billable/billed flags, and a formal contact link) was introduced that the owner never designed toward, never approved, and that is not meaningfully exposed in the trip UI.

This redesign removes all trip-billing code and data, replaces the formal contact link with a free-text client field, feeds route-preset learning from imported data, and fixes import-preview display so rejected rows explain themselves. The simple trip-entry experience (quick entry, odometer chaining, gap detection, category and purpose selection) is preserved and must not regress.

**Scope boundary:** This redesign touches ONLY the trip (rittenregistratie) module. It does NOT touch the standalone time-tracking and invoicing feature (ZZPTimeTracking, ZZPInvoices, zzp_invoice_service) or the `contacts` table and contacts feature. The only change affecting contacts is removing the contact_id link from the trips table; the contacts table and feature are left unchanged.

## Glossary

- **Rittenregistratie**: The trip/mileage registration module. After this redesign, a pure tax log that records kilometer trips for the Dutch Belastingdienst.
- **Trip_Module**: The system comprising the `zzp_trips` table and its backend routes, services, and frontend screens (ZZPTrips, ZZPTripQuick).
- **Belastingdienst**: The Dutch tax authority. A compliant kilometer log records date, from-address, to-address, start/end odometer, generated distance, category, purpose, and an optional client note.
- **Trip_Category**: One of the fixed tax categories a trip can belong to: Zakelijk (business), Privé (private), or Woon-werk (commute).
- **Client_Name**: A free-text field (`client_name VARCHAR(255) DEFAULT NULL`) on `zzp_trips` holding a client/Klant note. It has NO relationship to the formal contacts feature.
- **Klant**: The Dutch label for the client note shown in the UI, in CSV/Excel import headers, and in export columns. Maps to `Client_Name`.
- **Trip_Billing_Model**: The removed set of billing concepts — `is_billable`, `is_billed`, `invoice_id`, trip `contact_id` link, invoice-from-trips, unbilled-trips, and their indexes, routes, services, guards, and UI.
- **Contacts_Feature**: The separate, out-of-scope contacts domain (`contacts` table and related code). The owner considers it a real asset; it is not altered.
- **TimeTracking_Feature**: The separate, out-of-scope time-tracking and invoicing capability (ZZPTimeTracking, ZZPInvoices, zzp_invoice_service).
- **Import_Service**: The CSV/Excel import pipeline for trips (`zzp_trip_import_service.commit_import`).
- **Import_Preview**: The screen that previews rows parsed from an import file before committing, including per-row validation status.
- **Export_Service**: The trip export pipeline (`zzp_trip_export_service.py`).
- **Route_Preset**: An entry in `zzp_route_presets` representing a from-address/to-address pair, used to populate quick-entry suggestion cards. Auto-learned presets are created and ranked by use count; manual presets are user-created.
- **Route_Preset_Service**: The service managing route presets (`RoutePresetService`), including `increment_usage` and `get_suggestions`.
- **Quick_Entry**: The fast trip-entry screen (ZZPTripQuick) with odometer chaining, gap detection, category/purpose selects, and route-preset cards.
- **Migration_Runner**: The project migration mechanism (JSON migration files in `backend/src/migrations/`, applied by `DatabaseMigration.run_all_migrations()`).
- **Local_Docker**: The local development database (Docker MySQL), schema `finance`.
- **Railway_Production**: The production database on Railway, schema `finance`.
- **Administrator**: A human operator who approves and runs database migrations.

## Requirements

### Requirement 1: Rittenregistratie is a tax log

**User Story:** As a ZZP owner, I want the trip module to be a pure Belastingdienst kilometer log, so that I can produce a tax-compliant trip register without any billing concepts.

#### Acceptance Criteria

1. WHEN a user saves a trip, THE Trip_Module SHALL record the date, from-address, to-address, start odometer, end odometer, generated distance, Trip_Category, purpose, and an optional Client_Name note.
2. WHEN a user saves a trip, THE Trip_Module SHALL compute generated distance as end odometer minus start odometer, where start odometer and end odometer are each between 0 and 9,999,999 kilometers.
3. IF a user saves a trip where end odometer is less than start odometer, THEN THE Trip_Module SHALL reject the trip and present an error indicating that the end odometer must be greater than or equal to the start odometer, retaining the user-entered values without saving.
4. THE Trip_Module SHALL support exactly three Trip_Category values: Zakelijk, Privé, and Woon-werk.
5. IF a user saves a trip with a Trip_Category value other than Zakelijk, Privé, or Woon-werk, THEN THE Trip_Module SHALL reject the trip and present an error indicating that the Trip_Category is invalid, retaining the user-entered values without saving.
6. THE Trip_Module SHALL NOT present any invoicing, billing, or billable-amount concept to the user.
7. THE Trip_Module SHALL retain the `project_name` and `notes` fields on `zzp_trips` as non-billing trip data.

### Requirement 2: Klant is a free-text field

**User Story:** As a ZZP owner, I want to type a client name freely on a trip, so that I can note who a trip was for without linking to the formal contacts list.

#### Acceptance Criteria

1. THE Trip_Module SHALL store the Client_Name as a free-text value of 0 to 255 characters that defaults to null when no value is provided.
2. THE Trip_Module SHALL treat Client_Name as independent data with no reference to the Contacts_Feature.
3. WHEN a user enters a trip through Quick_Entry, THE Quick_Entry SHALL provide a free-text Klant input, accepting 0 to 255 characters, that writes Client_Name.
4. IF a user submits a Klant input exceeding 255 characters, THEN THE Quick_Entry SHALL reject the submission, retain the entered value for correction, and present an error indication that the Klant value exceeds the 255-character limit.
5. WHEN a user enters a trip through Quick_Entry with an empty Klant input, THE Quick_Entry SHALL store Client_Name as null.
6. WHEN the Trip_Module displays the trips list, THE Trip_Module SHALL display the Client_Name value in the Client column, and SHALL display an empty Client column cell when Client_Name is null.
7. WHEN an import file contains a `Klant` header, THE Import_Service SHALL map that column to Client_Name and persist the value, storing null when the cell is empty.
8. IF an import file row contains a Klant value exceeding 255 characters, THEN THE Import_Service SHALL reject that row, preserve any previously persisted Client_Name values for other rows, and record an error indication that the Klant value exceeds the 255-character limit.
9. WHEN a user exports trips, THE Export_Service SHALL populate the Klant column from Client_Name, and SHALL output an empty Klant value when Client_Name is null.

### Requirement 3: Remove the trip-billing data model

**User Story:** As a ZZP owner, I want all trip-billing columns removed from the trip table, so that the tax log carries no billing data.

#### Acceptance Criteria

1. WHEN the migration runs, THE Migration_Runner SHALL drop the `contact_id` foreign key constraint from `zzp_trips` before dropping any column, and IF the `contact_id` foreign key is still present when a column drop is attempted, THEN THE Migration_Runner SHALL abort the migration, leave `zzp_trips` unchanged, and surface an error indicating the foreign key must be dropped first.
2. WHEN the migration runs, THE Migration_Runner SHALL drop the columns `is_billable`, `is_billed`, `invoice_id`, and `contact_id` from `zzp_trips`, such that after completion a schema inspection of `zzp_trips` returns none of these four columns.
3. WHEN the migration runs, THE Migration_Runner SHALL drop the indexes `idx_admin_billable_contact`, `idx_admin_billed`, and `idx_admin_contact` from `zzp_trips`, such that after completion a schema inspection of `zzp_trips` returns none of these three indexes.
4. WHEN the migration completes, THE Migration_Runner SHALL retain the `project_name` and `notes` columns on `zzp_trips` with their pre-migration definitions unchanged.
5. WHEN the migration completes, THE Migration_Runner SHALL leave the `contacts` table and Contacts_Feature unchanged, such that a schema inspection of the `contacts` table before and after the migration returns identical definitions.
6. WHEN the `down` migration runs, THE Migration_Runner SHALL recreate the four dropped columns (`is_billable`, `is_billed`, `invoice_id`, `contact_id`), the three dropped indexes (`idx_admin_billable_contact`, `idx_admin_billed`, `idx_admin_contact`), and the `contact_id` foreign key, such that a schema inspection of `zzp_trips` after the `down` migration matches the pre-migration definition.
7. WHERE the target MySQL version is 9.4, THE Migration_Runner SHALL use index-drop statements that do not rely on `IF EXISTS`, and IF a referenced index does not exist when its drop statement runs, THEN THE Migration_Runner SHALL abort the migration, leave `zzp_trips` unchanged, and surface an error indicating the missing index.

### Requirement 4: Remove trip-billing backend behavior

**User Story:** As a ZZP owner, I want all trip-billing endpoints and logic removed from the backend, so that no billing path remains callable.

#### Acceptance Criteria

1. WHEN a client sends a request to the `POST /api/zzp/invoices/from-trips` endpoint, THE Trip_Module SHALL respond with a not-found status indicating the route is no longer registered, within 2 seconds.
2. WHEN a client sends a request to the `GET /api/zzp/trips/unbilled` endpoint, THE Trip_Module SHALL respond with a not-found status indicating the route is no longer registered, within 2 seconds.
3. IF a client sends a request to the list-trips route including an `is_billed` or `contact_id` query filter, THEN THE Trip_Module SHALL ignore the filter and return the full unfiltered trip result set, with no error attributable to the removed filter.
4. THE Trip_Module SHALL expose no callable `get_unbilled_trips` service path and no callable invoice-from-trips service path.
5. WHEN a client retrieves one or more trips, THE Trip_Module SHALL return each trip with no nested contact object and no `contact_id` field present in the response.
6. WHEN a user creates a trip or performs a gap-fill, THE Trip_Module SHALL persist the trip with no `contact_id`, `is_billable`, `is_billed`, or `invoice_id` field written to the stored record.
7. WHEN a user updates an existing trip with a valid payload, THE Trip_Module SHALL complete the update and persist the changes, applying no `is_billed`-based rejection regardless of any prior billing-related field value.
8. WHEN a user cancels an existing trip, THE Trip_Module SHALL complete the cancellation, applying no `is_billed`-based rejection regardless of any prior billing-related field value.

### Requirement 5: Remove trip-billing frontend surface

**User Story:** As a ZZP owner, I want all billing columns and actions removed from the trips UI, so that the screen reflects a pure tax log.

#### Acceptance Criteria

1. WHEN the trips list is rendered, THE Trip_Module SHALL display no "Fact." (is_billable) column and no cell derived from the is_billable field.
2. WHEN the trips UI is rendered, THE Trip_Module SHALL display no invoice-from-trips button and SHALL expose no handler that invokes createInvoiceFromTrips.
3. THE Trip_Module SHALL contain no hardcoded km_rate value (previously 0.23) anywhere in the trips UI or trip service.
4. THE trip service SHALL expose no getUnbilledTrips operation and SHALL return no billing-derived rows (fields sourced from is_billable or km_rate) in any trip retrieval.
5. THE frontend trip type definitions SHALL declare no billing-related fields (is_billable, km_rate, and invoice-from-trips payload types).
6. THE Trip_Module SHALL leave the TimeTracking_Feature screens (ZZPTimeTracking, ZZPInvoices) and the TimeTracking_Feature service unchanged, with zero modifications to their files.

### Requirement 6: Route presets learn from imported data

**User Story:** As a ZZP owner, I want imported trips to seed route presets, so that my real imported routes appear as quick-entry cards.

#### Acceptance Criteria

1. WHEN the Import_Service commits imported trips, THE Import_Service SHALL invoke Route_Preset learning once per successfully-committed (non-error) row, incrementing usage for that row's from-address/to-address pair, and SHALL NOT invoke learning for any row marked as an error.
2. WHEN the Import_Service invokes Route_Preset learning for a committed row whose from/to pair matches no existing Route_Preset after normalization (case-insensitive, leading/trailing whitespace trimmed), THE Route_Preset_Service SHALL create one auto-learned preset for that pair with a use count of 1 and a last-used timestamp set to the commit time.
3. WHEN the Import_Service invokes Route_Preset learning for a committed row whose normalized from/to pair matches an existing auto-learned Route_Preset, THE Route_Preset_Service SHALL increment that preset's use count by 1 and set its last-used timestamp to the commit time.
4. IF Route_Preset learning fails for a committed row, THEN THE Import_Service SHALL complete the trip import for that row, SHALL leave the import result as committed, and SHALL record a non-fatal indication that preset learning did not complete for that row.
5. WHEN a user opens Quick_Entry, THE Quick_Entry SHALL display all manual presets together with auto-learned presets whose last-used timestamp is within the preceding 6 months (182 days), ordered by use count descending, where the number of auto-learned presets shown is limited to the value of the `zzp_ritten.max_route_presets` parameter (minimum 0, default applied when the parameter is unset).
6. THE Trip_Module SHALL store `zzp_route_presets` as a table separate from imported trip records.

### Requirement 7: Import preview shows validation messages inline

**User Story:** As a ZZP owner, I want to see why each rejected import row failed, so that I understand import errors without hovering.

#### Acceptance Criteria

1. WHEN an import row fails validation, THE Import_Preview SHALL display that row's per-row validation message as visible inline text within the row, without requiring hover, focus, or any additional user interaction to reveal it.
2. WHEN an import row fails date validation, THE Import_Preview SHALL display inline the row's date-format validation message identifying the rejected value and the expected date format.
3. WHEN an import row has more than one validation message, THE Import_Preview SHALL display all of that row's messages inline, each shown as a separate, visually distinct entry.
4. WHEN an import row passes validation with zero validation messages, THE Import_Preview SHALL display no inline validation message for that row.
5. THE Import_Preview SHALL display a Klant column for every previewed row, populated with that row's Client_Name value, and SHALL show an empty Klant cell when Client_Name is absent or blank for that row.

### Requirement 8: Yearless Dutch dates are rejected

**User Story:** As a ZZP owner, I want yearless Dutch dates to be rejected with a clear reason, so that ambiguous dates never enter the tax log silently.

#### Acceptance Criteria

1. IF an import row contains a yearless date (a date value lacking a 4-digit year, such as `5-mei` or `17-mei`), THEN THE Import_Service SHALL reject that row and SHALL NOT infer or substitute any year for that value.
2. IF an import row contains a date value using a non-numeric month (including Dutch month names or abbreviations such as `mei`, `jan`, `dec`), THEN THE Import_Service SHALL reject that row.
3. WHEN an import row is rejected for an invalid date, THE Import_Service SHALL attach a per-row error message that includes the exact offending date value and the reason for rejection, within a maximum length of 500 characters.
4. WHEN an import row is rejected for an invalid date, THE Import_Service SHALL retain that row in the import preview marked as an error, and SHALL NOT drop or omit it from the preview.
5. WHEN an import row contains a date in one of the accepted formats (YYYY-MM-DD, DD-MM-YYYY, or DD/MM/YYYY with day and month either zero-padded or not, or a datetime/date object), THE Import_Service SHALL accept that date and SHALL NOT reject the row for date validity.

### Requirement 9: Production migration with human-confirmation gate

**User Story:** As an Administrator, I want the column-dropping migration applied safely with explicit approval before production, so that live tenant data is not lost accidentally.

#### Acceptance Criteria

1. THE Migration_Runner SHALL apply the billing-column-drop migration to Local_Docker before applying it to Railway_Production.
2. WHEN the Local_Docker migration completes, THE Migration_Runner SHALL report, within 10 seconds, whether each targeted billing column was removed and whether all pre-existing trip records remain readable.
3. WHILE the Local_Docker verification result has not confirmed that every targeted billing column is absent AND all pre-existing trip records are readable, THE Migration_Runner SHALL NOT target Railway_Production.
4. THE Migration_Runner SHALL apply the migration to Railway_Production only after receiving an explicit human go-ahead confirmation recorded for that specific migration.
5. IF no explicit human go-ahead confirmation is recorded for the migration, THEN THE Migration_Runner SHALL abort the Railway_Production run, leave Railway_Production data unchanged, and return an error indicating that human confirmation is required.
6. WHEN a migration has already been recorded as applied in the migration-tracking table, THE Migration_Runner SHALL skip re-applying that migration to the targeted environment and report it as already applied.
7. THE Trip_Module SHALL define the migration as a JSON migration file in `backend/src/migrations/` applied by `DatabaseMigration.run_all_migrations()`.

### Requirement 10: Preserve tax-log behavior and tenant isolation

**User Story:** As a ZZP owner, I want the simple trip-entry experience and tenant isolation preserved, so that removing billing does not regress the tax log.

#### Acceptance Criteria

1. WHEN the owner opens the Quick_Entry flow after billing removal, THE Trip_Module SHALL display the odometer start value pre-filled from the end odometer of the most recent prior trip for the same vehicle.
2. WHEN the owner saves a trip whose start odometer does not equal the end odometer of the most recent prior trip for the same vehicle, THE Trip_Module SHALL set the gap-detection flag on the saved trip.
3. WHEN the owner opens the Quick_Entry flow after billing removal, THE Trip_Module SHALL present a Trip_Category selection control and a purpose selection control, each requiring exactly one selection before the trip can be saved.
4. IF the owner attempts to save a trip without a Trip_Category selection or without a purpose selection, THEN THE Trip_Module SHALL reject the save, retain all entered trip values, and display an error indication identifying the missing selection.
5. THE Trip_Module SHALL scope every `zzp_trips` query to a single tenant by including the clause `WHERE administration = %s` bound to the requesting tenant's identifier.
6. IF a `zzp_trips` query is issued without a bound tenant identifier for the `administration` clause, THEN THE Trip_Module SHALL reject the query and return no trip rows.
7. WHEN the trip model changes, THE Trip_Module SHALL update the existing trip import, service, and preset tests so that all such tests execute against the changed model and pass.
