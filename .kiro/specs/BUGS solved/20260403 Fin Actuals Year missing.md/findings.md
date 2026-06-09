In FIN Reports the Actuals tab there is a block Profit & Loss (VW = Y)

## Problem

Years before the most recent closed year show €0 in the P&L report.

## Root cause

The `mutaties_cache.py` optimization only loads:

- Open years (not in `year_closure_status` table)
- The most recent closed year (for comparisons)

Older closed years are never loaded into the cache. When the P&L report requests years 2021-2026, the cache doesn't have data for 2021, 2022, or 2023.

## Fix

Added on-demand year loading to `MutatiesCache`:

- `get_data()` now accepts optional `requested_years` parameter
- When specific years are requested, checks if they're in the cache
- Missing years are loaded from the database and appended to the cached DataFrame
- Thread-safe with double-check locking
- Only the actuals routes pass `requested_years` — other callers are unaffected

Files changed:

- `backend/src/mutaties_cache.py` — added `_ensure_years_loaded()` method
- `backend/src/actuals_routes.py` — pass `requested_years` to `cache.get_data()`
