"""
TaxRateService: Looks up time-versioned tax rates with tenant -> _system_ fallback.

Supports date-filtered resolution, auto-close on overlap, and in-process caching.

Requirements: 2.3, 2.4, 2.5, 2.6, 2.7
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_DATE = date(9999, 12, 31)


class TaxRateService:
    """Looks up time-versioned tax rates with tenant -> _system_ fallback."""

    def __init__(self, db):
        self._cache: Dict[tuple, Any] = {}
        self.db = db

    def get_tax_rate(self, administration: str, tax_type: str, tax_code: str,
                     reference_date: date) -> Optional[dict]:
        """
        Get applicable tax rate for a given date.
        Checks tenant-specific first, falls back to _system_ defaults.
        Returns dict with rate, ledger_account, description, calc_method,
        calc_params or None if no rate found.
        """
        cache_key = (administration, tax_type, tax_code, reference_date)
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._lookup_rate(administration, tax_type, tax_code, reference_date)
        if result is None and administration != '_system_':
            result = self._lookup_rate('_system_', tax_type, tax_code, reference_date)

        if result is not None:
            self._cache[cache_key] = result
        return result

    def get_all_vat_codes(self, administration: str, reference_date: date) -> List[dict]:
        """
        Get all active BTW codes for a tenant on a given date.
        Returns list of {code, rate, ledger_account, description},
        preferring tenant-specific rates over system defaults per code.
        """
        query = """
            SELECT id, administration, tax_code, rate, ledger_account, description
            FROM tax_rates
            WHERE tax_type = 'btw'
              AND administration IN (%s, '_system_')
              AND effective_from <= %s
              AND effective_to >= %s
            ORDER BY tax_code, FIELD(administration, %s, '_system_')
        """
        rows = self.db.execute_query(
            query, (administration, reference_date, reference_date, administration), fetch=True
        )

        seen_codes = {}
        results = []
        for row in rows:
            code = row['tax_code']
            if code in seen_codes:
                continue
            seen_codes[code] = True
            results.append({
                'code': code,
                'rate': self._to_float(row['rate']),
                'ledger_account': row.get('ledger_account'),
                'description': row.get('description'),
            })
        return results

    def create_tax_rate(self, administration: str, tax_type: str, tax_code: str,
                        rate: float, effective_from: date, ledger_account: str = None,
                        effective_to: date = None, description: str = None,
                        calc_method: str = 'percentage', calc_params: dict = None,
                        created_by: str = None) -> int:
        """
        Create a new tax rate. Auto-closes any existing rate whose date range
        overlaps with the new rate's effective_from.
        Returns the new rate's ID.
        """
        if effective_to is None:
            effective_to = MAX_DATE

        if effective_from > effective_to:
            raise ValueError(
                f"effective_from ({effective_from}) must be <= effective_to ({effective_to})"
            )

        # Auto-close overlapping existing rate
        self._auto_close_overlapping(administration, tax_type, tax_code, effective_from)

        calc_params_json = json.dumps(calc_params) if calc_params else None

        insert_sql = """
            INSERT INTO tax_rates
                (administration, tax_type, tax_code, rate, ledger_account,
                 effective_from, effective_to, description, calc_method, calc_params, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        result = self.db.execute_query(
            insert_sql,
            (administration, tax_type, tax_code, rate, ledger_account,
             effective_from, effective_to, description, calc_method,
             calc_params_json, created_by),
            fetch=False, commit=True
        )
        self._invalidate_cache()
        return result

    def delete_tax_rate(self, rate_id: int, administration: str) -> bool:
        """
        Delete a tenant-specific tax rate override.
        System defaults (_system_) cannot be deleted via this method.
        """
        if administration == '_system_':
            raise PermissionError("System default tax rates cannot be deleted via this method")

        delete_sql = """
            DELETE FROM tax_rates WHERE id = %s AND administration = %s
        """
        result = self.db.execute_query(
            delete_sql, (rate_id, administration), fetch=False, commit=True
        )
        self._invalidate_cache()
        return result is not None and result > 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lookup_rate(self, administration: str, tax_type: str, tax_code: str,
                     reference_date: date) -> Optional[dict]:
        """Query tax_rates for a specific administration + type + code + date."""
        query = """
            SELECT id, rate, ledger_account, description, calc_method, calc_params,
                   effective_from, effective_to, administration
            FROM tax_rates
            WHERE administration = %s AND tax_type = %s AND tax_code = %s
              AND effective_from <= %s AND effective_to >= %s
            ORDER BY effective_from DESC
            LIMIT 1
        """
        rows = self.db.execute_query(
            query, (administration, tax_type, tax_code, reference_date, reference_date),
            fetch=True
        )
        if not rows:
            return None

        row = rows[0]
        calc_params = row.get('calc_params')
        if isinstance(calc_params, str):
            try:
                calc_params = json.loads(calc_params)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            'id': row['id'],
            'rate': self._to_float(row['rate']),
            'ledger_account': row.get('ledger_account'),
            'description': row.get('description'),
            'calc_method': row.get('calc_method', 'percentage'),
            'calc_params': calc_params,
            'effective_from': row.get('effective_from'),
            'effective_to': row.get('effective_to'),
            'source': 'tenant' if row['administration'] != '_system_' else 'system',
        }

    def _auto_close_overlapping(self, administration: str, tax_type: str,
                                tax_code: str, new_effective_from: date) -> None:
        """
        Auto-close any existing rate whose date range overlaps with new_effective_from.
        Sets existing rate's effective_to to new_effective_from - 1 day.
        """
        close_day = new_effective_from - timedelta(days=1)
        update_sql = """
            UPDATE tax_rates
            SET effective_to = %s
            WHERE administration = %s AND tax_type = %s AND tax_code = %s
              AND effective_from <= %s AND effective_to >= %s
        """
        self.db.execute_query(
            update_sql,
            (close_day, administration, tax_type, tax_code,
             new_effective_from, new_effective_from),
            fetch=False, commit=True
        )

    def _invalidate_cache(self) -> None:
        """Clear the entire cache (tax rates are interrelated)."""
        self._cache.clear()

    @staticmethod
    def _to_float(val) -> float:
        """Convert Decimal or other numeric types to float."""
        if isinstance(val, Decimal):
            return float(val)
        if isinstance(val, (int, float)):
            return float(val)
        return val
