"""
TripCalculationService: Trip summary and bijtelling calculations.

Handles yearly summaries, bijtelling (company car tax addition) tracking,
tax deduction calculations, and vehicle parameter lookups.
Extracted from zzp_trip_service.py for file size compliance (<500 lines).

Business rules:
- Business vehicles: bijtelling = Privé + Woon-werk km (warn at threshold)
- Private-for-business: tax_deduction = zakelijk_km × default_km_rate
- Odometer unit conversion: miles → km if vehicle uses miles
- Parameters from ParameterService with MODULE_REGISTRY fallback

Reference: .kiro/specs/ZZP/rittenregistratie/design.md §4.2
"""

import logging
from typing import Dict, List, Optional

from dialect_helpers import dialect

logger = logging.getLogger(__name__)

# Miles-to-km conversion factor
MILES_TO_KM = 1.60934


class TripCalculationService:
    """Trip calculation operations: summaries, bijtelling, parameters."""

    def __init__(self, service):
        """Initialize with reference to the parent TripService.

        Args:
            service: TripService instance (provides db, parameter_service).
        """
        self.service = service
        self.db = service.db

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
            zakelijk_km = round(zakelijk_km * MILES_TO_KM)
            prive_km = round(prive_km * MILES_TO_KM)
            woonwerk_km = round(woonwerk_km * MILES_TO_KM)
            total_km = round(total_km * MILES_TO_KM)

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
                km = round(km * MILES_TO_KM)
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
            bijtelling_km = round(bijtelling_km * MILES_TO_KM)

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

    # ── Parameter and vehicle helpers ──────────────────────

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
        if self.service.parameter_service:
            value = self.service.parameter_service.get_param(
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
        if self.service.parameter_service:
            categories = self.service.parameter_service.get_param(
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
        if self.service.parameter_service:
            purposes = self.service.parameter_service.get_param(
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
