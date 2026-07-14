# Implementation Plan

## Overview

Rittenregistratie (Trip/Mileage Registration) for the ZZP module — legally compliant trip administration for Dutch freelancers. Supports private vehicles (€0.23/km deduction) and business vehicles (bijtelling tracking, max 500 km/year private use).

The implementation is organized in 5 waves. Tasks within a wave can be executed in parallel. Each wave completes before the next starts.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 1, "tasks": ["1", "2", "3"] },
    { "id": 2, "tasks": ["4", "5", "6", "7"] },
    { "id": 3, "tasks": ["8", "9", "10", "11", "12"] },
    { "id": 4, "tasks": ["13", "14", "15", "16"] },
    { "id": 5, "tasks": ["17", "18", "19"] }
  ]
}
```

## Tasks

### Wave 1: Foundation (~1 day)

**Parallelism: 3 tracks can run simultaneously**

No dependencies — all tracks start immediately.

---

- [x] 1. Database & Migrations
     **Covers:** Requirements 1, 2, 3, 4, 7, 10
  - [x] 1.1 Create migration for `zzp_vehicles` table (2h)
    - license_plate, make, model, year, vin, vehicle_type ENUM('private_for_business','business'), odometer_unit ENUM('km','miles') DEFAULT 'km', start_odometer, owner_company, is_active, administration, tenant indexes
  - [x] 1.2 Create migration for `zzp_trips` table with generated `distance_km` column (2h)
    - date, start_time, end_time, start_address, end_address, start_odometer, end_odometer, distance_km AS (end_odometer - start_odometer) STORED, trip_purpose, trip_category, vehicle_id FK, contact_id FK (nullable), project_ref, notes, is_billable, is_billed, invoice_id, is_cancelled, cancel_reason, is_gap_fill, version DEFAULT 1, administration
  - [x] 1.3 Create migration for `zzp_trip_audit` table (1h)
    - trip_id FK, action ENUM('created','updated','cancelled','imported'), changed_fields JSON, old_values JSON, new_values JSON, correction_reason, changed_by, changed_at
  - [x] 1.4 Create migration for `zzp_route_presets` table (1h)
    - from_address, to_address, default_category, default_purpose, contact_id FK (nullable), typical_distance, use_count, last_used_at, is_manual, administration
  - [x] 1.5 Add `km_rate DECIMAL(10,4) DEFAULT NULL` column to `contacts` table (30min)
  - [x] 1.6 Run migrations, verify tables exist in dev environment (30min)
  - Testing: Migrations apply cleanly, correct indexes/constraints, generated column works.

---

- [x] 2. Parameter Registration
     **Covers:** Requirement 10
  - [x] 2.1 Register `zzp_ritten` parameters in MODULE_REGISTRY (1h)
    - `max_route_presets` (default: 5)
    - `bijtelling_warning_threshold` (default: 400)
    - `large_distance_warning` (default: 300)
    - `default_km_rate` (default: 0.23)
    - `bijtelling_limit` (default: 500)
    - `trip_categories` (default: ["Zakelijk", "Privé", "Woon-werk"])
    - `trip_purposes` (default: ["Klantbezoek", "Vergadering", "Materiaal ophalen", "Overig"])
  - Testing: Parameters accessible via ParameterService, tenant-scoped correctly.

---

- [x] 3. Frontend Types & i18n
     **Covers:** All requirements (frontend foundation)
  - [x] 3.1 Create `types/zzpTrips.ts` — Vehicle, Trip, RoutePreset, TripSummary, TripFilters, GapFillData, TripAuditEntry, ImportRow types (1h)
  - [x] 3.2 Add i18n translations (NL + EN) under `trips.*` namespace (1h)
    - Form labels, validation messages, status badges, export options, category/purpose labels
  - Testing: TypeScript compilation passes, translation keys load in both locales.

---

### Wave 2: Core Backend Services (~1.5 days)

**Parallelism: 4 tracks can run simultaneously**

Dependencies: Wave 1 complete (database tables exist, parameters registered, types defined).

---

- [x] 4. Vehicle Service & Routes
     **Covers:** Requirement 1
  - [x] 4.1 Create `VehicleService` class with CRUD methods (2h)
    - `create_vehicle`, `update_vehicle`, `deactivate_vehicle`, `get_vehicle`, `list_vehicles`, `get_last_odometer`
    - Enforce: unique license plate per tenant, cannot change start_odometer if trips exist
  - [x] 4.2 Create `zzp_trip_routes.py` Blueprint with vehicle endpoints (2h)
    - GET/POST `/api/zzp/vehicles`, PUT/DELETE `/api/zzp/vehicles/{id}`
    - Decorator chain: `@cognito_required` → `@tenant_required()` → `@module_required('ZZP')`
  - [x] 4.3 Register Blueprint in `app.py` (15min)
  - [x] 4.4 Write unit tests for VehicleService (2h)
  - [x] 4.5 Write API tests for vehicle endpoints (1h)
  - Testing: All CRUD operations, edge cases (duplicate plate, deactivate with trips, odometer immutability).

---

- [x] 5. Trip Service — Core CRUD
     **Covers:** Requirements 2, 5
  - [x] 5.1 Create `TripService` class extending `FieldConfigMixin` (3h)
    - `create_trip`, `get_trip`, `list_trips` with filtering
    - Validate: end_odometer > start_odometer, required fields from config
    - Auto-calculate: distance_km handled by DB generated column
  - [x] 5.2 Implement trip category validation against parameter list (1h)
    - Fetch `trip_categories` and `trip_purposes` from ParameterService
    - Validate submitted values are in the configured lists
  - [x] 5.3 Implement `enrich_with_contacts` for trip listings (1h)
  - [x] 5.4 Add trip CRUD routes to Blueprint (2h)
    - GET/POST `/api/zzp/trips`, GET `/api/zzp/trips/{id}`
  - [x] 5.5 Implement bijtelling tracking in `get_summary` method (2h)
    - Yearly totals per category, warning flag when threshold approached
    - Respect `odometer_unit` (convert miles→km for calculations if needed)
  - [x] 5.6 Write unit tests for TripService (3h)
  - Testing: CRUD operations, field validation, category validation, odometer validation, bijtelling calculation.

---

- [x] 6. Route Preset Service
     **Covers:** Requirement 3
  - [x] 6.1 Create `RoutePresetService` (2h)
    - `get_suggestions(tenant, limit)` — top X by use_count in last 6 months + manual presets
    - `create_preset`, `update_preset`, `delete_preset`
    - `increment_usage(tenant, from_address, to_address)` — upsert on usage
  - [x] 6.2 Add route preset endpoints (1h)
    - GET/POST/PUT/DELETE `/api/zzp/route-presets`
  - [x] 6.3 Write unit tests for RoutePresetService (1h)
  - Testing: Usage tracking, suggestion ordering by frequency, manual preset CRUD, 6-month window filter.

---

- [x] 7. Frontend Service Layer
     **Covers:** All requirements (API integration)
  - [x] 7.1 Create `services/tripService.ts` — all trip API calls (1.5h)
    - CRUD, filtering, summary, export, gap-fill, import
  - [x] 7.2 Create `services/vehicleService.ts` — vehicle API calls (1h)
  - [x] 7.3 Create `services/routePresetService.ts` — preset API calls (30min)
  - Testing: TypeScript compilation, service functions callable with correct types.

---

### Wave 3: Extended Backend Logic (~2 days)

**Parallelism: 4 tracks run simultaneously (12 starts after 8)**

Dependencies: Wave 2 core services complete.

---

- [x] 8. Odometer Gap Detection & Handling
     **Covers:** Requirement 4
  - [x] 8.1 Implement `detect_gap` method in TripService (2h)
    - Query previous trip's end_odometer for same vehicle
    - Compare with new trip's start_odometer
    - Return gap info or None
  - [x] 8.2 Integrate gap detection into `create_trip` (1h)
    - On gap: save trip anyway, add `warnings[]` and `gap_fill_offer` to response
  - [x] 8.3 Implement `create_gap_fill` method (1h)
    - Creates trip with `is_gap_fill = true`, category "Privé", purpose "Niet geregistreerd"
  - [x] 8.4 Add `POST /api/zzp/trips/gap-fill` endpoint (1h)
  - [x] 8.5 Implement `get_unresolved_gaps` — list gap-fill entries still unresolved (1h)
  - [x] 8.6 Add `GET /api/zzp/trips/gaps` endpoint (30min)
  - [x] 8.7 Implement large distance warning (parameter-driven threshold) (30min)
  - [x] 8.8 Write unit tests for gap detection and gap-fill creation (2h)
  - Testing: Gap detected, gap-fill created, no gap when odometers match, large distance warning triggered.

---

- [x] 9. Corrections & Audit Trail
     **Covers:** Requirement 7
  - [x] 9.1 Implement `update_trip` with version incrementing and audit logging (2h)
    - Require `correction_reason`
    - Compute changed_fields diff (old → new)
    - Insert into `zzp_trip_audit`
    - Increment trip `version`
  - [x] 9.2 Implement `cancel_trip` (soft-delete with reason) (1h)
    - Set `is_cancelled = true`, `cancel_reason`
    - Write audit entry with action "cancelled"
  - [x] 9.3 Implement `get_trip_history` — query audit table for a trip (1h)
  - [x] 9.4 Add routes: PUT `/api/zzp/trips/{id}`, DELETE `/api/zzp/trips/{id}`, GET `/api/zzp/trips/{id}/history` (1.5h)
  - [x] 9.5 Block editing/cancelling of billed trips (30min)
  - [x] 9.6 Write audit "created" entry on trip creation (retroactive for `create_trip`) (30min)
  - [x] 9.7 Write unit tests for corrections and audit trail (2h)
  - Testing: Version increments, audit entries created, billed trips blocked, history retrieval correct.

---

- [x] 10. Client Billing Integration
      **Covers:** Requirement 6
  - [x] 10.1 Implement `get_unbilled_trips` in TripService (1h)
    - Filter: tenant + contact_id + is_billable=true + is_billed=false + is_cancelled=false
  - [x] 10.2 Implement `mark_as_billed` in TripService (1h)
  - [x] 10.3 Add `create_invoice_from_trips` to ZZP Invoice Service (3h)
    - Mirror time-entries-to-invoice pattern
    - One invoice line per trip: description, quantity=distance_km, unit_price=km_rate
    - Validate all trips same contact, not already billed
    - Mark trips as billed after invoice creation
  - [x] 10.4 Add endpoints: GET `/api/zzp/trips/unbilled`, POST `/api/zzp/invoices/from-trips` (1.5h)
  - [x] 10.5 Write unit tests for billing flow (2h)
  - Testing: Unbilled retrieval, invoice creation, trips marked as billed, re-billing blocked.

---

- [x] 11. Reports & Export
      **Covers:** Requirement 8
  - [x] 11.1 Create `TripExportService` (1h)
  - [x] 11.2 Implement `export_csv` — pandas DataFrame → CSV bytes (1.5h)
    - Columns: Datum, Vertrekadres, Bestemming, Begin KM, Eind KM, Afstand, Categorie, Doel, Klant
  - [x] 11.3 Implement `export_xlsx` — openpyxl with styled headers (1.5h)
  - [x] 11.4 Implement `export_pdf` — HTML template → PDF via template system (2h)
    - Belastingdienst-compliant format: per vehicle, per year, all required fields
    - Yearly totals at bottom (zakelijk/privé/woon-werk)
  - [x] 11.5 Implement `get_yearly_summary` — aggregated yearly data (1h)
  - [x] 11.6 Add `GET /api/zzp/trips/export?vehicle_id=&year=&format=` endpoint (1h)
  - [x] 11.7 Add `GET /api/zzp/trips/summary?vehicle_id=&year=` endpoint (30min)
  - [x] 11.8 Write unit tests for export services (1.5h)
  - Testing: CSV/XLSX/PDF generation, correct totals, filtering by date/vehicle.

---

- [x] 12. CSV/Excel Import
      **Covers:** Requirement 13
      **Dependencies:** Task 8 (gap detection) must complete first
  - [x] 12.1 Create `TripImportService` (1h)
  - [x] 12.2 Implement `parse_file` — read CSV/XLSX via pandas (1.5h)
    - Detect file type, parse with column mapping
    - Return raw rows for validation
  - [x] 12.3 Implement `validate_import` (2h)
    - Check: required fields, date format, end > start odometer
    - Check: odometer continuity within import AND against existing trips
    - Flag duplicates (same vehicle + date + start_km + end_km)
    - Return per-row status: ok / warning / error
  - [x] 12.4 Implement `commit_import` — bulk insert validated rows (1.5h)
    - Skip error rows if user chose to
    - Write audit log entry for import action
  - [x] 12.5 Implement `get_template_csv` — downloadable example file (30min)
  - [x] 12.6 Add endpoints: POST `/api/zzp/trips/import`, POST `/api/zzp/trips/import/commit` (1.5h)
  - [x] 12.7 Write unit tests for import validation and commit (2h)
  - Testing: Valid import, duplicate detection, odometer validation, error handling, large file performance.

---

### Wave 4: Frontend Pages (~2 days)

**Parallelism: 4 tracks run simultaneously**

Dependencies: Wave 2 (service layer) + Wave 3 (backend features) complete.

---

- [x] 13. Desktop Trip Page
      **Covers:** Requirements 2, 4, 5, 6
  - [x] 13.1 Create `ZZPTrips.tsx` page component (3h)
    - Header with title, "Nieuw" button, vehicle selector, export dropdown
    - Summary bar (total km, zakelijk, privé, woon-werk)
    - Table with FilterableHeader columns (date, van, naar, km, categorie, doel, klant, status)
    - Row-click opens TripModal (BankingProcessor pattern)
  - [x] 13.2 Create `TripModal.tsx` — create/edit form (3h)
    - All fields, trip_category and trip_purpose as Select from configured lists
    - Correction reason field (required on edit)
    - Odometer pre-fill from last trip
    - Gap warning banner when gap detected in response
  - [x] 13.3 Create `BijtellingWidget.tsx` — progress bar component (1.5h)
    - Show for business vehicles: used km / limit, color-coded warning
  - [x] 13.4 Create `GapFillBanner.tsx` — warning with "Accept gap-fill" action (1h)
  - [x] 13.5 Implement multi-select + "Factureer geselecteerd" button (1.5h)
    - Same pattern as ZZPTimeTracking invoice flow
  - [x] 13.6 Register route in App router, add navigation link in ZZP menu (30min)
  - Testing: Manual smoke test on desktop and tablet viewports.

---

- [x] 14. Vehicles Page
      **Covers:** Requirement 1
  - [x] 14.1 Create `ZZPVehicles.tsx` page (2h)
    - Table/card list of vehicles
    - Add/edit modal with all fields (plate, make, model, year, VIN, type, unit, start odometer)
    - Deactivate action with confirmation
  - [x] 14.2 Create `VehicleModal.tsx` — form with validation (1.5h)
  - [x] 14.3 Register route in App router (30min)
  - Testing: Vehicle CRUD flow, deactivation confirmation dialog.

---

- [x] 15. Import Wizard Page
      **Covers:** Requirement 13
  - [x] 15.1 Create `ZZPTripImport.tsx` page — import wizard (3h)
    - Step 1: Upload file + select vehicle
    - Step 2: Column mapping (drag/drop or select)
    - Step 3: Preview with validation status per row (ok/warning/error badges)
    - Step 4: Commit with summary
  - [x] 15.2 Create `TripImportWizard.tsx` stepper component (2h)
    - Stepper UI, file upload, mapping grid, preview table
  - [x] 15.3 Add downloadable template link (30min)
  - [x] 15.4 Register route in App router (30min)
  - Testing: File upload, column mapping, validation display, import commit flow.

---

- [x] 16. Mobile Quick Entry
      **Covers:** Requirement 11
  - [x] 16.1 Create `ZZPTripQuick.tsx` page — single-screen mobile layout (3h)
    - Minimal header (back button + title only)
    - Vehicle auto-select (most recently used)
    - Route preset cards as tappable grid
    - End odometer input (start pre-filled)
    - "Registreer Rit" button
  - [x] 16.2 Create `RoutePresetCards.tsx` — touch-friendly card grid (2h)
    - Show from → to, category badge, typical km
    - One-tap fills form fields (min 44px tap targets)
  - [x] 16.3 Implement "Start Rit" / "Stop Rit" time capture workflow (1.5h)
    - Start: captures timestamp, shows timer
    - Stop: captures end timestamp, prompts for end odometer
  - [x] 16.4 Add PWA manifest entry for `/zzp/ritten/quick` (1h)
    - Icons, standalone display, theme colors
  - [x] 16.5 Register route in App router (no sidebar wrapper) (30min)
  - Testing: Mobile viewport testing, preset selection flow, PWA "add to home screen" verification.

---

### Wave 5: Integration & Polish (~1 day)

**Parallelism: 3 tracks run simultaneously**

Dependencies: All Wave 4 frontend pages complete.

---

- [x] 17. E2E Testing & Bug Fixes
  - [x] 17.1 Write Playwright E2E tests for trip CRUD flow (2h)
  - [x] 17.2 Write Playwright E2E tests for vehicle management (1h)
  - [x] 17.3 Write Playwright E2E tests for import wizard (1.5h)
  - [x] 17.4 Write Playwright E2E test for mobile quick entry (1h)
  - [x] 17.5 Fix bugs discovered during E2E testing (2h buffer)
  - Testing: All E2E tests green on CI.

---

- [x] 18. End-User Documentation
  - [x] 18.1 Write manual section for trip registration (1.5h)
  - [x] 18.2 Write manual section for vehicle management (1h)
  - [x] 18.3 Write manual section for import/export (1h)
  - [x] 18.4 Write manual section for mobile quick entry (30min)

---

- [x] 19. Performance & Optimization
  - [x] 19.1 Add database indexes for common query patterns (trip listing filters, summary aggregation) (1h)
  - [x] 19.2 Implement pagination for trip list endpoint (30min)
  - [x] 19.3 Test CSV import with 1000+ records, optimize if needed (1h)
  - [x] 19.4 Verify PDF generation < 5s for full year of data (30min)
  - Testing: Performance benchmarks meet success metrics from requirements.

---

## Notes

### Estimated Total Duration

| Wave      | Duration             | Parallelism                       | Calendar Time            |
| --------- | -------------------- | --------------------------------- | ------------------------ |
| Wave 1    | ~1 day total work    | 3 parallel tracks                 | 0.5 days                 |
| Wave 2    | ~3 days total work   | 4 parallel tracks                 | 1 day                    |
| Wave 3    | ~4.5 days total work | 4 parallel tracks (+1 sequential) | 1.5–2 days               |
| Wave 4    | ~4 days total work   | 4 parallel tracks                 | 1.5 days                 |
| Wave 5    | ~2 days total work   | 3 parallel tracks                 | 1 day                    |
| **Total** | **~14.5 days work**  |                                   | **~5.5–6 days calendar** |

### Parallel Execution Guidelines

- Each track within a wave is independent — no shared state or file conflicts
- Backend tracks (4, 5, 6) each create separate service files and route files
- Frontend tracks (13–16) each create separate page components
- Track 12 (Import) is the only track with an intra-wave dependency (needs 8 gap detection)
- Integration points are tested in Wave 5 after all components exist

### Key Integration Points

- `create_trip` is the central method — gap detection (8), audit logging (9), and route preset tracking (6) all hook into it
- Vehicle selector is shared between Trip Page (13), Import (15), and Quick Entry (16) — extract as shared component in 7 or early Wave 4
- Billing flow (10) depends on the invoice engine already existing in ZZP — verify interface before starting
