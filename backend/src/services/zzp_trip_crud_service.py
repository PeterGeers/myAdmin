"""
TripCrudService: Trip CRUD operations with odometer validation.

Handles trip creation, update, cancellation, and gap-fill creation.
Extracted from zzp_trip_service.py for file size compliance (<500 lines).

Business rules:
- All ALWAYS_REQUIRED fields must be present on create
- end_odometer > start_odometer (enforced)
- trip_date must be a valid date
- Tenant scoping: all queries include administration = %s
- distance_km is a DB generated column (end_odometer - start_odometer)

Reference: .kiro/specs/ZZP/rittenregistratie/design.md §4.2
"""

import json
import logging

from db_exceptions import IntegrityError

logger = logging.getLogger(__name__)


class TripCrudService:
    """Trip CRUD operations: create, update, cancel, gap-fill."""

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

    def __init__(self, service):
        """Initialize with reference to the parent TripService.

        Args:
            service: TripService instance (provides db, parameter_service,
                     validation helpers, and query methods).
        """
        self.service = service
        self.db = service.db

    def create_trip(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a new trip record with odometer gap detection.

        Returns dict with "success", "data", optional "warnings" and "gap_fill_offer".
        Raises ValueError on validation failure, IntegrityError on FK violations.
        """
        # Validate required fields via FieldConfigMixin
        self.service.validate_fields(tenant, data)

        # Validate trip_category and trip_purpose against configured lists
        self.service._validate_category_and_purpose(
            tenant, data["trip_category"], data["trip_purpose"]
        )

        # Validate odometer: end must be greater than start
        start_odometer = int(data["start_odometer"])
        end_odometer = int(data["end_odometer"])
        if end_odometer <= start_odometer:
            raise ValueError(
                "end_odometer must be greater than start_odometer "
                f"(got start={start_odometer}, end={end_odometer})"
            )

        # Validate trip_date is a valid date
        trip_date = self.service._parse_date(data["trip_date"])

        # Validate vehicle exists for this tenant
        self.service._validate_vehicle(tenant, data["vehicle_id"])

        # Detect gap BEFORE insert (check against existing trips)
        gap_info = self.service.detect_gap(
            tenant, int(data["vehicle_id"]), start_odometer
        )

        try:
            trip_id = self.db.execute_query(
                """INSERT INTO zzp_trips
                   (administration, vehicle_id, trip_date, start_time, end_time,
                    start_address, end_address, start_odometer, end_odometer,
                    trip_category, trip_purpose, route_description,
                    contact_id, project_name, notes,
                    is_billable, is_gap_fill, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s, %s)""",
                (
                    tenant,
                    int(data["vehicle_id"]),
                    trip_date,
                    data.get("start_time"),
                    data.get("end_time"),
                    data["start_address"].strip(),
                    data["end_address"].strip(),
                    start_odometer,
                    end_odometer,
                    data["trip_category"],
                    data["trip_purpose"],
                    data.get("route_description"),
                    data.get("contact_id"),
                    data.get("project_name"),
                    data.get("notes"),
                    data.get("is_billable", False),
                    data.get("is_gap_fill", False),
                    created_by,
                ),
                fetch=False,
                commit=True,
            )
        except IntegrityError as e:
            # FK violation (vehicle_id, contact_id, etc.)
            raise IntegrityError(
                f"Foreign key constraint failed: {e}",
                error_code=e.error_code,
                original_error=e.original_error,
            )

        # Write audit entry for creation
        self._write_audit_entry(
            tenant, trip_id, version=1, action="created", changed_by=created_by
        )

        trip = self.service.get_trip(tenant, trip_id)

        # Build response with warnings if detected
        warnings = []
        result = {"success": True, "data": trip}

        if gap_info:
            gap_km = gap_info["gap_km"]
            prev_end = gap_info["previous_end_odometer"]
            curr_start = gap_info["current_start_odometer"]

            warnings.append(
                {
                    "type": "odometer_gap",
                    "message": f"Gap of {gap_km} km detected ({prev_end} → {curr_start})",
                    "gap_km": gap_km,
                    "previous_end_odometer": prev_end,
                    "current_start_odometer": curr_start,
                }
            )
            result["gap_fill_offer"] = {
                "start_odometer": prev_end,
                "end_odometer": curr_start,
                "suggested_category": "Privé",
                "suggested_purpose": "Niet geregistreerd",
            }

        # Check for unusually large distance (Requirement 4.6)
        distance_km = end_odometer - start_odometer
        large_distance_threshold = self.service._get_ritten_param(
            "large_distance_warning", tenant, default=300
        )
        try:
            large_distance_threshold = int(large_distance_threshold)
        except (TypeError, ValueError):
            large_distance_threshold = 300

        if distance_km > large_distance_threshold:
            warnings.append(
                {
                    "type": "large_distance",
                    "message": (
                        f"Unusually large distance: {distance_km} km "
                        f"(threshold: {large_distance_threshold} km)"
                    ),
                    "distance_km": distance_km,
                    "threshold_km": large_distance_threshold,
                }
            )

        if warnings:
            result["warnings"] = warnings

        # Auto-learn route preset (Requirement 3 — track route frequency)
        try:
            from services.zzp_route_preset_service import RoutePresetService

            preset_service = RoutePresetService(self.db, self.service.parameter_service)
            preset_service.increment_usage(
                tenant,
                data["start_address"].strip(),
                data["end_address"].strip(),
                default_category=data.get("trip_category"),
                default_purpose=data.get("trip_purpose"),
                typical_distance_km=end_odometer - start_odometer,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Route preset auto-learn failed (non-blocking): {e}")

        return result

    def update_trip(
        self,
        tenant: str,
        trip_id: int,
        data: dict,
        correction_reason: str,
        updated_by: str,
    ) -> dict:
        """Update/correct a trip with version increment and audit logging.

        Raises ValueError if trip not found, correction_reason missing,
        trip is billed, or no valid fields to update.
        """
        # 1. Require correction_reason
        if not correction_reason or not correction_reason.strip():
            raise ValueError("correction_reason is required for trip updates")

        # 2. Fetch existing trip
        existing = self.service._get_raw_trip(tenant, trip_id)
        if not existing:
            raise ValueError(f"Trip {trip_id} not found for this tenant")

        # 3. Block editing billed trips
        if existing.get("is_billed"):
            raise ValueError(
                f"Trip {trip_id} is billed and cannot be edited. "
                "Unbill or create a new trip instead."
            )

        # 4. Filter to only updatable fields that are actually provided
        update_fields = {k: v for k, v in data.items() if k in self.UPDATABLE_FIELDS}
        if not update_fields:
            raise ValueError(
                "No valid fields to update. Updatable fields: "
                + ", ".join(self.UPDATABLE_FIELDS)
            )

        # 5. Compute changed_fields diff (only fields that actually changed)
        changed_fields = {}
        for field, new_value in update_fields.items():
            old_value = existing.get(field)
            # Normalize for comparison (handle date objects, booleans, etc.)
            old_comparable = self.service._normalize_for_comparison(old_value)
            new_comparable = self.service._normalize_for_comparison(new_value)
            if old_comparable != new_comparable:
                changed_fields[field] = {
                    "old": self.service._serialize_value(old_value),
                    "new": self.service._serialize_value(new_value),
                }

        if not changed_fields:
            raise ValueError("No fields have changed — nothing to update")

        # 6. Increment version
        current_version = int(existing.get("version", 1))
        new_version = current_version + 1

        # 7. Build and execute UPDATE statement
        set_clauses = []
        params = []
        for field in changed_fields:
            set_clauses.append(f"{field} = %s")
            params.append(update_fields[field])

        # Always update version
        set_clauses.append("version = %s")
        params.append(new_version)

        # WHERE clause params
        params.append(int(trip_id))
        params.append(tenant)

        update_sql = (
            f"UPDATE zzp_trips SET {', '.join(set_clauses)} "
            f"WHERE id = %s AND administration = %s"
        )
        self.db.execute_query(update_sql, tuple(params), fetch=False, commit=True)

        # 8. Write audit entry
        changed_fields_json = json.dumps(changed_fields, ensure_ascii=False)
        self._write_audit_entry(
            tenant=tenant,
            trip_id=trip_id,
            version=new_version,
            action="updated",
            changed_by=updated_by,
            changed_fields=changed_fields_json,
            correction_reason=correction_reason.strip(),
        )

        # 9. Return updated trip
        updated_trip = self.service.get_trip(tenant, trip_id)
        return updated_trip

    def cancel_trip(
        self, tenant: str, trip_id: int, cancel_reason: str, cancelled_by: str
    ) -> bool:
        """Soft-cancel a trip (sets is_cancelled = true with reason).

        Raises ValueError if cancel_reason missing, trip not found,
        trip already cancelled, or trip is billed.
        """
        # 1. Require cancel_reason
        if not cancel_reason or not cancel_reason.strip():
            raise ValueError("cancel_reason is required for trip cancellation")

        # 2. Fetch existing trip
        existing = self.service._get_raw_trip(tenant, trip_id)
        if not existing:
            raise ValueError(f"Trip {trip_id} not found for this tenant")

        # 3. Block cancellation of already-cancelled trips
        if existing.get("is_cancelled"):
            raise ValueError(f"Trip {trip_id} is already cancelled")

        # 4. Block cancellation of billed trips
        if existing.get("is_billed"):
            raise ValueError(
                f"Trip {trip_id} is billed and cannot be cancelled. "
                "Unbill the trip first."
            )

        # 5. Set is_cancelled = true and cancel_reason
        current_version = int(existing.get("version", 1))
        self.db.execute_query(
            """UPDATE zzp_trips
               SET is_cancelled = TRUE, cancel_reason = %s
               WHERE id = %s AND administration = %s""",
            (cancel_reason.strip(), int(trip_id), tenant),
            fetch=False,
            commit=True,
        )

        # 6. Write audit entry
        self._write_audit_entry(
            tenant=tenant,
            trip_id=trip_id,
            version=current_version,
            action="cancelled",
            changed_by=cancelled_by,
            correction_reason=cancel_reason.strip(),
        )

        # 7. Return True on success
        return True

    def create_gap_fill(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a gap-fill trip entry (unregistered km between two trips).

        Defaults: category "Privé", purpose "Niet geregistreerd".
        Does NOT call detect_gap (since this IS the gap fill).

        Returns {"success": True, "data": trip_dict}.
        Raises ValueError on validation failure, IntegrityError on FK violations.
        """
        # Apply gap-fill defaults
        data = dict(data)  # Don't mutate caller's dict
        data["is_gap_fill"] = True
        data.setdefault("trip_category", "Privé")
        data.setdefault("trip_purpose", "Niet geregistreerd")

        # Validate required fields via FieldConfigMixin
        self.service.validate_fields(tenant, data)

        # Skip _validate_category_and_purpose — gap-fill uses system values
        # like "Niet geregistreerd" which may not be in the user-configured
        # purposes list. The caller-provided category/purpose is trusted for
        # gap fills.

        # Validate odometer: end must be greater than start
        start_odometer = int(data["start_odometer"])
        end_odometer = int(data["end_odometer"])
        if end_odometer <= start_odometer:
            raise ValueError(
                "end_odometer must be greater than start_odometer "
                f"(got start={start_odometer}, end={end_odometer})"
            )

        # Validate trip_date is a valid date
        trip_date = self.service._parse_date(data["trip_date"])

        # Validate vehicle exists for this tenant
        self.service._validate_vehicle(tenant, data["vehicle_id"])

        # INSERT — no gap detection (this IS the gap fill)
        try:
            trip_id = self.db.execute_query(
                """INSERT INTO zzp_trips
                   (administration, vehicle_id, trip_date, start_time, end_time,
                    start_address, end_address, start_odometer, end_odometer,
                    trip_category, trip_purpose, route_description,
                    contact_id, project_name, notes,
                    is_billable, is_gap_fill, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s, %s)""",
                (
                    tenant,
                    int(data["vehicle_id"]),
                    trip_date,
                    data.get("start_time"),
                    data.get("end_time"),
                    data["start_address"].strip(),
                    data["end_address"].strip(),
                    start_odometer,
                    end_odometer,
                    data["trip_category"],
                    data["trip_purpose"],
                    data.get("route_description"),
                    data.get("contact_id"),
                    data.get("project_name"),
                    data.get("notes"),
                    data.get("is_billable", False),
                    True,  # is_gap_fill always True
                    created_by,
                ),
                fetch=False,
                commit=True,
            )
        except IntegrityError as e:
            raise IntegrityError(
                f"Foreign key constraint failed: {e}",
                error_code=e.error_code,
                original_error=e.original_error,
            )

        # Write audit entry
        self._write_audit_entry(
            tenant, trip_id, version=1, action="created", changed_by=created_by
        )

        trip = self.service.get_trip(tenant, trip_id)
        return {"success": True, "data": trip}

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
        """Insert an audit trail record into zzp_trip_audit.

        Args:
            tenant: Administration/tenant identifier.
            trip_id: The trip being audited.
            version: Current version of the trip.
            action: One of 'created', 'updated', 'cancelled'.
            changed_by: User who made the change.
            changed_fields: JSON string of field changes (for updates).
            correction_reason: Reason for the correction (for updates).
        """
        self.db.execute_query(
            """INSERT INTO zzp_trip_audit
               (administration, trip_id, version, action, changed_fields,
                correction_reason, changed_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                tenant,
                int(trip_id),
                int(version),
                action,
                changed_fields,
                correction_reason,
                changed_by,
            ),
            fetch=False,
            commit=True,
        )
