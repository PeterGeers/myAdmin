# Requirements Document — Rittenregistratie (ZZP Module)

## Introduction

The Rittenregistratie (Trip/Mileage Registration) extends the ZZP module with legally compliant trip administration for Dutch freelancers. It supports both private vehicles used for business (claiming €0.23/km deduction) and business vehicles (tracking private use for bijtelling, max 500 km/year). The module integrates with existing ZZP contacts for client linking, the invoice engine for billable trips, and the parameter system for configuration.

The module is accessible both as part of the ZZP module and as a standalone route (`/Ritten`) for tenants that only need trip registration.

## Glossary

- **Trip (Rit)**: A single recorded journey with start/end location, km, purpose, and business/private classification
- **Vehicle (Voertuig)**: A registered car with license plate, type classification, and odometer tracking
- **Odometer (Kilometerstand)**: The cumulative distance reading of a vehicle's odometer at trip start/end
- **Business Trip (Zakelijke rit)**: A trip made for business purposes, deductible or billable
- **Private Trip (Privérit)**: A trip made for personal reasons, counted toward the 500 km bijtelling threshold for business cars
- **Bijtelling**: Dutch tax addition for private use of a company car; exempt if private use stays below 500 km/year
- **Km Rate (Kilometertarief)**: The per-kilometer rate used for billing or tax deduction, configurable per client/contract
- **Route Preset (Favoriete route)**: A saved frequently-used route (from → to) for quick trip entry
- **Trip Purpose (Ritdoel)**: The business reason for the trip (client visit, meeting, delivery, etc.)
- **Correction (Correctie)**: A modification to a previously saved trip, with mandatory reason and full audit trail

## Requirements

### Requirement 1: Vehicle Management

**User Story:** As a ZZP user, I want to register and manage my vehicles, so that I can track trips per vehicle and comply with Belastingdienst requirements.

#### Acceptance Criteria

1. THE system SHALL store the following attributes per vehicle: license plate (kenteken), make (merk), model (type), year (bouwjaar), VIN/chassis number (optional), vehicle type (private-for-business OR business), odometer unit (km or miles, default km), owner/lease company (optional), and active status
2. THE system SHALL support multiple vehicles per tenant
3. THE system SHALL require a start odometer reading when registering a new vehicle
4. THE system SHALL include an `administration` field for multi-tenant isolation
5. WHEN a vehicle is marked as "business", THE system SHALL track private km toward the 500 km/year bijtelling threshold
6. WHEN a vehicle is marked as "private-for-business", THE system SHALL track business km for the €0.23/km tax deduction
7. WHEN a vehicle has existing trip records, THE system SHALL prevent hard deletion of that vehicle (soft-delete only)

#### Success Metrics

- Vehicles can be added in under 30 seconds
- Odometer continuity is enforced (no gaps)

---

### Requirement 2: Trip Registration

**User Story:** As a ZZP user, I want to register individual trips with all legally required fields, so that my administration is Belastingdienst-compliant.

#### Acceptance Criteria

1. THE system SHALL record per trip: date, start time (optional), end time (optional), start address, end address, start odometer, end odometer, calculated distance (end - start), trip purpose (from configurable list), trip category (zakelijk/privé/woon-werk), vehicle reference, optional client/project reference, and optional notes
2. THE system SHALL automatically calculate the driven distance as end odometer minus start odometer
3. THE system SHALL pre-fill the start odometer with the end odometer of the previous trip for the same vehicle
4. THE system SHALL validate that end odometer > start odometer
5. THE system SHALL validate that the start odometer equals the end odometer of the previous chronological trip for that vehicle (no gaps)
6. WHEN the route deviates from the usual route between two addresses, THE system SHALL allow recording the actual route taken
7. THE system SHALL require at minimum: date, start address, end address, start odometer, end odometer, trip purpose, and trip category
8. THE system SHALL scope all trip data by tenant (`administration` field)
9. THE trip purpose SHALL be selected from a configurable parameter list (namespace: `zzp_ritten`, key: `trip_purposes`) — e.g., "Klantbezoek", "Vergadering", "Materiaal ophalen", "Overig"
10. THE trip category SHALL be one of: "Zakelijk", "Privé", "Woon-werk" — configurable via parameter (namespace: `zzp_ritten`, key: `trip_categories`, default: ["Zakelijk", "Privé", "Woon-werk"])

#### Success Metrics

- A routine trip (using preset) can be registered in under 15 seconds
- 100% of trips have the Belastingdienst-required fields filled

---

### Requirement 3: Route Presets (Favoriete Routes)

**User Story:** As a ZZP user who frequently drives the same routes, I want the system to suggest my most-used routes, so that I can register trips quickly without retyping addresses.

#### Acceptance Criteria

1. THE system SHALL automatically track route frequency (from-address → to-address combinations)
2. THE system SHALL present the top X most-used routes from the last 6 months as suggestions when creating a new trip
3. THE parameter "X" (number of presets shown) SHALL be configurable via the parameter system (namespace: `zzp_ritten`, key: `max_route_presets`, default: 5)
4. WHEN a user selects a route preset, THE system SHALL auto-fill start address, end address, trip category (zakelijk/privé/woon-werk), trip purpose, and (if consistent) the typical distance
5. THE system SHALL allow manual creation/editing/deletion of route presets
6. Route presets SHALL store: from-address, to-address, default trip category, default trip purpose, optional client reference, and optional typical distance
7. Route presets SHALL be scoped per tenant

#### Success Metrics

- After 2 weeks of use, 80% of trips use a preset route

---

### Requirement 4: Odometer Continuity & Gap Handling

**User Story:** As a ZZP user, I want the system to detect odometer gaps and help me resolve them without blocking my workflow, so that my records stay audit-proof while remaining easy to use.

#### Acceptance Criteria

1. THE system SHALL detect when a new trip's start odometer does not match the previous trip's end odometer for the same vehicle
2. WHEN a gap is detected, THE system SHALL warn the user but SHALL NOT block saving the trip
3. WHEN a gap is detected, THE system SHALL offer to auto-generate a "gap-fill" entry with: date (between the two trips), start km = previous end km, end km = current start km, category = "Privé", purpose = "Niet geregistreerd", and a `gap_fill: true` flag
4. THE gap-fill entries SHALL be visually distinct in the trip list (e.g., highlighted, badge, or different row style)
5. THE user SHALL be able to edit a gap-fill entry later: change the category, split it into multiple actual trips, or add a proper purpose
6. THE system SHALL detect and warn about: overlapping odometer readings, negative distances, and unusually large distances (configurable threshold via parameter)
7. THE system SHALL provide a "gap detection" report showing all gap-fill entries that still need attention (purpose = "Niet geregistreerd")
8. WHEN an explicit odometer correction is needed (e.g., vehicle dashboard reset, odometer repair), THE system SHALL allow a correction entry with mandatory explanation
9. Unresolved gap-fill entries SHALL count as "Privé" km for bijtelling calculations (worst-case assumption per Belastingdienst rules)

#### Success Metrics

- Trip registration is never blocked by odometer gaps
- Zero undetected odometer gaps in a calendar year
- All gap-fill entries are visually flagged for user attention

---

### Requirement 5: Trip Category Tracking & Bijtelling

**User Story:** As a ZZP user with a business car, I want to track my private and woon-werk kilometers against the 500 km threshold, so that I can maintain my bijtelling exemption.

#### Acceptance Criteria

1. THE system SHALL classify each trip into one of the configurable categories (default: "Zakelijk", "Privé", "Woon-werk")
2. FOR business vehicles, THE system SHALL maintain a running yearly total of non-business kilometers (Privé + Woon-werk) toward the 500 km bijtelling threshold
3. WHEN the yearly non-business km total approaches 500 km (configurable warning threshold, e.g., 400 km), THE system SHALL display a warning
4. THE system SHALL provide a dashboard widget showing: total km this year, per category (Zakelijk / Privé / Woon-werk), and remaining non-business km budget (for business vehicles)
5. FOR private-for-business vehicles, THE system SHALL maintain a running yearly total of business kilometers for tax deduction calculation
6. THE system SHALL calculate the tax deduction as business_km × configurable_rate (default €0.23/km)
7. "Woon-werk" trips SHALL count toward the bijtelling threshold (same as privé) per Belastingdienst rules

#### Success Metrics

- Bijtelling threshold warnings are shown at least 100 km before the limit

---

### Requirement 6: Client/Project Linking & Billing

**User Story:** As a ZZP user, I want to link trips to clients and optionally bill travel costs, so that I can include travel expenses on invoices.

#### Acceptance Criteria

1. THE system SHALL allow linking a trip to a contact from the ZZP Contact Registry
2. THE system SHALL allow linking a trip to a project (optional, free text or from time tracking projects)
3. THE km rate for billing SHALL be configurable per client/contract (stored on the contact or a contract record, NOT in the global parameter system)
4. WHEN a trip is linked to a client with a configured km rate, THE system SHALL calculate the billable amount (km × rate)
5. THE system SHALL support generating invoice line items from unbilled trips (similar to time entries → invoice flow)
6. WHEN trips are invoiced, THE system SHALL mark those trips as "billed" and link them to the invoice number
7. THE system SHALL prevent re-billing of already-billed trips
8. THE system SHALL provide a filter to show unbilled trips per client

#### Success Criteria

- Unbilled trips can be converted to invoice lines in under 3 clicks

---

### Requirement 7: Corrections & Audit Trail

**User Story:** As a ZZP user, I want to correct trip records with a full audit trail, so that my administration remains legally compliant even after modifications.

#### Acceptance Criteria

1. THE system SHALL never physically delete or overwrite trip records; all modifications create a new version
2. WHEN a trip is corrected, THE system SHALL require a correction reason (free text)
3. THE system SHALL store: who made the change, when, what changed (old value → new value), and the reason
4. THE system SHALL provide a correction history view per trip showing all versions
5. THE system SHALL allow "cancelling" a trip (soft-delete with reason) rather than deleting it
6. THE audit trail SHALL be immutable — corrections to the audit trail itself are not permitted

#### Success Metrics

- 100% of corrections have a documented reason
- Full trip history is reconstructable for any date

---

### Requirement 8: Reports & Export

**User Story:** As a ZZP user, I want to generate reports and exports of my trip data, so that I can submit them to the Belastingdienst or use them for my own administration.

#### Acceptance Criteria

1. THE system SHALL generate a PDF report with Belastingdienst-required fields: date, start address, end address, start km, end km, distance, purpose, business/private, per vehicle
2. THE PDF report SHALL be based on a configurable template (via the existing template system)
3. THE system SHALL support filtering reports by: date range, vehicle, business/private, client
4. THE system SHALL provide summary reports: total km per month/quarter/year, split by business/private, per vehicle
5. THE system SHALL support Excel/CSV export of trip data
6. THE system SHALL generate a yearly summary suitable for tax declaration (aangifte IB)

#### Success Metrics

- PDF report generation completes in under 5 seconds for a full year of data

---

### Requirement 9: ~~Standalone Access~~ REMOVED

_Replaced by Requirement 11 (Mobile-Optimized Quick Entry). The `/Ritten/quick` route provides the accessible standalone experience without needing a separate module registration. The Rittenregistratie is part of the ZZP module only._

---

### Requirement 10: Parameter Configuration

**User Story:** As a tenant administrator, I want to configure trip registration parameters, so that the system matches my specific business needs.

#### Acceptance Criteria

1. THE following SHALL be configurable via the parameter system (namespace: `zzp_ritten`):
   - `max_route_presets`: Number of route suggestions shown (default: 5)
   - `bijtelling_warning_threshold`: Km before 500 limit to show warning (default: 400)
   - `large_distance_warning`: Km threshold for "unusually large trip" warning (default: 300)
   - `default_km_rate`: Default km rate for tax deduction (default: 0.23)
   - `bijtelling_limit`: Private km limit for business cars (default: 500)
   - `trip_categories`: List of trip categories (default: ["Zakelijk", "Privé", "Woon-werk"])
   - `trip_purposes`: List of trip purposes (default: ["Klantbezoek", "Vergadering", "Materiaal ophalen", "Overig"])
2. THE km rate for CLIENT BILLING SHALL NOT be in the parameter system but stored per client/contract
3. ALL parameters SHALL be tenant-scoped

#### Success Metrics

- Parameters can be adjusted without code changes

---

### Requirement 11: Mobile-Optimized Quick Entry

**User Story:** As a ZZP user on the road, I want to register trips quickly from my phone without navigating complex menus, so that I can record trips immediately before I forget the details.

#### Acceptance Criteria

1. THE system SHALL provide a dedicated quick-entry view (`/Ritten/quick`) optimized for mobile screens
2. THE quick-entry view SHALL present a single-screen form with large, touch-friendly controls (minimum 44px tap targets)
3. THE quick-entry view SHALL show route presets as tappable cards (not dropdowns) for one-tap selection
4. THE quick-entry view SHALL auto-fill the start odometer from the last trip for the active vehicle
5. THE quick-entry view SHALL support "Start Rit" / "Stop Rit" workflow: tap start (captures time), drive, tap stop (captures time + enter end odometer)
6. THE quick-entry view SHALL NOT display the full application sidebar/navigation; only a minimal header with back button
7. THE system SHALL support "Add to Home Screen" (PWA manifest) so the quick-entry URL can be saved as a phone app icon
8. THE system SHALL use responsive Chakra UI design — the same React app, no separate codebase
9. THE system SHALL retain full Cognito authentication on mobile (persistent session)
10. THE quick-entry view SHALL default to the most recently used vehicle if the tenant has multiple vehicles

#### Success Metrics

- A trip using a route preset can be completed in under 15 seconds on mobile
- The quick-entry view loads in under 2 seconds on a 4G connection

---

### Requirement 12: ~~GPS Location Capture & Distance Calculation~~ MOVED TO FUTURE

_Moved to Future Considerations. The odometer chain + gap detection provides sufficient data integrity. GPS coordinates don't add legal value for the Belastingdienst and the OpenRouteService distance calculation only catches typos that odometer validation already handles._

---

### Requirement 13: CSV/Excel Import of Historical Trips

**User Story:** As a ZZP user switching from another system (Excel, paper, or another app), I want to import my historical trip records, so that I have a complete archive in one place.

#### Acceptance Criteria

1. THE system SHALL support importing trips from CSV and Excel (.xlsx) files
2. THE system SHALL provide a column mapping interface where the user maps file columns to trip fields (date, start address, end address, start km, end km, purpose, category, client, notes)
3. THE system SHALL validate imported records for: odometer continuity (no gaps/overlaps), required fields present, valid date format, end km > start km
4. THE system SHALL show a preview of parsed records with validation status (OK / warning / error) before committing the import
5. THE system SHALL skip or flag duplicate records (same vehicle + date + start km + end km)
6. THE system SHALL assign all imported trips to the selected vehicle
7. THE system SHALL support importing trips in bulk (hundreds/thousands of records in one file)
8. WHEN validation errors exist, THE system SHALL allow the user to fix or skip individual records before finalizing
9. THE system SHALL log the import action in the audit trail (who, when, how many records, source filename)
10. THE system SHALL provide a downloadable template (CSV) with the expected column format and example data

#### Success Metrics

- A 500-record CSV import completes in under 30 seconds
- Import validation catches 100% of odometer continuity issues before commit

---

## Out of Scope (Phase 1)

The following are explicitly NOT in scope for the initial implementation:

- **Background GPS tracking** — No continuous tracking, OBD-II, or connected car integration
- **Multiple drivers per vehicle** — Single-user ZZP context; no driver management
- **Fuel registration** — Not part of trip registration
- **Maintenance/APK tracking** — Not part of trip registration
- **Geofencing** — Not applicable for manual entry
- **CO₂ reporting** — Not in initial scope
- **Woon-werk detection** — No automatic classification
- **Calendar integration** — No automatic trip creation from calendar events
- **Offline mode** — Requires mobile data/WiFi connection

## Future Considerations (Phase 2+)

- GPS location capture (browser geolocation at trip start/end for evidence)
- OpenRouteService distance calculation (validation aid, typo detection)
- Recurring trip templates (e.g., weekly client visit)
- Dashboard widgets for bijtelling status
- Integration with bank transactions (parking, fuel matched to trips)
- PWA with offline support and background sync
- Woon-werk automatic detection based on address patterns
