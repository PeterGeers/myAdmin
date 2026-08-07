"""
Data loaders for landing page live data blocks.

These loaders are invoked during PUBLISH to enrich the published JSON
with live data snapshots from the ZZP module.

Task: 3.11
"""

import logging

from database import DatabaseManager

logger = logging.getLogger(__name__)


def load_zzp_public_services(db: DatabaseManager, tenant: str) -> list[dict]:
    """
    Load ZZP products/services marked as public for a tenant.

    Queries the products table for active items with is_public = 1.
    The is_public flag is set via the ZZP service admin (task 3.13).

    Returns a list of service dicts for the ServicesBlock:
    [{"id": 1, "name": "Web Development", "description": "...", "price": "€95/uur", "category": "..."}]

    Args:
        db: DatabaseManager instance
        tenant: Administration identifier

    Returns:
        List of public service dicts, or empty list on failure.
    """
    query = """
        SELECT id, name, description, unit_price, unit_of_measure, product_type
        FROM products
        WHERE administration = %s
          AND is_active = TRUE
          AND is_public = 1
        ORDER BY name
    """
    try:
        results = db.execute_query(query, (tenant,))
        return [
            {
                "id": row["id"],
                "name": row.get("name", ""),
                "description": row.get("description", ""),
                "price": _format_price(
                    row.get("unit_price"), row.get("unit_of_measure")
                ),
                "category": row.get("product_type", ""),
            }
            for row in (results or [])
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to load ZZP services for %s: %s", tenant, e)
        return []


def _format_price(unit_price, unit_of_measure: str | None) -> str:
    """Format price with unit for display (e.g., '€95/uur')."""
    if unit_price is None:
        return ""
    try:
        amount = float(unit_price)
    except (TypeError, ValueError):
        return ""

    # Format with 2 decimals, strip trailing zeros
    formatted = f"€{amount:.2f}".rstrip("0").rstrip(".")
    if unit_of_measure:
        formatted += f"/{unit_of_measure}"
    return formatted
