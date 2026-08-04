"""
TripService: Facade for Trip CRUD, queries, and calculations.

Core service for the Rittenregistratie (Trip/Mileage Registration) module.
Delegates to sub-modules for implementation:
- zzp_trip_crud_service.py — create, update, cancel, gap-fill
- zzp_trip_query_service.py — get, list, history, gaps, billing, contacts
- zzp_trip_calculation_service.py — summary, bijtelling, parameters

Business rules:
- All ALWAYS_REQUIRED fields must be present on create
- end_odometer > start_odometer (enforced)
- trip_date must be a valid date
- Tenant scoping: all queries include administration = %s
- distance_km is a DB generated column (end_odometer - start_odometer)

Reference: .kiro/specs/ZZP/rittenregistratie/design.md §4.2
"""

import logging
from datetime import date, datetime
from decimal import Decimal

from services.field_config_mixin import FieldConfigMixin
from services.zzp_trip_calculation_service import TripCalculationService
from services.zzp_trip_crud_service import TripCrudService
from services.zzp_trip_query_service import TripQueryService

logger = logging.getLogger(__name__)


class TripService(FieldConfigMixin):
    """Trip CRUD with odometer validation and gap detection.

    This class acts as a facade, delegating to specialized sub-services
    while maintaining backward compatibility for all callers.
    """

    FIELD_CONFIG_KEY = "trip_field_config"
    ALWAYS_REQUIRED = [  # noqa: RUF012
        "vehicle_id",
        "trip_date",
        "start_address",
        "end_address",
        "start_odometer",
        "end_odometer",
        "trip_category",
        "trip_purpose",
    ]

    # Fields that can be updated via update_trip (excludes distance_km which is generated)
    UPDATABLE_FIELDS = [  # noqa: RUF012
        "trip_date",
        "start_time",
        "end_time",
        "start_address",
        "end_address",
        "start_odometer",
        "end_odometer",
        "trip_category",
        "trip_purpose",
        "route_description",
        "contact_id",
        "project_name",
        "notes",
        "is_billable",
    ]

    # Miles-to-km conversion factor
    MILES_TO_KM = 1.60934

    def __init__(self, db, parameter_service=None):
        self.db = db
        self.parameter_service = parameter_service

        # Initialize sub-services
        self._crud = TripCrudService(self)
        self._query = TripQueryService(self)
        self._calc = TripCalculationService(self)

    # ── CRUD operations (delegated to TripCrudService) ─────

    def create_trip(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a new trip record with odometer gap detection."""
        return self._crud.create_trip(tenant, data, created_by)

    def update_trip(
        self,
        tenant: str,
        trip_id: int,
        data: dict,
        correction_reason: str,
        updated_by: str,
    ) -> dict:
        """Update/correct a trip with version increment and audit logging."""
        return self._crud.update_trip(
            tenant, trip_id, data, correction_reason, updated_by
        )

    def cancel_trip(
        self, tenant: str, trip_id: int, cancel_reason: str, cancelled_by: str
    ) -> bool:
        """Soft-cancel a trip (sets is_cancelled = true with reason)."""
        return self._crud.cancel_trip(tenant, trip_id, cancel_reason, cancelled_by)

    def create_gap_fill(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a gap-fill trip entry."""
        return self._crud.create_gap_fill(tenant, data, created_by)

    # ── Query operations (delegated to TripQueryService) ───

    def get_trip(self, tenant: str, trip_id: int) -> dict | None:
        """Get a single trip by ID, scoped to tenant."""
        return self._query.get_trip(tenant, trip_id)

    def list_trips(self, tenant: str, filters: dict | None = None) -> dict:
        """List trips with filtering and pagination."""
        return self._query.list_trips(tenant, filters)

    def get_trip_history(self, tenant: str, trip_id: int) -> list[dict]:
        """Get the correction/audit history for a trip."""
        return self._query.get_trip_history(tenant, trip_id)

    def get_unresolved_gaps(
        self, tenant: str, vehicle_id: int | None = None
    ) -> list[dict]:
        """List gap-fill entries that are still unresolved."""
        return self._query.get_unresolved_gaps(tenant, vehicle_id)

    def detect_gap(
        self, tenant: str, vehicle_id: int, start_odometer: int
    ) -> dict | None:
        """Detect an odometer gap between the previous trip and the new trip."""
        return self._query.detect_gap(tenant, vehicle_id, start_odometer)

    def enrich_with_contacts(self, tenant: str, trips: list[dict]) -> list[dict]:
        """Enrich trip dicts with contact information (company_name)."""
        return self._query.enrich_with_contacts(tenant, trips)

    def get_unbilled_trips(self, tenant: str, contact_id: int) -> list[dict]:
        """Get unbilled billable trips for a specific client."""
        return self._query.get_unbilled_trips(tenant, contact_id)

    def mark_as_billed(self, tenant: str, trip_ids: list, invoice_id: int) -> int:
        """Mark specified trips as billed by linking them to an invoice."""
        return self._query.mark_as_billed(tenant, trip_ids, invoice_id)

    # ── Calculation operations (delegated to TripCalculationService) ──

    def get_summary(self, tenant: str, vehicle_id: int, year: int) -> dict:
        """Get yearly trip summary with bijtelling/tax deduction tracking."""
        return self._calc.get_summary(tenant, vehicle_id, year)

    def get_bijtelling_status(self, tenant: str, vehicle_id: int, year: int) -> dict:
        """Lightweight bijtelling status for a vehicle."""
        return self._calc.get_bijtelling_status(tenant, vehicle_id, year)

    def get_trip_categories(self, tenant: str) -> list[str]:
        """Return configured trip categories from ParameterService or defaults."""
        return self._calc.get_trip_categories(tenant)

    def get_trip_purposes(self, tenant: str) -> list[str]:
        """Return configured trip purposes from ParameterService or defaults."""
        return self._calc.get_trip_purposes(tenant)

    # ── Internal helpers (kept on facade for sub-service access) ──

    def _get_raw_trip(self, tenant: str, trip_id: int) -> dict | None:
        """Fetch raw trip row without formatting (for internal comparison)."""
        rows = self.db.execute_query(
            "SELECT * FROM zzp_trips WHERE id = %s AND administration = %s",
            (int(trip_id), tenant),
        )
        if not rows:
            return None
        return dict(rows[0])

    @staticmethod
    def _normalize_for_comparison(value):
        """Normalize a value for field comparison (handles type mismatches)."""
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float, Decimal)):
            return str(value)
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _serialize_value(value):
        """Serialize a value for JSON storage in changed_fields."""
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _get_vehicle_info(self, tenant: str, vehicle_id: int) -> dict | None:
        """Fetch vehicle type and odometer_unit for summary calculations."""
        return self._calc._get_vehicle_info(tenant, vehicle_id)

    def _get_ritten_param(self, key: str, tenant: str, default=None):
        """Fetch a zzp_ritten parameter with fallback to MODULE_REGISTRY default."""
        return self._calc._get_ritten_param(key, tenant, default)

    def _validate_category_and_purpose(
        self, tenant: str, category: str, purpose: str
    ) -> None:
        """Validate trip_category and trip_purpose against configured parameter lists.

        Raises ValueError if either value is not in the allowed list.
        """
        valid_categories = self.get_trip_categories(tenant)
        if category not in valid_categories:
            raise ValueError(
                f"Invalid trip_category '{category}'. "
                f"Must be one of: {', '.join(valid_categories)}"
            )

        valid_purposes = self.get_trip_purposes(tenant)
        if purpose not in valid_purposes:
            raise ValueError(
                f"Invalid trip_purpose '{purpose}'. "
                f"Must be one of: {', '.join(valid_purposes)}"
            )

    def _validate_vehicle(self, tenant: str, vehicle_id: int) -> None:
        """Verify that the vehicle exists and belongs to this tenant."""
        rows = self.db.execute_query(
            "SELECT id FROM zzp_vehicles WHERE id = %s AND administration = %s",
            (int(vehicle_id), tenant),
        )
        if not rows:
            raise ValueError(f"Vehicle {vehicle_id} not found for this tenant")

    @staticmethod
    def _parse_date(value) -> date:
        """Parse a date value, accepting date objects or ISO format strings.

        Raises ValueError if the date is invalid.
        """
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()  # noqa: DTZ007
            except (ValueError, TypeError):
                raise ValueError(
                    f"Invalid trip_date format: '{value}'. Expected YYYY-MM-DD."
                )
        raise ValueError(f"Invalid trip_date type: {type(value).__name__}")

    @staticmethod
    def _format_trip(row: dict) -> dict:
        """Convert date/datetime/Decimal/timedelta objects for JSON serialization."""
        row = dict(row)
        # Convert date/datetime fields
        for key in ("trip_date", "created_at", "updated_at"):
            val = row.get(key)
            if (
                val is not None
                and hasattr(val, "isoformat")
                and not isinstance(val, str)
            ):
                row[key] = val.isoformat()

        # Convert time/timedelta fields (MySQL returns TIME as timedelta)
        for key in ("start_time", "end_time"):
            val = row.get(key)
            if val is not None and not isinstance(val, str):
                # timedelta → "HH:MM" string
                if hasattr(val, "total_seconds"):
                    total_seconds = int(val.total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    row[key] = f"{hours:02d}:{minutes:02d}"
                elif hasattr(val, "isoformat"):
                    row[key] = val.isoformat()

        # Ensure integer odometer values
        for key in ("start_odometer", "end_odometer", "distance_km"):
            if key in row and row[key] is not None:
                row[key] = int(row[key])

        # Ensure boolean fields
        for key in ("is_billable", "is_billed", "is_gap_fill", "is_cancelled"):
            if key in row:
                row[key] = bool(row[key])

        # Ensure version is int
        if "version" in row and row["version"] is not None:
            row["version"] = int(row["version"])

        return row

    # ── Audit (delegated to TripCrudService) ───────────────

    def _write_audit_entry(
        self,
        tenant: str,
        trip_id: int,
        version: int,
        action: str,
        changed_by: str,
        changed_fields: str | None = None,
        correction_reason: str | None = None,
    ) -> None:
        """Insert an audit trail record into zzp_trip_audit."""
        self._crud._write_audit_entry(
            tenant,
            trip_id,
            version,
            action,
            changed_by,
            changed_fields,
            correction_reason,
        )
