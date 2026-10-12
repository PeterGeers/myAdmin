"""
TripQueryService: Trip query, listing, and tax-log operations.

Handles trip retrieval, filtering, pagination, gap detection, and audit
history. Trips carry a free-text ``client_name`` (Klant) directly — there is
no contacts JOIN and no billing path on any read query (Req 4.3, 4.5, 4.4).
Extracted from zzp_trip_service.py for file size compliance (<500 lines).

Reference: .kiro/specs/ZZP/rittenregistratie/design.md §4.2
"""

import json
import logging

logger = logging.getLogger(__name__)

# Non-billing columns selected on every trip read path. Mirrors the
# post-redesign zzp_trips schema: includes free-text ``client_name`` and
# excludes the dropped billing/contact-link columns (contact_id, is_billable,
# is_billed, invoice_id) — Req 4.5.
_TRIP_COLUMNS = (
    "id, administration, vehicle_id, trip_date, start_time, end_time, "
    "start_address, end_address, start_odometer, end_odometer, distance_km, "
    "trip_category, trip_purpose, route_description, project_name, notes, "
    "client_name, is_gap_fill, is_cancelled, cancel_reason, version, "
    "created_at, updated_at, created_by"
)


class TripQueryService:
    """Trip query operations: get, list, history, gaps."""

    def __init__(self, service):
        """Initialize with reference to the parent TripService.

        Args:
            service: TripService instance (provides db, parameter_service,
                     and helper methods).
        """
        self.service = service
        self.db = service.db

    def get_trip(self, tenant: str, trip_id: int) -> dict | None:
        """Get a single trip by ID, scoped to tenant.

        Returns the trip with ``client_name`` directly; no nested contact
        object and no ``contact_id`` (Req 4.5). The query is always scoped to
        the tenant via ``WHERE administration = %s`` (Req 10.5).
        """
        rows = self.db.execute_query(
            f"SELECT {_TRIP_COLUMNS} FROM zzp_trips "
            "WHERE id = %s AND administration = %s",
            (trip_id, tenant),
        )
        if not rows:
            return None
        return self.service._format_trip(rows[0])

    def list_trips(self, tenant: str, filters: dict | None = None) -> dict:
        """List trips with filtering and pagination.

        Supported filters:
            vehicle_id, date_from, date_to, trip_category, is_gap_fill

        Billing-related filters (``is_billed``, ``contact_id``) are not wired
        into the WHERE builder — they are silently ignored, so a request
        carrying them returns the same full, unfiltered result set as one
        without them, raising no error (Req 4.3).

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
            f"SELECT {_TRIP_COLUMNS} FROM zzp_trips WHERE {where_sql} "
            f"ORDER BY trip_date DESC, id DESC "
            f"LIMIT %s OFFSET %s"
        )
        data_params = tuple(params) + (limit, offset)
        rows = self.db.execute_query(data_query, data_params) or []

        return {
            "data": [self.service._format_trip(r) for r in rows],
            "total": total,
        }

    def get_trip_history(self, tenant: str, trip_id: int) -> list[dict]:
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
        rows = (
            self.db.execute_query(
                "SELECT version, action, changed_fields, correction_reason, "
                "changed_by, changed_at "
                "FROM zzp_trip_audit "
                "WHERE trip_id = %s AND administration = %s "
                "ORDER BY changed_at ASC",
                (int(trip_id), tenant),
            )
            or []
        )

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

    def get_unresolved_gaps(
        self, tenant: str, vehicle_id: int | None = None
    ) -> list[dict]:
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

        rows = (
            self.db.execute_query(
                f"SELECT {_TRIP_COLUMNS} FROM zzp_trips WHERE {where_sql} "
                "ORDER BY trip_date DESC",
                tuple(params),
            )
            or []
        )

        return [self.service._format_trip(r) for r in rows]

    # ── Odometer gap detection ─────────────────────────────

    def detect_gap(
        self, tenant: str, vehicle_id: int, start_odometer: int
    ) -> dict | None:
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

    # ── Billing ─────────────────────────────────────────────

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
