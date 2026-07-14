# Design Document — Rittenregistratie (ZZP Module)

## 1. Architecture Overview

The Rittenregistratie follows the established ZZP module architecture:

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React + Chakra UI)                           │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────┐  │
│  │ ZZPTrips   │  │ TripQuick  │  │ TripImport       │  │
│  │ (desktop)  │  │ (mobile)   │  │ (CSV/Excel)      │  │
│  └─────┬──────┘  └─────┬──────┘  └────────┬─────────┘  │
│        │               │                   │            │
│  ┌─────┴───────────────┴───────────────────┴─────────┐  │
│  │ tripService.ts / vehicleService.ts                 │  │
│  └─────────────────────┬─────────────────────────────┘  │
└────────────────────────┼────────────────────────────────┘
                         │ REST API
┌────────────────────────┼────────────────────────────────┐
│  Backend (Flask)       │                                │
│  ┌─────────────────────┴─────────────────────────────┐  │
│  │ zzp_trip_routes.py (Blueprint)                     │  │
│  └─────────────────────┬─────────────────────────────┘  │
│  ┌─────────────────────┴─────────────────────────────┐  │
│  │ TripService / VehicleService / TripImportService   │  │
│  └─────────────────────┬─────────────────────────────┘  │
│  ┌─────────────────────┴─────────────────────────────┐  │
│  │ DatabaseManager + dialect_helpers                   │  │
│  └─────────────────────┬─────────────────────────────┘  │
└────────────────────────┼────────────────────────────────┘
                         │
                    ┌────┴────┐
                    │ MySQL 8 │
                    └─────────┘
```

## 2. Database Schema

### 2.1 Table: `zzp_vehicles`

Stores registered vehicles per tenant. (Requirement 1)

```sql
CREATE TABLE IF NOT EXISTS zzp_vehicles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    license_plate VARCHAR(20) NOT NULL,
    make VARCHAR(100) DEFAULT NULL,
    model VARCHAR(100) DEFAULT NULL,
    year_built INT DEFAULT NULL,
    vin VARCHAR(17) DEFAULT NULL COMMENT 'Vehicle Identification Number (optional)',
    vehicle_type ENUM('private_for_business', 'business') NOT NULL,
    odometer_unit ENUM('km', 'miles') NOT NULL DEFAULT 'km',
    owner_lease_company VARCHAR(255) DEFAULT NULL,
    start_odometer INT NOT NULL COMMENT 'Odometer at registration',
    start_date DATE NOT NULL COMMENT 'Date of registration/start tracking',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT NULL,
    INDEX idx_administration (administration),
    INDEX idx_admin_active (administration, is_active),
    UNIQUE INDEX idx_admin_plate (administration, license_plate)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.2 Table: `zzp_trips`

Core trip records. (Requirements 2, 5, 6, 7)

```sql
CREATE TABLE IF NOT EXISTS zzp_trips (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    vehicle_id INT NOT NULL,
    trip_date DATE NOT NULL,
    start_time TIME DEFAULT NULL,
    end_time TIME DEFAULT NULL,
    start_address VARCHAR(500) NOT NULL,
    end_address VARCHAR(500) NOT NULL,
    start_odometer INT NOT NULL,
    end_odometer INT NOT NULL,
    distance_km INT GENERATED ALWAYS AS (end_odometer - start_odometer) STORED,
    trip_category VARCHAR(50) NOT NULL COMMENT 'Zakelijk, Privé, Woon-werk',
    trip_purpose VARCHAR(255) NOT NULL COMMENT 'From configurable list',
    route_description TEXT DEFAULT NULL COMMENT 'Only if deviating from standard route',
    contact_id INT DEFAULT NULL COMMENT 'Linked client from contacts table',
    project_name VARCHAR(255) DEFAULT NULL,
    notes TEXT DEFAULT NULL,
    is_billable BOOLEAN DEFAULT FALSE,
    is_billed BOOLEAN DEFAULT FALSE,
    invoice_id INT DEFAULT NULL COMMENT 'Set when billed',
    is_gap_fill BOOLEAN DEFAULT FALSE COMMENT 'Auto-generated gap entry',
    is_cancelled BOOLEAN DEFAULT FALSE COMMENT 'Soft-delete',
    cancel_reason TEXT DEFAULT NULL,
    version INT DEFAULT 1 COMMENT 'Incremented on correction',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES zzp_vehicles(id),
    FOREIGN KEY (contact_id) REFERENCES contacts(id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    INDEX idx_administration (administration),
    INDEX idx_admin_vehicle_date (administration, vehicle_id, trip_date),
    INDEX idx_admin_contact (administration, contact_id),
    INDEX idx_admin_billed (administration, is_billed),
    INDEX idx_admin_category (administration, trip_category),
    INDEX idx_vehicle_odometer (vehicle_id, start_odometer)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.3 Table: `zzp_trip_audit`

Immutable correction history. (Requirement 7)

```sql
CREATE TABLE IF NOT EXISTS zzp_trip_audit (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    trip_id INT NOT NULL,
    version INT NOT NULL,
    action ENUM('created', 'updated', 'cancelled') NOT NULL,
    changed_fields JSON DEFAULT NULL COMMENT '{"field": {"old": x, "new": y}}',
    correction_reason TEXT DEFAULT NULL,
    changed_by VARCHAR(255) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trip_id) REFERENCES zzp_trips(id),
    INDEX idx_administration (administration),
    INDEX idx_trip_id (trip_id),
    INDEX idx_admin_trip (administration, trip_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.4 Table: `zzp_route_presets`

Saved frequently-used routes. (Requirement 3)

```sql
CREATE TABLE IF NOT EXISTS zzp_route_presets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    from_address VARCHAR(500) NOT NULL,
    to_address VARCHAR(500) NOT NULL,
    default_category VARCHAR(50) DEFAULT NULL COMMENT 'Zakelijk, Privé, Woon-werk',
    default_purpose VARCHAR(255) DEFAULT NULL,
    contact_id INT DEFAULT NULL,
    typical_distance_km INT DEFAULT NULL,
    use_count INT DEFAULT 0,
    last_used_at TIMESTAMP DEFAULT NULL,
    is_manual BOOLEAN DEFAULT FALSE COMMENT 'User-created vs auto-learned',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (contact_id) REFERENCES contacts(id),
    INDEX idx_administration (administration),
    INDEX idx_admin_usage (administration, use_count DESC, last_used_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.5 Computed Column Note

The `distance_km` column is a MySQL generated column (`GENERATED ALWAYS AS (end_odometer - start_odometer) STORED`). This ensures the distance is always derived from odometer readings and cannot be manually overridden — directly satisfying the Belastingdienst requirement.

## 3. API Contracts

All endpoints use the standard decorator chain:

```python
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
```

Blueprint: `zzp_trip_bp = Blueprint("zzp_trip", __name__)`

### 3.1 Vehicle Endpoints

#### GET /api/zzp/vehicles

List vehicles for the tenant.

**Query params:** `is_active` (boolean, optional)

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "license_plate": "AB-123-CD",
      "make": "Volkswagen",
      "model": "Golf",
      "year_built": 2020,
      "vin": null,
      "vehicle_type": "private_for_business",
      "odometer_unit": "km",
      "start_odometer": 45000,
      "start_date": "2026-01-01",
      "is_active": true
    }
  ]
}
```

#### POST /api/zzp/vehicles

Create a vehicle.

**Request body:**

```json
{
  "license_plate": "AB-123-CD",
  "make": "Volkswagen",
  "model": "Golf",
  "year_built": 2020,
  "vin": "WVWZZZ1KZYW123456",
  "vehicle_type": "private_for_business",
  "odometer_unit": "km",
  "owner_lease_company": null,
  "start_odometer": 45000,
  "start_date": "2026-01-01"
}
```

#### PUT /api/zzp/vehicles/{id}

Update a vehicle. Cannot change `start_odometer` if trips exist.

#### DELETE /api/zzp/vehicles/{id}

Soft-delete (sets `is_active = false`). Returns 400 if trips exist and hard-delete attempted.

### 3.2 Trip Endpoints

#### GET /api/zzp/trips

List trips with filtering.

**Query params:**

- `vehicle_id` (int) — filter by vehicle
- `date_from`, `date_to` (date) — date range
- `trip_category` (string) — Zakelijk, Privé, Woon-werk
- `contact_id` (int) — filter by client
- `is_billed` (boolean) — billing status
- `is_gap_fill` (boolean) — show only gap entries
- `limit` (int, default 50), `offset` (int, default 0)

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "vehicle_id": 1,
      "trip_date": "2026-07-13",
      "start_address": "Keizersgracht 100, Amsterdam",
      "end_address": "Stationsplein 1, Utrecht",
      "start_odometer": 45230,
      "end_odometer": 45275,
      "distance_km": 45,
      "trip_category": "Zakelijk",
      "trip_purpose": "Klantbezoek",
      "contact": { "id": 5, "company_name": "Acme BV" },
      "is_billable": true,
      "is_billed": false,
      "is_gap_fill": false,
      "version": 1
    }
  ],
  "total": 156
}
```

#### POST /api/zzp/trips

Create a trip. Returns gap-fill suggestion if odometer gap detected.

**Request body:**

```json
{
  "vehicle_id": 1,
  "trip_date": "2026-07-13",
  "start_time": "08:30",
  "end_time": "09:15",
  "start_address": "Keizersgracht 100, Amsterdam",
  "end_address": "Stationsplein 1, Utrecht",
  "start_odometer": 45230,
  "end_odometer": 45275,
  "trip_category": "Zakelijk",
  "trip_purpose": "Klantbezoek",
  "contact_id": 5,
  "project_name": "Project Alpha",
  "notes": null,
  "is_billable": true
}
```

**Response (with gap warning):**

```json
{
  "success": true,
  "data": { "...trip object..." },
  "warnings": [
    {
      "type": "odometer_gap",
      "message": "Gap of 12 km detected (45218 → 45230)",
      "gap_km": 12,
      "previous_end_odometer": 45218,
      "current_start_odometer": 45230
    }
  ],
  "gap_fill_offer": {
    "start_odometer": 45218,
    "end_odometer": 45230,
    "suggested_category": "Privé",
    "suggested_purpose": "Niet geregistreerd"
  }
}
```

#### POST /api/zzp/trips/gap-fill

Accept the gap-fill suggestion.

**Request body:**

```json
{
  "vehicle_id": 1,
  "trip_date": "2026-07-12",
  "start_odometer": 45218,
  "end_odometer": 45230,
  "start_address": "Onbekend",
  "end_address": "Onbekend",
  "trip_category": "Privé",
  "trip_purpose": "Niet geregistreerd"
}
```

#### PUT /api/zzp/trips/{id}

Update/correct a trip. Requires `correction_reason`. Increments `version`, writes audit log.

**Request body:**

```json
{
  "end_odometer": 45280,
  "trip_purpose": "Vergadering",
  "correction_reason": "Foutieve eindstand gecorrigeerd"
}
```

#### DELETE /api/zzp/trips/{id}

Soft-cancel a trip (sets `is_cancelled = true`). Requires `cancel_reason`.

**Request body:**

```json
{
  "cancel_reason": "Dubbel ingevoerd"
}
```

#### GET /api/zzp/trips/{id}/history

Get correction audit trail for a trip.

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "version": 1,
      "action": "created",
      "changed_by": "user@example.com",
      "changed_at": "2026-07-13T08:30:00Z"
    },
    {
      "version": 2,
      "action": "updated",
      "changed_fields": { "end_odometer": { "old": 45275, "new": 45280 } },
      "correction_reason": "Foutieve eindstand gecorrigeerd",
      "changed_by": "user@example.com",
      "changed_at": "2026-07-13T10:00:00Z"
    }
  ]
}
```

### 3.3 Billing Endpoints

#### GET /api/zzp/trips/unbilled?contact_id={id}

Get unbilled billable trips for a client.

#### POST /api/zzp/invoices/from-trips

Create invoice from selected trips (mirrors time-entries-to-invoice flow).

**Request body:**

```json
{
  "contact_id": 5,
  "trip_ids": [10, 12, 15],
  "km_rate": 0.35,
  "invoice_date": "2026-07-31",
  "payment_terms_days": 14
}
```

**Behavior:**

- Creates one invoice line per trip: description = "{date} {from} → {to}", quantity = distance_km, unit_price = km_rate
- Marks trips as `is_billed = true`, sets `invoice_id`
- Returns created invoice

### 3.4 Summary & Report Endpoints

#### GET /api/zzp/trips/summary

**Query params:** `vehicle_id`, `year`, `period` (month/quarter/year)

**Response:**

```json
{
  "success": true,
  "data": {
    "year": 2026,
    "vehicle_id": 1,
    "total_km": 12450,
    "zakelijk_km": 10200,
    "prive_km": 950,
    "woonwerk_km": 1300,
    "bijtelling_km": 2250,
    "bijtelling_limit": 500,
    "bijtelling_warning": true,
    "tax_deduction": 2346.0,
    "monthly_breakdown": [
      { "month": "2026-01", "zakelijk": 850, "prive": 80, "woonwerk": 110 }
    ]
  }
}
```

#### GET /api/zzp/trips/export

**Query params:** `vehicle_id`, `year`, `format` (pdf/csv/xlsx)

Generates export file. PDF uses template system, CSV/XLSX uses openpyxl/pandas.

#### GET /api/zzp/trips/gaps

List unresolved gap-fill entries (purpose = "Niet geregistreerd").

### 3.5 Route Preset Endpoints

#### GET /api/zzp/route-presets

List presets (top X by usage in last 6 months + manual presets).

#### POST /api/zzp/route-presets

Create manual preset.

#### PUT /api/zzp/route-presets/{id}

Update preset defaults.

#### DELETE /api/zzp/route-presets/{id}

Delete a preset.

### 3.6 Import Endpoint

#### POST /api/zzp/trips/import

Upload and validate CSV/Excel file.

**Request:** multipart/form-data with `file` + `vehicle_id`

**Response (preview):**

```json
{
  "success": true,
  "data": {
    "total_rows": 500,
    "valid": 485,
    "warnings": 10,
    "errors": 5,
    "preview": ["...first 20 rows with validation status..."]
  }
}
```

#### POST /api/zzp/trips/import/commit

Commit validated import.

**Request body:**

```json
{
  "vehicle_id": 1,
  "skip_error_rows": true,
  "column_mapping": {
    "date": "Datum",
    "start_address": "Van",
    "end_address": "Naar",
    "start_km": "Begin KM",
    "end_km": "Eind KM",
    "purpose": "Doel",
    "category": "Type"
  }
}
```

## 4. Service Layer

### 4.1 VehicleService

```python
class VehicleService:
    """Vehicle CRUD scoped by tenant."""

    def __init__(self, db, parameter_service=None):
        self.db = db
        self.parameter_service = parameter_service

    def create_vehicle(self, tenant, data, created_by) -> dict
    def update_vehicle(self, tenant, vehicle_id, data) -> dict
    def deactivate_vehicle(self, tenant, vehicle_id) -> bool
    def get_vehicle(self, tenant, vehicle_id) -> Optional[dict]
    def list_vehicles(self, tenant, active_only=True) -> List[dict]
    def get_last_odometer(self, tenant, vehicle_id) -> int
```

### 4.2 TripService

```python
class TripService(FieldConfigMixin):
    """Trip CRUD with odometer validation and gap detection."""

    FIELD_CONFIG_KEY = "trip_field_config"
    ALWAYS_REQUIRED = ["vehicle_id", "trip_date", "start_address",
                       "end_address", "start_odometer", "end_odometer",
                       "trip_category", "trip_purpose"]

    def __init__(self, db, parameter_service=None):
        self.db = db
        self.parameter_service = parameter_service

    # CRUD
    def create_trip(self, tenant, data, created_by) -> dict
    def update_trip(self, tenant, trip_id, data, correction_reason, updated_by) -> dict
    def cancel_trip(self, tenant, trip_id, cancel_reason, cancelled_by) -> bool
    def get_trip(self, tenant, trip_id) -> Optional[dict]
    def list_trips(self, tenant, filters=None) -> List[dict]

    # Odometer & gaps
    def detect_gap(self, tenant, vehicle_id, start_odometer) -> Optional[dict]
    def create_gap_fill(self, tenant, data, created_by) -> dict
    def get_unresolved_gaps(self, tenant, vehicle_id=None) -> List[dict]

    # Billing
    def get_unbilled_trips(self, tenant, contact_id) -> List[dict]
    def mark_as_billed(self, tenant, trip_ids, invoice_id) -> int

    # Summaries
    def get_summary(self, tenant, vehicle_id, year) -> dict
    def get_bijtelling_status(self, tenant, vehicle_id, year) -> dict

    # Audit
    def get_trip_history(self, tenant, trip_id) -> List[dict]
```

### 4.3 RoutePresetService

```python
class RoutePresetService:
    """Route preset management with auto-learning."""

    def __init__(self, db, parameter_service=None):
        self.db = db
        self.parameter_service = parameter_service

    def get_suggestions(self, tenant, limit=None) -> List[dict]
    def create_preset(self, tenant, data) -> dict
    def update_preset(self, tenant, preset_id, data) -> dict
    def delete_preset(self, tenant, preset_id) -> bool
    def increment_usage(self, tenant, from_address, to_address) -> None
```

### 4.4 TripImportService

```python
class TripImportService:
    """CSV/Excel import with validation and preview."""

    def __init__(self, db, parameter_service=None):
        self.db = db
        self.parameter_service = parameter_service

    def parse_file(self, file_stream, filename, column_mapping) -> dict
    def validate_import(self, tenant, vehicle_id, rows) -> dict
    def commit_import(self, tenant, vehicle_id, rows, created_by) -> dict
    def get_template_csv(self) -> bytes
```

### 4.5 TripExportService

```python
class TripExportService:
    """PDF/CSV/XLSX export generation."""

    def __init__(self, db, parameter_service=None):
        self.db = db
        self.parameter_service = parameter_service

    def export_pdf(self, tenant, vehicle_id, year, filters=None) -> bytes
    def export_csv(self, tenant, vehicle_id, year, filters=None) -> bytes
    def export_xlsx(self, tenant, vehicle_id, year, filters=None) -> bytes
    def get_yearly_summary(self, tenant, vehicle_id, year) -> dict
```

## 5. Frontend Design

### 5.1 Pages

| Page        | Route                | Component           | Purpose                             |
| ----------- | -------------------- | ------------------- | ----------------------------------- |
| Trip List   | `/zzp/ritten`        | `ZZPTrips.tsx`      | Full desktop/tablet trip management |
| Quick Entry | `/zzp/ritten/quick`  | `ZZPTripQuick.tsx`  | Mobile-optimized quick entry        |
| Vehicles    | `/zzp/voertuigen`    | `ZZPVehicles.tsx`   | Vehicle management                  |
| Trip Import | `/zzp/ritten/import` | `ZZPTripImport.tsx` | CSV/Excel import wizard             |

### 5.2 ZZPTrips.tsx (Desktop Page)

Layout follows the ZZPTimeTracking pattern:

1. **Header**: Title + "Nieuw" button + "Export" dropdown + vehicle selector
2. **Summary bar**: Total km / Zakelijk / Privé / Woon-werk for selected period
3. **Bijtelling widget** (for business vehicles): Progress bar toward 500 km
4. **Filter row**: Date range, category, client, gap-fill toggle
5. **Table** (desktop): Date, Van, Naar, KM, Categorie, Doel, Klant, Status
6. **Cards** (mobile): Compact trip cards with swipe actions
7. **Row click → Modal**: Trip detail/edit with correction reason field
8. **Checkbox multi-select → "Factureer geselecteerd"** button

### 5.3 ZZPTripQuick.tsx (Mobile Quick Entry)

Minimal, single-screen design:

```
┌─────────────────────────────┐
│  ← Terug     Rittenregistratie │
├─────────────────────────────┤
│  [Vehicle selector]          │
├─────────────────────────────┤
│  Favoriete routes:           │
│  ┌─────────┐ ┌─────────┐   │
│  │ Huis →  │ │ Huis →  │   │
│  │ Kantoor │ │ Klant A │   │
│  │ 🏠→🏢  │ │ 🏠→📍  │   │
│  └─────────┘ └─────────┘   │
│  ┌─────────┐ ┌─────────┐   │
│  │ Kantoor │ │ + Nieuw  │   │
│  │ → Huis  │ │          │   │
│  │ 🏢→🏠  │ │          │   │
│  └─────────┘ └─────────┘   │
├─────────────────────────────┤
│  Kilometerstand: [_45275_]  │
│  (vorige: 45230)            │
├─────────────────────────────┤
│  [ REGISTREER RIT ]         │
└─────────────────────────────┘
```

Flow:

1. Open page → vehicle auto-selected (most recent)
2. Tap route preset → fills addresses, category, purpose
3. Enter end odometer (start pre-filled from last trip)
4. Tap "Registreer Rit" → saved

No sidebar, no complex navigation. PWA manifest for home screen icon.

### 5.4 Shared Components

| Component          | File                                  | Purpose                          |
| ------------------ | ------------------------------------- | -------------------------------- |
| `TripModal`        | `components/zzp/TripModal.tsx`        | Create/edit trip with all fields |
| `TripCard`         | `components/zzp/TripCard.tsx`         | Mobile card layout for trip      |
| `VehicleSelector`  | `components/zzp/VehicleSelector.tsx`  | Vehicle dropdown with type badge |
| `BijtellingWidget` | `components/zzp/BijtellingWidget.tsx` | Progress bar + warning           |
| `GapFillBanner`    | `components/zzp/GapFillBanner.tsx`    | Warning banner when gap detected |
| `RoutePresetCards` | `components/zzp/RoutePresetCards.tsx` | Tappable route preset grid       |
| `TripImportWizard` | `components/zzp/TripImportWizard.tsx` | Column mapping + preview         |

### 5.5 Frontend Services

```typescript
// tripService.ts
const BASE = "/api/zzp/trips";

export async function getTrips(filters?: TripFilters): Promise<ApiListResponse>;
export async function createTrip(data: Partial<Trip>): Promise<ApiTripResponse>;
export async function updateTrip(
  id: number,
  data: Partial<Trip>,
): Promise<ApiTripResponse>;
export async function cancelTrip(
  id: number,
  reason: string,
): Promise<ApiResponse>;
export async function getTripHistory(id: number): Promise<ApiAuditResponse>;
export async function getUnbilledTrips(
  contactId: number,
): Promise<ApiListResponse>;
export async function getTripSummary(
  vehicleId: number,
  year: number,
): Promise<ApiSummaryResponse>;
export async function exportTrips(
  vehicleId: number,
  year: number,
  format: string,
): Promise<Blob>;
export async function createGapFill(
  data: GapFillData,
): Promise<ApiTripResponse>;
export async function importTrips(
  file: File,
  vehicleId: number,
): Promise<ApiImportResponse>;
export async function commitImport(
  vehicleId: number,
  mapping: ColumnMapping,
): Promise<ApiResponse>;

// vehicleService.ts
const BASE = "/api/zzp/vehicles";

export async function getVehicles(
  activeOnly?: boolean,
): Promise<ApiListResponse>;
export async function createVehicle(
  data: Partial<Vehicle>,
): Promise<ApiItemResponse>;
export async function updateVehicle(
  id: number,
  data: Partial<Vehicle>,
): Promise<ApiItemResponse>;
export async function deactivateVehicle(id: number): Promise<ApiResponse>;

// routePresetService.ts
const BASE = "/api/zzp/route-presets";

export async function getRoutePresets(): Promise<ApiListResponse>;
export async function createRoutePreset(
  data: Partial<RoutePreset>,
): Promise<ApiItemResponse>;
export async function updateRoutePreset(
  id: number,
  data: Partial<RoutePreset>,
): Promise<ApiItemResponse>;
export async function deleteRoutePreset(id: number): Promise<ApiResponse>;
```

### 5.6 TypeScript Types

```typescript
// types/zzpTrips.ts

export interface Vehicle {
  id: number;
  license_plate: string;
  make: string | null;
  model: string | null;
  year_built: number | null;
  vin: string | null;
  vehicle_type: "private_for_business" | "business";
  odometer_unit: "km" | "miles";
  owner_lease_company: string | null;
  start_odometer: number;
  start_date: string;
  is_active: boolean;
}

export interface Trip {
  id: number;
  vehicle_id: number;
  trip_date: string;
  start_time: string | null;
  end_time: string | null;
  start_address: string;
  end_address: string;
  start_odometer: number;
  end_odometer: number;
  distance_km: number;
  trip_category: string;
  trip_purpose: string;
  route_description: string | null;
  contact_id: number | null;
  contact?: { id: number; company_name: string };
  project_name: string | null;
  notes: string | null;
  is_billable: boolean;
  is_billed: boolean;
  invoice_id: number | null;
  is_gap_fill: boolean;
  is_cancelled: boolean;
  version: number;
}

export interface RoutePreset {
  id: number;
  from_address: string;
  to_address: string;
  default_category: string | null;
  default_purpose: string | null;
  contact_id: number | null;
  typical_distance_km: number | null;
  use_count: number;
  is_manual: boolean;
}

export interface TripSummary {
  year: number;
  vehicle_id: number;
  total_km: number;
  zakelijk_km: number;
  prive_km: number;
  woonwerk_km: number;
  bijtelling_km: number;
  bijtelling_limit: number;
  bijtelling_warning: boolean;
  tax_deduction: number;
}

export interface TripFilters {
  vehicle_id?: number;
  date_from?: string;
  date_to?: string;
  trip_category?: string;
  contact_id?: number;
  is_billed?: boolean;
  is_gap_fill?: boolean;
  limit?: number;
  offset?: number;
}

export interface GapFillData {
  vehicle_id: number;
  trip_date: string;
  start_odometer: number;
  end_odometer: number;
  start_address: string;
  end_address: string;
  trip_category: string;
  trip_purpose: string;
}
```

## 6. Security

### 6.1 Authentication & Authorization

- All routes use `@cognito_required` + `@tenant_required()` + `@module_required('ZZP')`
- Permissions: `zzp_read` (view), `zzp_crud` (create/edit/cancel), `zzp_export` (export/reports)
- Tenant isolation: every query includes `WHERE administration = %s`

### 6.2 Data Integrity

- Odometer chain validation on create (warn, don't block)
- Audit trail immutability: `zzp_trip_audit` is INSERT-only, no UPDATE/DELETE routes
- Corrections increment `version` and require `correction_reason`
- Billed trips cannot be edited or cancelled
- Cancelled trips cannot be un-cancelled (create new trip instead)

### 6.3 Input Validation

- `end_odometer > start_odometer` (enforced)
- `trip_date` must be valid date, not in future
- `trip_category` must be from configured list
- `trip_purpose` must be from configured list
- `license_plate` unique per tenant
- SQL injection protection via parameterized queries

## 7. Performance

### 7.1 Indexing Strategy

- Primary query pattern: trips by tenant + vehicle + date range → composite index
- Billing queries: tenant + contact + is_billed → composite index
- Gap detection: vehicle + odometer ordering → dedicated index

### 7.2 Pagination

- All list endpoints support `limit`/`offset` with default limit of 50
- Total count returned for pagination UI
- Summary queries use aggregate functions (no full table scans)

### 7.3 Export Performance

- PDF generation for a full year (~1000 trips): target < 5 seconds
- Uses streaming for large XLSX exports
- Summary data pre-aggregated via SQL GROUP BY

## 8. Internationalization

Translation namespace: `zzp` (extends existing ZZP translations)

Key prefix: `trips.*` for all trip-related translations.

Example keys:

```
trips.title = "Rittenregistratie"
trips.quickEntry = "Snelle invoer"
trips.newTrip = "Nieuwe rit"
trips.vehicle = "Voertuig"
trips.startAddress = "Vertrekadres"
trips.endAddress = "Bestemming"
trips.startOdometer = "Begin km-stand"
trips.endOdometer = "Eind km-stand"
trips.distance = "Afstand (km)"
trips.category = "Categorie"
trips.purpose = "Doel"
trips.client = "Klant"
trips.billable = "Factureerbaar"
trips.billed = "Gefactureerd"
trips.gapFill = "Niet geregistreerd"
trips.gapWarning = "Er ontbreken {{km}} km tussen de vorige rit en deze rit"
trips.bijtellingWarning = "Let op: nog {{remaining}} km privé over dit jaar"
trips.registerTrip = "Registreer rit"
trips.correctionReason = "Reden correctie"
trips.cancelReason = "Reden annulering"
```

## 9. PWA Configuration (Mobile Quick Entry)

Extend existing `manifest.json` or create a minimal PWA manifest:

```json
{
  "name": "Rittenregistratie",
  "short_name": "Ritten",
  "start_url": "/zzp/ritten/quick",
  "display": "standalone",
  "background_color": "#1A202C",
  "theme_color": "#ED8936",
  "icons": [
    { "src": "/icons/ritten-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/ritten-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

This enables "Add to Home Screen" on mobile browsers, giving users an app-like experience for quick trip entry.

## 10. Parameter Registration

Register parameters in MODULE_REGISTRY under the ZZP module:

```python
"zzp_ritten": {
    "max_route_presets": {"default": 5, "type": "integer"},
    "bijtelling_warning_threshold": {"default": 400, "type": "integer"},
    "bijtelling_limit": {"default": 500, "type": "integer"},
    "large_distance_warning": {"default": 300, "type": "integer"},
    "default_km_rate": {"default": 0.23, "type": "decimal"},
    "trip_categories": {"default": ["Zakelijk", "Privé", "Woon-werk"], "type": "json"},
    "trip_purposes": {"default": ["Klantbezoek", "Vergadering", "Materiaal ophalen", "Overig"], "type": "json"},
}
```

## 11. Invoice Integration

The trip-to-invoice flow mirrors the existing time-entries-to-invoice pattern:

1. User selects unbilled trips for a client (checkboxes)
2. Clicks "Factureer geselecteerd"
3. System calls `POST /api/zzp/invoices/from-trips`
4. Backend creates invoice lines: one line per trip
   - Description: `"{trip_date} {start_address} → {end_address}"`
   - Quantity: `distance_km`
   - Unit price: `km_rate` (from request, sourced from client/contract config)
   - VAT code: configurable (default: high)
5. Marks trips as billed (`is_billed = true`, `invoice_id` set)
6. Returns draft invoice for review

The `km_rate` per client is stored on the contact record (new field: `km_rate DECIMAL(10,4) DEFAULT NULL` on `contacts` table) or passed explicitly per billing action.
