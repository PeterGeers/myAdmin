"""
Unit tests for TaxRateService.

Example-based tests for CRUD, seed data verification, date boundary cases,
and error conditions.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import sys
import os
import pytest
from datetime import date, timedelta
from unittest.mock import Mock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.tax_rate_service import TaxRateService, MAX_DATE


# ---------------------------------------------------------------------------
# Helpers (reuse the mock from props tests)
# ---------------------------------------------------------------------------

def make_row(row_id, admin, tax_type, tax_code, rate, eff_from, eff_to,
             ledger=None, desc=None, calc_method='percentage', calc_params=None):
    return {
        'id': row_id, 'administration': admin,
        'tax_type': tax_type, 'tax_code': tax_code,
        'rate': rate, 'ledger_account': ledger,
        'effective_from': eff_from, 'effective_to': eff_to,
        'description': desc, 'calc_method': calc_method,
        'calc_params': calc_params,
    }


def make_tax_db(rows=None):
    """In-memory mock DB simulating tax_rates table."""
    store = list(rows or [])
    next_id = [max((r['id'] for r in store), default=0) + 1]

    def execute_query(query, params=None, fetch=True, commit=False, pool_type='primary'):
        sql = query.strip().upper()

        if sql.startswith('SELECT') and params and len(params) == 5:
            admin, ttype, tcode, d1, d2 = params
            matches = [
                r for r in store
                if r['administration'] == admin
                and r['tax_type'] == ttype
                and r['tax_code'] == tcode
                and r['effective_from'] <= d1
                and r['effective_to'] >= d2
            ]
            matches.sort(key=lambda r: r['effective_from'], reverse=True)
            return matches[:1] if matches else []

        if sql.startswith('SELECT') and params and len(params) == 4:
            admin, d1, d2, admin2 = params
            matches = [
                r for r in store
                if r['tax_type'] == 'btw'
                and r['administration'] in (admin, '_system_')
                and r['effective_from'] <= d1
                and r['effective_to'] >= d2
            ]
            matches.sort(key=lambda r: (
                r['tax_code'],
                0 if r['administration'] == admin else 1
            ))
            return matches

        if sql.startswith('INSERT') and commit:
            row_id = next_id[0]
            next_id[0] += 1
            (admin, ttype, tcode, rate, ledger, eff_from, eff_to,
             desc, calc_method, calc_params_json, created_by) = params
            store.append({
                'id': row_id, 'administration': admin,
                'tax_type': ttype, 'tax_code': tcode,
                'rate': rate, 'ledger_account': ledger,
                'effective_from': eff_from, 'effective_to': eff_to,
                'description': desc, 'calc_method': calc_method,
                'calc_params': calc_params_json,
            })
            return row_id

        if sql.startswith('UPDATE') and commit:
            close_day, admin, ttype, tcode, new_from, new_from2 = params
            for r in store:
                if (r['administration'] == admin
                        and r['tax_type'] == ttype
                        and r['tax_code'] == tcode
                        and r['effective_from'] <= new_from
                        and r['effective_to'] >= new_from2):
                    r['effective_to'] = close_day
            return None

        if sql.startswith('DELETE') and commit:
            rate_id, admin = params
            before = len(store)
            store[:] = [
                r for r in store
                if not (r['id'] == rate_id and r['administration'] == admin)
            ]
            return before - len(store)

        return []

    db = Mock()
    db.execute_query = Mock(side_effect=execute_query)
    db._store = store
    return db


# ---------------------------------------------------------------------------
# Seed Data Verification
# ---------------------------------------------------------------------------

class TestSeedDataVerification:

    def test_system_btw_rates_resolvable(self):
        """System BTW seed rates (zero, low, high) should be resolvable."""
        rows = [
            make_row(1, '_system_', 'btw', 'zero', 0.0, date(2000, 1, 1), MAX_DATE, '2010',
                     'BTW 0% - Vrijgesteld'),
            make_row(2, '_system_', 'btw', 'low', 9.0, date(2000, 1, 1), MAX_DATE, '2021',
                     'BTW Laag tarief'),
            make_row(3, '_system_', 'btw', 'high', 21.0, date(2000, 1, 1), MAX_DATE, '2020',
                     'BTW Hoog tarief'),
        ]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        today = date(2026, 4, 12)
        zero = svc.get_tax_rate('AnyTenant', 'btw', 'zero', today)
        low = svc.get_tax_rate('AnyTenant', 'btw', 'low', today)
        high = svc.get_tax_rate('AnyTenant', 'btw', 'high', today)

        assert zero['rate'] == 0.0
        assert zero['ledger_account'] == '2010'
        assert low['rate'] == 9.0
        assert low['ledger_account'] == '2021'
        assert high['rate'] == 21.0
        assert high['ledger_account'] == '2020'

    def test_get_all_vat_codes_returns_seed_data(self):
        rows = [
            make_row(1, '_system_', 'btw', 'zero', 0.0, date(2000, 1, 1), MAX_DATE, '2010'),
            make_row(2, '_system_', 'btw', 'low', 9.0, date(2000, 1, 1), MAX_DATE, '2021'),
            make_row(3, '_system_', 'btw', 'high', 21.0, date(2000, 1, 1), MAX_DATE, '2020'),
        ]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        codes = svc.get_all_vat_codes('AnyTenant', date(2026, 1, 1))
        assert len(codes) == 3
        code_set = {c['code'] for c in codes}
        assert code_set == {'zero', 'low', 'high'}


# ---------------------------------------------------------------------------
# Date Boundary Cases
# ---------------------------------------------------------------------------

class TestDateBoundaryCases:

    def test_exact_effective_from_boundary(self):
        rows = [make_row(1, '_system_', 'btw', 'high', 21.0,
                         date(2020, 1, 1), MAX_DATE)]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        assert svc.get_tax_rate('T', 'btw', 'high', date(2020, 1, 1)) is not None
        assert svc.get_tax_rate('T', 'btw', 'high', date(2019, 12, 31)) is None

    def test_exact_effective_to_boundary(self):
        rows = [make_row(1, '_system_', 'btw', 'high', 21.0,
                         date(2020, 1, 1), date(2025, 12, 31))]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        assert svc.get_tax_rate('T', 'btw', 'high', date(2025, 12, 31)) is not None
        assert svc.get_tax_rate('T', 'btw', 'high', date(2026, 1, 1)) is None

    def test_multiple_periods_returns_most_recent(self):
        """When multiple periods match, the most recent effective_from wins."""
        rows = [
            make_row(1, '_system_', 'btw', 'low', 6.0,
                     date(2000, 1, 1), date(2019, 12, 31)),
            make_row(2, '_system_', 'btw', 'low', 9.0,
                     date(2019, 1, 1), MAX_DATE),
        ]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        result = svc.get_tax_rate('T', 'btw', 'low', date(2019, 6, 1))
        assert result['rate'] == 9.0


# ---------------------------------------------------------------------------
# Create Tax Rate
# ---------------------------------------------------------------------------

class TestCreateTaxRate:

    def test_create_returns_id(self):
        db = make_tax_db()
        svc = TaxRateService(db)
        result = svc.create_tax_rate(
            'T1', 'tourist_tax', 'standard', 6.9, date(2026, 1, 1),
            description='Toeristenbelasting 2026', calc_method='percentage'
        )
        assert result is not None

    def test_create_with_default_effective_to(self):
        db = make_tax_db()
        svc = TaxRateService(db)
        svc.create_tax_rate('T1', 'btw', 'high', 21.0, date(2026, 1, 1))

        created = db._store[0]
        assert created['effective_to'] == MAX_DATE

    def test_create_invalid_date_range_raises(self):
        db = make_tax_db()
        svc = TaxRateService(db)
        with pytest.raises(ValueError, match="effective_from.*must be <= effective_to"):
            svc.create_tax_rate(
                'T1', 'btw', 'high', 21.0,
                date(2026, 12, 31), effective_to=date(2026, 1, 1)
            )

    def test_create_auto_closes_overlapping(self):
        rows = [make_row(1, 'T1', 'btw', 'high', 21.0,
                         date(2020, 1, 1), MAX_DATE)]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        svc.create_tax_rate('T1', 'btw', 'high', 25.0, date(2026, 1, 1))

        existing = db._store[0]
        assert existing['effective_to'] == date(2025, 12, 31)

    def test_create_with_calc_params(self):
        db = make_tax_db()
        svc = TaxRateService(db)
        svc.create_tax_rate(
            'T1', 'tourist_tax', 'standard', 6.9, date(2026, 1, 1),
            calc_method='percentage', calc_params={'base': 'revenue_excl_vat'}
        )
        created = db._store[0]
        assert created['calc_params'] is not None

    def test_create_invalidates_cache(self):
        rows = [make_row(1, '_system_', 'btw', 'high', 21.0,
                         date(2000, 1, 1), MAX_DATE)]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        svc.get_tax_rate('T1', 'btw', 'high', date(2025, 6, 1))
        assert len(svc._cache) > 0

        svc.create_tax_rate('T1', 'btw', 'high', 25.0, date(2026, 1, 1))
        assert len(svc._cache) == 0


# ---------------------------------------------------------------------------
# Delete Tax Rate
# ---------------------------------------------------------------------------

class TestDeleteTaxRate:

    def test_delete_tenant_rate(self):
        rows = [make_row(1, 'T1', 'btw', 'high', 25.0,
                         date(2026, 1, 1), MAX_DATE)]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        assert svc.delete_tax_rate(1, 'T1') is True
        assert len(db._store) == 0

    def test_delete_system_rate_raises(self):
        db = make_tax_db()
        svc = TaxRateService(db)
        with pytest.raises(PermissionError, match="System default"):
            svc.delete_tax_rate(1, '_system_')

    def test_delete_nonexistent_returns_false(self):
        db = make_tax_db()
        svc = TaxRateService(db)
        assert svc.delete_tax_rate(999, 'T1') is False

    def test_delete_invalidates_cache(self):
        rows = [make_row(1, 'T1', 'btw', 'high', 25.0,
                         date(2026, 1, 1), MAX_DATE)]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        svc.get_tax_rate('T1', 'btw', 'high', date(2026, 6, 1))
        assert len(svc._cache) > 0

        svc.delete_tax_rate(1, 'T1')
        assert len(svc._cache) == 0


# ---------------------------------------------------------------------------
# Cache Behavior
# ---------------------------------------------------------------------------

class TestTaxRateCacheBehavior:

    def test_cache_hit_avoids_db_query(self):
        rows = [make_row(1, '_system_', 'btw', 'high', 21.0,
                         date(2000, 1, 1), MAX_DATE)]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        svc.get_tax_rate('T1', 'btw', 'high', date(2025, 1, 1))
        calls_after_first = db.execute_query.call_count

        svc.get_tax_rate('T1', 'btw', 'high', date(2025, 1, 1))
        assert db.execute_query.call_count == calls_after_first
