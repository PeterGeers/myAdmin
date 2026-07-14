"""
RoutePresetService: Route preset management with auto-learning.

Manages frequently-used routes for quick trip entry. Supports both manual
presets (user-created) and auto-learned presets (tracked from usage).

Business rules:
- get_suggestions: returns top X presets by use_count in last 6 months
  PLUS all manual presets. X comes from parameter `zzp_ritten.max_route_presets`
  (default 5).
- create_preset: creates a manual preset (is_manual=True)
- update_preset: updates default_category, default_purpose, typical_distance_km, contact_id
- delete_preset: hard delete
- increment_usage: UPSERT — if route exists, increment use_count + update last_used_at;
  if not, create with use_count=1, is_manual=False

Reference: .kiro/specs/ZZP/rittenregistratie/design.md §4.3
"""

import logging
from typing import List, Optional

from dialect_helpers import dialect

logger = logging.getLogger(__name__)


class RoutePresetService:
    """Route preset management with auto-learning."""

    def __init__(self, db, parameter_service=None):
        self.db = db
        self.parameter_service = parameter_service

    def get_suggestions(self, tenant: str, limit: Optional[int] = None) -> List[dict]:
        """Return top X presets by use_count in last 6 months, plus all manual presets.

        The limit X comes from parameter `zzp_ritten.max_route_presets` (default 5),
        or can be overridden via the `limit` parameter.

        Returns a deduplicated list: auto-learned presets (top X by usage in 6 months)
        merged with all manual presets. Manual presets always appear even if they haven't
        been used recently.
        """
        max_presets = limit if limit is not None else self._get_max_route_presets(tenant)

        # Query 1: Top X auto-learned presets by use_count in last 6 months
        six_months_ago = dialect.date_subtract(dialect.current_timestamp(), 6, "MONTH")
        auto_query = f"""
            SELECT * FROM zzp_route_presets
            WHERE administration = %s
              AND is_manual = FALSE
              AND last_used_at >= {six_months_ago}
            ORDER BY use_count DESC
            LIMIT %s
        """
        auto_rows = self.db.execute_query(
            auto_query, (tenant, max_presets)
        ) or []

        # Query 2: All manual presets (always shown regardless of usage)
        manual_query = """
            SELECT * FROM zzp_route_presets
            WHERE administration = %s
              AND is_manual = TRUE
            ORDER BY from_address, to_address
        """
        manual_rows = self.db.execute_query(manual_query, (tenant,)) or []

        # Merge and deduplicate (manual presets take priority if same route exists)
        seen_ids = set()
        results = []

        for row in manual_rows:
            seen_ids.add(row["id"])
            results.append(self._format_preset(row))

        for row in auto_rows:
            if row["id"] not in seen_ids:
                seen_ids.add(row["id"])
                results.append(self._format_preset(row))

        return results

    def create_preset(self, tenant: str, data: dict) -> dict:
        """Create a manual route preset.

        Required fields: from_address, to_address.
        Optional fields: default_category, default_purpose, contact_id, typical_distance_km.
        """
        required = ["from_address", "to_address"]
        for field in required:
            if field not in data or not data[field]:
                raise ValueError(f"Missing required field: {field}")

        preset_id = self.db.execute_query(
            """INSERT INTO zzp_route_presets
               (administration, from_address, to_address, default_category,
                default_purpose, contact_id, typical_distance_km,
                use_count, is_manual)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                tenant,
                data["from_address"].strip(),
                data["to_address"].strip(),
                data.get("default_category"),
                data.get("default_purpose"),
                data.get("contact_id"),
                data.get("typical_distance_km"),
                0,
                True,
            ),
            fetch=False,
            commit=True,
        )

        return self.get_preset(tenant, preset_id)

    def update_preset(self, tenant: str, preset_id: int, data: dict) -> dict:
        """Update a route preset's defaults.

        Updatable fields: default_category, default_purpose, typical_distance_km, contact_id.
        Returns the updated preset dict.
        Raises ValueError if preset not found.
        """
        existing = self.get_preset(tenant, preset_id)
        if not existing:
            raise ValueError(f"Route preset {preset_id} not found")

        updatable_fields = [
            "default_category", "default_purpose",
            "typical_distance_km", "contact_id",
        ]
        sets, params = [], []
        for field in updatable_fields:
            if field in data:
                sets.append(f"{field} = %s")
                params.append(data[field])

        if not sets:
            return existing

        params.extend([preset_id, tenant])
        self.db.execute_query(
            f"UPDATE zzp_route_presets SET {', '.join(sets)} "
            f"WHERE id = %s AND administration = %s",
            tuple(params),
            fetch=False,
            commit=True,
        )

        return self.get_preset(tenant, preset_id)

    def delete_preset(self, tenant: str, preset_id: int) -> bool:
        """Hard delete a route preset.

        Returns True on success. Raises ValueError if preset not found.
        """
        existing = self.get_preset(tenant, preset_id)
        if not existing:
            raise ValueError(f"Route preset {preset_id} not found")

        self.db.execute_query(
            "DELETE FROM zzp_route_presets WHERE id = %s AND administration = %s",
            (preset_id, tenant),
            fetch=False,
            commit=True,
        )
        return True

    def increment_usage(self, tenant: str, from_address: str, to_address: str) -> None:
        """UPSERT route usage: increment use_count if exists, else create with use_count=1.

        This is called automatically when a trip is created to track route frequency.
        Auto-learned presets have is_manual=False.
        """
        from_addr = from_address.strip()
        to_addr = to_address.strip()

        # Check if route preset already exists for this tenant + address combo
        rows = self.db.execute_query(
            """SELECT id, use_count FROM zzp_route_presets
               WHERE administration = %s
                 AND from_address = %s
                 AND to_address = %s""",
            (tenant, from_addr, to_addr),
        )

        if rows:
            # Update: increment use_count and refresh last_used_at
            self.db.execute_query(
                f"""UPDATE zzp_route_presets
                    SET use_count = use_count + 1,
                        last_used_at = {dialect.current_timestamp()}
                    WHERE id = %s AND administration = %s""",
                (rows[0]["id"], tenant),
                fetch=False,
                commit=True,
            )
        else:
            # Insert: new auto-learned preset
            self.db.execute_query(
                f"""INSERT INTO zzp_route_presets
                    (administration, from_address, to_address, use_count,
                     last_used_at, is_manual)
                    VALUES (%s, %s, %s, %s, {dialect.current_timestamp()}, %s)""",
                (tenant, from_addr, to_addr, 1, False),
                fetch=False,
                commit=True,
            )

    # ── Helper methods ──────────────────────────────────────

    def get_preset(self, tenant: str, preset_id: int) -> Optional[dict]:
        """Get a single preset by ID, scoped to tenant."""
        rows = self.db.execute_query(
            "SELECT * FROM zzp_route_presets WHERE id = %s AND administration = %s",
            (preset_id, tenant),
        )
        return self._format_preset(rows[0]) if rows else None

    def _get_max_route_presets(self, tenant: str) -> int:
        """Fetch max_route_presets parameter with fallback to default 5."""
        if self.parameter_service:
            value = self.parameter_service.get_param(
                "zzp_ritten", "max_route_presets", tenant=tenant
            )
            if value is not None:
                return int(value)

        # Fallback to MODULE_REGISTRY
        from services.module_registry import MODULE_REGISTRY

        params = MODULE_REGISTRY.get("ZZP", {}).get("required_params", {})
        registry_key = "zzp_ritten.max_route_presets"
        if registry_key in params:
            return int(params[registry_key]["default"])

        return 5

    @staticmethod
    def _format_preset(row: dict) -> dict:
        """Convert datetime objects to ISO strings for JSON serialization."""
        row = dict(row)
        for key in ("last_used_at", "created_at", "updated_at"):
            val = row.get(key)
            if val is not None and hasattr(val, "isoformat") and not isinstance(val, str):
                row[key] = val.isoformat()
        # Ensure booleans
        if "is_manual" in row:
            row["is_manual"] = bool(row["is_manual"])
        # Ensure integers
        if "use_count" in row and row["use_count"] is not None:
            row["use_count"] = int(row["use_count"])
        if "typical_distance_km" in row and row["typical_distance_km"] is not None:
            row["typical_distance_km"] = int(row["typical_distance_km"])
        return row
