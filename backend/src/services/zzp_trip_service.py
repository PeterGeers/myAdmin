"""
TripService: Trip CRUD with odometer validation and gap detection.

Core service for the Rittenregistratie (Trip/Mileage Registration) module.
Handles trip creation, retrieval, and listing with filtering/pagination.

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
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from db_exceptions import DatabaseError, IntegrityError
from dialect_helpers import dialect
from services.field_config_mixin import FieldConfigMixin

logger = logging.getLogger(__name__)


class TripService(FieldConfigMixin):
    """Trip CRUD with odometer validation and gap detection."""

    FIELD_CONFIG_KEY = "trip_field_config"
    ALWAYS_REQUIRED = [
        "vehicle_id",
        "trip_date",
        "start_address",
        "end_address",
        "start_odometer",
        "end_odometer",
        "trip_category",
        "trip_purpose",
    ]

    def __init__(self, db, parameter_service=None):
        self.db = db
        self.parameter_service = parameter_service

    def create_trip(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a new trip record with odometer gap detection.

        Validates required fields, odometer logic, and date.
        Detects gaps BEFORE insert (comparing against existing trips),
        then inserts the trip regardless of gap status.
        distance_km is auto-calculated by the DB generated column.

        Returns dict with:
            - "success": True
            - "data": the created trip dict
            - "warnings": list of warning dicts (if gap detected)
            - "gap_fill_offer": dict with suggested gap-fill data (if gap detected)

        Raises ValueError on validation failure.
        Raises IntegrityError on FK constraint violations.
        """
        # Validate required fields via FieldConfigMixin
        self.validate_fields(tenant, data)

        # Validate trip_category and trip_purpose against configured lists
        self._validate_category_and_purpose(
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
        trip_date = self._parse_date(data["trip_date"])

        # Validate vehicle exists for this tenant
        self._validate_vehicle(tenant, data["vehicle_id"])

        # Detect gap BEFORE insert (check against existing trips)
        gap_info = self.detect_gap(tenant, int(data["vehicle_id"]), start_odometer)

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
        self._write_audit_entry(tenant, trip_id, version=1,
                                action="created", changed_by=created_by)

        trip = self.get_trip(tenant, trip_id)

        # Build response with warnings if detected
        warnings = []
        result = {"success": True, "data": trip}

        if gap_info:
            gap_km = gap_info["gap_km"]
            prev_end = gap_info["previous_end_odometer"]
            curr_start = gap_info["current_start_odometer"]

            warnings.append({
                "type": "odometer_gap",
                "message": f"Gap of {gap_km} km detected ({prev_end} → {curr_start})",
                "gap_km": gap_km,
                "previous_end_odometer": prev_end,
                "current_start_odometer": curr_start,
            })
            result["gap_fill_offer"] = {
                "start_odometer": prev_end,
                "end_odometer": curr_start,
                "suggested_category": "Privé",
                "suggested_purpose": "Niet geregistreerd",
            }

        # Check for unusually large distance (Requirement 4.6)
        distance_km = end_odometer - start_odometer
        large_distance_threshold = self._get_ritten_param(
            "large_distance_warning", tenant, default=300
        )
        try:
            large_distance_threshold = int(large_distance_threshold)
        except (TypeError, ValueError):
            large_distance_threshold = 300

        if distance_km > large_distance_threshold:
            warnings.append({
                "type": "large_distance",
                "message": (
                    f"Unusually large distance: {distance_km} km "
                    f"(threshold: {large_distance_threshold} km)"
                ),
                "distance_km": distance_km,
                "threshold_km": large_distance_threshold,
            })

        if warnings:
            result["warnings"] = warnings

        return result

    # Fields that can be updated via update_trip (excludes distance_km which is generated)
    UPDATABLE_FIELDS = [
        "trip_date", "start_time", "end_time", "start_address", "end_address",
        "start_odometer", "end_odometer", "trip_category", "trip_purpose",
        "route_description", "contact_id", "project_name", "notes", "is_billable",
    ]

    def update_trip(
        self, tenant: str, trip_id: int, data: dict,
        correction_reason: str, updated_by: str
    ) -> dict:
        """Update/correct a trip with version increment and audit logging.

        Implements the correction workflow per Requirement 7:
        1. Fetch existing trip (verify exists + belongs to tenant)
        2. Require correction_reason
        3. Block editing of billed trips (is_billed = true)
        4. Compute changed_fields diff (old → new)
        5. Increment version
        6. UPDATE the trip record
        7. INSERT audit entry with action "updated"
        8. Return updated trip dict

        Args:
            tenant: Administration/tenant identifier.
            trip_id: The trip to update.
            data: Dict of fields to update (only UPDATABLE_FIELDS are accepted).
            correction_reason: Required reason for the correction.
            updated_by: Email/identifier of the user making the correction.

        Returns:
            Updated trip dict.

        Raises:
            ValueError: If trip not found, correction_reason missing,
                        trip is billed, or no valid fields to update.
        """
        # 1. Require correction_reason
        if not correction_reason or not correction_reason.strip():
            raise ValueError("correction_reason is required for trip updates")

        # 2. Fetch existing trip
        existing = self._get_raw_trip(tenant, trip_id)
        if not existing:
            raise ValueError(f"Trip {trip_id} not found for this tenant")

        # 3. Block editing billed trips
        if existing.get("is_billed"):
            raise ValueError(
                f"Trip {trip_id} is billed and cannot be edited. "
                "Unbill or create a new trip instead."
            )

        # 4. Filter to only updatable fields that are actually provided
        update_fields = {
            k: v for k, v in data.items()
            if k in self.UPDATABLE_FIELDS
        }
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
            old_comparable = self._normalize_for_comparison(old_value)
            new_comparable = self._normalize_for_comparison(new_value)
            if old_comparable != new_comparable:
                changed_fields[field] = {
                    "old": self._serialize_value(old_value),
                    "new": self._serialize_value(new_value),
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
        updated_trip = self.get_trip(tenant, trip_id)
        return updated_trip

    def cancel_trip(
        self, tenant: str, trip_id: int, cancel_reason: str, cancelled_by: str
    ) -> bool:
        """Soft-cancel a trip (sets is_cancelled = true with reason).

        Implements the cancellation workflow per Requirement 7:
        1. Require cancel_reason (raise ValueError if missing)
        2. Fetch existing trip (verify exists + belongs to tenant)
        3. Block cancellation of already-cancelled trips
        4. Block cancellation of billed trips (is_billed = true)
        5. Set is_cancelled = true and cancel_reason
        6. Write audit entry with action "cancelled"
        7. Return True on success

        Args:
            tenant: Administration/tenant identifier.
            trip_id: The trip to cancel.
            cancel_reason: Required reason for the cancellation.
            cancelled_by: Email/identifier of the user cancelling the trip.

        Returns:
            True on successful cancellation.

        Raises:
            ValueError: If cancel_reason missing, trip not found,
                        trip already cancelled, or trip is billed.
        """
        # 1. Require cancel_reason
        if not cancel_reason or not cancel_reason.strip():
            raise ValueError("cancel_reason is required for trip cancellation")

        # 2. Fetch existing trip
        existing = self._get_raw_trip(tenant, trip_id)
        if not existing:
            raise ValueError(f"Trip {trip_id} not found for this tenant")

        # 3. Block cancellation of already-cancelled trips
        if existing.get("is_cancelled"):
            raise ValueError(
                f"Trip {trip_id} is already cancelled"
            )

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

    def _get_raw_trip(self, tenant: str, trip_id: int) -> Optional[dict]:
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

    def get_trip(self, tenant: str, trip_id: int) -> Optional[dict]:
        """Get a single trip by ID, scoped to tenant."""
        rows = self.db.execute_query(
            "SELECT * FROM zzp_trips WHERE id = %s AND administration = %s",
            (trip_id, tenant),
        )
        if not rows:
            return None
        trip = self._format_trip(rows[0])
        # Enrich with contact info
        self.enrich_with_contacts(tenant, [trip])
        return trip

    def list_trips(self, tenant: str, filters: dict = None) -> dict:
        """List trips with filtering and pagination.

        Supported filters:
            vehicle_id, date_from, date_to, trip_category,
            contact_id, is_billed, is_gap_fill

        Pagination:
            limit (default 50), offset (default 0)

        Returns dict with 'data' (list of trips) and 'total' (count).
        """
        filters = filters or {}
        where_clauses = ["administration = %s", "is_cancelled = FALSE"]
        params: list = [tenant]

        # Apply filters
        if filters.get("vehicle_id"):
            where_clauses.append("vehicle_id = %s")
            params.append(int(filters["vehicle_id"]))

        if filters.get("date_from"):
            where_clauses.append("trip_date >= %s")
            params.append(filters["date_from"])

        if filters.get("date_to"):
            where_clauses.append("trip_date <= %s")
            params.append(filters["date_to"])

        if filters.get("trip_category"):
            where_clauses.append("trip_category = %s")
            params.append(filters["trip_category"])

        if filters.get("contact_id"):
            where_clauses.append("contact_id = %s")
            params.append(int(filters["contact_id"]))

        if "is_billed" in filters and filters["is_billed"] is not None:
            where_clauses.append("is_billed = %s")
            params.append(bool(filters["is_billed"]))

        if "is_gap_fill" in filters and filters["is_gap_fill"] is not None:
            where_clauses.append("is_gap_fill = %s")
            params.append(bool(filters["is_gap_fill"]))

        where_sql = " AND ".join(where_clauses)

        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM zzp_trips WHERE {where_sql}"
        count_rows = self.db.execute_query(count_query, tuple(params))
        total = count_rows[0]["total"] if count_rows else 0

        # Get paginated data
        limit = int(filters.get("limit", 50))
        offset = int(filters.get("offset", 0))

        data_query = (
            f"SELECT * FROM zzp_trips WHERE {where_sql} "
            f"ORDER BY trip_date DESC, id DESC "
            f"LIMIT %s OFFSET %s"
        )
        data_params = tuple(params) + (limit, offset)
        rows = self.db.execute_query(data_query, data_params) or []

        return {
            "data": self.enrich_with_contacts(tenant, [self._format_trip(r) for r in rows]),
            "total": total,
        }

    def create_gap_fill(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a gap-fill trip entry.

        A gap-fill trip represents unregistered kilometers between two trips.
        Per Belastingdienst rules, unregistered km default to worst-case
        assumptions: category "Privé", purpose "Niet geregistreerd".

        The caller may override category/purpose in data, but defaults are
        applied if not provided.

        Does NOT call detect_gap (since this IS the gap fill).
        Writes an audit entry with action "created".

        Args:
            tenant: Administration/tenant identifier.
            data: Dict with vehicle_id, trip_date, start_odometer, end_odometer,
                  start_address, end_address, trip_category (optional),
                  trip_purpose (optional).
            created_by: Email/identifier of the user creating this entry.

        Returns:
            {"success": True, "data": trip_dict}

        Raises ValueError on validation failure.
        Raises IntegrityError on FK constraint violations.
        """
        # Apply gap-fill defaults
        data = dict(data)  # Don't mutate caller's dict
        data["is_gap_fill"] = True
        data.setdefault("trip_category", "Privé")
        data.setdefault("trip_purpose", "Niet geregistreerd")

        # Validate required fields via FieldConfigMixin
        self.validate_fields(tenant, data)

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
        trip_date = self._parse_date(data["trip_date"])

        # Validate vehicle exists for this tenant
        self._validate_vehicle(tenant, data["vehicle_id"])

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
        self._write_audit_entry(tenant, trip_id, version=1,
                                action="created", changed_by=created_by)

        trip = self.get_trip(tenant, trip_id)
        return {"success": True, "data": trip}

    def get_unresolved_gaps(self, tenant: str, vehicle_id: int = None) -> List[dict]:
        """List gap-fill entries that are still unresolved.

        Unresolved gap-fill entries are trips where:
        - is_gap_fill = TRUE (auto-generated gap entry)
        - trip_purpose = 'Niet geregistreerd' (not yet updated by user)
        - is_cancelled = FALSE (still active)

        These represent gaps in the odometer chain that need user attention —
        the user should update the purpose to something meaningful.

        Args:
            tenant: Administration/tenant identifier.
            vehicle_id: Optional vehicle filter. If None, returns all
                        unresolved gaps for the tenant.

        Returns:
            List of formatted trip dicts, ordered by trip_date DESC.
        """
        where_clauses = [
            "administration = %s",
            "is_gap_fill = TRUE",
            "trip_purpose = %s",
            "is_cancelled = FALSE",
        ]
        params: list = [tenant, "Niet geregistreerd"]

        if vehicle_id is not None:
            where_clauses.append("vehicle_id = %s")
            params.append(int(vehicle_id))

        where_sql = " AND ".join(where_clauses)

        rows = self.db.execute_query(
            f"SELECT * FROM zzp_trips WHERE {where_sql} ORDER BY trip_date DESC",
            tuple(params),
        ) or []

        trips = [self._format_trip(r) for r in rows]
        self.enrich_with_contacts(tenant, trips)
        return trips

    def get_trip_history(self, tenant: str, trip_id: int) -> List[dict]:
        """Get the correction/audit history for a trip.

        Queries the zzp_trip_audit table for all entries related to the given
        trip, scoped to the tenant. Returns entries in chronological order.

        Each entry contains:
            - version: int
            - action: str ('created', 'updated', 'cancelled')
            - changed_fields: dict or None (parsed from JSON)
            - correction_reason: str or None
            - changed_by: str
            - changed_at: str (ISO format)

        Args:
            tenant: Administration/tenant identifier.
            trip_id: The trip to fetch history for.

        Returns:
            List of formatted audit entry dicts, ordered by changed_at ASC.
        """
        rows = self.db.execute_query(
            "SELECT version, action, changed_fields, correction_reason, "
            "changed_by, changed_at "
            "FROM zzp_trip_audit "
            "WHERE trip_id = %s AND administration = %s "
            "ORDER BY changed_at ASC",
            (int(trip_id), tenant),
        ) or []

        history = []
        for row in rows:
            entry = {
                "version": int(row["version"]),
                "action": row["action"],
                "changed_by": row["changed_by"],
                "changed_at": (
                    row["changed_at"].isoformat()
                    if hasattr(row["changed_at"], "isoformat")
                    else str(row["changed_at"])
                ),
            }

            # Parse changed_fields from JSON string to dict if present
            changed_fields = row.get("changed_fields")
            if changed_fields is not None:
                if isinstance(changed_fields, str):
                    try:
                        entry["changed_fields"] = json.loads(changed_fields)
                    except (json.JSONDecodeError, TypeError):
                        entry["changed_fields"] = changed_fields
                elif isinstance(changed_fields, dict):
                    # Already parsed (e.g., MySQL JSON column auto-deserialized)
                    entry["changed_fields"] = changed_fields
                else:
                    entry["changed_fields"] = changed_fields
            else:
                entry["changed_fields"] = None

            # Include correction_reason if present
            correction_reason = row.get("correction_reason")
            if correction_reason is not None:
                entry["correction_reason"] = correction_reason

            history.append(entry)

        return history

    def _write_audit_entry(
        self,
        tenant: str,
        trip_id: int,
        version: int,
        action: str,
        changed_by: str,
        changed_fields: str = None,
        correction_reason: str = None,
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

    # ── Odometer gap detection ─────────────────────────────

    def detect_gap(self, tenant: str, vehicle_id: int, start_odometer: int) -> Optional[dict]:
        """Detect an odometer gap between the previous trip and the new trip.

        Finds the most recent non-cancelled trip for the vehicle (ordered by
        end_odometer DESC) and compares its end_odometer with the given
        start_odometer. If no previous trips exist, compares against the
        vehicle's start_odometer from zzp_vehicles.

        Args:
            tenant: Administration/tenant identifier.
            vehicle_id: The vehicle to check.
            start_odometer: The new trip's starting odometer reading.

        Returns:
            Gap info dict if gap detected:
                {"gap_km": N, "previous_end_odometer": X, "current_start_odometer": Y}
            None if odometers match (no gap).
        """
        start_odometer = int(start_odometer)
        vehicle_id = int(vehicle_id)

        # Query the most recent non-cancelled trip's end_odometer for this vehicle
        rows = self.db.execute_query(
            "SELECT end_odometer FROM zzp_trips "
            "WHERE administration = %s AND vehicle_id = %s AND is_cancelled = FALSE "
            "ORDER BY end_odometer DESC LIMIT 1",
            (tenant, vehicle_id),
        )

        if rows:
            previous_end_odometer = int(rows[0]["end_odometer"])
        else:
            # First trip for this vehicle — compare against vehicle's start_odometer
            vehicle_rows = self.db.execute_query(
                "SELECT start_odometer FROM zzp_vehicles "
                "WHERE id = %s AND administration = %s",
                (vehicle_id, tenant),
            )
            if not vehicle_rows:
                # Vehicle not found; cannot detect gap
                return None
            previous_end_odometer = int(vehicle_rows[0]["start_odometer"])

        # Compare: gap exists when start_odometer > previous_end_odometer
        if start_odometer > previous_end_odometer:
            gap_km = start_odometer - previous_end_odometer
            return {
                "gap_km": gap_km,
                "previous_end_odometer": previous_end_odometer,
                "current_start_odometer": start_odometer,
            }

        # No gap
        return None

    # ── Contact enrichment ──────────────────────────────────

    def enrich_with_contacts(self, tenant: str, trips: List[dict]) -> List[dict]:
        """Enrich trip dicts with contact information (company_name).

        Batch-queries the contacts table to avoid N+1.
        Trips with a contact_id get a nested 'contact' object:
            {"id": <int>, "company_name": <str>}
        Trips without a contact_id get contact=None.
        If a contact_id references a non-existent contact (orphaned FK),
        the trip also gets contact=None.
        """
        # Collect unique non-null contact_ids
        contact_ids = list({
            t["contact_id"] for t in trips
            if t.get("contact_id") is not None
        })

        if not contact_ids:
            # No contacts to look up — set contact=None on all
            for trip in trips:
                trip["contact"] = None
            return trips

        # Batch query contacts table
        placeholders = ", ".join(["%s"] * len(contact_ids))
        query = (
            f"SELECT id, company_name FROM contacts "
            f"WHERE id IN ({placeholders}) AND administration = %s"
        )
        params = tuple(contact_ids) + (tenant,)
        rows = self.db.execute_query(query, params) or []

        # Build lookup dict
        lookup = {
            row["id"]: {"id": row["id"], "company_name": row["company_name"]}
            for row in rows
        }

        # Enrich each trip
        for trip in trips:
            cid = trip.get("contact_id")
            if cid is not None:
                trip["contact"] = lookup.get(cid)  # None if orphaned FK
            else:
                trip["contact"] = None

        return trips

    # ── Billing ─────────────────────────────────────────────

    def get_unbilled_trips(self, tenant: str, contact_id: int) -> List[dict]:
        """Get unbilled billable trips for a specific client.

        Filters for trips that are:
        - Scoped to the tenant (administration = tenant)
        - Linked to the given contact (contact_id = contact_id)
        - Marked as billable (is_billable = TRUE)
        - Not yet billed (is_billed = FALSE)
        - Not cancelled (is_cancelled = FALSE)

        Results are ordered by trip_date ASC (oldest first) for chronological
        billing.

        Args:
            tenant: Administration/tenant identifier.
            contact_id: The client's contact ID to filter on.

        Returns:
            List of formatted trip dicts enriched with contact info.
        """
        rows = self.db.execute_query(
            "SELECT * FROM zzp_trips "
            "WHERE administration = %s AND contact_id = %s "
            "AND is_billable = TRUE AND is_billed = FALSE AND is_cancelled = FALSE "
            "ORDER BY trip_date ASC",
            (tenant, int(contact_id)),
        ) or []

        trips = [self._format_trip(r) for r in rows]
        self.enrich_with_contacts(tenant, trips)
        return trips

    def mark_as_billed(self, tenant: str, trip_ids: list, invoice_id: int) -> int:
        """Mark specified trips as billed by linking them to an invoice.

        Updates trips that meet ALL conditions:
        - Belong to the tenant (administration = tenant)
        - ID is in the provided trip_ids list
        - Not already billed (is_billed = FALSE)
        - Not cancelled (is_cancelled = FALSE)

        Already-billed or cancelled trips are silently skipped (no error).

        Args:
            tenant: Administration/tenant identifier.
            trip_ids: List of trip IDs to mark as billed.
            invoice_id: The invoice ID to associate with the trips.

        Returns:
            Number of trips actually marked as billed.
        """
        if not trip_ids:
            return 0

        # Construct parameterized IN clause safely
        placeholders = ", ".join(["%s"] * len(trip_ids))
        params = [int(invoice_id), tenant] + [int(tid) for tid in trip_ids]

        query = (
            f"UPDATE zzp_trips "
            f"SET is_billed = TRUE, invoice_id = %s "
            f"WHERE administration = %s "
            f"AND id IN ({placeholders}) "
            f"AND is_billed = FALSE "
            f"AND is_cancelled = FALSE"
        )

        result = self.db.execute_query(query, tuple(params), fetch=False, commit=True)
        return result or 0

    # ── Summary & Bijtelling ───────────────────────────────

    # Miles-to-km conversion factor
    MILES_TO_KM = 1.60934

    def get_summary(self, tenant: str, vehicle_id: int, year: int) -> dict:
        """Get yearly trip summary with bijtelling/tax deduction tracking.

        For business vehicles: calculates bijtelling_km (Privé + Woon-werk)
        and warns when approaching the 500 km threshold.

        For private-for-business vehicles: calculates tax_deduction
        (zakelijk_km × default_km_rate).

        Respects odometer_unit: converts miles to km if vehicle uses miles.
        Only counts non-cancelled trips.

        Returns dict matching the GET /api/zzp/trips/summary response schema.
        """
        # Fetch vehicle to determine type and odometer unit
        vehicle = self._get_vehicle_info(tenant, vehicle_id)
        if not vehicle:
            raise ValueError(f"Vehicle {vehicle_id} not found for this tenant")

        vehicle_type = vehicle["vehicle_type"]
        odometer_unit = vehicle.get("odometer_unit", "km")

        # Fetch parameters
        bijtelling_limit = self._get_ritten_param(
            "bijtelling_limit", tenant, default=500
        )
        bijtelling_warning_threshold = self._get_ritten_param(
            "bijtelling_warning_threshold", tenant, default=400
        )
        default_km_rate = self._get_ritten_param(
            "default_km_rate", tenant, default=0.23
        )

        # Query category totals for the year (non-cancelled only)
        year_filter = dialect.year("trip_date")
        category_query = (
            f"SELECT trip_category, SUM(distance_km) as total_km "
            f"FROM zzp_trips "
            f"WHERE administration = %s AND vehicle_id = %s "
            f"AND {year_filter} = %s AND is_cancelled = FALSE "
            f"GROUP BY trip_category"
        )
        category_rows = self.db.execute_query(
            category_query, (tenant, int(vehicle_id), int(year))
        ) or []

        # Parse category totals
        zakelijk_km = 0
        prive_km = 0
        woonwerk_km = 0
        for row in category_rows:
            cat = row["trip_category"]
            km = int(row["total_km"] or 0)
            if cat == "Zakelijk":
                zakelijk_km = km
            elif cat == "Privé":
                prive_km = km
            elif cat == "Woon-werk":
                woonwerk_km = km

        total_km = zakelijk_km + prive_km + woonwerk_km

        # Convert if vehicle uses miles (distance_km column stores raw
        # odometer difference; if unit is miles, convert to km)
        if odometer_unit == "miles":
            zakelijk_km = round(zakelijk_km * self.MILES_TO_KM)
            prive_km = round(prive_km * self.MILES_TO_KM)
            woonwerk_km = round(woonwerk_km * self.MILES_TO_KM)
            total_km = round(total_km * self.MILES_TO_KM)

        # Calculate bijtelling (business vehicles) or tax deduction (private)
        bijtelling_km = prive_km + woonwerk_km
        bijtelling_warning = bijtelling_km >= bijtelling_warning_threshold

        tax_deduction = 0.0
        if vehicle_type == "private_for_business":
            tax_deduction = round(zakelijk_km * float(default_km_rate), 2)

        # Query monthly breakdown
        month_format = dialect.date_format("trip_date", "%Y-%m")
        monthly_query = (
            f"SELECT {month_format} as month, trip_category, "
            f"SUM(distance_km) as total_km "
            f"FROM zzp_trips "
            f"WHERE administration = %s AND vehicle_id = %s "
            f"AND {year_filter} = %s AND is_cancelled = FALSE "
            f"GROUP BY {month_format}, trip_category "
            f"ORDER BY month"
        )
        monthly_rows = self.db.execute_query(
            monthly_query, (tenant, int(vehicle_id), int(year))
        ) or []

        # Build monthly breakdown dict
        monthly_map: dict = {}
        for row in monthly_rows:
            month = row["month"]
            cat = row["trip_category"]
            km = int(row["total_km"] or 0)
            if odometer_unit == "miles":
                km = round(km * self.MILES_TO_KM)
            if month not in monthly_map:
                monthly_map[month] = {"month": month, "zakelijk": 0, "prive": 0, "woonwerk": 0}
            if cat == "Zakelijk":
                monthly_map[month]["zakelijk"] = km
            elif cat == "Privé":
                monthly_map[month]["prive"] = km
            elif cat == "Woon-werk":
                monthly_map[month]["woonwerk"] = km

        monthly_breakdown = list(monthly_map.values())

        return {
            "year": int(year),
            "vehicle_id": int(vehicle_id),
            "total_km": total_km,
            "zakelijk_km": zakelijk_km,
            "prive_km": prive_km,
            "woonwerk_km": woonwerk_km,
            "bijtelling_km": bijtelling_km,
            "bijtelling_limit": int(bijtelling_limit),
            "bijtelling_warning": bijtelling_warning,
            "tax_deduction": tax_deduction,
            "monthly_breakdown": monthly_breakdown,
        }

    def get_bijtelling_status(self, tenant: str, vehicle_id: int, year: int) -> dict:
        """Lightweight bijtelling status for a vehicle.

        Returns just the bijtelling tracking data (no monthly breakdown).
        Useful for dashboard widgets and quick status checks.
        """
        # Fetch vehicle info
        vehicle = self._get_vehicle_info(tenant, vehicle_id)
        if not vehicle:
            raise ValueError(f"Vehicle {vehicle_id} not found for this tenant")

        vehicle_type = vehicle["vehicle_type"]
        odometer_unit = vehicle.get("odometer_unit", "km")

        # Fetch parameters
        bijtelling_limit = self._get_ritten_param(
            "bijtelling_limit", tenant, default=500
        )
        bijtelling_warning_threshold = self._get_ritten_param(
            "bijtelling_warning_threshold", tenant, default=400
        )

        # Query non-business km (Privé + Woon-werk) for the year
        year_filter = dialect.year("trip_date")
        query = (
            f"SELECT SUM(distance_km) as total_km "
            f"FROM zzp_trips "
            f"WHERE administration = %s AND vehicle_id = %s "
            f"AND {year_filter} = %s AND is_cancelled = FALSE "
            f"AND trip_category IN ('Privé', 'Woon-werk')"
        )
        rows = self.db.execute_query(
            query, (tenant, int(vehicle_id), int(year))
        ) or []

        bijtelling_km = int(rows[0]["total_km"] or 0) if rows else 0

        # Convert if vehicle uses miles
        if odometer_unit == "miles":
            bijtelling_km = round(bijtelling_km * self.MILES_TO_KM)

        remaining_km = max(0, int(bijtelling_limit) - bijtelling_km)
        bijtelling_warning = bijtelling_km >= bijtelling_warning_threshold
        bijtelling_exceeded = bijtelling_km > int(bijtelling_limit)

        return {
            "year": int(year),
            "vehicle_id": int(vehicle_id),
            "vehicle_type": vehicle_type,
            "bijtelling_km": bijtelling_km,
            "bijtelling_limit": int(bijtelling_limit),
            "bijtelling_warning": bijtelling_warning,
            "bijtelling_exceeded": bijtelling_exceeded,
            "remaining_km": remaining_km,
        }

    # ── Private helpers ─────────────────────────────────────

    def _get_vehicle_info(self, tenant: str, vehicle_id: int) -> Optional[dict]:
        """Fetch vehicle type and odometer_unit for summary calculations."""
        rows = self.db.execute_query(
            "SELECT id, vehicle_type, odometer_unit FROM zzp_vehicles "
            "WHERE id = %s AND administration = %s",
            (int(vehicle_id), tenant),
        )
        return rows[0] if rows else None

    def _get_ritten_param(self, key: str, tenant: str, default=None):
        """Fetch a zzp_ritten parameter with fallback to MODULE_REGISTRY default.

        Args:
            key: Parameter key (e.g. 'bijtelling_limit')
            tenant: Tenant administration value
            default: Fallback if neither ParameterService nor registry has it
        """
        if self.parameter_service:
            value = self.parameter_service.get_param(
                "zzp_ritten", key, tenant=tenant
            )
            if value is not None:
                return value

        # Fallback to MODULE_REGISTRY
        from services.module_registry import MODULE_REGISTRY

        registry_key = f"zzp_ritten.{key}"
        params = MODULE_REGISTRY.get("ZZP", {}).get("required_params", {})
        if registry_key in params:
            return params[registry_key]["default"]

        return default

    def get_trip_categories(self, tenant: str) -> List[str]:
        """Return configured trip categories from ParameterService or defaults."""
        if self.parameter_service:
            categories = self.parameter_service.get_param(
                "zzp_ritten", "trip_categories", tenant=tenant
            )
            if categories:
                return categories
        from services.module_registry import MODULE_REGISTRY

        return list(
            MODULE_REGISTRY["ZZP"]["required_params"]["zzp_ritten.trip_categories"][
                "default"
            ]
        )

    def get_trip_purposes(self, tenant: str) -> List[str]:
        """Return configured trip purposes from ParameterService or defaults."""
        if self.parameter_service:
            purposes = self.parameter_service.get_param(
                "zzp_ritten", "trip_purposes", tenant=tenant
            )
            if purposes:
                return purposes
        from services.module_registry import MODULE_REGISTRY

        return list(
            MODULE_REGISTRY["ZZP"]["required_params"]["zzp_ritten.trip_purposes"][
                "default"
            ]
        )

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
                return datetime.strptime(value, "%Y-%m-%d").date()
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
            if val is not None and hasattr(val, "isoformat") and not isinstance(val, str):
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
