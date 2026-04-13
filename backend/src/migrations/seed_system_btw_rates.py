"""
Seed script: Insert NL system default BTW rates into tax_rates table.

Seeds three system-level BTW rates:
  - zero  (0.000%, ledger 2010)
  - low   (9.000%, ledger 2021)
  - high  (21.000%, ledger 2020)

Idempotent: skips rows that already exist (uses INSERT IGNORE).
Does NOT seed btw_accommodation or tourist_tax (tenant-specific).

Requirements: 2.8, 2.9
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database import DatabaseManager

logger = logging.getLogger(__name__)

SYSTEM_BTW_RATES = [
    ('_system_', 'btw', 'zero', 0.000, '2010', '2000-01-01', 'BTW 0% - Vrijgesteld'),
    ('_system_', 'btw', 'low', 9.000, '2021', '2000-01-01', 'BTW Laag tarief'),
    ('_system_', 'btw', 'high', 21.000, '2020', '2000-01-01', 'BTW Hoog tarief'),
]


def run_seed(db=None):
    """Insert NL system default BTW rates. Skips duplicates."""
    if db is None:
        db = DatabaseManager()

    insert_sql = """
        INSERT IGNORE INTO tax_rates
            (administration, tax_type, tax_code, rate, ledger_account, effective_from, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    inserted = 0
    for row in SYSTEM_BTW_RATES:
        result = db.execute_query(insert_sql, row, fetch=False, commit=True)
        if result and result > 0:
            inserted += 1
            logger.info("Inserted BTW rate: %s (%s)", row[2], row[6])
        else:
            logger.info("BTW rate '%s' already exists, skipped.", row[2])

    logger.info("Seed complete: %d of %d rates inserted.", inserted, len(SYSTEM_BTW_RATES))
    return inserted


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_seed()
