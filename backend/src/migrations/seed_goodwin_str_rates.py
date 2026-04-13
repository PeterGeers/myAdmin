"""
Seed GoodwinSolutions STR-specific tax rates into tax_rates table.

btw_accommodation: which system BTW rate applies to STR accommodation.
  - 'low' (9%) until 2025-12-31
  - 'high' (21%) from 2026-01-01
  The actual rate/ledger comes from the system btw rates.

tourist_tax: municipality-specific, not in system defaults.
  - 6.02% until 2025-12-31
  - 6.9% from 2026-01-01

Idempotent: uses INSERT IGNORE.
"""
import sys, os, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from database import DatabaseManager

logger = logging.getLogger(__name__)

RATES = [
    ('GoodwinSolutions', 'btw_accommodation', 'low', 9.000, '2021',
     '2000-01-01', '2025-12-31',
     'BTW Logies laag tarief (verwijst naar btw low)', 'percentage'),
    ('GoodwinSolutions', 'btw_accommodation', 'high', 21.000, '2020',
     '2026-01-01', '9999-12-31',
     'BTW Logies hoog tarief (verwijst naar btw high)', 'percentage'),
    ('GoodwinSolutions', 'tourist_tax', 'standard', 6.020, None,
     '2000-01-01', '2025-12-31',
     'Toeristenbelasting 6.02%', 'percentage'),
    ('GoodwinSolutions', 'tourist_tax', 'standard', 6.900, None,
     '2026-01-01', '9999-12-31',
     'Toeristenbelasting 6.9%', 'percentage'),
]

SQL = ("INSERT IGNORE INTO tax_rates"
       " (administration, tax_type, tax_code, rate, ledger_account,"
       " effective_from, effective_to, description, calc_method)"
       " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)")


def run_seed(db=None):
    if db is None:
        db = DatabaseManager()
    inserted = 0
    for r in RATES:
        result = db.execute_query(SQL, r, fetch=False, commit=True)
        status = 'inserted' if result else 'exists'
        logger.info("%s %s from %s: %s", r[1], r[2], r[5], status)
        if result:
            inserted += 1
    logger.info("Done: %d of %d inserted.", inserted, len(RATES))
    return inserted


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    run_seed()
