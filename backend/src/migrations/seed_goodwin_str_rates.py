"""
Seed STR-specific tax rates into tax_rates table for a given administration.

btw_accommodation: which system BTW rate applies to STR accommodation.
  - 'low' (9%) until 2025-12-31
  - 'high' (21%) from 2026-01-01
  The actual rate/ledger comes from the system btw rates.

tourist_tax: municipality-specific, not in system defaults.
  - 6.02% until 2025-12-31
  - 6.9% from 2026-01-01

Idempotent: uses INSERT IGNORE.

Usage:
    run_seed("ExampleTenant")
    run_seed("ExampleTenant", db=my_db_instance)
"""

import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from database import DatabaseManager

logger = logging.getLogger(__name__)

SQL = (
    "INSERT IGNORE INTO tax_rates"
    " (administration, tax_type, tax_code, rate, ledger_account,"
    " effective_from, effective_to, description, calc_method)"
    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
)


def _build_rates(administration: str):
    """Build the RATES tuples for the given administration."""
    return [
        (
            administration,
            "btw_accommodation",
            "low",
            9.000,
            "2021",
            "2000-01-01",
            "2025-12-31",
            "BTW Logies laag tarief (verwijst naar btw low)",
            "percentage",
        ),
        (
            administration,
            "btw_accommodation",
            "high",
            21.000,
            "2020",
            "2026-01-01",
            "9999-12-31",
            "BTW Logies hoog tarief (verwijst naar btw high)",
            "percentage",
        ),
        (
            administration,
            "tourist_tax",
            "standard",
            6.020,
            None,
            "2000-01-01",
            "2025-12-31",
            "Toeristenbelasting 6.02%",
            "percentage",
        ),
        (
            administration,
            "tourist_tax",
            "standard",
            6.900,
            None,
            "2026-01-01",
            "9999-12-31",
            "Toeristenbelasting 6.9%",
            "percentage",
        ),
    ]


def run_seed(administration: str, db=None):
    """Seed STR tax rates for the given administration.

    Args:
        administration: Tenant name (e.g. "ExampleTenant").
        db: Optional DatabaseManager instance. Created if not provided.

    Returns:
        Number of rows inserted.
    """
    if not administration:
        raise ValueError("administration is required for seeding tax rates")
    if db is None:
        db = DatabaseManager()
    rates = _build_rates(administration)
    inserted = 0
    for r in rates:
        result = db.execute_query(SQL, r, fetch=False, commit=True)
        status = "inserted" if result else "exists"
        logger.info("%s %s from %s: %s", r[1], r[2], r[5], status)
        if result:
            inserted += 1
    logger.info("Done: %d of %d inserted.", inserted, len(rates))
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 2:
        print("Usage: python seed_goodwin_str_rates.py <administration>")
        print("Example: python seed_goodwin_str_rates.py GoodwinSolutions")
        sys.exit(1)
    run_seed(sys.argv[1])
