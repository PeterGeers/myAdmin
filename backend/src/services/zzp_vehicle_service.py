"""
VehicleService: Vehicle CRUD scoped by tenant.

Manages vehicle registration, updates, soft-deletion, and odometer tracking
for the Rittenregistratie (Trip/Mileage Registration) module.

Business rules:
- Unique license plate per tenant (UNIQUE INDEX idx_admin_plate)
- Cannot change start_odometer if trips exist for that vehicle
- Soft-delete only (set is_active = false) — cannot hard-delete if trips exist
- get_last_odometer returns end_odometer of most recent trip, or start_odometer if no trips

Reference: .kiro/specs/ZZP/rittenregistratie/design.md §4.1
"""

import logging
from typing import List, Optional

from db_exceptions import IntegrityError

logger = logging.getLogger(__name__)


class VehicleService:
    """Vehicle CRUD scoped by tenant."""

    def __init__(self, db, parameter_service=None):
        self.db = db
        self.parameter_service = parameter_service

    def create_vehicle(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a new vehicle for the tenant.

        Required fields: license_plate, vehicle_type, start_odometer, start_date.
        Raises IntegrityError if license plate already exists for the tenant.
        """
        required = ["license_plate", "vehicle_type", "start_odometer", "start_date"]
        for field in required:
            if field not in data or data[field] is None:
                raise ValueError(f"Missing required field: {field}")

        # Validate vehicle_type
        valid_types = ("private_for_business", "business")
        if data["vehicle_type"] not in valid_types:
            raise ValueError(
                f"Invalid vehicle_type: {data['vehicle_type']}. "
                f"Must be one of: {', '.join(valid_types)}"
            )

        # Validate odometer_unit if provided
        odometer_unit = data.get("odometer_unit", "km")
        if odometer_unit not in ("km", "miles"):
            raise ValueError("odometer_unit must be 'km' or 'miles'")

        # Validate start_odometer is non-negative
        if int(data["start_odometer"]) < 0:
            raise ValueError("start_odometer must be non-negative")

        try:
            vehicle_id = self.db.execute_query(
                """INSERT INTO zzp_vehicles
                   (administration, license_plate, make, model, year_built,
                    vin, vehicle_type, odometer_unit, owner_lease_company,
                    start_odometer, start_date, is_active, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    tenant,
                    data["license_plate"].strip().upper(),
                    data.get("make"),
                    data.get("model"),
                    data.get("year_built"),
                    data.get("vin"),
                    data["vehicle_type"],
                    odometer_unit,
                    data.get("owner_lease_company"),
                    int(data["start_odometer"]),
                    data["start_date"],
                    True,
                    created_by,
                ),
                fetch=False,
                commit=True,
            )
        except IntegrityError as e:
            # Duplicate license plate for this tenant
            if e.error_code == 1062:
                raise IntegrityError(
                    f"License plate '{data['license_plate']}' already exists "
                    f"for this administration",
                    error_code=1062,
                    original_error=e.original_error,
                )
            raise

        return self.get_vehicle(tenant, vehicle_id)

    def update_vehicle(self, tenant: str, vehicle_id: int, data: dict) -> dict:
        """Update a vehicle. Cannot change start_odometer if trips exist.

        Returns the updated vehicle dict.
        Raises ValueError if vehicle not found or start_odometer change blocked.
        """
        existing = self.get_vehicle(tenant, vehicle_id)
        if not existing:
            raise ValueError(f"Vehicle {vehicle_id} not found")

        # Block start_odometer change if trips exist
        if "start_odometer" in data and int(data["start_odometer"]) != existing["start_odometer"]:
            if self._has_trips(tenant, vehicle_id):
                raise ValueError(
                    "Cannot change start_odometer: trips already exist for this vehicle"
                )

        # Validate vehicle_type if being changed
        if "vehicle_type" in data:
            valid_types = ("private_for_business", "business")
            if data["vehicle_type"] not in valid_types:
                raise ValueError(
                    f"Invalid vehicle_type: {data['vehicle_type']}. "
                    f"Must be one of: {', '.join(valid_types)}"
                )

        # Validate odometer_unit if being changed
        if "odometer_unit" in data:
            if data["odometer_unit"] not in ("km", "miles"):
                raise ValueError("odometer_unit must be 'km' or 'miles'")

        # Build dynamic update
        updatable_fields = [
            "license_plate", "make", "model", "year_built", "vin",
            "vehicle_type", "odometer_unit", "owner_lease_company",
            "start_odometer", "start_date", "is_active",
        ]
        sets, params = [], []
        for field in updatable_fields:
            if field in data:
                value = data[field]
                if field == "license_plate" and value:
                    value = value.strip().upper()
                if field == "start_odometer" and value is not None:
                    value = int(value)
                sets.append(f"{field} = %s")
                params.append(value)

        if not sets:
            return existing

        params.extend([vehicle_id, tenant])
        try:
            self.db.execute_query(
                f"UPDATE zzp_vehicles SET {', '.join(sets)} "
                f"WHERE id = %s AND administration = %s",
                tuple(params),
                fetch=False,
                commit=True,
            )
        except IntegrityError as e:
            if e.error_code == 1062:
                raise IntegrityError(
                    f"License plate '{data.get('license_plate', '')}' already exists "
                    f"for this administration",
                    error_code=1062,
                    original_error=e.original_error,
                )
            raise

        return self.get_vehicle(tenant, vehicle_id)

    def deactivate_vehicle(self, tenant: str, vehicle_id: int) -> bool:
        """Soft-delete a vehicle by setting is_active = false.

        Always soft-deletes. Returns True on success.
        Raises ValueError if vehicle not found.
        """
        existing = self.get_vehicle(tenant, vehicle_id)
        if not existing:
            raise ValueError(f"Vehicle {vehicle_id} not found")

        self.db.execute_query(
            "UPDATE zzp_vehicles SET is_active = FALSE "
            "WHERE id = %s AND administration = %s",
            (vehicle_id, tenant),
            fetch=False,
            commit=True,
        )
        return True

    def get_vehicle(self, tenant: str, vehicle_id: int) -> Optional[dict]:
        """Get a single vehicle by ID, scoped to tenant."""
        rows = self.db.execute_query(
            "SELECT * FROM zzp_vehicles WHERE id = %s AND administration = %s",
            (vehicle_id, tenant),
        )
        return self._format_vehicle(rows[0]) if rows else None

    def list_vehicles(self, tenant: str, active_only: bool = True) -> List[dict]:
        """List vehicles for the tenant, optionally filtered by active status."""
        if active_only:
            query = (
                "SELECT * FROM zzp_vehicles "
                "WHERE administration = %s AND is_active = TRUE "
                "ORDER BY license_plate"
            )
        else:
            query = (
                "SELECT * FROM zzp_vehicles "
                "WHERE administration = %s "
                "ORDER BY is_active DESC, license_plate"
            )
        rows = self.db.execute_query(query, (tenant,)) or []
        return [self._format_vehicle(r) for r in rows]

    def get_last_odometer(self, tenant: str, vehicle_id: int) -> int:
        """Get the last known odometer reading for a vehicle.

        Returns the end_odometer of the most recent (by trip_date, then id)
        non-cancelled trip, or the vehicle's start_odometer if no trips exist.
        """
        # Try to get end_odometer from the most recent trip
        rows = self.db.execute_query(
            """SELECT end_odometer FROM zzp_trips
               WHERE administration = %s AND vehicle_id = %s
                 AND is_cancelled = FALSE
               ORDER BY trip_date DESC, id DESC
               LIMIT 1""",
            (tenant, vehicle_id),
        )
        if rows:
            return int(rows[0]["end_odometer"])

        # Fallback to vehicle start_odometer
        vehicle = self.get_vehicle(tenant, vehicle_id)
        if vehicle:
            return vehicle["start_odometer"]

        raise ValueError(f"Vehicle {vehicle_id} not found")

    # ── Private helpers ─────────────────────────────────────

    def _has_trips(self, tenant: str, vehicle_id: int) -> bool:
        """Check if any trips exist for this vehicle."""
        rows = self.db.execute_query(
            """SELECT 1 FROM zzp_trips
               WHERE administration = %s AND vehicle_id = %s
               LIMIT 1""",
            (tenant, vehicle_id),
        )
        return bool(rows)

    @staticmethod
    def _format_vehicle(row: dict) -> dict:
        """Convert date/datetime objects to ISO strings for JSON serialization."""
        row = dict(row)
        for key in ("start_date", "created_at", "updated_at"):
            val = row.get(key)
            if val is not None and hasattr(val, "isoformat") and not isinstance(val, str):
                row[key] = val.isoformat()
        # Ensure start_odometer is int
        if "start_odometer" in row and row["start_odometer"] is not None:
            row["start_odometer"] = int(row["start_odometer"])
        # Ensure boolean
        if "is_active" in row:
            row["is_active"] = bool(row["is_active"])
        return row
